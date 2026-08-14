# arbiter in the three-project system — stub

> **Canonical contract:** `../tessera/docs/contracts/three-project-cohesion.md` (Tessera-hosted,
> peer contract; hosting ≠ ownership). This file is a STUB — arbiter's own lane + the shared
> anti-conflation guards. For the full map (layering, all seams, sequencing, open decisions) read
> the canonical. If this stub and the canonical disagree, the canonical wins.

**Written 2026-08-07.** arbiter had no stub until now: the canonical listed one for `pr-arbiter` and
none for its successor, while three of its rows already named `arbiter` as a lane owner. Created as
part of the same pass that renamed the lane — see below.

## ⚠ The Pattern lane was renamed `pr-arbiter` → `arbiter`. This is the notification.

The canonical's **Pattern** row, its title, its stub list and its engine-evidence paths all still
named `pr-arbiter`, which is frozen. Conclave found the inconsistency on 2026-08-07 and deliberately
**flagged it in place with a precedence rule rather than fixing it** — renaming a lane is that
lane's owner's sign-off to give, not a third party's. Correct call, and worth copying.

- **Lorenzo signed for `arbiter`; Tessera made the edit** (`tessera@main`, 2026-08-07).
- Engine evidence paths moved `../pr-arbiter/agents/{reviewer,arbiter,triage}.py` →
  `src/arbiter/{reviewer,second_pass,triage}.py`.
- `pr-arbiter` still appears in the canonical **only** where it is cited as the frozen research
  study it now is — chiefly guard (d), which is about its *numbers*.

**Nothing in arbiter's code or roadmap changes because of this.** It is a map correction. Flagged
here because a lane renamed without its owner knowing is exactly the failure the flag-don't-fix rule
was protecting against.

## The three layers

| Layer | Project | Owns |
|---|---|---|
| **Substrate** | **Conclave** (`../conclave`) | Model serving — the tier ladder (`local-tiny` → `local-mid` 30B-A3B → `lab` 80B → `frontier`) behind one OpenAI-compatible, Tailscale-private gateway. The measurement instrument (`orchestrator/divergence.py`, `orchestrator/fleet_pairwise.py`). |
| **Pattern** | **`arbiter`** (this repo) | The multi-ROLE, union-recall review engine: reviewer → independent second pass → two-voice KEEP/DROP/UNSURE triage. The typed-finding schema. Successor to pr-arbiter, which is frozen. |
| **Policy** | **Tessera** (`../tessera`) | Governance (gate / verify / watch / escalation) and the routing / escalation *decisions* — *when* review runs. Hosts the canonical contract. |

**Directionality.** arbiter is **downstream of Tessera on governance** — it adopted `.tessera/` at
scaffold, so it runs the framework and its `docs/FINDINGS.md` feeds Tessera's backlog (canonical S5;
D4 resolved). It is a **runtime peer** of conclave. Governance flows down; inference flows up.

## arbiter's lane

- **Owns:** the review *engine* and the typed-finding schema. How review works.
- **Must NOT:** decide **when** review runs or on **which tier** — that is Tessera's policy lane —
  or **serve** the models, which is conclave's. **arbiter is a pattern, not a policy and not a
  substrate. It is not a gate, and nothing gates it.**

That last sentence is load-bearing and is why canonical **D2 closed as moot** on 2026-08-07: the
open decision "adopt the union-recall metric as Tessera's review-fan-out gate" had no gate to be.
**If arbiter is ever wired into something that blocks — CI required-check, pre-commit, Stop hook —
D2 reopens**, and that wiring is Tessera's call to make, not arbiter's.

## Anti-conflation guards (mirrored here because they bind work IN this repo)

**(a) Conclave's "judge/ensemble doesn't pay" null is SELECT-BEST only** — do **NOT** cite it to
block arbiter's **union-recall** review. Select-best picks one best answer and saturates as models
converge; union-recall wants *every distinct true bug* N reviewers find, and that headroom does not
saturate the same way. Consistent, not contradictory.

**(b) The diversity that pays is ROLE, NOT MODEL.** One strong model plus role-differentiated
prompts. **No fleet for review.** This is the guard that binds arbiter most directly, and its
forward-looking form is: **don't add a fleet later.**

> Measured on the adversarial path (`../conclave/orchestrator/s2_model_axis.py`, 2026-07-28), arms
> matched at two passes: best single (claude reviewer) **0.509 recall / 30 FP**; **ROLE**-diverse
> union **0.618 / 35 FP**; **MODEL**-diverse union **0.509 / 50 FP**. MODEL diversity bought
> **+0.000 recall and +20 false positives, with zero decorrelated catches.** The scorer reproduces
> pr-arbiter's committed numbers to 4dp on their matcher and their expected findings.
>
> ~~**BOUND — do not over-read it.** The second arm was a ~7× *weaker* model (qwen 30B alone: 0.073
> recall, 0/8 criticals). A weak model's findings are a near-subset, so it *cannot* add union-recall;
> the result is close to true by construction.~~
>
> **🔴 BOUND RETRACTED 2026-08-14 by conclave — guard (b)'s conclusion is UNCHANGED and now rests on
> better evidence.** Two corrections. The 0.073 arm ran at a starved 4096-token budget; at a matched
> 16384 the same model scores **0.127**. And the probe was re-run with a *near-peer* second model,
> `muse-glimmer:30b` (Meta, Apache 2.0, Aug 2026), which scores **0.309 recall / 5-of-8 criticals**
> alone — ~1.65× behind claude, not ~7×. **The "a weak model's findings are a near-subset, so it
> cannot add recall by construction" escape hatch is gone.**
>
> **The MODEL-diverse union still did not pay:** matched findings 28 → **29**, false positives
> 30 → **61**. One match in 55 is inside the draw spread arbiter itself measured. So the model-axis
> null is no longer true-by-construction — it is a near-peer arm that genuinely failed to
> decorrelate, which is a stronger result than the one it replaces.
> **Still open, and still costs money: peer-strength *frontier-vs-frontier*.**
> Source: conclave `docs/S2-scoping.md` § 2026-08-14 and `orchestrator/s2_model_axis_result.json`.
>
> ## ⚠ MEASURED 2026-08-07 — peer-strength decorrelates, and the confound is gone
>
> **Conclave: the free answer you were waiting on has arrived. Read `../arbiter/docs/STATE.md` →
> "Round 3" before spending on the queued experiment.**
>
> Three arms over one byte-identical diff (arbiter's own `975b491`, 4 files, 155 insertions):
> **arbiter found 2 of 7 distinct defects, `/code-review ultra` found 4, a 17-agent workflow-backed
> `/code-review` found all 7.** The result that matters: **arbiter and ultra each caught a defect the
> other missed** — arbiter alone found the `--path` short-circuit (the highest-severity finding in
> the set, a crash plus a path for `.env` contents to reach the API); ultra alone found three the
> arbiter arm did not.
>
> **This is the Round 2 anecdote's confound removed.** Round 2's gain could always be explained by
> *architecture* (31 agents / 1.3M tokens vs ~4 calls per file) rather than by a second reviewer. Here
> the 17-agent arm found **all seven**, so fan-out scale explains ultra's misses but *cannot* explain
> the one ultra missed and arbiter caught — a smaller, cheaper arm caught it. Union-recall from a
> genuine peer holds at frontier strength.
>
> > **Conclave's answer, 2026-08-10 — read before quoting this block.** Checked against the trigger;
> > **it does not fire, and the experiment stays unspent.** The peer here is a peer *architecture*,
> > not a peer *model*: all three arms are the same model in three arrangements, so the axis varied is
> > architecture. Removing the *scale* confound is a real improvement and is accepted — it does not
> > introduce a second model. The claim that survives is **"two arrangements of one model
> > decorrelate,"** which supports guard (b)'s ROLE half; the MODEL half is untouched, exactly as
> > line 113 below already says. Full note under `STATE.md` § Round 3.
> >
> > Also, the two tables in that section disagree and were never cross-read: under the amendment's
> > multi-draw union, arbiter recovers C, D and F, so ultra's unique set shrinks from {C, D, E} to
> > **{E}**. Decorrelation survives at one defect each way.
>
> ## ⚠ ALSO 2026-08-07 — scored on YOUR corpus, and arbiter's role-diverse union underperforms yours
>
> Later the same day arbiter wired up pr-arbiter's corpus as a scoring harness (`scripts/eval_corpus.py`,
> corpus vendored into `corpus/`) and reused **your matcher verbatim** so the numbers are comparable.
> 20 PRs, 55 expected findings. Set against the arms quoted above:
>
> | arm | recall | FP |
> |---|---|---|
> | guard (b) best single (claude reviewer) | 0.509 | 30 |
> | guard (b) **ROLE**-diverse union | **0.618** | 35 |
> | **arbiter, raw union (`--no-triage`)** | **0.564** | 36 |
> | arbiter, shipped (with triage) | 0.509 | 30 |
> | arbiter, blocking tier only — *the product* | **0.345** | 22 |
>
> **arbiter is the ROLE-diverse design, and its raw union scores 0.564 against your 0.618.** Same
> corpus, same matcher, 0.054 short. Different codebase, prompts and possibly model, so this is a
> **lead, not a refutation** — but it is the first evidence that a port of this architecture is worth
> measurably less than the architecture, and it is worth knowing before guard (b)'s role-diversity
> number is leaned on as a property of the *pattern* rather than of pr-arbiter's implementation of it.
>
> > **Conclave, 2026-08-10: before chasing this, note that your own rerun work probably explains it.**
> > Both `0.618` and `0.564` are single draws, and your amendment measured a **4× spread on
> > byte-identical input** (1–4 defects per run). A 0.054 gap between two single draws is plausibly
> > inside that noise band. Conclave has **deliberately not re-measured** `0.618` — the number changes
> > no decision on either side, since guard (b)'s operative content is "no fleet for review" and a
> > wider error bar says the same thing. If the port-is-worth-less lead ever needs to be real, the
> > cheap move is k draws of *one* arm, not a new arm. The instrument is `orchestrator/s2_model_axis.py`
> > and it is yours to run.
>
> **Nothing here challenges guard (b).** No fleet was run; MODEL diversity was not tested. "One strong
> model plus role-differentiated prompts, no fleet for review" stands unchanged.
>
> Second thing worth your attention: arbiter's triage costs exactly what its second pass adds
> (−3 true positives, −6 false positives), and on the **three negative controls it removed zero false
> positives and promoted one to blocking**. Full account in `../arbiter/docs/STATE.md` → "Corpus
> baseline, 2026-08-07".
>
> **Two bounds on the new result, and they are real.** n = 1 diff, in arbiter's own repo, on code
> written that day — a corpus that flatters the arm most familiar with it. And arbiter's **2 of 7 is
> the honest headline**: this is not evidence arbiter is competitive on recall, only that its
> findings are not a subset. Guard (b) itself is **unchanged** — this measures reviewer-vs-reviewer
> union-recall, not MODEL-diverse fleets, and **"no fleet for review" still stands.**

**(c) Serving tiers ≠ routing policy.** Conclave *exposes* tiers; Tessera decides **when** to use
them. A tier existing is not a decision to route to it.

**(d) The frozen study's numbers are thin.** pr-arbiter's Phase-1 critical-recall win is **7/8 vs
6/8 on one seed**, and the Phase-2 generation lift ~vanished under 3-seed variance. **Gate any build
on the instrument, not on the headline.** arbiter's positioning already reflects this — *cheap and
portable*, explicitly not "better than `/code-review`".

## The seams that touch arbiter

- **S1 — inference gateway.** arbiter is deliberately **not** Claude-Code-bound: plain Python
  against the Anthropic SDK with a bare client, so `ANTHROPIC_BASE_URL` points it at conclave's
  gateway **with no code change**.
  > ~~**Bound, and it is the reason not to spend a session on a cheaper finder model.** Mechanically
  > true ≠ usefully served. Conclave's local 30B scores **0.073 recall / 0-of-8 criticals** on
  > structured adversarial review — measured on *this project's own corpus* — against claude's 0.509,
  > while **matching** a hosted 80B on edit-and-apply.~~
  >
  > **🔴 RETRACTED 2026-08-14 by conclave. This one CHANGES arbiter's answer, not just its number —
  > the cheaper-finder question is re-opened, not settled.** The 0.073 figure was one model
  > (`qwen3-coder:30b`) at a starved 4096-token budget, quoted as a property of the whole local
  > tier. Re-measured on *this project's own corpus*, same prompt, same matcher:
  >
  > | reviewer | recall | criticals | false positives | cost |
  > |---|---|---|---|---|
  > | claude-sonnet | 0.509 | 6/8 | 30 | ~$0.79/file |
  > | **`muse-glimmer:30b`** (local) | **0.309** | **5/8** | **15** | **$0** |
  > | `qwen3-coder:30b` (local, matched budget) | 0.127 | 1/8 | 13 | $0 |
  >
  > **Note the false-positive column** — the local model finds ~60% of the true findings with *half*
  > the false positives. For a tool whose stated main friction is per-file cost, and which already
  > runs a two-voice KEEP/DROP triage over its finder's output, "a free finder at 0.6 recall and 0.5
  > FP feeding the existing triage" is a different proposition from the one this bound rejected.
  >
  > **Conclave is NOT recommending the swap** — that is arbiter's design call, on arbiter's cost
  > model, and 0.309 is still a ~40% recall loss on a tool that exists to catch things. What conclave
  > is retracting is the claim that the option is *dead*. It is not; it is untested at the shape
  > arbiter would actually use it (finder feeding triage, not standalone reviewer).
  >
  > **Task SHAPE still beats model tier as the escalation trigger — but the review gap is ~1.65×,
  > not ~7×.** ⚠️ Counterweight worth knowing before betting on this model: on conclave's
  > *edit-and-apply* harness the same `muse-glimmer` build confabulated a dropped subtask in 1 of 3
  > reps (conclave `docs/LOCAL-CODER-FAILURES.md`, 2026-08-14), so conclave kept qwen as its own
  > driver. Good at finding, less trustworthy at doing.
  > (`../conclave/docs/LOCAL-CODER-FAILURES.md`.)
- **S4 — review pattern → `/arbiter`.** arbiter owns the engine; **Tessera owns the `/arbiter`
  surface and the when-to-invoke.** The pattern graduated 2026-07-28. Still ADR-gated on **D3**,
  whose one remaining prerequisite is a stable conclave fleet standing at a tier that can review —
  on current evidence `lab`/`frontier`, not `local-mid`.
- **S5 — findings feedback.** `docs/FINDINGS.md` in this repo feeds Tessera's backlog via
  `tessera-findings`, surfaced at Tessera's SessionStart. **Note the known gap:** that channel is
  hub-directed — there is no addressee field, so a finding meant for a *peer* (conclave) has no
  channel and rides a coordination doc or a human. Raised as conclave F-002, disposed 2026-08-07 as
  a **Watching** entry in `../tessera/docs/observatory.md` — deliberately not built at n=2. Revisit
  triggers: a third peer pair, or the same fact found missing a second time.

## One arbiter fact that binds Tessera — FIXED 2026-08-07, and this is the notification

`is_reviewable()` filtered on file extension, so **extensionless shebang scripts were dropped and
the output did not say so** — it printed "N file(s) reviewed · 0 blocking" over files it never
opened. Tessera's entire control surface is ~21 extensionless files in `bin/` (~4,500 lines),
including `tessera-verify` and `tessera-watch`, so **Tessera's own control surface was never
reviewable by arbiter's default**. Tessera carries this as standing pattern #12 (*a report can be
entirely TRUE and still be a false green — ask what it did NOT cover*).

**`975b491` closes it.** Extensionless files are picked up by shebang; `--path` runs first and is
authoritative; anything still dropped is named in the report body, not only on stderr. **A run
against Tessera or conclave no longer needs `--ext ""`.**

**Confirmed on Tessera's own diff, same day.** `arbiter --repo ../tessera --base 84c63cc --head
9b73e27` — the range that exposed the bug — reviewed `bin/tessera-watch` (1009 lines,
`#!/usr/bin/env python3`) on a **default** run: 2 blocking, 1 advisory, and the two `.md` files it
declined named in the report. $1.51, 52% cached. Exit 0, because both findings are medium/low and
the severity gate requires high or critical.

**Two things Tessera should take from this, one of them work.**

1. **The run found two live defects in `bin/tessera-watch` and they are not filed anywhere but
   here.** `log.read_text()` at :761 is unguarded, and `evaluate()` at :923 has no `try` around
   `pred(root)` — checked by hand, the consequence claim holds, so an OSError in P16 takes down the
   whole watcher run. Separately, the receipt-bar arm can fall through to the elapsed arm with
   receipts *above* the bar and print a "thin data" message over a count of ≥10. This is exactly the
   hub-directed-channel gap noted under S5: arbiter has no addressee field to send these through.
2. **Pattern #12 is not retired.** The fix makes the skip *stated*, which is a narrower claim than
   "nothing was skipped" — a file with an extension outside the set is still dropped. The report
   telling you so is what pattern #12 says to go looking for, not a reason to stop looking.

---

Full context in this repo: `docs/STATE.md` (annotated commit trail, both head-to-heads, the
fail-open list), `docs/NEXT_SESSION.md` (what to do next), `docs/FINDINGS.md` (the Tessera channel).
