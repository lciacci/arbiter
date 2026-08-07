# Corpus provenance

A snapshot of `pr-arbiter`'s labelled review corpus, vendored so that
`scripts/eval_corpus.py` cannot go dark if that repo moves or is archived.

| | |
|---|---|
| Source repo | `github.com/lciacci/pr-arbiter` (MIT) |
| Source commit | `84fd1481cbe2084693ef7be4051b5e47fe8dfb6d` |
| Source path | `corpus/` |
| Copied | 2026-08-07 |
| Contents | 20 PR directories + `manifest.json` — 55 expected findings, 3 negative controls |

**Vendored rather than referenced because pr-arbiter is frozen.** A snapshot of a
live repo drifts from its origin and is usually the wrong call; a snapshot of a
research artifact that will not change cannot. `scripts/eval_corpus.py --corpus`
still points at any other copy.

## What was deliberately left behind

`corpus/_source/` — 180K of **unmodified Flask 3.0.0 source** used to generate
the corpus. The harness never reads it, so copying it would have taken on a
redistribution obligation for zero benefit. If you need it, it is in
pr-arbiter at the commit above.

## Attribution

The `before.py` / `after.py` files in each PR directory are **derivative works of
Flask 3.0.0** (`pallets/flask`, BSD-3-Clause) with defects deliberately
introduced. Flask's copyright notice, retained per that licence:

    Copyright 2010 Pallets

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    1.  Redistributions of source code must retain the above copyright notice,
        this list of conditions and the following disclaimer.

    2.  Redistributions in binary form must reproduce the above copyright
        notice, this list of conditions and the following disclaimer in the
        documentation and/or other materials provided with the distribution.

    3.  Neither the name of the copyright holder nor the names of its
        contributors may be used to endorse or promote products derived from
        this software without specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
    AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
    IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
    ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
    LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
    CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
    ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.

## Open, and the repo owner's call

**This repository has no `LICENSE` file and no `license` field in
`pyproject.toml`.** That predates this snapshot, but vendoring third-party-derived
content into an unlicensed public repo makes it more pressing. pr-arbiter is MIT;
matching it would be the consistent choice. Not done here — it is a repository-level
decision, not a side effect of wiring up an eval harness.
