"""`arbiter review` — the three-agent pipeline over a git ref range.

Per file: reviewer → independent second pass → merge → two triage voices →
blocking/advisory/dropped. Four model calls per file; triage is what earns the
cost by keeping the blocking tier short enough to read.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from anthropic import AnthropicError

from .client import AgentError, require_python, usage
from .findings import merge, severity_rank
from .lang import DEFAULT_EXTS
from .reviewer import review
from .second_pass import second_pass
from .triage import classify, vote
from .vcs import GitError, change_units, resolve_repo


def run_unit(unit: dict, *, skip_triage: bool = False, repo: Path | None = None) -> dict:
    """Full pipeline for one file. Returns the unit with results attached.

    `repo` enables the finders' read-only verification tool; None disables it.
    """
    first = review(unit, repo)
    second = second_pass(unit, first, repo)
    merged = merge(first, second)

    triage_note = None
    ballot: list[dict] = []
    if skip_triage or not merged:
        tiers = [(f, "advisory") for f in merged]
    else:
        try:
            rv = vote(unit, merged, "reviewer")
            av = vote(unit, merged, "arbiter")
            tiers = classify(merged, rv, av)
            # Retain the ballot. Without it a surprising tier distribution is
            # undiagnosable: two sessions were spent guessing why everything
            # landed advisory, with the deciding evidence computed and dropped
            # on the floor each time.
            ballot = [
                {"finding": f.get("description", "")[:100],
                 "severity": f.get("severity"),
                 "reviewer": r["vote"], "arbiter": a["vote"],
                 "reviewer_why": r.get("rationale", ""),
                 "arbiter_why": a.get("rationale", "")}
                for f, r, a in zip(merged, rv, av)
            ]
        except (AgentError, AnthropicError) as e:
            # Triage failing must not delete findings two completed calls
            # already paid for. Degrade to all-advisory — the same fallback
            # vote() applies to a single malformed ballot — and say so, rather
            # than discarding the unit and re-deriving it at four calls a file.
            tiers = [(f, "advisory") for f in merged]
            triage_note = f"triage failed, all findings held advisory: {e}"

    return {
        "path": unit["path"],
        "status": unit["status"],
        "counts": {"first_pass": len(first), "second_pass": len(second), "merged": len(merged)},
        "blocking": [f for f, c in tiers if c == "blocking"],
        "advisory": [f for f, c in tiers if c == "advisory"],
        "dropped": [f for f, c in tiers if c == "dropped"],
        "triage_note": triage_note,
        "ballot": ballot,
    }


def exit_code(results: list[dict]) -> int:
    """Process exit status for a completed run.

    Strongest signal first:
        1  blocking findings           -> reject
        3  ran, but some file failed   -> incomplete, must not read as a pass
        2  could not run at all        -> emitted by main() on GitError
        0  reviewed clean

    Blocking is checked before failures so a partial failure can never mask a
    confirmed blocking finding behind a softer code. 3 is distinct from 2 so a
    hook can tell "reviewed nine of ten files" from "arbiter never started" —
    those warrant different responses.
    """
    if any(r["blocking"] for r in results):
        return 1
    if any(r.get("error") for r in results):
        return 3
    return 0


def render(results: list[dict], base: str, head: str, spend: dict | None = None) -> str:
    blocking = [(r["path"], f) for r in results for f in r["blocking"]]
    advisory = [(r["path"], f) for r in results for f in r["advisory"]]
    dropped = sum(len(r["dropped"]) for r in results)

    errored = [r for r in results if r.get("error")]
    degraded = [r for r in results if r.get("triage_note")]
    reviewed = len(results) - len(errored)
    out = [
        f"# arbiter — `{head}` vs `{base}`",
        "",
        f"{reviewed} file(s) reviewed · "
        f"**{len(blocking)} blocking** · {len(advisory)} advisory · {dropped} dropped by triage",
        "",
    ]
    if errored:
        out += [f"> **{len(errored)} file(s) failed to review** — not clean, unreviewed:", ""]
        out += [f"> - `{r['path']}`: {r['error']}" for r in errored]
        out += [""]
    if degraded:
        out += [f"> **{len(degraded)} file(s) skipped triage** — findings held advisory, not confirmed:", ""]
        out += [f"> - `{r['path']}`: {r['triage_note']}" for r in degraded]
        out += [""]

    # The empty-state must not claim triage agreed on anything when triage never
    # ran. A report saying "both voices agreed" after every call failed is a
    # false clean-review claim, and this report is meant to be pasted into PRs.
    if reviewed == 0:
        blocking_empty = "**No file was successfully reviewed.** This is not a clean result."
    elif errored or degraded:
        blocking_empty = (
            "Nothing blocking among the files that completed triage — "
            "see the caveats above for the ones that did not."
        )
    else:
        blocking_empty = "Nothing blocking. Both triage voices agreed to keep zero findings."

    for title, items, empty in (
        ("Blocking", blocking, blocking_empty),
        ("Advisory", advisory, "No advisory findings."),
    ):
        out += [f"## {title}", ""]
        if not items:
            out += [f"_{empty}_", ""]
            continue
        for path, f in sorted(items, key=lambda x: severity_rank(x[1])):
            lr = f.get("line_range", [0, 0])
            out += [
                f"### `{path}:{lr[0]}-{lr[1]}` — {f.get('severity', '?')}/{f.get('category', '?')}",
                "",
                f.get("description", ""),
            ]
            if f.get("rationale"):
                out += ["", f"_{f['rationale']}_"]
            out += [""]

    if spend:
        out += [
            "---",
            "",
            f"_{spend['calls']} model calls · {spend['input']:,} in / "
            f"{spend['output']:,} out tokens · ~${spend['usd']:.2f} at list price._",
            "",
        ]

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    require_python()

    p = argparse.ArgumentParser(prog="arbiter", description="Adversarial second-opinion code review.")
    p.add_argument("--base", default="main", help="base ref to diff against (default: main)")
    p.add_argument("--head", default="HEAD", help="head ref (default: HEAD)")
    p.add_argument("--repo", default=".", help="path inside the repo to review (default: cwd)")
    p.add_argument("--ext", action="append", default=None,
                   help=f"extension to review, repeatable (default: {' '.join(sorted(DEFAULT_EXTS))})")
    p.add_argument("--path", action="append", default=None,
                   help="limit review to these paths or globs, repeatable "
                        "(default: everything changed)")
    p.add_argument("--jobs", type=int, default=4, help="files reviewed concurrently (default: 4)")
    p.add_argument("--out", default=None, help="write markdown here instead of stdout")
    p.add_argument("--json", action="store_true", help="emit raw JSON instead of markdown")
    p.add_argument("--no-triage", action="store_true",
                   help="skip the triage voices; everything lands advisory (cheaper, noisier)")
    p.add_argument("--no-verify", action="store_true",
                   help="deny the finders the read-only shell tool (cheaper, and the "
                        "right choice when reviewing code you do not trust)")
    args = p.parse_args(argv)

    load_dotenv(find_dotenv(), override=True)

    try:
        repo = resolve_repo(args.repo)
        exts = frozenset(e.lstrip(".").lower() for e in args.ext) if args.ext else DEFAULT_EXTS
        units = change_units(repo, args.base, args.head, exts, args.path)
    except GitError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not units:
        print(f"No reviewable changes in {args.head} vs {args.base}.", file=sys.stderr)
        return 0

    print(f"Reviewing {len(units)} file(s) in {repo.name} ({args.head} vs {args.base})…", file=sys.stderr)

    def guarded(u: dict) -> dict:
        """Run one unit, converting any failure into a recorded error.

        Catches Exception deliberately. Naming specific types leaks whatever
        wasn't named out of pool.map, which re-raises on iteration and destroys
        every completed result — the opposite of this function's purpose. The
        earlier (AgentError, APIError) pair already missed anthropic's
        RetryableError and WorkloadIdentityError, which subclass AnthropicError
        rather than APIError. A failure here is always recorded and always
        surfaces; nothing is swallowed.
        """
        try:
            return run_unit(u, skip_triage=args.no_triage,
                            repo=None if args.no_verify else repo)
        except Exception as e:  # noqa: BLE001 — see docstring
            return {"path": u["path"], "status": u["status"],
                    "error": f"{type(e).__name__}: {e}",
                    "counts": {}, "blocking": [], "advisory": [], "dropped": [],
                    "triage_note": None}

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(guarded, units))

    for r in results:
        if r.get("error"):
            print(f"  {r['path']}: FAILED — {r['error']}", file=sys.stderr)
            continue
        c = r["counts"]
        print(
            f"  {r['path']}: {c['first_pass']}+{c['second_pass']} → {c['merged']} merged → "
            f"{len(r['blocking'])} blocking, {len(r['advisory'])} advisory",
            file=sys.stderr,
        )

    from collections import Counter
    mix = Counter(
        f"{b['reviewer']}/{b['arbiter']}" for r in results for b in r.get("ballot", [])
    )
    if mix:
        print("\ntriage ballot (reviewer/arbiter): "
              + ", ".join(f"{k}={v}" for k, v in mix.most_common()), file=sys.stderr)

    spend = usage()
    print(
        f"\n{spend['calls']} model calls · "
        f"{spend['input']:,} in / {spend['output']:,} out tokens · "
        f"~${spend['usd']:.2f}",
        file=sys.stderr,
    )

    body = (
        json.dumps({"results": results, "usage": spend}, indent=2)
        if args.json
        else render(results, args.base, args.head, spend)
    )

    if args.out:
        # Explicit encoding: findings are model output and routinely non-ASCII.
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(body)

    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
