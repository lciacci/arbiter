"""Shared Anthropic client and model pin.

pr-arbiter duplicated this block in all eight agent modules. One copy here.

Portability note: the client is constructed bare on purpose. The SDK reads
`ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` from the environment, so pointing
this engine at a gateway (conclave) is an env var, not a code change. Do not
hardcode a base_url.
"""

from __future__ import annotations

import sys
import threading

from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"

# Every agent asks for structured output via a forced tool call; 4096 is enough
# for a long finding list and keeps a runaway response bounded.
MAX_TOKENS = 4096

MIN_PYTHON = (3, 13)

_CLIENT: Anthropic | None = None
_CLIENT_LOCK = threading.Lock()


class AgentError(RuntimeError):
    """A model call did not produce the structured output it was forced to."""


def require_python() -> None:
    """Fail loudly on an unsupported interpreter.

    This exists because of a real bug: Tessera's spend guard used PEP-604
    (`str | None`) syntax, was run under Python 3.9, raised TypeError at
    definition time, exited non-zero, and the calling wrapper read that as
    ALLOW. It failed *open*. A tool whose job is catching that class of bug
    should not be able to have it.
    """
    if sys.version_info < MIN_PYTHON:
        want = ".".join(str(p) for p in MIN_PYTHON)
        have = ".".join(str(p) for p in sys.version_info[:3])
        raise SystemExit(
            f"arbiter requires Python {want}+ (running {have} at {sys.executable}). "
            "Refusing to run rather than fail in a way a caller might read as success."
        )


def client() -> Anthropic:
    global _CLIENT
    # Double-checked under a lock: cli.py runs units on a thread pool, so an
    # unguarded check-and-set races and can build two clients.
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = Anthropic()
    return _CLIENT


def call_tool(system: str, user_msg: str, tool: dict) -> dict:
    """One forced-tool-use call. Returns the tool input dict.

    Raises AgentError if the response carries no matching tool_use block.

    It must raise rather than return {}. The call is made with
    tool_choice={"type": "tool"}, so a missing block means something went
    wrong — a refusal, a truncated response, an API-shape change. Returning
    {} would flow through `.get("findings", [])` into an empty finding list
    and read as "this file is clean". That is the same fail-open shape this
    module's require_python() docstring warns about: an error a caller
    mistakes for a pass.
    """
    resp = client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_msg}],
    )
    stop = getattr(resp, "stop_reason", "unknown")

    # Truncation is the likelier failure than a missing block, and it is worse:
    # the tool_use block IS present, its input is just cut off mid-JSON. That
    # parses to {} or a partial object, yields zero findings, and reads as a
    # clean file. Checked before the block scan so a half-written finding list
    # can never be mistaken for a complete one.
    if stop == "max_tokens":
        raise AgentError(
            f"{tool['name']}: response hit max_tokens ({MAX_TOKENS}), so its "
            "tool input is truncated and any findings it carries are partial. "
            "Refusing to report this as a complete review."
        )

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
            return dict(block.input)
    raise AgentError(
        f"{tool['name']}: no tool_use block in response (stop_reason={stop}). "
        "Refusing to report this as a clean review."
    )
