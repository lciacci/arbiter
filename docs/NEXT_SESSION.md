# Kickoff prompt — arbiter, session 2

Copy everything below the line into a fresh Claude Code session started in
`~/claude/arbiter`.

---

**Project: arbiter — continuing work on the review engine.**

Read `docs/STATE.md` first; it has the commit trail, both head-to-head results,
and why things are the way they are. Then `docs/FINDINGS.md` for the
Tessera-facing channel. This prompt is the short version plus what to do next.

**What this is.** A CLI that runs an adversarial code review over a git ref
range: reviewer → independent second pass → two-voice KEEP/DROP/UNSURE triage →
blocking/advisory output, exiting non-zero so it can gate a hook. The pattern
came from `pr-arbiter`, which is now frozen as a research artifact. Positioning
is **cheap and portable**, explicitly not "better than `/code-review`" — the
measurements do not support that and should not be oversold.

**State.** Working, pushed, clean at `github.com/lciacci/arbiter`. 231 tests.
The finders can run typed read-only inspection tools (`read_file`, `search`,
`git_diff`, `git_log`) to check claims before reporting; that verification is
on by default and costs roughly 3× a bare run.

**Measured, so don't re-derive it:**
- ~$0.72 for 2 shell files, ~$2.74 for 7 Python files. Verification is ~3× and
  buys filtering, not volume: same finding count, three times as many dropped.
- Two head-to-heads against workflow-backed `/code-review` on identical diffs.
  arbiter finds real critical bugs and is not sufficient on a security boundary.
  Round 2: arbiter found 1 RCE in its own allowlist, `/code-review` found 5 more.

**Highest-value next steps, in order:**

1. **Use it on a real branch** in `tessera` or `conclave` and judge whether the
   blocking tier is short enough to actually read. It has had one run against a
   repo that is not itself. It has been reviewed harder than it has been used,
   and that is the wrong ratio.
2. **Wire it as a git hook.** The exit codes were designed for it (1 blocking,
   2 could-not-run, 3 partial failure) and it has never been run that way.
3. **Re-measure quality since the typed-tool rewrite.** Every head-to-head so
   far used the old shell tool or none, so the current standing is unmeasured.

**Two things to be careful about.**

*The security boundary is young.* `src/arbiter/tools.py` was rewritten on
2026-07-28 and has had one live run. Two independent reviews of the *previous*
design found six holes between them. The argument for the new one is that it
removed the category — model input never reaches argv, no interpreter, no free
text to a shell — not that it is proven. Use `--no-verify` for code you did not
write; use a container for a PR from a stranger.

*Fail-open is this codebase's recurring defect.* Three instances so far, twice
written by whoever had just fixed the previous one: a `{}` return that read as
"no findings", a swallowed `GitError` that read as "new file", a triage default
that turned total ballot failure into "nothing blocking". Each was written
defensively. When adding a fallback here, ask what a *gate* will conclude from
it — if the answer is "pass", it is wrong. `docs/FINDINGS.md` ARB-001.

**Ways of working that earned their keep this session, worth keeping:**

- **Instrument before hypothesising.** Three runs reported 0 blocking; two
  hypotheses were formed and both were wrong; logging the ballot took one commit
  and answered it immediately. The evidence was being computed and discarded.
- **Verify a finding's repro before acting on it.** arbiter's reported defects
  have been reliable; its worked examples and suggested patches have not. On the
  Tessera glob bug it was right about the bug, wrong in one example, and its
  proposed fix would have introduced a different one.
- **Record refuted hypotheses in the commit message**, not just fixes.

**Still open, lower priority:** an observatory entry for Tessera on whether hook
payload parsing should be a shared tested helper (`FINDINGS.md` F-001 — second
instance of a class nothing reviews); SQL support, deliberately deferred, not
dropped (thin corpus today, but it is part of what would make this useful to
someone other than its author).

**Communication preferences:** tight, direct, first-person. Push back when I am
wrong. Don't pad. Treat me as senior — I'll ask if I need explanation.
