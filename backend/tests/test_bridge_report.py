"""The backtest -> forward bridge: renders while every forward is PENDING, opens an
investigation only on a book that really trails, and the README section it
writes carries the required sentences with a receipt beside every number.

Offline: synthetic bars and books, plus the committed leaderboard receipt.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import bridge_report as BR

REPO = Path(__file__).resolve().parents[2]
ROW = {"id": "toy_rule", "dev_cagr": 0.10, "dev_spy_cagr": 0.13, "sealed_cagr": 0.40,
       "sealed_spy_cagr": 0.20, "sealed_vs_spy": 0.20, "sealed_dsr": 0.05, "max_dd": -0.35,
       "turnover_annual": 4.0, "mean_active_monthly": 0.01, "information_ratio_annual": 0.6,
       "caveat": ""}


def _bars(end: str = "2026-09-25") -> pd.DataFrame:
    cal = pd.bdate_range(end=end, periods=320)
    rows = []
    for k, d in enumerate(cal):
        for s, p in (("SPY", 500 + k * 0.2), ("AAA", 50 + k * 0.05), ("BBB", 20 + k * 0.01)):
            rows.append((s, d, p * 0.999, p * 1.01, p * 0.99, p, 1e7))
    return pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close", "volume"])


def _book(name: str = "lib_toy_rule_sealed_2026-09-26", asof: str = "2026-09-26") -> dict:
    return {"name": name, "kind": "personal", "model": "rule:strategy_library:toy_rule",
            "objective": "x", "asof": asof, "book_id": "b1", "n_positions": 2,
            "horizon_days": [1, 5, 21], "benchmark": "SPY",
            "positions": [{"ticker": "AAA", "weight": 0.5}, {"ticker": "BBB", "weight": 0.5},
                          {"ticker": "CASH", "weight": 0.0}]}


def test_bridge_renders_with_every_forward_pending(tmp_path):
    board = {"all_rows": [ROW]}
    doc = BR.report(today=date(2026, 9, 26), out_md=tmp_path / "BRIDGE.md", out_dir=tmp_path,
                    books=[_book()], bars=_bars(), board=board, board_path="lb.json",
                    earnings={}, semis={"status": "SKIPPED", "why": "test"})
    md = (tmp_path / "BRIDGE.md").read_text(encoding="utf-8")
    assert "PENDING (entry 2026-09-28)" in md
    assert "`lib_toy_rule_sealed_2026-09-26`" in md
    assert "+40.0%" in md and "+20.0%" in md                 # sealed CAGR (SPY) from the row
    r = doc["rows"][0]
    for k in ("forward_return", "forward_spy", "forward_relative", "expected_relative_to_date"):
        assert r[k] == "PENDING (entry 2026-09-28)"
    assert r["investigation"] is None
    assert doc["regime"]["status"] == "OK" and "SPY above 200d" in doc["regime"]["label"]
    assert (tmp_path / "bridge_2026-09-26.json").exists()
    assert "None open." in md


def test_a_book_the_receipt_does_not_know_still_renders(tmp_path):
    doc = BR.report(today=date(2026, 9, 26), out_md=tmp_path / "B.md", out_dir=tmp_path,
                    books=[_book("lib_forecast_dispersion_v1_2026-09-26")] , bars=_bars(),
                    board={"all_rows": []}, board_path="lb.json", earnings={},
                    semis={"status": "SKIPPED", "why": "test"})
    assert doc["rows"][0]["status"].startswith("FORWARD-ONLY")


def _path(n: int, rel: float, exp_per_session: float = 0.0005) -> list[dict]:
    return [{"as_of": f"d{i}", "sessions": i + 1, "relative": rel,
             "expected": exp_per_session * (i + 1)} for i in range(n)]


def _inv(path, **kw):
    args = dict(path=path, sigma_m=0.05, row=ROW, book_grade={"n_unpriceable": 0,
                "weight_priced": 1.0, "entry_cost_bps": 5.0, "dead_share": 0.0},
                twins={}, regime_now={"status": "OK", "label": "SPY above 200d, vol mid"},
                regime_at_entry={"status": "OK", "label": "SPY above 200d, vol mid"})
    args.update(kw)
    return BR.investigate(**args)


def test_the_investigation_fires_on_a_trailing_book():
    inv = _inv(_path(30, -0.20))
    assert inv is not None
    assert inv["cause"] in BR.TAXONOMY
    assert inv["cause"] == "UNKNOWN"                   # nothing checkable explains it
    assert set(inv["tests"]) == set(BR.INVESTIGATION_ORDER)


def test_the_investigation_does_not_fire_otherwise():
    assert _inv(_path(30, 0.0)) is None                # on expectation: no trail
    assert _inv(_path(20, -0.20)) is None              # fewer than 21 sessions
    p = _path(30, -0.20)
    p[-5]["relative"] = 0.05                           # one session of the 21 back above the bar
    assert _inv(p) is None
    assert _inv(_path(30, -0.20), sigma_m=None) is None


def test_the_cause_follows_the_declared_order():
    assert _inv(_path(30, -0.20), book_grade={"n_unpriceable": 2})["cause"] == "IMPLEMENTATION"
    assert _inv(_path(30, -0.07))["cause"] == "RANDOMNESS"          # z within 2
    assert _inv(_path(30, -0.20), regime_at_entry={"label": "SPY below 200d, vol high"}
                )["cause"] == "REGIME_SHIFT"
    leak = dict(ROW, caveat="GICS sector is Compustat's CURRENT classification")
    assert _inv(_path(30, -0.20), row=leak)["cause"] == "DATA_LEAK"
    assert _inv(_path(70, -0.20), twins={"random_same_band": 0.0})["cause"] == "FACTOR_DECAY"


def test_expected_relative_and_sigma_come_from_the_receipt_row():
    assert BR.expected_relative(ROW, 252) == pytest.approx(1.4 / 1.2 - 1)
    assert BR.sigma_active_monthly(ROW) == pytest.approx(0.01 * np.sqrt(12) / 0.6)
    assert BR.sigma_active_monthly({"mean_active_monthly": 0.01}) is None


# ───────────────────────────── README section ───────────────────────────────

def _readme_section() -> str:
    return BR.readme_block((REPO / "README.md").read_text(encoding="utf-8"))


def _cited_board() -> tuple[str, dict]:
    """The leaderboard the README section CITES (not the newest one on disk, so
    a later night's leaderboard does not turn this red before the README is
    re-rendered on purpose). Since 2026-09-26 the cite is a RUN receipt."""
    import json
    m = re.search(r"backend/data/optimus/strategy_library/leaderboard_\d{4}-\d{2}-\d{2}T\d{6}Z\.json",
                  _readme_section())
    assert m, "the README backtest section cites no run-id'd leaderboard receipt"
    return m.group(0), json.loads((REPO / m.group(0)).read_text(encoding="utf-8"))


def _cited(pattern: str):
    m = re.search(pattern, _readme_section())
    return m.group(1) if m else None


def test_readme_section_has_the_required_sentences():
    from backend.services import strategy_library as SL
    s = _readme_section()
    _bp, board = _cited_board()
    f = BR.library_facts(board)
    dse = board["dev_selected_sealed_evaluated"]
    t10 = dse["top_10"]
    assert "Nothing passes the multiplicity bar" in s and "vs 0.95" in s
    assert f"best DSR {f['best_dsr']:.2f}" in s
    assert f"{f['n_beat']} of {f['n_rules']} rules beat SPY in the 2024-26 window, median" in s
    assert f"{dse['n_beat_spy_in_both_windows']} of {f['n_rules']} rules beat SPY in both windows" in s
    assert SL.SELECTION_WINDOW_LABEL in s
    assert f"**{t10['mean_selection_window_vs_spy']*100:+.1f} pp/yr**" in s
    assert f"{t10['n_beat_spy']} of {t10['n']} beat SPY" in s
    assert "no forward day graded yet; the first 21-session reading is the 2026-10-26 close" in s.lower()
    assert "entry is the 2026-09-28 open" in s and "since 2026-09-28" not in s
    assert "not an independent engine (shares holdings, fills, cost formula)" in s
    assert "second engine" not in s
    # "sealed" survives only inside field names (`sealed_vs_spy`, `lib_*_sealed_*`)
    assert "sealed" not in s.replace("_sealed", "").replace("sealed_vs_spy", "").lower()
    assert re.search(r"at commit `[0-9a-f]{7,}`", s)
    assert "+28.3%" in s and "+114.8%" in s                         # kept as history
    for r in board["top_by_sealed_vs_spy"][:10]:
        assert f"`{r['id']}`" in s
        assert f"**{r['sealed_vs_spy']*100:+.1f}%**" in s


def test_readme_section_is_the_render_of_the_receipt():
    import json
    bp, board = _cited_board()
    gh = _cited(r"at commit `([0-9a-f]{7,}|UNKNOWN)`")
    rp = _cited(r"`(backend/data/optimus/strategy_library/replication_vectorbt_[^`]+\.json)`")
    brp = _cited(r"bridge receipt `(backend/data/optimus/bridge/bridge_[^`]+\.json)`")
    bridge = json.loads((REPO / brp).read_text(encoding="utf-8")) if brp else None
    assert _readme_section().strip() == BR.readme_section(
        board, bp, git_hash=gh, bridge=bridge, replication=rp, bridge_path=brp).strip()


def test_readme_section_has_no_unreceipted_number():
    receipt = re.compile(r"`[^`]*\.(json|md|jsonl|py)`|\((NEGATIVE_RESULTS\.md)")
    blocks = [b for b in re.split(r"\n\s*\n", _readme_section()) if b.strip()]
    tables = [b for b in blocks if b.lstrip().startswith("|")]
    for b in blocks:
        if not re.search(r"\d", b) or b.lstrip().startswith("#"):
            continue
        if b in tables:
            # a table's receipt is the paragraph right above it, or a path in the table
            k = blocks.index(b)
            assert receipt.search(b) or receipt.search(blocks[k - 1]), b[:120]
            continue
        for line in b.splitlines():
            if re.search(r"\d", line) and line.startswith("- "):
                assert receipt.search(line), line[:120]
        assert receipt.search(b), b[:120]


# ───────────────────── review 2026-09-26: void, gate, regression ─────────────

def test_a_voided_book_is_listed_and_its_ew_twin_is_the_strategy_test(tmp_path):
    parent = dict(_book(), book_id="p1",
                  void={"reason": "VOID_BEFORE_ENTRY: concentration", "who": "t",
                        "voided_utc": "2026-09-26T09:00:00+00:00"})
    ew = dict(_book("lib_toy_rule_sealed_2026-09-26__ew"), kind="twin", twin="ew",
              parent_book_id="p1", book_id="t1",
              positions=[{"ticker": "AAA", "weight": 0.5}, {"ticker": "BBB", "weight": 0.5}])
    other = dict(_book("lib_other_2026-09-26"), book_id="p2")
    doc = BR.report(today=date(2026, 9, 26), out_md=tmp_path / "B.md", out_dir=tmp_path,
                    books=[parent, ew, other], bars=_bars(), board={"all_rows": [ROW]},
                    board_path="lb.json", earnings={},
                    semis={"status": "SMH_NOT_IN_PANEL", "why": "t"})
    md = (tmp_path / "B.md").read_text(encoding="utf-8")
    names = [r["book"] for r in doc["rows"]]
    assert "lib_toy_rule_sealed_2026-09-26" not in names             # never graded
    st = next(r for r in doc["rows"] if r["book"].endswith("__ew"))
    assert st["strategy_test_for_voided"] and st["status"].startswith("STRATEGY TEST")
    assert doc["voided_before_entry"][0]["reason"].startswith("VOID_BEFORE_ENTRY")
    assert "## Voided before entry" in md and "VOID_BEFORE_ENTRY: concentration" in md
    # the gate column: 50/50 books fail construction and say why
    assert "| gate |" in md
    assert all(r["gate"].startswith("CONTROL(") for r in doc["rows"])
    assert "EFFECTIVE_N" in doc["rows"][0]["gate"]
    assert (tmp_path / "freeze_gate_2026-09-26.json").exists()
    assert "`SMH_NOT_IN_PANEL`" in md
    assert "no forward day graded yet" in md.lower()


def test_semis_regression_says_smh_not_in_panel_or_recovers_a_planted_alpha():
    rng = np.random.default_rng(3)
    ents = pd.bdate_range("2024-01-02", periods=40, freq="21B")
    spy_r, smh_r, mom_r = (rng.normal(0.01, 0.04, 40) for _ in range(3))
    net = 0.02 + 1.0 * spy_r + 0.5 * smh_r + 0.3 * mom_r + rng.normal(0, 0.001, 40)
    ser = [{"date": str((e - pd.Timedelta(days=1)).date()), "entry": str(e.date()),
            "net": float(n), "spy": float(s), "window": "sealed"}
           for e, n, s in zip(ents, net, spy_r)]
    doc = {"rows": [{"id": "toy", "monthly_return_series": ser}],
           "reference_series": {"mom_12_1": [{"date": x["date"], "net": float(m)}
                                             for x, m in zip(ser, mom_r)]}}
    assert BR.semis_umd_regression({}, None, rep_doc=doc,
                                   smh=pd.DataFrame())["status"] == "SMH_NOT_IN_PANEL"
    opens = np.r_[100.0, 100.0 * np.cumprod(1 + smh_r)]
    days = list(ents) + [ents[-1] + pd.offsets.BDay(21)]
    smh = pd.DataFrame({"symbol": "SMH", "date": days, "open": opens})
    out = BR.semis_umd_regression({}, None, rep_doc=doc, smh=smh)
    assert out["status"] == "OK"
    x = out["rows"][0]
    assert x["n"] == 39 and x["alpha"] == pytest.approx(0.02, abs=0.002)
    assert x["beta_smh"] == pytest.approx(0.5, abs=0.02) and x["t_alpha"] > 5


# ───────────── 2026-09-27: clusters, factor twins, FACTOR_BETA ──────────────

def _struct(books: dict) -> dict:
    return {"status": "OK", "receipt": "backend/data/optimus/signal_structure/x.json",
            "rho_cut": 0.8, "label": "HINDSIGHT", "books": books}


def _dec(alpha: float = 0.01) -> dict:
    return {"status": "OK", "n": 32, "alpha_monthly": alpha, "t_alpha": 1.0, "r2": 0.4,
            "betas": {"SMH": 0.5, "MTUM": 0.2, "IWM": 1.0},
            "t_betas": {"SMH": 1.0, "MTUM": 0.5, "IWM": 3.0}}


def test_two_books_in_one_cluster_are_one_distinct_bet(tmp_path, monkeypatch):
    # pin the factor bars to the toy panel: the live global_prices cache has
    # carried SMH since f485e9ec, so reading it made this a gate on the machine
    monkeypatch.setattr(BR, "factor_bars",
                        lambda bars: bars[bars["symbol"].isin(BR.FACTOR_ETFS + ("SPY",))])
    a = dict(_book("lib_toy_rule_2026-09-26"), book_id="a")
    b = dict(_book("lib_toy_rule_sealed_2026-09-26"), book_id="b")
    c = dict(_book("lib_other_2026-09-26"), book_id="c")
    st = _struct({
        "lib_toy_rule_2026-09-26": {"cell": "toy_rule@k20", "cluster_full": 7, "cluster_sealed": 3,
                                    "decomposition": _dec(), "dominant_etf": "IWM",
                                    "dominant_beta": 1.0, "dominant_t": 3.0},
        "lib_toy_rule_sealed_2026-09-26": {"cell": "toy_rule@k20", "cluster_full": 7,
                                           "cluster_sealed": 3, "decomposition": _dec(),
                                           "dominant_etf": "IWM", "dominant_beta": 1.0,
                                           "dominant_t": 3.0},
        "lib_other_2026-09-26": {"cell": "other@k20", "cluster_full": 9, "cluster_sealed": 4,
                                 "decomposition": _dec(), "dominant_etf": "SMH",
                                 "dominant_beta": 0.5, "dominant_t": 2.5}})
    doc = BR.report(today=date(2026, 9, 26), out_md=tmp_path / "B.md", out_dir=tmp_path,
                    books=[a, b, c], bars=_bars(), board={"all_rows": [ROW]},
                    board_path="lb.json", earnings={}, semis={"status": "SKIPPED", "why": "t"},
                    structure=st)
    db = doc["distinct_bets"]["full"]
    assert db["n_books"] == 3 and db["n_distinct"] == 2
    assert db["multi_book_clusters"] == {"7": ["lib_toy_rule_2026-09-26",
                                               "lib_toy_rule_sealed_2026-09-26"]}
    md = (tmp_path / "B.md").read_text(encoding="utf-8")
    assert "**3 books under test = 2 distinct bets**" in md
    assert "## Distinct bets and factor twins" in md and "7 (x2)" in md
    # the SMH twin refuses BY NAME: the toy bars carry no SMH series
    other = next(r for r in doc["rows"] if r["book"] == "lib_other_2026-09-26")
    assert other["forward_vs_factor_etf"] == "SMH_SERIES_MISSING"
    assert "`SMH_SERIES_MISSING`" in md
    # a book the structure receipt never saw is its own bet, and says so
    assert BR.distinct_bets([{"book": "x", "cluster_full": None}, {"book": "y", "cluster_full": 1},
                             {"book": "z", "cluster_full": 1}])["n_distinct"] == 2


def test_factor_beta_names_a_shortfall_the_factor_etf_explains():
    fb = _inv(_path(30, -0.20), factor={"etf": "IWM", "beta": 1.5, "etf_minus_spy": -0.12})
    assert fb["cause"] == "FACTOR_BETA"
    assert fb["factor"]["explained"] == pytest.approx(-0.18)
    assert fb["tests"]["FACTOR_BETA"] and "FACTOR_BETA" in BR.TAXONOMY
    # the factor moved a little: most of the loss is the book's own -> not FACTOR_BETA
    assert _inv(_path(30, -0.20), factor={"etf": "IWM", "beta": 1.0,
                                          "etf_minus_spy": -0.01})["cause"] == "UNKNOWN"
    # the factor ROSE: it cannot explain a loss
    assert _inv(_path(30, -0.20), factor={"etf": "IWM", "beta": 1.0,
                                          "etf_minus_spy": 0.15})["cause"] == "UNKNOWN"
    # checkable price evidence first: an unpriceable book is IMPLEMENTATION regardless
    assert _inv(_path(30, -0.20), book_grade={"n_unpriceable": 1},
                factor={"etf": "IWM", "beta": 1.5, "etf_minus_spy": -0.12})["cause"] == "IMPLEMENTATION"


def test_a_synthetic_forward_month_where_the_book_is_its_factor_is_factor_beta(tmp_path):
    """SPY rises; the book's only name and IWM fall together for 30 sessions.
    The book trails its expectation on every one of the last 21 sessions, and
    with beta 1 to IWM - SPY the whole shortfall is the factor's move."""
    cal = pd.bdate_range(end="2026-09-25", periods=320)
    rows = []
    for k, d in enumerate(cal):
        f = max(0, k - 289)                                  # the last 30 sessions
        down = 50.0 * (1 - 0.007) ** f
        for s, p in (("SPY", 500 + k * 0.2), ("AAA", down), ("IWM", down * 4)):
            rows.append((s, d, p, p * 1.01, p * 0.99, p, 1e7))
    bars = pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    asof = str(cal[289].date())
    bk = dict(_book("lib_toy_rule_sealed_2026-09-26", asof=asof),
              positions=[{"ticker": "AAA", "weight": 1.0}], n_positions=1)
    st = _struct({"lib_toy_rule_sealed_2026-09-26": {
        "cell": "toy_rule@k20", "cluster_full": 1, "cluster_sealed": 1,
        "decomposition": _dec(0.0), "dominant_etf": "IWM", "dominant_beta": 1.0,
        "dominant_t": 4.0}})
    doc = BR.report(today=cal[-1].date(), out_md=tmp_path / "B.md", out_dir=tmp_path,
                    books=[bk], bars=bars, board={"all_rows": [ROW]}, board_path="lb.json",
                    earnings={}, semis={"status": "SKIPPED", "why": "t"}, structure=st)
    r = doc["rows"][0]
    assert isinstance(r["forward_factor_etf"], float) and r["forward_factor_etf"] < -0.15
    assert abs(r["forward_vs_factor_etf"]) < 0.01          # the book IS its factor ETF
    assert r["investigation"]["cause"] == "FACTOR_BETA"
    assert r["expected_alpha_to_date"] == pytest.approx(0.0)
    md = (tmp_path / "B.md").read_text(encoding="utf-8")
    assert "**FACTOR_BETA**" in md


# ───────────── review 2026-09-27: the two-level read, the panel benchmark ─────────────

def _fwd_row(book, rule, cluster, fr, twin, fve):
    return {"book": book, "rule": rule, "cluster_full": cluster, "cluster_sealed": None,
            "forward_relative": fr, "twins_relative": {"random_same_band": twin},
            "forward_vs_factor_etf": fve}


def test_level1_is_one_observation_per_cluster_against_its_twin_and_factor():
    rows = [_fwd_row("a", "mom_12_1", 7, 0.04, 0.01, 0.02),
            _fwd_row("b", "mom_12_1_q", 7, 0.02, 0.03, 0.00),
            _fwd_row("c", "other", 9, 0.10, 0.0, 0.0)]
    obs = BR.cluster_observations(rows)
    assert len(obs) == 1 and obs[0]["cluster"] == "7"
    o = obs[0]
    assert o["forward_relative_one_observation"] == pytest.approx(0.03)
    assert o["forward_minus_random_twin_one_observation"] == pytest.approx(0.03 - 0.02)
    assert o["forward_vs_factor_etf_one_observation"] == pytest.approx(0.01)
    # one member still pending: the cluster observation is PENDING, never a partial mean
    rows[1]["forward_relative"] = "PENDING (entry 2026-09-28)"
    assert BR.cluster_observations(rows)[0]["forward_relative_one_observation"].startswith("PENDING")


def test_level2_pairs_are_member_minus_cluster_mean_tagged_by_axis():
    rows = [_fwd_row("a", "mom_12_1", 7, 0.04, 0.0, 0.0),
            _fwd_row("b", "mom_12_1_q", 7, 0.02, 0.0, 0.0),
            _fwd_row("c", "mom_12_1", 7, 0.00, 0.0, 0.0)]
    st = {"within_cluster": [{"cluster": 7, "median_te_vs_cluster_mean_annual": 0.10}]}
    L2 = {x["book"]: x for x in BR.level2_pairs(rows, st)}
    assert L2["a"]["axis"] == "anchor"
    assert L2["b"]["axis"] == "hold/offset"                  # quarterly vs monthly 12-1
    assert L2["c"]["axis"] == "same rule (frozen twice)"
    assert L2["a"]["forward_minus_cluster_mean"] == pytest.approx(0.02)
    assert L2["c"]["forward_minus_cluster_mean"] == pytest.approx(-0.02)
    assert L2["b"]["mde_after_12_months"] == pytest.approx(0.28)
    assert BR.construction_axis("no_such_rule", "mom_12_1").startswith("unknown")


def test_readme_benchmark_statement_reads_the_sidecar(tmp_path, monkeypatch):
    import json
    sc = {"benchmarks": {"beat_in_both_windows": {"spy": {"n_beat_both": 66, "n_rules": 282},
                                                  "iwm": {"n_beat_both": 112, "n_rules": 282},
                                                  "random_panel": {"n_beat_both": 135, "n_rules": 282}},
                         "random_controls_iwm_beta_full": {"random_1@k50": 0.7, "random_3@k20": 0.85,
                                                           "random_large@k50": 0.4}},
          "n_changed": {"loo_verdict": 3}, "rows": []}
    (tmp_path / "leaderboard_RUN.rekeyed.json").write_text(json.dumps(sc), encoding="utf-8")
    monkeypatch.setattr(BR, "STRUCT_DIR", tmp_path)
    got, path = BR.panel_sidecar({"run_id": "RUN"}, struct_dir=tmp_path)
    assert got["benchmarks"]["beat_in_both_windows"]["iwm"]["n_beat_both"] == 112
    assert BR.panel_sidecar({"run_id": "NONE"}, struct_dir=tmp_path) == (None, None)
    _bp, board = _cited_board()
    s = BR.readme_section(dict(board, run_id="RUN"), "lb.json", git_hash="abc1234")
    assert "tilts small (random controls' IWM beta 0.70-0.85" in s          # random_large excluded
    assert "**66 / 112 / 135 of 282 rules beat SPY / IWM / the random panel in both windows**" in s
    assert "understates every rule by the panel's own tilt" in s
    s0 = BR.readme_section(dict(board, run_id="NONE"), "lb.json", git_hash="abc1234")
    assert "vs IWM / vs the random panel: NOT COMPUTED" in s0


def test_readme_cites_the_committed_sidecar_for_its_run():
    """The rendered README states all three counts, from the sidecar of the
    run it cites (so a reader can check them)."""
    import json
    _bp, board = _cited_board()
    p = REPO / "backend" / "data" / "optimus" / "signal_structure" / f"leaderboard_{board['run_id']}.rekeyed.json"
    assert p.exists(), f"no hold-keyed sidecar for the cited run: {p}"
    bw = json.loads(p.read_text(encoding="utf-8"))["benchmarks"]["beat_in_both_windows"]
    s = _readme_section()
    assert (f"**{bw['spy']['n_beat_both']} / {bw['iwm']['n_beat_both']} / "
            f"{bw['random_panel']['n_beat_both']} of {bw['spy']['n_rules']} rules") in s
    assert "LOO-worst mean active/mo (hold-month key)" in s


# ───────────── 2026-09-27: the family pool in the README, and the leads ─────────────

def _fp_fixture(tmp_path, run: str = "RUN") -> None:
    import json

    def fam(name, mde, ratio, t_dev=0.5, t_sealed=0.5):
        return {"family": name, "members": [f"{name}_a@k20", f"{name}_b@k20", f"{name}_c@k20"],
                "vs_random_panel": {"windows": {"sealed": {"pooled": {"mde_80": mde},
                                                           "se_ratio_pooled_to_single": ratio}}},
                "rule_minus_twin": {"windows": {"dev": {"pooled": {"t_used": t_dev}},
                                                "sealed": {"pooled": {"t_used": t_sealed}}}}}
    fp = {"run_id": run, "n_families_pooled": 3, "n_primary_cells": 12,
          "alpha_both_windows_mean": {"random_panel": [], "spy": ["value"]},
          "pooled_median_mde_vs_panel": {"sealed": 0.02},
          "single_rule_reference": {"sealed": {"median_mde_mean_vs_panel": 0.03}},
          "rule_minus_twin_t_ge_2_both_windows": ["weighted"],
          "dsr_at_n_families": {"twin": {"weighted": 0.8, "value": 0.1, "momentum": 0.2}},
          "rows": [fam("weighted", 0.011, 0.6, 2.1, 2.3), fam("value", 0.03, 0.8),
                   fam("momentum", 0.045, 0.9)]}
    mt = {"run_id": run, "n_primary_cells": 12,
          "summary": {"sealed": {"n_cells": 12, "median_rule_minus_twin": -0.004,
                                 "median_rule_minus_random_1": 0.05, "median_share_removed": 0.6,
                                 "n_rule_minus_twin_gt_0": 5},
                      "dev": {"n_t_twin21_ge_2": 3}},
          "cells_t_twin21_ge_2_both_windows": ["momentum_a@k20"]}
    (tmp_path / f"family_pool_{run}.json").write_text(json.dumps(fp), encoding="utf-8")
    (tmp_path / f"matched_twins_{run}.json").write_text(json.dumps(mt), encoding="utf-8")


def test_family_pool_bullet_renders_every_number_from_the_receipts(tmp_path):
    _fp_fixture(tmp_path)
    s = BR.family_pool_bullet("RUN", struct_dir=tmp_path)
    assert s.startswith("- **Pooled by family")
    assert "3 families with >= 3 rules" in s and "12 primary cells" in s
    assert "**0 of 3** show alpha" in s and "**1 of 3** vs SPY" in s
    assert "+1.10% to +4.50%/month" in s and "median +2.00% vs +3.00%" in s
    assert "pooled SE 0.80x a single rule's, range 0.60-0.90" in s
    assert "**-0.4%**/yr against +5.0%" in s and "removes a median 60%" in s
    assert "5 of 12 cells beat their twin" in s and "1 (`momentum_a@k20`) at t >= 2" in s
    assert "`weighted` (t 2.10 dev, 2.30 2024-26; DSR 0.80 at n = 3 families)" in s
    assert "**a lead for forward paper, not a claim**" in s
    assert "family_pool_RUN.json" in s and "matched_twins_RUN.json" in s
    leads = {"run_id": "RUN", "entry_session": "2026-09-28", "forward_test": "rule - twin",
             "books": [{"cell": "weighted_a@k20", "book": "lib_weighted_a_lead_x", "gate": "PASS"}]}
    s2 = BR.family_pool_bullet("RUN", struct_dir=tmp_path, leads=leads, leads_path="leads.json")
    assert "`weighted_a@k20` -> `lib_weighted_a_lead_x` (PASS)" in s2 and "`leads.json`" in s2
    other = dict(leads, run_id="OTHER")               # a log for another run is not cited
    assert "lib_weighted_a_lead_x" not in BR.family_pool_bullet("RUN", struct_dir=tmp_path,
                                                                leads=other)


def test_family_pool_bullet_refuses_by_name_when_the_receipt_is_missing(tmp_path):
    with pytest.raises(BR.FamilyPoolMissing, match="family_pool_NONE.json"):
        BR.family_pool_facts("NONE", tmp_path)
    s = BR.family_pool_bullet("NONE", struct_dir=tmp_path)
    assert "NOT RENDERED" in s and "family_pool_NONE.json" in s and "matched_twins_NONE.json" in s
    assert not re.search(r"\d+\.\d+%", s)             # no pooled number is carried


def test_readme_carries_the_family_pool_bullet_of_its_cited_run():
    import json
    _bp, board = _cited_board()
    p = (REPO / "backend" / "data" / "optimus" / "signal_structure"
         / f"family_pool_{board['run_id']}.json")
    assert p.exists(), f"no family-pool receipt for the cited run: {p}"
    fp = json.loads(p.read_text(encoding="utf-8"))
    s = _readme_section()
    n = fp["n_families_pooled"]
    assert f"**{len(fp['alpha_both_windows_mean']['random_panel'])} of {n}** show alpha" in s
    assert f"**{len(fp['alpha_both_windows_mean']['spy'])} of {n}** vs SPY" in s
    for fam in fp["rule_minus_twin_t_ge_2_both_windows"]:
        assert f"`{fam}` (t " in s
    assert "a lead for forward paper, not a claim" in s


def test_weighted_leads_are_the_members_that_beat_their_twin_in_both_windows_by_dev_dsr():
    st = {"a": {"cell": "a", "beats_twin_both": True, "dev_dsr": 0.1, "dev_dsr_z": -1.0},
          "b": {"cell": "b", "beats_twin_both": False, "dev_dsr": 0.9, "dev_dsr_z": 1.0},
          "c": {"cell": "c", "beats_twin_both": True, "dev_dsr": 0.3, "dev_dsr_z": -0.5},
          "d": {"cell": "d", "beats_twin_both": True, "dev_dsr": 0.05, "dev_dsr_z": -2.0},
          "e": {"cell": "e", "beats_twin_both": True, "dev_dsr": 0.2, "dev_dsr_z": -0.8}}
    assert BR.select_weighted_leads(st) == ["c", "e", "a"]          # b fails in one window
    assert BR.select_weighted_leads(st, k=1) == ["c"]


def test_lead_member_stats_split_the_windows_by_entry_date():
    idx = pd.DatetimeIndex(pd.date_range("2017-01-31", "2026-07-31", freq="BME"), name="decision_date")
    x = pd.Series(np.where(idx < pd.Timestamp("2023-12-29"), 0.01, -0.01), index=idx)
    x = x + np.random.default_rng(0).normal(0, 0.001, len(x))
    tw = pd.DataFrame({("rule_minus_twin21", "r@k20"): x})
    st = BR.lead_member_stats(["r@k20"], tw, n_trials=10)["r@k20"]
    assert st["dev_mean"] > 0 > st["sealed_mean"] and st["beats_twin_both"] is False
    with pytest.raises(BR.FamilyPoolMissing, match="no rule_minus_twin21"):
        BR.lead_member_stats(["missing@k20"], tw, n_trials=10)


def test_a_lead_gate_is_construction_and_timing_and_keeps_the_full_verdict():
    g = {"verdict": "CONTROL", "reasons": ["MAX_DD", "FAMILY_CAP", "TOP5_MONTH_SHARE"], "label": "x"}
    lg = BR.lead_gate(g)
    assert lg["verdict"] == "PASS" and lg["verdict_full_rule"] == "CONTROL"
    assert lg["reasons_full_rule"] == ["MAX_DD", "FAMILY_CAP", "TOP5_MONTH_SHARE"]
    lg2 = BR.lead_gate({"verdict": "CONTROL", "reasons": ["MAX_DD", "NAME_WEIGHT", "STALE_BARS"]})
    assert lg2["verdict"] == "CONTROL" and lg2["label"] == "CONTROL(NAME_WEIGHT, STALE_BARS)"


def test_a_lead_carries_its_matched_twin_ranks_twin_and_both_legs():
    from backend.services import llm_portfolio as LP
    parent = LP.freeze({"name": "lib_toy_rule_lead_2026-09-27", "kind": "personal",
                        "objective": "x", "model": "rule:strategy_library:toy_rule",
                        "positions": [{"ticker": "AAA", "weight": 0.7, "falsifier": "f"},
                                      {"ticker": "BBB", "weight": 0.3, "falsifier": "f"},
                                      {"ticker": "CASH", "weight": 0.0, "falsifier": "n/a"}]},
                       today="2026-09-27")
    pairs = [("AAA", "EEE", "cell"), ("BBB", "FFF", "band")]
    tws = BR.lead_twin_books(parent, asof="2026-09-27", ranks=[("CCC", 0.5), ("DDD", 0.5)],
                             matched=pairs, seed=7, have=set())
    by = {t["twin"]: t for t in tws}
    assert set(by) == set(BR.LEAD_TWINS)
    assert all(t["parent_book_id"] == parent["book_id"] and t["kind"] == "twin" for t in tws)
    m = {p["ticker"]: p["weight"] for p in by["matched_random"]["positions"]}
    assert m["EEE"] == pytest.approx(0.7) and m["FFF"] == pytest.approx(0.3)  # the held name's weight
    assert [p["ticker"] for p in by["iwm"]["positions"]] == ["IWM"]
    assert {p["ticker"] for p in by["ranks_k1_2k"]["positions"]} == {"CCC", "DDD"}
    rest = {"ew", "spy", "ranks_k1_2k", "iwm"}
    only = BR.lead_twin_books(parent, asof="2026-09-27", ranks=[], matched=pairs, seed=7, have=rest)
    assert [t["twin"] for t in only] == ["matched_random"]
    with pytest.raises(LP.Refusal, match="no matched twin"):
        BR.lead_twin_books(parent, asof="2026-09-27", ranks=[], seed=7, have=rest,
                           matched=[("AAA", None, "none"), ("BBB", "FFF", "band")])


def test_the_bridge_lists_each_lead_with_its_cluster_gate_and_twin_ids():
    doc = {"rows": [{"book": "lib_x_lead", "cluster_full": 7, "gate": "PASS"}],
           "leads_log": "leads.json",
           "leads": {"date": "2026-09-27", "entry_session": "2026-09-28", "bars_asof": "2026-09-25",
                     "run_id": "RUN", "receipts": {}, "selection": {"a_rule": "r"},
                     "chance": {"expected_cells_by_chance": 0.82, "n_cells": 288, "basis": "b",
                                "observed": 2},
                     "gate_scope": "construction + timing", "forward_test": BR.LEAD_FORWARD_TEST,
                     "books": [{"cell": "x@k20", "source": "a", "book": "lib_x_lead", "book_id": "id1",
                                "gate": "PASS",
                                "declared": {"expected_sigma_21_sessions": 0.1,
                                             "stop": {"level_21_sessions": -0.2},
                                             "factor_betas": {"betas": {"SPY": 1.0}}},
                                "twin_ids": {"matched_random": "t1", "iwm": "t2"}}]}}
    s = "\n".join(BR.render_leads(doc))
    assert "| `lib_x_lead` (`id1`) | `x@k20` (a) | 7 | PASS | +10.0% | -20.0% |" in s
    assert "matched_random `t1`" in s and "iwm `t2`" in s
    assert "about 0.8 of 288 cells" in s and BR.LEAD_FORWARD_TEST in s
    assert BR.render_leads({"rows": []}) == []
