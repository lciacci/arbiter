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
| `46c42e3` | prompt caching on the finder prefix and the verification transcript |
| `975b491` | **scope stops lying** — skipped files reported, `--path` authoritative, shebang detection |
| `134cccc` | **the six defects three reviews found in `975b491`** — see Round 3 |

## Round 3: three arms, one diff — the first unconfounded peer-strength result

**2026-08-07.** Rounds 1 and 2 both predate the typed-tool rewrite, so neither
described the current build. This one does, and it is the only head-to-head run
with **three** arms on a byte-identical diff — `975b491`, the scope fix, 4 files,
155 insertions, on a throwaway `h2h` branch cut at its merge-base so every arm
could be pointed at the same thing.

| # | Distinct defect | arbiter | plain `/code-review`, 17 agents | `ultra`, cloud |
|---|---|:--:|:--:|:--:|
| A | `_is_script` → `UnicodeDecodeError` on a binary, kills the whole run | ✅ med | ✅ | ✅ normal |
| B | **`--path` short-circuits reviewability** → binary crash, `.env` to the API, cost amplifier | **✅ high** | ✅ (as 3) | ❌ |
| C | All-skipped run → empty `--json`, no `--out`, exit 0 | ❌ | ✅ | ✅ nit |
| D | stderr states one skip reason for a list carrying four | ❌ | ✅ | ✅ nit |
| E | Duplicate `git show` per extensionless file | ❌ | ✅ | ✅ nit |
| F | `--path`-excluded files never enter the skip list | ❌ | ✅ | ❌ |
| G | `has_extension` is a one-caller wrapper | ❌ | ✅ | ❌ |

**Union 7. arbiter 2, ultra 4, the 17-agent workflow 7** — but see the amendment
immediately below before quoting arbiter's number anywhere. **It is one draw
from a wide distribution, and taken alone it is misleading.**

**The load-bearing result, and it is the one conclave's queued experiment is
about: arbiter and ultra each caught something the other missed.** arbiter has
B; ultra has C, D and E. That is a genuine peer-strength union-recall gain on
the current build — and unlike Round 2's anecdote it is **not confounded by
architecture**, because the 17-agent arm found *all seven*. Scale explains
ultra's misses; it does not explain B specifically, since a smaller fan-out
caught it. Guard (b) in `INTEGRATION.md` is updated accordingly.

**Do not read this as a win.** arbiter found **2 of 7**. It is nowhere near the
workflow arm on recall, and both of its findings were a subset of that arm's.
What it has is one high-severity catch the premium arm did not make. The
positioning stays *cheap and portable*, not *better*.

**The part worth internalising: all seven defects were in code arbiter had
written that same day, and four of them were this project's own thesis turned
back on it.** `975b491` shipped "a filter and a report of what the filter did
are two features, not one" — and then left three more doors the report did not
cover (C, D, F), plus a crash (A) and a security hole (B) introduced by the
rescue path itself. Fixed in `134cccc`. The generalisation is in *Fail-open*
below: **the fix for a class of defect is the most likely place to find the next
instance of it.**

Cost is **not comparable across the arms** and should not be quoted as a ratio:
arbiter metered $1.56 / 46 calls / ~2 min at list price; the workflow arm
reported 17 agents / 692k subagent tokens / 8 min on a different meter; ultra
ran on the free tier and exposes no token count at all.

### Amendment, same day: "2 of 7" was one draw, and the real bottleneck is triage

The number above was published, and then a $0.40 diagnostic re-ran one file of
the same range and **arbiter found defect C** — which the scored run had
reported as a miss. Same input, different result. So the whole arm was re-run
three more times ($4.44) and the four runs scored as a union:

| Defect | scored run | run 1 | run 2 | run 3 | union |
|---|:--:|:--:|:--:|:--:|:--:|
| A `UnicodeDecodeError` crash | **blocking** | — | — | — | ✅ |
| B `--path` short-circuit | **blocking** | — | **blocking** | **blocking** | ✅ |
| C all-skipped → exit 0 | — | — | advisory | dropped | ✅ |
| D skip reason mischaracterised | — | advisory | advisory | dropped | ✅ |
| F `--path`-excluded not in skip list | — | — | — | dropped | ✅ |
| E duplicate `git show` | — | — | — | — | ❌ |
| G `has_extension` wrapper | — | — | — | — | ❌ |
| **distinct defects found** | **2** | **1** | **3** | **4** | **5** |

**Two numbers, and the gap between them is the finding.**

- **Union recall across four runs: 5 of 7**, up from 2. Per-run range **1–4** — a
  4× spread on byte-identical input. One run is a poor estimator of what this
  tool can find, and Round 3's headline was a single draw reported as a
  capability.
- **Blocking-tier recall does not move: still A and B, 2 of 7, in every
  combination.** Every defect the reruns recover lands advisory or dropped.

**So finding is not the bottleneck — triage is.** arbiter *locates* about 2.5×
what any one run reports and then discards it. That inverts where the effort
should go: not a better reviewer prompt, not more finders, but triage
calibration. It is also the third time this project has been wrong about triage
by reasoning instead of logging, and the second time the fix was to run the
instrument again rather than think harder.

**Two supporting observations, both cheap to re-check:**

- **`has_extension` was flagged in all three reruns as inverted-semantics, and
  all three are wrong.** It returns True when a file *has* an extension and the
  caller negates it correctly. A confident, reproducible false positive — triage
  dropped it twice and let it through once, so triage is not filtering it
  reliably either. G is scored ❌ above because the reports are not the finding.
- **E is invisible to arbiter across all four runs.** Not one mention of the
  duplicate read. Run 1 got adjacent — it noticed the shebang check pulls whole
  binaries into memory — without seeing that the same content is fetched again
  seventeen lines later. Seeing one function call twice in one function is
  exactly what per-file review should be best at.

**What this does *not* change.** The peer-strength result stands: even at union
5 of 7, B is still a defect ultra missed and arbiter caught, and the 17-agent
arm still found all seven. Nothing here makes arbiter competitive on the
blocking tier, which is the tier that is the product.

## The measurement that matters (Round 1 — predates the typed-tool rewrite)

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

1. **ANSWERED 2026-08-07 — see Round 3 at the top.** The open question was
   whether the typed-tool rewrite changed finding quality, since rounds 1 and 2
   both used the old shell tool or none. Three arms on one diff: arbiter found
   **2 of 7** distinct defects, ultra 4, a 17-agent workflow all 7 — and arbiter
   and ultra each caught one the other missed, which settles the peer-strength
   question guard (b) had open. Recall is the honest headline and it is not
   flattering; the decorrelation is the useful result.

   **Earlier partial answer, 2026-07-28, two runs on the typed-tool build** — arbiter on
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
   | tessera | 2 Python files, 1841 lines *(post-caching)* | $1.51 | $0.76 |

   The fifth point is the only one measured **after** prompt caching, and it is
   the most expensive per file on the table — because the files are the largest
   on it (1009 + 832 lines). 52% of 762k input tokens served from cache and it
   still cost $0.76/file. Caching does not repeal the size term; it discounts it.

   Per-file cost is **not** stable — it ranges 2x with file size, so estimating
   in "files changed" is wrong twice over: only reviewable files cost anything
   (conclave changed 114 files, 113 were logs and result data, one was
   reviewed), and their size drives the rest.

   **The first four points predate prompt caching (2026-07-30) and are upper
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

   **The cheap-model lever is measured, and it is dead (conclave, 2026-08-07).**
   Written here by conclave rather than proposed, because it is a fact about
   conclave's substrate that lands in this repo's cost path. Swapping the finder
   to a cheap self-hosted model is the obvious next cost move after caching, and
   it does not work: on **this project's own corpus** — pr-arbiter's 20 PRs, 55
   expected findings, the reviewer prompt verbatim, their matcher — a local
   Qwen3-Coder-30B scores **0.073 recall and 0/8 criticals** against
   claude-sonnet's **0.509** on the identical task. Not confabulation: it parsed
   cleanly every time and correctly returned zero on all three negative-control
   PRs. It under-detects, ~1 finding per PR where 3–5 exist.

   The load-bearing part is *why*, because it is not "small model bad". The same
   local model **matches** a hosted FP8 80B on edit-and-apply (3/3 byte-identical
   over three tasks, zero edit rejects) while losing ~7× on find-the-defect.
   **Task shape, not model tier, is what breaks.** Review is the shape that
   breaks it — which is this tool's entire workload.

   Consequence for the D3 seam: `ANTHROPIC_BASE_URL` → conclave's gateway works
   mechanically and buys nothing at the `local-mid` tier. Caching, `--path`
   scoping and `--no-verify` remain the real levers. Conclave's model-axis run
   also found MODEL-diverse union adds **+0.000 recall and +20 false positives**
   over a single reviewer, so a *fleet* of finders is not a cost or quality play
   either — though that arm used a weaker second model and so cannot speak to
   peer-strength diversity. Evidence:
   `../conclave/docs/LOCAL-CODER-FAILURES.md`, `../conclave/orchestrator/s2_model_axis.py`.

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

7. **FIXED 2026-08-07 (`975b491`) — the control-surface bug: reviews silently
   skipped extensionless files** (found 2026-07-29 from tessera — full account
   under *Fail-open* below, kept because the account is the transferable part).
   `is_reviewable()` filtering on suffix meant a shebang script was dropped
   while the output still read "N file(s) reviewed · 0 blocking", and `--path`
   could not override it because `is_reviewable` ran first in `change_units()`.
   Two runs against tessera reviewed the tests and skipped the code.

   It outranked the quality questions because it was not a quality question — a
   review *narrower than it claims* makes every clean result unfalsifiable. All
   three planned parts landed in one commit:

   - **Say what was skipped.** `change_units` returns `(units, skipped)`;
     both the stderr line and the report body name the dropped paths, and the
     stderr line prints *before* the "no reviewable changes" early return —
     the path where a false green was cheapest to produce.
   - **`--path` is authoritative** and runs first. A named path is reviewed
     whether or not it looks like code, which is what the docstring had been
     promising and the CLI had been refusing.
   - **Shebang detection**, gated on `has_extension` so it costs one `git show`
     per extensionless changed file and nothing for the rest. Tessera hit the
     identical blind spot in its iCPG extractor (ADR-0017).

   Two decisions inside it worth not re-litigating. **Any `#!` counts**, not the
   `python|bash|sh|zsh|node` allowlist sketched here earlier — the agents'
   prompts are language-agnostic, so an allowlist would only restore the silent
   drop for perl. And **`--ext` does not disable shebang sniffing**: a file with
   no extension is not a member of any extension set, so leaving it to `--ext`
   would restore the same drop under a different flag. `--path` is the lever for
   narrowing.

   `--ext ""` was the workaround and is no longer needed. What still needs a
   flag is a file with an extension *outside* the set — and that is now printed
   rather than assumed.

   **Confirmed on the diff that exposed it, 2026-08-07.** `arbiter --repo
   ../tessera --base 84c63cc --head 9b73e27` — the range whose subject is
   `bin/tessera-watch`, 1009 lines, `#!/usr/bin/env python3`, and whose only
   other code file is the `.py` test beside it. That is the "1 file(s) reviewed
   · 0 blocking" run: the old default opened the test and nothing else.

   On the fixed build: **2 files reviewed, 2 blocking + 1 advisory, both `.md`
   files named as skipped** in the stderr line and in the report body. 22 calls,
   762,244 in (52% cached) / 5,095 out, **$1.51**.

   Two things worth keeping from it beyond the pass/fail:

   - **Exit 0.** Both findings are medium and low, and `eef0cdc` requires high
     or critical. The severity gate and the scope fix compose the way they
     should — a wider review did not make the gate noisier.
   - **arbiter's consequence claim held, for the first time on record.** It
     reported the unguarded `log.read_text()` at `bin/tessera-watch:761` *and*
     argued the OSError propagates out of `evaluate()` and kills the whole
     watcher run. Checked: `evaluate()` (line 923) has no `try` around
     `pred(root)`. The standing note is that the finder locates better than it
     concludes; this is one data point against that, not a repeal of it.

   Not claimed: that this is the *same finding* the original `--ext ""` re-run
   produced. That run was a different range. What is confirmed is the scope —
   the default now opens the file.

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
5. **A real fifth, and it is not a fallback — it is the SCOPE (2026-07-29,
   fixed 2026-08-07 in `975b491`; the account stands because the shape is the
   transferable part).** `is_reviewable()` filtered on file extension, so
   extensionless files were dropped. Found from tessera: `arbiter --base 84c63cc` printed
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

   **What the fix generalises to, and it is the reason to read this entry
   rather than the diff:** the first two bullets above are one defect stated
   twice — a filter and a *report of what the filter did* are different
   features, and shipping the first without the second is what makes a true
   sentence ("1 file(s) reviewed") into a false claim. Every other silent
   `continue` in that loop was the same bug waiting; the emptied-file skip was
   one and is now reported too. **A component that narrows scope owes the caller
   a list, not a count.**

6. **A sixth, and it is instance 5's own fix (2026-08-07, `134cccc`).** Three
   independent reviews of `975b491` — arbiter, a 17-agent workflow, a cloud
   review — found seven defects in it (Round 3, top of this file). Four are this
   same class, shipped *by the commit that was fixing this same class*:

   - **`--path`-excluded files never entered the skip list.** `--path` is the
     largest ceiling the tool has, and it was the one ceiling that stayed
     unannounced. Instance 5 exactly, one door over.
   - **A run that skipped everything returned before `render()`** — empty
     `--json`, no `--out` file, exit 0, and the previous run's markdown left on
     disk to be read as current. The false green survived *in the one channel a
     gate actually reads*, which is the worst possible place for it to survive.
   - **The stderr line named one skip reason for a list already collecting
     four.** Not a false green — a false *diagnosis*, which sends the reader to
     `--ext` for a file that was empty at head. Worse than saying nothing.
   - **And the rescue path itself crashed.** `_is_script` opened extensionless
     files to sniff a shebang and caught only `GitError`, so a committed binary
     raised `UnicodeDecodeError` out of `subprocess.run` and killed the entire
     run. The feature added to stop files going unreviewed made *every* file in
     the diff go unreviewed.

   **The generalisation, and it is the most useful thing in this document: the
   fix for a class of defect is the most likely place to find the next instance
   of it.** Not because the author is careless — because a fix is written by
   someone thinking about the *old* instance, in new code that nothing has
   reviewed yet, under the confidence of having just understood the problem.
   Four of the seven were found by the two arms that were *not* arbiter, so this
   is also the argument for running a second reviewer over exactly the commits
   you are most sure about.

**The rule, and instance 5 widens it: when adding a fallback here, ask what a
*gate* will conclude from it. If the answer is "pass", it is wrong.** A silent
*filter* reaches the same conclusion by a different route — the gate passes on
a file it never read. So the rule is not only about fallbacks: **any narrowing
of scope must appear in the output, or the report is a false green.** A review
tool's worst failure is not a wrong finding; it is a confident silence over
code it never looked at.

This is arbiter-internal, not Tessera friction, so it lives here rather than in
`docs/FINDINGS.md`.
