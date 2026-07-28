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
anything blocking was found, so it can gate a hook.

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

# Deny the finders the shell tool — do this for code you do not trust
arbiter --no-verify

# Machine-readable (findings plus the usage record)
arbiter --json
```

Reviews `.py .sh .bash .zsh .ts .tsx .js .jsx .sql` by default. `--ext` overrides.

### Exit codes

| code | meaning |
|-----:|---------|
| 0 | reviewed clean |
| 1 | blocking findings — reject |
| 2 | could not run at all (bad ref, not a repo) |
| 3 | ran, but some file failed to review — **not** a pass |

Blocking is checked before failures, so a partial failure can never mask a
confirmed blocking finding behind a softer code. 3 is distinct from 2 so a hook
can tell "reviewed nine of ten files" from "arbiter never started".

## Verification

The reviewer and second pass can run **read-only** commands to check a claim
before reporting it — run git to see what a diff really contains, grep for a
symbol's other uses, evaluate an expression. This is on by default and it is the
single change that most improved finding quality: on its first run with the tool
enabled it found two allowlist bypasses in its own newly-written security code.

The model chooses those commands after reading a diff, and a diff can contain
text written by someone else, so it is a prompt-injection surface. It is an
allowlist, not a sandbox: allowlisted binaries only, `git` restricted to
read-only subcommands with no global options (`--exec-path` and `-c` are code
execution), argv passed without a shell so `;` and `|` are inert, paths confined
to the repo, `python3`/`sed`/`awk` limited to inline scripts so code under review
is never executed, plus a timeout and output cap. See `src/arbiter/tools.py`.

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
<N> model calls · <in> in / <out> out tokens · ~$<estimate>
```

No representative figure is quoted here on purpose — it depends entirely on how
much code you point it at, and a number invented for a README is worse than none.
Run it on your own diff and read the line.

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
