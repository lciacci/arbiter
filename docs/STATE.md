# Where this is, 2026-07-28

Written at a pause. Everything below is committed and pushed to
`github.com/lciacci/arbiter`. Nothing is half-applied.

## What arbiter is

The reviewer + independent second pass + mutual triage pattern from
[pr-arbiter](https://github.com/lciacci/pr-arbiter), extracted as a tool that
runs on a real git ref range. pr-arbiter is frozen as a research artifact; this
is where the work continues.

Positioning is **cheap and portable**, not "better than the alternative". That
distinction is load-bearing and the measurements below support it.

## Commit trail

| commit | what |
|---|---|
| `83dd5a7` | port of the engine; triage wired in (pr-arbiter never called it), shell + TS reviewed, `lang_fence` bug fixed |
| `0a9aacd` | root commits reviewable; `--path` filter |
| `26d4c55` | four defects arbiter found in its own first self-review |
| `d91e4c7` | six defects `/code-review` found that arbiter had twice called clean |
| `c5f6f78` | read-only shell for the finders; rationale on the triage ballot; threat-model context |
| `48283aa` | two allowlist bypasses + two API-protocol bugs, found by arbiter's first verified run |
| (this) | usage metering, README |

## The measurement that matters

A workflow-backed `/code-review` (31 agents, 1.3M tokens, ~9 min) and arbiter
(~4 calls/file, ~2 min) reviewed the **same diff**:

- Both found: the exit-code collision, the too-narrow exception catch.
- arbiter alone: `validate` not enforcing `rationale`.
- **`/code-review` alone: eight further defects**, including that arbiter's own
  rename fix was half-applied — the diff pathspec still named one side, so git
  emitted an all-added "new file" diff contradicting the before-state.

arbiter had reviewed that file twice and reported it clean both times.

### Why it missed them

Not context. Every missed defect was inside one file, most within twenty lines
of itself. The gap was that the workflow's agents **ran git in scratch repos and
introspected the installed SDK**, while arbiter's could only reason from text.
Knowing that pathspec filtering defeats rename detection is not derivable from
reading Python.

Secondary: arbiter reviewed the file *after* applying its own recommended fix,
saw its own remedy present, and stopped — it checked that the fix was there, not
that it was sufficient.

### What changed as a result

`c5f6f78` gave the finders a read-only shell. First run with it enabled found
four defects in code written twenty minutes earlier, **two of them security
bypasses in the allowlist itself** (`git --exec-path=…` slipping the subcommand
check; `HEAD~1:../etc/passwd` slipping the path check). It also caught that a
prompt patch in that same commit had silently matched nothing.

That is the strongest single piece of evidence in this repo: same architecture,
same model, same call count, plus a shell → qualitatively different findings.

## Open, in priority order

1. **Re-run the head-to-head.** Same diff, arbiter-with-verification vs
   `/code-review`. The earlier comparison predates the tool, so the current
   quality gap is unmeasured. This is the cheap experiment that settles whether
   the tool changed the standing or just the anecdotes.
2. **Cost, first real measurement:** 2 shell files in tessera →
   **24 model calls, 185k in / 12k out, $0.73**. That is ~12 calls per file, not
   4 — verification triples the call count, since every turn resends the
   conversation. ~$0.37/file, so a 20-file branch is ~$7. Earlier input-only
   estimates were 9x low. Still unmeasured: the same scope with `--no-verify`,
   which is the number that says whether verification is worth 3x.
3. **Tessera seams.** `docs/FINDINGS.md` exists and is empty — that is the S5
   feedback seam. And the canonical contract
   (`~/claude/tessera/docs/contracts/three-project-cohesion.md`) still gates S4
   on "pr-arbiter Phase 3", which is void; it should point here instead. D4
   ("should pr-arbiter adopt `.tessera/`") is moot for pr-arbiter and answered
   for this repo — it adopted at scaffold.
4. **The eight defects the workflow found are fixed; its *class* of finding is
   not covered by tests.** Rename/copy handling has unit coverage now; the
   verification loop's protocol handling does not.
5. **Deferred, recorded, not dropped:** SQL support. Thin surface today (one
   `.sql` file across all active repos, already linted by sqlfluff in the repo
   that owns it), but it is part of what would make this useful to someone other
   than its author.

6. **Triage was broken and is now fixed** — see below. Resolved, kept here
   because the *way* it was found is the transferable part.

## The triage bug, and two wrong diagnoses before it

Three consecutive runs reported **0 blocking / 8 advisory / 0 dropped**. Two
hypotheses were formed and both were wrong:

1. The "drop a finding whose rationale hedges" instruction was suppressing
   votes. Fixed it, re-ran, identical distribution. Refuted.
2. Blocking requires unanimity between a deliberately recall-oriented voice and
   a deliberately skeptical one, so on real code they never converge. Also
   wrong.

Both were inferences from output, because the votes were computed and thrown
away. Logging the ballot took one commit and answered it immediately: the votes
read `"missing or malformed vote"` — the internal fallback string. The voices had
never been heard at all.

Cause: the model returns `votes` as a JSON **string** rather than an array, and
that string is itself invalid JSON. Rationales quote the code under review, so a
finding about the shell glob `*'"source"'*'"startup"'*` puts single quotes,
double quotes and backslashes into the payload and the escaping does not
survive. Iterating the string yielded characters, none matched the dict guard,
and every finding fell to UNSURE.

The UNSURE default existed so a parse failure could not silently delete a
finding. It did something worse — it turned total triage failure into "both
voices unsure" → everything advisory → **zero blocking, reported as a clean
review**. The same fail-open shape already fixed in the finder path, left in the
triage path.

After the fix, same scope, same cost:

| | ballot | blocking / advisory / dropped |
|---|---|---|
| before | `unsure/unsure=5` (parse failures) | 0 / 8 / 0 |
| after | `keep/keep=4, drop/drop=3, keep/drop=1, keep/unsure=1` | **4 / 2 / 3** |

Zero `unsure/unsure` remained. Triage discriminates: a third of findings dropped
outright, which is the precision lever the architecture exists for.

**Transferable lesson: instrument before hypothesising.** Two rounds of
reasoning cost more than the one commit that logged the evidence.

## First run against a foreign repo

Done, and it found a real bug. In `tessera`'s
`.claude/scripts/icpg-session-base.sh`, the jq-absent fallback matches
`*'"source"'*'"startup"'*`, which does not require `startup` to be `source`'s
own value. Verified: a payload of `{"source":"compact","event":"startup"}`
resolves to `SOURCE=startup` and triggers the re-anchor the guard exists to
prevent. Reachability depends on another field carrying the string, and the
fallback only fires when jq is missing — but the logic is wrong regardless.

That is the class tessera's own postmortem says it cannot self-detect, found in
shell, on the first try, for $0.73.

## What has never been run

- arbiter as a git hook, despite the exit codes being designed for it.
- A head-to-head since verification landed — the comparison that made arbiter
  look weak predates the tool.
