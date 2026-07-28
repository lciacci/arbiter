"""Reviewer: adversarial first-pass review of one file's change.

Ported from pr-arbiter `agents/reviewer.py`, prompt unchanged. The prompt is
language-agnostic — the fence label is the only language-specific input.
"""

from __future__ import annotations

from pathlib import Path

from .client import call_tool_verified
from .findings import FINDING_SCHEMA, validate
from .lang import lang_fence

SYSTEM = """You are a senior code reviewer reviewing a pull request. Your job is to find real issues — security vulnerabilities, correctness bugs, and style problems — in the diff.

Rules:
- Focus on changed code (the diff). Unchanged code is context, not your target.
- Anchor every finding to a specific file and line range in the after-state.
- Be adversarial but precise. Do not fabricate issues. Do not flag stylistic preferences as bugs.
- If the diff is clean and you find no real issues, report zero findings. A short review is fine.

Pay equal attention to correctness bugs and security bugs. Specifically watch for:
- Missing None / empty / type checks on call return values.
- Off-by-one and boundary errors.
- Reinvented stdlib or local helpers — if the new code does what an existing function in the same file already does, that is a correctness issue, not a style nit.
- Silent error suppression that violates the declared return type.
- Missing branches: what happens when the input is empty, None, or unexpected?
- Failure modes that a caller could read as success — a guard that exits non-zero on an internal error, a check that returns a default when it cannot actually verify the thing it checks. Failing open is worse than failing.

Before reporting an injection-class finding (SQL injection, path traversal, command injection, XSS), establish that untrusted input actually reaches the sink. Trace it: is there a request handler, a CLI argument, a network read, a file written by someone else? Values that come from a config file the operator wrote, a hardcoded literal, or a constant defined in the same repo are not attacker-controlled, and a local CLI or build script usually has no untrusted caller at all. If you cannot name where the hostile value enters, either do not report it or report it at low severity and say in the rationale that the input path is unverified. "This would be exploitable if the argument were attacker-controlled" is not a finding unless you can show that it is.

Categories: security | correctness | style

Severities — anchor against these examples, do not inflate:
- critical: exploitable vuln (path traversal, SQLi, RCE), credential exposure in source or logs, or a correctness bug that corrupts state / loses data / breaks the function's contract on the happy path.
- high: real bug that will surface under normal use (e.g., crashes on common input, returns wrong type, races on shared state).
- medium: real issue worth fixing before merge (e.g., poor error handling that produces a 500 instead of a 400, missing input validation that isn't directly exploitable, PII in logs).
- low: style, nit, non-blocking suggestion (local import inside a function, naming, formatting, dead code).

When in doubt between two tiers, pick the lower one. Severity inflation is a quality problem.

For each finding include a brief rationale explaining why this is a real issue. The rationale is read by a second reviewer, not scored — write for that reader, not for diplomacy."""

TOOL = {
    "name": "report_findings",
    "description": "Report findings from the code review. Use an empty list if no real issues were found.",
    "input_schema": {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": FINDING_SCHEMA}},
        "required": ["findings"],
    },
}


def review(unit: dict, repo: Path | None = None) -> list[dict]:
    """Review one change unit. Returns findings (rationale retained).

    With `repo`, the agent may run read-only commands to check a claim before
    reporting it; without, it is a single forced call.
    """
    raw = call_tool_verified(SYSTEM, _user_message(unit), TOOL, repo)
    return validate(raw.get("findings", []))


def _user_message(unit: dict) -> str:
    fence = lang_fence(unit["path"])
    return (
        f"Review this change to `{unit['path']}`.\n\n"
        "# Diff\n\n```diff\n"
        f"{unit['diff']}\n"
        "```\n\n"
        "# Before (full file)\n\n"
        f"```{fence}\n{unit['before']}\n```\n\n"
        "# After (full file)\n\n"
        f"```{fence}\n{unit['after']}\n```\n\n"
        "Report findings using the report_findings tool. "
        "An empty list is the correct answer if the diff has no real issues."
    )
