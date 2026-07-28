"""File-extension → markdown fence label.

Ported from pr-arbiter's `agents/__init__.py`. Drives only syntax-highlight
hinting in the prompts; every agent's system prompt is language-agnostic, so an
unknown extension (empty label) still reviews fine.
"""

from __future__ import annotations

_EXT_FENCE = {
    "py": "python", "js": "javascript", "jsx": "javascript",
    "ts": "typescript", "tsx": "typescript", "java": "java",
    "go": "go", "rs": "rust", "rb": "ruby", "php": "php",
    "c": "c", "h": "c", "cpp": "cpp", "cc": "cpp", "hpp": "cpp",
    "cs": "csharp", "kt": "kotlin", "swift": "swift", "scala": "scala",
    "sh": "bash", "bash": "bash", "zsh": "bash",
    "sql": "sql", "html": "html", "css": "css",
    "yaml": "yaml", "yml": "yaml", "json": "json", "toml": "toml",
}

# What gets reviewed by default. Deliberately narrower than _EXT_FENCE: these
# are the languages with a real review surface in the repos this runs against.
# Config and markup are reviewable on request (--ext) but not by default —
# they generate noise disproportionate to the bugs they hide.
DEFAULT_EXTS = frozenset({"py", "sh", "bash", "zsh", "ts", "tsx", "js", "jsx", "sql"})


def lang_fence(path: str) -> str:
    """Fence label for a file path. '' (plain fence) if extension unknown."""
    return _EXT_FENCE.get(_ext(path), "")


def _ext(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def is_reviewable(path: str, exts: frozenset[str] | set[str] = DEFAULT_EXTS) -> bool:
    """True if this path's extension is in the review set.

    Extensionless files are skipped. Shell scripts without a `.sh` suffix are
    common (git hooks, `scripts/gate`), so callers that care should pass an
    explicit path list rather than relying on extension sniffing.
    """
    return _ext(path) in exts
