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

from typing import Literal

from .client import call_tool
from .lang import lang_fence

Voice = Literal["reviewer", "arbiter"]
Confidence = Literal["blocking", "advisory", "dropped"]

# Recall-oriented. Keeps a finding when the bug claim is plausible.
REVIEWER_VOICE = """You are a senior code reviewer. A set of findings has been compiled on a change. For each finding, decide whether it represents a real issue in the after-state code.

Vote KEEP if you can re-state the bug from the code without relying on the finding's wording.
Vote DROP if re-reading the code shows the finding is wrong, the reviewer misread something, or the issue does not apply to the after-state behavior.
Vote UNSURE if you can construct an argument both ways and can't reach a confident call from the code alone.

You see only the findings — not who proposed them. Treat every finding the same. Be willing to drop your own first instinct if the code doesn't support it. Be willing to keep findings that you wouldn't have flagged yourself if they describe a real bug.

For each vote include a one-sentence rationale grounded in the code."""

# Skeptical. Drops a finding when the bug can't be reproduced on close reading.
ARBITER_VOICE = """You are a skeptical second-pass reviewer. A set of findings has been compiled on a change. For each finding, decide whether it represents a real issue you would block on, after carefully re-reading the after-state code.

Vote KEEP if the bug claim is concrete and you can reproduce the issue from the code without referring back to the finding's wording.
Vote DROP if the finding is speculative, restates a different finding using different words, applies to unchanged code, or describes a "what if" that the function's contract does not actually allow.
Vote UNSURE if the issue is real but small, or if the bug claim is plausible but you can't verify it cleanly from the diff alone.

You see only the findings — not who proposed them. Apply equal scrutiny to every finding. A clean refactor where every finding is a hallucination is a legitimate outcome — return DROP on all of them if that is what the code shows.

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

    system = REVIEWER_VOICE if voice == "reviewer" else ARBITER_VOICE
    raw = call_tool(system, _user_message(unit, findings), TOOL).get("votes", [])
    by_index = {v["index"]: v for v in raw if isinstance(v, dict) and "index" in v}

    out: list[dict] = []
    for i in range(len(findings)):
        v = by_index.get(i)
        if not v or v.get("vote") not in ("keep", "drop", "unsure"):
            out.append({"index": i, "vote": "unsure", "rationale": "missing or malformed vote"})
        else:
            out.append({"index": i, "vote": v["vote"], "rationale": v.get("rationale", "")})
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
    numbered = "\n".join(
        f"[{i}] {f['file']} L{f['line_range']} {f['category']}/{f['severity']}: {f['description']}"
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
