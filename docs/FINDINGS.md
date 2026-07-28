# arbiter — Tessera dogfood findings

Runtime friction surfaced while working in arbiter. Framework-level fixes land in
`tessera`, not here — findings are staged for transfer and scanned by `tessera-findings`.

Contract: the downstream-findings contract in the Tessera framework
(`docs/contracts/findings.md` there). One finding per `## F-NNN — Title` section, each
carrying a `**Status:**` line (`open` | `transferred:<ref>` | `rejected:<reason>`).

## F-001 — icpg-session-base glob matched the payload value positionally, re-anchoring mid-session

**Status:** transferred:8af9789
**Surfaced:** 2026-07-28, arbiter's first review run against a repo other than itself.

The jq-absent fallback in `.claude/scripts/icpg-session-base.sh` (and its
`templates/` twin) matched `*'"source"'*'"startup"'*` — the literal `"source"`
followed by `"startup"` anywhere later in the raw payload, rather than
`"startup"` as the *value* of `source`. A compact event carrying the token
elsewhere, e.g. `{"source":"compact","event":"startup"}`, resolved to
`SOURCE=startup`, passed the `[ "$SOURCE" != "startup" ]` guard, and re-anchored
`.icpg/.session-base` mid-session — the data loss the whitelist rewrite was
written to prevent, reintroduced inside the fallback that exists precisely for
when jq is unavailable.

Why it slipped: the fallback was added as a safety net for a *missing
dependency*, and safety nets get less scrutiny than the path they protect. The
whitelist rewrite above it was carefully reasoned; the glob beneath it was not.

Fixed in tessera `8af9789` — matches key-and-value together, both compact and
spaced forms, verified against the patched file for correct classification, the
bug case, and the unknown-source preserve path.

**Framework-level lesson worth transferring beyond the one-line fix:** shell
glob parsing of JSON is a recurring hazard in the hook layer, and it is
unreviewed by anything. `sh -n` catches syntax, not semantics. Tessera's hooks
are the layer its own postmortem says it cannot self-detect failures in, and
this is a second instance. Worth an observatory entry on whether hook payload
parsing should be a shared, tested helper rather than open-coded per hook.

## F-002 — `.tessera/` adoption resolved D4 and trips the tessera-watch P4 threshold

**Status:** transferred:contract-regate
**Surfaced:** 2026-07-28, scaffolding arbiter.

arbiter adopted `.tessera/` at scaffold, which resolves open decision D4 in
`docs/contracts/three-project-cohesion.md` (previously "should pr-arbiter adopt
`.tessera/`?" — moot, since pr-arbiter froze). That makes arbiter a downstream,
so seam S5 now applies to it and this file is live rather than an empty channel.

The contract itself warned that adoption pushes the downstream count to 5 and
trips `tessera-watch` P4. That trip is now expected behaviour, not a regression
— noted here so it is not diagnosed as one later.

Contract updated in the same pass: S4's prerequisite was "pr-arbiter Phase 3",
which was abandoned rather than parked; the engine graduated into `arbiter`
instead, so S4's gate is now D3 plus a stable conclave fleet.
