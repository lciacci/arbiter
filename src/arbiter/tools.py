"""Typed, read-only inspection tools the review agents can call.

Why these exist: agents that can only reason about what git does miss defects
that agents which *run git and look* catch. Verification is worth having.

## Why they are typed rather than a shell command

The first version of this module took a command string, shlex-split it, and
allowed it if argv[0] was on a list of "read-only" binaries. An independent
review found five separate ways through it, all confirmed by execution:

- `python3 -c '<anything>'` — the allowlist admitted a full interpreter, which
  makes every other restriction decorative.
- `./scripts/cat foo` — only the *basename* was matched against the allowlist
  and argv[0] was never path-checked, so a binary shipped in the branch under
  review would run.
- `sort -o/etc/evil`, `git diff --output=/etc/evil`,
  `git grep --open-files-in-pager=id` — every argument starting with `-` was
  skipped by the containment check, so attached-value options escaped it.
- `find . -exec sh -c id \;` and `awk 'BEGIN{system("...")}'` — nothing looked
  past argv[0] for an executable, so a shell ran as an argument.
- `sed -i.bak s/a/b/ file` — a write, from a tool documented as read-only.
  Denying the exact token `-i` did not stop `-i.bak`.

Each individual hole was patchable and patching them was the wrong move: a
general-purpose Unix tool is a language, and enumerating the dangerous
sentences in a language does not work. The model now supplies *parameters*, not
argv. Every command below is a fixed argument vector with model input confined
to positions that cannot become flags.

## What that buys

No shell, no interpreter, no writes, no network, and no argv parsing to defeat.
Paths and refs are validated; search patterns go through `-e` so they cannot be
read as options.

Everything reads through git at a pinned ref rather than off disk, which also
fixes a subtler bug: the reviewer is shown before/after content from the base
and head refs, but the old tools read the live working tree. A finder could
confirm a claim against code that was not the code under review.

Still not a sandbox. `--no-verify` disables it; reviewing genuinely untrusted
code warrants a container regardless.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

TIMEOUT_SECONDS = 20
MAX_OUTPUT_CHARS = 6000
MAX_LOG_ENTRIES = 50

# Refs may contain letters, digits and the punctuation git uses for revision
# syntax. A leading dash is rejected separately so a ref can never be read as an
# option, and ".." is rejected so a ref cannot smuggle a parent-directory path.
_REF_RE = re.compile(r"\A[A-Za-z0-9._/~^{}@-]{1,200}\Z")


class ToolError(ValueError):
    """A tool call whose parameters are not acceptable."""


TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Read a file as it exists at a git ref. Use this to see code the diff "
            "does not show. Returns the file with line numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo-relative path."},
                "ref": {"type": "string", "description": "Git ref; defaults to the head under review."},
                "why": {"type": "string", "description": "What claim this checks."},
            },
            "required": ["path", "why"],
        },
    },
    {
        "name": "search",
        "description": (
            "Search the repository at a git ref for a literal pattern (fixed string, "
            "not a regex). Use this to find a symbol's other uses or confirm something "
            "does not exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Literal text to find."},
                "path": {"type": "string", "description": "Optional path to restrict the search to."},
                "ref": {"type": "string", "description": "Git ref; defaults to the head under review."},
                "why": {"type": "string", "description": "What claim this checks."},
            },
            "required": ["pattern", "why"],
        },
    },
    {
        "name": "git_diff",
        "description": (
            "Show the diff between two refs, optionally for one path. Use this to see "
            "what git actually produces rather than inferring it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "base": {"type": "string"},
                "head": {"type": "string"},
                "path": {"type": "string", "description": "Optional path to restrict the diff to."},
                "merge_base": {
                    "type": "boolean",
                    "description": (
                        "True (default) diffs from the merge-base of base and head — what "
                        "changed on head since it diverged, which is what branch review "
                        "means. False diffs the two refs directly, which is what you want "
                        "to ask 'what does this exact commit change'."
                    ),
                },
                "why": {"type": "string", "description": "What claim this checks."},
            },
            "required": ["base", "head", "why"],
        },
    },
    {
        "name": "git_log",
        "description": "Recent commits, optionally for one path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer", "description": f"1-{MAX_LOG_ENTRIES}."},
                "why": {"type": "string", "description": "What claim this checks."},
            },
            "required": ["why"],
        },
    },
]

TOOL_NAMES = frozenset(t["name"] for t in TOOLS)


def dispatch(repo: Path, name: str, params: dict, default_ref: str) -> str:
    """Run one tool call. Returns output, or a REFUSED/ERROR line."""
    try:
        if name == "read_file":
            return _read_file(repo, _path(params.get("path")),
                              _ref(params.get("ref") or default_ref))
        if name == "search":
            return _search(repo, str(params.get("pattern", "")),
                           _opt_path(params.get("path")),
                           _ref(params.get("ref") or default_ref))
        if name == "git_diff":
            sep = ".." if params.get("merge_base") is False else "..."
            return _git(repo, "diff", _ref(params.get("base")) + sep + _ref(params.get("head")),
                        *(["--", _path(params["path"])] if params.get("path") else []))
        if name == "git_log":
            n = max(1, min(int(params.get("limit") or 20), MAX_LOG_ENTRIES))
            return _git(repo, "log", "--oneline", f"-{n}",
                        *(["--", _path(params["path"])] if params.get("path") else []))
    except ToolError as e:
        return f"REFUSED: {e}"
    except (ValueError, TypeError) as e:
        return f"REFUSED: bad parameters ({e})"
    # Distinguish "you invented a tool" from "we declared one and forgot to wire
    # it up". The second is our bug and would otherwise be reported to the model
    # as though the tool never existed, which is misleading and silent.
    if name in TOOL_NAMES:
        raise NotImplementedError(f"{name} is declared in TOOLS but has no dispatch branch")
    return f"REFUSED: no tool named {name!r}"


# ---------- parameter validation ----------

def _ref(value: object) -> str:
    ref = str(value or "").strip()
    if not ref:
        raise ToolError("empty ref")
    if ref.startswith("-"):
        raise ToolError(f"ref {ref!r} may not start with '-'")
    if ".." in ref or not _REF_RE.match(ref):
        raise ToolError(f"ref {ref!r} is not a plain revision")
    return ref


def _path(value: object) -> str:
    path = str(value or "").strip()
    if not path:
        raise ToolError("empty path")
    if path.startswith("-"):
        raise ToolError(f"path {path!r} may not start with '-'")
    if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
        raise ToolError(f"path {path!r} must be repo-relative and may not contain '..'")
    return path


def _opt_path(value: object) -> str | None:
    return _path(value) if value else None


# ---------- fixed-shape commands ----------

def _git(repo: Path, *args: str) -> str:
    """Run git with an argument vector this module built. Never model-supplied argv.

    Only the validated parameter values reach this, always in positions where a
    leading dash has already been rejected, so no argument can turn into a flag.
    """
    try:
        proc = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True,
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


def _read_file(repo: Path, path: str, ref: str) -> str:
    body = _git(repo, "show", f"{ref}:{path}")
    if body.startswith("REFUSED:"):
        return body
    lines = body.splitlines()
    return "\n".join(f"{i:5}  {line}" for i, line in enumerate(lines, 1))


def _search(repo: Path, pattern: str, path: str | None, ref: str) -> str:
    if not pattern:
        raise ToolError("empty pattern")
    # -F fixed-string and -e both matter: -e keeps a pattern beginning with '-'
    # from being read as an option, and -F stops it being a regex.
    args = ["grep", "-n", "-F", "-e", pattern, ref]
    if path:
        args += ["--", path]
    return _git(repo, *args)
