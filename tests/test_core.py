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


# ---------- read-only command allowlist ----------
#
# The model picks these commands after reading a diff, and a diff can contain
# text written by someone else. Every refusal below is a prompt-injection path.

from pathlib import Path as _Path  # noqa: E402

from arbiter.tools import _refuse  # noqa: E402

REPO = _Path("/tmp/repo")


def refused(cmd: str) -> bool:
    import shlex
    return _refuse(REPO, shlex.split(cmd)) is not None


@pytest.mark.parametrize("cmd", [
    "git show HEAD:src/a.py",
    "git diff HEAD~1 HEAD",
    "git log --oneline -5",
    "grep -rn needle src",
    "python3 -c 'print(1)'",
    "sed -n 1,20p src/a.py",
    "wc -l src/a.py",
])
def test_readonly_commands_allowed(cmd):
    assert not refused(cmd)


@pytest.mark.parametrize("cmd", [
    "rm -rf /",                        # not on the allowlist
    "curl http://evil.example",        # no network
    "pip install requests",            # no installs
    "bash -c 'echo hi'",               # no shell
    "git push origin main",            # writes
    "git commit -am wip",              # writes
    "git checkout main",               # mutates the tree under review
    "python3 setup.py",                # would execute code under review
    "cat ../../../etc/passwd",         # escapes the repo
    "cat /etc/passwd",                 # absolute path outside the repo
])
def test_dangerous_commands_refused(cmd):
    assert refused(cmd)


def test_shell_metacharacters_are_inert_not_interpreted():
    """No shell means `;` and `|` arrive as argument text, never as operators.

    `git log ; rm -rf /` cannot chain: shlex yields one argv whose head is git,
    so the `rm` is just a search term. It is refused anyway — the trailing `/`
    trips the path-escape check — so the injection fails twice over. The point
    of this test is the first reason, hence the explicit argv assertions.
    """
    import shlex
    argv = shlex.split("git log ';' rm -rf /")
    assert argv[0] == "git" and argv[2] == ";"   # ';' is a literal argument
    assert _refuse(REPO, argv) is not None       # and refused regardless

    # Same metacharacters, no path escape: still a plain `git log` invocation,
    # so it is allowed — the `|` never becomes a pipe.
    assert _refuse(REPO, shlex.split("git log --grep '|' -5")) is None


# ---------- allowlist bypasses found by arbiter's own verified run ----------

@pytest.mark.parametrize("cmd,why", [
    ("git show HEAD~1:../etc/passwd", "single dotdot after a ref"),
    ("git show HEAD:../../secrets", "dotdot chain after a ref"),
    ("git --exec-path=/tmp/evil show HEAD:a.py", "--exec-path runs foreign binaries"),
    ("git -c alias.x=!sh log", "-c injects config, and aliases can shell out"),
    ("git --upload-pack=/tmp/evil log", "any global option before the subcommand"),
])
def test_git_bypasses_are_refused(cmd, why):
    assert refused(cmd), why


def test_plain_readonly_git_still_works():
    assert not refused("git show HEAD:src/arbiter/cli.py")
    assert not refused("git diff HEAD~1 HEAD -- src")


# ---------- ballot coercion ----------
#
# Observed live: the model returned `votes` as a JSON *string* that was itself
# invalid JSON, because rationales quote shell globs. Every vote then fell to the
# UNSURE default, three runs reported 0 blocking, and two diagnoses were wrong.

from arbiter.triage import _coerce_votes  # noqa: E402


def test_coerce_passes_through_a_proper_list():
    v = [{"index": 0, "vote": "keep", "rationale": "r"}]
    assert _coerce_votes(v) == v


def test_coerce_parses_a_json_string_payload():
    out = _coerce_votes('[{"index": 0, "vote": "drop", "rationale": "r"}]')
    assert out == [{"index": 0, "vote": "drop", "rationale": "r"}]


def test_coerce_recovers_votes_from_malformed_json():
    """The real payload: quotes from the reviewed code break the model's escaping."""
    broken = '''[
      {"index": 0, "vote": "keep", "rationale": "glob *'"source"'*'"startup"'* matches"},
      {"index": 1, "vote": "drop", "rationale": "fine"}
    ]'''
    out = _coerce_votes(broken)
    assert [(v["index"], v["vote"]) for v in out] == [(0, "keep"), (1, "drop")]


def test_coerce_returns_empty_for_unusable_payloads():
    assert _coerce_votes(None) == []
    assert _coerce_votes("not json at all") == []
    assert _coerce_votes(12) == []


# ---------- RCE and write bypasses (arbiter found these in its own allowlist) ----------

@pytest.mark.parametrize("cmd,why", [
    ("find . -exec sh -c 'echo pwned' ;", "find -exec is a full shell escape"),
    ("find . -execdir sh -c x ;", "-execdir likewise"),
    ("find . -ok rm {} ;", "-ok likewise, with a prompt"),
    ("find . -name x -delete", "-delete writes, on a read-only allowlist"),
    ("find . -fprintf /tmp/out %p", "-fprintf writes a file"),
    ("awk -f evil.awk", "-f runs a program file from the repo under review"),
    ("awk --file=evil.awk", "--flag=value form"),
    ("sed -f evil.sed", "sed -f likewise"),
    ("sed -i s/a/b/ file", "-i edits in place"),
    ("grep -f patterns.txt .", "grep -f reads a program file"),
])
def test_exec_and_write_flags_are_refused(cmd, why):
    assert refused(cmd), why


@pytest.mark.parametrize("cmd", [
    "find . -name '*.py'",
    "find . -type f -maxdepth 2",
    "awk '{print $1}' file.txt",
    "sed -n 1,20p file.txt",
    "grep -rn needle src",
])
def test_ordinary_inspection_still_allowed(cmd):
    assert not refused(cmd)


def test_find_exec_does_not_actually_execute(tmp_path):
    """Live check: the refusal happens before subprocess.run, not after."""
    from arbiter.tools import run_command
    out = run_command(tmp_path, "find . -maxdepth 0 -exec sh -c 'echo LEAKED' ;")
    assert out.startswith("REFUSED:")
    assert "LEAKED" not in out


# ---------- ballot coercion, hardened ----------

def test_coerce_handles_vote_before_index():
    """Field order is not guaranteed; the salvage regex must not assume it."""
    broken = '[{"vote": "keep", "index": 0, "rationale": "unterminated }]'
    assert [(v["index"], v["vote"]) for v in _coerce_votes(broken)] == [(0, "keep")]


def test_coerce_unwraps_a_dict_wrapped_array():
    assert _coerce_votes({"votes": [{"index": 0, "vote": "drop"}]}) == [
        {"index": 0, "vote": "drop"}
    ]


def test_coerce_does_not_stitch_pairs_across_two_votes():
    """An index from one object must not pair with a vote from the next.

    The trailing comma makes this unparseable, so the salvage path runs. Object
    0 has an index but no vote and must be dropped rather than borrowing the
    vote from object 1.
    """
    broken = '[{"index": 0, "note": "x"}, {"vote": "keep", "index": 1},]'
    got = [(v["index"], v["vote"]) for v in _coerce_votes(broken)]
    assert got == [(1, "keep")]
