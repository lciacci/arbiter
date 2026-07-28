"""Finding shape, validation, and the reviewer/arbiter merge.

A finding is a dict:
    file, line_range [start, end], category, severity, description, rationale?

Ported from pr-arbiter with the duplicated `_validate` collapsed to one copy.
"""

from __future__ import annotations

CATEGORIES = ("security", "correctness", "style")
SEVERITIES = ("critical", "high", "medium", "low")

_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# JSON-schema fragment shared by the reviewer and arbiter tools. Both agents
# report the same shape; only the prompt and the tool name differ.
FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string", "description": "File path as given in the review request."},
        "line_range": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
            "description": "[start_line, end_line] inclusive, in the after-state file.",
        },
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "description": {"type": "string", "description": "What the issue is. One sentence."},
        "rationale": {
            "type": "string",
            "description": "Why this is a real issue, argued from the code. One or two sentences.",
        },
    },
    "required": ["file", "line_range", "category", "severity", "description", "rationale"],
}


def validate(findings: list) -> list[dict]:
    """Drop malformed entries. The tool schema is strict; this is defense in depth."""
    out: list[dict] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        lr = f.get("line_range")
        if not (isinstance(lr, list) and len(lr) == 2 and all(isinstance(x, int) for x in lr)):
            continue
        if not all(k in f for k in ("file", "category", "severity", "description")):
            continue
        out.append(f)
    return out


def severity_rank(finding: dict) -> int:
    """Sort key: critical first. Unknown severities sort last."""
    return -_SEV_RANK.get(finding.get("severity", ""), 0)


def merge(
    reviewer_findings: list[dict],
    arbiter_findings: list[dict],
    line_tolerance: int = 3,
) -> list[dict]:
    """Union reviewer + arbiter findings, deduping by approximate match.

    Approximate match: same file + category, line midpoints within
    ±line_tolerance. On a match, keep the higher-severity version; on a tie,
    keep the reviewer's (it ran first).
    """
    merged: list[dict] = list(reviewer_findings)
    for a in arbiter_findings:
        hit = next((i for i, m in enumerate(merged) if _matches(m, a, line_tolerance)), None)
        if hit is None:
            merged.append(a)
        elif _SEV_RANK.get(a.get("severity"), 0) > _SEV_RANK.get(merged[hit].get("severity"), 0):
            merged[hit] = a
    return merged


def _matches(a: dict, b: dict, tol: int) -> bool:
    if a.get("file") != b.get("file") or a.get("category") != b.get("category"):
        return False
    a_lines = a.get("line_range", [0, 0])
    b_lines = b.get("line_range", [0, 0])
    a_mid = (a_lines[0] + a_lines[1]) / 2
    b_mid = (b_lines[0] + b_lines[1]) / 2
    return abs(a_mid - b_mid) <= tol
