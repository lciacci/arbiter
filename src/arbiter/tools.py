"""A read-only shell tool the review agents can call to check their claims.

Why this exists: a workflow-backed review found six defects arbiter had twice
declared clean, and every one was findable within a single file. The gap was
not context — it was that its agents could only *reason* about what git does,
while the agents that found them could *run git and look*. Reading Python and
knowing that pathspec filtering defeats rename detection are different skills;
only one of them is available to a model staring at a text blob.

## Security

The model is choosing these commands after reading a diff, and a diff can
contain text written by someone else. That makes this a prompt-injection
surface: hostile content in a reviewed file could try to talk the reviewer into
running something. The mitigations, in order of how much they carry:

- **Allowlist, not denylist.** Only the binaries in ALLOWED run, and `git` is
  further restricted to read-only subcommands. Anything unlisted is refused.
- **No shell.** Commands are shlex-split and passed as argv. There is no shell,
  so `;`, `|`, `>`, backticks and `$(…)` are inert argument text.
- **Confined to the repo.** cwd is the repo root; arguments that escape it via
  `..` or an absolute path are refused.
- **Bounded.** Wall-clock timeout and truncated output, so a command cannot
  hang or flood the context.

This is not a sandbox. It is a narrow allowlist that makes the obvious attacks
fail. Reviewing genuinely untrusted code — a PR from a stranger — warrants a
container, and `--no-verify` turns the tool off entirely.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

TIMEOUT_SECONDS = 20
MAX_OUTPUT_CHARS = 6000

# Read-only inspection only. Nothing that writes, networks, or installs.
ALLOWED = frozenset({
    "git", "grep", "rg", "ls", "cat", "head", "tail", "wc", "find", "file",
    "python3", "sed", "awk", "sort", "uniq", "diff", "basename", "dirname",
})

# git is the whole point of this tool and also the easiest way to mutate a
# repo, so its subcommands are allowlisted separately.
GIT_READONLY = frozenset({
    "show", "diff", "log", "cat-file", "ls-files", "ls-tree", "rev-parse",
    "merge-base", "blame", "grep", "status", "describe", "shortlog", "name-rev",
})

RUN_TOOL = {
    "name": "run_command",
    "description": (
        "Run a read-only shell command inside the repository to check a claim before "
        "reporting it. Use this to verify what code actually does rather than inferring "
        "it: run git to see how a diff is really produced, grep for a symbol's other "
        "uses, or `python3 -c` to evaluate an expression. Prefer checking over guessing. "
        "Read-only commands only; writes, installs and network access are refused."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command line, e.g. \"git log --oneline -5\". No shell syntax.",
            },
            "why": {
                "type": "string",
                "description": "What claim this checks, in one clause.",
            },
        },
        "required": ["command", "why"],
    },
}


def run_command(repo: Path, command: str) -> str:
    """Execute an allowlisted read-only command. Returns output or a refusal."""
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return f"REFUSED: could not parse command ({e})"
    if not argv:
        return "REFUSED: empty command"

    verdict = _refuse(repo, argv)
    if verdict:
        return f"REFUSED: {verdict}"

    try:
        proc = subprocess.run(
            argv, cwd=repo, capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS, shell=False,
        )
    except subprocess.TimeoutExpired:
        return f"REFUSED: exceeded {TIMEOUT_SECONDS}s"
    except (OSError, ValueError) as e:
        return f"REFUSED: {e}"

    out = (proc.stdout or "") + (proc.stderr or "")
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + f"\n… [truncated at {MAX_OUTPUT_CHARS} chars]"
    return out or f"(no output, exit {proc.returncode})"


def _refuse(repo: Path, argv: list[str]) -> str | None:
    """Reason to refuse, or None to allow."""
    binary = Path(argv[0]).name
    if binary not in ALLOWED:
        return f"{binary!r} is not in the read-only allowlist"
    if binary == "git":
        sub = next((a for a in argv[1:] if not a.startswith("-")), None)
        if sub not in GIT_READONLY:
            return f"git subcommand {sub!r} is not read-only"
    if binary in ("python3", "awk", "sed") and not _script_is_inline(argv):
        return f"{binary} is allowed only with an inline script (-c / -n / program text)"
    for arg in argv[1:]:
        if bad := _escapes_repo(repo, arg):
            return bad
    return None


def _script_is_inline(argv: list[str]) -> bool:
    """python3 -c / sed -n / awk 'prog' — not `python3 some_file.py`.

    Running a file from the repo would execute code under review, which is the
    one thing a reviewer must never do.
    """
    if Path(argv[0]).name == "python3":
        return "-c" in argv
    return True


def _escapes_repo(repo: Path, arg: str) -> str | None:
    if arg.startswith("-"):
        return None
    # Refs and pathspecs like `HEAD~1:src/a.py` are not filesystem paths.
    if ":" in arg or arg.startswith("HEAD") or ".." in arg.split("/"):
        if ".." in arg.split("/"):
            return f"path {arg!r} escapes the repository"
        return None
    if Path(arg).is_absolute():
        try:
            Path(arg).resolve().relative_to(repo.resolve())
        except ValueError:
            return f"absolute path {arg!r} is outside the repository"
    return None
