"""Chunk B -- the source/actor graph. Offline; nothing here touches the network."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from backend.services import source_registry as SR

REPO = Path(__file__).resolve().parents[2]


def _now_minus(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def _write_reg(path: Path, rows: list[dict]) -> Path:
    path.write_text(yaml.safe_dump({"sources": rows}), encoding="utf-8")
    return path


# ── registry ────────────────────────────────────────────────────────────────
def test_registry_loads(tmp_path):
    p = _write_reg(tmp_path / "r.yaml", [
        {"source_id": "news:x", "kind": "newswire"},
        {"source_id": "x:acme", "kind": "company", "handle": "@acme", "platform": "x",
         "verified": False, "tickers_covered": ["acme"]}])
    reg = SR.load_registry(p)
    assert set(reg) == {"news:x", "x:acme"}
    assert reg["x:acme"].tickers_covered == ("ACME",)
    assert reg["x:acme"].verified is False


def test_registry_refuses_source_with_no_kind(tmp_path):
    p = _write_reg(tmp_path / "r.yaml", [{"source_id": "news:x", "kind": "newswire"},
                                         {"source_id": "x:nokind", "handle": "@nokind"}])
    with pytest.raises(SR.RegistryRefused, match="no kind"):
        SR.load_registry(p)


def test_registry_refuses_unknown_kind_and_duplicates(tmp_path):
    with pytest.raises(SR.RegistryRefused):
        SR.load_registry(_write_reg(tmp_path / "a.yaml", [{"source_id": "s", "kind": "guru"}]))
    with pytest.raises(SR.RegistryRefused, match="duplicate"):
        SR.load_registry(_write_reg(tmp_path / "b.yaml", [{"source_id": "s", "kind": "filing"},
                                                          {"source_id": "s", "kind": "filing"}]))


def test_save_roundtrip(tmp_path):
    s = SR.x_source("@AcmeIR", kind="company", tickers=["ACME"], quest_id="q1")
    p = SR.save_registry({s.source_id: s}, tmp_path / "r.yaml")
    assert SR.load_registry(p)[s.source_id] == s


def test_shipped_registry_loads_if_present():
    if not SR.REGISTRY_PATH.exists():
        pytest.skip("registry not seeded on this checkout")
    reg = SR.load_registry()
    assert reg and all(s.kind in SR.KINDS for s in reg.values())
    # every X handle a quest proposed is unverified until a dated post verified it
    for s in reg.values():
        if s.platform == "x" and s.found_by_quest:
            assert s.verified == bool(s.verified_by)


# ── an X handle from a quest is unverified until a dated post exists ────────
def test_quest_handle_is_unverified_until_dated_post():
    s = SR.x_source("acme_ir", kind="company", quest_id="discover:2026-09-26:t")
    assert s.verified is False and s.handle == "@acme_ir"
    # no post, undated post, future post, another handle's post: still unverified
    assert SR.verify_with_posts(s, []).verified is False
    assert SR.verify_with_posts(s, [{"post_url": "https://x.com/acme_ir/status/1",
                                     "posted_utc": ""}]).verified is False
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert SR.verify_with_posts(s, [{"post_url": "https://x.com/acme_ir/status/1",
                                     "posted_utc": future}]).verified is False
    assert SR.verify_with_posts(s, [{"post_url": "https://x.com/someone_else/status/1",
                                     "posted_utc": _now_minus(3)}]).verified is False
    v = SR.verify_with_posts(s, [{"post_url": "https://x.com/Acme_IR/status/123",
                                  "posted_utc": _now_minus(3)}])
    assert v.verified is True and "status/123" in v.verified_by


def test_x_source_refuses_bad_handle():
    with pytest.raises(SR.RegistryRefused):
        SR.x_source("not a handle!", kind="company", quest_id="q")


# ── claims -> exactly one row per hash, never twice ─────────────────────────
def test_claim_writes_exactly_one_row_per_hash(tmp_path):
    led, cl = tmp_path / "pred.jsonl", tmp_path / "claims.jsonl"
    claim = {"source_id": "x:acme", "source_kind": "company", "ticker": "NVDA",
             "claim_text": "Record data-centre bookings", "claim_utc": _now_minus(5),
             "direction": "up", "horizon_days": 5}
    r1 = SR.write_claims([claim], path=led, claims_path=cl)
    assert r1["n_rows_written"] == 1 and r1["n_new_claims"] == 1
    r2 = SR.write_claims([claim, dict(claim)], path=led, claims_path=cl)
    assert r2["n_rows_written"] == 0 and r2["n_duplicate_claims"] == 2
    rows = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    r = rows[0]
    assert r["specialist"] == "source:x:acme"
    assert r["observable"] == "beats_benchmark" and r["benchmark"] == "SPY"
    assert r["probability"] == pytest.approx(0.60)
    assert r["inputs_used"]["claim_hash"] == SR.claim_hash("x:acme", "NVDA",
                                                           claim["claim_text"], claim["claim_utc"])
    assert len(SR.read_claims(cl)) == 1


def test_claim_probability_by_direction_and_no_direction_is_not_a_forecast():
    t = _now_minus(2)
    down = SR.claim_rows("x:a", "MU", "guide cut", t, direction="bearish", horizon_days=1)
    assert len(down) == 1 and down[0]["probability"] == pytest.approx(0.40)
    assert SR.claim_rows("x:a", "MU", "just a chart", t, direction="none", horizon_days=1) == []
    assert SR.claim_rows("x:a", "MU", "undated", "", direction="up", horizon_days=1) == []
    three = SR.claim_rows("x:a", "MU", "beat", t, direction="up")
    assert sorted(r["horizon_days"] for r in three) == list(SR.SCORE_HORIZONS)
    assert len({r["input_snapshot_hash"] for r in three}) == 1


def test_claim_dated_after_it_was_read_is_refused():
    made = _now_minus(10)
    assert SR.claim_rows("x:a", "MU", "later", _now_minus(1), direction="up",
                         horizon_days=1, made_at=made) == []


# ── the crowding/reversal signature ─────────────────────────────────────────
def test_crowding_signature_from_synthetic_path():
    # names pop +4% over 5 sessions then fade to -1% by 21: signature = -5%
    pop = SR.crowding_signature([0.04] * 12, [-0.01] * 12)
    assert pop["signature"] == pytest.approx(-0.05)
    assert pop["use_as"] == "reversal"
    # a drift that keeps going is not a reversal
    drift = SR.crowding_signature([0.01] * 12, [0.03] * 12)
    assert drift["signature"] == pytest.approx(0.02) and drift["use_as"] == "attention"
    # too few claims -> still a prior
    assert SR.crowding_signature([0.04] * 3, [-0.01] * 3)["use_as"] == "prior"
    assert SR.crowding_signature([], [])["signature"] is None


def test_crowding_signature_computed_from_bars_path():
    dates = pd.bdate_range("2026-01-05", periods=40)
    spy = np.full(40, 100.0)
    name = np.full(40, 100.0)
    # entry is the first session after the claim date (index 1); pop to +5% by
    # index 6 (5 sessions), fade to -2% by index 22 (21 sessions)
    name[2:7] = np.linspace(101, 105, 5)
    name[7:] = 98.0
    bars = pd.concat([
        pd.DataFrame({"symbol": "SPY", "date": dates, "close": spy}),
        pd.DataFrame({"symbol": "POP", "date": dates, "close": name})])
    claims = pd.DataFrame([{"source_id": "x:hype", "ticker": "POP",
                            "claim_utc": "2026-01-05T15:00:00Z", "direction": "up"}] * 12)
    rel = SR.forward_relative_returns(claims, bars)
    assert rel["rel_5d"].iloc[0] == pytest.approx(0.05)
    assert rel["rel_21d"].iloc[0] == pytest.approx(-0.02)
    reg = {"x:hype": SR.Source(source_id="x:hype", kind="retail_influencer", platform="x")}
    sb = SR.score(reg, claims=claims.to_dict("records"), ledger_rows=[], bars=bars,
                  mainstream=pd.DataFrame(columns=["ticker", "source_id", "t"]))
    row = sb["rows"][0]
    assert row["crowding_signature"] == pytest.approx(-0.07)
    assert row["use_as"] == "reversal"
    assert row["false_positive_rate_21d"] == pytest.approx(1.0)
    assert row["weight"] == "prior"


def test_every_source_starts_at_n0_weight_prior():
    reg = {"news:a": SR.Source(source_id="news:a", kind="newswire"),
           "sell_side:ms": SR.Source(source_id="sell_side:ms", kind="sell_side")}
    sb = SR.score(reg, claims=[], ledger_rows=[])
    assert sb["n_sources"] == 2
    for r in sb["rows"]:
        assert r["n_claims"] == 0 and r["weight"] == "prior" and r["use_as"] == "prior"


def test_lead_time_positive_when_source_is_first():
    claims = pd.DataFrame([{"source_id": "x:a", "ticker": "MU", "claim_utc": "2026-09-20T10:00:00Z"}])
    ms = pd.DataFrame([{"ticker": "MU", "source_id": "news:wire",
                        "t": pd.Timestamp("2026-09-20T16:00:00Z")},
                       {"ticker": "MU", "source_id": "news:wire",
                        "t": pd.Timestamp("2026-09-25T16:00:00Z")}])   # outside 48h
    assert SR.lead_times_h(claims, ms).iloc[0] == pytest.approx(6.0)


def test_skill_keyed_by_source_id():
    rows = []
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for i in range(40):
        y = i % 2
        rows.append({"specialist": "source:x:good", "probability": 0.6 if y else 0.4,
                     "outcome": bool(y), "made_at": (base + timedelta(days=i)).isoformat(),
                     "horizon_days": 5, "observable": "beats_benchmark", "ticker": "MU",
                     "benchmark": "SPY"})
    reg = {"x:good": SR.Source(source_id="x:good", kind="industry_specialist", platform="x")}
    sb = SR.score(reg, claims=[], ledger_rows=rows)
    r = sb["rows"][0]
    assert r["n_graded_h5"] == 40 and r["skill_h5"] > 0
    assert r["weight_status"] == "earned"


# ── never an order ──────────────────────────────────────────────────────────
def _names_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


@pytest.mark.parametrize("rel", ["backend/services/source_registry.py", "scripts/source_reads.py"])
def test_no_code_path_calls_pc_broker(rel):
    names = _names_in(REPO / rel)
    assert not any("pc_broker" in n for n in names), f"{rel} reaches the broker"
    assert not {"submit_order", "place_order"} & names


# ── the read script: EMPTY_READ, never silent ───────────────────────────────
def test_source_read_logs_empty_read_and_writes_claims(tmp_path, monkeypatch):
    from scripts import source_reads as S
    reg_p = tmp_path / "registry.yaml"
    a = SR.x_source("acme_ir", kind="company", tickers=["NVDA"], quest_id="q")
    b = SR.x_source("quiet_one", kind="journalist", tickers=["NVDA"], quest_id="q")
    SR.save_registry({a.source_id: a, b.source_id: b}, reg_p)
    monkeypatch.setattr(SR, "SOURCES_DIR", tmp_path)
    posted = _now_minus(6)

    def fake_turn(prompt, *, purpose, **kw):
        assert "READ-ONLY" in prompt
        return {"status": "OK", "cost_usd": 0.01, "reply": json.dumps({"reads": [
            {"handle": "@acme_ir", "status": "OK", "posts": [
                {"post_url": "https://x.com/acme_ir/status/9", "posted_utc": posted,
                 "ticker": "$NVDA", "claim": "Shipping ahead of plan", "direction": "up",
                 "event_type": "product_launch"}]},
            {"handle": "@quiet_one", "status": "EMPTY", "posts": []}]})}

    rc = S.run_reads(turn_fn=fake_turn, registry_path=reg_p, ledger_path=tmp_path / "p.jsonl",
                     claims_path=tmp_path / "c.jsonl", write_events=False,
                     tickers=["NVDA", "MU", "AAPL"])
    st = {p["handle"]: p["status"] for p in rc["per_source"]}
    assert st == {"@acme_ir": "OK", "@quiet_one": "EMPTY_READ"}
    assert rc["n_claims"] == 1 and rc["forecast_rows"]["n_rows_written"] == 3
    reg = SR.load_registry(reg_p)
    assert reg["x:acme_ir"].verified is True
    assert reg["x:quiet_one"].verified is False
    ev = S.web_event_row(reg["x:acme_ir"], {"post_url": "https://x.com/acme_ir/status/9",
                                            "posted_utc": posted, "ticker": "NVDA",
                                            "claim": "Shipping", "direction": "up",
                                            "event_type": "product_launch"}, observed_at=SR._now())
    from backend.services import web_events as WE
    assert WE.validate(ev)["source_type"] == "x"


def test_source_read_cap_is_logged_not_skipped(tmp_path, monkeypatch):
    from scripts import source_reads as S
    reg_p = tmp_path / "registry.yaml"
    srcs = [SR.x_source(f"h{i}", kind="journalist", quest_id="q") for i in range(9)]
    SR.save_registry({s.source_id: s for s in srcs}, reg_p)
    monkeypatch.setattr(SR, "SOURCES_DIR", tmp_path)
    calls = []

    def fake_turn(prompt, *, purpose, **kw):
        calls.append(1)
        return {"status": "OK", "cost_usd": 0.0, "reply": "{\"reads\": []}"}

    rc = S.run_reads(turn_fn=fake_turn, registry_path=reg_p, max_quests=1,
                     ledger_path=tmp_path / "p.jsonl", claims_path=tmp_path / "c.jsonl",
                     write_events=False, tickers=["NVDA"])
    assert len(calls) == 1
    st = [p["status"] for p in rc["per_source"]]
    assert len(st) == 9
    assert st.count("NOT_READ_CAP_QUESTS") == 9 - S.HANDLES_PER_QUEST
    assert all(s in ("NO_REPLY_FOR_SOURCE", "NOT_READ_CAP_QUESTS") for s in st)


def test_login_wall_is_a_refusal_not_an_empty_read(tmp_path, monkeypatch):
    """2026-09-26: all 7 discovery quests hit X's login wall and were first
    receipted as 'OK found 0'. An unread source is not an empty one."""
    from scripts import source_reads as S
    reg_p = tmp_path / "registry.yaml"
    srcs = [SR.x_source(f"h{i}", kind="journalist", quest_id="q") for i in range(8)]
    SR.save_registry({s.source_id: s for s in srcs}, reg_p)
    monkeypatch.setattr(SR, "SOURCES_DIR", tmp_path)
    calls = []

    def walled(prompt, *, purpose, **kw):
        calls.append(1)
        return {"status": "OK", "cost_usd": 0.005, "reply": json.dumps(
            {"searched": False, "blocker": "redirected to x.com/i/jf/onboarding/web?mode=login"})}

    rc = S.run_reads(turn_fn=walled, registry_path=reg_p, ledger_path=tmp_path / "p.jsonl",
                     claims_path=tmp_path / "c.jsonl", write_events=False, tickers=["NVDA"])
    assert len(calls) == 1                       # stops after the first wall
    assert rc["login_wall"]
    assert {p["status"] for p in rc["per_source"]} == {"NOT_READ_LOGIN_WALL"}
    assert "EMPTY_READ" not in {p["status"] for p in rc["per_source"]}
    SR.save_registry({s.source_id: s for s in srcs}, reg_p)
    dc = S.run_discovery(turn_fn=walled, registry_path=reg_p, day="2026-09-26")
    assert dc["quests"][0]["status"] == "REFUSED_LOGIN_WALL"
    assert all(q["status"] == "NOT_RUN_LOGIN_WALL" for q in dc["quests"][1:])


# ── the broker scoreboard (adjudication row 13) ─────────────────────────────
def _broker_fixture(tmp_path):
    """A synthetic panel and revisions parquet with known answers.

    40 sessions; UNI1..UNI4 flat (universe median return 0); WIN rises 1%/session,
    LOS falls 1%/session. GoodCo raises WIN and lowers LOS (always right);
    BadCo does the opposite (always wrong). A 3-firm cluster on WIN: Early
    (day 1), Mid (day 4), Late (day 8)."""
    dates = pd.bdate_range("2026-01-05", periods=60)
    rows = []
    for s, f in (("UNI1", 0.0), ("UNI2", 0.0), ("UNI3", 0.0), ("UNI4", 0.0),
                 ("WIN", 0.01), ("LOS", -0.01)):
        px = 100.0 * (1 + f) ** np.arange(len(dates))
        rows.append(pd.DataFrame({"symbol": s, "date": dates, "close": px}))
    bars = pd.concat(rows, ignore_index=True)
    rev = []

    def add(t, firm, ticker, ta, action="main"):
        rev.append({"ticker": ticker, "pulled_at": "2026-09-01T00:00:00+00:00",
                    "event_date": str(t), "firm": firm, "from_grade": "", "to_grade": "",
                    "action": action, "target_action": ta, "prior_target": 1.0,
                    "current_target": 1.1, "target_change": 0.1, "pit_safe": True})

    for i in range(0, 30, 2):
        add(dates[i] + pd.Timedelta(hours=14), "GoodCo", "WIN", "Raises")
        add(dates[i] + pd.Timedelta(hours=14), "GoodCo", "LOS", "Lowers")
        add(dates[i + 1] + pd.Timedelta(hours=14), "BadCo", "WIN", "Lowers")
        add(dates[i + 1] + pd.Timedelta(hours=14), "BadCo", "LOS", "Raises")
    add(dates[40] + pd.Timedelta(hours=14), "Early", "UNI1", "Raises")
    add(dates[43] + pd.Timedelta(hours=14), "Mid", "UNI1", "Raises")
    add(dates[47] + pd.Timedelta(hours=14), "Late", "UNI1", "Raises")
    add(dates[5], "Mixed", "WIN", "Raises", action="down")          # MIXED: not directional
    add("2026-10-05 10:00:00", "Future", "WIN", "Raises")            # after its own pull
    p = tmp_path / "rev.parquet"
    pd.DataFrame(rev).to_parquet(p)
    return bars, p, dates


def test_broker_direction_rules():
    assert SR.broker_direction("Raises", "main") == "up"
    assert SR.broker_direction("Lowers", "reit") == "down"
    assert SR.broker_direction("Maintains", "up") == "up"
    assert SR.broker_direction("Raises", "down") is None           # mixed
    assert SR.broker_direction("Announces", "init") is None


def test_broker_scoreboard_hit_rate_on_synthetic_parquet(tmp_path):
    bars, p, dates = _broker_fixture(tmp_path)
    claims, rc = SR.load_revision_claims(p, today="2026-09-26")
    assert rc["n_refused_future"] + rc["n_refused_after_pull"] == 1
    assert claims["direction"].isna().sum() == 1                    # the mixed row
    d, syms, rel = SR.relative_forward_returns(bars)
    c = SR.attach_outcomes(claims, d, syms, rel)
    # entry is the first session AFTER the claim date; WIN beats the flat median
    w = c[(c["firm"] == "GoodCo") & (c["ticker"] == "WIN")].iloc[0]
    assert w["entry"] == dates[1]
    assert w["rel_5d"] == pytest.approx(1.01 ** 5 - 1, rel=1e-4)
    # a claim before the panel starts is not priced at its first session
    early = pd.DataFrame([{"ticker": "WIN", "firm": "X", "source_id": "sell_side:x",
                           "t": pd.Timestamp("2015-06-01"), "direction": "up"}])
    assert np.isnan(SR.attach_outcomes(early, d, syms, rel)["rel_5d"].iloc[0])
    sb = SR.broker_scoreboard(c, today="2026-09-26", rank_min_n=10, weight_min_n=5)
    f = {r["source_id"]: r for r in sb["firms"]}
    assert f["sell_side:goodco"]["hit_5d"] == pytest.approx(1.0)
    assert f["sell_side:goodco"]["hit_21d"] == pytest.approx(1.0)
    assert f["sell_side:badco"]["hit_21d"] == pytest.approx(0.0)
    assert f["sell_side:goodco"]["rel_21d_after_raise"] > 0 > f["sell_side:goodco"]["rel_21d_after_lower"]
    assert sb["top"][0] == "sell_side:goodco" and sb["bottom"][0] == "sell_side:badco"
    assert f["sell_side:goodco"]["weight_status"] == "earned"
    n = f["sell_side:goodco"]["n_heldout_21d"]
    assert f["sell_side:goodco"]["weight"] == pytest.approx(1.0 * n / (n + 200), rel=1e-3)
    assert f["sell_side:badco"]["weight"] == 0.0                     # floored, never negative
    assert f["sell_side:early"]["weight"] == "prior"                 # n < min
    assert "2026" in f["sell_side:goodco"]["by_year"]


def test_first_mover_rank_and_pit_class(tmp_path):
    bars, p, dates = _broker_fixture(tmp_path)
    claims, _ = SR.load_revision_claims(p, today="2026-09-26")
    uni = claims[claims["ticker"] == "UNI1"]
    cl = SR.assign_clusters(uni)
    ranks = dict(zip(cl["firm"], cl["cluster_rank"]))
    assert ranks == {"Early": 1, "Mid": 2, "Late": 3}
    assert set(cl["cluster_size"]) == {3}
    # a pair of firms is not a cluster
    assert SR.assign_clusters(uni[uni["firm"] != "Late"]).empty
    # PIT: the class uses only earlier claims by OTHER firms within the window
    n_prior = SR.prior_firm_counts(uni)
    got = dict(zip(uni["firm"], n_prior.loc[uni.index]))
    assert got == {"Early": 0, "Mid": 1, "Late": 2}
    d, syms, rel = SR.relative_forward_returns(bars)
    c = SR.attach_outcomes(claims, d, syms, rel)
    fm = SR.first_mover_table(SR.assign_clusters(c), h=5)
    assert fm["n_clusters"] >= 1 and "first_minus_last_all" in fm
    pit = SR.pit_first_vs_follower(c)
    assert set(pit["5"]["by_class"]) >= {"first"}


def test_apply_broker_weights_writes_registry(tmp_path):
    reg = {"sell_side:goodco": SR.Source(source_id="sell_side:goodco", kind="sell_side"),
           "sell_side:thin": SR.Source(source_id="sell_side:thin", kind="sell_side", weight=0.3)}
    board = {"asof": "2026-09-26", "heldout_split_date": "2025-05-06", "firms": [
        {"source_id": "sell_side:goodco", "weight_status": "earned", "weight": 0.05,
         "skill_heldout_21d": 0.1, "n_heldout_21d": 200},
        {"source_id": "sell_side:thin", "weight_status": "prior (held-out n=3 < 20)", "weight": "prior"}]}
    out, res = SR.apply_broker_weights(reg, board)
    assert out["sell_side:goodco"].weight == 0.05 and "held-out" in out["sell_side:goodco"].weight_basis
    assert out["sell_side:thin"].weight is None                      # back to prior, not stale
    assert res == {"n_earned": 1, "n_prior": 1, "n_not_in_registry": 0}
    p = SR.save_registry(out, tmp_path / "r.yaml")
    assert SR.load_registry(p)["sell_side:goodco"].weight == 0.05


# ── X handle timelines (adjudication row 10) ────────────────────────────────
def _timeline_reg(tmp_path):
    reg_p = tmp_path / "registry.yaml"
    a = SR.x_source("Jukanlosreve", kind="industry_specialist", tickers=["MU"], quest_id="")
    b = SR.x_source("quiet_one", kind="journalist", tickers=["MU"], quest_id="")
    SR.save_registry({a.source_id: a, b.source_id: b}, reg_p)
    return reg_p


def test_timeline_read_with_dated_claims_marks_the_handle_verified(tmp_path, monkeypatch):
    from scripts import source_reads as S
    reg_p = _timeline_reg(tmp_path)
    monkeypatch.setattr(SR, "SOURCES_DIR", tmp_path)
    posted = _now_minus(30)
    seen = []

    def fake_turn(prompt, *, purpose, **kw):
        seen.append(prompt)
        return {"status": "OK", "cost_usd": 0.01, "reply": json.dumps({"searched": True, "reads": [
            {"handle": "@Jukanlosreve", "status": "OK",
             "latest_post_url": "https://x.com/Jukanlosreve/status/77", "latest_post_utc": posted,
             "posts": [{"post_url": "https://x.com/Jukanlosreve/status/77", "posted_utc": posted,
                        "ticker": "MU", "claim": "Samsung HBM4 qual slips again", "direction": "up",
                        "event_type": "supplier_constraint"},
                       {"post_url": "https://x.com/Jukanlosreve/status/78", "posted_utc": posted,
                        "ticker": "MU", "claim": "DRAM contract talks ongoing", "direction": "none"}]},
            {"handle": "@quiet_one", "status": "EMPTY", "posts": []}]})}

    rc = S.run_timeline_reads(turn_fn=fake_turn, registry_path=reg_p, ledger_path=tmp_path / "p.jsonl",
                              claims_path=tmp_path / "c.jsonl", write_events=False, tickers=["MU"])
    assert "https://x.com/Jukanlosreve" in seen[0] and "x.com/search" not in seen[0]
    st = {p["handle"]: p["status"] for p in rc["per_source"]}
    assert st == {"@Jukanlosreve": "OK", "@quiet_one": "EMPTY_READ"}
    assert rc["n_claims"] == 2 and rc["n_directional_claims"] == 1
    assert rc["forecast_rows"]["n_rows_written"] == len(SR.SCORE_HORIZONS)   # the directed one only
    assert rc["forecast_rows"]["n_no_direction"] == 1
    reg = SR.load_registry(reg_p)
    assert reg["x:jukanlosreve"].verified is True and "status/77" in reg["x:jukanlosreve"].verified_by
    assert reg["x:quiet_one"].verified is False
    assert (tmp_path / f"timelines_{rc['day']}.json").exists()


def test_timeline_login_wall_is_its_own_status_and_stops_spend(tmp_path, monkeypatch):
    from scripts import source_reads as S
    reg_p = tmp_path / "registry.yaml"
    srcs = [SR.x_source(f"h{i}", kind="journalist", quest_id="") for i in range(8)]
    SR.save_registry({s.source_id: s for s in srcs}, reg_p)
    monkeypatch.setattr(SR, "SOURCES_DIR", tmp_path)
    calls = []

    def walled(prompt, *, purpose, **kw):
        calls.append(1)
        return {"status": "OK", "cost_usd": 0.005, "reply": json.dumps(
            {"searched": False, "blocker": "redirected to x.com/i/flow/login"})}

    rc = S.run_timeline_reads(turn_fn=walled, registry_path=reg_p, ledger_path=tmp_path / "p.jsonl",
                              claims_path=tmp_path / "c.jsonl", write_events=False, tickers=["MU"])
    assert len(calls) == S.TIMELINE_WALL_STOP
    assert {p["status"] for p in rc["per_source"]} == {"NOT_READ_LOGIN_WALL"}
    assert rc["login_wall"] and rc["n_claims"] == 0
    assert not any(s.verified for s in SR.load_registry(reg_p).values())


def test_timeline_per_handle_wall_and_not_found(tmp_path, monkeypatch):
    from scripts import source_reads as S
    reg_p = _timeline_reg(tmp_path)
    monkeypatch.setattr(SR, "SOURCES_DIR", tmp_path)

    def mixed(prompt, *, purpose, **kw):
        return {"status": "OK", "cost_usd": 0.0, "reply": json.dumps({"searched": True, "reads": [
            {"handle": "@Jukanlosreve", "status": "LOGIN_WALL", "posts": []},
            {"handle": "@quiet_one", "status": "NOT_FOUND", "posts": []}]})}

    rc = S.run_timeline_reads(turn_fn=mixed, registry_path=reg_p, ledger_path=tmp_path / "p.jsonl",
                              claims_path=tmp_path / "c.jsonl", write_events=False, tickers=["MU"])
    st = {p["handle"]: p["status"] for p in rc["per_source"]}
    assert st == {"@Jukanlosreve": "NOT_READ_LOGIN_WALL", "@quiet_one": "NOT_FOUND"}


def test_timeline_seed_is_unverified_and_covers_the_reviewer_list():
    from scripts import source_reads as S
    seeds = S.timeline_seed_sources()
    hs = {s.handle for s in seeds}
    assert {"@dylan522p", "@Jukanlosreve", "@adamfeuerstein", "@DeItaone", "@muddywatersre"} <= hs
    assert all(s.platform == "x" and s.verified is False for s in seeds)
    assert len({h for h, *_ in S.SPECIALIST_HANDLES}) == len(S.SPECIALIST_HANDLES)
