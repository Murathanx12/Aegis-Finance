"""The analyst-target ratio must be computed on ONE share basis.

Found 2026-09-04 (Fable 5.1 review, `docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md`
§2): `learner/dataset.py` loads `ibes__ptgsum` — IBES's SPLIT-ADJUSTED
consensus, restated in end-of-sample share terms — and divides `meanptg` by
the RAW CRSP close. AAPL 2013-06-20: adjusted target 19.32, unadjusted
541.04, raw close 398.07, cfacpr 28. The tape said "ratio 0.05"; the truth
is 1.36. Because `ratio_used = true_ratio / cfacpr(t)`, a name that LATER
reverse-splits is labelled `toxic_ge_5` — a future-collapse detector, not an
opinion. Every band-prior receipt inherited it.

This test pins the FACT on the FILE THE BUILDER READS, not a path: it parses
which `ibes__ptgsum*` parquet `learner/dataset.py` opens, reads AAPL's
2013-06-20 row from that file, and asserts the target sits within a
plausible multiple of the raw CRSP close. It is xfail(strict) until B1
switches the loader to the unadjusted file; when it flips to XPASS the
marker must be deleted in the same commit (that is the lifecycle).

Skips when the local WRDS parquet is absent (CI) — a skip is printed, never
a silent pass.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATASET_PY = ROOT / "learner" / "dataset.py"
BULK = ROOT / "backend" / "data" / "optimus" / "wrds" / "bulk"
DSF_2013 = ROOT / "backend" / "data" / "optimus" / "wrds" / "crsp_dsf_2013.parquet"

AAPL_PERMNO = 14593
AAPL_CUSIP8 = "03783310"
STATPERS = "2013-06-20"


def _loader_file() -> Path:
    src = DATASET_PY.read_text(encoding="utf-8")
    m = re.search(r'BULK\s*/\s*"(ibes__ptgsum\w*\.parquet)"', src)
    assert m, "learner/dataset.py no longer names the IBES summary file it reads"
    return BULK / m.group(1)


@pytest.mark.xfail(
    strict=True,
    reason="B1 not yet done: dataset.py reads the split-ADJUSTED ibes__ptgsum; "
           "delete this marker when it reads ibes__ptgsumu (verdicts doc §2)",
)
def test_target_and_price_share_the_same_share_basis():
    pd = pytest.importorskip("pandas")
    f = _loader_file()
    if not f.exists() or not DSF_2013.exists():
        pytest.skip(f"local WRDS parquet absent ({f.name} / {DSF_2013.name})")
    ibes = pd.read_parquet(f, columns=["cusip", "statpers", "meanptg"])
    row = ibes[(ibes["cusip"].astype(str).str[:8] == AAPL_CUSIP8)
               & (ibes["statpers"].astype(str).str.startswith(STATPERS))]
    assert len(row) >= 1, "AAPL 2013-06-20 consensus row missing"
    target = float(row["meanptg"].iloc[0])
    dsf = pd.read_parquet(DSF_2013, columns=["permno", "date", "prc"])
    px = dsf[(dsf["permno"] == AAPL_PERMNO)
             & (dsf["date"].astype(str) >= STATPERS)].sort_values("date")
    assert len(px) >= 1
    close = abs(float(px["prc"].iloc[0]))
    ratio = target / close
    # A consensus target within 0.5x-3x of the same-basis price is an
    # opinion; 0.05 is a share-basis mismatch.
    assert 0.5 < ratio < 3.0, f"AAPL {STATPERS}: target {target} / close {close} = {ratio:.3f}"
