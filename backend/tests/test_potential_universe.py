"""The PotentialUniverse properties that must never quietly stop being true.

Born from the starved-seal incident (2026-09-03): `d_catalyst` unreadable on
all 810 candidates, hack4 sealed empty, the exit pass sold. The scorecard
exists so a data gap is VISIBLE at seal time -- so these tests pin exactly
the visibility properties, not model accuracy:

1. every row yields a scorecard; a per-name refusal is a FIELD, never a crash;
2. a refusal NAMES its missing inputs;
3. the toxic band is never admitted, and carries its flip condition;
4. capacity tiers follow the named convention; a missing liquidity column is
   CANNOT_DETERMINE, never zero;
5. disagreement is explicitly encoded against the base rate, never 0.5;
6. the scorecard/header key set is golden -- a consumer (the Capital
   Allocator) can rely on the shape;
7. a row stamped after its own day's close is PIT-refused and not scored;
8. whole-universe refusals (v2, state) are counted in the header;
9. the persisted JSONL round-trips and its header counts match its lines.

Offline, synthetic day rows, dates DERIVED from today (a fixture that
hard-codes a calendar moment fails the day after that moment passes).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pytest

from learner import dataset as D
from learner import potential_universe as PU
from learner import prior as P

# ------------------------------------------------------------------ fixtures

#: A recent weekday, derived from today. Weekday only so the fixture reads
#: like a trading day; nothing here depends on the calendar beyond "not
#: in the future".
def _recent_day() -> str:
    d = date.today() - timedelta(days=7)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


DAY = _recent_day()
PRE_OPEN = f"{DAY}T04:30:00+00:00"          # well before the 20:00 UTC close
POST_CLOSE = f"{DAY}T21:15:00+00:00"        # after it


def _row(symbol: str, *, close=20.0, mean_target=40.0, mdv=50e6,
         rec=None, observed_at=PRE_OPEN, d_cat=15, **extra) -> dict:
    """One synthetic tracker row carrying everything shadow's mapper reads."""
    rec = {"strongBuy": 3, "buy": 2, "hold": 1, "sell": 0, "strongSell": 0} \
        if rec is None else rec
    row = {
        "symbol": symbol, "day": DAY, "observed_at": observed_at,
        "close": close, "mean_target": mean_target,
        "target_high": (mean_target * 1.5 if mean_target else None),
        "target_low": (mean_target * 0.5 if mean_target else None),
        "rec_counts": rec, "n_analysts_yf": 6,
        "ret_12m": 0.10, "high_60d": close * 1.2 if close else None,
        "realised_vol_20d": 0.45, "market_cap_usd": 5e9,
        "median_dollar_volume": mdv, "sessions": 400,
        "tradable": True, "shortable": True,
        "sector": "Tech", "exchange": "NASDAQ",
        "days_to_catalyst": d_cat, "days_to_catalyst_units": "calendar_days",
    }
    row.update(extra)
    return row


class _StubModel:
    """predict_proba keyed off the ratio so tests can steer the learner's
    stance name by name: p = 0.30 where ratio >= 3, else 0.60."""

    def __init__(self, cols):
        self.cols = cols

    def predict_proba(self, X):
        ratio = X[:, self.cols.index("ratio")]
        p = np.where(ratio >= 3.0, 0.30, 0.60)
        return np.column_stack([1 - p, p])


def _champion():
    cols = ["ratio", "consensus", "coverage", "log_close",
            "log_market_cap", "log_dollar_vol_20d"]
    return {"kind": "lgbm_clf", "arm": "engine_feature", "horizon_months": 1,
            "model": _StubModel(cols), "feature_cols": cols,
            "schema_hash": D.schema_hash(shadow_only=True),
            "prior_version": P.PRIOR_VERSION,
            "model_vintage_sha256_16": "testvintage000000",
            "trained_rows": 100, "trained_through_month": "2024-11"}


def _band_map():
    return {lab: float(i) for i, lab in enumerate(P.ALL_BAND_LABELS)}


def _receipt():
    return {"calibration": {"1m": {"lgbm_clf": {"raw_all_rows": {
        "base_rate_realised": 0.4532,
        "mean_predicted_minus_base_rate": 0.02215}}}}}


def _build(rows):
    return PU.build_potential_universe(
        DAY, rows=rows, provenance={"note": "synthetic"},
        champion=_champion(), band_map=_band_map(), v2_receipt=_receipt())


def _card(pu, symbol):
    return next(c for c in pu["scorecards"] if c["symbol"] == symbol)


@pytest.fixture()
def standard_rows():
    return [
        _row("ADMIT", close=20.0, mean_target=40.0),               # ratio 2.0
        _row("TOX", close=10.0, mean_target=60.0),                 # ratio 6.0 toxic
        _row("SUBFLR", close=50.0, mean_target=55.0),              # ratio 1.1
        _row("PENNY", close=1.20, mean_target=3.0),                # hygiene fail
        _row("NOTGT", mean_target=None),                           # unreadable
        _row("THIN", mdv=100_000.0),                               # OBSERVE_ONLY
        _row("NOMDV", mdv=None, d_cat=None),                       # cap CANNOT_DETERMINE
        _row("LATE", observed_at=POST_CLOSE),                      # PIT refused
    ]


# ------------------------------------------------------------------ 1 + 2

def test_every_row_yields_a_scorecard_and_refusals_are_fields(standard_rows):
    pu = _build(standard_rows)
    assert pu["header"]["status"] == "OK"
    assert len(pu["scorecards"]) == len(standard_rows)
    # NOTGT cannot be scored -- but it is a scorecard, not an exception,
    # and its refusals NAME the missing inputs.
    c = _card(pu, "NOTGT")
    assert c["engine_prior"]["verdict"] == "unreadable"
    assert any("missing inputs" in r for r in c["engine_prior"]["reasons"])
    assert c["learner_v1"]["status"] == "REFUSED"
    assert "ratio" in c["learner_v1"]["missing_inputs"]


def test_named_per_name_v1_refusal_lists_exact_core_features(standard_rows):
    pu = _build(standard_rows)
    c = _card(pu, "NOTGT")
    for named in c["learner_v1"]["missing_inputs"]:
        assert named in PU.S.CORE_FEATURES


# ---------------------------------------------------------------------- 3

def test_toxic_band_is_never_admitted_and_carries_its_falsifier(standard_rows):
    pu = _build(standard_rows)
    c = _card(pu, "TOX")
    assert c["engine_prior"]["verdict"] == "toxic_ge_5"
    assert c["engine_prior"]["band"] == "toxic_ge_5"
    flips = [f for f in c["falsifiers"] if f["field"] == "ratio"]
    assert flips and flips[0]["op"] == "<" and flips[0]["value"] == 5.0
    # No scorecard with ratio >= 5 is ever admitted, whatever else is true.
    for card in pu["scorecards"]:
        r = card["engine_prior"]["ratio"]
        if r is not None and r >= 5.0 and card["pit"]["status"] == "OK":
            assert card["engine_prior"]["verdict"] == "toxic_ge_5"
            assert card["engine_prior"]["verdict"] != "admitted_shadow"


def test_sub_floor_and_no_opinion_verdicts(standard_rows):
    pu = _build(standard_rows)
    assert _card(pu, "SUBFLR")["engine_prior"]["verdict"] == "sub_floor"
    penny = _card(pu, "PENNY")
    assert penny["engine_prior"]["verdict"] == "no_opinion"
    # S30b: sub-$2 is NO OPINION, never "historically bad" -- the reason says so.
    assert any("no opinion" in r.lower() or "uninformative" in r.lower()
               for r in penny["engine_prior"]["reasons"])
    assert _card(pu, "ADMIT")["engine_prior"]["verdict"] == "admitted_shadow"


# ---------------------------------------------------------------------- 4

def test_capacity_tiers_follow_the_named_convention(standard_rows):
    pu = _build(standard_rows)
    assert _card(pu, "ADMIT")["execution"]["tier"] == "FULL"
    thin = _card(pu, "THIN")["execution"]
    assert thin["tier"] == "OBSERVE_ONLY" and thin["observe_only"] is True
    assert thin["max_usd"] == pytest.approx(100_000.0 * PU.MAX_ADV_PARTICIPATION)
    nomdv = _card(pu, "NOMDV")["execution"]
    assert nomdv["tier"] == "CANNOT_DETERMINE"
    assert nomdv["observe_only"] is None
    assert PU.LIQUIDITY_COLUMN in nomdv["reason"]           # the column is NAMED


def test_capacity_none_below_the_observation_floor():
    cap = PU.capacity_of(5_000.0)
    assert cap["tier"] == "NONE" and cap["max_usd"] == 0.0


# ---------------------------------------------------------------------- 5

def test_disagreement_is_encoded_against_the_base_rate(standard_rows):
    pu = _build(standard_rows)
    # ADMIT: ratio 2.0 -> engine positive; stub p=0.60 > base 0.4532 -> AGREE.
    agree = _card(pu, "ADMIT")["disagreement"]
    assert agree["engine_stance"] == "positive"
    assert agree["learner_stance"] == "above_base_rate"
    assert agree["sign_disagreement"] is False and agree["verdict"] == "AGREE"
    # A 3-5 band name: engine positive, stub p=0.30 < base rate -> DISAGREE.
    pu2 = _build(standard_rows + [_row("DIS", close=10.0, mean_target=40.0)])  # ratio 4
    dis = _card(pu2, "DIS")["disagreement"]
    assert dis["engine_stance"] == "positive"
    assert dis["learner_stance"] == "at_or_below_base_rate"
    assert dis["sign_disagreement"] is True and dis["verdict"] == "DISAGREE"
    assert pu2["header"]["counts"]["sign_disagreements"] >= 1
    # TOX: engine negative, p=0.30 below base -> the two AGREE (both bearish).
    tox = _card(pu2, "TOX")["disagreement"]
    assert tox["engine_stance"] == "negative" and tox["sign_disagreement"] is False


def test_p_beat_reference_is_the_receipt_base_rate_never_half(standard_rows):
    pu = _build(standard_rows)
    pb = _card(pu, "ADMIT")["p_beat"]
    assert pb["status"] == "OK"
    assert pb["base_rate"] == pytest.approx(0.4532)
    assert pb["vs_base_rate"] == pytest.approx(0.60 - 0.4532, abs=1e-4)
    assert pb["debiased"] == pytest.approx(0.60 - 0.02215, abs=1e-4)


# ---------------------------------------------------------------------- 6

def test_golden_scorecard_and_header_keys(standard_rows):
    """The Capital Allocator consumes this shape. Changing it is a schema
    change: update SCORECARD_KEYS/HEADER_KEYS, bump CODE_VERSION, and fix
    this test KNOWINGLY."""
    assert PU.SCORECARD_KEYS == (
        "symbol", "day", "observed_at", "pit", "identity",
        "engine_prior", "learner_v1", "learner_v2", "p_beat", "state",
        "disagreement", "execution", "days_to_catalyst", "falsifiers",
    )
    pu = _build(standard_rows)
    for card in pu["scorecards"]:
        assert tuple(card.keys()) == PU.SCORECARD_KEYS
    assert set(PU.HEADER_KEYS) <= set(pu["header"].keys()) | {"status"}
    assert pu["header"]["schema"]["schema_hash"] == PU.schema_hash()


# ---------------------------------------------------------------------- 7

def test_pit_after_close_row_is_refused_and_not_scored(standard_rows):
    pu = _build(standard_rows)
    late = _card(pu, "LATE")
    assert late["pit"]["status"] == "REFUSED"
    assert "post-close" in late["pit"]["reason"]
    assert late["learner_v1"]["status"] == "REFUSED"
    assert late["learner_v1"]["score"] is None
    assert late["engine_prior"]["prior_1m"] is None
    assert pu["header"]["counts"]["pit_refused"] == 1


def test_pit_unstamped_row_is_refused():
    assert PU.pit_check(DAY, None)["status"] == "REFUSED"
    assert PU.pit_check(DAY, "not-a-timestamp")["status"] == "REFUSED"
    assert PU.pit_check(DAY, PRE_OPEN)["status"] == "OK"
    # The boundary itself is refused: AT the close is not before it.
    assert PU.pit_check(DAY, f"{DAY}T20:00:00+00:00")["status"] == "REFUSED"


# ---------------------------------------------------------------------- 8

def test_whole_universe_refusals_are_counted_in_the_header(standard_rows):
    pu = _build(standard_rows)
    wu = pu["header"]["whole_universe_refusals"]
    n = len(standard_rows)
    assert wu["learner_v2"]["refused_on"] == n and wu["learner_v2"]["of"] == n
    assert len(wu["learner_v2"]["missing_inputs"]) > 0
    # Derived from the schema functions, so it cannot drift from them.
    assert set(wu["learner_v2"]["missing_inputs"]) == (
        set(D.feature_columns(shadow_only=False)) - set(D.feature_columns(shadow_only=True)))
    assert wu["state"]["refused_on"] == n
    assert "dispersion" in wu["state"]["missing_inputs"]
    # Per-name fields point at the header rather than crashing or imputing.
    for card in pu["scorecards"]:
        assert card["learner_v2"]["status"] == "REFUSED"
        assert card["state"]["status"] == "CANNOT_DETERMINE"


def test_the_starved_seal_sensor_counts_d_catalyst(standard_rows):
    """The incident's exact shape: days_to_catalyst unreadable -- here on one
    name -- must be COUNTED in the header, and the name's falsifier must say
    what a readable value would unlock."""
    pu = _build(standard_rows)
    fr = pu["header"]["field_readability"]["days_to_catalyst"]
    assert fr["unreadable"] == 1                      # NOMDV has d_cat=None
    assert pu["header"]["counts"]["d_catalyst_unreadable"] == 1
    nomdv = _card(pu, "NOMDV")
    assert nomdv["days_to_catalyst"]["readable"] is False
    assert any(f["field"] == "days_to_catalyst" for f in nomdv["falsifiers"])


# ---------------------------------------------------------------------- 9

def test_written_jsonl_round_trips_and_counts_match(tmp_path, standard_rows):
    pu = _build(standard_rows)
    path = PU.write_potential_universe(pu, out_dir=tmp_path)
    assert path.name == f"{DAY}.jsonl"
    back = PU.read_potential_universe(path)
    assert back["header"]["counts"] == pu["header"]["counts"]
    assert len(back["scorecards"]) == back["header"]["counts"]["n_scorecards"]
    assert back["header"]["graded_like_a_book"] == "pending"
    # Header is the FIRST line -- a streaming consumer reads it before any card.
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert first["artefact"] == "AEGIS_POTENTIAL_UNIVERSE"


def test_a_day_with_no_rows_is_a_refused_header_not_a_crash():
    pu = PU.build_potential_universe(
        DAY, rows=[], provenance={"note": "synthetic-empty"},
        champion=_champion(), band_map=_band_map(), v2_receipt=_receipt())
    assert pu["header"]["status"] == "REFUSED"
    assert pu["scorecards"] == []
    assert any("missing or empty" in r for r in pu["header"]["reasons"])


def test_broker_authority_is_declared_none(standard_rows):
    pu = _build(standard_rows)
    assert pu["header"]["broker_authority"].startswith("NONE")
