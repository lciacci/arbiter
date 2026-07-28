"""Git plumbing: turn a ref range into reviewable change units.

A change unit is one file's before/after/diff — the shape every agent expects.
pr-arbiter's dogfood script hardcoded its own repo root and `main..HEAD`; this
takes any repo path and any base ref.

Per-file review is a known ceiling, inherited from pr-arbiter: the agents see
one file at a time and cannot reason across files in the same change.
# ponytail: per-file units. Cross-file context needs a different prompt shape
# and a bigger budget — revisit when a finding is actually missed because of it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .lang import DEFAULT_EXTS, is_reviewable


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def resolve_repo(path: str | Path) -> Path:
    """Absolute path to the repo root containing `path`."""
    p = Path(path).resolve()
    try:
        root = _git(p if p.is_dir() else p.parent, "rev-parse", "--show-toplevel")
    except GitError as e:
        raise GitError(f"{p} is not inside a git repository") from e
    return Path(root.strip())


def changed_files(repo: Path, base: str, head: str = "HEAD") -> list[tuple[str, str]]:
    """[(status, path)] for files changed in head vs base. Status: A/M/D/R…"""
    out = _git(repo, "diff", "--name-status", f"{base}...{head}")
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        # Renames report as "R100\told\tnew" — take the destination path.
        rows.append((parts[0][0], parts[-1]))
    return rows


def _content_at(repo: Path, ref: str, path: str) -> str:
    try:
        return _git(repo, "show", f"{ref}:{path}")
    except GitError:
        return ""


def change_units(
    repo: Path,
    base: str,
    head: str = "HEAD",
    exts: frozenset[str] | set[str] = DEFAULT_EXTS,
) -> list[dict]:
    """Reviewable units for a ref range. Deletions and non-code files skipped."""
    units: list[dict] = []
    for status, path in changed_files(repo, base, head):
        if status == "D" or not is_reviewable(path, exts):
            continue
        after = _content_at(repo, head, path)
        if not after.strip():
            continue
        units.append(
            {
                "path": path,
                "status": status,
                "before": "" if status == "A" else _content_at(repo, base, path),
                "after": after,
                "diff": _git(repo, "diff", f"{base}...{head}", "--", path),
            }
        )
    return units
