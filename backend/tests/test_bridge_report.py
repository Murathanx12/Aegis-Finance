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
