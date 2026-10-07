"""Replay of tonight's PC-PAPER plan on the REAL account state (owner, 2026-10-07 17:05 HKT).

Owner: "dont stay cash on pc. lets do the best decision and profit maximizing strat"
-> D14 benchmark core ON, D21 the active sleeve counts in the contract, D22 the
index ETF is exempt from the 12% name cap, plus an EXPLOIT sleeve mirroring the
frozen book revision_flow_v0 (cb8d492bb8bf9ade).

The fixture is the real 2026-10-06 broker read of PC-PAPER (equity, cash, the
ten held PROBE names) with real prices and the panel's 63-session sigmas
(`fixtures/pc_plan_replay/pc_paper_2026-10-06.json`). Every broker call is
faked as in test_u_plan_probe.py; dates derive from today.

Pins:
* every new flag OFF -> the plan equals the golden captured from the code
  BEFORE this change (`plan_flags_off_golden.json`), field by field;
* flags ON -> SPY core + the revision_flow sleeve + the ranker's sleeves,
  gross <= 100%, no name above 12% except SPY, the worst-case block printed;
* the order-path gate still blocks (mandate disagreement, worst case) and
  observe still sends nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import config
from backend.services import pc_broker as PB
from backend.services import pc_risk as PR
from backend.tests.test_u_plan_probe import ASOF, _ranking
from scripts import sim_run as S

FIX = Path(__file__).parent / "fixtures" / "pc_plan_replay"
STATE = json.loads((FIX / "pc_paper_2026-10-06.json").read_text(encoding="utf-8"))
GOLDEN = FIX / "plan_flags_off_golden.json"
HELD = [p["symbol"] for p in STATE["positions"]]
RF_NAMES = ["OKTA", "SNOW", "CRWD", "PANW", "CRM", "ABNB", "AFRM", "GTLB", "AMD", "ESTC",
            "AMGN", "TGT", "NET", "DDOG", "MDB", "ZS", "WDAY", "S", "XYZ", "DELL"]
NEW_FLAGS = ("PC_BENCHMARK_CORE", "PC_BENCHMARK_CORE_EXEMPT_FROM_NAME_CAP",
             "PC_SLEEVE_REVISION_FLOW")


def _funnel_held(tmp: Path) -> Path:
    """Today's shortlist = the ten held PROBE names (vol from the panel sigma)."""
    from datetime import datetime, timedelta, timezone
    stamp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    cands = [{"ticker": t, "score": 1.0 - i / 100.0, "median_dollar_vol": 5e9,
              "vol_annual": float(STATE["sigmas"][t]) * 252 ** 0.5, "why": [f"held {t}"]}
             for i, t in enumerate(HELD)]
    p = tmp / "funnel.json"
    p.write_text(json.dumps({"generated_at": stamp,
                             "evidence_basis": {"ranked_by": ["profitability_small"]},
                             "candidates": cands}), encoding="utf-8")
    return p


class ReplayBroker:
    def __init__(self, *, is_open: bool = True):
        self.is_open = is_open
        self.submitted: list[PB.PlannedOrder] = []

    def install(self, mp: pytest.MonkeyPatch) -> "ReplayBroker":
        snap = {"equity": STATE["equity"], "cash": STATE["cash"],
                "account_number": config.PC_PAPER_ACCOUNT_NUMBER,
                "n_positions": len(STATE["positions"]),
                "positions": [dict(p) for p in STATE["positions"]]}
        mp.setattr(PB, "snapshot", lambda **kw: snap)
        mp.setattr(PB, "last_prices", lambda syms: {s: float(STATE["prices"].get(s, 50.0))
                                                    for s in syms})
        mp.setattr(PB, "clock", lambda: {"is_open": self.is_open})
        mp.setattr(PB, "orders", lambda **kw: [])

        def _submit(plan, **kw):
            self.submitted.append(plan)
            return {"status": "submitted", "symbol": plan.symbol, "side": plan.side,
                    "qty": plan.qty, "notional": plan.notional, "reason": plan.reason}
        mp.setattr(PB, "submit", _submit)
        sig = dict(STATE["sigmas"])
        mp.setattr(PR, "panel_sigmas", lambda *a, **k: dict(sig))
        mp.setattr(S, "bars_gate", lambda *a, **k: {"stale": False, "line": "BARS_FRESH (replay)"})
        return self


def _set_flags(mp: pytest.MonkeyPatch, on: bool) -> None:
    for f in NEW_FLAGS:
        mp.setattr(config, f, on, raising=False)


def _replay(tmp: Path, mp: pytest.MonkeyPatch, *, on: bool, mode: str = "paper_profit",
            net: float = -0.2) -> tuple[dict, ReplayBroker]:
    _set_flags(mp, on)
    rb = ReplayBroker().install(mp)
    _funnel_held(tmp)
    _ranking(tmp / "out", net=net)
    S.u_plan(tmp / "out", mode, asof=ASOF, funnel_path=tmp / "funnel.json",
             ledger_path=tmp / "ledger.jsonl", contracts_dir=tmp / "decisions" / "pc_plan",
             bars_paths=[tmp / "bars.parquet"])
    rec = json.loads((tmp / "out" / "intended_book.json").read_text(encoding="utf-8"))
    return rec, rb


_PINNED = ("verdict", "acting", "exploit_acting", "probe_acting", "n_targets", "n_orders",
           "orders_by_state", "sendable_by_state", "n_to_send", "send_block", "turnover_usd",
           "book", "refusals", "probe_weights", "worst_case", "risk_gate_line", "equity")


def _pinned(rec: dict, rb: ReplayBroker) -> dict:
    out = {k: rec.get(k) for k in _PINNED}
    out["submitted"] = [[p.symbol, p.side, p.qty] for p in rb.submitted]
    out["new_keys_absent"] = sorted(k for k in ("benchmark_core", "revision_flow",
                                                "worst_case_owner_d14") if k in rec)
    return json.loads(json.dumps(out, default=str))


def test_flags_off_plan_is_the_pre_change_plan(tmp_path, monkeypatch):
    rec, rb = _replay(tmp_path, monkeypatch, on=False)
    got = _pinned(rec, rb)
    if not GOLDEN.exists():                       # captured ONCE, from the pre-change code
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True), encoding="utf-8")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert got == want


# ─────────────────────────────── flags ON ───────────────────────────────────

def _rf_stub(mp: pytest.MonkeyPatch) -> None:
    """The frozen book's names without reading this machine's store (one test
    below reads the real store)."""
    from backend.services import pc_sleeves as SL
    mp.setattr(SL, "load_revision_flow", lambda **kw: {
        "book_id": "cb8d492bb8bf9ade", "name": "revision_flow_v0",
        "frozen_utc": "2026-09-25T05:54:13+00:00", "asof": "2026-09-25",
        "tickers": list(RF_NAMES), "book_weight": 0.05, "licence": "PRODUCT_EXPERIMENT",
        "mechanism": "analyst revision flow", "source": "stub", "cross_check": "stub"})


def _final_weights(rec: dict, rb: ReplayBroker) -> dict:
    """Holdings after every submitted order fills at the replay price."""
    qty = {p["symbol"]: float(p["qty"]) for p in STATE["positions"]}
    for p in rb.submitted:
        qty[p.symbol] = qty.get(p.symbol, 0.0) + (p.qty if p.side == "buy" else -p.qty)
    eq = float(STATE["equity"])
    return {s: q * float(STATE["prices"].get(s, 50.0)) / eq for s, q in qty.items() if q}


def _plan(tmp: Path, mp: pytest.MonkeyPatch, *, funnel: Path | None = None,
          net: float = -0.2, symbols: list | None = None, is_open: bool = True) -> tuple:
    _set_flags(mp, True)
    rb = ReplayBroker(is_open=is_open).install(mp)
    f = funnel or _funnel_held(tmp)
    _ranking(tmp / "out", net=net, symbols=symbols)
    S.u_plan(tmp / "out", "paper_profit", asof=ASOF, funnel_path=f,
             ledger_path=tmp / "ledger.jsonl", contracts_dir=tmp / "decisions" / "pc_plan",
             bars_paths=[tmp / "bars.parquet"])
    return json.loads((tmp / "out" / "intended_book.json").read_text(encoding="utf-8")), rb


def test_the_shipped_owner_decision():
    from backend.tests.conftest import SHIPPED_OWNER_D14_FLAGS
    assert SHIPPED_OWNER_D14_FLAGS == {"PC_BENCHMARK_CORE": True,
                                       "PC_BENCHMARK_CORE_EXEMPT_FROM_NAME_CAP": True,
                                       "PC_SLEEVE_REVISION_FLOW": True,
                                       "PC_CONTRACT_COUNTS_PLAN_SLEEVES": True}
    assert config.PC_SLEEVE_REVISION_FLOW_GROSS == pytest.approx(0.60)
    assert config.PC_SLEEVE_REVISION_FLOW_BOOK_ID == "cb8d492bb8bf9ade"
    assert PB.MAX_NAME_FRAC == pytest.approx(0.12) and PB.MAX_INVESTED_FRAC == pytest.approx(1.0)


def test_flags_on_core_plus_sleeve_plus_probe_within_every_hard_limit(tmp_path, monkeypatch):
    _rf_stub(monkeypatch)
    rec, rb = _replay(tmp_path, monkeypatch, on=True)
    core, rf = rec["benchmark_core"], rec["revision_flow"]
    assert core["status"] == "CORE_EXEMPT_BY_OWNER_D22" and core["applied"]
    assert "CORE_EXEMPT_BY_OWNER_D22" in core["line"]
    assert rf["applied"] and rf["acting"] and len(rf["weights"]) == 20
    assert rf["weight_each"] == pytest.approx(0.60 / 20)
    assert rec["risk_gate"]["block"] is None
    want = 1.0 - core["active_gross"]
    assert core["want_weight"] == pytest.approx(want)
    assert core["weight_planned"] <= want - config.PC_BENCHMARK_CORE_CASH_BUFFER + 1e-9
    assert core["active_gross"] == pytest.approx(0.20 + 0.60, abs=1e-6)
    states: dict = {}
    for s in rec["sent"]:
        states.setdefault(s["state"], []).append(s["symbol"])
    assert sorted(states["REVISION_FLOW"]) == sorted(RF_NAMES)
    assert states["CORE"] == ["SPY"]
    assert all("REVISION_FLOW sleeve" in p.reason for p in rb.submitted if p.symbol in RF_NAMES)
    fw = _final_weights(rec, rb)
    assert sum(fw.values()) <= 1.0 + 1e-9, f"gross {sum(fw.values()):.4f}"
    assert sum(fw.values()) >= 0.95, "the owner's point: not cash"
    assert all(v <= PB.MAX_NAME_FRAC + 1e-9 for s, v in fw.items() if s != "SPY")
    assert fw["SPY"] > PB.MAX_NAME_FRAC
    assert all(v >= 0 for v in fw.values()), "long-only"
    wc = rec["worst_case_owner_d14"]
    assert wc["planned_passes"] is True and wc["planned_total_frac"] <= 0.10
    assert wc["planned_gross_over_equity"] <= 1.0 + 1e-9
    assert len(rec["worst_case_owner_d14_lines"]) == 3
    assert all("-$" in ln and "$-" not in ln for ln in rec["worst_case_owner_d14_lines"])
    assert rec["sendable_by_state"]["REVISION_FLOW"] == 20


def test_flags_on_leaves_the_probe_orders_identical(tmp_path, monkeypatch):
    _rf_stub(monkeypatch)
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    off, rb_off = _replay(tmp_path / "off", monkeypatch, on=False)
    on, rb_on = _replay(tmp_path / "on", monkeypatch, on=True)
    probe = set(HELD)
    assert [(p.symbol, p.side, p.qty) for p in rb_off.submitted if p.symbol in probe] == \
        [(p.symbol, p.side, p.qty) for p in rb_on.submitted if p.symbol in probe]


def test_observe_sends_nothing_with_flags_on(tmp_path, monkeypatch):
    _rf_stub(monkeypatch)
    rec, rb = _replay(tmp_path, monkeypatch, on=True, mode="observe")
    assert rb.submitted == [] and rec["revision_flow"]["acting"] is False


def test_a_mandate_disagreement_still_blocks_every_send(tmp_path, monkeypatch):
    _rf_stub(monkeypatch)
    from backend.services import decision_contract as DC
    monkeypatch.setattr(DC, "account_mandate", lambda *a, **k: {
        "status": "UNRECONCILED", "disagreements": ["BROKER_EQUITY_STALE: test"]})
    rec, rb = _replay(tmp_path, monkeypatch, on=True)
    assert rb.submitted == []
    assert rec["send_block"].startswith("MANDATE: BROKER_EQUITY_STALE")


def test_a_closed_venue_sends_nothing(tmp_path, monkeypatch):
    _rf_stub(monkeypatch)
    rec, rb = _plan(tmp_path, monkeypatch, is_open=False)
    assert rb.submitted == [] and "venue closed" in rec["send_block"]


def test_a_volatile_sleeve_is_scaled_never_a_limit_widened(tmp_path, monkeypatch):
    """Sleeve names at 10%/day: PROBE + sleeve over 10% -> the sleeve is scaled
    to fit (ranker EXPLOIT first, here not acting), the core shrinks, no block."""
    _rf_stub(monkeypatch)
    hot = {**STATE["sigmas"], **{s: 0.10 for s in RF_NAMES}}
    _set_flags(monkeypatch, True)
    ReplayBroker().install(monkeypatch)
    monkeypatch.setattr(PR, "panel_sigmas", lambda *a, **k: dict(hot))
    f = _funnel_held(tmp_path)
    _ranking(tmp_path / "out", net=-0.2)
    S.u_plan(tmp_path / "out", "paper_profit", asof=ASOF, funnel_path=f,
             ledger_path=tmp_path / "ledger.jsonl",
             contracts_dir=tmp_path / "decisions" / "pc_plan", bars_paths=[tmp_path / "b"])
    rec = json.loads((tmp_path / "out" / "intended_book.json").read_text(encoding="utf-8"))
    g = rec["risk_gate"]
    assert g["block"] is None and g["scale_revision_flow"] < 1.0
    assert g["after_frac"] <= 0.10 + 1e-9
    assert rec["benchmark_core"]["status"] == "CORE_SHRUNK_BY_WORST_CASE"
    assert rec["benchmark_core"]["exempt_from_name_cap"] is True
    assert "CORE_EXEMPT_BY_OWNER_D22" in rec["benchmark_core"]["line"]
    assert rec["worst_case_owner_d14"]["planned_total_frac"] <= 0.10 + 1e-6


def test_probe_alone_over_the_line_still_blocks(tmp_path, monkeypatch):
    _rf_stub(monkeypatch)
    f = _funnel_held(tmp_path)
    blob = json.loads(f.read_text(encoding="utf-8"))
    for c in blob["candidates"]:
        c["vol_annual"] = 3.0          # ~19%/day each: PROBE alone is over the line
    f.write_text(json.dumps(blob), encoding="utf-8")
    rec, rb = _plan(tmp_path, monkeypatch, funnel=f)
    assert rb.submitted == [] and "WORST CASE REFUSE" in rec["send_block"]


def test_an_acting_exploit_name_is_not_double_held(tmp_path, monkeypatch):
    _rf_stub(monkeypatch)
    from backend.services import expected_return as ER

    def _no_er(*a, **k):
        raise RuntimeError("test: no E[r] view")
    monkeypatch.setattr(ER, "build", _no_er)
    monkeypatch.setattr(S, "_blend_grade", lambda *a, **k: {
        "verdict": "MEASURED_POSITIVE", "may_trade": True, "why": "test"})
    rec, rb = _plan(tmp_path, monkeypatch, net=+0.05,
                    symbols=["AMD"] + [f"RK{i:02d}" for i in range(17)])
    assert "AMD" in rec["revision_flow"]["skipped_already_in_a_sleeve"]
    assert [x["symbol"] for x in rec["book"]].count("AMD") == 1
    assert {x["symbol"]: x["state"] for x in rec["book"]}["AMD"] == "EXPLOIT"
    assert sum(_final_weights(rec, rb).values()) <= 1.0 + 1e-9


# ─────────────────────────────── the frozen book ────────────────────────────

def test_the_real_frozen_book_matches_the_hack2_copy():
    from backend.services import pc_sleeves as SL
    b = SL.load_revision_flow(book_id="cb8d492bb8bf9ade",
                              contract_path=config.OPTIMUS_LEDGER_DIR / "paper_accounts"
                              / "fleet_manager" / "contracts" / "hack2_v2.json")
    assert sorted(b["tickers"]) == sorted(RF_NAMES)
    assert b["book_weight"] == pytest.approx(0.05)


def test_the_sleeve_refuses_when_the_ticker_sets_differ(tmp_path):
    from backend.services import pc_sleeves as SL
    books = tmp_path / "books.jsonl"
    books.write_text(json.dumps({"schema": "llm_portfolio/1", "name": "revision_flow_v0",
                                 "book_id": "abc", "positions": [
                                     {"ticker": t, "weight": 0.5} for t in ("AAA", "BBB")]})
                     + "\n", encoding="utf-8")
    c = tmp_path / "c.json"
    c.write_text(json.dumps({"selection": {"book_id": "abc", "positions": [
        {"ticker": "AAA"}, {"ticker": "CCC"}]}}), encoding="utf-8")
    with pytest.raises(SL.SleeveRefused, match="ticker sets differ"):
        SL.load_revision_flow(book_id="abc", books_path=books, contract_path=c)
    with pytest.raises(SL.SleeveRefused, match="not in the llm_portfolio store"):
        SL.load_revision_flow(book_id="zzz", books_path=books, contract_path=c)


def test_a_refused_book_plans_no_sleeve_and_the_core_takes_the_room(tmp_path, monkeypatch):
    from backend.services import pc_sleeves as SL

    def _refuse(**kw):
        raise SL.SleeveRefused("ticker sets differ: test")
    monkeypatch.setattr(SL, "load_revision_flow", _refuse)
    rec, rb = _replay(tmp_path, monkeypatch, on=True)
    assert rec["revision_flow"]["applied"] is False and "REFUSED" in rec["revision_flow_line"]
    assert not any(p.symbol in RF_NAMES for p in rb.submitted)
    assert sum(_final_weights(rec, rb).values()) <= 1.0 + 1e-9


def test_the_gross_rule_reproduces_sixty_percent():
    """The config value is the rule's answer on the fixture's sigmas with PROBE
    at its largest admissible (20% at the universe p90, 4.92% on 2026-10-06)."""
    from backend.services import pc_sleeves as SL
    sig = STATE["sigmas"]
    ch = SL.choose_gross(rf_names=RF_NAMES, probe_gross=config.PROBE_GROSS_CAP,
                         probe_sigma=0.049209219472656204, core_sigma=sig["SPY"], sigmas=sig,
                         k=config.PROBE_WORST_CASE_SIGMA,
                         limit=config.FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC, fallback=0.0492,
                         cash_buffer=0.01)
    assert ch["gross"] == pytest.approx(config.PC_SLEEVE_REVISION_FLOW_GROSS)


# ─────────────────────────────── D21: the contract counts the sleeves ────────

def _equity_read(core_frac: float, sleeve_frac: float) -> dict:
    eq = float(STATE["equity"])
    n = 20
    pos = [{"symbol": f"N{i}", "market_value": sleeve_frac / n * eq} for i in range(n)]
    if core_frac:
        pos.append({"symbol": "SPY", "market_value": core_frac * eq})
    return {"equity_usd": eq, "cash_usd": (1 - core_frac - sleeve_frac) * eq,
            "positions": pos, "as_of": "t"}


def test_d21_off_is_the_old_split(monkeypatch):
    from backend.services import decision_contract as DC
    monkeypatch.setattr(config, "PC_CONTRACT_COUNTS_PLAN_SLEEVES", False)
    assert DC.plan_sleeves_from_broker(_equity_read(0.0, 0.2)) is None
    old = DC.capital_resolution([], capital=1e6)
    assert old == DC.capital_resolution([], capital=1e6, plan_sleeves=None)
    assert "plan_sleeves_pct" not in old


def test_d21_counts_the_active_sleeve_and_reconciles_both_sides_of_tonight(monkeypatch):
    """Before tonight's orders (20% PROBE, 80% cash) and after them (80% sleeves,
    19% SPY core, 1% cash) the contract and the broker agree; before D21 the
    20% PROBE sleeve resolved to 0% and POSITIONS_DISAGREE was permanent."""
    from backend.services import decision_contract as DC
    monkeypatch.setattr(config, "PC_CONTRACT_COUNTS_PLAN_SLEEVES", True)
    for core, sleeves in ((0.0, 0.20), (0.19, 0.80)):
        er = _equity_read(core, sleeves)
        ps = DC.plan_sleeves_from_broker(er)
        assert "SPY" not in ps and sum(ps.values()) == pytest.approx(sleeves)
        res = DC.capital_resolution([], capital=er["equity_usd"], plan_sleeves=ps)
        assert res["plan_sleeves_pct"] == pytest.approx(sleeves)
        assert res["benchmark_pct"] == pytest.approx(1.0 - sleeves - config.IC_CASH_FLOOR_PCT)
        assert res["sums_to"] == pytest.approx(1.0) and "refused" not in res
        rec = DC.positions_reconciliation([], capital=er["equity_usd"], equity=er,
                                          resolution=res)
        assert rec["status"] == "OK", rec["disagreements"]
        monkeypatch.setattr(config, "PC_CONTRACT_COUNTS_PLAN_SLEEVES", False)
        old = DC.capital_resolution([], capital=er["equity_usd"],
                                    plan_sleeves=DC.plan_sleeves_from_broker(er))
        assert DC.positions_reconciliation([], capital=er["equity_usd"], equity=er,
                                           resolution=old)["status"] != "OK"
        monkeypatch.setattr(config, "PC_CONTRACT_COUNTS_PLAN_SLEEVES", True)
