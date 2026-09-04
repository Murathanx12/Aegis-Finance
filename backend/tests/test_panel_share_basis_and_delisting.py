"""The rebuilt panel's three invariants: one share basis, dead names counted,
hygiene inside the table.

WHAT THIS FILE DEFENDS
======================
On 2026-09-04 (`docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md` §2) the panel every
tape receipt was measured on turned out to be built from IBES's SPLIT-ADJUSTED
consensus (`ibes__ptgsum`, restated in end-of-sample share terms) divided by the
RAW CRSP close. `ratio_used = true_ratio / cfacpr(t)`, `cfacpr(t)` is a FUTURE
quantity, and so a name that LATER reverse-split was labelled `toxic_ge_5`:
74.35% of the toxic rows carry a future reverse split against 0.09% of `lt_1_5`.
The label was a future-collapse detector.

Two more provenance defects rode along: `crsp.dsf.ret` is not delisting-
inclusive (of 1,114 events coded 400-591 in 2013-24, 1,103 have a bar on
`dlstdt` and exactly FOUR carry `ret == dlret`), and the hygiene rules that
every consumer of the panel was supposed to apply lived in the callers.

`backend/tests/test_ibes_target_share_basis.py` pins the FILE. This file pins
the RULES around it, offline on synthetic frames, plus a receipt-gated block
that pins the numbers the 2026-09-04 rebuild actually produced.

WHY THE FILL RULE IS TESTED ON A SYNTHETIC FRAME
================================================
`resolve_delisting_return` was split out of `load_delistings` precisely so that
the Shumway branch can be exercised without a 19k-row parquet. A fill that only
ever runs inside a loader is a fill nobody checks -- and only 53 of the 866
performance events need it, so it would never show up in a spot check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from learner import benchmark as BM
from learner import dataset as D
from learner import prior as P
from scripts import tracker_ibes_backtest as tib

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_RECEIPT = ROOT / "backend" / "data" / "optimus" / "learner" / "train_table_schema.json"


# ------------------------------------------------- 1. the file that is read

def test_the_only_ibes_summary_literal_in_the_loaders_is_the_unadjusted_one():
    """Both loaders must NAME `ibes__ptgsumu`, and the adjusted file must be
    reachable only through a named constant.

    The share-basis test parses the loader source for a
    `BULK / "ibes__ptgsum*.parquet"` literal. If the adjusted file were written
    as a second literal, that parser could match the diagnostic read and pass
    while the panel was still built on the wrong basis -- a green line meaning
    the opposite of what it says.
    """
    for src_path in (ROOT / "learner" / "dataset.py",
                     ROOT / "scripts" / "tracker_ibes_backtest.py"):
        src = src_path.read_text(encoding="utf-8")
        lits = re.findall(r'BULK\s*/\s*"(ibes__ptgsum\w*\.parquet)"', src)
        assert lits == ["ibes__ptgsumu.parquet"], (
            f"{src_path.name} names {lits!r}; it must name exactly the UNADJUSTED "
            "file and reach the adjusted one through _ADJUSTED_PTG_FILE")
        assert '_ADJUSTED_PTG_FILE = "ibes__ptgsum.parquet"' in src, (
            f"{src_path.name} lost the named constant for the adjusted file")


def test_the_schema_version_moved_when_the_basis_did():
    """A panel built on a different basis is a different table.

    Not cosmetic: `schema_hash` does not cover the SOURCE FILE, so a consumer
    holding a v1 parquet and a v2 code path would see matching hashes over
    incompatible numbers.
    """
    assert D.SCHEMA_VERSION == "learner-train-table-2"
    assert D.feature_schema()["schema_version"] == D.SCHEMA_VERSION
    note = D.feature_schema()["unit_note"]
    assert "ibes__ptgsumu" in note and "UNADJUSTED" in note


# ---------------------------------------------------------- 2. the hygiene

def test_hygiene_delegates_the_price_and_coverage_floors_to_the_prior():
    """ONE definition of the floor. Not a copy that agrees today."""
    rng = np.random.default_rng(4)
    close = pd.Series(rng.uniform(0.2, 40.0, 500))
    cov = pd.Series(rng.integers(0, 12, 500))
    ratio = pd.Series(rng.uniform(0.1, 4.0, 500))
    got = D.hygiene(ratio, close, cov, pd.Series(False, index=ratio.index))
    expect = P.has_opinion(close, cov)
    pd.testing.assert_series_equal(
        got["has_opinion"].reset_index(drop=True),
        expect.reset_index(drop=True).astype(bool), check_names=False)
    # and the floors are the prior's constants, not local numbers
    assert (got.loc[close < P.MIN_PRICE, "has_opinion"] == False).all()   # noqa: E712
    assert (got.loc[cov < P.MIN_COVERAGE, "has_opinion"] == False).all()  # noqa: E712


def test_a_ratio_at_fifty_times_the_price_is_unreadable_not_bullish():
    """The band prior's job is to say "no opinion", never "1,000,000% upside"."""
    ratio = [1.2, D.RATIO_UNREADABLE_AT - 0.001, D.RATIO_UNREADABLE_AT, 1e6]
    h = D.hygiene(ratio, [10.0] * 4, [5] * 4, [False] * 4)
    assert list(h["target_readable"]) == [True, True, False, False]
    assert list(h["hygiene_ok"]) == [True, True, False, False]


def test_a_target_that_straddles_a_share_basis_change_is_unreadable():
    h = D.hygiene([1.2, 1.2], [10.0, 10.0], [5, 5], [False, True])
    assert list(h["target_readable"]) == [True, False]


def test_a_null_or_nonpositive_ratio_is_never_an_opinion():
    h = D.hygiene([np.nan, 0.0, -1.0, 1.5], [10.0] * 4, [5] * 4, [False] * 4)
    assert list(h["target_readable"]) == [False, False, False, True]


def test_hygiene_failure_does_not_delete_the_row():
    """Deleting a name that failed hygiene is survivorship bias with extra steps.

    The contract is: keep the row, NULL the ratio-derived features, band
    `no_opinion`. This asserts the contract the schema declares, so a future
    edit that starts dropping rows has to change the declaration too.
    """
    schema = D.feature_schema()
    assert schema["hygiene"]["on_failure"].endswith("row kept")
    assert schema["hygiene"]["columns"] == ["has_opinion", "target_readable",
                                            "hygiene_ok"]


# ------------------------------------------------------- 3. the delistings

@pytest.mark.parametrize("code,expect", [
    (100, "active"), (199, "active"),
    (200, "merger_or_exchange"), (300, "merger_or_exchange"),
    (399, "merger_or_exchange"),
    (400, "liquidation"), (450, "liquidation"), (489, "liquidation"),
    (500, "performance"), (520, "performance"), (552, "performance"),
    (584, "performance"),
    (490, "other"), (585, "other"), (591, "other"),
    (None, "unknown"),
])
def test_delisting_categories_are_named_not_one_wide_range(code, expect):
    """The review's stated 400-591 "performance" range is wrong: it swallows
    code 450 (liquidation, 216 events, mean dlret -0.74%) and dilutes the
    performance mean from -24.63% to -19.57%. Categories, not a range.
    """
    assert tib.delist_category(code) == expect


def test_shumway_fills_only_missing_performance_returns_and_by_exchange():
    """The fill rule, on a frame that contains every branch.

    -30% NYSE/AMEX (`hexcd` 1-2), -55% NASDAQ (`hexcd` 3), and NOTHING for a
    merger or a liquidation whose proceeds CRSP did not record: inventing a
    number for those would be a fabrication wearing a citation.
    """
    d = pd.DataFrame({
        "permno": [1, 2, 3, 4, 5, 6, 7],
        "category": ["performance", "performance", "performance", "performance",
                     "merger_or_exchange", "liquidation", "performance"],
        "dlret": [np.nan, np.nan, np.nan, -0.80, np.nan, np.nan, np.nan],
        "hexcd": [1, 2, 3, 3, 3, 1, 9],
    })
    out = tib.resolve_delisting_return(d)
    assert list(out["dlret_source"]) == [
        "shumway_nyse_amex", "shumway_nyse_amex", "shumway_nasdaq",
        "crsp", "none", "none", "none"]
    assert out.loc[0, "dlret_used"] == BM.SHUMWAY_FILL["NYSE_AMEX"] == -0.30
    assert out.loc[2, "dlret_used"] == BM.SHUMWAY_FILL["NASDAQ"] == -0.55
    assert out.loc[3, "dlret_used"] == -0.80          # CRSP's own number wins
    # No fill -> factor 1.0, which is "we did not measure this", and the census
    # counts it. It is NOT a claim that the holder got their money back.
    assert out.loc[4, "dl_factor"] == 1.0
    assert out.loc[6, "dl_factor"] == 1.0             # hexcd 9: no fill, not -0.55
    np.testing.assert_allclose(out["dl_factor"].to_numpy(),
                               [0.70, 0.70, 0.45, 0.20, 1.0, 1.0, 1.0])


def test_a_delisting_return_below_minus_one_cannot_produce_negative_wealth():
    d = pd.DataFrame({"permno": [1], "category": ["performance"],
                      "dlret": [-1.4], "hexcd": [1]})
    out = tib.resolve_delisting_return(d)
    assert out.loc[0, "dl_factor"] == 0.0


def test_the_shumway_constants_come_from_the_benchmark_module():
    """The panel and the benchmark must count a dead name the same way."""
    src = (ROOT / "scripts" / "tracker_ibes_backtest.py").read_text(encoding="utf-8")
    assert "from learner.benchmark import SHUMWAY_FILL" in src
    assert "-0.30" not in src.split("SHUMWAY_FILL")[0][-400:], (
        "a local copy of the Shumway constant appeared beside the import")
    assert BM.SHUMWAY_FILL == {"NYSE_AMEX": -0.30, "NASDAQ": -0.55}


# ------------------------ 4. the delisting return reaches the forward return

def _synthetic_prices(dies: bool) -> pd.DataFrame:
    """Two names, 400 sessions. Name 2 stops trading at session 300 when
    `dies` -- well before the panel edge, so `daily_panel` calls it delisted.
    """
    dates = pd.bdate_range("2015-01-01", periods=400)
    rows = []
    for permno in (1, 2):
        n = 300 if (dies and permno == 2) else 400
        for i, dt in enumerate(dates[:n]):
            rows.append({"permno": permno, "date": dt, "prc": 10.0,
                         "adj_prc": 10.0, "cfacpr": 1.0, "ret": 0.0,
                         "vol": 1e6, "shrout": 1e5, "market_cap": 1e9})
    return pd.DataFrame(rows)


def test_the_delisting_return_is_compounded_into_the_final_index_value():
    """Without this the horizon return of a dead name stops at its last TRADE.

    A flat name that delists at -60% must show a -60% forward return over any
    horizon that outlives it -- not 0%.
    """
    px = _synthetic_prices(dies=True)
    dl = pd.DataFrame({
        "permno": [2], "dlstdt": [px.loc[px.permno == 2, "date"].max()],
        "dlstcd": [574], "category": ["performance"], "dlret": [-0.60],
        "dlret_used": [-0.60], "dlret_source": ["crsp"], "dl_factor": [0.40]})

    with_dl = D.daily_panel(px.copy(), delist=dl)
    without = D.daily_panel(px.copy(), delist=None)

    # The LAST bar of the dead name: its 1m and 12m horizons both outlive it, so
    # both take the fill. (An early bar still has a real forward window inside
    # the name's own life and must NOT be touched -- asserted below.)
    dead = with_dl[(with_dl.permno == 2)].iloc[-1]
    alive_dead = without[(without.permno == 2)].iloc[-1]
    # tri is 1.0 throughout (flat returns), so the forward index value IS the
    # delisting factor.
    assert dead["_tri_fwd_12m"] == pytest.approx(0.40)
    assert dead["_tri_fwd_1m"] == pytest.approx(0.40)
    assert alive_dead["_tri_fwd_12m"] == pytest.approx(1.00), (
        "the None path must be the OLD, generous behaviour -- not a silent fill")
    # A bar whose 1m window closes while the name is still trading keeps the
    # real index value: the wind-up is compounded at the END, not smeared.
    early = with_dl[(with_dl.permno == 2)].iloc[0]
    assert early["_tri_fwd_1m"] == pytest.approx(1.00)
    # a surviving name is untouched either way
    assert with_dl[with_dl.permno == 1].iloc[0]["_tri_fwd_1m"] == pytest.approx(1.0)
    assert with_dl.attrs["delisting_return_applied"]["permnos_applied"] == 1
    assert without.attrs["delisting_return_applied"]["permnos_applied"] == 0
    assert "NOT applied" in without.attrs["delisting_return_applied"]["source"]


def test_a_delisting_record_far_from_the_series_end_is_not_applied():
    """A wind-up dated years before the last bar is a data inconsistency.

    Counting it would mark a live name down by 60%; skipping it silently would
    be the house failure mode. It is skipped AND counted.
    """
    px = _synthetic_prices(dies=True)
    dl = pd.DataFrame({
        "permno": [2], "dlstdt": [pd.Timestamp("2010-01-04")], "dlstcd": [574],
        "category": ["performance"], "dlret": [-0.60], "dlret_used": [-0.60],
        "dlret_source": ["crsp"], "dl_factor": [0.40]})
    dp = D.daily_panel(px.copy(), delist=dl)
    assert dp[dp.permno == 2].iloc[0]["_tri_fwd_12m"] == pytest.approx(1.0)
    a = dp.attrs["delisting_return_applied"]
    assert a["permnos_applied"] == 0
    assert a["permnos_event_out_of_range"] == 1


def test_a_name_that_ran_into_the_panel_edge_is_not_delisted():
    """Truncated is not dead. Its target stays NULL rather than becoming a loss."""
    px = _synthetic_prices(dies=False)
    dl = pd.DataFrame({
        "permno": [2], "dlstdt": [px["date"].max()], "dlstcd": [574],
        "category": ["performance"], "dlret": [-0.60], "dlret_used": [-0.60],
        "dlret_source": ["crsp"], "dl_factor": [0.40]})
    dp = D.daily_panel(px.copy(), delist=dl)
    last = dp[(dp.permno == 2)].iloc[-1]
    assert pd.isna(last["_tri_fwd_12m"]), (
        "a name still trading at the panel edge was treated as delisted")
    assert dp.attrs["delisting_return_applied"]["permnos_applied"] == 0


# ------------------------------------ 5. the numbers the 2026-09-04 rebuild got

_needs_receipt = pytest.mark.skipif(
    not SCHEMA_RECEIPT.exists(),
    reason="train_table_schema.json absent (panel not built on this machine)")


@pytest.fixture(scope="module")
def build_receipt() -> dict:
    return json.loads(SCHEMA_RECEIPT.read_text(encoding="utf-8"))["build"]


@_needs_receipt
def test_the_built_panel_declares_the_pit_share_basis(build_receipt):
    sb = build_receipt["share_basis"]
    assert "ptgsumu" in sb["pit_source"]
    assert sb["adjusted_source"].startswith("ibes__ptgsum.parquet")
    # The cross-check CANNOT agree everywhere -- it multiplies by a future
    # cfacpr. Measured 93.0067% on 441,223 rows; a rate outside this window
    # means the basis or the panel changed and the receipt must be re-read.
    assert 0.90 < sb["agree_rate"] < 0.96, sb["agree_rate"]
    assert sb["agree_rate"] + sb["disagree_rate"] == pytest.approx(1.0, abs=1e-6)
    assert sb["hand_verified_row"]["meanptg_unadjusted"] == 541.04


@_needs_receipt
def test_the_built_panel_merged_the_delisting_returns(build_receipt):
    dl = build_receipt["delistings"]
    perf = dl["by_category"]["performance"]
    assert perf["events"] == 866, "the performance-coded count moved"
    assert perf["mean_dlret"] == pytest.approx(-0.2463, abs=0.0005)
    # 450 is its own category and keeps its own (much milder) mean.
    assert dl["by_category"]["liquidation"]["mean_dlret"] == pytest.approx(
        -0.0074, abs=0.0005)
    assert sum(dl["shumway_filled"].values()) == perf["events"] - perf["with_crsp_dlret"]
    merge = build_receipt["delisting_return_merge"]
    assert merge["permnos_applied"] > 2000
    assert merge["mean_factor_applied"] < 1.0
    assert "dsedelist" in merge["source"]


@_needs_receipt
def test_the_built_panel_recorded_its_universe_coverage(build_receipt):
    """It is a 99.78%-complete SUBSET of the screen, not a "screened superset".

    Zero pulled permnos fall outside `shrcd in (10,11)` / `exchcd in (1,2,3)`,
    and the 15 absent permnos are NAMED. That is why no re-pull was ordered.
    """
    u = build_receipt["universe_coverage"]
    assert u["pulled_outside_the_screen"] == 0, u["verdict"]
    assert u["coverage"] >= D.UNIVERSE_COVERAGE_FLOOR
    assert u["missing_from_the_pull"] == len(u["missing_permnos"])
    assert 11993 in u["missing_permnos"]


@_needs_receipt
def test_the_built_panel_says_the_band_prior_is_void(build_receipt):
    """A void constant that nobody flagged is how the corrupted tape spread.

    `prior_*`/`resid_*` are carried for schema continuity ONLY until B1.5
    re-derives them, and the corrected toxic cell is explicitly not a signal.
    """
    ps = build_receipt["prior_status"]
    assert ps["status"].startswith("VOID")
    assert "not a signal" in ps["corrected_toxic_cell_is_not_a_signal"] \
        or "84.1%" in ps["corrected_toxic_cell_is_not_a_signal"]


@_needs_receipt
def test_the_rebucketing_census_shows_toxic_was_mostly_not_toxic(build_receipt):
    """The headline consequence, as a table rather than a sentence.

    26,199 rows the old tape called `toxic_ge_5`; under the PIT ratio the large
    majority are ordinary or below-1.5 names.
    """
    c = build_receipt["rebucketing_census"]
    old_toxic = c["table"]["toxic_ge_5"]
    assert sum(old_toxic.values()) == c["old_band_counts"]["toxic_ge_5"]
    assert old_toxic["toxic_ge_5"] < 0.20 * sum(old_toxic.values()), (
        "most of the old toxic band must have moved; if it did not, the loader "
        "is reading the adjusted file again")
    assert c["new_band_counts"]["toxic_ge_5"] < c["old_band_counts"]["toxic_ge_5"] / 5


@_needs_receipt
def test_the_built_panel_carries_a_canonical_market_stamp(build_receipt):
    """The panel's own market leg names the one ruler, and validates."""
    stamp = build_receipt["market_benchmark"]
    ok, why = BM.validate_stamp(stamp)
    assert ok, why
    assert stamp["benchmark_id"] == "vw_crsp_common_main"
    assert stamp["provenance"]["dividends_included"] is True


@_needs_receipt
def test_sic_9999_never_reads_as_public_administration(build_receipt):
    """9999 is CRSP's NONCLASSIFIABLE code. It means "we do not know", and a
    label that claims an industry for 22% of the panel neutralises against a
    bucket of unknowns.
    """
    s = build_receipt["sector_labels"]
    assert s["unclassified_label"] == tib.SIC_UNCLASSIFIED == "Unclassified"
    counts = s["counts"]
    assert counts.get("Unclassified", 0) > 10_000
    # Genuine Division J (9100-9729) is a handful of names, not a fifth of the
    # panel. If this ever crosses a few hundred rows the mapping regressed.
    assert counts.get("Public Administration", 0) < 1_000
