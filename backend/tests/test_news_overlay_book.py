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
    out, d = [], date.today() - timedelta(days=3 * n)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


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


def test_contract_hash_is_stable_and_names_the_mapping_declaration():
    a, b = NO.contract(), NO.contract()
    assert a["policy_hash"] == b["policy_hash"] and len(a["policy_hash"]) == 16
    assert a["params"]["NEWS_OVERLAY_MAPPINGS_TRIED"] == 1
    assert a["params"]["NEWS_OVERLAY_MAPPING_DECLARED_UTC"]


def test_flag_is_off_by_default():
    assert cfg.NEWS_OVERLAY_BOOK_ENABLED is False
