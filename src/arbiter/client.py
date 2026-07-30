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
from pathlib import Path

from anthropic import Anthropic

from .tools import TOOL_NAMES, TOOLS, dispatch

MODEL = "claude-sonnet-4-6"

# Every agent asks for structured output via a forced tool call; 4096 is enough
# for a long finding list and keeps a runaway response bounded.
MAX_TOKENS = 4096

# Turns of read-only checking a finder may take before it must report.
MAX_VERIFY_TURNS = 4

MIN_PYTHON = (3, 13)

_CLIENT: Anthropic | None = None
_CLIENT_LOCK = threading.Lock()

# Indicative list pricing, USD per million tokens. Not authoritative — it moves,
# and it is wrong for batched traffic. Good enough to answer "is this run cents
# or dollars", which is the question that decides whether the tool is worth
# running on every branch.
PRICE_IN_PER_MTOK = 3.00
PRICE_OUT_PER_MTOK = 15.00

# Cached input is priced off the base input rate: a write costs 1.25x (5-minute
# TTL) and a read 0.1x. Break-even at the 5-minute TTL is two requests.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10

_USAGE = {"calls": 0, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
_USAGE_LOCK = threading.Lock()


def _record(resp) -> None:
    """Accumulate one response's usage.

    All three input counters, not just `input_tokens`. `input_tokens` is the
    **uncached remainder** — the real prompt size is
    input + cache_creation_input_tokens + cache_read_input_tokens. Summing only
    the first would under-report the prompt by exactly the amount caching saves,
    so the reported cost would fall while the reported token total silently went
    wrong. That is the shape of failure this codebase keeps producing: a number
    that moves in the right direction for the wrong reason.
    """
    u = getattr(resp, "usage", None)
    if u is None:
        return
    with _USAGE_LOCK:
        _USAGE["calls"] += 1
        _USAGE["input"] += getattr(u, "input_tokens", 0) or 0
        _USAGE["output"] += getattr(u, "output_tokens", 0) or 0
        _USAGE["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        _USAGE["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0


def usage() -> dict:
    """Tokens, cache hit rate, and estimated dollars for this process so far.

    `prompt` is the whole prompt across every call; `input` remains the uncached
    part of it. `hit_rate` is the fraction served from cache — read it as the
    answer to "did caching engage at all", where a flat zero over repeated calls
    means something is invalidating the prefix, not that caching is off.
    """
    with _USAGE_LOCK:
        snap = dict(_USAGE)
    snap["prompt"] = snap["input"] + snap["cache_write"] + snap["cache_read"]
    snap["hit_rate"] = round(snap["cache_read"] / snap["prompt"], 4) if snap["prompt"] else 0.0
    snap["usd"] = round(
        (
            snap["input"]
            + snap["cache_write"] * CACHE_WRITE_MULTIPLIER
            + snap["cache_read"] * CACHE_READ_MULTIPLIER
        )
        / 1_000_000
        * PRICE_IN_PER_MTOK
        + snap["output"] / 1_000_000 * PRICE_OUT_PER_MTOK,
        4,
    )
    return snap


def reset_usage() -> None:
    with _USAGE_LOCK:
        _USAGE.update(calls=0, input=0, output=0, cache_write=0, cache_read=0)


class AgentError(RuntimeError):
    """A model call did not produce the structured output it was forced to."""


# ---------- prompt caching ----------
#
# Caching is a prefix match, and render order is tools -> system -> messages.
# Two breakpoints per request, well under the cap of four.

_EPHEMERAL = {"type": "ephemeral"}


def _cached_system(system: str) -> list[dict]:
    """The system prompt as one cacheable block, which caches tools with it.

    A breakpoint here covers everything rendered before it, so the inspection
    tools and the agent's report schema ride along. Measured against
    claude-sonnet-4-6 with count_tokens: 2138 tokens for the reviewer with
    verification on, 2006 for the second pass, 1551 and 1419 with --no-verify.
    All clear the model's 1024-token minimum. Every one of those is a module
    constant, so each file in a run and each turn of the verification loop
    reads the same entry.

    Deliberately not used by triage — see the note in triage.py. Its two voices
    measure 1017 and 1024 tokens, i.e. one is below the minimum and the other
    is exactly on it, and a marker that silently caches nothing is worse than
    no marker because it reads as done.
    """
    return [{"type": "text", "text": system, "cache_control": _EPHEMERAL}]


def _move_transcript_breakpoint(messages: list[dict]) -> None:
    """Put the one message breakpoint on the newest turn, so turn N reads 1..N-1.

    This is the larger win, not the fixed prefix. Each turn of the verification
    loop resends the whole conversation, and turn one already carries the diff
    plus the entire before- and after-state. Measured over three files in this
    repo, a five-turn verified review re-sends 76-78% of its input tokens:
    docs/STATE.md is 14,409 tokens on turn one and 79,045 across five turns.

    One marker, moved, rather than one per turn. The cap is four breakpoints per
    request and the system block takes one, so marking every turn would sit
    exactly on the cap at MAX_VERIFY_TURNS=4 and break silently the first time
    anyone raised it. A single moving marker is still read every turn: the
    lookback window is 20 content blocks and a round adds about four.

    Marks the last block of the last message that has one — the assistant turns
    hold SDK objects rather than dicts, and the final nudge is a bare string, so
    those are skipped and the marker stays on the newest tool_result turn.
    """
    target = None
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict):
                block.pop("cache_control", None)
        if content and isinstance(content[-1], dict):
            target = content[-1]
    if target is not None:
        target["cache_control"] = _EPHEMERAL


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


def call_tool_verified(
    system: str,
    user_msg: str,
    tool: dict,
    repo: Path | None,
    max_turns: int = MAX_VERIFY_TURNS,
    ref: str = "HEAD",
) -> dict:
    """Like call_tool, but the model may run read-only commands first.

    Loops: the model either calls run_command (we execute it and hand back the
    output) or calls the report tool (we return its input and stop). Falls back
    to a plain forced call if `repo` is None or the turn budget runs out, so a
    model that never stops exploring still produces a report.

    Turn budget rather than an open loop because each turn costs a full call;
    MAX_VERIFY_TURNS is where checking stops paying for itself.
    """
    if repo is None:
        return call_tool(system, user_msg, tool, cache_prefix=True)

    # A block list, not a bare string, so the transcript breakpoint can land on
    # it: turn one's body is what turn two would otherwise re-send at full price.
    messages: list[dict] = [{"role": "user", "content": [{"type": "text", "text": user_msg}]}]
    for _ in range(max_turns):
        _move_transcript_breakpoint(messages)
        resp = client().messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_cached_system(system),
            tools=[*TOOLS, tool],
            messages=messages,
        )
        _record(resp)
        if resp.stop_reason == "max_tokens":
            # Only fatal on a turn that was meant to produce the report. An
            # exploration turn running long is recoverable: stop exploring and
            # force the report with what has been established, rather than
            # failing the whole file over a truncated intermediate step.
            break

        calls = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        report = next((b for b in calls if b.name == tool["name"]), None)
        if report is not None:
            return dict(report.input)

        if not calls:
            break  # model produced only prose; fall through to the forced call

        # A tool_result is required for EVERY tool_use in the preceding
        # assistant turn. Answering only the run_command blocks would leave a
        # hallucinated tool name unanswered and the next request would be
        # rejected outright, so unknown tools get an explicit refusal instead.
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": (
                        dispatch(repo, b.name, dict(b.input), ref)
                        if b.name in TOOL_NAMES
                        else f"REFUSED: no tool named {b.name!r} is available"
                    ),
                }
                for b in calls
            ],
        })

    # Budget spent or the model stalled. Force the report with what it now knows.
    #
    # Only append the nudge when the transcript does not already end on a user
    # turn. Exhausting the budget leaves the last message as the tool_result
    # user turn, and appending a second user message breaks the API's strict
    # alternation — which failed the fallback in exactly the case it exists for.
    if messages[-1]["role"] != "user":
        messages.append({
            "role": "user",
            "content": (
                "Stop checking and report now, using the "
                f"{tool['name']} tool, based on what you have established."
            ),
        })
    _move_transcript_breakpoint(messages)
    resp = client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_cached_system(system),
        # The transcript may reference the inspection tools, so they stay
        # declared even though tool_choice forces the report. Omitting them
        # leaves tool_use blocks pointing at undeclared tools.
        tools=[*TOOLS, tool],
        # tool_choice does not invalidate the tools+system cache — only tool
        # definitions and the model itself do.
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=messages,
    )
    _record(resp)
    return _extract(resp, tool)


def call_tool(system: str, user_msg: str, tool: dict, *, cache_prefix: bool = False) -> dict:
    """One forced-tool-use call. Returns the tool input dict.

    `cache_prefix` puts a breakpoint on the system block, caching it with the
    tool definitions. It is opt-in rather than the default because it is only
    correct when the prefix actually clears the model's minimum — see
    `_cached_system`, and the measured numbers in triage.py for the caller
    where it does not.

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
        system=_cached_system(system) if cache_prefix else system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_msg}],
    )
    _record(resp)
    return _extract(resp, tool)


def _extract(resp, tool: dict) -> dict:
    """Pull the report tool's input out of a response, or fail loudly.

    Truncation is the likelier failure than a missing block, and it is worse:
    the tool_use block IS present, its input just cut off mid-JSON. That parses
    to {} or a partial object, yields zero findings, and reads as a clean file.
    Checked before the block scan so a half-written finding list can never be
    mistaken for a complete one.
    """
    stop = getattr(resp, "stop_reason", "unknown")
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
