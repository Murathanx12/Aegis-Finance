"""The C19 legibility routers (Paper Arena, Forecast Lab, Theory Lab, System Health):
404 / 422 / 500 / shape / age, and the deny-by-default sanitiser on WHOLE payloads. Offline.

Every receipt is constructed in tmp_path in the shape of the real receipts, POISONED with
fake secrets (account numbers, dollar equity, a user-home path, PIDs, ports, credential
env-var names, broker URLs, a paywalled publisher's reader and page counts). The whole
serialized response is then grepped: none of it may reach a browser. Every date is derived
from `now`, never a calendar literal (protocol item 5).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config as _config
from backend.routers import arena_v1 as RA
from backend.routers import legibility_v1 as RL
from backend.services import legibility as L
from backend.services import legibility_sanitise as S

NOW = datetime.now(timezone.utc).replace(microsecond=0)
HOME = r"C:\Users\someone\aegis-finance\backend\data\optimus\x.json"

#: Nothing matching any of these may appear in a served payload.
DENY_PATTERNS = {
    "account number": r"PA9SECRET0001",
    "user home": r"someone|C:\\\\|C:/",
    "pid": r"\bpid \d",
    "loopback/port": r"127\.0\.0\.1|:18789|:8080",
    "credential env": r"FAKE_BROKER_KEY_ID|REDDIT_KEYS_ABSENT|AAT_HACK9_",
    "dot env": r"\.env\b",
    "dollar keys": r'"(equity|cash|start_capital|sum_equity|sum_start_capital|pnl|last_equity|buying_power)"',
    "equity value": r"123456\.78|98765\.43",
    "publisher": r"(?i)dow ?jones|barron",
    "page counts": r"14347",
    "owner personal": r"murat_live|murat_book|murat_core",
    "broker host": r"paper-api\.alpaca\.markets",
}


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _dash(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H%M%SZ")


def _w(p: Path, blob) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(blob, list):
        p.write_text("\n".join(json.dumps(r) for r in blob) + "\n", encoding="utf-8")
    else:
        p.write_text(json.dumps(blob), encoding="utf-8")
    return p


def assert_clean(payload) -> None:
    s = json.dumps(payload)
    for what, pat in DENY_PATTERNS.items():
        assert not re.search(pat, s), f"{what} leaked: {re.search(pat, s).group(0)!r}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    L._CACHE.clear()
    app = FastAPI()
    app.include_router(RA.router)
    app.include_router(RL.router)
    return TestClient(app, raise_server_exceptions=False), tmp_path


# ───────────────────────────────────────── real-shaped poisoned receipts

def _roi(base: Path, gen: datetime, *, nobroker: bool = False, dna_name: str | None = None) -> Path:
    rows = [
        {"account": "hack2", "family": "alpaca_fleet", "inception": (gen - timedelta(days=40)).date().isoformat(),
         "start_capital": 100000.0, "equity": 123456.78, "roi_pct": 2.5, "spy_same_window_pct": 1.4,
         "vs_spy_pp": 1.1, "status": "LIVE", "mark_status": "LIVE", "mark_age_days": 0,
         "account_number": "PA9SECRET0001", "cash": 4623.57, "last_equity": 98765.43,
         "source": "GET https://paper-api.alpaca.markets/v2/account + /v2/positions (AAT_HACK9_* in repo/.env)",
         "note": f"read {HOME}"},
        {"account": "PC-PAPER", "family": "pc_paper", "equity": 123456.78, "roi_pct": 0.3, "vs_spy_pp": -0.6,
         "status": "LIVE", "source": "GET https://paper-api.alpaca.markets/v2/account"},
        {"account": "murat_live", "family": "murat_book", "equity": 98765.43, "roi_pct": -3.8, "vs_spy_pp": -4.6,
         "status": "LIVE"},
        {"account": "orphan", "family": "agency", "roi_pct": None, "vs_spy_pp": None, "status": "UNGRADED",
         "note": "never entered"},
    ]
    agg = {"top_line": "1 book with >= 21 sessions is ahead of SPY.", "collapse_line": "3 ahead = 1 twin + 2.",
           "n_ahead_raw": 3, "n_ahead_strategy": 2, "n_ahead_dense": 1, "effective_bets_exante": 1.5,
           "by_family": {"pc_paper": {"n": 1, "n_priced": 1, "sum_equity": 123456.78, "sum_start_capital": 1e6,
                                      "pnl": 2662.35, "roi_pct": 0.27},
                         "murat_book": {"n": 1, "sum_equity": 98765.43, "pnl": -1271.0, "roi_pct": -3.8}},
           "tilt": {"ticker": "MU", "n_books": 2, "of": 3, "sector": "Semiconductors"},
           "book_dna_receipt": (f"backend/data/optimus/paper_accounts/{dna_name}" if dna_name else None)}
    name = f"roi_{_dash(gen)}{'.nobroker' if nobroker else ''}.json"
    return _w(base / "paper_accounts" / name,
              {"schema": "paper_accounts_roi/1", "generated_utc": gen.isoformat(), "rows": rows, "aggregate": agg,
               "read_me_first": "ROI over each account's own window.", "licence": "PRODUCT_EXPERIMENT",
               "broker_read": {"performed": True, "n_accounts": 2, "n_priced": 1,
                               "errors": {"hack3": "HTTP_401: credential refused on /v2/account"}}})


def _dna(base: Path, gen: datetime) -> str:
    name = f"book_dna_{_dash(gen)}.json"
    _w(base / "paper_accounts" / name, {
        "schema": "book_dna/1", "generated_utc": gen.isoformat(), "label_ceiling": "REPLICATED",
        "params": {"early_min_sessions": 21},
        "summary": {"top_line": "x"},
        "holdings_clusters": [{"cluster_id": 0, "n": 2, "members": ["hack2", "murat_live"],
                               "families": ["alpaca_fleet", "murat_book"],
                               "shared_basket": [{"ticker": "MU", "n_books": 2}], "excess_pp_mean": 1.0}],
        "exante_bets": {"construction": "frozen weights"},
        "books": [
            {"account": "hack2", "family": "alpaca_fleet", "category": "strategy", "status": "LIVE",
             "return_pct": 2.5, "spy_leg_pct": 1.4, "excess_pp": 1.1, "sessions_graded": 26,
             "tickers": ["MU", "TGT"], "weights": {"MU": 0.1, "TGT": 0.2},
             "holdings_source": f"fleet_daily/fleet.json via {HOME}",
             "beta_vs_spy": {"value": "NOT_COMPUTABLE", "why": "6 period returns < 20"},
             "cash_fraction": {"value": 0.045, "basis": "broker cash / equity"},
             "evidence": {"label": "OBSERVED(26)", "why": "sub-windows short"}},
            {"account": "young", "family": "llm_portfolio:lib", "category": "strategy", "return_pct": 9.0,
             "spy_leg_pct": 1.0, "excess_pp": 8.0, "sessions_graded": 6,
             "evidence": {"label": "OBSERVED(6)", "why": "6 sessions < 21"}},
            {"account": "PC-PAPER", "family": "pc_paper", "category": "strategy", "return_pct": 0.3,
             "spy_leg_pct": 0.9, "excess_pp": -0.6, "sessions_graded": 10,
             "evidence": {"label": "OBSERVED(10)", "why": "10 sessions < 21"}},
            {"account": "t1", "family": "llm_portfolio:twin", "category": "twin", "twin_kind": "ew",
             "twin_of": "lib_x", "return_pct": 11.0, "spy_leg_pct": 1.0, "excess_pp": 10.0, "sessions_graded": 6,
             "evidence": {"label": "OBSERVED(6)", "why": "6 sessions < 21"}},
            {"account": "murat_live", "family": "murat_book", "category": "strategy", "excess_pp": -4.6,
             "sessions_graded": 38, "evidence": {"label": "OBSERVED(38)"}},
            {"account": "murat_core_satellite_x__spy", "family": "llm_portfolio:twin", "category": "twin",
             "excess_pp": 0.1, "sessions_graded": 6, "evidence": {"label": "OBSERVED(6)"}},
        ],
        "losers": [{"account": "PC-PAPER", "error_type": "not_determinable", "why": "too short"}],
    })
    return name


def _health(base: Path, gen: datetime) -> dict:
    rows = [
        {"name": "sim_session", "probe": "sim_session", "where": "pc", "verdict": "ALIVE",
         "state": "ALIVE_PROGRESSING", "evidence_utc": gen.isoformat(), "age_s": 5.0, "detail": "heartbeat ok",
         "proof": "pid 185016 cmdline contains sim_run"},
        {"name": "task:AegisDailyPass", "probe": "task", "where": "pc", "verdict": "STALE", "state": "STALE",
         "evidence_utc": (gen - timedelta(hours=30)).isoformat(), "age_s": 108000.0,
         "detail": f"same output for 30.0 h across 3 probes ({HOME})", "proof": "daily_pass.json"},
        {"name": "process_census:sim_run", "probe": "process_census", "verdict": "ALIVE", "state": "ALIVE",
         "evidence_utc": gen.isoformat(), "age_s": 0.0,
         "detail": "sim_run: 1 live instance(s); parents: 1 x parent pid 4242 [python]"},
        {"name": "openclaw_gateway", "probe": "openclaw_gateway", "verdict": "ALIVE", "state": "ALIVE",
         "evidence_utc": gen.isoformat(), "evidence": "GET http://127.0.0.1:18789/health",
         "detail": "dowjones reader: 14347 page loads total; REDDIT_KEYS_ABSENT", "proof": "port 18789 answers"},
        {"name": "railway_backend", "probe": "railway_backend", "verdict": "UNKNOWN", "state": "UNKNOWN",
         "evidence_utc": None, "age_s": None, "detail": "GET :8080/health; FAKE_BROKER_KEY_ID unset"},
    ]
    rec = {"receipt": "system_health", "generated_utc": gen.isoformat(), "exit_code": 2, "source": "pc",
           "read_me_first": f"evidence lives under {HOME}",
           "counts": {"DEAD": 0, "STALE": 1, "REFUSED": 0, "UNKNOWN": 1, "STOPPED_BY_OPERATOR": 0, "ALIVE": 3},
           "rows": rows}
    _w(base / "health" / f"health_{_stamp(gen)}.json", rec)
    return rec


def _board_row(rule: str, v: float = 0.001) -> dict:
    col = {w: {"mean_monthly": v, "t_blocks": 1.0, "mde_monthly": 0.01} for w in L.TWIN_WINDOWS}
    return {"rule": rule, "family": "momentum", "status": "OK", **{c: col for c in L.TWIN_COLUMNS}}


def _theory(base: Path) -> str:
    hyp = base / "hyp_lab"
    t0 = (NOW - timedelta(hours=2)).isoformat()
    _w(hyp / "ledger.jsonl", [
        {"kind": "hypothesis", "hyp_id": "H-1", "title": "a", "family": "momentum", "status": "PROPOSED",
         "created_utc": t0},
        {"kind": "hypothesis", "hyp_id": "H-2", "title": "b", "family": "momentum", "status": "PROPOSED",
         "created_utc": t0, "mechanism": f"see {HOME}"},
        {"kind": "update", "hyp_id": "H-2", "status": "RUN", "verdict": "FAILED_VARIANT", "utc": t0,
         "summary": {"confirm": {"mean": -0.001, "t": -0.5, "mde": 0.02}}},
        {"kind": "hypothesis", "hyp_id": "H-3", "title": "c", "family": "momentum", "status": "PROPOSED",
         "created_utc": t0},
        {"kind": "update", "hyp_id": "H-3", "status": "RUN", "verdict": "FAILED_VARIANT", "utc": t0,
         "summary": {"confirm": {"mean": -0.01, "t": -3.0, "mde": 0.005}}},
    ])
    day = NOW.date().isoformat()
    for run, rules in ((f"STK_{day}_1", ["r0", "r1", "liqw"]), (f"STK_{day}_2", ["liqw"]),
                       (f"STK_SMOKE_{day}_1", [f"s{i}" for i in range(9)])):
        _w(hyp / f"twin_board_{run}.jsonl", [_board_row(r, 0.5 if run.endswith("_2") else 0.001) for r in rules])
        _w(hyp / f"twin_board_SUMMARY_{run}.json", {"written_utc": NOW.isoformat(), "twin_kind": "sticky",
                                                    "summary": {"n_rules": len(rules), "n_ok": len(rules)}})
    _w(hyp / "board_supersessions.json", {"written_utc": NOW.isoformat(), "supersessions": [
        {"supplement_run": f"STK_{day}_2", "twin_kind": "sticky", "supersedes_runs": [f"STK_{day}_1"],
         "rules": ["liqw"], "why": "weights carried"}]})
    return day


# ───────────────────────────────────────── 404 / 422 / 500

def test_every_endpoint_404s_without_receipts(client):
    c, _ = client
    for path in ("/api/arena/v1/latest", "/api/arena/v1/stories", "/api/legibility/v1/forecast-lab",
                 "/api/legibility/v1/theory-lab", "/api/legibility/v1/system-health"):
        r = c.get(path)
        assert r.status_code == 404, path
        assert r.json()["detail"], path


def test_422_on_bad_queries(client):
    c, _ = client
    assert c.get("/api/arena/v1/stories", params={"ticker": "BAD TICKER!"}).status_code == 422
    assert c.get("/api/arena/v1/stories", params={"limit": 0}).status_code == 422
    assert c.get("/api/legibility/v1/theory-lab", params={"board": "nope"}).status_code == 422


def test_500_names_the_type_never_the_message(client, monkeypatch):
    c, _ = client

    def boom(**kw):
        raise PermissionError(f"[Errno 13] Permission denied: '{HOME}'")
    monkeypatch.setattr(L, "arena_payload", boom)
    r = c.get("/api/arena/v1/latest")
    assert r.status_code == 500
    assert r.json()["detail"] == "paper arena: internal error (PermissionError)"
    assert "someone" not in r.text


# ───────────────────────────────────────── the sanitiser on whole payloads

def test_whole_payloads_carry_no_secret_and_urls_keep_their_path(client):
    c, base = client
    gen = NOW - timedelta(hours=3)
    _roi(base, gen, dna_name=_dna(base, gen))
    _health(base, NOW - timedelta(hours=1))
    _theory(base)
    for path in ("/api/arena/v1/latest", "/api/legibility/v1/system-health", "/api/legibility/v1/theory-lab"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert_clean(r.json())
    a = c.get("/api/arena/v1/latest").json()
    books = {b["account"]: b for b in a["books"]}
    assert books["hack2"]["source"].startswith("GET /v2/account + /v2/positions")       # path kept, host gone
    assert books["hack2"]["cash_fraction"] == pytest.approx(0.045)                         # a fraction survives
    assert set(a["by_family"]) == {"pc_paper"}
    assert a["by_family"]["pc_paper"] == {"n": 1, "n_priced": 1, "roi_pct": 0.27}
    assert a["clusters"][0]["members"] == ["hack2"]
    assert a["numbers"]["n_owner_personal_dropped"] == 2
    h = c.get("/api/legibility/v1/system-health").json()
    proofs = {x["name"]: x for x in h["groups"][-1]["rows"]}
    assert proofs["sim_session"]["proof"] == "a live process answers as sim_run"
    owners = {o["task"]: o for o in h["task_owners"]}
    assert "someone" not in json.dumps(owners["AegisDailyPass"])


def test_sanitiser_drops_unlisted_keys_and_structures():
    spec = {"a": S.LEAF, "m": S.MapOf(S.LEAF), "l": S.ListOf({"x": S.LEAF})}
    out = S.sanitise({"a": {"nested": 1}, "b": 2, "m": {"ok": 1, "equity": 5, "api_key": "k"},
                      "l": [{"x": 1, "y": 2}]}, spec)
    assert out == {"a": None, "m": {"ok": 1}, "l": [{"x": 1}]}


# ───────────────────────────────────────── Paper Arena

def test_arena_leads_with_dense_winners_and_dims_twins(client):
    c, base = client
    gen = NOW - timedelta(hours=3)
    _roi(base, gen, dna_name=_dna(base, gen))
    d = c.get("/api/arena/v1/latest").json()
    assert d["top"]["top_line"] == "1 book with >= 21 sessions is ahead of SPY."
    assert [w["account"] for w in d["winners"]] == ["hack2"]                 # >= 21 sessions only
    assert [w["account"] for w in d["short_lived"]] == ["young"]             # not evidence
    assert d["books"][0]["category"] == "strategy"                           # twins sorted after strategy
    assert d["books"][-2]["category"] == "twin" or d["books"][-1]["category"] in ("twin", None)
    kinds = {x["kind"]: x for x in d["receipts"]}
    assert len(kinds["paper_accounts_roi"]["sha256"]) == 64
    assert 2.9 < kinds["paper_accounts_roi"]["age_hours"] < 3.2
    books = {b["account"]: b for b in d["books"]}
    assert books["orphan"]["evidence_label"] is None and books["orphan"]["missing_because"]["evidence_label"]


def test_arena_serves_the_newest_receipt_and_says_when_it_is_a_nobroker_pass(client):
    c, base = client
    old = _roi(base, NOW - timedelta(hours=10))
    _roi(base, NOW - timedelta(hours=1), nobroker=True)
    _w(base / "paper_accounts" / f"roi_{NOW.date().isoformat()}.json", {"generated_utc": NOW.isoformat()})
    d = c.get("/api/arena/v1/latest").json()
    assert d["receipt_choice"]["served_is_nobroker"] is True
    assert d["receipt_choice"]["newest_broker_file"].endswith(old.name)
    assert "NO-BROKER" in d["receipt_choice"]["line"]


def test_arena_stale_and_missing_book_dna(client):
    c, base = client
    old = NOW - timedelta(hours=float(_config.LEGIBILITY_STALE_HOURS["paper_accounts_roi"]) + 5)
    _roi(base, old, dna_name=None)
    d = c.get("/api/arena/v1/latest").json()
    assert d["status"] == "STALE"
    assert d["receipts"][1]["status"] == "MISSING" and d["missing_because"]["book_dna"]


def test_stories_and_regret_h5_table(client):
    c, base = client
    month = NOW.strftime("%Y-%m")
    _w(base / "decision_story" / f"stories_{month}.jsonl", [
        {"kind": "decision", "decision_id": "d1", "session": NOW.date().isoformat(), "ticker": "MU",
         "action": "HOLD", "abstention": True, "built_utc": NOW.isoformat(), "chain": {}, "equity": 123456.78},
        {"kind": "decision", "decision_id": "d2", "session": NOW.date().isoformat(), "ticker": "TGT",
         "action": "BUY", "built_utc": NOW.isoformat(), "chain": {}}])
    _w(base / "decision_story" / f"alternatives_{month}.jsonl", [
        {"kind": "alternative", "decision_id": "d1", "alt": "buy_default", "target_weight": 0.02, "status": "OK"}])
    _w(base / "decision_story" / "regret" / f"regret_{_stamp(NOW)}.json", {
        "run_id": _stamp(NOW), "asof": NOW.date().isoformat(), "status": "OK", "line": "1 graded",
        "written_utc": NOW.isoformat(),
        "summary": {"by_horizon": {"h5": {"cohorts": {"acted": {
            "mean_names": 2.0, "mean_gross_scaled": 0.01,
            "vs_spy": {"mean_bps": 3.0, "t": 0.4, "n_sessions": 5, "mde_bps": 40.0},
            "vs_band_control": {"mean_bps": 1.0}}}}}}})
    d = c.get("/api/arena/v1/stories").json()
    assert d["n_decisions"] == 2
    assert {x["decision_id"]: x for x in d["stories"]}["d1"]["alternatives"][0]["alt"] == "buy_default"
    assert d["regret"]["h5_table"][0]["cohort"] == "acted"
    assert c.get("/api/arena/v1/stories", params={"ticker": "MU"}).json()["n_decisions"] == 1
    assert_clean(d)


# ───────────────────────────────────────── Forecast Lab

def test_forecast_lab_cited_run_review_rerun_baselines_and_wilson(client):
    c, base = client
    day = NOW.date().isoformat()
    _w(base / "reputation" / f"reputation_{day}.json", {
        "written_utc": NOW.isoformat(), "n_graded": 10, "split": "later half",
        "calibration": {"h5": [{"arm_prefix": "investigator:", "horizon": 5, "observable": "abs_move_exceeds",
                                "bin": 0, "n": 10, "p_mean": 0.05, "base_rate": 0.3}]},
        "arms": [{"arm": "investigator:x", "n": 10, "skill": 0.05}],
        "arms_by_observable": [
            {"arm": "a", "observable": "abs_move_exceeds", "horizon_days": 5.0, "kind": "magnitude", "n": 100,
             "skill": 0.1},
            {"arm": "b", "observable": "return_sign", "horizon_days": 5.0, "kind": "direction", "n": 100,
             "skill": -0.2},
            {"arm": "c", "observable": "return_sign", "horizon_days": 5.0, "kind": "direction", "n": 0,
             "skill": None}]})
    rd = base / "nn_lab" / "receipts"
    _w(rd / "wf_20200101_cited.json", {"run_id": "wf_cited", "written_utc": (NOW - timedelta(days=2)).isoformat(),
                                       "magnitude": {"h5": {"trailing_vol_ic_with_abs_y": {"mean": 0.3, "t": 50.0,
                                                                                           "n_blocks": 40}}},
                                       "models": {"lgbm": {"h5": {"rank_ic": {"mean": 0.01, "t": 2.0},
                                                                  "verdict": "BETA_EXPLAINS"}}}})
    _w(rd / "wf_29990101_review.json", {"run_id": "wf_review", "written_utc": NOW.isoformat(),
                                        "models": {"lgbm": {"h5": {"rank_ic": {"mean": 0.02, "t": 3.0}}}}})
    _w(rd / f"nightly_{_stamp(NOW)}.json", {
        "written_utc": NOW.isoformat(), "status": "OK",
        "tournament": {"rule": "beat max(ridge, lgbm) by one SE",
                       "walk_forward": {"receipt": "wf_20200101_cited.json",
                                        "written_utc": (NOW - timedelta(days=2)).isoformat(),
                                        "by_horizon": {"h5": {"nn": {"rank_ic": 0.01}}}}},
        "trust": {"trust": {"nn": {"h5": {"graded_dates": 0, "trust": 0.0, "source": "prior_only"}}}}})
    _w(base / "learning_reports" / f"report_{day}.json", {"generated_utc": NOW.isoformat(), "closing": {
        "vol_prior": {"5": {"skill_prior": 0.05, "skill_llm": 0.04, "n_heldout": 875}}}})
    _w(base / "digest" / f"world_digest_{_stamp(NOW)}.json", {"shadow": {"grade": {
        "size": {"n_dates": 1, "n_rows": 4, "trust": 0.0}, "direction": {"n_dates": 0, "trust": 0.0}}}})
    r = c.get("/api/legibility/v1/forecast-lab")
    assert r.status_code == 200
    d = r.json()
    assert_clean(d)
    t = d["tournament"]
    assert t["cited_run"] == "wf_cited" and t["cited_models"][0]["verdict"] == "BETA_EXPLAINS"
    assert d["review_rerun"]["run_id"] == "wf_review"
    roles = {x["role"] for x in d["receipts"] if x["kind"] == "nn_lab_walkforward"}
    assert roles == {"tournament table (the run the nightly cites)", "review rerun (not the tournament's run)"}
    cell = {(x["kind"], x["horizon_days"]): x for x in d["skill"]["by_kind_horizon"]}[("direction", 5.0)]
    assert "pooled_skill" not in cell and cell["best_arm"] == "b" and cell["n_arms_scored"] == 1
    assert d["skill"]["baseline"] == L.BASELINE_REPUTATION
    assert d["sigma_prior"][0]["baseline"] == L.BASELINE_SIGMA_PRIOR
    hf = d["house_finding"]["evidence"][0]
    assert hf["baseline"] == L.BASELINE_SIGMA_PRIOR and "0.3" in hf["sanity_check"]
    b = d["calibration"]["h5"][0]
    assert b["wilson_lo"] < 0.3 < b["wilson_hi"] and b["thin"] is True
    assert b["n_date_blocks"] is None and b["blocks_missing_because"]
    assert t["sentence"].startswith("no model has earned forward weight")
    assert all(x["below_min_dates"] for x in d["trust"]["news"])


def test_wilson_interval():
    lo, hi = L.wilson(100, 0.5)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)
    assert L.wilson(0, 0.5) == (None, None)


# ───────────────────────────────────────── Theory Lab

def test_theory_state_map():
    st = lambda h, p, c=None: L.theory_state(h, p, c)[0]                      # noqa: E731
    fv = {"status": "RUN", "verdict": "FAILED_VARIANT", "history": [{"verdict": "FAILED_VARIANT"}]}
    assert st(fv, False) == "UNINFORMATIVE" and st(fv, None) == "UNINFORMATIVE"
    assert st(fv, True) == "FALSIFIED_VARIANT"
    assert st({"status": "RUN", "verdict": "MECHANISM_REJECTED"}, True) == "FALSIFIED"
    assert st({"status": "RUN", "verdict": "CANNOT_DISTINGUISH"}, False) == "UNINFORMATIVE"
    assert st({"status": "PROPOSED"}, False) == "HYPOTHESIS"
    after_pos = {"status": "RUN", "verdict": "FAILED_VARIANT",
                 "history": [{"verdict": "CANDIDATE"}, {"verdict": "FAILED_VARIANT"}]}
    assert st(after_pos, True) == "WEAKENING" and st(after_pos, False) == "UNINFORMATIVE"
    assert st({"status": "RUN", "verdict": "CANDIDATE",
               "history": [{"verdict": "CANNOT_DISTINGUISH"}, {"verdict": "CANDIDATE"}]}, False) == "STRENGTHENING"
    assert st({"status": "RUN", "verdict": "CONDITIONAL_POSITIVE"}, False) == "CONDITIONAL_SUPPORT"
    assert st({"status": "RUN", "verdict": "CANDIDATE"}, False) == "EARLY_SUPPORT"
    assert st({"status": "RUN", "verdict": "CANDIDATE"}, False,
              {"primary_stats": {"design": {"mean_monthly": 0.01}, "late": {"mean_monthly": -0.01}}}) == "REGIME_SPECIFIC"
    assert st({"status": "RUN", "verdict": "REFUSED"}, False) == "INVALID_EXPERIMENT"
    assert st({"status": "DUPLICATE_IN_LEDGER"}, False) == "RETIRED"


def test_theory_lab_supersession_states_and_board_param(client):
    c, base = client
    day = _theory(base)
    d = c.get("/api/legibility/v1/theory-lab").json()
    st = {x["hyp_id"]: x for x in d["theories"]}
    assert st["H-1"]["state"] == "HYPOTHESIS"
    assert st["H-2"]["state"] == "UNINFORMATIVE"
    assert st["H-3"]["state"] == "FALSIFIED_VARIANT"                       # confirm t <= -2: powered
    assert d["n_negative"] == 1 and d["n_uninformative"] == 1
    assert [m["state"] for m in d["state_map"]][0].startswith("HYPOTHESIS")
    sticky = d["boards"]["sticky"]
    assert sticky["run_id"] == f"STK_{day}_1"                               # largest; SMOKE excluded
    rows = {r["rule"]: r for r in sticky["rows"]}
    assert rows["liqw"]["source_run"] == f"STK_{day}_2"                     # the supplement's row is served
    assert rows["liqw"]["columns"]["fair_twin_net"]["validate"]["mean_monthly"] == 0.5
    assert rows["r0"]["source_run"] is None
    assert sticky["supersessions_applied"][0]["rules"] == ["liqw"]
    assert d["boards"]["basket"] is None and d["missing_because"]["twin_board_FT"]
    roles = {x["role"] for x in d["receipts"]}
    assert {"row supersessions", f"supplement STK_{day}_2", "sticky board rows"} <= roles


# ───────────────────────────────────────── System Health

def test_system_health_shape_groups_and_same_output(client):
    c, base = client
    _health(base, NOW - timedelta(hours=30))                 # older receipt: must not be served
    rec = _health(base, NOW - timedelta(hours=1))
    d = c.get("/api/legibility/v1/system-health").json()
    assert d["receipts"][0]["file"].endswith(f"health_{_stamp(NOW - timedelta(hours=1))}.json")
    assert d["status"] == "FRESH"
    assert [g["verdict"] for g in d["groups"]] == ["STALE", "UNKNOWN", "ALIVE"]
    assert [x["name"] for x in d["same_output_rows"]] == ["task:AegisDailyPass"]
    assert [x["name"] for x in d["process_census"]] == ["process_census:sim_run"]
    owners = {o["task"]: o for o in d["task_owners"]}
    assert owners["AegisDailyPass"]["state"] == "STALE"
    assert owners["AegisWorldDigest"]["missing_because"]
    assert d["health_line"] == L.health_line(rec)
    assert_clean(d)


def test_health_line_is_the_daily_pass_line(monkeypatch, tmp_path):
    """The page's one-line summary must be identical to the daily pass's health headline."""
    from scripts import daily_pass as DP
    rec = _health(tmp_path, NOW)
    monkeypatch.setattr(DP, "run_health_probes", lambda **kw: rec)
    row = DP.step_health({"rows": []})
    assert row["headline"] == L.health_line(rec)


def test_freshness_unknown_when_undateable(tmp_path):
    f = L.freshness("system_health", None, NOW)
    assert f["status"] == "UNKNOWN" and f["age_hours"] is None
    f = L.freshness("system_health", _stamp(NOW - timedelta(hours=2)), NOW)
    assert f["status"] == "FRESH" and f["age_hours"] == pytest.approx(2.0)
