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

from .client import require_python
from .findings import merge, severity_rank
from .lang import DEFAULT_EXTS
from .reviewer import review
from .second_pass import second_pass
from .triage import classify, vote
from .vcs import GitError, change_units, resolve_repo


def run_unit(unit: dict, *, skip_triage: bool = False) -> dict:
    """Full pipeline for one file. Returns the unit with results attached."""
    first = review(unit)
    second = second_pass(unit, first)
    merged = merge(first, second)

    if skip_triage or not merged:
        tiers = [(f, "advisory") for f in merged]
    else:
        rv = vote(unit, merged, "reviewer")
        av = vote(unit, merged, "arbiter")
        tiers = classify(merged, rv, av)

    return {
        "path": unit["path"],
        "status": unit["status"],
        "counts": {"first_pass": len(first), "second_pass": len(second), "merged": len(merged)},
        "blocking": [f for f, c in tiers if c == "blocking"],
        "advisory": [f for f, c in tiers if c == "advisory"],
        "dropped": [f for f, c in tiers if c == "dropped"],
    }


def render(results: list[dict], base: str, head: str) -> str:
    blocking = [(r["path"], f) for r in results for f in r["blocking"]]
    advisory = [(r["path"], f) for r in results for f in r["advisory"]]
    dropped = sum(len(r["dropped"]) for r in results)

    out = [
        f"# arbiter — `{head}` vs `{base}`",
        "",
        f"{len(results)} file(s) reviewed · "
        f"**{len(blocking)} blocking** · {len(advisory)} advisory · {dropped} dropped by triage",
        "",
    ]

    for title, items, empty in (
        ("Blocking", blocking, "Nothing blocking. Both triage voices agreed to keep zero findings."),
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

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(lambda u: run_unit(u, skip_triage=args.no_triage), units))

    for r in results:
        c = r["counts"]
        print(
            f"  {r['path']}: {c['first_pass']}+{c['second_pass']} → {c['merged']} merged → "
            f"{len(r['blocking'])} blocking, {len(r['advisory'])} advisory",
            file=sys.stderr,
        )

    body = json.dumps(results, indent=2) if args.json else render(results, args.base, args.head)

    if args.out:
        Path(args.out).write_text(body)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(body)

    # Exit 1 when something blocking was found, so this can gate a hook.
    return 1 if any(r["blocking"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
