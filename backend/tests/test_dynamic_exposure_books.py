"""Dynamic exposure book family (CH-45): contracts, rules, PIT, store.

Synthetic fixtures only (a business-day range in the past, so nothing expires),
no network, no live data. The exchange calendar is injected; the forward catalyst
calendar is written by `forward_calendar.pull` itself with a fake vendor fetch, so
the books read the same snapshot, receipt and index files the live task writes.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config as _config
from backend.services import forward_calendar as FC
from backend.services.portfolio_intelligence import branch_population_rolling as R
from backend.services.portfolio_intelligence import dynamic_exposure_books as D

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / D.CONTRACTS_REL
CONTRACTS_V1 = ROOT / D.CONTRACTS_V1_REL
CONTRACTS_V2 = ROOT / D.CONTRACTS_V2_REL
SPECS_V2 = ROOT / D.SPECS_V2_REL
DAYS = pd.bdate_range("2024-01-02", periods=330)
ANCHOR_I = 280
EARN_I = ANCHOR_I + 3            # the leader's reaction session (a -10% opening gap planted here)
SYMS = [f"S{i:02d}" for i in range(60)]
#: byte pins (LF-normalised sha256) of the superseded contract files: never edited
V1_FILE_SHA = "d74cf3258ab1a7b79e53e6cf8858bfcfc2075919d29e7d50bd33befb02a7dcdc"
V2_FILE_SHA = "7285fd0ab8225b7d0eee6df26f00cc21d25224a13cdd79e5a2baa2d392d0bb89"


class FakeCal:
    """Business days, open 14:30Z, close 21:00Z, no holidays."""

    def next_open_after(self, day):
        d = pd.Timestamp(day) + pd.offsets.BDay(1)
        return datetime.combine(d.date(), time(14, 30), tzinfo=timezone.utc)

    def open_after(self, t):
        t = pd.Timestamp(t)
        d = t.tz_convert(None).normalize() if t.tzinfo else t.normalize()
        for _ in range(10):
            if d.weekday() < 5:
                o = datetime.combine(d.date(), time(14, 30), tzinfo=timezone.utc)
                if o > t.to_pydatetime():
                    return o
            d = d + pd.Timedelta(days=1)
        raise AssertionError("no open within 10 days")

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
        o = lead[j - 1] * 0.90 if j == EARN_I else c * 0.999     # a -10% opening gap on EARN_I
        rows.append(("AAPL", d, o, c, 4e7))
    for i, s in enumerate(SYMS):
        beta = 0.4 + 0.04 * i
        r = beta * spy_r + rng.normal(0.0003 * (i % 9 - 4), 0.006 + 0.0003 * i, len(days))
        px = 50 * np.cumprod(1 + r)
        vol = 3e6 if i < 45 else 1e5
        for d, c in zip(days, px):
            rows.append((s, d, c * 0.998, c, vol))
    return pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "volume"])


# ─────────────────────────── the forward calendar fixture ───────────────────────────

def day(i: int) -> pd.Timestamp:
    """DAYS[i], extended past the bars (business days)."""
    return DAYS[0] + pd.offsets.BDay(i)


def amc(i: int) -> datetime:
    """An after-close report on DAYS[i] (16:30 New York in winter)."""
    return datetime.combine(day(i).date(), time(21, 30), tzinfo=timezone.utc)


def bmo(i: int) -> datetime:
    """A before-open report on DAYS[i] (07:00 New York)."""
    return datetime.combine(day(i).date(), time(12, 0), tzinfo=timezone.utc)


def untimed(i: int) -> datetime:
    """The vendor's 'time not supplied' stamp: 00:00:00 UTC of the date."""
    return datetime.combine(day(i).date(), time(0, 0), tzinfo=timezone.utc)


def pull_at(i: int, hour: float = 10.5) -> datetime:
    return datetime.combine(day(i).date(), time(0, 0), tzinfo=timezone.utc) + timedelta(hours=hour)


def fc_pull(root: Path, at: datetime, quotes: dict) -> None:
    """One FULL_UNIVERSE forward-calendar pull at `at` through `forward_calendar.pull`.
    `quotes[ticker] = {"next": dt|None, "last": dt|None, "est": bool}`. A filler issuer
    with a date keeps the receipt's coverage shares OK."""
    q = {**quotes, "ZZZZ": {"next": at + timedelta(days=40)}}

    def fetch(symbols):
        out = {}
        for s in symbols:
            v = q.get(s) or {}
            row = {"symbol": s, "quoteType": "EQUITY", "isEarningsDateEstimate": bool(v.get("est", False))}
            if v.get("next") is not None:
                row["earningsTimestampStart"] = v["next"].timestamp()
            if v.get("last") is not None:
                row["earningsTimestamp"] = v["last"].timestamp()
            out[s] = row
        return out

    FC.pull(sorted(q), root, fetch=fetch, macro=False, now_fn=lambda: at, sleep_fn=lambda s: None,
            resume=False, scope=FC.FULL_UNIVERSE)


def default_calendar(root: Path, last_i: int) -> None:
    """AAPL's report announced well ahead (AMC on EARN_I-1, reaction EARN_I), pulled daily."""
    for i in range(max(ANCHOR_I - 3, 0), last_i + 1, 3):
        nxt = amc(EARN_I - 1) if i < EARN_I else amc(EARN_I + 63)
        last = amc(EARN_I - 64) if i < EARN_I else amc(EARN_I - 1)
        fc_pull(root, pull_at(i), {"AAPL": {"next": nxt, "last": last}})
    if (last_i - max(ANCHOR_I - 3, 0)) % 3:
        i = last_i
        nxt = amc(EARN_I - 1) if i < EARN_I else amc(EARN_I + 63)
        last = amc(EARN_I - 64) if i < EARN_I else amc(EARN_I - 1)
        fc_pull(root, pull_at(i), {"AAPL": {"next": nxt, "last": last}})


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
            "long": long_w, "holdings_hash": hh, "backfilled": True, "gross_long": float(sum(long_w.values()))}


def obs(leader: str, at: datetime, *, next_date=None, timing="AMC", event_utc=None, known=True,
        last=None, last_utc=None, conf="VENDOR_ANNOUNCED") -> dict:
    """One stored observation row, as `ingest_forward_calendar` writes it."""
    return {"schema": D.FACT_SCHEMA, "kind": "forward_calendar_observation", "leader": leader,
            "pull_id": f"fc_{at:%Y%m%dT%H%M%SZ}_000000", "observed_utc": at.isoformat(),
            "status": "DATE" if next_date else "NO_DATE", "next_date": next_date,
            "timing": timing if next_date else None, "event_utc": None if event_utc is None else event_utc.isoformat(),
            "event_time_known": bool(known and next_date), "confirmation": conf if next_date else None,
            "last_reported_date": last, "last_reported_utc": None if last_utc is None else last_utc.isoformat()}


def ahead(i_report: int = EARN_I - 1) -> list[dict]:
    """AAPL's AMC report on DAYS[i_report], announced ten sessions ahead."""
    at = pull_at(i_report - 10)
    return [obs("AAPL", at, next_date=DAYS[i_report].date().isoformat(), event_utc=amc(i_report))]


def dec_map(sessions):
    cal = FakeCal()
    return {s: pd.Timestamp(cal.close_of(s)) for s in sessions}


def compute(c, bars, sessions, observations, **kw):
    return D.compute_cohort(c, bars, sessions, observations, horizon=kw.pop("horizon", 126),
                            through=sessions[-1], decision_utc=dec_map(sessions), cal=FakeCal(), **kw)


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


def test_v3_states_the_cap_and_the_forward_calendar():
    doc = json.loads(CONTRACTS.read_bytes())
    by = {c["personality"]: c for c in doc["contracts"]}
    assert {c["contract_id"] for c in doc["contracts"]} == {f"DXB-{p}-v3" for p in D.PERSONALITIES}
    p = by["preservation"]["rule"]
    assert p["hedge_notional_cap"] == 1.0 and p["gross_cap"] == 2.0
    wc = p["worst_case_usd"]
    assert wc["v3"]["gross_admissible"] <= 2.0 and wc["v2_form"]["gross_admissible"] == pytest.approx(3.95)
    assert wc["v3"]["hedge_squeeze_usd"] == pytest.approx(-10_000) and wc["v3"]["longs_gap_usd"] == pytest.approx(-28_500)
    b = by["balanced"]["rule"]
    assert D.FORWARD_CALENDAR_REL in b["earnings_dates"] and "CLOSE of the report date" in b["reaction_session"]
    assert "LEARNED_LATE" in b["calendar_observation"] and "MOVED" in b["calendar_observation"]
    assert all(D.EARNINGS_REL not in x for x in by["growth"]["inputs"])


def test_v1_and_v2_are_kept_byte_stable_and_superseded_by_v3():
    assert D.contracts_file_sha(CONTRACTS_V1) == V1_FILE_SHA
    assert D.contracts_file_sha(CONTRACTS_V2) == V2_FILE_SHA
    v1 = json.loads(CONTRACTS_V1.read_bytes())
    v2 = json.loads(CONTRACTS_V2.read_bytes())
    assert v1["manifest_sha256"] == D.CONTRACTS_V1_MANIFEST and v2["manifest_sha256"] == D.CONTRACTS_V2_MANIFEST
    for doc in (v1, v2):
        assert D.digest({k: v for k, v in doc.items() if k != "manifest_sha256"}) == doc["manifest_sha256"]
        for c in doc["contracts"]:
            assert D.digest({k: v for k, v in c.items() if k != "contract_sha256"}) == c["contract_sha256"]
    v3 = json.loads(CONTRACTS.read_bytes())
    for c in v3["contracts"]:
        assert c["supersedes"]["file"] == D.CONTRACTS_V2_REL
        assert c["supersedes"]["manifest_sha256"] == v2["manifest_sha256"]
        assert "BEFORE any forward decision" in c["supersedes"]["why"]
        assert c["supersedes"]["chain"][0]["manifest_sha256"] == v1["manifest_sha256"]
    hashes = [{c["contract_sha256"] for c in d["contracts"]} for d in (v1, v2, v3)]
    assert not (hashes[0] & hashes[2]) and not (hashes[1] & hashes[2])
    specs, _ = R.load_specs(SPECS_V2)
    with pytest.raises(D.DynamicBookRefused):          # v2 no longer equals the code in force
        D.verify_contracts(v2, specs)


def test_an_edited_contract_is_refused():
    doc = json.loads(CONTRACTS.read_bytes())
    specs, _ = R.load_specs(SPECS_V2)
    doc["contracts"][2]["rule"]["hedge_notional_cap"] = 3.0
    with pytest.raises(D.DynamicBookRefused, match="edited|no longer hashes"):
        D.verify_contracts(doc, specs)


def test_a_config_that_drifted_from_the_contract_is_refused(monkeypatch):
    doc = json.loads(CONTRACTS.read_bytes())
    specs, _ = R.load_specs(SPECS_V2)
    monkeypatch.setattr(_config, "DYNAMIC_BOOK_HEDGE_NOTIONAL_CAP", 1.5)
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
    facts = D.leader_facts(ahead(), cal=FakeCal())
    ev = D.leader_events(bars, facts, sessions)
    assert [(e["leader"], e["session"], e["fires"]) for e in ev] == [("AAPL", DAYS[EARN_I].date().isoformat(), True)]
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, _ = compute(c, bars, sessions, ahead())
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
    c = cohort(bars, sessions, spec, EARN_I + 6)                 # entered after the cut window
    paths, _ = compute(c, bars, sessions, ahead())
    assert [r["nav"] for r in paths["growth"]] == [r["nav"] for r in paths["balanced"]]


def test_preservation_hedges_only_below_the_sma_with_the_capped_beta(synthetic):
    bars, sessions, spec = synthetic
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, ser = compute(c, bars, sessions, [])
    rows = paths["preservation"]
    assert any(r["hedge"] > 0 for r in rows) and any(r["hedge"] == 0 for r in rows)
    qc = ser["q_close"]
    for r in rows:
        i = sessions.index(r["date"])
        hist = qc.iloc[:i].dropna()
        below = hist.iloc[-1] < hist.iloc[-50:].mean()
        assert (r["hedge"] > 0) == (below and r["beta_prev"] > 0)
        if r["hedge"] > 0:
            assert r["hedge"] == pytest.approx(min(3.0, max(0.0, r["beta_prev"]), 1.0, 2.0 - c["gross_long"]))
    y, x = ser["pre_book_ret"].to_numpy(), ser["pre_q_ret"].to_numpy()
    assert rows[0]["beta_prev"] == pytest.approx(np.polyfit(x[-126:], y[-126:], 1)[0])


def test_preservation_gross_never_exceeds_two_on_random_beta_paths():
    """Property: for random book/QQQ paths whose beta ranges 0..6, every decision's
    gross (stock exposure x gross long + hedge) is <= 2.0 under v3, while the v2 form
    exceeds it on some paths (the check is not vacuous)."""
    sessions = list(pd.bdate_range("2023-01-02", periods=400))
    worst_v3 = worst_v2 = 0.0
    n_checked = 0
    for seed in range(60):
        rng = np.random.default_rng(1000 + seed)
        q_ret = rng.normal(-0.002, 0.012, len(sessions))            # a falling QQQ: below its SMA often
        beta = rng.uniform(0.0, 6.0)
        book = beta * q_ret + rng.normal(0, rng.uniform(0.001, 0.03), len(sessions))
        q_close = pd.Series(300 * np.cumprod(1 + q_ret), index=sessions)
        i0 = 200
        days = sessions[i0: i0 + 120]
        gross_long = float(rng.uniform(0.5, 1.0))
        pre_b = pd.Series(book[i0 - 126: i0], index=sessions[i0 - 126: i0])
        pre_q = pd.Series(q_ret[i0 - 126: i0], index=sessions[i0 - 126: i0])
        for capped in (True, False):
            rows = D.exposure_path("preservation", days=days, sessions=sessions, base_ret=book[i0: i0 + 120],
                                   q_ret=q_ret[i0: i0 + 120], q_close=q_close, pre_book_ret=pre_b,
                                   pre_q_ret=pre_q, events=[], decision_utc=None, gross_long=gross_long,
                                   hedge_capped=capped)
            g = max(r["exposure"] * gross_long + r["hedge"] for r in rows)
            if capped:
                worst_v3 = max(worst_v3, g)
                assert all(0.0 <= r["hedge"] <= 1.0 for r in rows)
                n_checked += len(rows)
            else:
                worst_v2 = max(worst_v2, g)
    assert worst_v3 <= 2.0 + 1e-12 and n_checked >= 60 * 120
    assert worst_v2 > 2.0


def test_costs_are_charged_on_every_change_and_never_zero(synthetic):
    bars, sessions, spec = synthetic
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, _ = compute(c, bars, sessions, ahead())
    b = paths["balanced"]
    k = next(j for j, r in enumerate(b) if r["exposure"] < 1)
    assert b[k]["rule_cost"] == pytest.approx(0.5 * _config.DYNAMIC_BOOK_COST_STOCK_BPS / 1e4)
    p = [r for r in paths["preservation"] if r["hedge"] > 0]
    assert all(r["rule_cost"] > 0 for r in p)                    # borrow accrues every hedged session


# ───────────────────────── report timing and the calendar ─────────────────────────

@pytest.mark.parametrize("label,report,known,est,reaction_i,fires", [
    ("after close the day before", amc(EARN_I - 1), True, False, EARN_I, True),
    ("before open the same day", bmo(EARN_I), True, False, EARN_I, True),
    ("after close the same day", amc(EARN_I), True, False, EARN_I + 1, False),
    ("time not stated, the day before", untimed(EARN_I - 1), False, False, EARN_I, True),
    ("time not stated, the same day: taken at its close", untimed(EARN_I), False, False, EARN_I + 1, False),
    ("vendor estimate with a time: the time is not information", bmo(EARN_I), True, True, EARN_I + 1, False),
])
def test_before_open_and_after_close_timing(synthetic, tmp_path, label, report, known, est, reaction_i, fires):
    """The reaction session is the first session whose open is after the report; an
    unstated time (or an estimate) is taken at the close of its date. The gap read is
    always of a session whose open follows the event, so no price before it is used."""
    bars, sessions, spec = synthetic
    root = tmp_path / "optimus"
    fc_pull(root, pull_at(EARN_I - 8), {"AAPL": {"next": report, "est": est}})
    out = tmp_path / "dxb"
    out.mkdir()
    ing = D.ingest_forward_calendar(out, root, now=pull_at(EARN_I - 7), run_id="t")
    assert ing["appended"] == 1
    o = ing["observations"][0]
    assert o["event_time_known"] is (known and not est)
    facts = D.leader_facts(ing["observations"], cal=FakeCal())
    assert len(facts) == 1 and facts[0]["reaction_session"] == DAYS[reaction_i].date().isoformat(), label
    f = facts[0]
    t_event = pd.Timestamp(f["event_utc_assumed"])
    assert pd.Timestamp(FakeCal().open_after(t_event)) > t_event
    ev = D.leader_events(bars, facts, sessions)
    assert len(ev) == 1 and ev[0]["fires"] is fires
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, _ = compute(c, bars, sessions, ing["observations"])
    cut = {r["date"] for r in paths["balanced"] if r["exposure"] < 1}
    assert cut == (set(sessions[reaction_i + 1: reaction_i + 6]) if fires else set())


def _contracts(tmp_path):
    specs, _ = R.load_specs(SPECS_V2)
    cpath = tmp_path / "contracts.json"
    if not cpath.is_file():
        cpath.write_text(json.dumps(D.compile_contracts(frozen_utc="x", specs=specs)), encoding="utf8")
    return cpath


def _close(i, hours=0):
    return datetime.combine(DAYS[i].date(), time(21, 0), tzinfo=timezone.utc) + pd.Timedelta(hours=hours)


def _bars_root(tmp_path: Path, bars: pd.DataFrame) -> Path:
    root = tmp_path / "optimus"
    (root / "prices_2025_26").mkdir(parents=True, exist_ok=True)
    bars.to_parquet(root / R.BARS_REL, index=False)
    (root / "potential_universe").mkdir(exist_ok=True)
    with (root / "potential_universe" / "2023-12-01.jsonl").open("w", encoding="utf8") as f:
        for i, s in enumerate(SYMS + ["AAPL"]):
            f.write(json.dumps({"symbol": s, "identity": {"sector": f"Sector{i % 6}"}}) + "\n")
    return root


def _data_root(tmp_path: Path, bars: pd.DataFrame, *, calendar: bool = True) -> Path:
    root = _bars_root(tmp_path, bars)
    if calendar and not (root / D.FORWARD_CALENDAR_REL).is_dir():
        last_i = int(DAYS.get_loc(bars["date"].max()))
        default_calendar(root, last_i)
    return root


def _paths(out):
    return pd.concat([pd.read_parquet(x) for x in sorted((out / "paths").glob("part-*.parquet"))])


def _run_through(tmp_path, bars, i, out, cpath, *, hours=2, mode="backfill"):
    root = _bars_root(tmp_path, bars[bars["date"] <= DAYS[i]])
    return D.run(mode, data_root=root, out=out, contracts_path=cpath, asof=DAYS[i], now=_close(i, hours),
                 calendar=FakeCal())


def test_an_announced_date_observed_before_the_event_fires_on_time(synthetic, tmp_path):
    """Three forward runs; the report was announced ten sessions ahead: the cut starts at
    the first session after the reaction close, and no stored row ever changes."""
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    root = _bars_root(tmp_path, bars)
    fc_pull(root, pull_at(EARN_I - 10), {"AAPL": {"next": amc(EARN_I - 1), "last": amc(EARN_I - 64)}})
    fc_pull(root, pull_at(EARN_I + 1), {"AAPL": {"next": amc(EARN_I + 62), "last": amc(EARN_I - 1)}})
    _run_through(tmp_path, bars, EARN_I - 1, out, cpath)
    stored1 = _paths(out)
    r2 = _run_through(tmp_path, bars, EARN_I, out, cpath)
    ev = [e for e in r2["leader_events"] if e["session"] == DAYS[EARN_I].date().isoformat()]
    assert len(ev) == 1 and ev[0]["status"] == "ON_TIME" and ev[0]["announced_before_event"] is True
    r3 = _run_through(tmp_path, bars, EARN_I + 10, out, cpath)
    assert r3["stored_rows_differ"] == 0
    p = _paths(out)
    bal = p[(p["personality"] == "balanced") & (p["cohort_id"] == DAYS[ANCHOR_I].date().isoformat())]
    assert set(bal.loc[bal["exposure"] < 1, "date"]) == {DAYS[EARN_I + j].date().isoformat() for j in range(1, 6)}
    assert set(bal["calendar_observed"]) == {"forward_calendar"}
    m = stored1.merge(p, on=["contract_sha256", "cohort_id", "k"], suffixes=("_1", "_now"))
    assert len(m) == len(stored1) and (m["nav_1"] == m["nav_now"]).all()
    facts = [json.loads(x) for x in (out / D.FACTS_FILE).read_text(encoding="utf8").splitlines()]
    assert {f["observed_utc"] for f in facts} == {pull_at(EARN_I - 10).isoformat(), pull_at(EARN_I + 1).isoformat()}
    assert all(f["schema"] == D.FACT_SCHEMA and "forward_calendar" in f["source"] for f in facts)
    assert len(facts) == 2                                       # each pull recorded once across three runs


def test_a_date_observed_after_the_event_is_learned_late_and_never_cuts_retroactively(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    root = _bars_root(tmp_path, bars)
    # before the event the calendar names no next date (only the previous report)
    fc_pull(root, pull_at(EARN_I - 10), {"AAPL": {"last": amc(EARN_I - 64)}})
    # the report is first seen the morning after its reaction session's close
    fc_pull(root, pull_at(EARN_I + 1), {"AAPL": {"last": amc(EARN_I - 1)}})
    _run_through(tmp_path, bars, EARN_I, out, cpath)
    stored1 = _paths(out)
    r2 = _run_through(tmp_path, bars, EARN_I + 1, out, cpath)
    ev = [e for e in r2["leader_events"] if e["session"] == DAYS[EARN_I].date().isoformat()]
    assert len(ev) == 1 and ev[0]["status"] == "LEARNED_LATE" and ev[0]["announced_before_event"] is False
    r3 = _run_through(tmp_path, bars, EARN_I + 10, out, cpath)
    assert r3["stored_rows_differ"] == 0 and r3["stored_rows_rechecked"] > len(stored1)
    p = _paths(out)
    bal = p[(p["personality"] == "balanced") & (p["cohort_id"] == DAYS[ANCHOR_I].date().isoformat())]
    cut = set(bal.loc[bal["exposure"] < 1, "date"])
    # EARN_I+1 was decided at the close of EARN_I, before the fact was observed: never cut
    assert DAYS[EARN_I + 1].date().isoformat() not in cut
    assert cut == {DAYS[EARN_I + j].date().isoformat() for j in range(2, 6)}
    m = stored1.merge(p, on=["contract_sha256", "cohort_id", "k"], suffixes=("_1", "_now"))
    assert len(m) == len(stored1) and (m["exposure_1"] == m["exposure_now"]).all() and (m["nav_1"] == m["nav_now"]).all()


def test_a_moved_date_acts_only_where_it_was_believed(synthetic):
    bars, sessions, spec = synthetic
    c = cohort(bars, sessions, spec, ANCHOR_I)
    d0, d_late = day(EARN_I - 1).date().isoformat(), day(EARN_I + 20).date().isoformat()
    # announced for EARN_I-1 (would fire on EARN_I), then moved three weeks later before the event
    moved_away = [obs("AAPL", pull_at(EARN_I - 12), next_date=d0, event_utc=amc(EARN_I - 1)),
                  obs("AAPL", pull_at(EARN_I - 3), next_date=d_late, event_utc=amc(EARN_I + 20))]
    facts = {f["earnings_date"]: f for f in D.leader_facts(moved_away, cal=FakeCal())}
    ev = {e["earnings_date"]: e for e in D.leader_events(bars, list(facts.values()), sessions)}
    assert ev[d0]["fires"] and D.event_status(ev[d0], dec_map(sessions)) == "MOVED"
    paths, _ = compute(c, bars, sessions, moved_away)
    assert not [r for r in paths["balanced"] if r["exposure"] < 1]
    # announced late in the quarter, then moved EARLIER to EARN_I-1 before it happened: fires on time
    moved_in = [obs("AAPL", pull_at(EARN_I - 12), next_date=d_late, event_utc=amc(EARN_I + 20)),
                obs("AAPL", pull_at(EARN_I - 3), next_date=d0, event_utc=amc(EARN_I - 1))]
    paths, _ = compute(c, bars, sessions, moved_in)
    assert {r["date"] for r in paths["balanced"] if r["exposure"] < 1} == set(sessions[EARN_I + 1: EARN_I + 6])


# ──────────────────────────────── PIT ───────────────────────────────────────

def test_no_decision_reads_a_bar_or_a_calendar_fact_from_after_it(synthetic):
    bars, sessions, spec = synthetic
    late = [obs("AAPL", pull_at(EARN_I + 2), last=DAYS[EARN_I - 1].date().isoformat(), last_utc=amc(EARN_I - 1))]
    for i, o in ((ANCHOR_I, ahead()), (ANCHOR_I + 2, late)):
        c = cohort(bars, sessions, spec, i)
        res = D.pit_recheck(c, bars, sessions, o, horizon=40, through=sessions[-1], decision_utc=dec_map(sessions),
                            cal=FakeCal())
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
    res = D.pit_recheck(c, bars, sessions, ahead(), horizon=20, through=sessions[-1],
                        decision_utc=dec_map(sessions), cal=FakeCal())
    assert res["differ"] > 0


def test_the_poison_check_catches_a_rule_that_acts_before_the_observation(synthetic, monkeypatch):
    bars, sessions, spec = synthetic
    late = [obs("AAPL", pull_at(EARN_I + 3), last=DAYS[EARN_I - 1].date().isoformat(), last_utc=amc(EARN_I - 1))]
    c = cohort(bars, sessions, spec, ANCHOR_I)
    kw = dict(horizon=30, through=sessions[-1], decision_utc=dec_map(sessions), cal=FakeCal())
    assert D.pit_recheck(c, bars, sessions, late, **kw)["differ"] == 0
    monkeypatch.setattr(D, "believed", lambda fact, decision: True)      # ignores the observation stamp
    assert D.pit_recheck(c, bars, sessions, late, **kw)["differ"] > 0


def test_a_row_whose_signal_is_not_before_its_session_is_refused():
    rows = [{"date": pd.Timestamp("2024-03-01"), "signal_asof": pd.Timestamp("2024-03-01"),
             "exposure": 1.0, "hedge": 0.0}]
    with pytest.raises(D.DynamicBookRefused, match="read data dated"):
        D.apply_path(rows, np.array([0.01]), np.array([0.0]))


# ──────────────────────────────── store ─────────────────────────────────────

def test_backfill_then_rerun_is_idempotent_and_flags_backfill(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath = _contracts(tmp_path)
    asof = sessions[ANCHOR_I + 30]
    root = _data_root(tmp_path, bars[bars["date"] <= asof])
    out = tmp_path / "dxb"
    now = _close(ANCHOR_I + 30, 2)
    row = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=asof, now=now, calendar=FakeCal())
    assert row["born"] and row["paths_written"] > 0 and row["marks_written"] > 0
    m = D.stored_marks(out)
    assert set(m["personality"]) == set(D.PERSONALITIES) and m["backfilled"].all()
    assert not m["forward_evidence"].any()
    assert {"worst_case_usd", "beta_adj_excess", "max_drawdown", "sector_top1", "effective_bets"} <= set(m.columns)
    pres = m[m["personality"] == "preservation"]
    assert (pres["gross_notional_max"] <= 2.0).all() and (pres["gross_notional_admissible"] <= 2.0).all()
    assert (pres["squeeze_usd_admissible"] >= -10_000 - 1e-6).all()
    again = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=asof, now=now, calendar=FakeCal())
    assert again["stored_rows_rechecked"] == row["paths_written"]
    assert again["born"] == [] and again["paths_written"] == 0 and again["marks_written"] == 0
    assert again["forward_calendar"]["observations_appended"] == 0
    for p in (out / "cohorts").glob("dxb_cohort_*.json"):
        assert json.loads(p.read_bytes())["backfilled"] is True


def test_a_changed_config_under_the_same_out_is_refused(synthetic, tmp_path, monkeypatch):
    bars, sessions, spec = synthetic
    cpath = _contracts(tmp_path)
    root = _data_root(tmp_path, bars[bars["date"] <= sessions[ANCHOR_I + 8]])
    out = tmp_path / "dxb"
    kw = dict(data_root=root, out=out, contracts_path=cpath, asof=sessions[ANCHOR_I + 8],
              now=_close(ANCHOR_I + 8, 2), calendar=FakeCal())
    D.run("backfill", **kw)
    monkeypatch.setattr(_config, "DYNAMIC_BOOK_BETS_WINDOW", 21)        # report-only: not in a rule
    with pytest.raises(D.DynamicBookRefused, match="another config"):
        D.run("backfill", **kw)


def test_step_births_a_forward_cohort_before_its_entry_opens(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath = _contracts(tmp_path)
    d = sessions[ANCHOR_I + 10]                                  # a scheduled cohort date (cadence 5)
    root = _data_root(tmp_path, bars[bars["date"] <= d])
    now = datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc)
    row = D.run("step", data_root=root, out=tmp_path / "dxb", contracts_path=cpath, asof=d, now=now,
                calendar=FakeCal())
    assert row["born"] == [d.date().isoformat()] and row["rc"] == 0 and row["calendar_stale"] == {}
    assert row["leader_calendar"]["AAPL"]["state"] == "SCHEDULED"         # next report ~56 sessions out
    rec = json.loads((tmp_path / "dxb" / "cohorts" / f"dxb_cohort_{d.date()}.json").read_bytes())
    assert rec["backfilled"] is False and rec["forward_evidence"] is True
    assert row["paths_written"] == 0                             # nothing marked before the entry session


def test_out_inside_the_data_root_is_refused(tmp_path):
    root = tmp_path / "optimus"
    root.mkdir()
    with pytest.raises(D.DynamicBookRefused):
        D.output_dir(root, root / "elsewhere")
    assert D.output_dir(root, None) == (root / "dynamic_books").resolve()


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


# ─────────────────────────── STALE and UNSCHEDULED ───────────────────────────

def test_a_step_on_a_stale_forward_calendar_exits_3_and_names_it(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath = _contracts(tmp_path)
    d = sessions[ANCHOR_I + 10]
    root = _bars_root(tmp_path, bars[bars["date"] <= d])
    fc_pull(root, pull_at(ANCHOR_I + 4), {"AAPL": {"next": amc(EARN_I + 63), "last": amc(EARN_I - 1)}})
    row = D.run("step", data_root=root, out=tmp_path / "dxb", contracts_path=cpath, asof=d,
                now=datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc), calendar=FakeCal())
    assert row["rc"] == 3 and row["action"] == "STALE_CALENDAR"
    assert "_forward_calendar" in row["calendar_stale"] and "AAPL" in row["calendar_stale"]
    assert "CALENDAR_STALE" in row["calendar_stale"]["AAPL"][0]


def test_no_calendar_at_all_is_stale_never_green(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath = _contracts(tmp_path)
    d = sessions[ANCHOR_I + 10]
    root = _bars_root(tmp_path, bars[bars["date"] <= d])
    row = D.run("step", data_root=root, out=tmp_path / "dxb", contracts_path=cpath, asof=d,
                now=datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc), calendar=FakeCal())
    assert row["rc"] == 3 and "UNKNOWN" in row["calendar_stale"]["_forward_calendar"][0]
    assert "NOT_COVERED" in row["calendar_stale"]["AAPL"][0]


def test_an_unscheduled_leader_is_named_and_healthy_while_the_calendar_is_fresh(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath = _contracts(tmp_path)
    d = sessions[ANCHOR_I + 10]
    root = _bars_root(tmp_path, bars[bars["date"] <= d])
    fc_pull(root, pull_at(ANCHOR_I + 10), {"AAPL": {"last": amc(ANCHOR_I - 5)}})      # only a past report
    row = D.run("step", data_root=root, out=tmp_path / "dxb", contracts_path=cpath, asof=d,
                now=datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc), calendar=FakeCal())
    assert row["rc"] == 0 and row["calendar_stale"] == {}
    assert row["leader_calendar"]["AAPL"]["state"] == "UNSCHEDULED" and "AAPL" in row["calendar_unscheduled"]
    assert "OVERDUE" not in row["calendar_unscheduled"]["AAPL"][0]
    assert row["leader_calendar"]["AAPL"]["last_reported"] == DAYS[ANCHOR_I - 5].date().isoformat()


def test_a_far_future_date_is_healthy_and_an_old_unscheduled_leader_is_overdue(synthetic, tmp_path, monkeypatch):
    bars, sessions, spec = synthetic
    root = _bars_root(tmp_path, bars)
    now = datetime.combine(DAYS[ANCHOR_I].date(), time(23, 0), tzinfo=timezone.utc)
    fc_pull(root, pull_at(ANCHOR_I), {"AAPL": {"next": amc(ANCHOR_I + 200), "last": amc(ANCHOR_I - 150)}})
    h = D.calendar_health(root, now=now)
    assert h["leaders"]["AAPL"]["state"] == "SCHEDULED_FAR" and h["stale"] == {} and h["unscheduled"] == {}
    fc_pull(root, pull_at(ANCHOR_I, 11), {"AAPL": {"last": amc(ANCHOR_I - 150)}})
    h = D.calendar_health(root, now=now)
    assert h["leaders"]["AAPL"]["state"] == "UNSCHEDULED" and h["stale"] == {}
    assert "OVERDUE" in h["unscheduled"]["AAPL"][0]


# ─────────────────────────── versions and the attended path ───────────────────────────

def test_a_changed_rolling_config_or_code_version_is_refused(synthetic, tmp_path, monkeypatch):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[EARN_I + 4]])
    kw = dict(data_root=root, out=out, contracts_path=cpath, asof=DAYS[EARN_I + 4], now=_close(EARN_I + 4, 3),
              calendar=FakeCal())
    D.run("backfill", **kw)
    decl = json.loads((out / "declaration.json").read_bytes())
    assert decl["rolling_config"] == json.loads(json.dumps(R.config_snapshot(), default=list))
    assert decl["contract_version"] == "v3"
    with monkeypatch.context() as m:
        m.setattr(_config, "ROLLING_COHORT_RANDOM_CONTROLS", 9)
        with pytest.raises(D.DynamicBookRefused, match="rolling grading config"):
            D.run("backfill", **kw)
    monkeypatch.setattr(R, "code_version", lambda: "f" * 40)
    with pytest.raises(D.DynamicBookRefused, match="accept-code-version"):
        D.run("backfill", **kw)
    row = D.run("backfill", **kw, accept_code_version=True)
    assert row["code_note"] and row["stored_rows_differ"] == 0
    journal = [json.loads(x) for x in (out / D.CODE_VERSIONS_FILE).read_text(encoding="utf8").splitlines()]
    assert journal == [{"code_version": "f" * 40, "accepted_utc": _close(EARN_I + 4, 3).isoformat(),
                        "run_id": row["run_id"]}]
    assert D.run("backfill", **kw)["code_note"] is None           # accepted once, journaled


def test_a_v2_out_folder_refuses_under_v3_code_with_or_without_the_attended_flag(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb_v2"
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[EARN_I + 4]])
    out.mkdir()
    v2 = json.loads(CONTRACTS_V2.read_bytes())
    (out / "declaration.json").write_text(json.dumps({
        "schema": "dynamic_exposure_declaration/2", "task": D.TASK_NAME, "declared_utc": "2026-11-15T02:00:00+00:00",
        "contracts_manifest_sha256": v2["manifest_sha256"],
        "contracts": {c["contract_id"]: c["contract_sha256"] for c in v2["contracts"]},
        "config": {}, "rolling_config": R.config_snapshot(), "code_version": R.code_version()}), encoding="utf8")
    (out / D.FACTS_FILE).write_text(json.dumps({"schema": "dynamic_exposure_calendar_fact/1", "leader": "AAPL",
                                                "earnings_date": "2025-01-30"}) + "\n", encoding="utf8")
    before = sorted((p.name, p.stat().st_size) for p in out.rglob("*"))
    kw = dict(data_root=root, out=out, contracts_path=cpath, asof=DAYS[EARN_I + 4], now=_close(EARN_I + 4, 3),
              calendar=FakeCal())
    for flag in (False, True):
        with pytest.raises(D.DynamicBookRefused, match="other contracts"):
            D.run("backfill", **kw, accept_code_version=flag)
        with pytest.raises(D.DynamicBookRefused, match="other contracts"):
            D.run("step", **kw, accept_code_version=flag)
    assert sorted((p.name, p.stat().st_size) for p in out.rglob("*")) == before        # nothing appended
    st = D.status(root, out, now=_close(EARN_I + 4, 3))
    assert st["rc"] == 2 and any("not the v3 in force" in p for p in st["problems"])


def test_status_is_read_only_and_names_what_a_scheduler_needs(synthetic, tmp_path, monkeypatch):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    monkeypatch.setattr(D, "CONTRACTS_REL", str(cpath))
    d = sessions[ANCHOR_I + 10]
    root = _data_root(tmp_path, bars[bars["date"] <= d])
    now = datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc)
    st0 = D.status(root, out, now=now)
    assert not out.exists() and st0["declaration"] is None and st0["rc"] == 0     # creates nothing
    D.run("step", data_root=root, out=out, contracts_path=cpath, asof=d, now=now, calendar=FakeCal())
    before = sorted((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in out.rglob("*"))
    st = D.status(root, out, now=now)
    assert sorted((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in out.rglob("*")) == before
    assert st["rc"] == 0 and st["contract_version"] == "v3" and st["declaration"]["contract_version"] == "v3"
    a = st["leaders"]["AAPL"]
    assert a["state"] == "SCHEDULED" and a["next_date"] == day(EARN_I + 63).date().isoformat()
    assert a["observed_utc"] and st["cohorts"] and st["last_run"]["action"] == "BORN"
    assert st["calendar_observations_on_record"] > 0
    late = now + timedelta(days=5)
    assert D.status(root, out, now=late)["rc"] == 3                                 # the calendar aged out


# ─────────────────────────── fix round of PR #158's review ───────────────────────────

@pytest.mark.parametrize("shape", ["reported: NO_DATE + last_reported", "rolled: next estimate, no last_reported"])
def test_a_vendor_rolling_forward_after_the_report_does_not_cancel_the_event(synthetic, shape):
    """The two post-report row shapes of the live 2026-11-13 sample: 10 of 11 reporters
    showed NO_DATE with last_reported_date (+utc); one (CDZI) showed the next estimate
    with no last_reported_date. Pulled after the event but BEFORE the reaction close, so
    the old rule (replaced before the reaction close = MOVED) would have cancelled it."""
    bars, sessions, spec = synthetic
    d0 = day(EARN_I - 1).date().isoformat()
    after = pull_at(EARN_I)                                  # 10:30Z on the reaction session
    pre = obs("AAPL", pull_at(EARN_I - 5), next_date=d0, event_utc=amc(EARN_I - 1))
    if shape.startswith("reported"):
        post = obs("AAPL", after, last=d0, last_utc=amc(EARN_I - 1))
    else:
        post = obs("AAPL", after, next_date=day(EARN_I + 63).date().isoformat(), timing="UNKNOWN",
                   event_utc=untimed(EARN_I + 63), known=False, conf="VENDOR_ESTIMATE")
    rows = [pre, post]
    facts = {f["earnings_date"]: f for f in D.leader_facts(rows, cal=FakeCal())}
    assert facts[d0]["observation_kind"] == "ANNOUNCED" and facts[d0]["acts_from_utc"] == pre["observed_utc"]
    ev = [e for e in D.leader_events(bars, list(facts.values()), sessions) if e["earnings_date"] == d0]
    assert D.event_status(ev[0], dec_map(sessions)) == "ON_TIME"
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, _ = compute(c, bars, sessions, rows)
    assert {r["date"] for r in paths["balanced"] if r["exposure"] < 1} == set(sessions[EARN_I + 1: EARN_I + 6])


def test_a_date_withdrawn_before_its_event_but_confirmed_after_acts_from_the_confirmation(synthetic):
    bars, sessions, spec = synthetic
    d0 = day(EARN_I - 1).date().isoformat()
    rows = [obs("AAPL", pull_at(EARN_I - 8), next_date=d0, event_utc=amc(EARN_I - 1)),
            obs("AAPL", pull_at(EARN_I - 2), last=day(EARN_I - 64).date().isoformat()),   # withdrawn pre-event
            obs("AAPL", pull_at(EARN_I + 2), last=d0, last_utc=amc(EARN_I - 1))]          # confirmed after
    f = next(x for x in D.leader_facts(rows, cal=FakeCal()) if x["earnings_date"] == d0)
    assert f["observation_kind"] == "MOVED" and f["acts_from_utc"] == rows[2]["observed_utc"]
    c = cohort(bars, sessions, spec, ANCHOR_I)
    paths, _ = compute(c, bars, sessions, rows)
    # decided at the closes of EARN_I+2.. (after the 10:30Z confirmation): sessions EARN_I+3..+5
    assert {r["date"] for r in paths["balanced"] if r["exposure"] < 1} == set(sessions[EARN_I + 3: EARN_I + 6])


def _files(out):
    return sorted((str(p), p.stat().st_size) for p in out.rglob("*")
                  if p.name != "runs.jsonl" and not p.name.endswith(".lock"))


def test_a_missing_leader_bar_is_stale_bars_writes_nothing_and_recovers_when_it_lands(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    root = _bars_root(tmp_path, bars)
    fc_pull(root, pull_at(EARN_I - 10), {"AAPL": {"next": amc(EARN_I - 1), "last": amc(EARN_I - 64)}})
    _run_through(tmp_path, bars, EARN_I - 1, out, cpath)
    files0 = _files(out)
    fc_pull(root, pull_at(EARN_I + 1), {"AAPL": {"next": amc(EARN_I + 62), "last": amc(EARN_I - 1)}})
    holed = bars[~((bars["symbol"] == "AAPL") & (bars["date"] == DAYS[EARN_I]))]
    for i in (EARN_I, EARN_I + 1):
        r = _run_through(tmp_path, holed, i, out, cpath)
        assert r["rc"] == 3 and r["action"] == "STALE_BARS" and r["paths_written"] == 0
        assert r["bar_gaps"][0]["leader"] == "AAPL" and r["bar_gaps"][0]["session"] == DAYS[EARN_I].date().isoformat()
        assert "no open of the reaction session" in r["calendar_stale"]["AAPL"][-1]
        assert r["forward_calendar"]["observations_appended"] == 0
    assert _files(out) == files0                                  # nothing but the journal was written
    r = _run_through(tmp_path, bars, EARN_I + 8, out, cpath)      # the bar lands: no refusal, correct cut
    assert r["rc"] == 0 and r["stored_rows_differ"] == 0
    p = _paths(out)
    bal = p[(p["personality"] == "balanced") & (p["cohort_id"] == DAYS[ANCHOR_I].date().isoformat())]
    assert set(bal.loc[bal["exposure"] < 1, "date"]) == {DAYS[EARN_I + j].date().isoformat() for j in range(1, 6)}


def test_a_session_not_closed_plus_grace_is_never_read_or_stored(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    root = _data_root(tmp_path, bars[bars["date"] <= DAYS[ANCHOR_I + 6]])
    for hours in (-3, 0.25):                                      # mid-session, and inside the 20-min grace
        r = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=DAYS[ANCHOR_I + 6],
                  now=_close(ANCHOR_I + 6, hours), calendar=FakeCal())
        assert r["sessions_unclosed_dropped"] == [DAYS[ANCHOR_I + 6].date().isoformat()]
        assert r["through"] == DAYS[ANCHOR_I + 5].date().isoformat()
    assert DAYS[ANCHOR_I + 6].date().isoformat() not in set(_paths(out)["date"])
    r = D.run("backfill", data_root=root, out=out, contracts_path=cpath, asof=DAYS[ANCHOR_I + 6],
              now=_close(ANCHOR_I + 6, 1), calendar=FakeCal())
    assert r["sessions_unclosed_dropped"] == [] and r["stored_rows_differ"] == 0
    assert DAYS[ANCHOR_I + 6].date().isoformat() in set(_paths(out)["date"])


def test_a_due_cohort_whose_entry_window_passed_is_missed_never_silent(synthetic, tmp_path):
    bars, sessions, spec = synthetic
    cpath, out = _contracts(tmp_path), tmp_path / "dxb"
    d = sessions[ANCHOR_I + 10]                                   # a scheduled cohort date
    _data_root(tmp_path, bars[bars["date"] <= d])                 # the calendar
    # the family is declared before d's close; d's bars are first seen after the next open
    D.run("step", data_root=_bars_root(tmp_path, bars[bars["date"] <= sessions[ANCHOR_I + 9]]), out=out,
          contracts_path=cpath, asof=sessions[ANCHOR_I + 9], now=_close(ANCHOR_I + 9, 2), calendar=FakeCal())
    root = _bars_root(tmp_path, bars[bars["date"] <= d])
    late = datetime.combine(sessions[ANCHOR_I + 11].date(), time(15, 0), tzinfo=timezone.utc)
    r = D.run("step", data_root=root, out=out, contracts_path=cpath, asof=d, now=late, calendar=FakeCal())
    assert r["rc"] == 0 and r["action"] == "MISSED_ENTRY_WINDOW" and r["born"] == []
    assert [m["cohort_id"] for m in r["missed"]] == [d.date().isoformat()]
    assert not (out / "cohorts" / f"dxb_cohort_{d.date()}.json").exists()
    assert all(pd.Timestamp(m["entry_open_utc"]) > pd.Timestamp(_close(ANCHOR_I + 9, 2)) for m in r["missed"])


def test_ingest_reads_full_universe_pulls_only(synthetic, tmp_path):
    root = tmp_path / "optimus"
    fc_pull(root, pull_at(EARN_I - 8), {"AAPL": {"next": amc(EARN_I - 1)}})
    FC.pull(["AAPL"], root, fetch=lambda s: {"AAPL": {"symbol": "AAPL", "quoteType": "EQUITY",
                                                      "earningsTimestampStart": amc(EARN_I + 20).timestamp()}},
            macro=False, now_fn=lambda: pull_at(EARN_I - 7), sleep_fn=lambda s: None, resume=False,
            scope=FC.PARTIAL)
    out = tmp_path / "dxb"
    out.mkdir()
    ing = D.ingest_forward_calendar(out, root, now=pull_at(EARN_I - 6), run_id="t")
    assert ing["appended"] == 1 and len(ing["snapshots_partial_skipped"]) == 1
    assert {o["scope"] for o in ing["observations"]} == {FC.FULL_UNIVERSE}
    pend = D.ingest_forward_calendar(out, root, now=pull_at(EARN_I - 6), run_id="t2", write=False)
    assert pend["appended"] == 0 and pend["pending"] == []        # already on record


def test_a_cohort_born_inside_a_cut_window_enters_at_the_cut_exposure(synthetic):
    bars, sessions, spec = synthetic
    c = cohort(bars, sessions, spec, EARN_I + 1)                  # entry EARN_I+2, inside EARN_I+1..+5
    paths, _ = compute(c, bars, sessions, ahead())
    b = paths["balanced"]
    assert [r["exposure"] for r in b[:4]] == [0.5] * 4 and b[4]["exposure"] == 1.0
    assert b[0]["rule_cost"] == pytest.approx(0.5 * _config.DYNAMIC_BOOK_COST_STOCK_BPS / 1e4)
    doc = json.loads(CONTRACTS.read_bytes())
    bal = next(x for x in doc["contracts"] if x["personality"] == "balanced")
    assert "enters at the cut exposure" in bal["rule"]["definition"]
    assert "BEFORE ITS EVENT TIME" in bal["rule"]["calendar_observation"]
    assert "No forward row existed" in doc["compile_history"]
