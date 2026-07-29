# Kickoff prompt — arbiter, session 3

Copy everything below the line into a fresh Claude Code session started in
`~/claude/arbiter`.

---

**Project: arbiter — continuing work on the review engine.**

Read `docs/STATE.md` first; it has the commit trail, both head-to-head results,
and why things are the way they are. Then `docs/FINDINGS.md` for the
Tessera-facing channel. This prompt is the short version plus what to do next.

**What this is.** A CLI that runs an adversarial code review over a git ref
range: reviewer → independent second pass → two-voice KEEP/DROP/UNSURE triage →
blocking/advisory output, exiting 1 on a high or critical blocking finding so it
can gate a hook. The pattern
came from `pr-arbiter`, which is now frozen as a research artifact. Positioning
is **cheap and portable**, explicitly not "better than `/code-review`" — the
measurements do not support that and should not be oversold.

**State.** Working, pushed, clean at `github.com/lciacci/arbiter`. Run
`uv run pytest -q && uv run ruff check src tests` — both were green at the last
commit. (No test count here on purpose: the written-down number went stale
within one commit of being corrected, twice. Ask the suite, not the doc.)
The finders can run typed read-only inspection tools (`read_file`, `search`,
`git_diff`, `git_log`) to check claims before reporting; that verification is
on by default and costs roughly 3× a bare run.

**Measured, so don't re-derive it:**
- Cost per file is **not** stable — it ranges 2× with file size, so don't
  estimate in "files changed". Four runs: $0.73 / 2 shell files, $2.74 / 7
  Python files, $1.54 / 3 large Python files, $0.79 / 1 shell file of 287 lines.
  Only *reviewable* files cost anything: conclave changed 114 files, 113 were
  logs and result data, one was reviewed. Full table in `STATE.md` item 2.
- Verification is ~3× and buys filtering, not volume: same finding count, three
  times as many dropped.
- Two head-to-heads against workflow-backed `/code-review` on identical diffs.
  arbiter finds real critical bugs and is not sufficient on a security boundary.
  Round 2: arbiter found 1 RCE in its own allowlist, `/code-review` found 5 more.
  **Both predate the typed-tool rewrite** — there is no comparative number for
  the current build.
- Exit 1 now needs a blocking finding at high or critical (`eef0cdc`). Measured
  cause: three of three blocking findings across two foreign-repo runs were not
  worth stopping a commit for.

**Highest-value next steps, in order:**

1. **Keep using it on real branches.** Done once more on 2026-07-28 against
   conclave's `harness/t1t3-matched-instrument` — see `STATE.md` item 1 for what
   it found and what it got wrong. The blocking tier *is* short enough to read;
   the problem was that it blocked on things not worth blocking for, now fixed.
   Still only two foreign repos. Safe to point at a repo with a live session in
   it: refs are pinned to SHAs at startup, and only committed state is read.
2. **Re-measure quality since the typed-tool rewrite** — partially done, see
   STATE item 1. Two runs, three blocking findings, one wrong in its
   consequence. No head-to-head against `/code-review` on the typed-tool build
   yet, so the comparative standing is still unmeasured.
3. **Get a run cheap and fast enough to be worth automating.** Today a run is
   1–2 minutes and $0.79–$2.74. Nothing that costs a dollar per invocation gets
   run automatically. Unmeasured and worth knowing: the same scope with
   `--no-verify`, and whether `--path`-scoped runs land near $0.10.

**Demoted: wiring it as a git hook.** This was step 2 and it was the wrong
target. Reasons, so it does not get re-promoted by someone reading only the
exit-code table:

- **Cost and latency rule out pre-commit.** 9 commits were made in the session
  that measured this; as a pre-commit hook that is roughly $10 and 15 minutes of
  waiting for one afternoon. You would reach for `git commit --no-verify` on day
  one, and a hook everyone bypasses is worse than no hook — it reads as
  assurance while providing none.
- **The gate has never fired.** After `eef0cdc`, zero of three blocking findings
  were high or critical, so the exit-1 path has not triggered on real code once.
  We know the tier *below* the gate is noisy and know nothing about the tier that
  gates. Wiring an untriggered gate is wiring an untested one.
- **The house rule already covers this.** `CLAUDE.md` on sqlfluff: make it
  blocking "once findings are genuinely real ... not before, since a gate that
  cries wolf gets bypassed." That was written for a linter that costs nothing.
- **The hook adds little.** arbiter is already a command you run before opening a
  PR. A hook only adds *automatic* invocation, which is exactly what makes the
  cost unpredictable. The manual path has the property you want: you choose when
  it is worth a dollar.

If it does get automated, **CI on pull requests, not a local hook** — once per PR
rather than per commit, cost visible and attributable, latency off your keyboard,
and a bad run is a red check to read rather than a blocked commit to fight. And
**non-blocking first** in any venue: report, exit 0, watch for a few weeks.

Flip to blocking when the exit-1 path has fired correctly on a genuine
high/critical defect three or four times *and* a scoped run is under ~15 seconds
and ~$0.10. Cheap and fast are prerequisites for automatic; it is currently
neither.

**Two things to be careful about.**

*The security boundary is young.* `src/arbiter/tools.py` was rewritten on
2026-07-28 and has three live runs behind it, none adversarial. Two independent
reviews of the *previous* design found six holes between them; **the current one
has never been independently reviewed at all.** The argument for it is that it
removed the category — model input never reaches argv, no interpreter, no free
text to a shell — not that it is proven. Use `--no-verify` for code you did not
write; use a container for a PR from a stranger.

*Fail-open is this codebase's recurring defect.* Four instances now, several
written by whoever had just fixed the previous one, each defensive in intent.
The fourth was nearly shipped this session: `_SEV_RANK.get(sev, 0)` was the
obvious thing to reuse for the new severity gate, and its unknown-sorts-last
default would have meant an unparseable severity passes. When adding a fallback
here, ask what a *gate* will conclude from it — if the answer is "pass", it is
wrong. Full list in `STATE.md`, section "Fail-open, the recurring defect".

**Ways of working that earned their keep this session, worth keeping:**

- **Instrument before hypothesising.** Three runs reported 0 blocking; two
  hypotheses were formed and both were wrong; logging the ballot took one commit
  and answered it immediately. The evidence was being computed and discarded.
- **Verify a finding's repro before acting on it.** arbiter's reported defects
  have been reliable; its worked examples and suggested patches have not. On the
  Tessera glob bug it was right about the bug, wrong in one example, and its
  proposed fix would have introduced a different one. Held again on conclave:
  it located a real leak in the watchdog and was wrong about what the leak does.
  **The finder is better at locating than at concluding.**
- **Record refuted hypotheses in the commit message**, not just fixes.
- **Check that a new test fails without its fix.** Two tests written this
  session passed for reasons unrelated to the code they guarded — one asserted
  the pre-fix behaviour outright. Reverting the fix and re-running is cheap.

**Still open, lower priority:** an observatory entry for Tessera on whether hook
payload parsing should be a shared tested helper (`FINDINGS.md` F-001 — second
instance of a class nothing reviews); SQL support, deliberately deferred, not
dropped (thin corpus today, but it is part of what would make this useful to
someone other than its author).

**Communication preferences:** tight, direct, first-person. Push back when I am
wrong. Don't pad. Treat me as senior — I'll ask if I need explanation.
