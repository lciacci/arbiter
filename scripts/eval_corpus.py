#!/usr/bin/env python3
"""Score arbiter against pr-arbiter's labelled corpus — recall AND precision.

Why this exists: on 2026-08-07 a triage prompt change was scored against a diff
with 7 labelled true positives and no labelled false positives. It looked like a
recall win. It was actually promoting a confidently-wrong finding to *blocking*
in two runs of three, and that was caught by hand, not by the test. **A corpus
that can only measure recall will approve any change that trades precision for
it.** Full account in `docs/STATE.md` -> "REFUTED, same day".

This corpus can measure both: 20 PRs, 55 expected findings, and — the part that
matters here — **three negative controls with zero expected findings**, where
every reported finding is unambiguously a false positive.

    python3 scripts/eval_corpus.py --limit 5              # iterate
    python3 scripts/eval_corpus.py                        # full run, 20 PRs
    python3 scripts/eval_corpus.py --only pr_002 pr_007 pr_018   # precision only

Measured on three PRs: **$0.08 to $0.35 each**, so the full corpus is a few
dollars, not the ~$12 first guessed by extrapolating from arbiter's own diff.
Corpus PRs are one file; that diff was four, two of them large. Every run prints
its own total — trust that over this paragraph.

Scores the **blocking tier separately**, because that is the product. A change
that lifts advisory recall while adding a blocking false positive is a
regression, and reporting a single blended number would hide exactly that.

The matcher is pr-arbiter's own `_approximate_match`, reused verbatim (same
file, same category, line midpoint within +/-3) so numbers stay comparable with
its committed results — which conclave independently reproduced to 4dp. Do not
"improve" it without re-baselining; a matcher change silently rewrites history.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Vendored, not referenced — pr-arbiter is frozen, so a snapshot cannot drift
# from its origin, and the harness cannot go dark if that repo moves. Excludes
# its `_source/` (unmodified Flask, never read here). See corpus/PROVENANCE.md.
CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# The reviewed path inside the throwaway repo. Rubric line numbers and `file`
# fields are written against `after.py`, so the file has to carry that name for
# the matcher to line up.
REVIEWED = "after.py"


def approximate_match(agent: dict, expected: dict, line_tolerance: int = 3) -> bool:
    """pr-arbiter's matcher, verbatim. Same file, same category, mid-line +/-3."""
    if agent.get("file") != expected.get("file"):
        return False
    if agent.get("category") != expected.get("category"):
        return False
    a = agent.get("line_range", [0, 0])
    e = expected.get("line_range", [0, 0])
    return abs((a[0] + a[1]) / 2 - (e[0] + e[1]) / 2) <= line_tolerance


def score(expected: list[dict], agent: list[dict]) -> tuple[int, int, list[str]]:
    """(matched, false_positives, missed_ids). One expected finding consumes at
    most one agent finding, so two reports of the same bug cost a false
    positive — which is the honest accounting for a list a human has to read."""
    used: set[int] = set()
    matched, missed = 0, []
    for e in expected:
        hit = next(
            (i for i, a in enumerate(agent) if i not in used and approximate_match(a, e)),
            None,
        )
        if hit is None:
            missed.append(e["id"])
        else:
            used.add(hit)
            matched += 1
    return matched, len(agent) - len(used), missed


def build_repo(pr: Path, workdir: Path) -> Path:
    """A two-commit repo: before.py, then after.py, both at `after.py`.

    Real git rather than a hand-built change unit, deliberately — the finders'
    verification tools read through git at a pinned ref, so bypassing the CLI
    would score a different tool than the one that ships.
    """
    repo = workdir / pr.name
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q", ".")
    git("config", "user.email", "eval@local")
    git("config", "user.name", "eval")
    (repo / REVIEWED).write_text((pr / "before.py").read_text())
    git("add", "-A")
    git("commit", "-qm", "before")
    (repo / REVIEWED).write_text((pr / "after.py").read_text())
    git("add", "-A")
    git("commit", "-qm", "after")
    return repo


def run_arbiter(repo: Path, extra: list[str]) -> dict:
    proc = subprocess.run(
        ["uv", "run", "arbiter", "--repo", str(repo), "--base", "HEAD~1", "--json", *extra],
        capture_output=True,
        text=True,
        check=False,   # exit 1 means blocking findings, which is a result, not an error
        cwd=Path(__file__).resolve().parent.parent,
    )
    # Exit 1 means blocking findings, which is a normal outcome here, not a
    # failure. Only an unparseable stdout is a real failure — and it must be
    # loud, because an empty finding list scores as perfect precision.
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise SystemExit(
            f"arbiter produced no JSON for {repo.name} (exit {proc.returncode}).\n"
            f"stderr tail:\n{proc.stderr[-1500:]}"
        ) from None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--limit", type=int, help="score only the first N PRs")
    p.add_argument("--only", nargs="+", metavar="PR_ID", help="score these PR ids")
    p.add_argument("--corpus", default=str(CORPUS), help=f"corpus dir (default: {CORPUS})")
    p.add_argument("--arbiter-arg", action="append", default=[], metavar="ARG",
                   help="pass through to arbiter, repeatable (e.g. --arbiter-arg --no-verify)")
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"error: corpus not found at {corpus}", file=sys.stderr)
        return 2

    prs = sorted(d for d in corpus.glob("pr_*") if (d / "rubric.json").exists())
    if args.only:
        wanted = set(args.only)
        prs = [d for d in prs if d.name in wanted]
    if args.limit:
        prs = prs[: args.limit]
    if not prs:
        print("error: no PRs selected", file=sys.stderr)
        return 2

    tiers = ("blocking", "advisory")
    totals = {t: {"expected": 0, "matched": 0, "fp": 0} for t in tiers}
    usd = 0.0

    print(f"{'PR':9} {'category':28} {'exp':>4} {'blk':>9} {'blk+adv':>9} {'$':>6}")
    print("-" * 72)

    with tempfile.TemporaryDirectory() as tmp:
        for pr in prs:
            rubric = json.loads((pr / "rubric.json").read_text())
            expected = rubric["expected_findings"]
            data = run_arbiter(build_repo(pr, Path(tmp)), args.arbiter_arg)
            usd += data.get("usage", {}).get("usd", 0.0)

            found = {t: [f for r in data["results"] for f in r.get(t, [])] for t in tiers}
            # Cumulative: the advisory row is "blocking + advisory", i.e. what a
            # reader who scrolls sees. The blocking row alone is what a gate sees.
            cumulative = {
                "blocking": found["blocking"],
                "advisory": found["blocking"] + found["advisory"],
            }
            cells = {}
            for t in tiers:
                m, fp, _ = score(expected, cumulative[t])
                totals[t]["expected"] += len(expected)
                totals[t]["matched"] += m
                totals[t]["fp"] += fp
                cells[t] = f"{m}/{len(expected)}+{fp}fp"

            print(f"{pr.name:9} {rubric['category']:28} {len(expected):>4} "
                  f"{cells['blocking']:>9} {cells['advisory']:>9} "
                  f"{data.get('usage', {}).get('usd', 0):>6.2f}")

    print("-" * 72)
    for t in tiers:
        d = totals[t]
        recall = d["matched"] / d["expected"] if d["expected"] else 0.0
        label = "blocking only" if t == "blocking" else "blocking+advisory"
        print(f"{label:20} recall {d['matched']:>3}/{d['expected']:<3} = {recall:.3f}   "
              f"false positives {d['fp']}")
    print(f"{'':20} ${usd:.2f} over {len(prs)} PR(s)")
    print("\nBoth rows matter. A change that lifts the second while raising "
          "blocking false positives is a regression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
