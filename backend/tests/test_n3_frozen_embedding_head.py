"""N3's headline numbers are pinned to N3's receipt, and its PIT claim is tested.

Same rule as `test_x9_day_run_numbers.py`: **the receipt wins.** Every number
quoted anywhere about N3 has to be a number the run actually wrote, so a re-run
that moves the result goes red here rather than quietly disagreeing with the
prose beside it. A receipt that is absent SKIPS (receipts are large and are not
on every checkout); a receipt that is present and inconsistent FAILS.

Two families of test, and the second is the one that matters most:

* **arithmetic** -- the headline string, the per-era table and the cost line all
  have to agree with each other inside the receipt. A net number that is not
  `gross - realised turnover x COST_BPS` is the C2 defect (a flat per-date
  charge) and fails here.
* **PIT** -- no label may be drawn from a session at or before publication. This
  is tested against the PANEL ITSELF, not against the receipt's assertion that
  it holds, because a run can only report the check it ran.

The N3 script also refuses to use the panel's `dollar_vol` column, which is the
ENTRY session's own close x volume and therefore a look-ahead. That refusal is
tested functionally: `_price_features` must produce a liquidity number that is
unchanged when the entry session's own bar is deleted.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
NIGHT = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-10"
RECEIPT = NIGHT / "N3_frozen_embedding_head_run01.json"
PANEL = REPO / "backend" / "data" / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet"
BARS = REPO / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"

ARMS = ("EMBED", "TFIDF", "SHUFFLE", "NOTEXT")
CONTROLS = ("TFIDF", "SHUFFLE", "NOTEXT")


def _receipt() -> dict:
    if not RECEIPT.is_file():
        pytest.skip(f"receipt absent on this machine: {RECEIPT}")
    r = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if r.get("status") != "done":
        pytest.skip(f"receipt is {r.get('status')!r}, not a finished run")
    return r


# ---------------------------------------------------------------------------
# the receipt has to be the shape a PRODUCT_EXPERIMENT receipt is
# ---------------------------------------------------------------------------
def test_receipt_carries_the_standard_fields():
    r = _receipt()
    for k in ("job", "licence", "headline", "verdict", "llm_spend_usd",
              "family_max_p", "written_utc", "elapsed_s", "results", "encoder", "panel"):
        assert k in r, f"receipt is missing {k}"
    assert r["job"] == "N3_frozen_embedding_head"
    assert r["licence"] == "PRODUCT_EXPERIMENT"
    assert r["llm_spend_usd"] == 0.0, "N3 is local; a non-zero LLM spend means something else ran"
    assert r["smoke"] is False, "run01 must not be the smoke run"


def test_the_encoder_is_pinned_frozen_and_free():
    """A model id without a revision is not a pinned model."""
    e = _receipt()["encoder"]
    assert e["model_id"] == "BAAI/bge-small-en-v1.5"
    assert len(e["revision"]) == 40 and all(c in "0123456789abcdef" for c in e["revision"]), \
        "the revision must be a full commit sha, not 'main'"
    assert e["dim"] == 384
    assert e["cost_usd"] == 0.0
    assert e["rows_embedded"] == _receipt()["panel"]["unique_texts"], \
        "every distinct text in the corpus must have been embedded exactly once"


def test_headline_quotes_the_numbers_the_run_produced():
    """Each number in the headline string is a number in `results`."""
    r = _receipt()
    a = r["results"]["eras"]["ALL"]
    head = r["headline"]
    for probe in (f"{a['arms']['EMBED']['ic']['mean']:+.4f}",
                  f"{a['arms']['TFIDF']['ic']['mean']:+.4f}",
                  f"{a['vs_controls']['EMBED_minus_TFIDF']['ic']['mean']:+.4f}",
                  f"{a['vs_controls']['EMBED_minus_SHUFFLE']['ic']['mean']:+.4f}",
                  str(a["vs_controls"]["EMBED_minus_TFIDF"]["ic"]["t"]),
                  str(a["vs_controls"]["EMBED_minus_TFIDF"]["ic"]["n_date_blocks"])):
        assert probe in head, f"{probe} is in the results but not in the headline"


def test_the_verdict_is_the_one_the_numbers_support():
    """A verdict is a decision rule applied to numbers, not a mood."""
    r = _receipt()
    a = r["results"]["eras"]["ALL"]
    d = a["vs_controls"]["EMBED_minus_TFIDF"]["ic"]
    s = a["vs_controls"]["EMBED_minus_SHUFFLE"]["ic"]
    beats_tfidf = (d["t"] or 0) > 2.0 and (d["mean"] or 0) > 0
    beats_shuffle = (s["t"] or 0) > 2.0 and (s["mean"] or 0) > 0
    v = r["verdict"]
    if not beats_shuffle:
        assert v.startswith("FAILED_VARIANT") and "SHUFFLED-TEXT" in v
    elif not beats_tfidf:
        assert v.startswith("FAILED_VARIANT") and "TF-IDF" in v
    else:
        assert v.startswith("PRODUCT_PROMISING")


# ---------------------------------------------------------------------------
# the controls, and the cost line
# ---------------------------------------------------------------------------
def test_every_arm_and_every_control_is_graded_in_every_era():
    """A control reported only pooled is a control the reader cannot check per era."""
    r = _receipt()
    eras = r["results"]["eras"]
    assert len(eras) >= 3, "one era is not an era table"
    for era, cell in eras.items():
        for arm in ARMS:
            assert arm in cell["arms"], f"{arm} missing in {era}"
            for k in ("ic", "gross", "net"):
                assert k in cell["arms"][arm], f"{arm}.{k} missing in {era}"
        for c in CONTROLS:
            assert f"EMBED_minus_{c}" in cell["vs_controls"], f"EMBED_minus_{c} missing in {era}"


def test_net_is_gross_minus_realised_turnover_not_a_flat_charge():
    """`net = gross - sum|dw| x COST_BPS`. A flat per-date charge is the C2 defect."""
    from scripts.night_g3_evolve_v2 import COST_BPS

    r = _receipt()
    assert r["design"]["cost_bps_per_side"] == COST_BPS
    for era, cell in r["results"]["eras"].items():
        for arm in ARMS:
            a = cell["arms"][arm]
            assert a["cost_bps_per_unit_turnover"] == COST_BPS
            expected = a["gross"]["ann_pct"] - a["mean_daily_turnover"] * COST_BPS / 1e4 * 252 * 100
            assert abs(a["net"]["ann_pct"] - expected) < 0.05, (
                f"{era}/{arm}: net {a['net']['ann_pct']} is not gross {a['gross']['ann_pct']} "
                f"minus turnover {a['mean_daily_turnover']} x {COST_BPS} bps (~{expected:.2f})")
            assert a["mean_daily_turnover"] > 0, f"{era}/{arm}: a book with zero turnover is not a book"


def test_the_shuffled_control_actually_shuffled():
    r = _receipt()
    sh = r["shuffle_control"]
    assert sh["fixed_points"] < 0.001 * r["panel"]["cells"], \
        "a permutation that leaves most cells in place is not a control"


def test_splits_are_temporal_and_purged():
    """Every fold trains strictly before its test month, with the embargo applied."""
    r = _receipt()
    folds = r["folds"]
    assert len(folds) >= 6, "too few walk-forward folds to say anything per era"
    prev_train = 0
    for f in folds:
        cut = pd.Timestamp(f["train_cut_session"])
        month_start = pd.Period(f["test_month"], freq="M").start_time
        assert cut < month_start, f"{f['test_month']}: train cut {cut} is not before the test month"
        assert f["n_train"] >= prev_train, "the walk-forward window must expand, never shrink"
        prev_train = f["n_train"]
        assert f["n_test"] > 0


# ---------------------------------------------------------------------------
# PIT -- tested against the panel, not against the receipt's claim about it
# ---------------------------------------------------------------------------
def test_no_label_is_drawn_from_a_session_at_or_before_publication():
    """The whole panel: the entry session's OPEN must be strictly after publication.

    `x_oc` is that session's open-to-close. If publication were at or after the
    open, the label would cover a window the news was already inside.
    """
    if not PANEL.is_file():
        pytest.skip(f"panel absent on this machine: {PANEL}")
    df = pd.read_parquet(PANEL, columns=["published_utc", "entry_date"])
    pub = pd.to_datetime(df["published_utc"], utc=True, errors="coerce")
    entry_open = (pd.to_datetime(df["entry_date"]).dt.tz_localize("America/New_York")
                  + pd.Timedelta(hours=9, minutes=30)).dt.tz_convert("UTC")
    known = pub.notna()
    assert known.mean() > 0.99, "most rows must carry a publication timestamp for this to mean anything"
    violations = int((known & (pub >= entry_open)).sum())
    assert violations == 0, f"{violations} rows have an entry open at or before publication"


def test_pit_liquidity_never_reads_the_entry_session_bar():
    """`pit_dv_21` must be unchanged when the entry session's own bar is deleted.

    This is the functional form of the reason N3 ignores the panel's own
    `dollar_vol` column: that column IS the entry session's close x volume.
    """
    if not BARS.is_file():
        pytest.skip(f"bars absent on this machine: {BARS}")
    from scripts import night_n3_frozen_embedding_head as N3

    b = pd.read_parquet(BARS, columns=["symbol", "date", "close", "volume"])
    sym = "AAPL" if "AAPL" in set(b["symbol"]) else sorted(b["symbol"].unique())[0]
    full = N3._price_features({sym}).dropna(subset=["pit_dv_21"]).reset_index(drop=True)
    assert len(full) > 60, "not enough sessions to test the lag"
    probe = full.iloc[len(full) // 2]

    g = b[b["symbol"] == sym].copy()
    g["date"] = pd.to_datetime(g["date"]).dt.normalize()
    g = g.sort_values("date").reset_index(drop=True)
    i = int(g.index[g["date"] == probe["entry_date"]][0])
    dv = (g["close"] * g["volume"]).to_numpy()
    manual = float(np.median(dv[max(0, i - 21):i]))          # t-21 .. t-1, never t
    assert abs(float(probe["pit_dv_21"]) - manual) < max(1.0, 1e-6 * manual), (
        f"pit_dv_21 {probe['pit_dv_21']} != median of the 21 sessions ending at t-1 ({manual})")
    assert float(probe["pit_dv_21"]) != dv[i], "the liquidity number is the entry session's own bar"


def test_the_hand_rolled_ridge_is_the_library_ridge():
    """N3 solves the whole alpha path from one eigendecomposition, for speed.

    A hand-rolled solver that silently disagrees with `sklearn` would change
    every number in the receipt while looking like an optimisation, so it is
    pinned to the library estimator here.
    """
    from sklearn.linear_model import Ridge

    from scripts.night_n3_frozen_embedding_head import ALPHAS, _RidgePath

    rng = np.random.default_rng(0)
    for n, d in ((400, 25), (2000, 120)):
        X = rng.normal(size=(n, d))
        y = X @ rng.normal(size=d) + rng.normal(size=n) * 3.0 + 7.0
        path = _RidgePath(X, y)
        Xt = rng.normal(size=(150, d))
        for a in ALPHAS:
            ref = Ridge(alpha=a, fit_intercept=True).fit(X, y).predict(Xt)
            assert np.max(np.abs(ref - path.predict(Xt, a))) < 1e-7, (n, d, a)


def test_the_panel_dollar_vol_column_is_declared_unusable():
    """The receipt has to SAY the column was ignored, so the next reader knows why."""
    r = _receipt()
    note = r["panel"]["dollar_vol_column_of_panel"]
    assert "IGNORED" in note and "not PIT" in note
    assert "dollar volume" in r["design"]["arms"]["NOTEXT"] or "dollar_vol" not in r["design"]["arms"]["NOTEXT"]
