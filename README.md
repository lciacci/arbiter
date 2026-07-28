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
  Four model calls per file, and the triage step exists specifically to keep the
  blocking list short instead of long.
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

# Cheaper and noisier: skip triage, everything lands advisory
arbiter --no-triage

# Machine-readable
arbiter --json
```

Reviews `.py .sh .bash .zsh .ts .tsx .js .jsx .sql` by default. `--ext` overrides.

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

## Known limits

- **Per-file review.** Agents see one file at a time and cannot reason across
  files in the same change. Inherited from pr-arbiter; the main real ceiling.
- **False positives on request-derived-input findings.** The reviewer prompt
  assumes untrusted input reaches the sink. On config-driven or local-only code
  it over-flags SQL injection and path traversal. Fixing this — threat-model
  context in the prompt — is the top item.
- **Extension sniffing misses extensionless shell scripts** (git hooks,
  `scripts/gate`). Pass explicit paths if you care about those.
- **No cross-file or repo-level context**, no incremental caching, no cost cap.
