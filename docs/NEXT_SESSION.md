# Kickoff prompt — arbiter, session 3

Copy everything below the line into a fresh Claude Code session started in
`~/claude/arbiter`.

---

**Project: arbiter — continuing work on the review engine.**

Read `docs/STATE.md` first; it has the annotated commit trail, both head-to-head
results, and why things are the way they are. Then `docs/FINDINGS.md` for the
Tessera-facing channel. This prompt is the short version plus what to do next.

**What this is.** A CLI that runs an adversarial code review over a git ref
range: reviewer → independent second pass → two-voice KEEP/DROP/UNSURE triage →
blocking/advisory output. Exit 1 on a blocking finding at high or critical. The
pattern came from `pr-arbiter`, now frozen as a research artifact. Positioning is
**cheap and portable**, explicitly not "better than `/code-review`" — the
measurements do not support that and should not be oversold.

**State.** Working, pushed, clean at `github.com/lciacci/arbiter`. Run
`uv run pytest -q && uv run ruff check src tests` — both green at the last
commit. (No test count written here on purpose; see *doc rot* below.) The
finders can run typed read-only inspection tools (`read_file`, `search`,
`git_diff`, `git_log`) to check claims before reporting; verification is on by
default and costs roughly 3× a bare run.

**Measured, so don't re-derive it:**

- **Cost per file is not stable** — it ranges 2× with file size, so don't
  estimate in "files changed". Four runs: $0.73 / 2 shell files, $2.74 / 7
  Python files, $1.54 / 3 large Python files, $0.79 / 1 shell file of 287 lines.
  Only *reviewable* files cost anything: conclave changed 114 files, 113 were
  logs and result data, one was reviewed. Table in `STATE.md` item 2.
- Verification is ~3× and buys **filtering, not volume**: same finding count,
  three times as many dropped by triage.
- Two head-to-heads against workflow-backed `/code-review` on identical diffs.
  arbiter finds real critical bugs and is not sufficient on a security boundary.
  Round 2: arbiter found 1 RCE in its own allowlist, `/code-review` found 5 more.
  **Both predate the typed-tool rewrite** — no comparative number exists for the
  current build.
- Exit 1 needs high or critical (`eef0cdc`). Cause: three of three blocking
  findings across two foreign-repo runs were not worth stopping a commit for.

**Highest-value next steps, in order:**

1. **Keep using it on real branches.** Two foreign repos so far (tessera,
   conclave) — that is the binding constraint, and it has still been reviewed
   harder than it has been used. Safe to point at a repo with a live session in
   it: refs are pinned to SHAs at startup and only committed state is read.
2. **Re-measure quality since the typed-tool rewrite.** Partially done — see
   `STATE.md` item 1 for the two runs and all three findings with verdicts. No
   head-to-head against `/code-review` on the current build, so the comparative
   standing is unmeasured.
3. **Get a run cheap and fast enough to be worth automating.** Partly done.
   Prompt caching landed 2026-07-30 and takes back ~29% on a verified run
   (measured: 1 file, 6 calls, 75,552 prompt tokens, 50% cached, $0.17), so the
   $0.79–$2.74 table in `STATE.md` is now an upper bound. Triage is
   deliberately uncached — its prefix measures 1017/1024 tokens against a
   1024-token minimum, and a marker that caches nothing reads as done. Still
   unmeasured: **the same scope with `--no-verify`**, and whether
   `--path`-scoped runs land near $0.10.
   **Do not spend a session on a cheaper finder model — conclave measured it and
   it is dead:** a local 30B scores 0.073 recall / 0-of-8 criticals on *this
   project's own corpus* against claude's 0.509, while matching a hosted 80B on
   edit-and-apply. Task shape, not model tier. Full account in `STATE.md` item 2.

**Demoted, deliberately: wiring it as a git hook.** It was step 2 and it was the
wrong target. Reasons are in full in `STATE.md` under "What has never been run",
recorded so it does not get re-promoted by someone reading only the exit-code
table. Short version: 9 commits in one session means a pre-commit hook costs ~$10
and ~15 minutes of waiting per afternoon, so `--no-verify` becomes reflexive and
a bypassed hook is worse than no hook; and the exit-1 path has never fired on
real code, so its precision at the tier that gates is unmeasured. If it is ever
automated: **CI on pull requests, not a local hook, and non-blocking first.**
Flip to blocking once exit-1 has fired correctly on a genuine high/critical
defect three or four times *and* a scoped run is under ~15s and ~$0.10.

**Three things to be careful about.**

*The security boundary is young.* `src/arbiter/tools.py` was rewritten on
2026-07-28 and has three live runs behind it, none adversarial. Two independent
reviews of the *previous* design found six holes between them; **the current one
has never been independently reviewed at all.** The argument for it is that it
removed the category — model input never reaches argv, no interpreter, no free
text to a shell — not that it is proven. Use `--no-verify` for code you did not
write; use a container for a PR from a stranger.

*Fail-open is this codebase's recurring defect.* Four instances, several written
by whoever had just fixed the previous one, each defensive in intent. The fourth
was nearly shipped in session 2: `_SEV_RANK.get(sev, 0)` was the obvious thing to
reuse for the new severity gate, and its unknown-sorts-last default would have
meant an unparseable severity passes. **When adding a fallback here, ask what a
*gate* will conclude from it — if the answer is "pass", it is wrong.** Full list
in `STATE.md`, "Fail-open, the recurring defect".

*The instrument needs the same scrutiny as the thing it measures.* The triage
ballot — added specifically to diagnose missing votes — was built with
`zip(merged, rv, av)` and so silently omitted the findings whose votes went
missing. Third instance of that shape in that one function. Nothing had reviewed
it because it was "only logging". Found by ruff (B905), fixed in `db50d16`.

**Ways of working that have earned their keep. Keep doing these:**

- **Instrument before hypothesising.** Three runs reported 0 blocking; two
  hypotheses were formed and both were wrong; logging the ballot took one commit
  and answered it immediately. The evidence was being computed and discarded.
- **Verify a finding's repro before acting on it.** arbiter's reported defects
  have been reliable; its worked examples and proposed fixes have not. On the
  Tessera glob bug it was right about the bug and wrong in one example. On
  conclave it located a real leak in a watchdog and was wrong about what the leak
  does. **The finder is better at locating than at concluding** — take the
  location, re-derive the consequence.
- **Check that a new test fails without its fix.** Two tests written in session 2
  passed for reasons unrelated to the code they guarded; one asserted the pre-fix
  behaviour outright. Reverting the fix and re-running is cheap and caught both.
- **Record refuted hypotheses in the commit message**, not just fixes. The two
  wrong triage diagnoses and the refuted watchdog consequence are in the history
  on purpose.
- **Don't hand-write facts a command can answer** — *doc rot*. The test count went
  stale twice (231 while the suite was at 247; 247 within one commit of being
  corrected). The commit trail went 15 behind in a day, then 6 behind within an
  hour of being fixed. Both are now either removed or declared curated with
  `git log` authoritative. Prefer a command in the doc over a number in the doc.
  **The published page is the copy nothing scans.** `docs/promo/index.html` (live
  at `houseofyeti.com`) restates the four-run cost table, the extensionless-file
  bug as OPEN, "the security boundary has never been independently reviewed", and
  "the hook is deliberately unwired". Fixing the START HERE item below flips the
  second one false — re-read the page when it lands, and it is deployed by sftp,
  so a commit here does not update the site.

**START HERE — reviews are silently narrower than they claim (2026-07-29).**
`is_reviewable()` filters on file extension, so extensionless shebang scripts are
dropped and **nothing in the output says so**. Two runs against tessera printed
"1 file(s) reviewed · 0 blocking" having never opened the file under review;
re-run with `--ext ""` the same diffs produced two blocking findings, one of them
real and fixed. `--path` cannot rescue it — `is_reviewable` runs before
`matches_any` in `change_units()`, so the docstring's own advice ("pass an
explicit path list") is not honoured by the CLI.

This is item 7 in `STATE.md`'s priority list and instance 5 under *Fail-open*.
It outranks the quality questions: a review narrower than it claims makes every
clean result unfalsifiable, and this tool's whole value is that a green means
something. **Do the cheapest part first — print what was skipped.** Even with the
filter unchanged, an announced skip is a ceiling; an unannounced one is a false
green. Then make `--path` authoritative, then detect by shebang.

**Still open, lower priority:** an observatory entry for Tessera on whether hook
payload parsing should be a shared tested helper (`FINDINGS.md` F-001 — second
instance of a class nothing reviews); SQL support, deliberately deferred, not
dropped (thin corpus today, but part of what would make this useful to someone
other than its author).

**Communication preferences:** tight, direct, first-person. Push back when I am
wrong — session 2 ended with the assistant arguing against its own prior
recommendation on the git hook, and that was the right call. Don't pad. Treat me
as senior; I'll ask if I need explanation.
