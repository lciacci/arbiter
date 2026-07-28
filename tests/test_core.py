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


# ---------- git name-status parsing ----------

from arbiter.vcs import parse_name_status  # noqa: E402


def test_parse_name_status_plain():
    assert parse_name_status("M\tsrc/a.py\nA\tsrc/b.py") == [
        ("M", "src/a.py", "src/a.py"),
        ("A", "src/b.py", "src/b.py"),
    ]


def test_parse_name_status_rename_keeps_old_path():
    """Regression: before-state must be read at the path the file had at base.

    Using the destination path against base returns empty, so a renamed file
    was reviewed as if newly written — with no before-state to compare to.
    """
    assert parse_name_status("R100\told/name.py\tnew/name.py") == [
        ("R", "new/name.py", "old/name.py")
    ]


def test_parse_name_status_copy_keeps_source_path():
    assert parse_name_status("C75\tsrc/orig.py\tsrc/copy.py") == [
        ("C", "src/copy.py", "src/orig.py")
    ]


def test_parse_name_status_ignores_malformed_lines():
    assert parse_name_status("garbage\n\nM\tok.py") == [("M", "ok.py", "ok.py")]


# ---------- fail-loud contract ----------

from arbiter.client import AgentError, call_tool  # noqa: E402


class _FakeResp:
    def __init__(self, content):
        self.content = content
        self.stop_reason = "end_turn"


class _Block:
    def __init__(self, type, name=None, input=None):
        self.type, self.name, self.input = type, name, input


def test_call_tool_raises_when_no_tool_use_block(monkeypatch):
    """A missing tool_use block must raise, never read as 'no findings'.

    tool_choice forces the tool, so its absence means something failed. If this
    returned {}, every caller's .get("findings", []) would yield [] and the
    file would be reported clean — an error a gate mistakes for a pass.
    """
    monkeypatch.setattr(
        "arbiter.client.client",
        lambda: type("C", (), {"messages": type("M", (), {
            "create": staticmethod(lambda **kw: _FakeResp([_Block("text")]))
        })()})(),
    )
    with pytest.raises(AgentError, match="no tool_use block"):
        call_tool("sys", "msg", {"name": "report_findings"})


def test_call_tool_returns_tool_input_when_present(monkeypatch):
    monkeypatch.setattr(
        "arbiter.client.client",
        lambda: type("C", (), {"messages": type("M", (), {
            "create": staticmethod(
                lambda **kw: _FakeResp([_Block("tool_use", "report_findings", {"findings": [1]})])
            )
        })()})(),
    )
    assert call_tool("sys", "msg", {"name": "report_findings"}) == {"findings": [1]}


# ---------- dotfiles ----------

def test_dotfiles_are_extensionless():
    """A leading-dot basename is a dotfile, not a file of that type.

    Only `.py` actually discriminates: for `.gitignore` and `my.dir/Makefile`
    the old rsplit produced junk ("gitignore", "dir/makefile") that matched no
    key either, so both implementations agreed. Asserting those alone would be
    a test that passes against the code it is supposed to guard.
    """
    assert lang_fence(".py") == ""          # old impl returned "python"
    assert not is_reviewable(".py")         # old impl returned True
    assert lang_fence(".gitignore") == ""
    assert not is_reviewable("my.dir/Makefile")
    assert is_reviewable("my.dir/run.sh")


# ---------- fail-loud CLI paths ----------
#
# The load-bearing promise of this tool is that an unreviewed file never reads
# as a clean one. Nothing asserted that until these.

from arbiter.cli import exit_code, render  # noqa: E402


def ok(path="a.py", blocking=(), advisory=()):
    return {"path": path, "status": "M", "blocking": list(blocking),
            "advisory": list(advisory), "dropped": [],
            "counts": {"first_pass": 0, "second_pass": 0, "merged": 0},
            "triage_note": None}


def err(path="b.py", error="AgentError: no tool_use block"):
    return {"path": path, "status": "M", "error": error, "counts": {},
            "blocking": [], "advisory": [], "dropped": [], "triage_note": None}


def test_blocking_outranks_failure_in_exit_code():
    """A partial failure must not downgrade a confirmed blocking finding.

    Regression: `if failed: return 2` ran first, so a hook branching on 1 for
    blocking never saw it when any file also errored.
    """
    assert exit_code([ok(blocking=[f()]), err()]) == 1


def test_failed_file_never_exits_zero():
    assert exit_code([ok(), err()]) == 3
    assert exit_code([err()]) == 3


def test_clean_run_exits_zero():
    assert exit_code([ok(), ok()]) == 0


def test_render_never_claims_triage_agreed_when_nothing_was_reviewed():
    """The all-clear is a quotable claim; it must not appear after a total failure."""
    out = render([err(), err("c.py")], "main", "HEAD")
    assert "Both triage voices agreed" not in out
    assert "not a clean result" in out
    assert "0 file(s) reviewed" in out


def test_render_hedges_the_all_clear_when_some_files_failed():
    out = render([ok(), err()], "main", "HEAD")
    assert "Both triage voices agreed" not in out
    assert "files that completed triage" in out


def test_render_lists_failures_as_unreviewed():
    out = render([err("b.py", "boom")], "main", "HEAD")
    assert "failed to review" in out and "b.py" in out and "boom" in out


def test_render_surfaces_degraded_triage():
    r = ok(advisory=[f()])
    r["triage_note"] = "triage failed, all findings held advisory: boom"
    out = render([r], "main", "HEAD")
    assert "skipped triage" in out and "not confirmed" in out
