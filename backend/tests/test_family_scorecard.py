"""CH-55 (2026-11-16): the market-exposure block on every book and the family scorecard.

Known answers: a book that is exactly 2 x SPY every session comes out with beta 2 and a
residual of 0; a book with fewer sessions than the beta floor reads CANNOT DETERMINE with
its reason; two books with the same returns are ONE family; an empty, stale or pre-exposure
input exits non-zero with a named reason and writes nothing; a live book without the block,
or a label without its false-fire rate, is a FAILED scorecard and a non-zero exit.

Every date is derived from today; nothing reads the live data folder, the network or a clock
the test does not pass in. All files live under tmp_path.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import book_dna as D
from backend.services import family_scorecard as FS
from backend.services import results_voice as RV
from scripts import family_scorecard as CLI

NOW = datetime.now(timezone.utc).replace(microsecond=0)
RID = NOW.strftime("%Y-%m-%dT%H%M%SZ")
N = 60                    # sessions of the long books (>= every floor: beta 20, early 21)
N_SHORT = 8               # < BOOK_DNA_MIN_BETA_OBS


def _sessions(n: int) -> list[str]:
    d = date.today() - timedelta(days=1)
    out: list[str] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return sorted(out)


def _spy_returns(n: int = N) -> np.ndarray:
    return np.random.default_rng(55).normal(0.0012, 0.004, n)


def _two_x_series(n: int = N) -> list:
    r = _spy_returns(n)
    return [(d, float(2 * x), float(x)) for d, x in zip(_sessions(n + 1)[1:], r)]


def _compound(xs) -> float:
    return 100 * (float(np.prod([1 + x for x in xs])) - 1)


# ── book_dna: the exposure block and the drawdown ──────────────────────────

def test_a_book_that_is_exactly_twice_spy_has_beta_two_and_no_residual():
    s = _two_x_series()
    beta = D.beta_of(s, D.params()["min_beta_obs"])
    assert beta["value"] == pytest.approx(2.0, abs=1e-6) and beta["n_obs"] == N
    rp, sp = _compound(b for _, b, _ in s), _compound(x for _, _, x in s)
    me = D.market_exposure(s, beta, return_pct=rp, spy_leg_pct=sp, sessions=N, window=(s[0][0], s[-1][0]))
    assert me["beta"]["value"] == pytest.approx(2.0, abs=1e-3) and me["beta"]["n_obs"] == N
    assert me["beta"]["se"] == pytest.approx(0.0, abs=1e-6)
    # the residual r_book - beta x r_SPY is zero every session, so it compounds to zero
    assert me["series_beta_adjusted_pp"]["value"] == pytest.approx(0.0, abs=1e-6)
    assert all(abs(m["beta_adjusted_pp"]) < 1e-6 for m in me["by_month"])
    # `return - beta x SPY leg` is NOT zero for this book: it carries the compounding of 2x in a
    # rising window (here over half a point). That is why the scorecard reads the residual above.
    bax = me["beta_adjusted_excess_pp"]
    assert bax["value"] == pytest.approx(rp - 2.0 * sp, abs=1e-3) and sp > 0 and bax["value"] > 0.5
    assert bax["raw_excess_pp"] == pytest.approx(rp - sp, abs=1e-3)
    x = RV.exposure_view({"market_exposure": me})
    assert x["residual_pp"] == pytest.approx(0.0, abs=1e-6) and x["residual_why"] is None
    assert x["beta_adjusted_excess_pp"] == bax["value"]


def test_fewer_sessions_than_the_floor_is_cannot_determine_with_a_reason():
    floor = D.params()["min_beta_obs"]
    s = _two_x_series(floor - 1)
    beta = D.beta_of(s, floor)
    me = D.market_exposure(s, beta, return_pct=1.0, spy_leg_pct=0.5, sessions=floor - 1)
    for k in ("beta", "beta_adjusted_excess_pp", "up_capture", "down_capture"):
        assert me[k]["value"] == D.CANNOT_DETERMINE
        assert f"{floor - 1} period returns < {floor}" in me[k]["why"]


def test_no_price_series_is_cannot_determine_never_zero():
    me = D.market_exposure([], D.beta_of([], 20), return_pct=3.0, spy_leg_pct=1.0)
    assert me["beta"]["value"] == D.CANNOT_DETERMINE and "no period-return series" in me["beta"]["why"]
    assert me["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE
    dd = D.drawdown_of([])
    assert dd["value"] == D.CANNOT_DETERMINE and dd["why"] and dd["n_periods"] == 0


def test_drawdown_is_the_largest_fall_from_a_peak():
    d = _sessions(5)
    s = [(d[0], 0.10, 0.0), (d[1], -0.50, 0.0), (d[2], 0.10, 0.0), (d[3], 0.20, 0.0), (d[4], -0.10, 0.0)]
    dd = D.drawdown_of(s, sessions=5)
    assert dd["value"] == pytest.approx(-50.0, abs=1e-6)
    assert dd["peak"] == d[0] and dd["trough"] == d[1] and dd["n_periods"] == 5
    # a book that only rises has fallen 0 from its peak -- a number, with its series beside it
    up = D.drawdown_of([(x, 0.01, 0.0) for x in d])
    assert up["value"] == 0.0 and up["n_periods"] == 5


# ── a synthetic fleet, built by the real book_dna ──────────────────────────

def _world() -> tuple[dict, dict]:
    """Four night books: two_x and two_x_copy (2 x SPY: one bet), indep (half of SPY plus its
    own noise: a different bet), and short (its last 8 sessions). Returns (roi receipt, book_dna receipt) as the real code builds them."""
    dates = _sessions(N + 1)
    r = _spy_returns()
    spy = 100 * np.cumprod(np.concatenate([[1.0], 1 + r]))
    noise = 0.5 * r + np.random.default_rng(7).normal(0.0, 0.002, N)
    navs = {"two_x": np.cumprod(np.concatenate([[1.0], 1 + 2 * r])),
            "two_x_copy": np.cumprod(np.concatenate([[1.0], 1 + 2 * r])),
            "indep": np.cumprod(np.concatenate([[1.0], 1 + noise]))}
    bars = pd.DataFrame([{"symbol": "SPY", "date": pd.Timestamp(d), "open": c, "close": c}
                         for d, c in zip(dates, spy)])
    px = D.Prices(bars)
    night_nav = {k: [(d, float(v)) for d, v in zip(dates, nav)] for k, nav in navs.items()}
    night_nav["short"] = night_nav["indep"][-(N_SHORT + 1):]

    def row(account: str) -> dict:
        nav = night_nav[account]
        inc, last = nav[0][0], nav[-1][0]
        ret = 100 * (nav[-1][1] / nav[0][1] - 1)
        sp = 100 * (px.close_on_or_before("SPY", last) / px.close_on_or_before("SPY", inc) - 1)
        return {"account": account, "family": "night_books", "book_id": account, "inception": inc,
                "last_mark": last, "start_capital": 1e6, "equity": 1e6 * (1 + ret / 100), "roi_pct": ret,
                "spy_same_window_pct": sp, "vs_spy_pp": ret - sp, "status": "LIVE", "spy_base": "close",
                "graded_against": None, "note": "", "n_positions": None, "source": "test"}

    roi = {"schema": "paper_accounts_roi/1", "run_id": RID, "licence": "PRODUCT_EXPERIMENT",
           "generated_utc": NOW.isoformat(), "rows": [row(a) for a in ("two_x", "two_x_copy", "indep", "short")]}
    inputs = {"gaps": {}, "books": [], "leaderboards": [], "night_nav": night_nav, "night_decisions": None,
              "sector_map": {}, "sector_source": "test"}
    dna = D.build(roi, inputs, px, today=date.today(), prices_source="injected")
    return roi, json.loads(json.dumps(dna, default=str))


@pytest.fixture(scope="module")
def world() -> tuple[dict, dict]:
    return _world()


@pytest.fixture
def root(tmp_path: Path, world) -> Path:
    roi, dna = world
    pa = tmp_path / "optimus" / "paper_accounts"
    pa.mkdir(parents=True)
    (pa / f"roi_{RID}.json").write_text(json.dumps(roi), encoding="utf-8")
    (pa / f"book_dna_{RID}.json").write_text(json.dumps(dna), encoding="utf-8")
    return tmp_path / "optimus"


def _files(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_every_book_record_carries_the_exposure_block_and_a_drawdown(world):
    _, dna = world
    by = {b["account"]: b for b in dna["books"]}
    assert set(by) == {"two_x", "two_x_copy", "indep", "short"}
    two = by["two_x"]["market_exposure"]
    assert two["beta"]["value"] == pytest.approx(2.0, abs=1e-3) and two["n_obs"] == N
    assert two["series_beta_adjusted_pp"]["value"] == pytest.approx(0.0, abs=1e-3)
    assert two["estimation_window"]["comparable"] is True
    assert isinstance(by["two_x"]["max_drawdown"]["value"], float) and by["two_x"]["max_drawdown"]["value"] <= 0
    sh = by["short"]["market_exposure"]
    assert sh["beta"]["value"] == D.CANNOT_DETERMINE and f"{N_SHORT} period returns <" in sh["beta"]["why"]
    assert sh["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE and sh["n_obs"] == N_SHORT
    # the drawdown needs no floor: eight sessions still have a peak and a trough
    assert isinstance(by["short"]["max_drawdown"]["value"], float)


def test_scorecard_groups_the_two_copies_into_one_family(world):
    roi, dna = world
    sc = FS.build(roi, dna, roi_path="roi.json", dna_path="book_dna.json", now=NOW, run_id=RID)
    assert sc["status"] == "OK" and sc["failures"] == []
    fams = {f["family"]: f for f in sc["families"]}
    assert sc["counts"]["n_families"] == 3 and sc["counts"]["n_strategy_books"] == 4
    twin_family = next(f for f in sc["families"] if f["n_members"] == 2)
    assert sorted(twin_family["members"]) == ["two_x", "two_x_copy"]
    # no holdings are recorded for night books, so each member is its own bet BY HOLDINGS and
    # the join came from the daily-excess correlation: the existing rule, not a new one
    assert twin_family["n_distinct_bets_by_holdings"] == 2
    assert twin_family["beta"]["value"] == pytest.approx(2.0, abs=1e-3)
    assert twin_family["beta_adjusted_excess_pp"]["value"] == pytest.approx(0.0, abs=1e-3)
    assert twin_family["beta_adjusted_excess_pp"]["return_minus_beta_x_spy_leg_pp"] > 0.5
    assert twin_family["ahead_raw"] is True and twin_family["ahead_beta_adjusted"] is False
    assert twin_family["beta_adjusted_excess_pp"]["n_members_determined"] == 2
    assert twin_family["raw_excess_pp"] == pytest.approx(roi["rows"][0]["vs_spy_pp"], abs=1e-3)
    assert twin_family["sessions"] == {"min": N, "max": N, "median": N}
    assert isinstance(twin_family["max_drawdown_pct"]["value"], float)
    assert twin_family["twin_gap_pp"]["value"] is None and twin_family["twin_gap_pp"]["why"]
    sh = fams["short"]
    assert sh["beta"]["value"] == D.CANNOT_DETERMINE and "period returns <" in sh["beta"]["why"]
    assert sh["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE and sh["ahead_beta_adjusted"] is None
    # the top line: counted from the rows themselves
    c = sc["counts"]
    assert c["n_ahead_raw_excess"] == sum(1 for f in sc["families"] if f["raw_excess_pp"] > 0)
    assert c["n_beta_adjusted_determinable"] == 2 and c["n_beta_adjusted_cannot_determine"] == 1
    assert 0.3 < fams["indep"]["beta"]["value"] < 0.7
    # the 2 x SPY family is ahead raw and NOT ahead after beta; nothing clears its MDE both ways
    assert c["n_beta_adjusted_ahead_beyond_mde"] == 0 and c["family_beta_median"] == pytest.approx(1.2, abs=0.2)
    assert c["n_family_beta_above_high_beta_flag"] == 1
    # `short` has too few sessions to be compared with anyone: its own family by default
    assert fams["short"]["independence_tested"] is False and twin_family["independence_tested"] is True
    assert c["n_families_independence_not_testable"] == 1
    assert "1 of the 3 families could not be compared" in sc["second_line"]
    lead, worst = FS.ends(sc)
    assert len(lead) == 2 and len(worst) == 1 and not {f["family"] for f in lead} & {f["family"] for f in worst}
    assert c["n_ahead_beta_adjusted"] == sum(
        1 for f in sc["families"] if isinstance(f["beta_adjusted_excess_pp"]["value"], float)
        and f["beta_adjusted_excess_pp"]["value"] > 0)
    assert (f"{c['n_families']} independent families from 4 live strategy books" in sc["top_line"]
            and f"raw excess: {c['n_ahead_raw_excess']} of 3" in sc["top_line"]
            and f"beta-adjusted excess: {c['n_ahead_beta_adjusted']} of 2 determinable" in sc["top_line"])
    a = sc["exposure_audit"]
    assert a["n_live_books"] == 4 and a["n_beta_and_residual"] == 3
    assert a["n_cannot_determine_with_reason"] == 1 and a["n_missing"] == 0


def test_every_label_prints_its_false_fire_rate(world):
    roi, dna = world
    sc = FS.build(roi, dna, roi_path="roi.json", dna_path="book_dna.json", now=NOW, run_id=RID)
    m = C.LABEL_FALSE_FIRE_MEASURED["rates"]
    for f in sc["families"]:
        assert f["labels"]
        for e in f["labels"]:
            assert e["label"] in D.LABEL_LADDER and "[" in e["text"] and D.CANNOT_DETERMINE not in e["text"]
            want = m["REPLICATED"]["rate"] if e["label"] == "REPLICATED" else m["EARLY_EVIDENCE"]["rate"]
            assert f"{100 * want:.1f}%" in e["text"]
    md = FS.render_md(sc)
    for f in sc["families"]:
        for e in f["labels"]:
            assert e["text"] in md
    assert "LABEL FALSE-FIRE RATES: EARLY_EVIDENCE fires on 35.8% of random books" in md


def test_label_rate_for_each_rung_and_for_a_changed_rule():
    ff = RV.label_false_fire({"early_min_sessions": C.BOOK_DNA_EARLY_MIN_SESSIONS})
    assert ff["status"] == "OK"
    assert RV.label_rate("EARLY_EVIDENCE", ff)["rate"] == pytest.approx(0.358)
    assert RV.label_rate("REPLICATED", ff)["rate"] == pytest.approx(0.256)
    assert RV.label_tag("OBSERVED(12)", ff) == ("OBSERVED(12) [floor label, no evidence claimed; 35.8% of random "
                                                "books rise above it]")
    assert RV.label_rate("VALIDATED_EDGE", ff)["rate"] == D.CANNOT_DETERMINE
    assert RV.label_rate("SOMETHING_ELSE", ff)["rate"] == D.CANNOT_DETERMINE
    # the measurement holds only for the rule it was taken under
    changed = RV.label_false_fire({"early_min_sessions": C.BOOK_DNA_EARLY_MIN_SESSIONS + 9})
    assert changed["status"] == D.CANNOT_DETERMINE and "label rule changed" in changed["why"]
    assert RV.label_rate("EARLY_EVIDENCE", changed)["rate"] == D.CANNOT_DETERMINE
    assert "CANNOT DETERMINE" in RV.label_tag("EARLY_EVIDENCE", changed)
    assert RV.label_false_fire({}, {"rates": {"EARLY_EVIDENCE": {"rate": 7}}})["status"] == D.CANNOT_DETERMINE


def test_false_fire_rates_can_be_read_from_a_table2_receipt(tmp_path):
    p = tmp_path / "table2_x.json"
    p.write_text(json.dumps({"meta": {"run_utc": NOW.isoformat()}, "all": [{
        "n_books": 1000, "early_or_higher": 0.4, "early_or_higher_time_block_ci95": [0.3, 0.5],
        "early_or_higher_by_window": {"min": 0.0, "max": 0.9}, "replicated_twin": 0.2,
        "replicated_twin_time_block_ci95": [0.1, 0.3], "replicated_twin_by_window": {"min": 0.0, "max": 0.5},
        "replicated_twin_or_sibling_upper_bound": 0.25}]}), encoding="utf-8")
    ff = RV.label_false_fire({}, RV.false_fire_from_table2(p))
    assert ff["status"] == "OK" and ff["rates"]["EARLY_EVIDENCE"]["rate"] == 0.4
    assert "not checked" in ff["rule_check"] and "fires on 40.0%" in ff["line"]
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RV.ResultsVoiceRefused):
        RV.false_fire_from_table2(tmp_path / "bad.json")


def test_twin_gap_is_reported_where_a_random_twin_exists(world):
    roi, dna = json.loads(json.dumps(world[0])), json.loads(json.dumps(world[1]))
    parent = next(b for b in dna["books"] if b["account"] == "indep")
    twin = {**parent, "account": "indep_shadow", "twin_of": "indep", "twin_kind": "random_same_band",
            "category": "twin", "return_pct": parent["return_pct"] - 1.25}
    dna["books"].append(twin)
    roi["rows"].append({**next(r for r in roi["rows"] if r["account"] == "indep"), "account": "indep_shadow",
                        "family": "night_books_twin", "roi_pct": twin["return_pct"]})
    sc = FS.build(roi, dna, roi_path="roi.json", dna_path="book_dna.json", now=NOW, run_id=RID)
    f = next(x for x in sc["families"] if x["family"] == "indep")
    assert f["twin_gap_pp"]["value"] == pytest.approx(1.25, abs=1e-3) and f["twin_gap_pp"]["n_members_with_a_twin"] == 1
    assert sc["counts"]["n_strategy_books"] == 4 and sc["counts"]["n_excluded_controls_twins"] == 1
    assert sc["exposure_audit"]["n_live_books"] == 5          # the twin is audited too


# ── the CLI: exit codes ────────────────────────────────────────────────────

def test_cli_writes_the_scorecard_and_leaves_the_data_root_alone(root, tmp_path, capsys):
    out = tmp_path / "out"
    before = _files(root / "paper_accounts")
    rc = CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()])
    assert rc == 0
    assert _files(root / "paper_accounts") == before
    assert _files(out) == [f"family_scorecard_{RID}.json", f"family_scorecard_{RID}.md",
                           f"results_voice_{RID}.json", f"results_voice_{RID}.md"]
    sc = json.loads((out / f"family_scorecard_{RID}.json").read_text(encoding="utf-8"))
    assert sc["status"] == "OK" and sc["counts"]["n_families"] == 3
    assert sc["input_age"]["status"] == "FRESH" and sc["input_age"]["age_days"] == 0.0
    txt = capsys.readouterr().out
    assert "FAMILY SCORECARD as of" in txt and "LEADING 1:" in txt and "WORST 1:" in txt
    assert f"live folder files before/after: {len(before)}/{len(before)}" in txt
    voice = (out / f"results_voice_{RID}.md").read_text(encoding="utf-8")
    assert "\nBETA-ADJUSTED: " in voice and "\nLABEL FALSE-FIRE RATES: " in voice


def test_cli_is_deterministic_on_a_rerun(root, tmp_path):
    out = tmp_path / "out"
    args = ["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat(), "--json"]
    assert CLI.main(args) == 0
    a = (out / f"family_scorecard_{RID}.json").read_bytes()
    assert CLI.main(args) == 0
    assert (out / f"family_scorecard_{RID}.json").read_bytes() == a


def test_cli_refuses_an_empty_folder(tmp_path, capsys):
    (tmp_path / "optimus" / "paper_accounts").mkdir(parents=True)
    out = tmp_path / "out"
    assert CLI.main(["--data-root", str(tmp_path / "optimus"), "--out", str(out)]) == 2
    assert "REFUSED family_scorecard: EMPTY_INPUT" in capsys.readouterr().out
    assert not out.exists()
    # and a data root with no paper_accounts folder at all
    assert CLI.main(["--data-root", str(tmp_path / "nowhere"), "--out", str(out)]) == 2
    assert not out.exists()


def test_cli_refuses_a_receipt_with_no_rows(root, tmp_path, capsys):
    p = root / "paper_accounts" / f"roi_{RID}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["rows"] = []
    p.write_text(json.dumps(d), encoding="utf-8")
    out = tmp_path / "out"
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 2
    assert "EMPTY_INPUT" in capsys.readouterr().out and not out.exists()


def test_cli_refuses_a_stale_receipt_and_an_undateable_one(root, tmp_path, capsys):
    out = tmp_path / "out"
    late = NOW + timedelta(days=float(C.FAMILY_SCORECARD_STALE_DAYS) + 1)
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", late.isoformat()]) == 2
    assert "STALE_INPUT" in capsys.readouterr().out and not out.exists()
    # one hour inside the limit is still fresh
    ok = NOW + timedelta(days=float(C.FAMILY_SCORECARD_STALE_DAYS)) - timedelta(hours=1)
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", ok.isoformat()]) == 0
    age = FS.receipt_age({"generated_utc": "not a time"}, "not-a-run-id", NOW, 4)
    assert age["status"] == "UNKNOWN"
    with pytest.raises(RV.ResultsVoiceRefused, match="UNDATED_INPUT"):
        FS.build({"rows": [{"account": "a"}], "generated_utc": None}, {"books": [{"account": "a"}]},
                 roi_path="r", dna_path="d", now=NOW, run_id=None)


def test_cli_refuses_a_book_dna_that_predates_the_exposure_block(root, tmp_path, capsys):
    p = root / "paper_accounts" / f"book_dna_{RID}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    for b in d["books"]:
        b.pop("market_exposure")
    p.write_text(json.dumps(d), encoding="utf-8")
    out = tmp_path / "out"
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 2
    assert "NO_EXPOSURE_BLOCK" in capsys.readouterr().out and not out.exists()


def test_cli_fails_when_one_live_book_has_no_exposure_block(root, tmp_path, capsys):
    p = root / "paper_accounts" / f"book_dna_{RID}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    next(b for b in d["books"] if b["account"] == "indep").pop("market_exposure")
    p.write_text(json.dumps(d), encoding="utf-8")
    out = tmp_path / "out"
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 3
    sc = json.loads((out / f"family_scorecard_{RID}.json").read_text(encoding="utf-8"))
    assert sc["status"] == "FAILED" and "indep" in sc["failures"][0]
    assert sc["exposure_audit"]["missing"][0]["account"] == "indep"
    assert "FAILED: 1 live book(s)" in capsys.readouterr().out
    assert "FAILED: 1 live book(s)" in (out / f"family_scorecard_{RID}.md").read_text(encoding="utf-8")


def test_cli_fails_when_a_label_has_no_false_fire_rate(root, tmp_path, monkeypatch, capsys):
    stale_rule = {**C.LABEL_FALSE_FIRE_MEASURED, "early_min_sessions": C.BOOK_DNA_EARLY_MIN_SESSIONS + 9}
    monkeypatch.setattr(C, "LABEL_FALSE_FIRE_MEASURED", stale_rule)
    out = tmp_path / "out"
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 3
    txt = capsys.readouterr().out
    assert "have no false-fire rate" in txt and "label rule changed" in txt
    monkeypatch.delattr(C, "LABEL_FALSE_FIRE_MEASURED")
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 3


def test_cli_refuses_an_out_folder_inside_the_data_root(root, capsys):
    assert CLI.main(["--data-root", str(root), "--out", str(root / "paper_accounts" / "x")]) == 2
    assert "OUT_INSIDE_INPUT" in capsys.readouterr().out
    assert not (root / "paper_accounts" / "x").exists()


def test_cli_rebuild_refuses_a_data_root_the_checkout_is_not_configured_for(root, tmp_path, capsys):
    out = tmp_path / "out"
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--rebuild-dna"]) == 2
    assert "AEGIS_DATA_DIR" in capsys.readouterr().out and not out.exists()
