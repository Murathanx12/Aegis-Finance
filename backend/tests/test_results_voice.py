"""results_voice: results first, the claim line last (2026-10-07, "speak with results").

Every test reads a TRIMMED copy of the 2026-10-06T235345Z roi + book_dna pair
(`fixtures/results_voice/`), copied into tmp_path; the live ledger is never read.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from backend.services import book_dna as DNA
from backend.services import legibility as L
from backend.services import legibility_sanitise as S
from backend.services import publish_receipts as PR
from backend.services import results_voice as RV

FIX = Path(__file__).parent / "fixtures" / "results_voice"
RID = "2026-10-06T235345Z"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    d = tmp_path / "paper_accounts"
    shutil.copytree(FIX, d)
    return d


@pytest.fixture
def voice(folder: Path) -> dict:
    return RV.run(RID, folder)["voice"]


def _dna_params() -> dict:
    return json.loads((FIX / f"book_dna_{RID}.json").read_text(encoding="utf-8"))["params"]


# ── counts ────────────────────────────────────────────────────────────────

def test_headline_counts_exclude_controls_twins_and_non_live(voice):
    h = voice["headline"]
    # 21 roi rows: hack3 is not LIVE; 7 are twins/controls by twin_of, book_dna
    # category or a name marker (comparato, __, -control)
    assert h["n_strategy_accounts"] == 13
    assert h["n_ahead"] == 7 and h["n_behind"] == 6
    assert h["as_of_mark"] == "2026-10-06"
    excluded = {x["account"]: x["why"] for x in voice["excluded_controls"]}
    assert "balanced-ew-control" in excluded
    assert any("comparato" in a for a in excluded)
    assert "lib_skill_raises_2026-09-30__control" in excluded
    assert excluded["lib_net_raises_2026-09-26__random_same_band"].startswith("twin_of")
    assert "hack3" not in excluded and "hack3" not in {x["account"] for x in voice["leaders"] + voice["losers"]}


def test_families_have_accounts_ahead_and_median(voice):
    fam = {f["family"]: f for f in voice["families"]}
    assert fam["alpaca_fleet"]["accounts"] == 3 and fam["alpaca_fleet"]["ahead"] == 1
    assert fam["website_lane"]["ahead"] == 0
    assert all(isinstance(f["median_vs_spy_pp"], float) for f in voice["families"])


# ── clusters ──────────────────────────────────────────────────────────────

def test_clusters_by_set_equality_and_by_jaccard(voice):
    c = voice["clusters"]
    assert ["hack2", "revision_flow_v0"] in c["exact_same_names"]
    assert ["conviction", "mirror"] in c["exact_same_names"]
    bets = [set(b) for b in c["jaccard_bets"]]
    assert {"lib_net_raises_2026-09-26", "lib_net_raises_ivw_lead_2026-09-27"} in bets
    # 0.55 Jaccard with revision_flow_v0: related, but NOT one bet at >= 0.8
    assert not any("pers_revision_flow_leaders_2026-09-25" in b and "revision_flow_v0" in b for b in bets)
    assert voice["headline"]["n_distinct_bets"] == 10
    assert voice["headline"]["n_distinct_bets_ahead"] == 5


# ── leaders ───────────────────────────────────────────────────────────────

def test_leaders_are_distinct_bets_with_windows_labels_and_mechanisms(voice):
    L5 = voice["leaders"]
    assert [x["account"] for x in L5][:3] == ["revision_flow_v0", "lib_net_raises_2026-09-26",
                                              "pers_revision_flow_leaders_2026-09-25"]
    assert "hack2" not in [x["account"] for x in L5], "hack2 is the same bet as revision_flow_v0"
    assert "lib_net_raises_ivw_lead_2026-09-27" not in [x["account"] for x in L5]
    top = L5[0]
    assert top["same_names_as"] == ["hack2"]
    assert top["vs_spy_pp"] == pytest.approx(5.741) and top["spy_same_window_pct"] == pytest.approx(1.398)
    assert (top["inception"], top["last_mark"], top["sessions_graded"]) == ("2026-09-28", "2026-10-06", 7)
    assert top["evidence_label"] == "OBSERVED(7)"
    assert top["mechanism"].startswith("analyst revision flow")
    assert top["random_twin"] is None and "NOT_COMPUTABLE" in top["twin_line"]
    assert top["random_twin_relationship_status"] == "RELATIONSHIP_UNKNOWN"
    assert "relationship UNKNOWN" in top["twin_line"]
    assert "no random twin seeded" not in top["twin_line"]
    assert top["receipts"][0].endswith(f"roi_{RID}.json") or top["receipts"][0] == f"roi_{RID}.json"
    abst = next(x for x in L5 if "[b109c886]" in x["account"])
    assert abst["mechanism"].startswith("SPY by default")


def test_random_twin_gap_is_parent_minus_twin(voice):
    x = next(y for y in voice["leaders"] if y["account"] == "pers_revision_flow_leaders_2026-09-25")
    tw = x["random_twin"]
    assert x["random_twin_relationship_status"] == "RECORDED_LINK"
    assert tw["kind"] == "random_same_band"
    assert tw["gap_pp"] == pytest.approx(6.705 - 0.608, abs=1e-3)


def test_losers_named_worst_first(voice):
    assert [x["account"] for x in voice["losers"]][:3] == ["mirror", "hack4", "hack6"]
    assert voice["losers"][0]["family"] == "website_lane"
    assert voice["losers"][0]["inception"] == "2026-06-16"


# ── label thresholds come from book_dna, not from this module ─────────────

def test_sessions_to_next_label_read_from_book_dna_params(voice):
    early = _dna_params()["early_min_sessions"]
    for x in voice["leaders"]:
        rz = x["raise"]
        assert rz["next_label"] == "EARLY_EVIDENCE"
        assert rz["sessions_needed"] == max(0, early - x["sessions_graded"])
    abst = next(x for x in voice["leaders"] if "[b109c886]" in x["account"])
    assert abst["raise"]["sessions_needed"] == early - 17
    assert any("sub-windows not computable" in b for b in abst["raise"]["blockers"])


def test_raise_path_walks_book_dnas_ladder():
    p = {"early_min_sessions": 21}
    sub_ok = {"status": "OK", "n_positive": 3}
    obs = RV.raise_path({"evidence": {"label": "OBSERVED(30)"}, "sessions_graded": 30,
                         "subwindows": {"status": "OK", "n_positive": 1}}, 2.0, p)
    assert obs["sessions_needed"] == 0 and any("1 of 3" in b for b in obs["blockers"])
    neg = RV.raise_path({"evidence": {"label": "OBSERVED(30)"}, "sessions_graded": 30,
                         "subwindows": sub_ok}, -1.0, p)
    assert any("excess vs SPY must be > 0" in b for b in neg["blockers"])
    early = RV.raise_path({"evidence": {"label": "EARLY_EVIDENCE"}, "sessions_graded": 30,
                           "subwindows": sub_ok}, 2.0, p)
    assert early["next_label"] == "REPLICATED"
    rep = RV.raise_path({"evidence": {"label": "REPLICATED"}}, 2.0, p)
    assert rep["next_label"] == "VALIDATED_EDGE"
    assert RV.params()["label_ladder"] == list(DNA.LABEL_LADDER)


def test_claims_line_is_last_and_says_none(voice):
    assert voice["claims"]["top_rung"] == "OBSERVED"
    assert voice["claims"]["promoted"] == []
    assert voice["claims"]["line"].startswith("CLAIMS PROMOTED: none")
    lines = voice["headline_lines"]
    assert len(lines) == 6
    assert lines[0].startswith("RESULTS ") and lines[1].startswith("LEADER revision_flow_v0")
    assert lines[3].startswith("WHAT RAISES IT:") and lines[-1].startswith("CLAIMS PROMOTED: none")
    assert not any("proof" in ln.lower() for ln in lines)


# ── determinism, files, refusals ──────────────────────────────────────────

def test_deterministic_bytes_on_rerun(folder):
    RV.run(RID, folder)
    a = [(folder / f"results_voice_{RID}{s}").read_bytes() for s in (".json", ".md")]
    RV.run(RID, folder)
    b = [(folder / f"results_voice_{RID}{s}").read_bytes() for s in (".json", ".md")]
    assert a == b
    md = b[1].decode("utf-8")
    assert f"roi_{RID}.json" in md and f"book_dna_{RID}.json" in md


def test_default_run_id_is_the_newest_SHARED_pair(folder):
    (folder / "roi_2026-10-07T000000Z.json").write_text("{}", encoding="utf-8")   # no book_dna partner
    assert RV.newest_shared_run_id(folder) == RID


def test_refuses_without_a_pair(tmp_path):
    with pytest.raises(RV.ResultsVoiceRefused):
        RV.newest_shared_run_id(tmp_path)
    with pytest.raises(RV.ResultsVoiceRefused):
        RV.load_pair(RID, tmp_path)
    with pytest.raises(RV.ResultsVoiceRefused):
        RV.build({"rows": []}, {"books": []}, roi_path="r", dna_path="d")
    out = RV.safe_run(None, tmp_path)
    assert out["status"] == "skip" and out["line"].startswith("SKIP results_voice")


def test_headline_block_reads_the_md(folder):
    RV.run(RID, folder)
    p, lines = RV.headline_block(folder)
    assert p.name == f"results_voice_{RID}.md"
    assert len(lines) == 6 and lines[-1].startswith("CLAIMS PROMOTED:")


def test_no_equity_dollars_in_the_voice(voice):
    blob = json.dumps(voice)
    for k in ("\"equity\"", "\"start_capital\"", "\"pnl\""):
        assert k not in blob


# ── the public /arena section ─────────────────────────────────────────────

def test_public_section_is_a_sanitiser_fixed_point_and_drops_personal(voice):
    v = json.loads(json.dumps(voice))
    v["losers"].append({**v["losers"][0], "account": "murat_live", "family": "murat_book"})
    v["headline_lines"].append("BEHIND: worst murat_live -8.32 pp")
    pub = RV.public_view(v, L.is_personal)
    spec = S.SPEC["arena"]["results_voice"]
    clean = S.sanitise(pub, spec)
    assert clean == S.sanitise(json.loads(json.dumps(clean)), spec)
    assert clean == pub, "every field public_view emits must be enrolled in the allow-list"
    assert "murat_live" not in json.dumps(clean)
    assert clean["n_headline_lines_dropped_owner_personal"] == 1
    assert clean["leaders"][0]["account"] == "revision_flow_v0"
    assert clean["claims_line"].startswith("CLAIMS PROMOTED: none")
    assert not [x for x in PR.leak_scan(clean) if "owner identity" not in x]


def test_arena_payload_carries_the_section_for_the_same_run(folder, monkeypatch):
    RV.run(RID, folder)
    monkeypatch.setattr(L, "base_dir", lambda: folder.parent)
    p = L.arena_payload()
    assert p is not None and p["results_voice"]["run_id"] == RID
    clean = S.sanitise(p, S.SPEC["arena"])
    assert clean["results_voice"]["n_ahead"] == 7
    (folder / f"results_voice_{RID}.json").unlink()
    p2 = L.arena_payload()
    assert p2["results_voice"] is None and "results_voice" in p2["missing_because"]


def test_telegram_results_block(folder):
    from backend.services import telegram_cockpit as TC
    root = folder.parent
    assert "CANNOT DETERMINE" in TC.results_block(root)
    RV.run(RID, folder)
    txt = TC.results_block(root)
    assert txt.splitlines()[0].startswith("RESULTS ") and f"results_voice_{RID}.md" in txt
    assert "revision\\_flow\\_v0" in TC.results_block(root, markdown=True)


# ── CH-11 note (2026-11-13): every book row prints its market exposure ─────

def test_a_receipt_older_than_the_fields_says_cannot_determine_with_why(voice):
    for x in voice["leaders"] + voice["losers"]:
        e = x["market_exposure"]
        assert e["beta_adjusted_excess_pp"] == DNA.CANNOT_DETERMINE
        assert "predates the market_exposure fields" in e["beta_adjusted_excess_pp_why"]
        assert x["exposure_line"].startswith("beta CANNOT DETERMINE, up-capture CANNOT DETERMINE, "
                                             "down-capture CANNOT DETERMINE, beta-adjusted excess CANNOT DETERMINE")
    lines = voice["headline_lines"]
    assert len(lines) == 6
    assert "beta-adjusted excess CANNOT DETERMINE" in lines[1] and "beta-adjusted excess" in lines[4]
    rk = voice["beta_adjusted_ranking"]
    assert rk["n_determined"] == 0 and rk["n_cannot_determine"] == voice["headline"]["n_strategy_accounts"]


def _with_exposure(folder: Path) -> dict:
    """Give every book in the fixture's book_dna a synthetic market_exposure block; one
    strategy account gets a NOT_CREDIBLE beta instead."""
    p = folder / f"book_dna_{RID}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    want = {}
    for i, b in enumerate(d["books"]):
        if b["account"] == "hack4":
            why = "beta NOT_CREDIBLE: beta: NOT_CREDIBLE (date stamp lag): synthetic"
            b["market_exposure"] = {k: {"value": DNA.CANNOT_DETERMINE, "why": why}
                                    for k in ("beta", "up_capture", "down_capture", "beta_adjusted_excess_pp")}
            continue
        beta = 0.5 + 0.1 * i
        bax = round(float(b.get("excess_pp") or 0.0) - 0.37 * i, 3)
        want[b["account"]] = (beta, bax)
        b["market_exposure"] = {"beta": {"value": beta}, "up_capture": {"value": beta + 0.1},
                                "down_capture": {"value": beta - 0.1},
                                "beta_adjusted_excess_pp": {"value": bax}, "n_obs": 25}
    p.write_text(json.dumps(d), encoding="utf-8")
    return want


def test_rows_print_beta_capture_and_beta_adjusted_excess(folder):
    want = _with_exposure(folder)
    v = RV.run(RID, folder)["voice"]
    top = v["leaders"][0]
    beta, bax = want[top["account"]]
    assert top["exposure_line"] == (f"beta {beta:.2f}, up-capture {beta + 0.1:.2f}, down-capture "
                                    f"{beta - 0.1:.2f}, beta-adjusted excess {bax:+.2f} pp")
    assert top["exposure_line"] in v["headline_lines"][1]
    hack4 = next(x for x in v["losers"] if x["account"] == "hack4")
    assert "CANNOT DETERMINE: beta NOT_CREDIBLE" in hack4["exposure_line"]
    md = (folder / f"results_voice_{RID}.md").read_text(encoding="utf-8")
    assert "- hack4 — CANNOT DETERMINE (beta, up-capture, down-capture, beta-adjusted excess)" in md


def test_ranking_by_beta_adjusted_excess_excludes_controls_like_the_headline(folder):
    want = _with_exposure(folder)
    v = RV.run(RID, folder)["voice"]
    rk = v["beta_adjusted_ranking"]
    accs = [x["account"] for x in rk["rows"]]
    excluded = {x["account"] for x in v["excluded_controls"]}
    assert len(accs) == v["headline"]["n_strategy_accounts"] and not (set(accs) & excluded)
    det = [a for a in accs if a != "hack4"]
    assert [want[a][1] for a in det] == sorted((want[a][1] for a in det), reverse=True)
    assert accs[-1] == "hack4" and rk["n_cannot_determine"] == 1
    md = (folder / f"results_voice_{RID}.md").read_text(encoding="utf-8")
    assert "## Books ranked by beta-adjusted excess" in md
    assert "Ranked after the fact" in md and f"range {rk['sessions_min']}–{rk['sessions_max']}" in md


def test_rebuild_dna_refuses_to_write_beside_the_receipts(folder):
    with pytest.raises(RV.ResultsVoiceRefused):
        RV.run(RID, folder, rebuild_dna=True)
    with pytest.raises(RV.ResultsVoiceRefused):
        RV.run(RID, folder, rebuild_dna=True, out_dir=folder)


def test_rebuild_dna_writes_only_into_out_dir_and_reads_read_only(folder, tmp_path, monkeypatch):
    import pandas as pd
    from datetime import date, timedelta
    seen = {}

    def fake_inputs(receipt, *, http_get=None, fetch_lanes=True, read_only_db=False):
        seen.update(fetch_lanes=fetch_lanes, read_only_db=read_only_db)
        return {"books": [], "leaderboards": [], "fleet_positions": {}, "fleet_manager_last_run": {},
                "fleet_grades": {}, "pc_state": None, "pc_nav": [], "pc_manager_last_run": None,
                "night_nav": {}, "lane_positions": {}, "lane_caps": {}, "sector_map": {},
                "sector_source": "test", "gaps": {}}
    monkeypatch.setattr(DNA, "load_inputs", fake_inputs)
    days = [date.today() - timedelta(days=k) for k in range(60, 0, -1)]
    bars = pd.DataFrame([{"symbol": "SPY", "date": pd.Timestamp(d), "open": 100 + i * 0.1, "close": 100 + i * 0.1}
                         for i, d in enumerate(x for x in days if x.weekday() < 5)])
    before = sorted(p.name for p in folder.iterdir())
    out = tmp_path / "out"
    res = RV.run(RID, folder, out_dir=out, rebuild_dna=True, bars=bars)
    assert sorted(p.name for p in folder.iterdir()) == before
    assert seen == {"fetch_lanes": False, "read_only_db": True}
    names = sorted(p.name for p in out.iterdir())
    assert names == [f"book_dna_{RID}.json", f"results_voice_{RID}.json", f"results_voice_{RID}.md"]
    assert res["run_id"] == RID
    for x in res["voice"]["leaders"] + res["voice"]["losers"]:
        assert "market_exposure" in x and x["market_exposure"]["beta_adjusted_excess_pp"] is not None


# ── CH-11 fix round (review of PR #140, 2026-11-14): each test fails on 0b45f7f8 ──

def _rich(beta: float, bax: float, *, window=("2026-09-01", "2026-11-12", 45, 103)) -> dict:
    """A market_exposure block in the shape book_dna writes after the fix round."""
    f, t, n, s = window
    return {"beta": {"value": beta, "se": 0.05, "n_obs": n, "from": f, "to": t},
            "up_capture": {"value": beta + 0.07, "se": 0.08, "n_periods": 22, "estimate": beta + 0.07},
            "down_capture": {"value": beta - 0.09, "se": 0.06, "n_periods": 23, "estimate": beta - 0.09},
            "beta_adjusted_excess_pp": {"value": bax, "se_pp": 2.1, "mde_pp": 5.88, "rf_effect_pp": 1.05,
                                        "rf_note": "rf = 0 declared; ASSUMED 4%/yr"},
            "estimation_window": {"from": f, "to": t, "n_periods": n, "receipt_sessions": s,
                                  "comparable": True},
            "n_obs": n}


def _with_fix_round_exposure(folder: Path) -> tuple[str, str, str]:
    """Every book gets a rich block; one is NOT COMPARABLE (M1), one is a flat book printed
    near zero (m1) with a date-stamp note (B1). Returns (not comparable, near zero, ranked)."""
    p = folder / f"book_dna_{RID}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    names = [b["account"] for b in d["books"]]
    nc, nz = "hack4", next(a for a in names if a not in ("hack4",) and not a.startswith("hack"))
    for i, b in enumerate(d["books"]):
        b["market_exposure"] = _rich(0.3 + 0.01 * i, 5.0 - 0.5 * i)
        if b["account"] == nc:
            why = ("not comparable: beta measured on 2026-09-28..2026-11-11 (31 periods) and the receipt window "
                   "is 2026-08-28..2026-11-12 (54 sessions): it covers 31 of 54 receipt sessions (57% < 80%)")
            b["market_exposure"]["beta_adjusted_excess_pp"] = {
                "value": DNA.CANNOT_DETERMINE, "why": why, "window_figure_pp": -2.87, "window_figure_se_pp": 3.0,
                "window_from": "2026-09-28", "window_to": "2026-11-11", "window_n_periods": 31}
            b["market_exposure"]["estimation_window"].update(comparable=False, receipt_sessions=54)
        if b["account"] == nz:
            me = b["market_exposure"]
            me["beta"]["value"], me["down_capture"]["value"] = 0.0001, -0.0001
            me["beta_adjusted_excess_pp"]["value"] = -0.001
            me["stamp_note"] = "date stamp lag in 1 month(s) (2026-08 same-day -0.09 / lag -1 +0.62): synthetic"
    p.write_text(json.dumps(d), encoding="utf-8")
    return nc, nz, names[0]


def test_fix_m1_not_comparable_rows_print_their_window_figure_and_follow_the_ranked(folder):
    nc, nz, _ = _with_fix_round_exposure(folder)
    v = RV.run(RID, folder)["voice"]
    rk = v["beta_adjusted_ranking"]
    accs = [x["account"] for x in rk["rows"]]
    assert rk["n_not_comparable"] == 1 and accs[-1] == nc          # after every ranked account
    row = rk["rows"][-1]["market_exposure"]
    assert row["not_comparable"]["figure_pp"] == -2.87
    md = (folder / f"results_voice_{RID}.md").read_text(encoding="utf-8")
    assert "NOT COMPARABLE: -2.87 pp on 2026-09-28..2026-11-11 (31 p)" in md
    assert "covers 31 of 54 receipt sessions" in md                 # the reason line, not a blank


def test_fix_rows_print_se_n_mde_and_the_beta_window(folder):
    _, _, first = _with_fix_round_exposure(folder)
    v = RV.run(RID, folder)["voice"]
    md = (folder / f"results_voice_{RID}.md").read_text(encoding="utf-8")
    assert "| beta | up-capture | down-capture | beta-adjusted excess | beta window |" in md
    assert "±0.05 | " in md and "±0.08 (n 22)" in md and "pp ±2.10 (MDE 5.88)" in md
    assert "2026-09-01..2026-11-12, 45 p of 103 s" in md
    top = v["leaders"][0]
    assert " on 2026-09-01..2026-11-12, 45 p of 103 s" in top["exposure_line"]
    assert "Jensen at assumed rf" in md


def test_fix_m1_minor_never_prints_minus_zero_and_prints_the_stamp_note(folder):
    _, nz, _ = _with_fix_round_exposure(folder)
    RV.run(RID, folder)
    md = (folder / f"results_voice_{RID}.md").read_text(encoding="utf-8")
    assert "-0.00" not in md
    if any(nz in ln for ln in md.splitlines() if ln.startswith("|")):
        assert f"- {nz} — beta window: date stamp lag in 1 month(s)" in md
