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
from fnmatch import fnmatch
from pathlib import Path

from .lang import DEFAULT_EXTS, has_extension, is_reviewable


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
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


def resolve_ref(repo: Path, ref: str) -> str:
    """Pin a ref to the commit it names *now*.

    `HEAD` is a moving target and this tool re-runs git constantly: once per
    file for the before/after/diff, and again for every verification tool call
    a finder makes. A commit landing mid-run therefore reviewed some files
    against one tree and some against another, and let a finder confirm a claim
    against code that was not the code in the diff it was shown. Resolving once
    at startup makes "pinned ref" true of *time* as well as of disk.

    A ref naming a tree rather than a commit (the empty tree, used to review an
    initial commit) has nothing to resolve to. It is already a content hash, so
    it cannot move; return it unchanged. A ref that does not exist at all also
    lands here, and still fails loudly at the first real git call.
    """
    try:
        return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    except GitError:
        return ref


def _range_args(repo: Path, base: str, head: str) -> list[str]:
    """Git args expressing "what changed in head, relative to base".

    Prefers three-dot (merge-base) semantics, which is what branch review wants:
    it excludes commits that landed on base after the branch diverged. Falls
    back to the two-argument form when three-dot is invalid — a root commit has
    no merge base, and a bare tree ref (e.g. the empty tree, for reviewing an
    initial commit) is not a commit at all.
    """
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
        _git(repo, "merge-base", base, head)
    except GitError:
        return [base, head]
    return [f"{base}...{head}"]


def changed_files(
    repo: Path, base: str, head: str = "HEAD", rng: list[str] | None = None
) -> list[tuple[str, str, str]]:
    """[(status, path, old_path)] for files changed in head vs base.

    Status is a single letter (A/M/D/R…). `old_path` is the path the file had
    at `base` — the same as `path` except for renames and copies, where git
    reports "R100\\told\\tnew" and the two differ. Callers need the old path to
    fetch before-state content; using the new path against `base` silently
    returns empty, which makes a renamed file look brand new.

    `rng` lets a caller reuse an already-computed range instead of paying for
    the two git subprocesses in _range_args again.
    """
    # Trailing `--` so every preceding token is read as a revision. Git refuses
    # to guess: a branch that shares its name with a file in the tree is
    # "ambiguous argument 'x': both revision and filename", exit 128, and the
    # whole run dies at exit 2 on a branch that is perfectly valid. Git does not
    # silently take it as a pathspec, so this is a false-failure fix, not a
    # false-pass one.
    out = _git(repo, "diff", "--name-status", *(rng or _range_args(repo, base, head)), "--")
    return parse_name_status(out)


def parse_name_status(out: str) -> list[tuple[str, str, str]]:
    """Parse `git diff --name-status` output into (status, path, old_path)."""
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0][0]
        path = parts[-1]
        old_path = parts[1] if status in ("R", "C") and len(parts) >= 3 else path
        rows.append((status, path, old_path))
    return rows


def _content_at(repo: Path, ref: str, path: str) -> str:
    """Content of `path` at `ref`. Raises GitError if it isn't there.

    This used to swallow every GitError into "". That is what hid the rename
    bug: a file read at the wrong path produced an empty before-state with no
    signal, and the change was reviewed as if freshly written. Callers now only
    call this where the file is known to exist at the ref, so a failure is a
    real error and must surface.
    """
    return _git(repo, "show", f"{ref}:{path}")


def matches_any(path: str, patterns: list[str]) -> bool:
    """True if path is under, or glob-matches, any pattern.

    `src/arbiter` matches everything beneath it; `*.sh` matches by glob. An
    empty pattern list matches everything.
    """
    if not patterns:
        return True
    return any(
        path == p or path.startswith(p.rstrip("/") + "/") or fnmatch(path, p)
        for p in patterns
    )


def _head_text(repo: Path, ref: str, path: str) -> str | None:
    """Head-state content, or None if it cannot be read as text.

    `_git` runs with `text=True`, so a file whose bytes are not valid UTF-8
    raises `UnicodeDecodeError` *inside* `subprocess.run` — before `_git` gets
    to build a `GitError`. An earlier version caught only `GitError`, so a
    committed binary with no extension took down the entire run with a
    traceback: every other file in the same diff went unreviewed too. Found by
    three independent reviews of this function, and reproduced.

    None is the fail-closed direction — the caller drops the file into the
    *reported* skip list rather than into silence, and rather than into a crash.
    """
    try:
        return _content_at(repo, ref, path)
    except (GitError, UnicodeDecodeError):
        return None


def change_units(
    repo: Path,
    base: str,
    head: str = "HEAD",
    exts: frozenset[str] | set[str] = DEFAULT_EXTS,
    paths: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """(reviewable units, every changed path left unreviewed) for a ref range.

    The second element is the point: a file this tool declines to review is a
    ceiling on every clean result it prints, and an unannounced ceiling makes a
    green unfalsifiable. **Every** reason for declining lands in that list —
    outside `--path`, wrong extension, not text, empty at head. Deletions are
    the one exception: there is no after-state to review and their absence
    surprises nobody.

    Scope is decided in this order:

    1. `--path` filters first, and is **authoritative over the extension set**:
       a named path is reviewed whether or not its suffix is in `exts`. It used
       to run *after* the extension filter and so could not rescue anything.
       It is deliberately **not** authoritative over whether the file is code
       at all — see step 3. `--path config` sweeping up `config/.env` and
       shipping it to the model is not what "authoritative" was meant to buy,
       and `--path assets` used to crash outright on a PNG.
    2. A known code extension passes.
    3. An extensionless file passes only if its head-state starts with `#!` —
       under `--path` as much as without it. This is the one gate `--path` does
       not override, because "the user named this directory" is not evidence
       that everything under it is source.

    Content is read at most once per file: the shebang test keeps what it read
    and hands it to the after-state, so a script costs one `git show`, not two.
    """
    rng = _range_args(repo, base, head)
    units: list[dict] = []
    skipped: list[str] = []
    for status, path, old_path in changed_files(repo, base, head, rng):
        if status == "D":
            continue
        if not matches_any(path, paths or []):
            # Reported, not silent. `--path` is the largest ceiling this tool
            # has — scoping a 30-file branch to one file and printing
            # "1 file(s) reviewed · 0 blocking" is the same false green as the
            # extension filter, reached through a different door.
            skipped.append(path)
            continue

        after: str | None = None
        if not (is_reviewable(path, exts) or (paths and has_extension(path))):
            if has_extension(path):
                skipped.append(path)
                continue
            after = _head_text(repo, head, path)
            if after is None or not after.startswith("#!"):
                skipped.append(path)
                continue

        # A (added) and C (copied) both produce a file that did not exist at
        # base, so there is no before-state to read. Only R carries a real
        # before-state at a *different* path.
        is_new = status in ("A", "C")
        before = "" if is_new else _content_at(repo, base, old_path)

        # The pathspec must name both sides of a rename. Git applies rename
        # detection *after* pathspec filtering, so limiting to the destination
        # alone makes it emit "new file" with every line added — a diff that
        # flatly contradicts the before-state above, and one the agents would
        # review as 500 lines of brand-new code.
        pathspec = [old_path, path] if status == "R" and old_path != path else [path]

        if after is None:
            after = _head_text(repo, head, path)
        if after is None or not after.strip():
            skipped.append(path)
            continue
        units.append(
            {
                "path": path,
                "status": status,
                # The ref the after-state came from. Verification reads through
                # git at this ref rather than off disk, so a finder cannot
                # confirm a claim against a working tree that differs from the
                # code under review.
                "ref": head,
                "before": before,
                "after": after,
                "diff": _git(repo, "diff", *rng, "--", *pathspec),
            }
        )
    return units, skipped
