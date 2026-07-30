# arbiter

A cheap, portable adversarial second opinion on a code change.

```bash
arbiter --base main
```

Three agents run over each changed file:

1. **Reviewer** — adversarial first pass. Tuned to surface issues, not triage them.
2. **Second pass** — an *independent* review that sees the first pass only as
   anti-redundancy context. Additive: it can add findings, never remove them.
3. **Triage** — two source-blind voices vote KEEP / DROP / UNSURE on the merged
   list. Both keep → **blocking**. Both drop → dropped. Mixed → **advisory**.

Output is two tiers. The blocking tier is meant to be short enough that you
actually read it; the advisory tier is where the maybes go. Exit code is 1 when
a blocking finding is high or critical, so it can gate a hook without rejecting
a commit over a cosmetic one.

## Why this exists

Claude Code's `/code-review ultra` is good and does more than this does. It is
also a premium feature, and it only runs inside Claude Code. This is the cheap
version that runs anywhere:

- **Cheap** — the win comes from triage, not from fanning out more agents.
  Four model calls per file plus a few verification turns, and the triage step
  exists specifically to keep the blocking list short instead of long. Every run
  prints its own token count and estimated cost, so this claim stays checkable.
- **Portable** — plain Python against the Anthropic SDK. The client is
  constructed bare, so `ANTHROPIC_BASE_URL` points it at any compatible
  gateway. No Claude Code dependency anywhere in the engine.

It is not trying to beat `ultra` on finding quality. See *Provenance* for what
the numbers behind this pattern actually support.

Working notes: [`docs/STATE.md`](docs/STATE.md) for where this is and how it
got here, [`docs/NEXT_SESSION.md`](docs/NEXT_SESSION.md) to pick it back up.

## Install

Requires Python 3.13+ and `ANTHROPIC_API_KEY` in the environment or a `.env`.

```bash
uv sync
uv run arbiter --help
```

## Usage

```bash
# Review the current branch against main
arbiter --base main

# Review another repo from anywhere
arbiter --repo ~/code/thing --base main

# Review a specific commit range, write markdown
arbiter --base HEAD~3 --head HEAD --out review.md

# Scope to part of the change (repeatable; directory prefixes or globs)
arbiter --path src/arbiter --path 'tests/*.py'

# Cheaper and noisier: skip triage, everything lands advisory
arbiter --no-triage

# Deny the finders the inspection tools — do this for code you do not trust
arbiter --no-verify

# Machine-readable (findings plus the usage record)
arbiter --json
```

Reviews `.py .sh .bash .zsh .ts .tsx .js .jsx .sql` by default. `--ext` overrides.

### Exit codes

| code | meaning |
|-----:|---------|
| 0 | nothing worth stopping for |
| 1 | blocking findings at high or critical — reject |
| 2 | could not run at all (bad ref, not a repo) |
| 3 | ran, but some file failed to review — **not** a pass |

Blocking is checked before failures, so a partial failure can never mask a
confirmed blocking finding behind a softer code. 3 is distinct from 2 so a hook
can tell "reviewed nine of ten files" from "arbiter never started".

**Severity gates as well as agreement.** Triage votes on whether a finding is
*real*, never on whether it is worth stopping for, so `low` used to reject a
commit exactly as hard as `critical`. Measured over two runs, three of three
blocking findings were cosmetic or inapplicable — a label that annotated a SHA
with itself, a portability nit about a macOS version not in use, and a leaked
`sleep` process. As a hook, the old behaviour rejected the commit for all three,
and a gate that cries wolf gets bypassed. Findings below high are reported in
full and still say "blocking" in the report; they
just do not fail the process. A severity that cannot be recognised at all
gates — it is model output, and the safe direction is to stop.

## Verification

The reviewer and second pass can run **read-only** commands to check a claim
before reporting it — run git to see what a diff really contains, grep for a
symbol's other uses, evaluate an expression. This is on by default and it is the
single change that most improved finding quality: on its first run with any
inspection tool at all — the earlier shell version, since replaced — it found
two allowlist bypasses in its own newly-written security code.

The model chooses what to inspect after reading a diff, and a diff can contain
text written by someone else, so this is a prompt-injection surface.

The tools are **typed, not a shell**. An earlier version took a command string
and allowlisted `argv[0]`; an independent review found five confirmed ways
through it, including `python3 -c` (a whole interpreter), a repo-supplied binary
whose basename matched the allowlist, and `sed -i.bak` writing to the tree.
Enumerating dangerous invocations of general-purpose Unix tools does not work.

Now the model supplies parameters — `read_file(path, ref)`, `search(pattern,
path, ref)`, `git_diff(base, head, path)`, `git_log(path, limit)` — and the
argument vector is built here. There is no position where model input becomes a
binary or a flag: paths and refs are rejected if they are absolute, contain
`..`, or begin with `-`, and search patterns go through `-e` so they cannot be
read as options. Everything reads through git at a pinned ref, so a finder
cannot confirm a claim against a working tree that differs from the code under
review. See `src/arbiter/tools.py`.

`--base` and `--head` are resolved to commit SHAs once at startup, so the ref is
pinned in time as well: it is safe to review a repo someone else is actively
committing to, and the report records the SHAs it actually read. Uncommitted
work is never reviewed — everything comes from git, nothing from the working
tree.

**This boundary is young.** `tools.py` was rewritten on 2026-07-28 and has three
live runs behind it, none of them adversarial. Two independent reviews of the
*previous* design found six holes between them; **the current design has never
been independently reviewed at all.** The argument for it is that it removes the
category — model input never reaches argv, no interpreter, no free text to a
shell — not that it has been proven in use.

**Reviewing a PR from someone you do not trust: use `--no-verify`, or run it in
a container.**

## Provenance, and what the numbers do and don't say

The pattern comes from [pr-arbiter](https://github.com/lciacci/pr-arbiter), a
research POC that measured it against a 20-PR corpus of planted bugs. Read the
result honestly before trusting this tool more than it has earned:

- Phase 1: the multi-agent config caught **7/8 criticals vs 6/8** for the best
  single-agent reviewer, at comparable precision — **one seed**.
- Phase 2: ported to code generation, the effect **largely vanished under
  3-seed variance** — 34/39 vs 32/39 across 39 runs.

So: the architecture is directionally useful and thinly evidenced. The reason to
run it is cost and portability, not a claim that it out-finds the alternatives.
All of that was measured on Sonnet 4.6.

## Cost

Every run reports its own usage, to stderr and at the foot of the report:

```
<N> model calls · <in> in (<pct>% cached) / <out> out tokens · ~$<estimate>
```

`<in>` is the whole prompt across every call, not the part that was billed at
full rate — `input_tokens` alone is the *uncached remainder*, and reporting that
would make the token total shrink for the same reason the cost does. The
percentage is what was served from cache; a run that reports 0% across repeated
calls means something is invalidating the prefix, not that caching is off.

Four measured runs, all with verification on. **All four predate prompt
caching** — see below; expect a run today to come in cheaper than these:

| repo | scope | calls | cost | per file |
|---|---|--:|--:|--:|
| tessera | 2 shell files | 24 | $0.73 | $0.37 |
| tessera | 7 Python files | — | $2.74 | $0.39 |
| arbiter | 3 large Python files | 34 | $1.54 | $0.51 |
| conclave | 1 shell file, 287 lines | 12 | $0.79 | **$0.79** |

**Per-file cost is not stable — it ranges 2× with file size**, so "files changed"
is the wrong unit to estimate in. A 20-file branch is somewhere between $7 and
$15 depending on how big those files are. Note also that only *reviewable* files
cost anything: the conclave branch changed 114 files, but 113 were logs and
result data, so one file was reviewed and the run cost $0.79.

Verification is most of the spend; it triples the call count (~12 calls per file
rather than 4) because every turn resends the conversation. What that 3× buys is
**filtering, not volume** — the same number of findings, but roughly three times
as many of them dropped by triage. Run it and read the line rather than trusting
these.

**Prompt caching takes most of that resend cost back.** The finders' system
prompt and tool definitions are cached together, and so is the verification
transcript, so turn N reads turns 1..N−1 instead of re-paying for them. Measured
end-to-end on one 230-line Python file, `--jobs 1`: 6 calls, 75,552 prompt
tokens, **50% served from cache, $0.17** — against $0.24 for the same token
count at full input rate, so about 29% off. The savings scale with how many
verification turns a file provokes, and dilute on files that produce findings,
since the two triage calls are not cached (their prefix measures 1017 and 1024
tokens against a 1024-token minimum — a marker there would cache nothing).

Pricing is indicative list price (`PRICE_IN_PER_MTOK` in `client.py`) and will
drift; treat it as "cents or dollars", not an invoice. Drivers, in order:

- **File size.** The whole before- and after-state go in every call, so one
  200KB file can cost more than twenty small ones. `--path` is the lever.
- **Verification turns.** Each turn resends the conversation. `--no-verify`
  removes them and roughly halves a run.
- **Triage.** Two extra calls per file with findings. `--no-triage` removes them
  at the cost of the blocking/advisory split — which is the point of the tool.

## Known limits

- **Per-file review.** Agents see one file at a time and cannot reason across
  files in the same change. Worth knowing, but measurably *not* the binding
  constraint: in the head-to-head below, every defect arbiter missed sat inside
  a single file, most within twenty lines of itself. Tool access was the gap,
  not context.
- **False positives on request-derived-input findings** — partially addressed.
  The reviewer now has to trace where an attacker-controlled value actually
  enters before reporting an injection-class finding. Whether that holds up
  outside this repo is untested.
- **Extension sniffing misses extensionless shell scripts** (git hooks,
  `scripts/gate`). Pass explicit paths if you care about those.
- **No incremental caching and no cost cap.** A large branch can be expensive
  and nothing stops it mid-run.
- **Not a substitute for a heavier review.** Measured head-to-head against a
  31-agent workflow review on the same diff, arbiter found 2 of its 3 real
  defects and missed 8 others. It is a cheap first pass, and it is honest about
  being one.
