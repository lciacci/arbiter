# CLAUDE.md — arbiter

Project-specific guidance for Claude Code working in this repo.

## What this is

A CLI that runs an adversarial code review over a git ref range: reviewer →
independent second pass → two-voice KEEP/DROP/UNSURE triage → blocking/advisory
output, exiting 1 on a high or critical blocking finding so it can gate a hook.
Positioning is **cheap and portable**, explicitly not "better than
`/code-review`" — the measurements do not support that and should not be
oversold.

`docs/STATE.md` for how it got here and what has been measured,
`docs/NEXT_SESSION.md` to pick it back up.

- **Tessera profile:** `standard` (see `.tessera/project.yml`).

## Working conventions

How the project owner works. The most important section.

- **Push back when you see drift.** Don't perform agreement. If a decision seems wrong or an
  assumption seems loaded, surface it — as honest feedback, not a refusal.
- **"Batching" is a one-word signal.** It means you're bundling decisions into prose instead of
  surfacing them as numbered choices. Stop, list the decisions, ask before committing.
- **Surface decisions before committing them.** Multi-step or irreversible changes warrant a
  brief "here's what I'd do, OK to proceed?" This is an accepted *convention* — it shapes how
  the model works, which principle #17 permits.
- **Also record each surfaced gate — a separate step, now backstopped.**
  `python3 scripts/gate/emit.py --fired --kind <kind> --note "<what you proposed>"` (use
  `--held` if you weighed surfacing one and decided against). This is Tessera principle #12 (the
  suggestion-gate); the log is a reviewable journal of gate decisions. Recording used to ride
  pure model recall and missed ~85% of gates; a Stop hook (`.claude/scripts/tessera-gate-scan.sh`
  → `scripts/gate/scan.py`) now counts gate-shaped turns in the transcript, diffs them against
  the session's gate log, and exits 2 on a gap so you must adjudicate before finishing.
  **Its detector is a recall net, not an oracle — you are the precision filter.** When it fires,
  log the gates you genuinely surfaced and say plainly which detected turns were only clarifying
  questions. It stays quiet on a gap of 1, so keep logging as you go.
  Contract: the gate-event contract in the Tessera framework.
- **When you are blocked and cannot proceed, raise an escalation — do not just say so and stop.**
  `tessera-escalate raise --category <cat> --summary "<what is stuck>" --tried "<attempt — how it
  failed>" --option "<what to choose between>"` (if `tessera/bin` is not on your PATH, use
  `python3 scripts/tessera-escalate`). This is the suggestion-gate's *asynchronous* form:
  principle #12 needs a human to dispose, and one is not always there. `--tried` is required — a
  packet with no attempts is a complaint, not an escalation. Resolve with `tessera-escalate
  resolve <id> --note "<the decision>"`. Contract: the escalation contract in Tessera.
- **Use numbered lists for decision points.** Binary A/B beats a dense paragraph with embedded
  choices.
- **Name biases you notice in your own reasoning** — confirmation, sunk-cost, excitement,
  familiarity, anchoring. Honesty about bias is part of the trail.
- **Brief acknowledgments.** "Done," "Confirmed," "Clean" — not "Excellent! Great choice!"
- **Flag confidence levels.** Be explicit about what you know vs. infer vs. guess.
- **Tone is direct, not performative.** No witty-coworker framing.

## Hook lifecycle (Mnemos)

The hooks in `.claude/settings.json` invoke scripts in `.claude/scripts/`:

- **SessionStart** — `mnemos-session-start.sh` loads any prior checkpoint
- **PreCompact** — `mnemos-pre-compact.sh` writes an emergency checkpoint before compaction
- **PreToolUse** — `mnemos-post-compact-inject.sh` checks for post-compaction restore;
  `mnemos-pre-edit.sh` (Edit/Write) checks fatigue + intent
- **PostToolUse** — `mnemos-post-tool.sh` logs tool outcomes
- **Stop** — `mnemos-stop-checkpoint.sh` checkpoints; `mnemos-stop-ingest.sh` ingests the
  transcript + scores haze

When you see `MNEMOS CHECKPOINT` in context, a hook injected it — announce briefly, resume from
it, don't re-derive. If no checkpoint fires on resume but `.mnemos/` exists, run `mnemos resume`.

Requires the `mnemos` CLI on PATH (pip-installed globally). Hooks degrade gracefully without it.

## Findings channel — how friction gets back to the framework

`docs/FINDINGS.md` is this project's channel to Tessera. When the *framework* gets in your way
here — a hook that misfires, a guard that blocks the wrong thing, a convention that does not fit
this stack — write it up as `## F-NNN — Title` with a `**Status:**` line
(`open` | `transferred:<ref>` | `rejected:<reason>`).

It is scanned by `tessera-findings` and surfaced in the framework's SessionStart, so an open
finding is seen without anyone remembering to look. **An empty channel is meaningfully different
from a missing file** — the scanner distinguishes them, so never delete it when it has no
findings.

Framework-level fixes land in the Tessera repo, not here. This file is where they get staged.

## SQL

If this project has `.sql` files, `scripts/sql/lint.sh` runs from `.githooks/pre-commit`
(ADR-0012). It is **warn-only** and silent unless the commit stages `.sql`, so it costs nothing
in projects without any — but it does shout if sqlfluff cannot run at all, because a linter that
silently skips looks exactly like one that passed.

Set `dialect` in `.sqlfluff` — the shipped default is `ansi`, and guessing wrong makes every rule
lie. `exclude_rules = layout` is deliberate: stock sqlfluff output measured 89% whitespace on the
first real corpus. To make it blocking once findings are genuinely real, change the script's
final `exit 0` to `exit 1` — not before, since a gate that cries wolf gets bypassed.

## Don't

- Don't modify `.env` / `.env.*` (also denied in settings.json)
- Don't add dependencies without checking existing ones cover the need
- Don't commit secrets
- Don't delete `docs/FINDINGS.md` when it is empty — empty ≠ missing

## Commands

```bash
uv sync                          # install, including the dev group
uv run pytest -q                 # the whole suite; no API calls, ~1s
uv run ruff check src tests      # lint; config in pyproject.toml
uv run arbiter --help
uv run arbiter --base main       # review the current branch — THIS COSTS MONEY
```

`arbiter` makes real API calls and there is no cost cap. A run is cents to a few
dollars depending on how much code it is pointed at — see the cost table in
`README.md`. Don't run it speculatively; `--path` is the lever for scoping, and
`--no-verify` roughly halves a run.
