"""Dynamic exposure book family (CH-45): contracts, rules, PIT, store.

Synthetic fixtures only (a business-day range in the past, so nothing expires),
no network, no live data. The exchange calendar is injected.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config as _config
from backend.services.portfolio_intelligence import branch_population_rolling as R
from backend.services.portfolio_intelligence import dynamic_exposure_books as D

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / D.CONTRACTS_REL
CONTRACTS_V1 = ROOT / D.CONTRACTS_V1_REL
SPECS_V2 = ROOT / D.SPECS_V2_REL
DAYS = pd.bdate_range("2024-01-02", periods=330)
ANCHOR_I = 280
EARN_I = ANCHOR_I + 3            # the leader's earnings session (gap planted here)
SYMS = [f"S{i:02d}" for i in range(60)]


class FakeCal:
    def next_open_after(self, day):
        d = pd.Timestamp(day) + pd.offsets.BDay(1)
        return datetime.combine(d.date(), time(14, 30), tzinfo=timezone.utc)

    def close_of(self, day):
        return datetime.combine(pd.Timestamp(day).date(), time(21, 0), tzinfo=timezone.utc)


def make_bars(n_days: int = len(DAYS)) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    days = DAYS[:n_days]
    spy_r = rng.normal(0.0004, 0.01, len(days))
    spy_r[ANCHOR_I + 6: ANCHOR_I + 26] = -0.012          # a slide that puts QQQ under its SMA50
    rows = []
    spy = 400 * np.cumprod(1 + spy_r)
    qqq = 300 * np.cumprod(1 + 1.3 * spy_r + rng.normal(0, 0.003, len(days)))
    for d, c, q in zip(days, spy, qqq):
        rows.append(("SPY", d, c * 0.999, c, 5e7))
        rows.append(("QQQ", d, q * 0.999, q, 5e7))
    lead_r = 1.1 * spy_r + rng.normal(0, 0.01, len(days))
    lead = 150 * np.cumprod(1 + lead_r)
    for j, (d, c) in enumerate(zip(days, lead)):
        o = lead[j - 1] * 0.90 if j == EARN_I else c * 0.999     # a -10% opening gap on the earnings session
        rows.append(("AAPL", d, o, c, 4e7))
    for i, s in enumerate(SYMS):
        beta = 0.4 + 0.04 * i
        r = beta * spy_r + rng.normal(0.0003 * (i % 9 - 4), 0.006 + 0.0003 * i, len(days))
        px = 50 * np.cumprod(1 + r)
        vol = 3e6 if i < 45 else 1e5
        for d, c in zip(days, px):
            rows.append((s, d, c * 0.998, c, vol))
    return pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "volume"])


def earn() -> dict:
    out = {t: [] for t in _config.DYNAMIC_BOOK_LEADERS}
    out["AAPL"] = [DAYS[EARN_I - 63], DAYS[EARN_I]]
    return out


@pytest.fixture()
def synthetic(monkeypatch):
    monkeypatch.setattr(_config, "ROLLING_COHORT_ANCHOR", DAYS[ANCHOR_I].date().isoformat())
    monkeypatch.setattr(_config, "DYNAMIC_BOOK_LEADERS", ("AAPL",))     # the only leader with bars here
    bars = make_bars()
    sessions = R.bench_sessions(bars)
    specs, _ = R.load_specs(SPECS_V2)
    spec = next(s for s in specs["specifications"] if s["policy_id"] == _config.DYNAMIC_BOOK_BASE_POLICY_ID)
    return bars, sessions, spec


def cohort(bars, sessions, spec, i):
    d = sessions[i]
    market = R.market_features(bars, d)
    long_w, short, hh = D.base_book(spec, market)
    return {"cohort_id": d.date().isoformat(), "entry_session": sessions[i + 1].date().isoformat(),
            "long": long_w, "holdings_hash": hh, "backfilled": True}


# ─────────────────────────────── contracts ──────────────────────────────────

def test_contract_hashes_recompute():
    doc = json.loads(CONTRACTS.read_bytes())
    assert doc["schema"] == D.CONTRACTS_SCHEMA
    assert len(doc["contracts"]) == 3
    for c in doc["contracts"]:
        body = {k: v for k, v in c.items() if k != "contract_sha256"}
        assert D.digest(body) == c["contract_sha256"], c["contract_id"]
        assert c["license"] == "PRODUCT_EXPERIMENT"
        assert c["costs"]["stock_exposure_change_bps"] > 0 and c["costs"]["etf_hedge_change_bps"] > 0
    assert D.digest({k: v for k, v in doc.items() if k != "manifest_sha256"}) == doc["manifest_sha256"]
    assert {c["personality"] for c in doc["contracts"]} == set(D.PERSONALITIES)
    specs, _ = R.load_specs(SPECS_V2)
    assert set(D.verify_contracts(doc, specs)) == set(D.PERSONALITIES)


def test_v1_is_kept_byte_stable_and_superseded_by_v2():
    v1 = json.loads(CONTRACTS_V1.read_bytes())
    assert v1["manifest_sha256"] == D.CONTRACTS_V1_MANIFEST
    for c in v1["contracts"]:
        assert D.digest({k: v for k, v in c.items() if k != "contract_sha256"}) == c["contract_sha256"]
    v2 = json.loads(CONTRACTS.read_bytes())
    assert {c["contract_id"] for c in v2["contracts"]} == {f"DXB-{p}-v2" for p in D.PERSONALITIES}
    for c in v2["contracts"]:
        assert c["supersedes"]["manifest_sha256"] == v1["manifest_sha256"]
        assert "before any return was read" not in json.dumps(c)
        assert "ALREADY SEEN" in c["base_selection"]["why"]
    assert not ({c["contract_sha256"] for c in v1["contracts"]} & {c["contract_sha256"] for c in v2["contracts"]})


def test_an_edited_contract_is_refused():
    doc = json.loads(CONTRACTS.read_bytes())
    specs, _ = R.load_specs(SPECS_V2)
    doc["contracts"][1]["rule"]["gap_threshold"] = -0.04
    with pytest.raises(D.DynamicBookRefused, match="edited|no longer hashes"):
        D.verify_contracts(doc, specs)


def test_a_config_that_drifted_from_the_contract_is_refused(monkeypatch):
    doc = json.loads(CONTRACTS.read_bytes())
    specs, _ = R.load_specs(SPECS_V2)
    monkeypatch.setattr(_config, "DYNAMIC_BOOK_LEADER_SESSIONS", 3)
    with pytest.raises(D.DynamicBookRefused, match="NEW contract id"):
        D.verify_contracts(doc, specs)


def test_no_new_key_reaches_the_rolling_population_declaration():
    # rolling.config_snapshot binds every ROLLING_COHORT_* key; a new one would make the live
    # population refuse. The family's keys must stay outside that prefix.
    assert not [k for k in R.config_snapshot() if "DYNAMIC" in k]
    assert D.config_snapshot() and all(k.startswith("DYNAMIC_BOOK_") for k in D.config_snapshot())


# ─────────────────────────────── the rules ──────────────────────────────────

def test_balanced_cuts_exactly_the_five_sessions_after_the_gap(synthetic):
    bars, sessions, spec = synthetic
    ev = D.leader_events(bars, earn(), sessions)
    assert [(e["leader"], e["session"]) for e in ev] == [("AAPL", DAYS[EARN_I].date().isoformat())]
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, _ = D.compute_cohort(c, bars, sessions, earn(), horizon=126, through=sessions[-1])
    cut = {r["date"] for r in paths["balanced"] if r["exposure"] < 1}
    assert cut == set(sessions[EARN_I + 1: EARN_I + 6])
    assert all(r["exposure"] == _config.DYNAMIC_BOOK_LEADER_GROSS for r in paths["balanced"] if r["date"] in cut)
    assert all(r["exposure"] == 1.0 and r["hedge"] == 0.0 for r in paths["growth"])
    g = {r["date"]: r["nav"] for r in paths["growth"]}
    b = {r["date"]: r["nav"] for r in paths["balanced"]}
    first = min(cut)
    assert all(g[d] == b[d] for d in g if d < first)            # identical before the rule fires
    assert g[max(cut)] != b[max(cut)]


def test_books_are_identical_where_no_rule_fired(synthetic):
    bars, sessions, spec = synthetic
    i = EARN_I + 6                                               # entered after the cut window
    c = cohort(bars, sessions, spec, i)
    paths, _ = D.compute_cohort(c, bars, sessions, earn(), horizon=126, through=sessions[-1])
    assert [r["nav"] for r in paths["growth"]] == [r["nav"] for r in paths["balanced"]]


def test_preservation_hedges_only_below_the_sma_with_the_clipped_beta(synthetic):
    bars, sessions, spec = synthetic
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, ser = D.compute_cohort(c, bars, sessions, earn(), horizon=126, through=sessions[-1])
    rows = paths["preservation"]
    assert any(r["hedge"] > 0 for r in rows) and any(r["hedge"] == 0 for r in rows)
    qc = ser["q_close"]
    for r in rows:
        i = sessions.index(r["date"])
        hist = qc.iloc[:i].dropna()
        below = hist.iloc[-1] < hist.iloc[-50:].mean()
        assert (r["hedge"] > 0) == (below and r["beta_prev"] > 0)
        if r["hedge"] > 0:
            assert r["hedge"] == pytest.approx(min(3.0, max(0.0, r["beta_prev"])))
    # the first decision's beta is the pre-entry backcast on QQQ over 126 sessions
    y, x = ser["pre_book_ret"].to_numpy(), ser["pre_q_ret"].to_numpy()
    assert rows[0]["beta_prev"] == pytest.approx(np.polyfit(x[-126:], y[-126:], 1)[0])


def test_costs_are_charged_on_every_change_and_never_zero(synthetic):
    bars, sessions, spec = synthetic
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, _ = D.compute_cohort(c, bars, sessions, earn(), horizon=126, through=sessions[-1])
    b = paths["balanced"]
    k = next(j for j, r in enumerate(b) if r["exposure"] < 1)
    assert b[k]["rule_cost"] == pytest.approx(0.5 * _config.DYNAMIC_BOOK_COST_STOCK_BPS / 1e4)
    p = [r for r in paths["preservation"] if r["hedge"] > 0]
    assert all(r["rule_cost"] > 0 for r in p)                    # borrow accrues every hedged session


# ──────────────────────────────── PIT ───────────────────────────────────────

def test_no_decision_reads_a_bar_dated_on_or_after_its_session(synthetic):
    bars, sessions, spec = synthetic
    for i in (ANCHOR_I, ANCHOR_I + 5):
        c = cohort(bars, sessions, spec, i)
        res = D.pit_recheck(c, bars, sessions, earn(), horizon=40, through=sessions[-1])
        assert res["decisions_checked"] > 100 and res["differ"] == 0, res


def test_the_poison_check_catches_a_rule_that_reads_the_session_close(synthetic, monkeypatch):
    bars, sessions, spec = synthetic
    real = D.exposure_path

    def leaky(personality, **kw):
        rows = real(personality, **kw)
        if personality == "balanced":                            # reads its own session's return
            for r, b in zip(rows, kw["base_ret"]):
                r["exposure"] = 0.5 if b < 0 else 1.0
        return rows

    monkeypatch.setattr(D, "exposure_path", leaky)
    c = cohort(bars, sessions, spec, ANCHOR_I)
    res = D.pit_recheck(c, bars, sessions, earn(), horizon=20, through=sessions[-1])
    assert res["differ"] > 0


def test_a_row_whose_signal_is_not_before_its_session_is_refused():
    rows = [{"date": pd.Timestamp("2024-03-01"), "signal_asof": pd.Timestamp("2024-03-01"),
             "exposure": 1.0, "hedge": 0.0}]
    with pytest.raises(D.DynamicBookRefused, match="read data dated"):
        D.apply_path(rows, np.array([0.01]), np.array([0.0]))


# ──────────────────────────────── store ─────────────────────────────────────

def write_cache(root: Path, dates: dict, pulled: datetime) -> None:
    (root / "straddle_forward").mkdir(exist_ok=True)
    (root / D.EARNINGS_REL).write_text(json.dumps(
        {t: {"dates": [d.date().isoformat() for d in v], "pulled_utc": pulled.isoformat()}
         for t, v in dates.items()}), encoding="utf8")


def _data_root(tmp_path: Path, bars: pd.DataFrame, *, dates: dict | None = None,
               pulled: datetime | None = None) -> Path:
    root = tmp_path / "optimus"
    (root / "prices_2025_26").mkdir(parents=True, exist_ok=True)
    bars.to_parquet(root / R.BARS_REL, index=False)
    last = bars["date"].max()
    write_cache(root, earn() if dates is None else dates,
                pulled or datetime.combine(last.date(), time(23, 0), tzinfo=timezone.utc))
    (root / "potential_universe").mkdir(exist_ok=True)
    with (root / "potential_universe" / "2023-12-01.jsonl").open("w", encoding="utf8") as f:
        for i, s in enumerate(SYMS + ["AAPL"]):
            f.write(json.dumps({"symbol": s, "identity": {"sector": f"Sector{i % 6}"}}) + "\n")
    return root


def test_backfill_then_rerun_is_idempotent_and_flags_backfill(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    specs, _ = R.load_specs(SPECS_V2)
    cpath = tmp_path / "contracts.json"
    cpath.write_text(json.dumps(D.compile_contracts(frozen_utc="2024-01-01T00:00:00+00:00", specs=specs)),
                     encoding="utf8")
    root = _data_root(tmp_path, bars)
    out = tmp_path / "dxb"
    asof = sessions[ANCHOR_I + 30]
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    row = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=asof, now=now,
                calendar=FakeCal())
    assert row["born"] and row["paths_written"] > 0 and row["marks_written"] > 0
    m = D.stored_marks(out)
    assert set(m["personality"]) == set(D.PERSONALITIES) and m["backfilled"].all()
    assert not m["forward_evidence"].any()
    assert {"worst_case_usd", "beta_adj_excess", "max_drawdown", "sector_top1", "effective_bets"} <= set(m.columns)
    again = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=asof, now=now,
                  calendar=FakeCal())
    assert again["stored_rows_rechecked"] == row["paths_written"]
    assert again["born"] == [] and again["paths_written"] == 0 and again["marks_written"] == 0
    for p in (out / "cohorts").glob("dxb_cohort_*.json"):
        assert json.loads(p.read_bytes())["backfilled"] is True


def test_a_changed_config_under_the_same_out_is_refused(synthetic, tmp_path, monkeypatch):
    bars, sessions, spec = synthetic
    specs, _ = R.load_specs(SPECS_V2)
    cpath = tmp_path / "contracts.json"
    cpath.write_text(json.dumps(D.compile_contracts(frozen_utc="x", specs=specs)), encoding="utf8")
    root = _data_root(tmp_path, bars)
    out = tmp_path / "dxb"
    D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=sessions[ANCHOR_I + 8],
          now=datetime(2030, 1, 1, tzinfo=timezone.utc), calendar=FakeCal())
    monkeypatch.setattr(_config, "DYNAMIC_BOOK_REPORT_EQUITY_USD", 50_000.0)
    with pytest.raises(D.DynamicBookRefused, match="another config"):
        D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=sessions[ANCHOR_I + 8],
              now=datetime(2030, 1, 1, tzinfo=timezone.utc), calendar=FakeCal())


def test_step_births_a_forward_cohort_before_its_entry_opens(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    specs, _ = R.load_specs(SPECS_V2)
    cpath = tmp_path / "contracts.json"
    cpath.write_text(json.dumps(D.compile_contracts(frozen_utc="x", specs=specs)), encoding="utf8")
    d = sessions[ANCHOR_I + 10]                                  # a scheduled cohort date (cadence 5)
    root = _data_root(tmp_path, bars[bars["date"] <= d])
    now = datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc)
    row = D.run("step", data_root=root, out=tmp_path / "dxb", contracts_path=cpath, asof=d, now=now,
                calendar=FakeCal())
    assert row["born"] == [d.date().isoformat()] and row["rc"] == 0 and row["calendar_stale"] == {}
    rec = json.loads((tmp_path / "dxb" / "cohorts" / f"dxb_cohort_{d.date()}.json").read_bytes())
    assert rec["backfilled"] is False and rec["forward_evidence"] is True
    assert row["paths_written"] == 0                             # nothing marked before the entry session


def test_out_inside_the_data_root_is_refused(tmp_path):
    root = tmp_path / "optimus"
    root.mkdir()
    with pytest.raises(D.DynamicBookRefused):
        D.output_dir(root, root / "elsewhere")
    assert D.output_dir(root, None) == (root / "dynamic_books").resolve()


def test_a_missing_earnings_calendar_is_refused(tmp_path):
    with pytest.raises(D.DynamicBookRefused, match="earnings calendar"):
        D.load_earnings(tmp_path)


# ─────────────────────── review of PR #150: the forward path ───────────────────────

def _contracts(tmp_path):
    specs, _ = R.load_specs(SPECS_V2)
    cpath = tmp_path / "contracts.json"
    cpath.write_text(json.dumps(D.compile_contracts(frozen_utc="x", specs=specs)), encoding="utf8")
    return cpath


def _close(i, hours=0):
    return datetime.combine(DAYS[i].date(), time(21, 0), tzinfo=timezone.utc) + pd.Timedelta(hours=hours)


def test_a_calendar_fact_learned_late_never_acts_retroactively(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    early = {"AAPL": [DAYS[EARN_I - 63]]}                       # the report of EARN_I not yet in the cache
    # run 1 (declaring): through EARN_I-1, the cache does not know the EARN_I report
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[EARN_I - 1]], dates=early, pulled=_close(EARN_I - 1, 1))
    D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=DAYS[EARN_I - 1],
          now=_close(EARN_I - 1, 3), calendar=FakeCal())
    stored1 = pd.read_parquet(next((out / "paths").glob("part-*.parquet")))
    # run 2: the cache is re-pulled one hour after the reaction session's close
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[EARN_I]], pulled=_close(EARN_I, 1))
    r2 = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=DAYS[EARN_I],
               now=_close(EARN_I, 2), calendar=FakeCal())
    ev = [e for e in r2["leader_events"] if e["session"] == DAYS[EARN_I].date().isoformat()]
    assert len(ev) == 1 and ev[0]["status"] == "LEARNED_LATE"
    # run 3: ten sessions later
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[EARN_I + 10]], pulled=_close(EARN_I + 10, 1))
    r3 = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=DAYS[EARN_I + 10],
               now=_close(EARN_I + 10, 2), calendar=FakeCal())
    assert r3["stored_rows_differ"] == 0 and r3["stored_rows_rechecked"] > len(stored1)
    paths = pd.concat([pd.read_parquet(x) for x in sorted((out / "paths").glob("part-*.parquet"))])
    bal = paths[(paths["personality"] == "balanced") & (paths["cohort_id"] == DAYS[ANCHOR_I].date().isoformat())]
    cut = set(bal.loc[bal["exposure"] < 1, "date"])
    # EARN_I+1 was decided at the close of EARN_I, before the fact was recorded: never cut
    assert DAYS[EARN_I + 1].date().isoformat() not in cut
    assert cut == {DAYS[EARN_I + j].date().isoformat() for j in range(2, 6)}
    # the rows stored by run 1 are unchanged
    m = stored1.merge(paths, on=["contract_sha256", "cohort_id", "k"], suffixes=("_1", "_now"))
    assert len(m) == len(stored1) and (m["exposure_1"] == m["exposure_now"]).all() and (m["nav_1"] == m["nav_now"]).all()
    assert set(bal.loc[bal["date"] <= DAYS[EARN_I - 1].date().isoformat(), "calendar_observed"]) == {"unknown"}
    assert set(bal.loc[bal["date"] >= DAYS[EARN_I + 2].date().isoformat(), "calendar_observed"]) == {"recorded"}
    facts = [json.loads(x) for x in (out / D.FACTS_FILE).read_text(encoding="utf8").splitlines()]
    late = [f for f in facts if f["earnings_date"] == DAYS[EARN_I].date().isoformat()]
    assert len(late) == 1 and late[0]["baseline"] is False and late[0]["first_recorded_utc"] == _close(EARN_I, 2).isoformat()


def test_a_stored_row_that_no_longer_recomputes_is_refused(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[EARN_I + 8]])
    kw = dict(data_root=root, out=out, contracts_path=cpath, asof=DAYS[EARN_I + 8], now=_close(EARN_I + 8, 3),
              calendar=FakeCal())
    D.run("backfill", **kw)
    part = next((out / "paths").glob("part-*.parquet"))
    t = pd.read_parquet(part)
    t.loc[t.index[3], "nav"] = t.loc[t.index[3], "nav"] * 1.01
    t.to_parquet(part, index=False)
    with pytest.raises(D.DynamicBookRefused, match="differ from the recompute"):
        D.run("backfill", **kw)


def test_a_step_with_a_stale_leader_calendar_exits_non_zero_and_names_it(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath = _contracts(tmp_path)
    d = sessions[ANCHOR_I + 10]
    root = _data_root(tmp_path, bars[bars["date"] <= d], pulled=_close(ANCHOR_I + 8))   # pulled before d
    row = D.run("step", data_root=root, out=tmp_path / "dxb", contracts_path=cpath, asof=d,
                now=datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc), calendar=FakeCal())
    assert row["rc"] == 3 and row["action"] == "STALE_CALENDAR"
    assert "AAPL" in row["calendar_stale"] and "before the last session" in row["calendar_stale"]["AAPL"][0]
    old = D.leader_calendar_status({"AAPL": [pd.Timestamp("2024-01-02")]}, {"AAPL": pd.Timestamp("2024-06-01", tz="UTC")},
                                   now=datetime(2024, 5, 1, tzinfo=timezone.utc), last_session=pd.Timestamp("2024-04-30"))
    assert old["AAPL"]["status"] == "STALE" and "days old" in old["AAPL"]["why"][0]


def test_a_changed_rolling_config_or_code_version_is_refused(synthetic, tmp_path, monkeypatch):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[EARN_I + 4]])
    kw = dict(data_root=root, out=out, contracts_path=cpath, asof=DAYS[EARN_I + 4], now=_close(EARN_I + 4, 3),
              calendar=FakeCal())
    D.run("backfill", **kw)
    decl = json.loads((out / "declaration.json").read_bytes())
    assert decl["rolling_config"] == json.loads(json.dumps(R.config_snapshot(), default=list))
    with monkeypatch.context() as m:
        m.setattr(_config, "ROLLING_COHORT_RANDOM_CONTROLS", 9)
        with pytest.raises(D.DynamicBookRefused, match="rolling grading config"):
            D.run("backfill", **kw)
    monkeypatch.setattr(R, "code_version", lambda: "f" * 40)
    with pytest.raises(D.DynamicBookRefused, match="accept-code-version"):
        D.run("backfill", **kw)
    row = D.run("backfill", **kw, accept_code_version=True)
    assert row["code_note"] and row["stored_rows_differ"] == 0
    assert D.run("backfill", **kw)["code_note"] is None           # accepted once, journaled
