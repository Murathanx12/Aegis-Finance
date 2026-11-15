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


@pytest.fixture(autouse=True)
def _measurement_dated_now(monkeypatch):
    """The false-fire measurement expires (fix round), and config dates it on a calendar day:
    every test here re-dates it to the test's own NOW so no test depends on today's date."""
    monkeypatch.setattr(C, "LABEL_FALSE_FIRE_MEASURED", {**C.LABEL_FALSE_FIRE_MEASURED,
                                                         "measured_utc": NOW.isoformat()})


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
    assert fams["short"]["compared_with_the_others"] is False and twin_family["compared_with_the_others"] is True
    assert c["n_families_not_comparable_with_the_others"] == 1
    assert "1 of the 3 families could not be compared" in sc["second_line"]
    lead, worst = FS.ends(sc)
    assert len(lead) == 2 and len(worst) == 1 and not {f["family"] for f in lead} & {f["family"] for f in worst}
    assert c["n_ahead_beta_adjusted"] == sum(
        1 for f in sc["families"] if isinstance(f["beta_adjusted_excess_pp"]["value"], float)
        and f["beta_adjusted_excess_pp"]["value"] > 0)
    assert (f"{c['n_families']} families distinct under the holdings-Jaccard >= 0.8 / excess-correlation >= 0.9 "
            f"rule (an upper bound) from 4 live strategy books" in sc["top_line"]
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
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 0
    assert FS.receipt_age({"generated_utc": NOW.isoformat()}, None,
                          NOW + timedelta(days=float(C.FAMILY_SCORECARD_STALE_DAYS)) - timedelta(hours=1),
                          float(C.FAMILY_SCORECARD_STALE_DAYS))["status"] == "FRESH"
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


# ── fix round (review of PR #164): each test below fails on 7c5d5b11 ────────

def _keys(x, acc=None) -> set:
    acc = set() if acc is None else acc
    if isinstance(x, dict):
        for k, v in x.items():
            acc.add(str(k))
            _keys(v, acc)
    elif isinstance(x, list):
        for v in x:
            _keys(v, acc)
    return acc


def test_blocker1_no_headline_or_field_calls_the_families_independent(world):
    roi, dna = world
    sc = FS.build(roi, dna, roi_path="roi.json", dna_path="book_dna.json", now=NOW, run_id=RID)
    assert "independen" not in sc["top_line"].lower()
    assert "(an upper bound)" in sc["top_line"] and "effective number of bets" in sc["top_line"]
    assert not [k for k in _keys(sc) if "independen" in k.lower()]
    md = FS.render_md(sc)
    assert not [ln for ln in md.splitlines() if ln.startswith(("#", "FAMILY SCORECARD")) and "independen" in ln.lower()]
    # three families, one of them eight sessions old: too few to say, and the top line says so
    eb = sc["effective_bets"]
    assert eb["status"] == D.CANNOT_DETERMINE and eb["raw"] == D.CANNOT_DETERMINE and "needs >=" in eb["why"]
    assert f"effective number of bets {D.CANNOT_DETERMINE} (" in sc["top_line"]


def _eb_world(extra_copy: bool, crash: bool = False) -> tuple[list, dict]:
    """Three families whose returns are EXACTLY uncorrelated (orthonormal, zero-mean columns)
    against a flat SPY, optionally a fourth that copies the first."""
    n = int(C.FAMILY_SCORECARD_EFFECTIVE_MIN_DATES) + 10
    dates = _sessions(n)
    m = np.random.default_rng(3).normal(size=(n, 3))
    q, _ = np.linalg.qr(m - m.mean(axis=0))
    q = 0.05 * q
    if crash:
        q[n // 2, :] = -0.5                      # one date on which every family has its worst day
    cols = {"fam_a": q[:, 0], "fam_b": q[:, 1], "fam_c": q[:, 2]}
    if extra_copy:
        cols["fam_a_again"] = q[:, 0]
    books = {k: {"period_returns": [[d, float(x), 0.0] for d, x in zip(dates, v)]} for k, v in cols.items()}
    return [{"family": k, "members": [k]} for k in cols], books


def test_blocker1_effective_bets_is_the_participation_ratio_with_known_answers():
    fams, books = _eb_world(extra_copy=False)
    eb = FS.effective_bets(fams, books)
    assert eb["status"] == "OK" and eb["raw"] == pytest.approx(3.0, abs=0.01) and eb["excess"] == pytest.approx(3.0, abs=0.01)
    assert eb["n_families"] == 3 and eb["n_dates"] == int(C.FAMILY_SCORECARD_EFFECTIVE_MIN_DATES) + 10
    assert eb["components_at_loose_join_excess"] == 3 and abs(eb["median_pairwise_corr_raw"]) < 1e-6
    # a fourth family that copies the first: eigenvalues 2, 1, 1, 0 -> 16 / 6
    fams, books = _eb_world(extra_copy=True)
    eb = FS.effective_bets(fams, books)
    assert eb["raw"] == pytest.approx(16 / 6, abs=0.01) and eb["n_families"] == 4
    assert eb["components_at_loose_join_excess"] == 3 and eb["components_at_loose_join_raw"] == 3
    # four copies of one series are one bet
    one = {k: books["fam_a"] for k in ("w", "x", "y", "z")}
    eb = FS.effective_bets([{"family": k, "members": [k]} for k in one], one)
    assert eb["raw"] == pytest.approx(1.0, abs=0.01) and eb["components_at_loose_join_excess"] == 1


def test_blocker1_worst_day_share_and_the_reasons_it_cannot_be_determined():
    fams, books = _eb_world(extra_copy=False, crash=True)
    eb = FS.effective_bets(fams, books)
    wd = eb["worst_day"]
    assert wd["share"] == 1.0 and wd["n_families"] == 3
    assert wd["date"] == _sessions(int(C.FAMILY_SCORECARD_EFFECTIVE_MIN_DATES) + 10)[(int(C.FAMILY_SCORECARD_EFFECTIVE_MIN_DATES) + 10) // 2]
    assert eb["raw"] < 1.5                       # one shared crash makes three "distinct" families one bet
    # a receipt without the series
    none = FS.effective_bets(fams, {k: {} for k in books})
    assert none["status"] == D.CANNOT_DETERMINE and "period_returns" in none["why"]
    # too few common dates
    cut = {k: {"period_returns": v["period_returns"][:5]} for k, v in books.items()}
    few = FS.effective_bets(fams, cut)
    assert few["status"] == D.CANNOT_DETERMINE and "fewer than" in few["why"]


def test_blocker1_book_dna_rows_carry_their_period_returns(world):
    _, dna = world
    two = next(b for b in dna["books"] if b["account"] == "two_x")
    assert len(two["period_returns"]) == N and len(two["period_returns"][0]) == 3
    assert two["period_returns"][0][1] == pytest.approx(2 * two["period_returns"][0][2], abs=1e-7)


def _write_roi(root: Path, **changes) -> None:
    p = root / "paper_accounts" / f"roi_{RID}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    for r in d["rows"]:
        r.update({k: v for k, v in changes.items() if k != "generated_utc"})
    if "generated_utc" in changes:
        d["generated_utc"] = changes["generated_utc"]
    p.write_text(json.dumps(d), encoding="utf-8")


def test_blocker2_marks_weeks_old_refuse_even_when_the_receipt_was_generated_now(root, tmp_path, capsys):
    old = (date.today() - timedelta(days=int(C.FAMILY_SCORECARD_MARK_STALE_DAYS) + 21)).isoformat()
    _write_roi(root, last_mark=old)
    out = tmp_path / "out"
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 2
    txt = capsys.readouterr().out
    assert "REFUSED family_scorecard: STALE_MARKS" in txt and old in txt and not out.exists()
    assert FS.marks_age(old, NOW, 4)["status"] == "STALE"
    assert FS.marks_age((NOW.date() - timedelta(days=4)).isoformat(), NOW, 4)["status"] == "FRESH"
    assert FS.marks_age("soon", NOW, 4)["status"] == "UNKNOWN"


def test_blocker2_a_future_stamp_or_mark_is_refused_never_fresh(root, tmp_path, capsys):
    out = tmp_path / "out"
    _write_roi(root, generated_utc=(NOW + timedelta(days=3)).isoformat())
    assert FS.receipt_age({"generated_utc": (NOW + timedelta(days=3)).isoformat()}, None, NOW, 4)["status"] == "UNKNOWN"
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 2
    assert "UNDATED_INPUT" in capsys.readouterr().out and "FUTURE" in FS.receipt_age(
        {"generated_utc": (NOW + timedelta(days=3)).isoformat()}, None, NOW, 4)["why"]
    assert not out.exists()
    _write_roi(root, generated_utc=NOW.isoformat(), last_mark=(NOW.date() + timedelta(days=9)).isoformat())
    assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 2
    assert "UNDATED_INPUT" in capsys.readouterr().out and not out.exists()
    # a few minutes of clock skew is not the future
    assert FS.receipt_age({"generated_utc": (NOW + timedelta(minutes=2)).isoformat()}, None, NOW, 4)["status"] == "FRESH"


def test_blocker3_the_false_fire_measurement_expires(root, tmp_path, capsys):
    p = {"early_min_sessions": C.BOOK_DNA_EARLY_MIN_SESSIONS}
    limit = float(C.LABEL_FALSE_FIRE_MAX_AGE_DAYS)
    assert RV.label_false_fire(p, now=NOW + timedelta(days=limit - 1))["status"] == "OK"
    late = NOW + timedelta(days=limit + 1)
    ff = RV.label_false_fire(p, now=late)
    assert ff["status"] == D.CANNOT_DETERMINE and f"measurement of {NOW.date().isoformat()} expired" in ff["why"]
    tag = RV.label_tag("EARLY_EVIDENCE", ff)
    assert tag.startswith(f"EARLY_EVIDENCE [false-fire rate CANNOT DETERMINE (measurement of {NOW.date().isoformat()} expired")
    undated = RV.label_false_fire(p, {**C.LABEL_FALSE_FIRE_MEASURED, "measured_utc": None}, now=NOW)
    assert undated["status"] == D.CANNOT_DETERMINE and "no date" in undated["why"]
    # the rule invalidation still stands
    assert "label rule changed" in RV.label_false_fire({"early_min_sessions": 99}, now=NOW)["why"]
    # the CLI: a fresh receipt read with a measurement older than the limit exits 3
    old = {**C.LABEL_FALSE_FIRE_MEASURED, "measured_utc": (NOW - timedelta(days=limit + 2)).isoformat()}
    import pytest as _pt
    mp = _pt.MonkeyPatch()
    try:
        mp.setattr(C, "LABEL_FALSE_FIRE_MEASURED", old)
        out = tmp_path / "out"
        assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 3
    finally:
        mp.undo()
    txt = capsys.readouterr().out
    assert "have no false-fire rate" in txt and "expired" in txt


def test_item4_families_with_t_beyond_two_are_counted_and_named(world):
    roi, dna = world[0], json.loads(json.dumps(world[1]))
    b = next(x for x in dna["books"] if x["account"] == "indep")
    val = b["market_exposure"]["series_beta_adjusted_pp"]["value"]
    b["market_exposure"]["series_beta_adjusted_pp"]["se_pp"] = abs(val) / 2.5        # t = -2.5, below its MDE
    b["market_exposure"]["series_beta_adjusted_pp"]["mde_pp"] = 2.8 * abs(val) / 2.5
    sc = FS.build(roi, dna, roi_path="roi.json", dna_path="book_dna.json", now=NOW, run_id=RID)
    assert val < 0
    c = sc["counts"]
    assert c["n_t_named_behind"] == 1 and c["n_t_named_ahead"] == 0 and c["n_beta_adjusted_behind_beyond_mde"] == 0
    assert c["t_named"] == [{"family": "indep", "t": -2.5}]
    line = sc["second_line"]
    assert "|t| >= 2: 0 ahead and 1 behind (indep t -2.50)" in line
    assert "cannot be distinguished from zero" not in line
    assert "expected in each direction by chance" in line
    assert "treats daily residuals as independent draws; autocorrelation would widen it" in line
    # 1 family with an SE at |t| >= 2: 0.0455 x 1 expected in all
    assert c["n_with_t"] == 1 and c["t_named_expected_by_chance_each_direction"] == pytest.approx(0.02, abs=0.005)
    assert "(t -2.50)" in FS.family_line(next(f for f in sc["families"] if f["family"] == "indep"))


def _sparse_series(step: int, start: int = 0) -> tuple[list, dict, float, float, list]:
    """A 0.8 x SPY book read every `step` sessions from session `start` of a 60-session window:
    (series, SPY closes by date, the WINDOW's book return %, the window's SPY return %, dates)."""
    dates = _sessions(N + 1)
    r = _spy_returns()
    spy = np.cumprod(np.concatenate([[1.0], 1 + r]))
    nav = np.cumprod(np.concatenate([[1.0], 1 + 0.8 * r]))
    idx = list(range(start, N + 1, step))
    if idx[-1] != N:
        idx.append(N)
    s = [(dates[j], float(nav[j] / nav[i] - 1), float(spy[j] / spy[i] - 1)) for i, j in zip(idx, idx[1:])]
    return (s, {d: float(100 * c) for d, c in zip(dates, spy)}, 100 * float(nav[-1] - 1),
            100 * float(spy[-1] - 1), dates)


def test_item5_multi_session_periods_that_span_the_window_are_determined_with_their_coverage():
    s, closes, rp, sp, dates = _sparse_series(step=2)
    assert len(s) == N // 2
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=rp, spy_leg_pct=sp, sessions=N,
                           window=(dates[0], dates[-1]), spy_close=closes)
    w = me["estimation_window"]
    assert w["coverage"] == 0.5 and w["span_coverage"] >= 0.95 and w["comparable"] is True
    assert "accepted" in w["coverage_note"] and "50% by periods" in w["coverage_note"]
    assert isinstance(me["beta_adjusted_excess_pp"]["value"], float)
    x = RV.exposure_view({"market_exposure": me})
    assert isinstance(x["residual_pp"], float) and x["coverage"] == 0.5 and x["coverage_note"]
    fam = {"min_member_coverage_by_periods": 0.5, "coverage_notes": [w["coverage_note"]]}
    assert FS._cov(fam) == " (coverage 50% by periods)"


def test_item5_a_series_that_starts_weeks_late_stays_cannot_determine_whatever_its_return():
    s, closes, _rp, sp, dates = _sparse_series(step=1, start=N // 2)
    own = 100 * (float(np.prod([1 + b for _, b, _ in s])) - 1)
    # even a receipt return that happens to equal the late series' own return is not enough
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=own, spy_leg_pct=sp, sessions=N,
                           window=(dates[0], dates[-1]), spy_close=closes)
    w = me["estimation_window"]
    assert w["coverage"] == 0.5 and w["span_coverage"] == pytest.approx(0.5, abs=0.02) and w["comparable"] is False
    assert me["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE and w["coverage_note"] is None
    # and sparse periods that do NOT reproduce the receipt return stay refused too
    s2, closes2, rp2, sp2, dates2 = _sparse_series(step=2)
    me2 = D.market_exposure(s2, D.beta_of(s2, 20), return_pct=rp2 + 1.5, spy_leg_pct=sp2, sessions=N,
                            window=(dates2[0], dates2[-1]), spy_close=closes2)
    assert me2["estimation_window"]["comparable"] is False


def test_item6_a_truncated_receipt_is_a_named_refusal_not_a_traceback(root, tmp_path, capsys):
    out = tmp_path / "out"
    for name in (f"book_dna_{RID}.json", f"roi_{RID}.json"):
        p = root / "paper_accounts" / name
        whole = p.read_text(encoding="utf-8")
        p.write_text(whole[: len(whole) // 2], encoding="utf-8")
        assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 2
        txt = capsys.readouterr().out
        assert "REFUSED family_scorecard: UNREADABLE_INPUT" in txt and name in txt and not out.exists()
        p.write_text("[1, 2]", encoding="utf-8")
        assert CLI.main(["--data-root", str(root), "--out", str(out), "--now", NOW.isoformat()]) == 2
        assert "UNREADABLE_INPUT" in capsys.readouterr().out
        p.write_text(whole, encoding="utf-8")


def test_item6_the_cli_says_leaders_are_chosen_after_the_fact(root, tmp_path, capsys):
    assert CLI.main(["--data-root", str(root), "--out", str(tmp_path / "out"), "--now", NOW.isoformat()]) == 0
    assert "Leaders are chosen after the fact" in capsys.readouterr().out


def test_item6_a_constant_drift_book_is_not_called_a_flat_nav():
    dates = _sessions(N + 1)[1:]
    s = [(d, 0.001, float(x)) for d, x in zip(dates, _spy_returns())]
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=6.0, spy_leg_pct=5.0, sessions=N)
    why = me["beta"]["why"]
    assert me["beta"]["value"] == D.CANNOT_DETERMINE
    assert "flat NAV" not in why and "constant period return (+0.1000% in each of 60 periods" in why
    flat = [(d, 0.0, float(x)) for d, x in zip(dates, _spy_returns())]
    assert "flat NAV" in D.market_exposure(flat, D.beta_of(flat, 20), return_pct=0.0, spy_leg_pct=5.0)["beta"]["why"]


def test_blocker1_the_matrix_keeps_as_many_families_as_share_the_dates():
    """Five families on one calendar and one long family on another: the odd one is dropped,
    not the five (dropping fewest-dates-first kept 6 of 45 families on live data)."""
    n = int(C.FAMILY_SCORECARD_EFFECTIVE_MIN_DATES)
    dates = _sessions(3 * n)
    rng = np.random.default_rng(11)
    books = {f"f{i}": {"period_returns": [[d, float(x), 0.0] for d, x in zip(dates[-n:], rng.normal(0, 0.01, n))]}
             for i in range(5)}
    books["long_odd"] = {"period_returns": [[d, float(x), 0.0] for d, x in
                                            zip(dates[: 3 * n - 5], rng.normal(0, 0.01, 3 * n - 5))]}
    eb = FS.effective_bets([{"family": k, "members": [k]} for k in books], books)
    assert eb["status"] == "OK" and eb["n_families"] == 5 and eb["n_dates"] == n
    assert eb["families_left_out"]["dropped_to_reach_common_dates"] == ["long_odd"]
