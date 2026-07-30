# Where this is, 2026-07-28 (updated after the first foreign-repo runs)

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

**Curated, not exhaustive — `git log` is authoritative.** An earlier version of
this table tried to mirror every commit and was fifteen behind within a day,
then six behind within an hour of being corrected. The value here is the
annotation, not the completeness; pure `docs:` commits are left out.

| commit | what |
|---|---|
| `83dd5a7` | port of the engine; triage wired in (pr-arbiter never called it), shell + TS reviewed, `lang_fence` bug fixed |
| `0a9aacd` | root commits reviewable; `--path` filter |
| `26d4c55` | four defects arbiter found in its own first self-review |
| `d91e4c7` | six defects `/code-review` found that arbiter had twice called clean |
| `c5f6f78` | read-only shell for the finders; rationale on the triage ballot; threat-model context |
| `48283aa` | two allowlist bypasses + two API-protocol bugs, found by arbiter's first verified run |
| `1c7722a` | usage metering, README |
| `e60d3e5` | first foreign-repo run and the real cost per file |
| `ff817fd` | separate bounding from undermining in triage; retain the ballot |
| `fbf3829` | recover malformed triage ballots instead of silently voting UNSURE |
| `7540e9b` | the triage bug and the two wrong diagnoses before it |
| `049aa51` | an RCE in the allowlist closed; ballot salvage hardened |
| `443c2c0` | **the shell allowlist replaced with typed tools** |
| `294645d` | merge-base control, honest dispatch errors, an unflattering threat model |
| `cd4a52e` | round 2 and the security-boundary result |
| `56d94fe` | the S5 findings channel opened |
| `b018a91` | session-2 kickoff prompt |
| `66be55b` | base/head pinned to SHAs so a live repo cannot move mid-run |
| `6e6a80a` | `ref_label` on abbreviated SHAs; the two-arg diff disambiguated |
| `eef0cdc` | **severity gates the exit code** — see item 1 |
| `db50d16` | CLAUDE.md scaffold filled; ruff added; the ballot truncation it found |

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

## Round 2: the security boundary

`tools.py` was reviewed independently for the first time. arbiter found one RCE
(`find -exec`); a workflow-backed review found **five more**, all confirmed by
execution — `python3 -c` (a whole interpreter), a repo-supplied binary matched by
basename, attached-value options escaping containment
(`sort -o/etc/evil`, `git grep --open-files-in-pager=id`), `awk 'BEGIN{system()}'`,
and `sed -i.bak` writing to the tree.

It also caught that my first fix was the wrong *shape*. I patched `find -exec`
with a flag denylist; seven of eight exploits still worked afterwards, because
`-i.bak` is not `-i`. **A general-purpose Unix tool is a language, and you cannot
enumerate the dangerous sentences in a language.**

The command string is gone. The model now supplies typed parameters —
`read_file`, `search`, `git_diff`, `git_log` — and the module builds the argv.
No position where model input becomes a binary or a flag. Verified live: the
rewrite works end-to-end and the model does use the typed tools.

Standing after two rounds: **arbiter is a useful cheap pass that finds real
critical bugs and is not sufficient on a security boundary.** Two independent
looks produced six exploits between them, one apiece missed by the other. That
is an argument for running both, not for picking one.

## Open, in priority order

1. **Done twice — see Round 2 above.** The remaining unmeasured thing is whether
   the typed-tool rewrite changed finding quality, since every head-to-head so
   far used the old shell tool or none.

   **Partial answer, 2026-07-28, two runs on the typed-tool build** — arbiter on
   its own diff, and on conclave's `harness/t1t3-matched-instrument`. Three
   blocking findings between them, each verified by hand before acting:

   - *arbiter, low/correctness:* `ref_label` annotated an abbreviated SHA with
     itself. **Real**, fixed.
   - *conclave, medium/correctness:* the watchdog subshell leaks its `sleep`
     child. **Observation right, consequence wrong.** It claimed the orphan goes
     on to `kill -KILL` the next aider invocation and fake an rc=137. It cannot:
     `kill "$wd"` terminates the subshell, so the kill sequence dies with it.
     Verified by running a reduced copy — neither watchdog stage fires. The real
     defect is a leaked `sleep` per task, cosmetic.
   - *conclave, low/correctness:* `env -C` called non-portable. True only for
     macOS <13; works on the actual mac (26.5.2) and on GNU coreutils ≥8.28.
     Inert.

   So: the reported-defects-are-reliable / worked-examples-are-not pattern held
   again, and **the finder is better at locating than at concluding**. Verifying
   the repro before acting caught the one wrong consequence both times.

   **Three more from tessera, 2026-07-29 — the pattern held a third time, and
   one finding was worth taking on a reason arbiter did not give:**

   - *tessera, medium/correctness (blocking):* a found-but-crashing `offer.py`
     set its found-flag on the same line as the interpreter call, suppressing
     the `degraded` report the change existed to emit. **Real, fixed** — and it
     was in code written an hour earlier *to close a silent-failure bug*, which
     its author had already tested hard.
   - *tessera, medium/correctness (blocking):* a `tessera-watch` predicate keyed
     its per-project tally by directory name, so same-named projects would
     merge. **Premise false** — the discovery glob is single-parent and
     non-recursive, so names are unique by construction and the collision cannot
     occur. Taken anyway, for a reason arbiter did not state: the merged counter
     would hold a *counting predicate quiet*, and it should not depend on a
     property of a different function. **Right instinct, wrong justification,
     still worth acting on** — a category the earlier runs had not produced.
   - *tessera, medium/correctness (advisory):* restore scripts are not
     `chmod +x`'d unlike `spend/guard.py`. **Observation right, consequence
     wrong** — it argued `offer.py` is probed with `[ -x ]` so a missing exec
     bit silently skips the install. The probe is `[ -f ]` and the file is run
     as `python3 <path>`; the exec bit is irrelevant. Inert, no action.

   Read together with instance 5 under *Fail-open*: the two blocking findings
   came from a run that had to be **re-invoked with `--ext ""`** to see the code
   at all. The default run reported "0 blocking" over files it never opened.

   The load-bearing result is about the *tiering*, not the finding quality:
   three of three blocking findings were not worth stopping a commit for.
   Triage votes on whether a finding is real and nothing consulted severity
   afterwards, so `low` rejected as hard as `critical`. Fixed —
   `findings.gates_exit`, exit 1 now needs high or critical, unclassifiable
   severity gates rather than passes. This had to be settled before the git
   hook: a gate that cries wolf gets bypassed. (The hook itself is since
   demoted — see "What has never been run" below.)
2. **Cost, first real measurement:** 2 shell files in tessera →
   **24 model calls, 185k in / 12k out, $0.73**. That is ~12 calls per file, not
   4 — verification triples the call count, since every turn resends the
   conversation. ~$0.37/file, so a 20-file branch is ~$7. Earlier input-only
   estimates were 9x low. What the 3x buys is filtering, not volume — same
   finding count, ~3x as many dropped by triage. Four points now:

   | repo | scope | cost | per file |
   |---|---|--:|--:|
   | tessera | 2 shell files | $0.73 | $0.37 |
   | tessera | 7 Python files | $2.74 | $0.39 |
   | arbiter | 3 large Python files | $1.54 | $0.51 |
   | conclave | 1 shell file, 287 lines | $0.79 | $0.79 |

   Per-file cost is **not** stable — it ranges 2x with file size, so estimating
   in "files changed" is wrong twice over: only reviewable files cost anything
   (conclave changed 114 files, 113 were logs and result data, one was
   reviewed), and their size drives the rest.

   **All four points predate prompt caching (2026-07-30) and are now upper
   bounds.** Measured end-to-end afterwards on one 230-line Python file at
   `--jobs 1`: 6 calls, 75,552 prompt tokens, 50% served from cache, $0.17 —
   against $0.24 for the same token count at full input rate, about 29% off.

   The load-bearing finding was *where* the money was, and it was not the fixed
   prefix. Each verification turn resends the whole conversation, and turn one
   already carries the diff plus the entire before- and after-state, so a
   five-turn review re-sends 76-78% of its input tokens — `docs/STATE.md` itself
   measures 14,409 tokens on turn one and 79,045 across five turns. The system
   prompt is 2138 of that. So the transcript breakpoint is the one that pays;
   the prefix breakpoint is the cheap one that also pays across files.

   **Triage is deliberately not cached, and the number is why.** Its prefix
   measures 1017 tokens for the reviewer voice and 1024 for the arbiter voice,
   against claude-sonnet-4-6's 1024-token minimum. One is below the floor and
   the other is exactly on it. A breakpoint there would silently cache nothing
   half the time and flip on any wording edit — and a marker that caches nothing
   is *worse* than no marker, because it reads as done. Same family as
   *Fail-open* below: not a wrong answer, a confident claim about work that
   never happened. Re-measure with `count_tokens` before adding one.

   Related trap, avoided on purpose: `usage()` used to sum `input_tokens`, which
   is the **uncached remainder**, not the prompt. Had the meter not been fixed
   first and separately, the cost line would have fallen while the token total
   silently under-reported by exactly the amount caching saved — a number moving
   the right way for the wrong reason. The meter landed as its own commit
   (`57a7683`) ahead of any `cache_control` (`46c42e3`) for that reason.
3. **Tessera seams — both resolved, kept for the trail.** `docs/FINDINGS.md` is
   the S5 feedback seam and is no longer empty: F-001 (the icpg-session-base
   glob, transferred as tessera `8af9789`) and F-002 (`.tessera/` adoption,
   which resolved D4 and re-gated S4). The contract
   (`~/claude/tessera/docs/contracts/three-project-cohesion.md`) no longer gates
   S4 on the void "pr-arbiter Phase 3" — updated in the same pass; S4's gate is
   now D3 plus a stable conclave fleet. The remaining open item is the
   observatory entry F-001 asks for: whether hook payload parsing should be a
   shared tested helper rather than open-coded per hook.
4. **The eight defects the workflow found are fixed; its *class* of finding is
   not covered by tests.** Rename/copy handling has unit coverage now; the
   verification loop's protocol handling does not.
5. **Deferred, recorded, not dropped:** SQL support. Thin surface today (one
   `.sql` file across all active repos, already linted by sqlfluff in the repo
   that owns it), but it is part of what would make this useful to someone other
   than its author.

6. **Triage was broken and is now fixed** — see below. Resolved, kept here
   because the *way* it was found is the transferable part.

7. **OPEN, and it is the control-surface bug: reviews silently skip
   extensionless files** (2026-07-29, found from tessera — full account under
   *Fail-open* below). `is_reviewable()` filters on suffix, so a shebang script
   with no extension is dropped, the output still reads
   "N file(s) reviewed · 0 blocking", and `--path` cannot override it because
   `is_reviewable` runs first in `change_units()`. Two runs against tessera
   reviewed the tests and skipped the code.

   This outranks most of the list because it is not a quality question — a
   review that is *narrower than it claims* makes every clean result
   unfalsifiable. Three parts, and the first is the one that matters:

   - **Say what was skipped.** Print dropped paths and a count in the summary,
     always. Even with the filter unchanged, an announced skip is a ceiling; an
     unannounced one is a false green. Cheapest fix, largest effect, no
     behaviour change.
   - **Make `--path` authoritative.** A path the caller named explicitly should
     bypass the extension filter — that is what the docstring already promises.
   - **Detect by shebang.** `#!` + `python|bash|sh|zsh|node` on line 1 for
     extensionless files. Tessera solved the same problem in its iCPG extractor
     (ADR-0017) and the approach carries over.

   `--ext ""` is the current workaround and selects extensionless files only.

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

### The instrument had the same bug, twice over (`db50d16`)

Adding ruff turned up B905 on the ballot: it was built with
`zip(merged, rv, av)`, which truncates to the shortest list. `classify()`
indexes with an `"unsure"` fallback so every finding is still tiered — but the
ballot silently omitted the findings whose votes went missing, and the stderr
vote-mix counter reads from the ballot.

So the diagnostic added to catch missing votes under-reported precisely when
votes went missing. Third instance of this shape in the same function. A missing
vote is now recorded as `"missing"` rather than borrowing classify's `"unsure"`:
both tier the finding advisory, but one means the voice abstained and the other
means it was never heard, and conflating them is what made the original bug take
two sessions.

**Worth generalising: the instrument needs the same scrutiny as the thing it
measures.** Nothing reviewed the ballot because it was "only logging".

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

- **arbiter as a git hook**, despite the exit codes being designed for it. This
  was the right order: run it by hand first, and the first two foreign-repo runs
  showed the gate would have fired on cosmetics. Fixed in `eef0cdc` — but
  **deliberately still not wired, and demoted out of the next steps.** At 1–2
  minutes and $0.79–$2.74 a run it is too slow and too expensive to fire
  automatically, and after the severity fix the exit-1 path has not triggered on
  real code once, so its precision at the tier that gates is unmeasured. Full
  reasoning in `NEXT_SESSION.md` under "Demoted"; the conditions for revisiting
  are written down there rather than left to judgement.
- **A head-to-head since verification landed.** The comparison that made arbiter
  look weak predates the tool entirely, and the typed-tool rewrite has never
  been measured against `/code-review` on the same diff. Item 1's two runs are
  arbiter-alone results, not comparative ones.
- **An independent review of the current `tools.py`.** Every review that found
  holes in the security boundary was of the *previous*, command-string design.

## Fail-open, the recurring defect

Not one bug, a pattern — four instances now, several written by whoever had just
fixed the previous one. Each was defensive in intent:

1. A `{}` return from a missing `tool_use` block that read as "no findings".
2. A swallowed `GitError` in `_content_at` that read as "new file".
3. A triage UNSURE default that turned total ballot failure into "nothing
   blocking" — see the triage-bug section below.
4. Nearly a fifth: `_SEV_RANK.get(sev, 0)` was the obvious thing to reuse for
   the new severity gate in `eef0cdc`, and its unknown-sorts-last default would
   have meant an unparseable severity passes. `findings.gates_exit` deliberately
   does not use it.
5. **A real fifth, and it is not a fallback — it is the SCOPE (2026-07-29).**
   `is_reviewable()` filters on file extension, so extensionless files are
   dropped. Found from tessera: `arbiter --base 84c63cc` printed
   **"1 file(s) reviewed · 0 blocking"** having never opened
   `bin/tessera-watch` — a `#!/usr/bin/env python3` file with no suffix, and
   the entire subject of the change. Re-run with `--ext ""` it produced a
   blocking finding immediately. The same filter had silently skipped
   `bin/tessera-new-project` in an earlier run that *did* report findings from
   the `.sh` files beside it, so the output looked like a working review of the
   whole diff while the shipped file went unread.

   **The docstring is honest — and that is what made it dangerous.** It says
   *"Extensionless files are skipped… callers that care should pass an explicit
   path list rather than relying on extension sniffing."* Two problems:

   - **The output never says anything was dropped.** "1 file(s) reviewed" is
     true and reads as complete. A caller sees a clean review, not a narrowed
     one.
   - **The documented escape hatch does not work.** In `change_units()`,
     `is_reviewable(path, exts)` runs *before* `matches_any(path, paths)`, so
     `--path bin/tessera-watch` returns "No reviewable changes." `--path` can
     only narrow; it can never rescue a file the extension filter already
     dropped. The docstring tells callers to do the one thing the CLI refuses.

   Worth knowing: **tessera hit this exact defect independently in iCPG**
   (its ADR-0017 — `symbols.py` dispatched on extension, so iCPG saw 84 of 260
   code files, 32% of the repo). Two unrelated tools, same repo, same blind
   spot. Shebang detection is the fix in both cases; tessera already wrote one.

**The rule, and instance 5 widens it: when adding a fallback here, ask what a
*gate* will conclude from it. If the answer is "pass", it is wrong.** A silent
*filter* reaches the same conclusion by a different route — the gate passes on
a file it never read. So the rule is not only about fallbacks: **any narrowing
of scope must appear in the output, or the report is a false green.** A review
tool's worst failure is not a wrong finding; it is a confident silence over
code it never looked at.

This is arbiter-internal, not Tessera friction, so it lives here rather than in
`docs/FINDINGS.md`.
