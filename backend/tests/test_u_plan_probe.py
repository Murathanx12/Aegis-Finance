"""C3 (2026-09-25): the committee shortlist reaches `sim_run.u_plan` under PROBE.

Before this, `u_plan` read only `ranking.json` and refused whenever the ranker's
own `top20_net_rel_21d <= 0` (measured negative since §59), so PC-PAPER never
placed an order and nothing it could have decided was ever graded.

Every broker call is faked on the module (`pc_broker` has no network seam of its
own; the pattern is `test_pc_live_stack.py`'s monkeypatching). Dates derive from
TODAY (session protocol item 5), never a literal.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config
from backend.services import decision_ledger as DL
from backend.services import investment_committee as IC
from backend.services import pc_broker as PB
from scripts import sim_run as S

EQUITY = 1_000_000.0
PRICE = 50.0
TODAY = datetime.now(timezone.utc).date()
ASOF = TODAY.isoformat()


def _funnel(tmp: Path, *, n: int = 25, age_days: float = 1.0,
            generated_at: str | None = "derive", tickers: list[str] | None = None) -> Path:
    tickers = tickers or [f"SL{i:02d}" for i in range(n)]
    stamp = ((datetime.now(timezone.utc) - timedelta(days=age_days))
             .isoformat(timespec="seconds") if generated_at == "derive" else generated_at)
    payload = {"generated_at": stamp,
               "evidence_basis": {"ranked_by": ["profitability_small"]},
               "candidates": [{"ticker": t, "score": 1.0 - i / 100.0,
                               "median_dollar_vol": 5e9, "vol_annual": 0.30 + i / 100.0,
                               "why": [f"reason for {t}"]}
                              for i, t in enumerate(tickers)]}
    p = tmp / "funnel.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _ranking(out: Path, net: float, symbols: list[str] | None = None) -> None:
    symbols = symbols or [f"RK{i:02d}" for i in range(18)]
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranking.json").write_text(json.dumps({
        "asof": ASOF, "top20_net_rel_21d": net, "model_version": "test",
        "top": [{"rank": i + 1, "symbol": s, "decile": 9,
                 "expected_relative_return_21d_net": -0.004}
                for i, s in enumerate(symbols)]}), encoding="utf-8")


class FakeBroker:
    def __init__(self, *, is_open: bool = True, held: dict | None = None):
        self.is_open = is_open
        self.held = held or {}
        self.submitted: list[PB.PlannedOrder] = []
        self.open_orders: list[dict] = []

    def install(self, mp: pytest.MonkeyPatch) -> "FakeBroker":
        mp.setattr(PB, "snapshot", lambda **kw: {
            "equity": EQUITY, "cash": EQUITY, "n_positions": len(self.held),
            "positions": [{"symbol": s, "qty": q} for s, q in self.held.items()]})
        mp.setattr(PB, "last_prices", lambda syms: {s: PRICE for s in syms})
        mp.setattr(PB, "clock", lambda: {"is_open": self.is_open})
        mp.setattr(PB, "orders", lambda **kw: list(self.open_orders))

        def _submit(plan, **kw):
            self.submitted.append(plan)
            self.open_orders.append({"symbol": plan.symbol})
            return {"status": "submitted", "symbol": plan.symbol, "side": plan.side,
                    "qty": plan.qty, "notional": plan.notional}
        mp.setattr(PB, "submit", _submit)
        return self


def _run(tmp: Path, mode: str = "paper_profit", **kw) -> dict:
    return S.u_plan(tmp / "out", mode, asof=ASOF,
                    funnel_path=kw.get("funnel_path") or tmp / "funnel.json",
                    ledger_path=tmp / "ledger.jsonl",
                    contracts_dir=tmp / "decisions" / "pc_plan")


def _receipt(tmp: Path) -> dict:
    return json.loads((tmp / "out" / "intended_book.json").read_text(encoding="utf-8"))


# ─────────────────────────────── the headline ───────────────────────────────

def test_negative_ranker_still_probes_the_shortlist_at_the_cap(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)

    res = _run(tmp_path)

    assert res["verdict"] == "MEASURED_NEGATIVE"
    assert res["exploit_acting"] is False
    assert res["probe_verdict"] == "UNMEASURED_TRADE_SMALL"
    assert res["probe_acting"] is True and res["acting"] is True
    assert res["n_exploit_orders"] == 0
    assert res["shortlist"] == 25 and res["shortlist_red"] is None
    assert res["n_considered"] == 25 + 18

    shortlist = {f"SL{i:02d}" for i in range(25)}
    assert fb.submitted, "a PROBE book must actually be sent in paper_profit"
    assert all(p.symbol in shortlist for p in fb.submitted), "zero EXPLOIT orders"
    assert all(p.side == "buy" for p in fb.submitted)
    assert len(fb.submitted) <= config.PROBE_MAX_NAMES
    cap = config.PROBE_MAX_WEIGHT * EQUITY
    assert all(p.notional <= cap + 1e-6 for p in fb.submitted)
    assert sum(p.notional for p in fb.submitted) <= config.PROBE_GROSS_CAP * EQUITY + 1e-6
    # best shortlist score first
    assert [p.symbol for p in fb.submitted] == sorted(p.symbol for p in fb.submitted)
    assert fb.submitted[0].symbol == "SL00"


def test_every_probe_decision_is_on_the_ledger_and_gradeable(tmp_path, monkeypatch):
    FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path)

    n_rows = res["n_probe"] * len(config.PROBE_HORIZONS_SESSIONS)
    decided = [r for r in DL.read(tmp_path / "ledger.jsonl") if r["state"] == "DECIDED"]
    assert len(decided) == n_rows
    d = decided[0]["detail"]
    assert d["state"] == "PROBE" and d["ticker"].startswith("SL")
    assert d["weight"] == pytest.approx(config.PROBE_MAX_WEIGHT)
    assert d["dollars"] == pytest.approx(config.PROBE_MAX_WEIGHT * EQUITY)
    assert d["thesis_source"].startswith("funnel:profitability_small@")
    assert d["ranking_verdict"]["verdict"] == "MEASURED_NEGATIVE"
    assert d["hypothesis_id"] == config.PROBE_SHORTLIST_HYPOTHESIS_ID

    # the grader's own reader finds them (source + expiry are what it prices on)
    rows = DL._open_contract_rows(day=TODAY, out_dir=tmp_path / "decisions",
                                  path=tmp_path / "ledger.jsonl")
    mine = [r for r in rows if r.get("policy_id") == S.PROBE_POLICY_ID]
    assert len(mine) == n_rows
    assert all(r["direction"] == "PROBE" and r["source"] == "investment_committee"
               and r["expiry_utc"] and r["virtual"] is False for r in mine)

    # and so does the autopsy
    from scripts import decision_autopsy as DA
    got = DA.load_decisions(tmp_path / "decisions")
    assert {g["ticker"] for g in got if g["origin"] == "pc_plan"} == \
        {f"SL{i:02d}" for i in range(res["n_probe"])}


def test_a_second_cycle_neither_duplicates_decisions_nor_resends(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    _run(tmp_path)
    n_sent, n_ledger = len(fb.submitted), len(DL.read(tmp_path / "ledger.jsonl"))
    res2 = _run(tmp_path)
    assert len(fb.submitted) == n_sent, "an open order must not be sent again"
    assert len(DL.read(tmp_path / "ledger.jsonl")) == n_ledger
    assert res2["decisions_new"] == 0


def test_a_closed_venue_sends_nothing_and_says_so(tmp_path, monkeypatch):
    fb = FakeBroker(is_open=False).install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path)
    assert fb.submitted == []
    assert "venue closed" in res["send_block"]


# ─────────────────────────────── red, not silent ────────────────────────────

def test_an_empty_shortlist_is_red_and_places_nothing(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=0, tickers=[])
    p = tmp_path / "funnel.json"
    blob = json.loads(p.read_text(encoding="utf-8"))
    blob["candidates"] = []
    p.write_text(json.dumps(blob), encoding="utf-8")
    _ranking(tmp_path / "out", net=-0.2)

    res = _run(tmp_path)

    assert fb.submitted == []
    assert res["shortlist"] == 0
    assert res["shortlist_red"] and res["shortlist_red"].startswith("shortlist: 0")
    assert res["probe_acting"] is False
    rec = _receipt(tmp_path)
    assert rec["shortlist"] == 0 and "shortlist: 0" in rec["why_not"]
    assert not (tmp_path / "ledger.jsonl").exists()


def test_a_stale_funnel_refuses(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    f = _funnel(tmp_path, n=25, age_days=IC.FUNNEL_STALE_DAYS + 5)
    with pytest.raises(IC.ShortlistRefused, match="days old"):
        IC.shortlist(ASOF, funnel_path=f)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path)
    assert fb.submitted == []
    assert "REFUSED" in res["shortlist_red"] and res["shortlist"] == 0


def test_an_undateable_or_future_funnel_refuses(tmp_path):
    f = _funnel(tmp_path, n=5, generated_at=None)
    with pytest.raises(IC.ShortlistRefused, match="CANNOT BE DETERMINED"):
        IC.shortlist(ASOF, funnel_path=f)
    f = _funnel(tmp_path, n=5, age_days=-3)
    with pytest.raises(IC.ShortlistRefused, match="lookahead"):
        IC.shortlist(ASOF, funnel_path=f)


def test_shortlist_rows_carry_the_declared_fields(tmp_path):
    rows = IC.shortlist(ASOF, funnel_path=_funnel(tmp_path, n=4))
    assert [r["ticker"] for r in rows] == ["SL00", "SL01", "SL02", "SL03"]
    assert set(rows[0]) >= {"ticker", "score", "source", "reasons"}
    assert rows[0]["reasons"] == ["reason for SL00"]


# ─────────────────────────────── the worst case ─────────────────────────────

def test_the_worst_case_line_is_on_the_receipt_and_its_arithmetic_checks(tmp_path, monkeypatch):
    FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path)
    wc = _receipt(tmp_path)["worst_case"]["largest_admissible"]

    n, w = config.PROBE_MAX_NAMES, config.PROBE_MAX_WEIGHT
    assert wc["n_names"] == n and wc["notional_pct"] == pytest.approx(w)
    max_vol = 0.30 + 24 / 100.0                     # the shortlist's highest vol_annual
    sigma = max_vol / math.sqrt(252)
    stop = config.PROBE_WORST_CASE_SIGMA * sigma
    assert wc["stop_sigma_pct"] == pytest.approx(stop)
    assert wc["worst_case_k_sigma_usd"] == pytest.approx(-(n * w * stop * EQUITY))
    assert wc["gross_over_equity"] == pytest.approx(n * w)
    assert wc["gross_over_equity"] <= config.PROBE_GROSS_CAP + 1e-12
    assert wc["worst_case_no_stop_usd"] == pytest.approx(-(n * w * EQUITY))
    assert wc["stop_declared"] is False
    assert res["worst_case_line"] == wc["line"]
    assert f"-${n * w * stop * EQUITY:,.0f}" in wc["line"]
    assert f"-${n * w * EQUITY:,.0f}" in wc["line"]


# ─────────────────────────────── the gates ──────────────────────────────────

def test_observe_never_acts(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=+0.05)            # even a POSITIVE ranking
    res = S.u_plan(tmp_path / "out", "observe", asof=ASOF,
                   funnel_path=tmp_path / "funnel.json",
                   ledger_path=tmp_path / "ledger.jsonl",
                   contracts_dir=tmp_path / "decisions" / "pc_plan")
    assert res["acting"] is False
    assert res["probe_acting"] is False and res["exploit_acting"] is False
    assert fb.submitted == []
    rec = _receipt(tmp_path)
    assert rec["acting"] is False and rec["why_not"] == "mode=observe"
    # the decision is still recorded, as a virtual one
    rows = json.loads((tmp_path / "decisions" / "pc_plan" / f"{ASOF}.json")
                      .read_text(encoding="utf-8"))["rows"]
    assert rows and all(r["virtual"] is True and r["acting"] is False for r in rows)


def test_the_exploit_gate_is_unchanged_when_the_ranking_is_positive(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=+0.01)
    res = _run(tmp_path)
    assert res["verdict"] == "MEASURED_POSITIVE" and res["exploit_acting"] is True
    assert res["n_exploit_orders"] == 18
    probe = [p for p in fb.submitted if p.symbol.startswith("SL")]
    assert probe and all(p.notional <= config.PROBE_MAX_WEIGHT * EQUITY + 1e-6 for p in probe)
    # total gross stays at or under equity: no leverage from adding PROBE
    assert sum(p.notional for p in fb.submitted) <= EQUITY + 1e-6


def test_a_measured_negative_shortlist_stops_probing(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    h = min(config.PROBE_HORIZONS_SESSIONS)
    ledger = tmp_path / "ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for i in range(config.PROBE_GRADE_MIN_SESSIONS):
            fh.write(json.dumps({
                "decision_id": f"x{i}", "state": "SCORED",
                "asof": (TODAY - timedelta(days=60 - i)).isoformat(),
                "detail": {"hypothesis_id": config.PROBE_SHORTLIST_HYPOTHESIS_ID,
                           "horizon_sessions": h, "excess_return": -0.01}}) + "\n")
    res = _run(tmp_path)
    assert res["probe_verdict"] == "MEASURED_NEGATIVE"
    assert res["probe_acting"] is False and fb.submitted == []


def test_one_day_short_of_the_grade_is_still_unmeasured(tmp_path):
    h = min(config.PROBE_HORIZONS_SESSIONS)
    ledger = tmp_path / "ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for i in range(config.PROBE_GRADE_MIN_SESSIONS - 1):
            for _ in range(3):                       # three rows on one day count once
                fh.write(json.dumps({
                    "decision_id": f"x{i}-{_}", "state": "SCORED",
                    "asof": (TODAY - timedelta(days=60 - i)).isoformat(),
                    "detail": {"hypothesis_id": config.PROBE_SHORTLIST_HYPOTHESIS_ID,
                               "horizon_sessions": h, "excess_return": -0.01}}) + "\n")
    g = S._probe_grade(ledger)
    assert g["verdict"] == "UNMEASURED_TRADE_SMALL"
    assert g["n_days_scored"] == config.PROBE_GRADE_MIN_SESSIONS - 1
