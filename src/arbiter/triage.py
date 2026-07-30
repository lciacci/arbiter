"""Mutual triage: two voices vote KEEP / DROP / UNSURE on the merged list.

This is the step pr-arbiter's dogfooding script never wired in, and it is the
one that makes the output usable rather than merely long. Both voices are
source-blind — they see findings, not who proposed them. Aggregation:

    both keep    -> blocking   (high confidence)
    both drop    -> dropped
    anything else -> advisory  (low confidence)

Ported from pr-arbiter `agents/triage.py`. One fix on the way over: the
original hardcoded a ```python fence in the user message, which mislabels every
non-Python file. It now uses the same lang_fence as the other agents.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from .client import AgentError, call_tool
from .lang import lang_fence

Voice = Literal["reviewer", "arbiter"]
Confidence = Literal["blocking", "advisory", "dropped"]

# Recall-oriented. Keeps a finding when the bug claim is plausible.
REVIEWER_VOICE = """You are a senior code reviewer. A set of findings has been compiled on a change. For each finding, decide whether it represents a real issue in the after-state code.

Vote KEEP if you can re-state the bug from the code without relying on the finding's wording.
Vote DROP if re-reading the code shows the finding is wrong, the reviewer misread something, or the issue does not apply to the after-state behavior.
Vote UNSURE if you can construct an argument both ways and can't reach a confident call from the code alone.

You see only the findings — not who proposed them. Treat every finding the same. Be willing to drop your own first instinct if the code doesn't support it. Be willing to keep findings that you wouldn't have flagged yourself if they describe a real bug.

Each finding is shown with the reasoning its author gave. Read that reasoning critically — it is an argument, not evidence.

Distinguish two things that both look like hedging:
- Bounding the claim — naming what has to be true for the bug to bite, which code path reaches it, how likely that is. That is a well-calibrated finding, and it is evidence the author actually checked. KEEP on the merits.
- Undermining the claim — contradicting itself, conceding the code is correct after all, or arguing its way back out of the conclusion it opened with. DROP, however confident the one-line description sounds.

A finding that says "this is a real bug, and it only fires when X" is stronger than one that asserts a bug flatly. Do not punish precision.

For each vote include a one-sentence rationale grounded in the code."""

# Skeptical. Drops a finding when the bug can't be reproduced on close reading.
ARBITER_VOICE = """You are a skeptical second-pass reviewer. A set of findings has been compiled on a change. For each finding, decide whether it represents a real issue you would block on, after carefully re-reading the after-state code.

Vote KEEP if the bug claim is concrete and you can reproduce the issue from the code without referring back to the finding's wording.
Vote DROP if the finding is speculative, restates a different finding using different words, applies to unchanged code, or describes a "what if" that the function's contract does not actually allow.
Vote UNSURE if the issue is real but small, or if the bug claim is plausible but you can't verify it cleanly from the diff alone.

You see only the findings — not who proposed them. Apply equal scrutiny to every finding. A clean refactor where every finding is a hallucination is a legitimate outcome — return DROP on all of them if that is what the code shows.

Each finding is shown with the reasoning its author gave. Treat that reasoning as the claim's strongest case: if it still does not establish that the bug is real, DROP.

Be precise about what fails that test. A rationale that bounds the bug — "this fires only when jq is absent", "reachability depends on another field carrying the string" — has established the bug and told you its blast radius; that is rigor, not weakness, and it is grounds to KEEP. What fails is a rationale that concedes the code is correct, contradicts its own description, or reasons its way back out of the conclusion it opened with.

Judge whether the bug is real, not how confidently it was asserted.

For each vote include a one-sentence rationale grounded in the code."""

TOOL = {
    "name": "report_votes",
    "description": "Cast a KEEP / DROP / UNSURE vote on every finding, in order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "votes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "0-based index of the finding, matching input order.",
                        },
                        "vote": {"type": "string", "enum": ["keep", "drop", "unsure"]},
                        "rationale": {"type": "string"},
                    },
                    "required": ["index", "vote", "rationale"],
                },
            }
        },
        "required": ["votes"],
    },
}


def vote(unit: dict, findings: list[dict], voice: Voice) -> list[dict]:
    """One voice votes on every finding. Returns votes in input order.

    Missing or malformed votes default to UNSURE, which classifies as advisory
    rather than dropped — a parse failure must not silently delete a finding.
    """
    if not findings:
        return []

    # No cache_prefix here, deliberately. Measured with count_tokens against
    # claude-sonnet-4-6, whose minimum cacheable prefix is 1024 tokens: this
    # tool plus REVIEWER_VOICE is 1017, plus ARBITER_VOICE is 1024. One voice is
    # below the floor and the other sits exactly on it, so a breakpoint would
    # silently cache nothing half the time and flip on any wording edit. A
    # marker that caches nothing is worse than no marker — it reads as done.
    # Re-measure before adding one; do not add it on the assumption that a
    # prompt this size must be cacheable.
    system = REVIEWER_VOICE if voice == "reviewer" else ARBITER_VOICE
    raw = call_tool(system, _user_message(unit, findings), TOOL).get("votes", [])
    parsed = _coerce_votes(raw)
    by_index = {v["index"]: v for v in parsed if isinstance(v, dict) and "index" in v}

    # A ballot that could not be read at all is a failure, not a shrug. Defaulting
    # every finding to UNSURE turns it into "nothing blocking" — a total triage
    # failure that reads as a clean review. That silently produced 0 blocking on
    # three consecutive runs and cost two wrong diagnoses before the ballot was
    # logged. Per-finding gaps still default to UNSURE; a wholesale failure raises.
    if findings and not by_index:
        raise AgentError(
            f"{voice} voice returned no readable votes for {len(findings)} findings "
            f"(payload type {type(raw).__name__}). "
            "Refusing to record that as an all-UNSURE ballot."
        )

    out: list[dict] = []
    for i in range(len(findings)):
        v = by_index.get(i)
        if not v or v.get("vote") not in ("keep", "drop", "unsure"):
            out.append({"index": i, "vote": "unsure", "rationale": "missing or malformed vote"})
        else:
            out.append({"index": i, "vote": v["vote"], "rationale": v.get("rationale", "")})
    return out


def _coerce_votes(raw: object) -> list[dict]:
    """Normalise the model's `votes` payload into a list of vote dicts.

    Two observed deviations from the schema, both content-dependent:

    1. `votes` arrives as a JSON *string* rather than an array.
    2. That string is not valid JSON, because rationales quote the code under
       review. A finding about the shell glob `*'"source"'*'"startup"'*` puts
       single quotes, double quotes and backslashes into a rationale, and the
       model's own escaping does not survive it.

    So: pass lists through, try strict parsing, and fall back to pulling the
    index/vote pairs out with a regex. The rationale is lost in that last case,
    which is acceptable — it is diagnostic text, while the vote is the decision.
    """
    if isinstance(raw, list):
        return [v for v in raw if isinstance(v, dict)]
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return _salvage(raw)
        return _coerce_votes(loaded)
    if isinstance(raw, dict):
        # Seen: the array arrives wrapped, e.g. {"votes": [...]}. Recurse into
        # the first list-valued entry rather than discarding a readable ballot.
        for v in raw.values():
            if isinstance(v, list):
                return _coerce_votes(v)
    return []


def _salvage(raw: str) -> list[dict]:
    """Pull index/vote pairs out of a ballot whose JSON will not parse.

    Field order is not guaranteed, so index-then-vote and vote-then-index are
    both matched. Objects are split on braces first so a pair cannot be assembled
    from two different votes.
    """
    out: list[dict] = []
    for chunk in re.findall(r"\{[^{}]*\}", raw, re.DOTALL):
        i = re.search(r'"index"\s*:\s*(\d+)', chunk)
        v = re.search(r'"vote"\s*:\s*"(keep|drop|unsure)"', chunk)
        if i and v:
            out.append({"index": int(i.group(1)), "vote": v.group(1),
                        "rationale": "(recovered; ballot JSON was malformed)"})
    return out


def classify(
    findings: list[dict],
    reviewer_votes: list[dict],
    arbiter_votes: list[dict],
) -> list[tuple[dict, Confidence]]:
    """Apply the aggregation rule to each finding."""
    out: list[tuple[dict, Confidence]] = []
    for i, f in enumerate(findings):
        rv = reviewer_votes[i]["vote"] if i < len(reviewer_votes) else "unsure"
        av = arbiter_votes[i]["vote"] if i < len(arbiter_votes) else "unsure"
        if rv == "keep" and av == "keep":
            out.append((f, "blocking"))
        elif rv == "drop" and av == "drop":
            out.append((f, "dropped"))
        else:
            out.append((f, "advisory"))
    return out


def _user_message(unit: dict, findings: list[dict]) -> str:
    fence = lang_fence(unit["path"])
    # The rationale must be on the ballot. Without it the voices see only the
    # claim and never the argument, so a finding whose own rationale retracts it
    # ("re-reading: this is actually correct") still collects two KEEP votes and
    # is promoted to blocking. Observed exactly that on a real run.
    numbered = "\n\n".join(
        f"[{i}] {f['file']} L{f['line_range']} {f['category']}/{f['severity']}: "
        f"{f['description']}"
        + (f"\n    Reasoning given: {f['rationale']}" if f.get("rationale") else "")
        for i, f in enumerate(findings)
    )
    return (
        f"Vote on each of the following findings against this change to `{unit['path']}`.\n\n"
        "# Diff\n\n```diff\n"
        f"{unit['diff']}\n"
        "```\n\n"
        "# Before (full file)\n\n"
        f"```{fence}\n{unit['before']}\n```\n\n"
        "# After (full file)\n\n"
        f"```{fence}\n{unit['after']}\n```\n\n"
        "# Findings to vote on\n\n"
        f"{numbered}\n\n"
        "Use the report_votes tool. Cast one vote per finding, in order. "
        "KEEP, DROP, or UNSURE; one-sentence rationale each."
    )
