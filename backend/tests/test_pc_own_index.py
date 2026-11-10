"""OD-10 (owner 2026-11-10): PC-PAPER makes its own index; SPY is the benchmark only.

Offline. Dates derive from now (protocol item 5). The broker is the replay fake
from test_pc_plan_replay_owner_d14.py; nothing here can reach a venue.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config
from backend.services import pc_broker as PB
from backend.services import pc_own_index as OI

NOW = datetime.now(timezone.utc)
ISSUERS = {"GOOGL": "cik-alphabet", "GOOG": "cik-alphabet"}


def _funnel(tmp: Path, tickers: list[str], *, age_days: float = 1.0,
            stamp: str | None = "derive", name: str = "funnel.json") -> Path:
    gen = ((NOW - timedelta(days=age_days)).isoformat(timespec="seconds")
           if stamp == "derive" else stamp)
    p = tmp / name
    p.write_text(json.dumps({"generated_at": gen, "candidates": [
        {"ticker": t, "score": 1.0 - i / 100.0, "median_dollar_vol": 5e9 - i,
         "vol_annual": 0.30} for i, t in enumerate(tickers)]}), encoding="utf-8")
    return p


def _frozen(folder: Path) -> dict:
    return OI.freeze(folder / OI.CONTRACT_FILE, now=NOW)


# ─────────────────────────── contract ───────────────────────────────────────

def test_contract_names_licence_inputs_costs_fills_objective_and_code():
    c = OI.contract_content()
    assert c["licence"] == "PRODUCT_EXPERIMENT"
    for k in ("inputs", "construction", "risk", "costs_and_fills", "objective", "code"):
        assert c[k], k
    assert "SPY" in c["inputs"]["excluded_symbols"]
    assert c["code"]["source_sha256"] == OI.source_sha256()
    assert OI.policy_hash(c) == OI.policy_hash(OI.contract_content())


def test_freeze_is_idempotent_and_a_changed_contract_refuses(tmp_path, monkeypatch):
    a = _frozen(tmp_path)
    assert _frozen(tmp_path)["policy_hash"] == a["policy_hash"]
    assert OI.load_frozen(tmp_path / OI.CONTRACT_FILE)["policy_hash"] == a["policy_hash"]
    monkeypatch.setattr(config, "PC_OWN_INDEX_N", 21)
    with pytest.raises(OI.OwnIndexRefused, match="changed since the freeze"):
        OI.load_frozen(tmp_path / OI.CONTRACT_FILE)
    with pytest.raises(OI.OwnIndexRefused, match="never rewritten"):
        _frozen(tmp_path)
    monkeypatch.setattr(config, "PC_OWN_INDEX_VERSION", "own_index_test_v2")
    b = _frozen(tmp_path)
    assert b["superseded"] == a["policy_hash"] and b["policy_hash"] != a["policy_hash"]


def test_no_frozen_contract_refuses(tmp_path):
    with pytest.raises(OI.OwnIndexRefused, match="no frozen contract"):
        OI.load_frozen(tmp_path / OI.CONTRACT_FILE)


# ─────────────────────────── candidates ─────────────────────────────────────

@pytest.mark.parametrize("kw,match", [
    ({"age_days": 11.0}, "STALE"),
    ({"stamp": None}, "CANNOT BE DETERMINED"),
    ({"stamp": "not a date"}, "CANNOT BE DETERMINED"),
])
def test_a_stale_or_undateable_candidate_file_refuses(tmp_path, kw, match):
    f = _funnel(tmp_path, ["AAA", "BBB"], **kw)
    with pytest.raises(OI.OwnIndexRefused, match=match):
        OI.read_candidates(f, now=NOW, issuer_of={})


def test_an_empty_or_missing_candidate_file_refuses(tmp_path):
    with pytest.raises(OI.OwnIndexRefused, match="EMPTY"):
        OI.read_candidates(_funnel(tmp_path, []), now=NOW, issuer_of={})
    with pytest.raises(OI.OwnIndexRefused, match="unreadable"):
        OI.read_candidates(tmp_path / "absent.json", now=NOW, issuer_of={})


def test_candidates_print_age_and_size_and_collapse_share_classes(tmp_path):
    info = OI.read_candidates(_funnel(tmp_path, ["GOOGL", "GOOG", "AAA"], age_days=2.0),
                              now=NOW, issuer_of=ISSUERS)
    assert info["n_raw"] == 3 and info["n_after_issuer_collapse"] == 2
    assert 1.9 < info["age_days"] < 2.1
    assert [r["ticker"] for r in info["rows"]] == ["GOOGL", "AAA"]


# ─────────────────────────── membership ─────────────────────────────────────

def test_membership_excludes_spy_and_other_sleeves_and_takes_top_n(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PC_OWN_INDEX_N", 3)
    c = _frozen(tmp_path)
    f = _funnel(tmp_path, ["SPY", "AAA", "RF1", "BBB", "QQQ", "CCC", "DDD"])
    row = OI.membership(tmp_path, contract=c, funnel_path=f, now=NOW, exclude={"RF1"},
                        issuer_of={})
    assert row["members"] == ["AAA", "BBB", "CCC"]
    assert {"SPY", "QQQ", "RF1"} <= set(row["excluded_skipped"])
    assert (tmp_path / OI.MEMBERS_FILE).exists()


def test_membership_is_held_for_the_period_then_rebuilt_from_a_fresh_file(tmp_path):
    c = _frozen(tmp_path)
    f = _funnel(tmp_path, ["AAA", "BBB"])
    OI.membership(tmp_path, contract=c, funnel_path=f, now=NOW, issuer_of={})
    stale = _funnel(tmp_path, ["ZZZ"], age_days=30, name="stale.json")
    held = OI.membership(tmp_path, contract=c, funnel_path=stale,
                         now=NOW + timedelta(days=2), issuer_of={})
    assert held["status"] == "HELD_MEMBERSHIP" and held["members"] == ["AAA", "BBB"]
    with pytest.raises(OI.OwnIndexRefused, match="STALE"):
        OI.membership(tmp_path, contract=c, funnel_path=stale,
                      now=NOW + timedelta(days=8), issuer_of={})
    fresh = _funnel(tmp_path, ["CCC"], age_days=-7.0, name="fresh.json")   # stamped NOW+7d
    row = OI.membership(tmp_path, contract=c, funnel_path=fresh,
                        now=NOW + timedelta(days=8), issuer_of={})
    assert row["status"] == "REBUILT" and row["members"] == ["CCC"]
    assert row["previous_members"] == ["AAA", "BBB"]


def test_a_dry_run_membership_writes_nothing(tmp_path):
    c = OI.contract_content()
    contract = {"content": c, "policy_hash": OI.policy_hash(c)}
    row = OI.membership(tmp_path, contract=contract, funnel_path=_funnel(tmp_path, ["AAA"]),
                        now=NOW, write=False, issuer_of={})
    assert row["status"] == "REBUILT_NOT_WRITTEN"
    assert not (tmp_path / OI.MEMBERS_FILE).exists()


# ─────────────────────────── sizing ─────────────────────────────────────────

def _choose(**kw):
    base = dict(names=[f"N{i}" for i in range(20)], n_declared=20, max_name_frac=0.03,
                room=0.63, other_weights={"RF": 0.30}, sigmas={}, fallback=0.02, k=3.0,
                day_limit=0.10, worst_21=-0.2935, window_limit=0.10, step=0.05)
    base.update(kw)
    return OI.choose_gross(**base)


def test_the_21_session_bound_shrinks_the_index_and_never_widens():
    pick = _choose()
    assert pick["declared_gross"] == pytest.approx(0.30)
    assert pick["gross"] * 0.2935 <= 0.10 and pick["binding"] == "worst_21_session"
    assert _choose(worst_21=None)["gross"] == 0.0, "an UNKNOWN bound fails"


def test_fewer_qualifying_names_leave_their_slots_in_cash():
    pick = _choose(names=["A", "B", "C", "D", "E"], worst_21=-0.10)
    assert pick["w_each"] == pytest.approx(0.03)           # G/N capped, never G/5
    assert pick["gross"] == pytest.approx(0.15)


def test_the_one_day_bound_binds_on_volatile_names():
    pick = _choose(sigmas={f"N{i}": 0.10 for i in range(20)}, worst_21=-0.05)
    assert pick["binding"] == "one_day_k_sigma"
    assert pick["book_k_sigma_frac"] <= 0.10 + 1e-12


# ─────────────────────────── the plan ───────────────────────────────────────

def _plan(tmp: Path, *, refusal: str | None = None, contract: bool = True, mode="paper_profit",
          claimed: set | None = None, held: dict | None = None):
    c = _frozen(tmp) if contract else None
    row = {"members": ["AAA", "BBB", "CCC"], "previous_members": ["OLD"],
           "frozen_utc": NOW.isoformat()}
    held = held if held is not None else {"SPY": 633.4, "AAA": 10.0, "OLD": 5.0, "XYZ": 7.0}
    prices = {"SPY": 700.0, "AAA": 100.0, "BBB": 50.0, "CCC": 25.0, "OLD": 10.0, "XYZ": 20.0}
    return OI.plan(contract=c, members_row=row, refusal=refusal, equity=1_000_000.0,
                   held=held, prices=prices, acting_weights={"RF1": 0.30},
                   claimed=claimed or {"RF1"}, held_residual={"XYZ": 0.0001},
                   sigmas={}, fallback_sigma=0.02, history={"worst_window_return": -0.25},
                   mode=mode)


def test_the_plan_sells_the_spy_core_whole_shares_and_never_buys_spy(tmp_path):
    res = _plan(tmp_path)
    spy = [p for p in res["plans"] if p.symbol == "SPY"]
    assert len(spy) == 1 and spy[0].side == "sell" and spy[0].qty == 633
    assert res["state_of"]["SPY"] == OI.CORE_EXIT_STATE
    assert res["core_exit"]["fractional_residual"] == pytest.approx(0.4)
    assert "SPY" not in res["weights"]
    assert all(p.side == "sell" for p in res["plans"] if p.symbol == "SPY")
    assert res["state_of"]["OLD"] == OI.EXIT_STATE, "a member that left is sold"
    assert "XYZ" not in res["state_of"], "a name no index rule owns is untouched"
    assert res["applied"] and res["acting"]
    assert all(w <= config.PC_OWN_INDEX_MAX_NAME_FRAC + 1e-12 for w in res["weights"].values())
    assert res["worst_case_lines"][0].startswith("LARGEST ADMISSIBLE own index")


def test_a_stale_candidate_set_buys_nothing_holds_members_and_still_retires_spy(tmp_path):
    res = _plan(tmp_path, refusal="candidate file funnel.json is 11.0 days old: STALE")
    assert res["refused"].endswith("STALE") and not res["applied"]
    assert [p.symbol for p in res["plans"]] == ["SPY"]
    assert res["state_of"]["AAA"] == OI.HOLD_STATE and res["state_of"]["OLD"] == OI.HOLD_STATE
    assert res["exit_acting"] is True
    assert "not a filler" in res["line"]


def test_no_valid_contract_moves_nothing_not_even_spy(tmp_path):
    res = _plan(tmp_path, contract=False, refusal="no frozen contract")
    assert res["plans"] == [] and not res["applied"]
    assert "SPY is not sold either" in res["line"]


def test_a_member_another_acting_sleeve_holds_is_skipped_and_its_slot_is_cash(tmp_path):
    res = _plan(tmp_path, claimed={"RF1", "BBB"})
    assert "BBB" not in res["weights"] and res["skipped_claimed"] == ["BBB"]
    assert res["n_slots_cash"] == config.PC_OWN_INDEX_N - 2


def test_observe_mode_plans_but_does_not_act(tmp_path):
    res = _plan(tmp_path, mode="observe")
    assert res["applied"] and not res["acting"] and not res["exit_acting"]


def test_post_fill_clip_cuts_index_buys_only(tmp_path):
    plans = [PB.PlannedOrder("AAA", "buy", 100, 10_000.0, "x", price=100.0),
             PB.PlannedOrder("RF1", "buy", 100, 10_000.0, "x", price=100.0)]
    cut = OI.clip_buys_to_post_fill_gross(
        plans, held={"HELD": 9_750.0}, prices={"HELD": 100.0, "AAA": 100.0, "RF1": 100.0},
        equity=1_000_000.0, sendable=lambda p: True, cash_buffer=0.01, clip_syms={"AAA"})
    assert cut and cut["cut_shares"] == {"AAA": 50}
    assert plans[1].qty == 100


# ─────────────────────────── through sim_run.u_plan ─────────────────────────

def _uplan(tmp: Path, mp: pytest.MonkeyPatch, *, own: bool, core: bool = False,
           funnel_age: float = 1.0, freeze: bool = True, spy_qty: float = 100.0):
    from backend.tests import test_pc_plan_replay_owner_d14 as R
    from backend.tests.test_u_plan_probe import ASOF, _ranking
    from scripts import sim_run as S
    extra = [{"symbol": "SPY", "qty": spy_qty, "market_value": spy_qty * 779.705,
              "current_price": 779.705}] if spy_qty else []
    rb = R.ReplayBroker(extra=extra).install(mp)
    R._rf_stub(mp)
    mp.setattr(config, "PC_SLEEVE_REVISION_FLOW", True)
    mp.setattr(config, "PC_BENCHMARK_CORE", core)
    mp.setattr(config, "PC_BENCHMARK_CORE_EXEMPT_FROM_NAME_CAP", core)
    mp.setattr(config, "PC_OWN_INDEX", own)
    mp.setattr(OI, "bound_history", lambda names, *a, **k: {
        "worst_window_return": -0.20, "worst_window_end": "2020-03-16", "window_sessions": 21,
        "worst_day_return": -0.08, "worst_day": "2020-03-12", "panel": "stub",
        "eligible": list(names), "short_history": []})
    # the funded-buy gate (review #89 R3): fills confirmed, the account re-read
    real_submit = PB.submit

    def _submit(plan, **kw):
        res = real_submit(plan, **kw)
        return {**res, "client_order_id": f"aegispc-t{len(rb.submitted):04d}"}
    mp.setattr(PB, "submit", _submit)
    mp.setattr(PB, "order_by_client_id", lambda coid: {"status": "filled"})
    mp.setattr(PB, "account", lambda: {"cash": str(R.STATE["cash"] + spy_qty * 779.705),
                                       "equity": str(R.STATE["equity"]),
                                       "long_market_value": "0"})
    mp.setattr(OI, "_sleep", lambda s: None)
    from backend.services import investment_committee as IC
    mp.setattr(IC, "issuer_map", lambda *a, **k: ({}, "stub"))
    folder = tmp / "decisions" / "pc_plan"
    if freeze:
        OI.freeze(folder / OI.CONTRACT_FILE)
    # ten held PROBE names first (the shortlist takes them), then five index-only names
    f = _funnel(tmp, R.HELD + ["IDX1", "IDX2", "SPY", "IDX3", "IDX4", "IDX5"],
                age_days=funnel_age)
    _ranking(tmp / "out", net=-0.2)
    try:
        S.u_plan(tmp / "out", "paper_profit", asof=ASOF, funnel_path=f,
                 ledger_path=tmp / "ledger.jsonl", contracts_dir=folder,
                 bars_paths=[tmp / "bars.parquet"])
    except OI.OwnIndexRefused:
        if freeze:
            raise
    rec = json.loads((tmp / "out" / "intended_book.json").read_text(encoding="utf-8"))
    return rec, rb


def test_flag_off_receipt_has_no_own_index_and_spy_is_not_touched(tmp_path, monkeypatch):
    rec, rb = _uplan(tmp_path, monkeypatch, own=False)
    assert "own_index" not in rec
    assert [p for p in rb.submitted if p.symbol == "SPY"] == []


def test_flag_on_sells_spy_buys_the_index_within_every_limit(tmp_path, monkeypatch):
    rec, rb = _uplan(tmp_path, monkeypatch, own=True)
    oi = rec["own_index"]
    assert oi["applied"] and oi["acting"], oi.get("line")
    sent = {(p.symbol, p.side) for p in rb.submitted}
    assert ("SPY", "sell") in sent and ("SPY", "buy") not in sent
    states = {s["symbol"]: s["state"] for s in rec["sent"]}
    assert states["SPY"] == "CORE_EXIT"
    idx = [s for s, st in states.items() if st == "OWN_INDEX"]
    assert set(idx) == {"IDX1", "IDX2", "IDX3", "IDX4", "IDX5"}, "acting PROBE keeps its names"
    assert "SPY" not in oi["weights"]
    assert oi["weights"] and all(w <= config.PC_OWN_INDEX_MAX_NAME_FRAC + 1e-12
                                 for w in oi["weights"].values())
    from backend.tests import test_pc_plan_replay_owner_d14 as R
    fw = R._final_weights(rec, rb)
    assert fw.get("SPY", 0.0) < 1e-9
    assert sum(fw.values()) <= 1.0 + 1e-9
    assert all(v <= PB.MAX_NAME_FRAC + 1e-9 for v in fw.values())
    assert rec["sendable_by_state"]["CORE_EXIT"] == 1
    assert rec["own_index_worst_case_lines"][0].startswith("LARGEST ADMISSIBLE")
    assert rec["own_index"].get("decisions") is not None, "OWN_INDEX decision rows are written"


def test_flag_on_with_a_stale_candidate_file_buys_no_index_and_never_spy(tmp_path, monkeypatch):
    rec, rb = _uplan(tmp_path, monkeypatch, own=True, funnel_age=30.0)
    oi = rec["own_index"]
    assert "STALE" in oi["refused"] and not oi["applied"]
    assert not any(s.get("state") == "OWN_INDEX" for s in rec["sent"])
    assert ("SPY", "buy") not in {(p.symbol, p.side) for p in rb.submitted}


def test_flag_on_without_a_frozen_contract_moves_nothing_at_all(tmp_path, monkeypatch):
    """Review #89 R2: no (or no matching) contract holds EVERY order, not only
    the index's, and the plan unit raises (red) after writing the receipt."""
    rec, rb = _uplan(tmp_path, monkeypatch, own=True, freeze=False)
    assert "no frozen contract" in rec["own_index"]["refused"]
    assert rb.submitted == [] and rec["sent"] == []
    assert "own index contract REFUSED" in rec["send_block"]


def test_core_and_own_index_both_on_refuses_the_index(tmp_path, monkeypatch):
    rec, rb = _uplan(tmp_path, monkeypatch, own=True, core=True)
    assert "both True" in rec["own_index"]["refused"]
    assert rec["benchmark_core"]["applied"]


# ─────────────────────────── the CLI dry-run ────────────────────────────────

def test_cli_dry_run_prints_orders_and_refuses_non_zero_on_a_stale_file(tmp_path, monkeypatch,
                                                                        capsys):
    from scripts import pc_own_index as CLI
    from backend.services import investment_committee as IC
    from backend.services import pc_risk as PR
    monkeypatch.setattr(IC, "issuer_map", lambda *a, **k: ({}, "stub"))
    monkeypatch.setattr(PR, "panel_sigmas", lambda *a, **k: {})
    monkeypatch.setattr(OI, "bound_history", lambda names, *a, **k: {"worst_window_return": -0.2})
    monkeypatch.setattr(CLI, "_last_closes", lambda bars, syms: {s: 50.0 for s in syms})
    snap = tmp_path / "state.json"
    snap.write_text(json.dumps({
        "t": NOW.isoformat(timespec="seconds"), "account_number": config.PC_PAPER_ACCOUNT_NUMBER,
        "equity": 1_000_000.0, "cash": 10_000.0, "long_market_value": 990_000.0,
        "positions": [{"symbol": "SPY", "qty": 1000, "market_value": 700_000.0,
                       "current_price": 700.0}]}), encoding="utf-8")
    rec = tmp_path / "rec.json"
    rec.write_text(json.dumps({"asof": "x", "revision_flow": {"acting": True, "weights_after_gate":
                                                               {"RF1": 0.29}}}), encoding="utf-8")
    args = ["dry-run", "--snapshot", str(snap), "--plan-receipt", str(rec),
            "--folder", str(tmp_path / "f"), "--bars", str(tmp_path / "bars.parquet")]
    rc = CLI.main(args + ["--funnel", str(_funnel(tmp_path, ["AAA", "BBB"]))])
    out = capsys.readouterr().out
    assert rc == 0 and "CORE_EXIT" in out and "sell   1000 SPY" in out
    assert "OWN_INDEX       buy" in out
    assert not (tmp_path / "f" / OI.MEMBERS_FILE).exists(), "a dry-run writes nothing"
    rc = CLI.main(args + ["--funnel", str(_funnel(tmp_path, ["AAA"], age_days=30,
                                                  name="old.json"))])
    out = capsys.readouterr().out
    assert rc == 2 and "REFUSED" in out and "SPY is never the filler" in out
