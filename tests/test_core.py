"""Checks for the pure logic — merge, triage aggregation, fence, git parsing.

No API calls. Everything model-facing is a prompt; everything here is the code
that decides what survives, which is where a silent bug would actually hurt.
"""

from __future__ import annotations

import pytest

from arbiter.findings import merge, severity_rank, validate
from arbiter.lang import is_reviewable, lang_fence
from arbiter.triage import classify


def f(file="a.py", line=10, category="correctness", severity="high", desc="x"):
    return {
        "file": file,
        "line_range": [line, line + 2],
        "category": category,
        "severity": severity,
        "description": desc,
    }


# ---------- merge ----------

def test_merge_appends_non_duplicates():
    assert len(merge([f(line=10)], [f(line=100)])) == 2


def test_merge_dedupes_within_line_tolerance():
    assert len(merge([f(line=10)], [f(line=12)])) == 1


def test_merge_keeps_higher_severity_on_duplicate():
    merged = merge([f(line=10, severity="low")], [f(line=11, severity="critical")])
    assert len(merged) == 1
    assert merged[0]["severity"] == "critical"


def test_merge_prefers_first_pass_on_severity_tie():
    merged = merge([f(line=10, desc="first")], [f(line=11, desc="second")])
    assert merged[0]["description"] == "first"


def test_merge_does_not_dedupe_across_category_or_file():
    assert len(merge([f(category="security")], [f(category="correctness")])) == 2
    assert len(merge([f(file="a.py")], [f(file="b.py")])) == 2


# ---------- triage aggregation ----------

def votes(*vs):
    return [{"index": i, "vote": v, "rationale": ""} for i, v in enumerate(vs)]


@pytest.mark.parametrize(
    "reviewer,arbiter,expected",
    [
        ("keep", "keep", "blocking"),
        ("drop", "drop", "dropped"),
        ("keep", "drop", "advisory"),
        ("drop", "keep", "advisory"),
        ("unsure", "keep", "advisory"),
        ("unsure", "unsure", "advisory"),
    ],
)
def test_classify_aggregation_rule(reviewer, arbiter, expected):
    (_, conf), = classify([f()], votes(reviewer), votes(arbiter))
    assert conf == expected


def test_classify_missing_votes_become_advisory_not_dropped():
    """A parse failure must never silently delete a finding."""
    (_, conf), = classify([f()], [], [])
    assert conf == "advisory"


# ---------- validation ----------

@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {"file": "a.py", "category": "correctness", "severity": "high", "description": "x"},
        {**f(), "line_range": [1]},
        {**f(), "line_range": ["1", "3"]},
    ],
)
def test_validate_drops_malformed(bad):
    assert validate([bad]) == []


def test_validate_keeps_wellformed():
    assert validate([f()]) == [f()]


# ---------- ordering ----------

def test_severity_rank_sorts_critical_first():
    order = sorted(
        [f(severity="low"), f(severity="critical"), f(severity="medium")],
        key=severity_rank,
    )
    assert [x["severity"] for x in order] == ["critical", "medium", "low"]


# ---------- language ----------

@pytest.mark.parametrize(
    "path,fence",
    [("a.py", "python"), ("scripts/gate.sh", "bash"), ("x.ts", "typescript"),
     ("q.sql", "sql"), ("Makefile", ""), ("weird.xyz", "")],
)
def test_lang_fence(path, fence):
    assert lang_fence(path) == fence


def test_shell_is_reviewable_by_default():
    """Regression: pr-arbiter's runner was .py-only, which skipped every hook."""
    assert is_reviewable("scripts/gate.sh")
    assert is_reviewable("src/app.ts")
    assert not is_reviewable("README.md")


# ---------- path filtering ----------

from arbiter.vcs import matches_any  # noqa: E402


@pytest.mark.parametrize(
    "path,patterns,expected",
    [
        ("src/arbiter/cli.py", [], True),                      # no filter = everything
        ("src/arbiter/cli.py", ["src/arbiter"], True),         # directory prefix
        ("src/arbiter/cli.py", ["src/arbiter/"], True),        # trailing slash tolerated
        ("src/arbiter/cli.py", ["src/arb"], False),            # prefix must be a path segment
        ("scripts/gate/scan.py", ["src/arbiter"], False),
        ("scripts/sql/lint.sh", ["*.sh"], True),               # glob
        ("src/arbiter/cli.py", ["tests", "src/arbiter"], True),  # any-of
        ("README.md", ["src/arbiter"], False),
    ],
)
def test_matches_any(path, patterns, expected):
    assert matches_any(path, patterns) is expected
