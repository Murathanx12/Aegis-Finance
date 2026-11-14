"""Rolling live cohorts (CH-16 / M3): synthetic fixtures only, no network, no live data.

Dates are a synthetic business-day range in the past, so nothing here expires.
The exchange calendar is injected (next business day, 14:30Z open / 21:00Z close).
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config as _config
from backend.services.portfolio_intelligence import branch_population_rolling as R

ROOT = Path(__file__).resolve().parents[2]
SPECS_V2 = ROOT / "docs/TRIALS/ROLLING-COHORTS-SPECIFICATIONS-v2.json"
DAYS = pd.bdate_range("2024-01-02", periods=330)
ANCHOR_I = 280
SYMS = [f"S{i:02d}" for i in range(60)]


class FakeCal:
    def next_open_after(self, day):
        d = pd.Timestamp(day) + pd.offsets.BDay(1)
        return datetime.combine(d.date(), time(14, 30), tzinfo=timezone.utc)

    def close_of(self, day):
        return datetime.combine(pd.Timestamp(day).date(), time(21, 0), tzinfo=timezone.utc)


def utc(day, hh=23):
    return datetime.combine(pd.Timestamp(day).date(), time(hh, 0), tzinfo=timezone.utc)


def make_bars(n_days: int) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    days = DAYS[:n_days]
    spy_r = rng.normal(0.0004, 0.01, len(days))
    rows = []
    spy = 400 * np.cumprod(1 + spy_r)
    for d, c in zip(days, spy):
        rows.append(("SPY", d, c * 0.999, c, 5e7))
    for i, s in enumerate(SYMS):
        beta = 0.2 + 0.03 * i
        r = beta * spy_r + rng.normal(0.0002 * (i % 7 - 3), 0.005 + 0.0004 * i, len(days))
        px = 50 * np.cumprod(1 + r)
        vol = 3e6 if i < 30 else 1e5
        for d, c in zip(days, px):
            rows.append((s, d, c * 0.998, c, vol))
    return pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "volume"])


def make_revisions(cohort: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for k in range(1, 12):
        day = cohort - pd.Timedelta(days=k)
        for i in range(0, 30, 3):
            for f in range(4):
                rows.append(dict(ticker=SYMS[i], event_date=str(day + pd.Timedelta(hours=14)), firm=f"F{f}",
                                 target_action="Raises" if (i + f) % 4 else "Lowers", prior_target=50.0,
                                 current_target=55.0, pit_safe=True,
                                 first_seen_utc=(day + pd.Timedelta(hours=16)).tz_localize("UTC").isoformat()))
    return pd.DataFrame(rows)


def news_lines(cohort: pd.Timestamp, *, n: int, cached_after=None) -> list[str]:
    out = []
    for k in range(n):
        t = SYMS[k % 30]
        pub = (cohort - pd.Timedelta(hours=10 + k)).tz_localize("UTC")
        cached = cached_after or pub + pd.Timedelta(hours=1)
        row = {"item_id": f"it{k}", "url": f"https://example.invalid/{k}", "source_kind": "news",
               "first_seen_utc": pub.isoformat(), "published_utc": pub.isoformat(),
               "event_type": "earnings", "tickers": [t], "sentiment": 0.5, "injection_lines_removed": 0}
        out.append(json.dumps({"row": row, "cached_utc": pd.Timestamp(cached).isoformat()}))
    return out


def make_root(tmp: Path, n_days: int, *, news: int = 20, revisions: bool = True) -> Path:
    root = tmp / "optimus"
    (root / "prices_2025_26").mkdir(parents=True)
    make_bars(n_days).to_parquet(root / R.BARS_REL, index=False)
    anchor = DAYS[ANCHOR_I]
    if revisions:
        (root / "analyst").mkdir()
        make_revisions(anchor).to_parquet(root / R.REVISIONS_REL, index=False)
    if news:
        (root / "news_corpus/_digest_cache").mkdir(parents=True)
        (root / R.NEWS_REL).write_text("\n".join(news_lines(anchor, n=news)) + "\n", encoding="utf8")
    return root


def subset_specs(tmp: Path, per_family: int = 6) -> Path:
    full = json.loads(SPECS_V2.read_bytes())
    keep, seen = [], {}
    for s in full["specifications"]:
        if seen.get(s["family"], 0) < per_family or (s["family"] == "news_only" and s.get("event_type") == "earnings"
                                                     and seen.get("news_e", 0) < 3):
            if s["family"] == "news_only" and s.get("event_type") == "earnings":
                seen["news_e"] = seen.get("news_e", 0) + 1
            seen[s["family"]] = seen.get(s["family"], 0) + 1
            keep.append(s)
    full["specifications"] = keep
    p = tmp / "specs_v2_subset.json"
    p.write_text(json.dumps(full), encoding="utf8")
    return p


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(_config, "ROLLING_COHORT_ANCHOR", DAYS[ANCHOR_I].date().isoformat())
    monkeypatch.setattr(_config, "ROLLING_COHORT_REVISION_MIN_EVENTS", 10)
    monkeypatch.setattr(_config, "ROLLING_COHORT_NEWS_MIN_ITEMS", 5)
    monkeypatch.setattr(_config, "ROLLING_COHORT_RANDOM_CONTROLS", 3)


def run(mode, root, out, specs, now, **kw):
    return R.run(mode, data_root=root, out=out, specs_path=specs, now=now, calendar=FakeCal(), **kw)


def test_spec_file_is_the_v1_grid_plus_two_bar_families():
    specs, manifest = R.load_specs(SPECS_V2)
    fam = specs["counts"]["by_family"]
    assert fam["low_risk"] == 72 and fam["momentum_12_1"] == 72
    v1 = json.loads((ROOT / "docs/TRIALS/POPULATION-1000-SPECIFICATIONS.json").read_bytes())
    assert specs["parent_manifest_sha256"] == R.digest(v1)
    v1_ids = {s["policy_id"] for s in v1["specifications"] if s["family"] in R.V1_RUNNABLE}
    assert v1_ids <= {s["policy_id"] for s in specs["specifications"]}       # same specs, same ids
    assert not any(s["family"] == "no_news_control" for s in specs["specifications"])


def test_two_steps_on_one_day_birth_once(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 1)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    d = DAYS[ANCHOR_I]
    a = run("step", root, out, specs, utc(d))
    assert a["action"] == "BORN" and a["born"][0]["backfilled"] is False and a["rc"] == 0
    b = run("step", root, out, specs, utc(d, 23) + timedelta(minutes=30))
    assert b["born"] == [] and b["action"] == "NOTHING_DUE"
    assert len(list((out / "cohorts").glob("cohort_*.json"))) == 1
    rec = json.loads((out / "cohorts" / f"cohort_{d.date()}.json").read_bytes())
    assert rec["forward_evidence"] is True and rec["entry_session"] == DAYS[ANCHOR_I + 1].date().isoformat()
    assert rec["n_books"] > 0 and rec["n_distinct_portfolios"] <= rec["n_books"]


def test_a_step_after_the_entry_open_does_not_birth_forward(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 1)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    nxt = DAYS[ANCHOR_I + 1]
    r = run("step", root, out, specs, datetime.combine(nxt.date(), time(15, 0), tzinfo=timezone.utc))
    assert r["born"] == [] and r["missed"] and r["action"] == "MISSED_ENTRY_WINDOW"


def test_spec_edit_after_birth_is_refused(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 1)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    run("step", root, out, specs, utc(DAYS[ANCHOR_I]))
    doc = json.loads(specs.read_bytes())
    doc["specifications"][0]["max_names"] = 99                       # edited in place
    specs.write_text(json.dumps(doc), encoding="utf8")
    with pytest.raises(R.RollingCohortRefused, match="edited"):
        run("step", root, out, specs, utc(DAYS[ANCHOR_I]))
    doc = json.loads(specs.read_bytes())
    doc["specifications"][0]["max_names"] = json.loads(SPECS_V2.read_bytes())["specifications"][0]["max_names"]
    doc["specifications"] = doc["specifications"][1:]                 # a different grid
    specs.write_text(json.dumps(doc), encoding="utf8")
    with pytest.raises(R.RollingCohortRefused, match="changed after birth"):
        run("step", root, out, specs, utc(DAYS[ANCHOR_I]))


def _books(out: Path, cohort) -> list:
    rec = json.loads((out / "cohorts" / f"cohort_{pd.Timestamp(cohort).date()}.json").read_bytes())
    return [(b["policy_id"], b["status"], b.get("holdings_hash"), b.get("inputs_hash"),
             json.dumps(b.get("long"), sort_keys=True)) for b in rec["books"]], rec


def test_backfill_never_reads_a_row_dated_on_or_after_the_entry(tmp_path):
    d, e = DAYS[ANCHOR_I], DAYS[ANCHOR_I + 1]
    clean = make_root(tmp_path / "clean", ANCHOR_I + 26)
    poison = make_root(tmp_path / "poison", ANCHOR_I + 26)
    bars = pd.read_parquet(poison / R.BARS_REL)
    after = (bars["date"] > d) & bars["symbol"].isin(["S00", "S05", "S31"])
    bars.loc[after, ["open", "close"]] *= 25.0                         # future prices: marks only
    bars.to_parquet(poison / R.BARS_REL, index=False)
    rv = pd.read_parquet(poison / R.REVISIONS_REL)
    late = []
    for f in range(12):                                               # dated on/after D, or first seen after the cutoff
        late.append(dict(ticker="S40", event_date=str(d + pd.Timedelta(hours=15)), firm=f"P{f}", target_action="Raises",
                         prior_target=10.0, current_target=30.0, pit_safe=True,
                         first_seen_utc=(d + pd.Timedelta(hours=16)).tz_localize("UTC").isoformat()))
        late.append(dict(ticker="S41", event_date=str(d - pd.Timedelta(days=1)), firm=f"P{f}", target_action="Raises",
                         prior_target=10.0, current_target=30.0, pit_safe=True,
                         first_seen_utc=(e + pd.Timedelta(hours=1)).tz_localize("UTC").isoformat()))
    pd.concat([rv, pd.DataFrame(late)], ignore_index=True).to_parquet(poison / R.REVISIONS_REL, index=False)
    with (poison / R.NEWS_REL).open("a", encoding="utf8") as f:
        f.write("\n".join(news_lines(d, n=40, cached_after=e + pd.Timedelta(hours=2))).replace('"it', '"late') + "\n")
    specs = subset_specs(tmp_path, per_family=10)
    now = utc(DAYS[ANCHOR_I + 30])
    for root, name in ((clean, "a"), (poison, "b")):
        run("backfill", root, tmp_path / name, specs, now, date_from=d, date_to=d)
    ba, ra = _books(tmp_path / "a", d)
    bb, rb = _books(tmp_path / "b", d)
    assert ba == bb and ra["input_hashes"] == rb["input_hashes"]
    assert ra["backfilled"] is True and ra["forward_evidence"] is False
    held = {t for b in rb["books"] if b["status"] == "READY" and b["family"] not in R.BAR_FAMILIES
            for t in b["long"]}
    assert not held & {"S40", "S41"}                                  # only the poisoned rows name them
    assert any(b["status"] == "READY" and b["family"] in ("revision_flow", "net_raises") for b in rb["books"])


def test_wait_input_rows_are_written_with_their_counts(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 1, news=0, revisions=False)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    run("step", root, out, specs, utc(DAYS[ANCHOR_I]))
    _, rec = _books(out, DAYS[ANCHOR_I])
    waits = [b for b in rec["books"] if b["status"] == "WAIT_INPUT"]
    fams = {b["family"] for b in waits}
    assert {"news_only", "revision_flow", "net_raises", "hybrid_news_revision"} <= fams
    news = next(b for b in waits if b["family"] == "news_only")
    assert news["why"]["news"]["n_items_5d"] == 0 and news["why"]["news"]["min_items_5d"] == 5
    assert rec["input_status"]["revision"]["status"] == "WAIT_INPUT"
    assert any(b["status"] == "READY" and b["family"] in R.BAR_FAMILIES for b in rec["books"])


def test_controls_dedupe_and_seeds(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 1)
    specs, out = subset_specs(tmp_path, per_family=24), tmp_path / "out"
    run("step", root, out, specs, utc(DAYS[ANCHOR_I]))
    _, rec = _books(out, DAYS[ANCHOR_I])
    ready = [b for b in rec["books"] if b["status"] == "READY"]
    distinct = {b["holdings_hash"] for b in ready}
    assert rec["n_distinct_portfolios"] == len(distinct) < len(ready)
    assert len(rec["controls"]) == 3 * len(distinct)
    market = pd.read_parquet(out / "inputs" / (rec["input_snapshot_prefix"] + ".market.parquet")).set_index("symbol")
    by_hash = {b["holdings_hash"]: b for b in ready}
    for c in rec["controls"]:
        parent = by_hash[c["parent_holdings_hash"]]
        assert c["seed"] > 2 ** 40 and not set(c["long"]) & set(parent["long"])
        assert sorted(c["long"].values()) == pytest.approx(sorted(parent["long"].values()))
        if c["band_fallbacks"] == 0:
            assert sorted(market.loc[list(c["long"]), "band"]) == sorted(market.loc[list(parent["long"]), "band"])
    assert any(c["band_fallbacks"] == 0 for c in rec["controls"])
    hedged = [b for b in ready if b["family"] == "momentum_12_1" and b["params"]["hedge"] == "spy_beta"]
    assert hedged and all(b["short"] > 0 and b["invested_share"] < b["gross_long"] for b in hedged)


def test_marks_table_is_append_only_and_honest(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 31)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    now = utc(DAYS[ANCHOR_I + 31])
    r1 = run("backfill", root, out, specs, now, date_from=DAYS[ANCHOR_I])
    assert len(r1["born"]) >= 5 and all(b["backfilled"] for b in r1["born"])
    m = pd.read_parquet(next((out / "marks").glob("part-*.parquet")))
    assert {"excess_same_share", "spy_ret", "beta_window", "beta_se", "inputs_hash", "cost_charged",
            "holdings_hash", "params_json", "backfilled"} <= set(m.columns)
    b = m[m["kind"] == "book"]
    assert np.allclose(b["excess_same_share"], b["ret_net"] - b["control_same_share_net"])
    assert (b["cost_charged"] > 0).all() and b["backfilled"].all()
    hedged = b[b["family"] == "momentum_12_1"]
    assert (m["kind"] == "random_control").any() and b["excess_vs_random"].notna().any()
    r2 = run("step", root, out, specs, now + timedelta(minutes=5))
    assert r2["marks_written"] == 0 and r2["born"] == []
    assert r2["scoreboard"] == r1["scoreboard"]                   # an idle step does not copy the board
    assert len(list(out.glob("scoreboard_*.json"))) == 1
    allm = R.Store(out).marks()
    assert not allm.duplicated(["book_id", "mark_k"]).any()
    board = json.loads(Path(r2["scoreboard"]).read_bytes())["boards"]["21"]
    assert board["specs"] == []                                   # forward view: backfill excluded
    assert board["specs_all"] and all(s["label"].startswith("OBSERVED(") for s in board["specs_all"])
    assert all(s["verdict"].startswith("CANNOT DETERMINE") or s["mde"] is not None for s in board["specs_all"])
    # a hedged momentum book pays SPY cost and borrow on its short leg
    if len(hedged):
        h = hedged[hedged["gross_short"] > 0]
        assert (h["cost_charged"] > 0).all()


def test_evening_price_wait_is_a_wait_with_rc_0(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 3)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    # the session after the last bar has CLOSED, the bars do not have it yet
    r = run("step", root, out, specs, utc(DAYS[ANCHOR_I + 3], 22))
    assert r["action"] == "WAIT_PRICES" and r["rc"] == 0 and r["prices_waiting"] is True


def test_missing_bars_is_a_refusal(tmp_path):
    with pytest.raises(R.RollingCohortRefused):
        R.load_bars(tmp_path / "nowhere", start="2024-01-01", end="2024-12-31")


def test_cli_refusal_exits_non_zero(tmp_path, capsys):
    from scripts import rolling_cohorts as CLI
    rc = CLI.main(["step", "--data-root", str(tmp_path / "optimus"), "--out", str(tmp_path / "out"),
                   "--specs", str(tmp_path / "absent.json")])
    assert rc == 2 and "REFUSED" in capsys.readouterr().out
    with pytest.raises(R.RollingCohortRefused):
        CLI.output_dir(tmp_path / "optimus", tmp_path / "optimus" / "analyst")
    assert CLI.output_dir(tmp_path / "optimus", None) == (tmp_path / "optimus" / "rolling_cohorts").resolve()
