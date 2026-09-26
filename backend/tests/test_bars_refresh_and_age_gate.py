"""The bar panels' refresh and the age gate on `sim_run.u_plan` (review 2026-09-26).

On 2026-09-26 the ranker's panel ended 2026-09-21, nothing refreshed it, and
`u_plan` acted on a five-day-old ranking while every reader printed "bars
unchanged" as a normal skip. These tests pin:

* `u_plan` REFUSES -- EXPLOIT and PROBE, no broker call at all -- when the
  panel is older than `config.BARS_MAX_AGE_SESSIONS` closed sessions, and the
  receipt says `BARS_STALE: newest=<date> sessions_old=<n>`;
* the same gate on the ranking's own `asof`;
* `merge_panel` replaces a partial bar, drops a not-yet-closed session, and
  re-bases a symbol whose adjustment moved;
* a failed pull refuses WITHOUT touching the panel.

Every date derives from TODAY (session protocol item 5); no network.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backend import config
from backend.services import pc_broker as PB
from scripts import pull_bars_refresh as BR
from scripts import sim_run as S

NOW = datetime.now(timezone.utc)


def _sessions_back(n: int) -> date:
    """The closed session `n` sessions before the last closed one."""
    last, _ = BR.last_closed_session(NOW)
    days, _ = BR._sessions(last - timedelta(days=n * 3 + 20), last)
    return days[-1 - n]


def _panel(path: Path, newest: date, *, symbols=("AAA", "BBB"), n_days: int = 30,
           close: float = 10.0) -> Path:
    days, _ = BR._sessions(newest - timedelta(days=n_days * 2), newest)
    days = days[-n_days:]
    rows = [{"symbol": s, "date": pd.Timestamp(d), "open": close, "high": close,
             "low": close, "close": close + i * 0.01, "volume": 1000, "vwap": close,
             "trades": 10} for s in symbols for i, d in enumerate(days)]
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def _ranking(out: Path, asof: date) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranking.json").write_text(json.dumps({
        "asof": asof.isoformat(), "top20_net_rel_21d": 0.01, "model_version": "t",
        "top": [{"rank": 1, "symbol": "AAA", "decile": 9,
                 "expected_relative_return_21d_net": 0.01}]}), encoding="utf-8")


@pytest.fixture
def no_broker(monkeypatch):
    def _boom(*a, **k):
        pytest.fail("u_plan reached the broker on a stale panel")
    for name in ("snapshot", "last_prices", "clock", "orders", "submit"):
        monkeypatch.setattr(PB, name, _boom)


# ─────────────────────────────── the age ────────────────────────────────────

def test_bars_age_reads_the_date_column_and_counts_sessions(tmp_path):
    p = _panel(tmp_path / "bars.parquet", _sessions_back(4))
    age = BR.bars_age([p], now_utc=NOW, max_age_sessions=2)
    assert age["sessions_old"] == 4 and age["stale"] is True
    assert age["line"].startswith(f"BARS_STALE: newest={_sessions_back(4).isoformat()} "
                                  f"sessions_old=4")
    fresh = BR.bars_age([_panel(tmp_path / "f.parquet", _sessions_back(0))], now_utc=NOW)
    assert fresh["stale"] is False and fresh["sessions_old"] == 0


def test_a_missing_panel_is_unknown_and_counts_as_stale(tmp_path):
    age = BR.bars_age([tmp_path / "absent.parquet"], now_utc=NOW)
    assert age["stale"] is True and age["sessions_old"] is None
    assert "UNKNOWN" in age["line"]


def test_the_age_module_never_reads_an_mtime():
    import ast
    src = Path(BR.__file__).read_text(encoding="utf-8")
    names = {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)}
    assert not ({"st_mtime", "getmtime", "st_mtime_ns"} & names)


# ─────────────────────────────── the gate ───────────────────────────────────

def test_u_plan_refuses_exploit_and_probe_on_a_stale_panel(tmp_path, no_broker):
    stale = _sessions_back(config.BARS_MAX_AGE_SESSIONS + 2)
    p = _panel(tmp_path / "bars.parquet", stale)
    out = tmp_path / "out"
    _ranking(out, _sessions_back(0))
    res = S.u_plan(out, "paper_profit", asof=NOW.date().isoformat(),
                   funnel_path=tmp_path / "funnel.json",
                   ledger_path=tmp_path / "ledger.jsonl",
                   contracts_dir=tmp_path / "decisions" / "pc_plan",
                   bars_paths=[p], now_utc=NOW)
    assert res["refused"] == "BARS_STALE"
    assert res["acting"] is False and res["probe_acting"] is False
    assert res["exploit_acting"] is False and res["n_sent"] == 0
    rec = json.loads((out / "intended_book.json").read_text(encoding="utf-8"))
    assert rec["verdict"] == "REFUSED_BARS_STALE"
    assert rec["bars_line"].startswith(
        f"BARS_STALE: newest={stale.isoformat()} "
        f"sessions_old={config.BARS_MAX_AGE_SESSIONS + 2}")
    assert rec["why_not"] == rec["bars_line"]
    assert not (tmp_path / "ledger.jsonl").exists(), "no decision is written on stale bars"


def test_u_plan_refuses_on_a_stale_ranking_over_a_fresh_panel(tmp_path, no_broker):
    p = _panel(tmp_path / "bars.parquet", _sessions_back(0))
    out = tmp_path / "out"
    _ranking(out, _sessions_back(config.BARS_MAX_AGE_SESSIONS + 1))
    res = S.u_plan(out, "paper_profit", asof=NOW.date().isoformat(),
                   ledger_path=tmp_path / "ledger.jsonl",
                   contracts_dir=tmp_path / "decisions" / "pc_plan",
                   bars_paths=[p], now_utc=NOW)
    assert res["refused"] == "BARS_STALE"
    assert "ranking asof=" in res["bars_line"]


def test_the_gate_passes_inside_the_limit(tmp_path):
    p = _panel(tmp_path / "bars.parquet", _sessions_back(config.BARS_MAX_AGE_SESSIONS))
    g = S.bars_gate(_sessions_back(1).isoformat(), bars_paths=[p], now_utc=NOW)
    assert g["stale"] is False and g["line"].startswith("BARS_FRESH")


# ─────────────────────────────── the merge ──────────────────────────────────

def _new_rows(symbols, days, close_by=lambda s, d: 10.0, volume=5000):
    return pd.DataFrame([{"symbol": s, "date": pd.Timestamp(d), "open": 1.0, "high": 1.0,
                          "low": 1.0, "close": close_by(s, d), "volume": volume,
                          "vwap": 1.0, "trades": 5} for s in symbols for d in days])


def test_merge_replaces_the_partial_bar_and_appends_new_sessions(tmp_path):
    newest = _sessions_back(3)
    p = _panel(tmp_path / "b.parquet", newest)
    old = pd.read_parquet(p)
    days, _ = BR._sessions(newest - timedelta(days=12), _sessions_back(0))
    # the same closes as the old panel on overlap dates (no adjustment drift)
    closes = {(r.symbol, r.date.date()): r.close for r in old.itertuples()}
    new = _new_rows(["AAA", "BBB"], days,
                    close_by=lambda s, d: closes.get((s, d), 11.0))
    m = BR.merge_panel(p, new, keep_through=_sessions_back(0),
                       overlap_start=newest - timedelta(days=10))
    t = m["table"].to_pandas()
    assert not t.duplicated(["symbol", "date"]).any() and m["duplicate_keys"] == 0
    assert m["newest_after"] == _sessions_back(0).isoformat()
    assert m["rows_added"] == 2 * 3 and m["readjusted_symbols"] == []
    # the old newest bar (possibly partial) was REPLACED by the new one
    row = t[(t.symbol == "AAA") & (t.date == pd.Timestamp(newest))]
    assert int(row["volume"].iloc[0]) == 5000


def test_merge_drops_a_session_that_has_not_closed(tmp_path):
    newest = _sessions_back(1)
    p = _panel(tmp_path / "b.parquet", newest)
    new = _new_rows(["AAA"], [_sessions_back(0), _sessions_back(0) + timedelta(days=1)])
    m = BR.merge_panel(p, new, keep_through=_sessions_back(0))
    assert m["newest_after"] == _sessions_back(0).isoformat()


def test_an_adjustment_drift_rebases_the_symbol_from_its_repull(tmp_path):
    newest = _sessions_back(2)
    p = _panel(tmp_path / "b.parquet", newest)
    days, _ = BR._sessions(newest - timedelta(days=12), _sessions_back(0))
    new = _new_rows(["AAA"], days, close_by=lambda s, d: 5.0)     # a 2:1 split
    assert BR.drift_symbols(p, new, overlap_start=newest - timedelta(days=10),
                            newest=newest) == ["AAA"]
    full, _ = BR._sessions(newest - timedelta(days=120), _sessions_back(0))
    repull = _new_rows(["AAA"], full, close_by=lambda s, d: 5.0)
    m = BR.merge_panel(p, new, keep_through=_sessions_back(0), repulled=repull,
                       overlap_start=newest - timedelta(days=10))
    t = m["table"].to_pandas()
    assert set(t[t.symbol == "AAA"]["close"]) == {5.0}, "one adjustment base per series"
    assert t[t.symbol == "BBB"]["close"].max() < 11.0, "an undrifted symbol is untouched"


def test_a_failed_pull_refuses_and_leaves_the_panel_untouched(tmp_path):
    p = _panel(tmp_path / "b.parquet", _sessions_back(4))
    before = p.read_bytes()

    def _fail(symbols, start):
        raise SystemExit("REFUSED: no data credential")
    rec = BR.refresh({"ranker_deep": p}, now_utc=NOW, puller=_fail,
                     receipt_dir=tmp_path / "r", index=tmp_path / "r" / "i.jsonl")
    assert rec["status"] == "refused" and "nothing overwritten" in rec["reason"]
    assert p.read_bytes() == before
    assert rec["line"].startswith("BARS_STALE")
    assert Path(rec["path"]).exists()


def test_a_second_run_with_nothing_new_rewrites_nothing(tmp_path):
    newest = _sessions_back(0)
    p = _panel(tmp_path / "b.parquet", newest)
    old = pd.read_parquet(p)
    same = old[old["date"] >= pd.Timestamp(newest - timedelta(days=10))].copy()
    before = p.read_bytes()
    rec = BR.refresh({"ranker_deep": p}, now_utc=NOW,
                     puller=lambda syms, start: (same, "fixture"),
                     receipt_dir=tmp_path / "r", index=tmp_path / "r" / "i.jsonl")
    assert rec["status"] == "unchanged"
    assert p.read_bytes() == before
