"""C18 (2026-10-07): reputation-weighted analyst consensus + the snowball shadow series.

Offline. Every input is a literal fixture or a synthetic frame built here; dates are
fixed literals of PAST moments (no calendar moment is encoded as "next week").
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import analyst_reputation as AR
from backend.services import pit_features as PF
from backend.services import snowball_shadow as SS

FIX = Path(__file__).parent / "fixtures" / "analyst_reputation"
ASOF = pd.Timestamp("2026-06-01")


def _claims(firm: str, sector: str, n: int, hit: float, direction: int = 1,
            public_at: str = "2025-06-01") -> pd.DataFrame:
    k = int(round(n * hit))
    return pd.DataFrame({"firm": firm, "sector": sector, "horizon": AR.HORIZON, "direction": direction,
                         "outcome": [1.0] * k + [0.0] * (n - k), "public_at": pd.Timestamp(public_at)})


def _corpus() -> pd.DataFrame:
    """A (reliable) and B..F (unreliable), all buy-direction claims in one sector, plus
    a second sector so the direction base rate is not the sector's own mean."""
    parts = [_claims("A", "Tech", 50, 0.80)]
    parts += [_claims(f, "Tech", 50, 0.30) for f in "BCDEF"]
    parts += [_claims("G", "Banks", 100, 0.55), _claims("G", "Banks", 60, 0.50, direction=-1)]
    return pd.concat(parts, ignore_index=True)


# ── constants frozen before any read ──

def test_k1_is_the_unchanged_prereg_constant_and_k_sub_is_declared_in_config():
    assert AR.K1 == PF.SKILL_SHRINK_K == 20
    assert C.ANALYST_REP_K_SUB == 40 and AR.K_SUB == 40


def test_firm_reliability_is_byte_identical_to_the_pinned_fixture():
    blob = json.loads((FIX / "firm_reliability_pinned.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(blob["corpus"])
    df["public_at"] = pd.to_datetime(df["public_at"])
    out = PF.firm_reliability(df, pd.Timestamp(blob["asof"]))
    csv = out.to_csv(float_format="%.17g")
    assert csv == blob["expected_csv"]
    assert hashlib.sha256(csv.encode()).hexdigest() == blob["expected_sha256"]


# ── the three levels ──

def test_one_reliable_firm_outweighs_each_unreliable_one_and_pulls_the_stance():
    tabs = AR.reputation_tables(_corpus(), ASOF)
    wa = AR.cell_weight(tabs, "A", "Tech")["weight"]
    wb = [AR.cell_weight(tabs, f, "Tech")["weight"] for f in "BCDEF"]
    assert wa == PF.SKILL_CLIP[1] and all(w == PF.SKILL_CLIP[0] for w in wb)
    # stance: A says buy (+1), B..F say sell (-1)
    flat = (1 - 5) / 6
    weighted = (wa * 1 + sum(-w for w in wb)) / (wa + sum(wb))
    assert weighted > flat + 0.3            # -0.25 vs -0.667: the weighting, not the data, moved it
    # the clip caps one firm at 3x another: against THREE unreliable firms A's sign wins
    w3 = (wa - sum(wb[:3])) / (wa + sum(wb[:3]))
    assert w3 == 0.0 or np.sign(w3) >= 0
    w2 = (wa - sum(wb[:2])) / (wa + sum(wb[:2]))
    assert w2 > 0 and (1 - 2) / 3 < 0     # flat mean would have gone the other way


def test_a_new_firm_inherits_its_sector_prior_exactly():
    tabs = AR.reputation_tables(_corpus(), ASOF)
    sec = tabs["sectors"].set_index("sector")
    shrunk = float(sec.at["Tech", "shrunk_sh"])
    assert abs(shrunk) > 1e-6                                   # a measured, nonzero sector prior
    z = AR.cell_weight(tabs, "NEWFIRM", "Tech")
    assert z["n_firm"] == 0 and z["n_cell"] == 0
    assert z["firm_eff"] == pytest.approx(shrunk, abs=1e-12)
    assert z["edge_final"] == pytest.approx(shrunk, abs=1e-12)
    assert z["weight"] == pytest.approx(float(np.clip(1 + PF.SKILL_SLOPE * shrunk, *PF.SKILL_CLIP)))
    assert z["weight"] != PF.SKILL_PRIOR
    # a sector with no history shrinks to the global anchor: weight exactly 1.0
    assert AR.cell_weight(tabs, "NEWFIRM", "Nowhere")["weight"] == 1.0


def test_pit_claims_not_resolved_before_asof_change_nothing():
    base = _corpus()
    t0 = AR.reputation_tables(base, ASOF)
    # rows dated before ASOF by naive date but whose outcome resolves on/after it
    late = pd.Timestamp(ASOF) - pd.Timedelta(days=PF.RESOLVE_DAYS) + pd.Timedelta(days=1)
    extra = pd.concat([_claims("A", "Tech", 200, 0.0, public_at=str(late.date())),
                       _claims("NEW", "Tech", 200, 1.0, public_at=str(late.date()))], ignore_index=True)
    t1 = AR.reputation_tables(pd.concat([base, extra], ignore_index=True), ASOF)
    cols = ["firm", "sector", "horizon", "n_cell", "n_firm", "n_sh", "edge_final", "weight"]
    pd.testing.assert_frame_equal(t0["cells"][cols].reset_index(drop=True), t1["cells"][cols].reset_index(drop=True))
    pd.testing.assert_frame_equal(t0["sectors"], t1["sectors"])


def test_rows_first_seen_after_asof_never_enter():
    rv = pd.DataFrame({"ticker": ["X", "X"], "firm": ["A", "B"], "target_action": ["Raises", "Raises"],
                       "event_date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
                       "first_seen": pd.to_datetime(["2026-05-03", "2026-06-02"])})
    k = AR.known_before(rv, ASOF)
    assert list(k["firm"]) == ["A"]


# ── per-ticker aggregate ──

def _rv(firms, grades, targets, days, ticker="T"):
    return pd.DataFrame({"ticker": ticker, "firm": firms, "to_grade": grades, "current_target": targets,
                         "event_date": pd.to_datetime(days),
                         "first_seen": pd.to_datetime(days) + pd.Timedelta(days=1)})


def test_unequal_weights_order_the_firms_and_thin_coverage_is_printed_not_dropped():
    tabs = AR.reputation_tables(_corpus(), ASOF)
    wa, wb = AR.cell_weight(tabs, "A", "Tech")["weight"], AR.cell_weight(tabs, "B", "Tech")["weight"]
    assert wa > wb                                               # unequal by construction (1.5 vs 0.5)
    rv = _rv(["B", "A"], ["Sell", "Buy"], [8.0, 20.0], ["2026-05-01", "2026-05-02"])
    c = AR.ticker_consensus(rv, "T", "Tech", tabs, ASOF, price=10.0)
    assert [f["firm"] for f in c["weight_bearing_firms"]] == ["A", "B"]   # |w x stance| descending
    assert c["weighted_stance"] == pytest.approx((wa - wb) / (wa + wb))
    assert c["weighted_stance"] > c["flat_stance"] == 0.0
    assert c["sum_of_weights"] == pytest.approx(wa + wb)
    one = AR.ticker_consensus(rv.iloc[:1], "T", "Tech", tabs, ASOF, price=10.0)
    assert one["n_covering_firms"] == 1 and one["sum_of_weights"] == pytest.approx(wb)   # printed, not excluded


def test_n_covering_firms_never_exceeds_the_firms_in_the_file():
    tabs = AR.reputation_tables(_corpus(), ASOF)
    rv = _rv(["A", "A", "B", "G"], ["Buy", "Buy", "Sell", "Hold"], [20.0, 21.0, 8.0, 10.0],
             ["2026-03-01", "2026-05-01", "2026-05-02", "2026-04-01"])
    c = AR.ticker_consensus(rv, "T", "Tech", tabs, ASOF, price=10.0)
    assert c["n_covering_firms"] <= rv["firm"].nunique() == 3
    old = _rv(["A"], ["Buy"], [20.0], ["2025-01-01"])            # outside the 365-day cover window
    assert AR.ticker_consensus(old, "T", "Tech", tabs, ASOF) is None


def test_weighted_target_is_null_when_stale_or_single_firm_and_upside_is_diagnostic_only():
    tabs = AR.reputation_tables(_corpus(), ASOF)
    stale = _rv(["A", "B"], ["Buy", "Buy"], [20.0, 18.0], ["2026-01-02", "2026-01-03"])   # > 90 days before ASOF
    c = AR.ticker_consensus(stale, "T", "Tech", tabs, ASOF, price=10.0)
    assert c["weighted_median_target"] is None and c["weighted_upside_DIAGNOSTIC_ONLY"] is None
    assert c["missing_because"]["weighted_median_target"].startswith("stale_target")
    single = _rv(["A", "B"], ["Buy", "Buy"], [20.0, 18.0], ["2026-05-01", "2026-01-03"])
    c1 = AR.ticker_consensus(single, "T", "Tech", tabs, ASOF, price=10.0)
    assert c1["weighted_median_target"] is None
    assert c1["missing_because"]["weighted_median_target"].startswith("single_firm")
    fresh = _rv(["A", "B"], ["Buy", "Buy"], [20.0, 18.0], ["2026-05-01", "2026-05-02"])
    c2 = AR.ticker_consensus(fresh, "T", "Tech", tabs, ASOF, price=10.0)
    assert c2["weighted_median_target"] == 20.0 and "weighted_upside" not in c2
    assert c2["weighted_upside_DIAGNOSTIC_ONLY"] == pytest.approx(1.0)


def _persist_claims(sign: int) -> pd.DataFrame:
    """20 firms, 60 tickers each half; firm i's hit rate is fixed across halves (sign=+1)
    or reversed in the second half (sign=-1)."""
    rng = np.random.default_rng(11)
    rows = []
    for i in range(20):
        p1 = 0.3 + 0.02 * i
        for half, start in ((0, "2025-01-01"), (1, "2025-09-01")):
            p = p1 if (half == 0 or sign > 0) else 1.0 - p1
            for k in range(120):
                day = pd.Timestamp(start) + pd.Timedelta(days=int(k % 150))
                rows.append({"firm": f"F{i:02d}", "sector": "Tech", "horizon": AR.HORIZON, "direction": 1,
                             "outcome": float(rng.random() < p), "ticker": f"T{k}",
                             "event_date": day, "public_at": day})
    return pd.DataFrame(rows)


def test_persistence_test_reads_persistent_and_reversed_firms():
    good = AR.persistence_test(_persist_claims(+1), thresholds=(20, 50, 100), n_boot=200)
    bad = AR.persistence_test(_persist_claims(-1), thresholds=(20, 50, 100), n_boot=200)
    assert good["verdict"] == "PERSISTENT_OOS"
    assert bad["verdict"] == "NOT_PERSISTENT_OOS" and bad["label"].startswith("REPUTATION_WEIGHT: NOT_PERSISTENT_OOS")
    assert good["module_weight_vs_second_half"]["spearman_vs_month_x_direction_edge"] > 0.5
    assert bad["module_weight_vs_second_half"]["spearman_vs_month_x_direction_edge"] < -0.5
    with pytest.raises(AR.ReputationRefused):
        AR.persistence_test(_persist_claims(+1).head(50))


def test_dry_run_writes_nothing_and_receipts_are_never_overwritten(tmp_path, monkeypatch):
    blob = {"schema": AR.SCHEMA, "asof": "2026-10-07T00:00:00", "label": "X",
            "persistence": {"verdict": "NOT_PERSISTENT_OOS", "label": "X"}}
    monkeypatch.setattr(AR, "compute_receipt", lambda asof, **kw: dict(blob))
    out, path, fresh = AR.monthly_receipt(pd.Timestamp("2026-10-07"), base=tmp_path, write=False)
    assert path is None and not fresh and list(tmp_path.iterdir()) == []
    out, path, fresh = AR.monthly_receipt(pd.Timestamp("2026-10-07"), base=tmp_path)
    assert fresh and path.exists() and len(list(tmp_path.glob("reputation_persistence_*.json"))) == 1
    again, p2, fresh2 = AR.monthly_receipt(pd.Timestamp("2026-10-20"), base=tmp_path)
    assert p2 == path and not fresh2                          # read back, never rewritten
    # a receipt under an OLDER schema stays on disk and is not read back
    (tmp_path / "reputation_weights_2026-11.json").write_text(json.dumps({"schema": "analyst_reputation/1"}))
    assert AR.current_month_receipt("2026-11", tmp_path) is None
    with pytest.raises(AR.ReputationRefused):
        AR._write_new(path, blob)


def test_kish_and_weighted_median():
    assert AR.kish_n_effective([1, 1, 1, 1]) == pytest.approx(4.0)
    assert AR.kish_n_effective([1.5, 0.5]) == pytest.approx(4 / 2.5)
    assert AR.kish_n_effective([]) is None
    assert AR.weighted_median([10, 20, 30], [1, 1, 5]) == 30
    assert AR.weighted_median([10, 20, 30], [1, 1, 1]) == 20


# ── the Explorer ──

OWNER = ("QUBT", "KYTX", "SLDP", "SOC", "NOVT")


def test_saved_explorer_receipt_rows_for_the_owners_names_carry_coverage_and_the_label():
    """Pinned from the receipt written after review C18 (path inside the fixture)."""
    blob = json.loads((FIX / "explorer_owner_rows.json").read_text(encoding="utf-8"))
    assert blob["analyst_reputation_label"].startswith("REPUTATION_WEIGHT: NOT_PERSISTENT_OOS")
    rows = {r["ticker"]: r for r in blob["rows"]}
    assert set(rows) == set(OWNER)
    for t in OWNER:
        r = rows[t]
        assert r["n_targets"] is not None                     # the raw yfinance count, kept, not compared
        assert r["n_covering_firms"] >= 1 and r["sum_of_weights"] > 0
        assert r["label"] == blob["analyst_reputation_label"]
        assert r["weighted_upside_shown"] is False
    for t in ("SLDP", "SOC", "NOVT"):                          # the n < 5 cliff names: printed, not gated
        assert rows[t]["cliff_replaced"]["n_covering_firms"] == rows[t]["n_covering_firms"]


def test_build_row_carries_reputation_fields(monkeypatch):
    from scripts import opportunities_build as B
    assert "ZZZT" not in C.WHY_MOVED_TICKER_SECTOR      # sector comes from the rep context
    tabs = AR.reputation_tables(_corpus(), ASOF)
    rv = pd.DataFrame({"ticker": ["ZZZT", "ZZZT"], "firm": ["A", "G"], "to_grade": ["Buy", "Buy"],
                       "current_target": [150.0, 140.0],
                       "event_date": pd.to_datetime(["2026-05-01", "2026-04-01"]),
                       "first_seen": pd.to_datetime(["2026-05-02", "2026-04-02"])})
    rep = {"known": rv, "tabs": tabs, "sectors": {"ZZZT": "Tech"}, "source": "fixture", "receipt": "fixture",
           "asof": ASOF, "error": None, "label": "REPUTATION_WEIGHT: NOT_PERSISTENT_OOS (fixture)",
           "pit_status": "NOT_PIT"}
    ctx = {"today": "2026-06-01", "asof": "2026-06-01", "cards": {}, "facts": {}, "yf": {"ZZZT": {"n": 2, "key": "buy"}},
           "mw": {}, "identity": {}, "px": {"ZZZT": {"close": 100.0, "date": "2026-05-29", "source": "fixture",
                                                    "sigma63": 0.02, "n_obs": 63}},
           "targets": {"ZZZT": {"low": 120.0, "median": 140.0, "high": 150.0, "mean": 140.0,
                                "observed_utc": "2026-05-30", "snapshot_price": 100.0}},
           "revisions": {}, "revisions_pulled": "pulled 2026-05-30", "revision_through": "2026-05-30",
           "official": {"insiders": {}, "insider_table_first_public_utc": "2026-05-01T00:00:00+00:00",
                        "issuer_names": {}, "short_interest": {}, "politicians": {}},
           "news": {}, "earn_cache": {}, "ciks": {}, "spy_dates": [], "dated_firms": {}, "dated_firms_ok": True,
           "runway": {}, "insider_window_days": 30, "reputation": rep}
    lst = {"list_id": "roi_v3", "kind": "ranking", "asof": "2026-05-01", "horizon": "x", "evidence_default": "OBSERVED"}
    e = {"ticker": "ZZZT", "rank": None, "list_score": 0.26, "eligibility": "EXCLUDED_BY_v3.2_RULE",
         "why_list": "n < 5 (n 2)", "n": 2}
    r = B.build_row(e, lst, ctx)
    u, a = r["upside"], r["analyst_reputation"]
    assert u["n_targets"] == 2                                # yfinance count, never compared below
    for gone in ("n_effective", "weighted_upside", "weight_bearing_firms", "n_covering_firms"):
        assert gone not in u                                  # review F3-F6: not on the upside cell
    assert a["label"] == "REPUTATION_WEIGHT: NOT_PERSISTENT_OOS (fixture)"
    assert a["n_covering_firms"] == 2 and a["sum_of_weights"] > 0
    assert u["cliff_replaced"] == {"old_rule": "n analysts >= 5 (stock lists v3.2)", "n_covering_firms": 2,
                                   "sum_of_weights": a["sum_of_weights"], "label": a["label"],
                                   "note": "the list's frozen rule still excluded it; coverage is printed, not gated"}
    assert "weighted_stance" not in r["analyst_stance"]
    # a failed reputation load is a named reason, never a crash
    ctx["reputation"] = {"error": "ERROR fixture"}
    r2 = B.build_row(e, lst, ctx)
    assert "analyst reputation unavailable" in r2["missing_because"]["analyst_reputation"]
    assert r2["analyst_reputation"] is None and r2["upside"]["n_targets"] == 2


# ── the snowball shadow series ──

def test_expanding_base_rate_never_uses_a_window_that_closed_on_or_after_the_day():
    day = pd.to_datetime(pd.Series(["2020-01-01", "2020-03-01", "2020-06-01", "2020-09-01"]))
    res = pd.to_datetime(pd.Series(["2020-04-01", "2020-06-01", "2020-09-01", "2020-12-01"]))
    out = pd.Series([1.0, 1.0, 0.0, 1.0])
    p, n = SS.expanding_base_rate(day, res, out, pseudo=20)
    assert list(n) == [0, 0, 1, 2]                       # event 2: only event 0 closed BEFORE 06-01
    assert p[0] == p[1] == 0.5
    assert p[2] == pytest.approx((1 + 10) / (1 + 20))
    assert p[3] == pytest.approx((2 + 10) / (2 + 20))
    # mutating a FUTURE outcome changes nothing earlier
    out2 = out.copy()
    out2.iloc[3] = 0.0
    p2, _ = SS.expanding_base_rate(day, res, out2, pseudo=20)
    np.testing.assert_array_equal(p, p2)
    # the trailing window: an event that closed more than 24 months before the day drops out
    d4 = pd.to_datetime(pd.Series(["2020-01-01", "2023-01-01"]))
    r4 = pd.to_datetime(pd.Series(["2020-04-01", "2023-04-01"]))
    _, n4 = SS.expanding_base_rate(d4, r4, pd.Series([1.0, 1.0]), pseudo=20, window_months=24)
    _, n4_all = SS.expanding_base_rate(d4, r4, pd.Series([1.0, 1.0]), pseudo=20, window_months=None)
    assert list(n4) == [0, 0] and list(n4_all) == [0, 1]
    # an unknown outcome never enters
    out3 = out.copy()
    out3.iloc[0] = np.nan
    _, n3 = SS.expanding_base_rate(day, res, out3, pseudo=20)
    assert list(n3) == [0, 0, 0, 1]


def _sessions() -> pd.DatetimeIndex:
    return pd.bdate_range("2023-01-02", "2024-12-31")


def test_t0_events_follow_through_and_the_grader():
    s = _sessions()
    rows = [("X", "2023-01-03", "A"),                    # history
            ("X", "2023-08-01", "B"),                    # t0: >= 90 quiet days, history >= 180 days before
            ("X", "2023-08-01", "C"),                    # same-day co-raiser: a t0 broker, not a follower
            ("X", "2023-08-10", "D"), ("X", "2023-09-01", "E"), ("X", "2023-09-02", "D")]
    r = pd.DataFrame(rows, columns=["ticker", "day", "firm"])
    r["day"] = pd.to_datetime(r["day"])
    ev = SS.t0_events(r, s)
    assert list(ev["day"].dt.strftime("%Y-%m-%d")) == ["2023-08-01"]
    assert ev["t0_brokers"].iloc[0] == ["B", "C"]
    assert int(SS.follow_through(ev, r, s).iloc[0]) == 2          # D and E, D once
    recs = [{"ticker": "X", "t0_brokers": ["B", "C"], "made_at": "2023-08-01", "probability": 0.25,
             "resolves_after": str(s[s.searchsorted(pd.Timestamp("2023-08-01")) + SS.H].date()),
             "outcome": None}]
    now = datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert SS.grade_due(recs, r, s, today=pd.Timestamp("2023-09-01"), now=now) == 0   # not yet due
    assert SS.grade_due(recs, r, s, today=pd.Timestamp("2024-06-01"), now=now) == 1
    assert recs[0]["outcome"] == 1 and recs[0]["brier"] == pytest.approx(0.5625)


def test_belief_state_cannot_grade_the_follow_through_observable():
    """Spec §4.1, pinned: the forecast ledger's resolver does not know this observable."""
    from backend.services import belief_state as BS
    rec = {"ticker": "X", "observable": SS.OBSERVABLE, "horizon_days": 63, "probability": 0.3,
           "made_at": "2024-01-02", "resolves_after": "2024-04-01", "outcome": None, "benchmark": "SPY"}
    prices = pd.DataFrame({"X": [1.0, 1.1], "SPY": [1.0, 1.0]}, index=pd.to_datetime(["2024-01-02", "2024-05-01"]))
    try:
        out = BS.resolve_one(rec, prices, today=pd.Timestamp("2024-06-01"))
    except Exception:                                          # noqa: BLE001
        out = None
    assert out is None or (isinstance(out, dict) and out.get("outcome") is None)


def test_ledger_never_shrinks(tmp_path):
    p = tmp_path / "s.jsonl"
    SS._write_ledger([{"a": 1}, {"a": 2}], p, 0)
    with pytest.raises(SS.SnowballRefused):
        SS._write_ledger([{"a": 1}], p, 2)
    assert len(SS.read_ledger(p)) == 2


def test_task_keeper_snowball_job_logs_ok_and_refused(tmp_path):
    from scripts import task_keeper as TK
    log = tmp_path / "keeper.jsonl"
    ok = TK.run_snowball(job=lambda: {"status": "ok", "rows_total": 3, "rows_new": 1}, log_path=log)
    assert ok["action"] == "ok" and ok["snowball"]["rows_new"] == 1

    def boom() -> dict:
        raise SS.SnowballRefused("no t0 event")
    bad = TK.run_snowball(job=boom, log_path=log)
    assert bad["action"] == "refused" and "no t0 event" in bad["snowball"]["why"]
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2


def test_summary_never_blends_forward_into_replay():
    rows = [{"made_at": "2024-01-02", "evidence": "REPLAY", "probability": 0.3, "outcome": 1, "brier": 0.49},
            {"made_at": "2024-02-02", "evidence": "REPLAY", "probability": 0.3, "outcome": 0, "brier": 0.09},
            {"made_at": "2026-10-05", "evidence": "FORWARD", "probability": 0.3, "outcome": 1, "brier": 0.49},
            {"made_at": "2026-10-06", "evidence": "FORWARD", "probability": 0.3, "outcome": None, "brier": None}]
    s = SS.summary(rows)
    assert s["replay"]["graded"] == 2 and s["replay"]["brier"] == pytest.approx(0.29)
    assert s["forward"]["graded"] == 1 and s["forward"]["brier"] == pytest.approx(0.49)
    assert s["replay"]["brier_constant_rate_LOOKAHEAD"] == pytest.approx(0.25)
    assert "brier_replay" not in s
