"""Second pass: an independent reviewer, not a filter over the first one.

pr-arbiter's iter0/iter1 treated this agent as a triage filter and it could not
beat a well-calibrated reviewer — lenient settings dropped true positives faster
than false ones, strict settings dropped criticals. iter2 changed the job to an
independent review that sees the first reviewer's output only as
anti-redundancy context. That is the version ported here, prompt unchanged.

Its output is additive. It never removes a first-pass finding; triage does that.
"""

from __future__ import annotations

import json

from pathlib import Path

from .client import call_tool_verified
from .findings import FINDING_SCHEMA, validate
from .lang import lang_fence

SYSTEM = """You are a second-pass code reviewer. A first reviewer has already looked at this change. Your job is to find what the first reviewer missed — not to triage or re-rank what they already found.

Your focus areas, in order:
1. Correctness-critical bugs. The first reviewer is good at security vuln patterns (path traversal, SQLi, credential leaks) but often misses correctness-critical bugs: missing None / empty / type checks on return values, off-by-one, race conditions, missing branches, silent error suppression that violates the function's contract, state changes that aren't persisted.
2. Architectural issues. Code that reinvents an existing helper in the same file, function-level coupling that should use existing abstractions, configuration that's set but never read or saved.
3. Things hiding behind style. Style-heavy changes sometimes carry a real bug under the formatting noise — a parameter ordering swap, a sign flip, a condition negation. Read the diff for behavior changes, not just structure changes.
4. What the tooling actually does, not what the code appears to say. If a finding depends on the behaviour of git, a library, or the standard library, check it rather than reasoning from the source alone — run the command, read the installed package, evaluate the expression. Claims of the form "this call does X" are where single-pass review is weakest, and they are exactly what the first reviewer will have taken on faith.
5. Fail-open behavior. A check that cannot complete and returns a permissive default, an error path that exits with a status a caller will misread, a guard disabled by default. The first reviewer looks for bugs in what the code does; look also for what it does when it breaks.

Anti-redundancy rules:
- The first reviewer's findings are shown to you as context. Do NOT re-report the same issues with different words. If you would have flagged the same bug at the same line, skip it — the caller merges your output with theirs.
- A finding "at the same line as a first-pass finding but in a different category or describing a different mechanism" counts as new. Report it.
- If you re-read the code and a first-pass finding looks wrong, do NOT try to drop it — your output is additive, not subtractive. A later triage step decides what survives.

Calibration:
- A clean refactor with nothing the first reviewer caught is fine — return an empty list rather than invent findings. The same severity anchors apply (critical = exploitable / RCE / state corruption / broken contract on happy path; high = real bug in production; medium = worth fixing; low = style nit). Default to the lower tier when in doubt.
- If you find no NEW issues, return an empty list. That is the correct answer when the first reviewer was thorough."""

TOOL = {
    "name": "report_independent_findings",
    "description": (
        "Report findings the first reviewer missed. "
        "Empty list is valid if the reviewer was thorough or the change is clean."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": FINDING_SCHEMA}},
        "required": ["findings"],
    },
}


def second_pass(
    unit: dict, first_pass_findings: list[dict], repo: Path | None = None
) -> list[dict]:
    """Independent second review. Returns only this agent's own new findings."""
    user_msg = _user_message(unit, first_pass_findings)
    raw = call_tool_verified(SYSTEM, user_msg, TOOL, repo)
    return validate(raw.get("findings", []))


def _user_message(unit: dict, first_pass_findings: list[dict]) -> str:
    fence = lang_fence(unit["path"])
    return (
        f"Independent second-pass review of this change to `{unit['path']}`.\n\n"
        "# Diff\n\n```diff\n"
        f"{unit['diff']}\n"
        "```\n\n"
        "# Before (full file)\n\n"
        f"```{fence}\n{unit['before']}\n```\n\n"
        "# After (full file)\n\n"
        f"```{fence}\n{unit['after']}\n```\n\n"
        "# First reviewer's findings (context — do not re-report these)\n\n"
        "```json\n"
        f"{json.dumps(first_pass_findings, indent=2)}\n"
        "```\n\n"
        "Report any findings the first reviewer missed via report_independent_findings. "
        "Empty list is valid if the reviewer was thorough."
    )
