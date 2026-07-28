"""arbiter — a cheap, portable adversarial second opinion on a code change.

Reviewer → independent second pass → mutual triage → blocking/advisory.
The pattern comes from pr-arbiter (github.com/lciacci/pr-arbiter), where it was
measured against a 20-PR corpus; this is that pattern as a tool.
"""

from __future__ import annotations

from .cli import main

__all__ = ["main"]
