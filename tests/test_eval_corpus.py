"""Checks for the corpus scorer.

No API calls. The matcher and the tallies decide every number this project will
quote about quality from now on, so a silent bug here would not produce a wrong
answer — it would produce a *plausible* one, which is worse. Same reasoning as
the triage ballot in `db50d16`: the instrument needs the same scrutiny as the
thing it measures.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from eval_corpus import approximate_match, score


def e(id="F1", file="after.py", category="correctness", lines=(100, 100)):
    return {"id": id, "file": file, "category": category, "line_range": list(lines)}


def a(file="after.py", category="correctness", lines=(100, 100)):
    return {"file": file, "category": category, "line_range": list(lines)}


# ---------- the matcher, reused verbatim from pr-arbiter ----------

def test_match_is_tolerant_to_three_lines_by_midpoint():
    assert approximate_match(a(lines=(103, 103)), e(lines=(100, 100)))
    assert not approximate_match(a(lines=(104, 104)), e(lines=(100, 100)))
    # Midpoint, not endpoints: a wide range centred on the target still matches.
    assert approximate_match(a(lines=(95, 105)), e(lines=(100, 100)))


def test_match_requires_same_file_and_category():
    assert not approximate_match(a(file="other.py"), e())
    assert not approximate_match(a(category="security"), e())


# ---------- the tallies ----------

def test_each_expected_consumes_at_most_one_finding():
    """Two reports of the same bug cost a false positive.

    That is the honest accounting for a list a human reads: the duplicate is a
    line they have to evaluate and discard. Letting one expected finding absorb
    both would score a noisier reviewer as identical to a clean one.
    """
    matched, fp, missed = score([e()], [a(), a(lines=(101, 101))])
    assert (matched, fp, missed) == (1, 1, [])


def test_unmatched_expected_are_reported_as_missed():
    matched, fp, missed = score([e("F1"), e("F2", lines=(500, 500))], [a()])
    assert matched == 1
    assert missed == ["F2"]
    assert fp == 0


def test_negative_control_scores_every_finding_as_a_false_positive():
    """The three negative controls are the whole reason this corpus was wired
    up — the Round 3 diff had no labelled false positives and so approved a
    change that traded precision for recall."""
    matched, fp, missed = score([], [a(), a(lines=(200, 200))])
    assert (matched, fp, missed) == (0, 2, [])


def test_a_clean_run_on_a_negative_control_is_a_perfect_score():
    assert score([], []) == (0, 0, [])
