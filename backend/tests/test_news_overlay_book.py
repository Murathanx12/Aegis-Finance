"""CH-14b news risk-overlay book: offline, synthetic digests and a synthetic base book.

No live data, no network, no calendar-moment literals: every date is derived
from `date.today()`.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend import config as cfg
from backend.services import news_overlay_book as NO


def _sessions(n: int) -> list[date]:
    """The last n real XNYS full-day sessions before today (calendar-derived)."""
    from backend.services import market_sessions as MS
    y = date.today().year
    early = set(MS.early_close_sessions(y)) | set(MS.early_close_sessions(y - 1))
    pool = [d for d in MS.sessions_in_year(y - 1) + MS.sessions_in_year(y)
            if d < date.today() and d not in early]
    return pool[-n:]


def _digest(stamp_dt: datetime, fgs, *, src: int = 2) -> dict:
    themes = [{"title": f"t{i}", "tone": {"fear_greed": fg, "n_independent_sources": src}}
              for i, fg in enumerate(fgs)]
    return {"stamp": stamp_dt.strftime("%Y%m%dT%H%M%SZ"), "dry_run": False, "themes": themes}


def _summaries(raw: list[dict]) -> list[dict]:
    return sorted((NO.digest_summary(d) for d in raw), key=lambda r: r["stamped_utc"])


def _history(session: date, fgs_per: list[float], *, hours_before: float = 3.0) -> list[dict]:
    """One digest per hour ending `hours_before` hours before the decision."""
    dt = NO.decision_time(session) - timedelta(hours=hours_before)
    raw = [_digest(dt - timedelta(hours=len(fgs_per) - 1 - i), [v, v, v]) for i, v in enumerate(fgs_per)]
    return _summaries(raw)


def test_scalar_bounds_over_any_deviation():
    for d in [x / 100.0 for x in range(-200, 201, 7)]:
        raw, s = NO.map_scalar(d)
        assert cfg.NEWS_OVERLAY_SCALAR_MIN <= s <= cfg.NEWS_OVERLAY_SCALAR_MAX
    assert NO.map_scalar(-5.0)[1] == cfg.NEWS_OVERLAY_SCALAR_MIN
    assert NO.map_scalar(+5.0)[1] == cfg.NEWS_OVERLAY_SCALAR_MAX


def test_fear_below_baseline_lowers_the_scalar():
    s = _sessions(3)[-1]
    dg = _history(s, [0.0] * 6 + [-0.12])
    out = NO.compute_scalar(dg, NO.decision_time(s))
    assert out["degradation"] is None
    assert out["scalar"] < 1.0
    assert out["digest_id"] == dg[-1]["digest_id"]


def test_no_look_ahead_a_digest_after_decision_time_is_never_read():
    s = _sessions(3)[-1]
    dg = _history(s, [0.0] * 6)
    late = _summaries([_digest(NO.decision_time(s) + timedelta(minutes=1), [-0.9] * 4)])
    exact = _summaries([_digest(NO.decision_time(s), [-0.9] * 4)])
    out = NO.compute_scalar(dg + late + exact, NO.decision_time(s))
    assert out["digest_id"] == dg[-1]["digest_id"]
    assert out["scalar"] == 1.0
    assert datetime.fromisoformat(out["digest_stamped_utc"]) < NO.decision_time(s)


def test_stale_digest_is_one_with_degradation():
    s = _sessions(3)[-1]
    hrs = cfg.NEWS_OVERLAY_MAX_AGE_HOURS + 5
    dg = _history(s, [0.0] * 6 + [-0.5], hours_before=hrs)
    out = NO.compute_scalar(dg, NO.decision_time(s))
    assert out["scalar"] == 1.0 and out["degradation"] == NO.STALE


def test_empty_digest_is_one_with_degradation():
    s = _sessions(3)[-1]
    dg = _history(s, [0.0] * 6)
    empty = _summaries([{"stamp": (NO.decision_time(s) - timedelta(minutes=30)).strftime("%Y%m%dT%H%M%SZ"),
                         "dry_run": False, "themes": []}])
    out = NO.compute_scalar(dg + empty, NO.decision_time(s))
    assert out["scalar"] == 1.0 and out["degradation"] == NO.EMPTY


def test_no_digest_and_no_baseline_are_one_with_degradation():
    s = _sessions(3)[-1]
    assert NO.compute_scalar([], NO.decision_time(s))["degradation"] == NO.NO_DIGEST
    out = NO.compute_scalar(_history(s, [-0.5, -0.9]), NO.decision_time(s))
    assert out["scalar"] == 1.0 and out["degradation"] == NO.NO_BASELINE


def test_dry_runs_are_ignored():
    assert NO.digest_summary({"stamp": "20260101T000000Z", "dry_run": True, "themes": []}) is None


def _base(sessions, *, change_at: int | None = None):
    syms = ["AAA", "BBB", "CCC", "DDD"]
    prices, weights, changed = {}, {}, {}
    for i, t in enumerate(sessions):
        prices[t] = {s: 10.0 + j + 0.3 * ((i * (j + 1)) % 5) for j, s in enumerate(syms + ["EEE"])}
        held = syms if (change_at is None or i < change_at) else ["BBB", "CCC", "DDD", "EEE"]
        weights[t] = {s: 0.24 for s in held}
        changed[t] = change_at is not None and i == change_at
    return prices, weights, changed


def test_twin_identical_at_scalar_one():
    ss = _sessions(12)
    prices, weights, changed = _base(ss, change_at=6)
    sim = NO.simulate(ss, prices, weights, changed, {t: 1.0 for t in ss})
    for r in sim["rows"]:
        assert r["overlay_nav"] == pytest.approx(r["twin_nav"], rel=0, abs=1e-9)
    assert sim["holdings_last"]["overlay"] == pytest.approx(sim["holdings_last"]["twin"])
    assert set(sim["holdings_last"]["twin"]) == set(weights[ss[-1]])


def test_overlay_holds_the_twins_names_scaled():
    ss = _sessions(6)
    prices, weights, changed = _base(ss)
    sim = NO.simulate(ss, prices, weights, changed, {t: (0.5 if i >= 2 else 1.0) for i, t in enumerate(ss)})
    ov, tw = sim["holdings_last"]["overlay"], sim["holdings_last"]["twin"]
    assert set(ov) == set(tw)
    ratios = {s: ov[s] / tw[s] for s in tw}
    assert max(ratios.values()) - min(ratios.values()) < 1e-9
    assert sim["rows"][-1]["overlay_gross"] < sim["rows"][-1]["twin_gross"]


def test_costs_charged_on_scalar_changes():
    ss = _sessions(8)
    prices, weights, changed = _base(ss)
    sc = {t: (0.7 if i % 2 else 1.0) for i, t in enumerate(ss)}
    sim = NO.simulate(ss, prices, weights, changed, sc)
    rows = sim["rows"]
    assert sim["cost_rate"] > 0
    for i in range(1, len(rows)):
        if sc[ss[i]] != sc[ss[i - 1]]:
            assert rows[i]["overlay_cost"] > 0
        assert rows[i]["twin_cost"] == 0.0
    assert sum(r["overlay_cost"] for r in rows[1:]) > 0


def test_zero_costs_are_refused(monkeypatch):
    monkeypatch.setattr(cfg, "NEWS_OVERLAY_COST_BPS_PER_SIDE", 0.0)
    monkeypatch.setattr(cfg, "NEWS_OVERLAY_SLIPPAGE_BPS", 0.0)
    with pytest.raises(Exception):
        NO.cost_rate()


def test_flag_off_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "NEWS_OVERLAY_BOOK_ENABLED", False)
    s = _sessions(3)[-1]
    out = tmp_path / "news_overlay_book" / "decisions.jsonl"
    row = NO.step(s, digests=_history(s, [0.0] * 6 + [-0.2]), base_weights={"AAA": 0.5, "BBB": 0.5},
                  out_path=out)
    assert row["written"] is False and not out.exists() and not out.parent.exists()


def test_flag_on_writes_one_row_citing_the_digest(tmp_path):
    s = _sessions(3)[-1]
    dg = _history(s, [0.0] * 6 + [-0.2])
    out = tmp_path / "d.jsonl"
    row = NO.step(s, digests=dg, base_weights={"AAA": 0.5, "BBB": 0.5}, enabled=True, out_path=out)
    got = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert len(got) == 1 and got[0]["digest_id"] == dg[-1]["digest_id"] == row["digest_id"]
    assert got[0]["policy_hash"] == NO.contract()["policy_hash"]


def test_a_foreign_contract_file_refuses(tmp_path):
    s = _sessions(3)[-1]
    out = tmp_path / "d.jsonl"
    out.write_text(json.dumps({"policy_hash": "0000000000000000"}) + "\n", encoding="utf-8")
    with pytest.raises(NO.NewsOverlayRefused):
        NO.step(s, digests=[], base_weights={"AAA": 1.0}, enabled=True, out_path=out)


def test_missing_inputs_refuse(tmp_path):
    s = _sessions(3)[-1]
    with pytest.raises(NO.NewsOverlayRefused):
        NO.step(s, digests=[], base_weights={})
    with pytest.raises(NO.NewsOverlayRefused):
        NO.load_digests(tmp_path / "nowhere")
    ss = _sessions(3)
    prices, weights, changed = _base(ss)
    prices.pop(ss[1])
    with pytest.raises(NO.NewsOverlayRefused):
        NO.simulate(ss, prices, weights, changed, {})


def test_contract_carries_disclosure_history_and_hash():
    a, b = NO.contract(), NO.contract()
    assert a["policy_hash"] == b["policy_hash"] and len(a["policy_hash"]) == 16
    assert a["name"] == "NEWS_OVERLAY_v3"
    assert a["disclosure"]["mappings_tried"] == cfg.NEWS_OVERLAY_MAPPINGS_TRIED
    assert "-0.21" in a["disclosure"]["seen_before_choosing"]
    assert "no return" in a["disclosure"]["seen_before_choosing"]
    assert a["history"][0]["policy_hash"] == "ce686058847fdbc7"
    assert a["history"][1]["policy_hash"] == "2d85fa126b83f4ac"
    assert a["policy_hash"] not in ("ce686058847fdbc7", "2d85fa126b83f4ac")
    assert "NO_DECISION_ROW" in a["grading"] and "LIQUID-RANDOM-50" in a["base_definition"]
    assert a["disclosure"]["bases_tried"] == 2 and "SECOND LOOK" in a["disclosure"]["v3_change"]
    assert "not a strategy" in a["why_random_base"] and a["comparison_base"]["id"] == "SPY"
    assert "REFUSED" in a["stale_bar_refusal"]


def test_flag_is_off_by_default():
    assert cfg.NEWS_OVERLAY_BOOK_ENABLED is False


def test_the_committed_contract_is_the_rule_in_code():
    """Frozen: changing any NEWS_OVERLAY_* parameter or the rule text changes the
    hash, and this fails. A changed rule is a new version, a new file."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "docs" / "TRIALS" / "CONTRACT_NEWS_OVERLAY_v3.json"
    frozen = json.loads(p.read_text(encoding="utf-8"))
    assert frozen["policy_hash"] == NO.contract()["policy_hash"] == V3_HASH


V3_HASH = "c777f997289240e4"


def test_v3_keeps_every_v2_mapping_parameter():
    """FAILURE value of the v3 brief: any mapping parameter changed from v2."""
    from pathlib import Path
    v2 = json.loads((Path(__file__).resolve().parents[2] / "docs" / "TRIALS"
                     / "CONTRACT_NEWS_OVERLAY_v2.json").read_text(encoding="utf-8"))
    now = NO.params()
    changed = {k for k, v in v2["params"].items() if now.get(k) != (tuple(v) if isinstance(v, list) else v)}
    assert changed == {"NEWS_OVERLAY_BASE_BOOK"}
    assert v2["policy_hash"] != NO.contract()["policy_hash"]
    assert v2["mapping"] == NO.contract()["mapping"] and v2["timing"] == NO.contract()["timing"]


# -- review round 1 (PR #125) ------------------------------------------------

def _at_et(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, datetime.min.time().replace(hour=hh, minute=mm), tzinfo=NO.ET)


def _a_friday_session() -> date:
    return next(d for d in reversed(_sessions(30)) if d.weekday() == 4)


def test_forward_session_is_the_new_york_date_on_a_friday():
    fri = _a_friday_session()
    now = _at_et(fri, 15, 45)
    # on a UTC+8 machine that instant is already Saturday
    assert now.astimezone(timezone(timedelta(hours=8))).date() == fri + timedelta(days=1)
    d, refusal = NO.forward_session(now)
    assert d == fri and refusal is None
    assert NO.decision_time(d) <= now.astimezone(timezone.utc) < NO.decision_time(d) + timedelta(hours=1)


def test_forward_session_refuses_weekend_holiday_and_outside_window():
    from backend.services import market_sessions as MS
    fri = _a_friday_session()
    assert NO.forward_session(_at_et(fri + timedelta(days=1), 15, 45))[1]          # Saturday
    hol = MS.non_sessions_in_year(date.today().year - 1)[0]
    assert NO.forward_session(_at_et(hol, 15, 45))[1]                             # holiday
    assert NO.forward_session(_at_et(fri, 15, 0))[1]                              # before window
    assert NO.forward_session(_at_et(fri, 16, 5))[1]                              # after close
    with pytest.raises(NO.NewsOverlayRefused):
        NO.forward_session(datetime.combine(fri, datetime.min.time()))            # naive clock


def test_decision_time_follows_dst():
    """15:30 ET is 19:30 UTC in summer (EDT) and 20:30 UTC in winter (EST)."""
    from backend.services import market_sessions as MS
    y = date.today().year - 1
    early = set(MS.early_close_sessions(y))
    ss = [d for d in MS.sessions_in_year(y) if d not in early]
    first_sun_nov = next(date(y, 11, k) for k in range(1, 8) if date(y, 11, k).weekday() == 6)
    after = next(d for d in ss if d > first_sun_nov)            # the DST week, after the change
    before = max(d for d in ss if d < first_sun_nov)
    assert NO.decision_time(before).hour == 19 and NO.decision_time(after).hour == 20
    assert NO.forward_session(_at_et(after, 15, 45)) == (after, None)
    assert NO.forward_session(_at_et(before, 15, 45)) == (before, None)


def test_decision_time_respects_an_early_close():
    from backend.services import market_sessions as MS
    ec = MS.early_close_sessions(date.today().year - 1)
    if not ec:
        pytest.skip("no early close in the calendar year")
    d = ec[0]
    assert NO.decision_time(d) <= MS.session_close_utc(d) - timedelta(minutes=30)


def test_written_utc_and_idempotent_forward_row(tmp_path):
    s = _sessions(3)[-1]
    out = tmp_path / "d.jsonl"
    dg = _history(s, [0.0] * 6 + [-0.2])
    now = _at_et(s, 15, 45)
    a = NO.step(s, digests=dg, base_weights={"AAA": 1.0}, enabled=True, out_path=out, now=now)
    b = NO.step(s, digests=dg, base_weights={"AAA": 1.0}, enabled=True, out_path=out, now=now)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and a["written"] and b["duplicate"] and not b["written"]
    assert json.loads(lines[0])["written_utc"] == now.astimezone(timezone.utc).isoformat(timespec="seconds")


def test_every_row_is_checked_for_a_foreign_contract(tmp_path):
    s = _sessions(3)[-1]
    out = tmp_path / "d.jsonl"
    good = {"policy_hash": NO.contract()["policy_hash"], "session": "x", "label": "FORWARD"}
    out.write_text(json.dumps(good) + "\n" + json.dumps({"policy_hash": "0000000000000000"}) + "\n",
                   encoding="utf-8")
    with pytest.raises(NO.NewsOverlayRefused, match="line 2"):
        NO.step(s, digests=[], base_weights={"AAA": 1.0}, enabled=True, out_path=out)


def test_backdated_and_backfill_rows_are_never_graded(tmp_path):
    ss = _sessions(4)
    h = NO.contract()["policy_hash"]
    out = tmp_path / "d.jsonl"
    rows = [{"policy_hash": h, "session": ss[0].isoformat(), "label": "BACKDATED", "scalar": 0.5},
            {"policy_hash": h, "session": ss[1].isoformat(), "label": "BACKFILL", "scalar": 0.5},
            {"policy_hash": h, "session": ss[2].isoformat(), "label": "FORWARD", "scalar": 0.7}]
    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = NO.read_forward_rows(out, h)
    assert [r["session"] for r in got] == [ss[2].isoformat()]


def test_a_session_with_no_decision_row_grades_at_one():
    ss = _sessions(3)
    rows = [{"session": ss[0].isoformat(), "scalar": 0.5, "degradation": None},
            {"session": ss[2].isoformat(), "scalar": 0.6, "degradation": None}]
    sc, why = NO.grade_scalars(ss, rows)
    assert sc[ss[1]] == 1.0 and why[ss[1]] == NO.NO_DECISION_ROW
    assert sc[ss[0]] == 0.5 and sc[ss[2]] == 0.6


def test_baseline_digests_older_than_the_bound_do_not_count():
    s = _sessions(3)[-1]
    old_age = timedelta(days=cfg.NEWS_OVERLAY_BASELINE_MAX_AGE_DAYS + 3)
    t0 = NO.decision_time(s) - timedelta(hours=2)
    raw = [_digest(t0 - old_age - timedelta(hours=i), [0.0] * 3) for i in range(12)]
    raw.append(_digest(t0, [-0.3] * 3))
    out = NO.compute_scalar(_summaries(raw), NO.decision_time(s))
    assert out["degradation"] == NO.NO_BASELINE and out["scalar"] == 1.0 and out["n_baseline"] == 0
    fresh = [_digest(t0 - timedelta(hours=i + 1), [0.0] * 3) for i in range(6)]
    out2 = NO.compute_scalar(_summaries(raw + fresh), NO.decision_time(s))
    assert out2["degradation"] is None and out2["n_baseline"] == 6 and out2["scalar"] < 1.0


def test_stale_holdings_are_flagged():
    ss = _sessions(4)
    w = {t: {"AAA": 0.5, "BBB": 0.5} for t in ss}
    lim = cfg.NEWS_OVERLAY_STALE_BAR_SESSIONS
    pos = {"AAA": {t: 0 for t in ss}, "BBB": {t: lim + 1 + i for i, t in enumerate(ss)}}
    st = NO.stale_holdings(pos, ss, w)
    assert set(st) == set(ss) and all(set(v) == {"BBB"} for v in st.values())
    pos["BBB"] = {t: lim for t in ss}
    assert NO.stale_holdings(pos, ss, w) == {}


def test_a_rebalance_dated_on_a_non_session_day_takes_effect_next_session():
    ss = _sessions(6)
    gap = next(i for i in range(1, len(ss)) if (ss[i] - ss[i - 1]).days > 1)   # a weekend
    non_session = ss[gap - 1] + timedelta(days=1)
    snaps = [{"asof": ss[0], "shares": {"AAA": 10.0}, "cash": 0.0},
             {"asof": non_session, "shares": {"BBB": 10.0}, "cash": 0.0}]
    closes = {t: {"AAA": 10.0, "BBB": 10.0} for t in ss}
    weights, changed = NO.base_weights_by_session(snaps, ss, closes)
    assert changed[ss[gap]] is True and sum(changed.values()) == 1
    assert set(weights[ss[gap]]) == {"BBB"}


def test_worst_single_name_loss_is_signed_and_at_actual_weight():
    from scripts import news_overlay_book as CLI
    ss = _sessions(3)
    closes = {ss[0]: {"UP": 10.0, "DN": 10.0}, ss[1]: {"UP": 30.0, "DN": 9.0}, ss[2]: {"UP": 30.0, "DN": 9.0}}
    weights = {t: {"UP": 0.1, "DN": 0.4} for t in ss}
    sim = NO.simulate(ss, closes, weights, {t: False for t in ss}, {t: 1.0 for t in ss})
    wc = CLI.worst_case_lines(ss, closes, weights, sim)
    a = wc["worst_single_name_loss"]
    assert a["symbol"] == "DN" and a["usd"] < 0          # a +200% move cannot set it
    assert a["usd"] == pytest.approx(0.4 * sim["rows"][0]["twin_nav"] * -0.1, rel=1e-6)
    assert wc["total_loss_bound"]["usd"]["twin"] <= 1.01 * sim["notional"]


def _small_liquid_rules(monkeypatch):
    """Shrink the LIQUID-RANDOM rules to a synthetic panel's size."""
    for k, v in {"NEWS_OVERLAY_LIQUID_N": 3, "NEWS_OVERLAY_LIQUID_MIN_HISTORY": 30,
                 "NEWS_OVERLAY_LIQUID_DV_SESSIONS": 20, "NEWS_OVERLAY_LIQUID_SUSPECT_LOOKBACK": 30,
                 "NEWS_OVERLAY_LIQUID_MIN_DOLLAR_VOL": 50_000_000.0}.items():
        monkeypatch.setattr(cfg, k, v)


def _all_sessions(n: int) -> list[date]:
    from backend.services import market_sessions as MS
    y = date.today().year
    pool = [d for d in MS.sessions_in_year(y - 1) + MS.sessions_in_year(y) if d < date.today()]
    return pool[-n:]


def _synthetic_data_dir(tmp_path, sessions):
    """A data folder with the inputs the CLI reads, all synthetic: digests over
    `sessions` and a bars panel (close, volume) with history before them."""
    import pandas as pd
    d = tmp_path / "data"
    dig = d / "optimus" / "digest"
    dig.mkdir(parents=True)
    for i, t in enumerate(sessions):
        for h in (4, 3):
            stamp = NO.decision_time(t) - timedelta(hours=h)
            fg = -0.3 if (i % 3 == 2 and h == 3) else 0.0
            (dig / f"world_digest_{stamp:%Y%m%dT%H%M%SZ}.json").write_text(
                json.dumps(_digest(stamp, [fg, fg, fg])), encoding="utf-8")
    bars = d / "optimus" / "prices_2025_26"
    bars.mkdir(parents=True)
    allss = _all_sessions(len(sessions) + 80)
    syms = [f"S{j:02d}" for j in range(8)] + ["SPY"]
    pd.DataFrame([{"symbol": s, "date": pd.Timestamp(t), "close": 20.0 + j + 0.05 * (i % 7),
                   "volume": 5_000_000.0}
                  for i, t in enumerate(allss) for j, s in enumerate(syms)]).to_parquet(bars / "bars.parquet")
    return d


def test_cli_replay_step_and_grade_end_to_end(tmp_path, monkeypatch):
    from scripts import news_overlay_book as CLI
    _small_liquid_rules(monkeypatch)
    ss = _sessions(10)
    d = _synthetic_data_dir(tmp_path, ss)
    out = tmp_path / "out"
    assert CLI.main(["replay", "--out", str(out), "--data-dir", str(d)]) == 0
    rc = json.loads(next(out.glob("news_overlay_replay_*.json")).read_text(encoding="utf-8"))
    assert rc["headline"]["LABEL"].startswith("BACKFILL")
    assert all(r["label"] == "BACKFILL" for r in rc["decision_rows"])
    assert rc["live_folder_counts"]["unchanged"] is True
    assert "total_loss_bound" in rc["headline"]["worst_case_first"]
    assert rc["headline"]["stale_refusals"]["n_days_refused"] == 0
    assert rc["headline"]["comparison_spy_base"]["role"].startswith("COMPARISON")
    assert all(len(dr["names"]) == 3 and "SPY" not in dr["names"] for dr in rc["headline"]["base"]["draws"])
    assert CLI.main(["replay", "--out", str(d / "optimus" / "x"), "--data-dir", str(d)]) == 2
    dp = NO.decisions_path(d / "optimus")
    monkeypatch.setattr(cfg, "NEWS_OVERLAY_BOOK_ENABLED", False)
    assert CLI.main(["step", "--data-dir", str(d)], now=_at_et(ss[-2], 15, 45)) == 0
    assert not dp.exists()
    assert CLI.main(["grade", "--out", str(out), "--data-dir", str(d)]) == 2
    monkeypatch.setattr(cfg, "NEWS_OVERLAY_BOOK_ENABLED", True)
    assert CLI.main(["step", "--data-dir", str(d)], now=_at_et(ss[-2], 12, 0)) == 2   # outside window
    sat = ss[-2] + timedelta(days=(5 - ss[-2].weekday()) % 7 or 7)
    assert CLI.main(["step", "--data-dir", str(d)], now=_at_et(sat, 15, 45)) == 2     # Saturday
    assert not dp.exists()
    assert CLI.main(["step", "--date", ss[-5].isoformat(), "--data-dir", str(d)],
                    now=_at_et(ss[-2], 15, 45)) == 0                                  # BACKDATED
    assert CLI.main(["grade", "--out", str(out), "--data-dir", str(d)]) == 2
    for t in (ss[-4], ss[-2], ss[-2]):                                                # a miss + a repeat
        assert CLI.main(["step", "--data-dir", str(d)], now=_at_et(t, 15, 45)) == 0
    rows = [json.loads(x) for x in dp.read_text(encoding="utf-8").splitlines()]
    assert [r["label"] for r in rows] == ["BACKDATED", "FORWARD", "FORWARD"]
    assert all(r["digest_id"] and r["written_utc"] for r in rows)
    assert CLI.main(["grade", "--out", str(out), "--data-dir", str(d)]) == 0
    g = json.loads(next(out.glob("news_overlay_grade_*.json")).read_text(encoding="utf-8"))
    reasons = {r["session"]: r["reason"] for r in g["daily"]}
    assert reasons[ss[-3].isoformat()] == NO.NO_DECISION_ROW
    assert g["no_decision_row_sessions"] == 1


# -- v3: the LIQUID-RANDOM-50 base ---------------------------------------------

def _panel(n: int = 60):
    """Wide synthetic close/volume frames over n real sessions, one symbol per rule."""
    import numpy as np
    import pandas as pd
    idx = _all_sessions(n)
    good = [f"G{j}" for j in range(6)]
    cols = good + ["LOWDV", "CHEAP", "YOUNG", "STALE", "SPLIT", "SPY"]
    close = pd.DataFrame(20.0, index=idx, columns=cols)
    for j, g in enumerate(good):
        close[g] = 20.0 + j + np.arange(n) * 0.01
    vol = pd.DataFrame(5_000_000.0, index=idx, columns=cols)       # 20 x 5M = $100M/day
    vol["LOWDV"] = 100_000.0
    close["CHEAP"] = 3.0
    vol["CHEAP"] = 100_000_000.0
    close.loc[idx[:-10], "YOUNG"] = np.nan
    close.loc[idx[-6:], "STALE"] = np.nan
    close.loc[idx[-8]:, "SPLIT"] = 10.0                            # a one-bar -50%: suspect
    return idx, close, vol


def test_liquid_rules_exclude_each_failing_name(monkeypatch):
    _small_liquid_rules(monkeypatch)
    idx, close, vol = _panel()
    asof = idx[-1] + timedelta(days=1)
    while not NO.is_session(asof):
        asof += timedelta(days=1)
    el = NO.eligibility(close, vol, asof)
    assert el["pool"] == [f"G{j}" for j in range(6)]
    f = el["fails"]
    assert "LOWDV" in f["dollar_vol"] and "CHEAP" in f["price"] and "YOUNG" in f["history"]
    assert "STALE" in f["stale"] and "SPLIT" in f["suspect"] and "SPY" in f["etf"]
    assert not any(g in v for v in f.values() for g in el["pool"])


def test_the_draw_is_reproducible_from_its_seed_and_uses_only_bars_before_its_date(monkeypatch):
    _small_liquid_rules(monkeypatch)
    idx, close, vol = _panel(70)
    D = idx[-10]
    a = NO.draw_liquid_base(close, vol, D)
    b = NO.draw_liquid_base(close, vol, D)
    assert a == b and a["seed"] == NO.draw_seed(D) and len(a["names"]) == 3
    assert date.fromisoformat(a["last_bar_date_used"]) < D
    # rewrite every bar ON and AFTER D: the draw must not move
    c2, v2 = close.copy(), vol.copy()
    c2.loc[D:, :] = 1.0
    v2.loc[D:, :] = 1e12
    c2.loc[D:, "G0"] = float("nan")
    assert NO.draw_liquid_base(c2, v2, D) == a
    # the same seed through the engine's draw gives the same names (reproducible by hand)
    from backend.services import paper_books as PB
    pool = NO.eligibility(close, vol, D)["pool"]
    assert PB._draw(pool, 3, a["seed"]) == a["names"]
    # a different base seed is a different recorded seed
    monkeypatch.setattr(cfg, "NEWS_OVERLAY_LIQUID_SEED", cfg.NEWS_OVERLAY_LIQUID_SEED + 1)
    assert NO.draw_liquid_base(close, vol, D)["seed"] != a["seed"]


def test_a_draw_with_too_few_eligible_names_refuses(monkeypatch):
    _small_liquid_rules(monkeypatch)
    monkeypatch.setattr(cfg, "NEWS_OVERLAY_LIQUID_N", 50)
    idx, close, vol = _panel()
    with pytest.raises(NO.NewsOverlayRefused, match="eligible"):
        NO.draw_liquid_base(close, vol, idx[-1])


def test_month_draw_date_is_the_first_session_of_the_month():
    for t in _sessions(40):
        D = NO.month_draw_date(t)
        assert D.month == t.month and D <= t and NO.is_session(D)
        assert all(not NO.is_session(date(t.year, t.month, k)) for k in range(1, D.day))


def test_stale_weight_share_refuses_the_day_at_one(tmp_path):
    s = _sessions(3)[-1]
    dg = _history(s, [0.0] * 6 + [-0.3])
    lim = cfg.NEWS_OVERLAY_STALE_BAR_SESSIONS
    shares = {"AAA": 1.0, "BBB": 1.0, "CCC": 1.0}
    px = {"AAA": 10.0, "BBB": 10.0, "CCC": 10.0}
    ok = NO.stale_weight_share(shares, px, {"AAA": 0, "BBB": 0, "CCC": lim})
    assert ok["share"] == 0.0 and ok["names"] == {}
    bad = NO.stale_weight_share(shares, px, {"AAA": 0, "BBB": 0, "CCC": lim + 1})
    assert bad["share"] == pytest.approx(1 / 3) and set(bad["names"]) == {"CCC"}
    assert bad["share"] > cfg.NEWS_OVERLAY_STALE_REFUSE_SHARE
    w = {k: 1 / 3 for k in shares}
    mapped = NO.step(s, digests=dg, base_weights=w, write=False, stale=ok)
    assert mapped["scalar"] < 1.0 and mapped["degradation"] is None and not mapped.get("refused")
    out = tmp_path / "d.jsonl"
    r = NO.step(s, digests=dg, base_weights=w, enabled=True, out_path=out, stale=bad)
    assert r["scalar"] == 1.0 and r["degradation"] == NO.STALE_BASE and r["refused"] is True
    assert r["tone_scalar"] < 1.0 and r["stale_names"] == {"CCC": lim + 1}
    assert json.loads(out.read_text(encoding="utf-8").splitlines()[0])["degradation"] == NO.STALE_BASE
    # a missing bar altogether counts as stale
    assert NO.stale_weight_share(shares, px, {"AAA": None})["share"] == pytest.approx(1.0)


def test_the_flag_is_an_env_var_read_without_editing_config():
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    code = "from backend import config as c; print(c.NEWS_OVERLAY_BOOK_ENABLED)"
    outs = {}
    for v in ("1", "0", None):
        env = {k: x for k, x in os.environ.items() if k != "AEGIS_NEWS_OVERLAY_BOOK"}
        env["AEGIS_IGNORE_DOTENV"] = "1"
        if v is not None:
            env["AEGIS_NEWS_OVERLAY_BOOK"] = v
        outs[v] = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True,
                                 text=True, timeout=120).stdout.strip().splitlines()[-1]
    assert outs == {"1": "True", "0": "False", None: "False"}
