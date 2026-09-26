"""Freeze the Bloomberg dress-rehearsal book and Murat's core-satellite for the 09-28 open.

    python -m scripts.bloomberg_rehearsal_book            # dry run: prints + receipt, no ledger write
    python -m scripts.bloomberg_rehearsal_book --freeze   # appends both books + twins to books.jsonl

Selection logic lives in `backend.services.rehearsal_book` (tested there); this
script loads the data on disk, applies `night_backtest_factory.freeze_gate`'s
construction and timing checks, freezes through `llm_portfolio.freeze` and
`llm_portfolio.twins`, and writes one receipt under
`backend/data/optimus/rehearsal/`. $0: no LLM, no network, no order.

PRODUCT_EXPERIMENT; nothing here is a claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                       # noqa: E402
from backend.services import llm_portfolio as LP         # noqa: E402
from backend.services import rehearsal_book as RB        # noqa: E402

OPT = Path(_cfg.OPTIMUS_LEDGER_DIR)
OUT_DIR = OPT / "rehearsal"
NAME_A = "bloomberg_rehearsal_{d}"
NAME_B = "murat_core_satellite_{d}"
FACTOR_ETFS = ("SPY", "IWM", "SMH", "MTUM")


def _seed(name: str) -> int:
    return int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)


def load_bars() -> pd.DataFrame:
    b = pd.read_parquet(OPT / "prices_2025_26" / "bars.parquet",
                        columns=["symbol", "date", "close", "volume"])
    b["date"] = pd.to_datetime(b["date"])
    try:
        from backend.services import global_prices as GP
        g = GP.read_cache()
        g = g[g["symbol"].isin(["SMH", "MTUM"])][["symbol", "date", "close", "volume"]].copy()
        g["date"] = pd.to_datetime(g["date"])
        g = g[g["date"] >= b["date"].min()]
        b = pd.concat([b, g], ignore_index=True).drop_duplicates(["symbol", "date"], keep="first")
    except Exception as e:                                # noqa: BLE001 -- printed
        print(f"  factor ETFs SMH/MTUM not loaded: {type(e).__name__}: {e}")
    return b


def gics_by_symbol() -> dict:
    base = OPT / "wrds" / "bulk"
    co = pd.read_parquet(base / "comp__company.parquet", columns=["gvkey", "gind"])
    sec = pd.read_parquet(base / "comp__security.parquet",
                          columns=["gvkey", "iid", "tic", "excntry", "secstat"])
    sec = sec[(sec["iid"] == "01") & (sec["excntry"] == "USA") & sec["tic"].notna()]
    sec = sec[~sec["tic"].astype(str).str.contains(r"[.\s]", regex=True)]
    m = sec.merge(co, on="gvkey").dropna(subset=["gind"])
    m = m.sort_values("secstat").drop_duplicates("tic", keep="first")
    return dict(zip(m["tic"].astype(str).str.upper(), m["gind"].astype(str)))


def _already_frozen(name: str) -> bool:
    return any(b.get("name") == name for b in LP.read_books())


def _twin(parent: dict, twin: str, positions: list, asof: str, note: str) -> dict:
    return LP.freeze({
        "name": f"{parent['name']}__{twin}", "kind": "twin", "twin": twin,
        "objective": f"twin of {parent['name']}: {parent['objective']}",
        "strategy": f"{twin} twin of {parent['book_id']}: {note}",
        "model": "twin", "parent_book_id": parent["book_id"],
        "parent_kind": parent["kind"], "benchmark": parent.get("benchmark"),
        "horizon_days": parent.get("horizon_days"), "positions": positions}, today=asof)


def random_same_band(names: list[str], bars: pd.DataFrame, asof: str, seed: int,
                     exclude: set) -> list[str]:
    """One random live same-band replacement per name (llm_portfolio's twin rule)."""
    rng = np.random.default_rng(seed)
    bands = LP.liquidity_bands(bars, asof=asof)
    pool = LP._live_pool(bars, asof, set(names) | exclude)
    by: dict = {}
    for s in pool:
        by.setdefault(bands.get(s, "small"), []).append(s)
    out, chosen = [], set()
    for n in sorted(names):
        c = [s for s in by.get(bands.get(n, ""), []) if s not in chosen] or \
            [s for s in pool if s not in chosen]
        p = str(c[int(rng.integers(len(c)))])
        chosen.add(p)
        out.append(p)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--asof", default=str(date.today()))
    ap.add_argument("--freeze", action="store_true", help="append to books.jsonl")
    a = ap.parse_args(argv)
    asof = a.asof
    name_a, name_b = NAME_A.format(d=asof), NAME_B.format(d=asof)
    say = print
    rc: dict = {"receipt": "bloomberg_rehearsal", "licence": "PRODUCT_EXPERIMENT",
                "sentence": RB.LICENCE_SENTENCE, "asof": asof,
                "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "llm_spend_usd": 0.0, "review": "docs/reviews/REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md §9"}

    bars = load_bars()
    cal = pd.DatetimeIndex(sorted(bars["date"].unique()))
    rc["bars"] = {"path": "prices_2025_26/bars.parquet (+ SMH/MTUM from global_prices)",
                  "last_date": str(cal.max().date()), "n_symbols": int(bars["symbol"].nunique())}
    say(f"bars: {rc['bars']['n_symbols']} symbols through {rc['bars']['last_date']}")
    U = RB.universe(bars, asof)
    sig = RB.sigma63(bars[bars["symbol"].isin(set(U.index) | set(RB_ETFS()))], asof)
    facts = pd.read_parquet(OPT / "fundamentals_sec" / "sec_facts_history.parquet",
                            columns=["ticker", "fact", "filed", "end", "period_days", "val"])
    shares = RB.latest_shares(facts, asof)
    fund = RB.fundamentals_composite(facts, asof, U.index)
    del facts
    ek = pd.read_parquet(OPT / "edgar_8k" / "eightk_items.parquet",
                         columns=["ticker", "filing_date", "items_joined"])
    earn = RB.earnings_estimates(ek, U.index, asof)
    del ek
    gics = gics_by_symbol()

    closes_all = RB.wide_closes(bars, asof, n=RB.BETA_WINDOW + 5)
    rets = closes_all.pct_change(fill_method=None).iloc[-RB.CORR_WINDOW:]
    smh_corr = rets.corrwith(rets["SMH"]) if "SMH" in rets.columns else None

    C = pd.DataFrame(index=U.index)
    C["close"], C["mdv63"], C["band"] = U["close"], U["mdv63"], U["band"]
    C["sigma63"] = sig.reindex(C.index)
    C["shares"] = shares.reindex(C.index)
    C["mcap"] = C["shares"] * C["close"]
    C["fund_score"] = fund["fund_score"].reindex(C.index)
    C["n_legs"] = fund["n_legs"].reindex(C.index)
    C["earnings_status"] = [earn[s]["status"] for s in C.index]
    sf = RB.semis_flags(C.index, gind_by_symbol=gics, smh_corr=smh_corr)
    C = C.join(sf)
    ranked, counts = RB.rank_candidates(C)
    rc["filter_counts"] = counts
    rc["earnings_status_counts"] = pd.Series([earn[s]["status"] for s in U.index]).value_counts().to_dict()
    say(f"filters: {counts}")
    top = list(ranked.index[:80])
    corr = rets[[s for s in top if s in rets.columns]].corr(min_periods=40)
    picks, skipped = RB.pick(ranked, corr)
    nxt, skipped2 = RB.pick(ranked, corr, exclude=picks)
    rc["skipped_book"], rc["skipped_twin"] = skipped, skipped2
    if len(picks) < RB.K or len(nxt) < RB.K:
        rc["status"] = f"REFUSED: only {len(picks)} + {len(nxt)} qualifying names"
        say(rc["status"])
        _write(rc, asof)
        return 2

    # the freeze gate: construction + timing (selection needs a backtest row this book has not)
    from scripts.night_backtest_factory import freeze_gate
    wA = {s: RB.WEIGHT for s in picks}
    gate = freeze_gate(None, wA, bars, cal, decision_date=asof,
                       earnings={s: {"status": "NOT_DUE", "why": "no name above 10%"} for s in picks})
    con_ok = all(v is True for v in gate["construction"].values())
    tim_ok = all(v is True for v in gate["timing"].values())
    gate_rec = {"verdict_construction_timing": "PASS" if (con_ok and tim_ok) else "FAIL",
                "construction": gate["construction"], "timing": gate["timing"],
                "detail": {k: gate["detail"][k] for k in ("k", "max_weight", "weight_cap", "effective_n",
                                                          "max_cluster", "max_cluster_share",
                                                          "largest_name_to_zero_usd", "bar_date",
                                                          "staleness_sessions")},
                "selection_not_applied": ("SELECTION needs a leaderboard row; this book is not a "
                                          "library rule (NO_BACKTEST_ROW by construction)"),
                "rule": gate["rule"]}
    rc["freeze_gate"] = gate_rec
    say(f"freeze gate (construction + timing): {gate_rec['verdict_construction_timing']} "
        f"{gate['construction']} {gate['timing']}")
    if gate_rec["verdict_construction_timing"] != "PASS":
        rc["status"] = "REFUSED: freeze gate construction/timing"
        _write(rc, asof)
        return 2

    closes = RB.wide_closes(bars, asof, symbols=set(picks) | set(nxt) | set(FACTOR_ETFS),
                            n=RB.BETA_WINDOW + 5)
    stA = RB.book_stats(wA, closes, sigma=sig)
    stN = RB.book_stats({s: RB.WEIGHT for s in nxt}, closes, sigma=sig)
    stop = RB.stop_rule_book(stA["rel_sigma_daily_vs_spy"])
    rows = []
    for i, s in enumerate(picks + nxt):
        r = ranked.loc[s]
        e = earn[s]
        rows.append({"rank": i + 1, "symbol": s, "in_book": s in picks,
                     "weight": RB.WEIGHT if s in picks else 0.0,
                     "sigma63_daily": round(float(r["sigma63"]), 5),
                     "sigma_21": round(float(r["sigma63"]) * np.sqrt(21), 4),
                     "pred_abs_move_21": round(float(r["pred_move"]), 4),
                     "two_sigma_21": round(2 * float(r["sigma63"]) * np.sqrt(21), 4),
                     "fund_score": round(float(r["fund_score"]), 4), "n_legs": int(r["n_legs"]),
                     "mcap_usd": float(r["mcap"]), "band": r["band"], "mdv63": float(r["mdv63"]),
                     "is_semi": bool(r["is_semi"]), "sector_source": r["sector_source"],
                     "last_202": e.get("last_202"), "earnings_estimate": e.get("estimate"),
                     "earnings_session": e.get("session"), "yoy_cross_check": e.get("yoy_cross_check"),
                     "earnings_source": f"{e['source']}; {e['rule']}"})
    rc["book_a_names"] = rows
    fac = stA["factor_exposure"]
    declared_a = {
        "expected_sigma_21_abs": stA["sigma_21"], "expected_sigma_daily": stA["sigma_daily"],
        "expected_rel_sigma_21_vs_spy": stA["rel_sigma_21_vs_spy"],
        "expected_relative_return": f"0 +/- {stA['rel_sigma_21_vs_spy']:.4f} over 21 sessions "
                                    f"(no directional edge is claimed)",
        "avg_pairwise_rho_63": stA["avg_pairwise_rho_63"],
        "factor_exposure": fac,
        "benchmark_note": ("contest benchmark is WLS (proxy URTH, graded by llm_portfolio); the "
                           "relative sigma and betas are vs SPY/IWM/SMH/MTUM, which the bars carry"),
        "stop": stop, "checks_2026_10_26": list(RB.CHECKS_2026_10_26),
        "checks_detail": list(RB.CHECKS_DETAIL), "check_date": RB.CHECK_DATE,
        "check_thresholds": {"move_rank_spearman_min": RB.MOVE_RANK_MIN,
                             "exposure_tolerance": RB.EXPOSURE_TOL},
        "fundamentals_score": ("PROXY: percentile-rank average of gp_at+, ope_be+, ni_be+, at_gr1-, "
                               "debt_at- (fundamental_features, filed+2d), >= 3 legs; NOT the "
                               "LightGBM that measured +39 bps/month (panel ends 2024-12)"),
        "worst_case": ("10 x 10% = 100% gross of $1,000,000, gross/equity 1.00, long only: one "
                       "name to zero = -$100,000; a 3-sigma book day = "
                       f"-{3*stA['sigma_daily']:.2%} = -${3*stA['sigma_daily']*1e6:,.0f}"),
        "rotation": ("DECLARED, NOT AUTOMATED: once a name has printed, the contest book rotates it "
                     "into the next un-printed name; the frozen rehearsal record does not rotate"),
        "licence": RB.LICENCE_SENTENCE}
    rc["book_a_declared"] = declared_a
    rc["twin_next_k_stats"] = stN

    positions_a = [{
        "ticker": x["symbol"], "weight": RB.WEIGHT, "theme": "semis" if x["is_semi"] else None,
        "thesis": (f"rank {x['rank']} by sigma63-predicted |21-session move| "
                   f"{x['pred_abs_move_21']:.1%} (sigma63 {x['sigma63_daily']:.2%}/day); fundamentals "
                   f"proxy {x['fund_score']:.2f} >= median; Q3 print est {x['earnings_estimate']} "
                   f"(last 8-K 2.02 {x['last_202']} + {RB.EARNINGS_CADENCE_DAYS}d)"),
        "falsifier": (f"its realised |move| to {RB.CHECK_DATE} ranks in the bottom half of the "
                      f"book's predicted order, or no 8-K 2.02 is filed by {RB.CHECK_DATE}")}
        for x in rows if x["in_book"]]
    book_a = {
        "name": name_a, "kind": "competition", "objective": _cfg.BOOK_COMPETITION_OBJECTIVE,
        "model": "rule:rehearsal_book:sigma63_x_fundamentals_x_q3_print",
        "strategy": (f"{RB.LICENCE_SENTENCE} Bloomberg dress rehearsal (review 2026-09-27 §9): "
                     f"10 small/mid names x 10% with a Q3 print estimated inside the 21-session "
                     f"window to {RB.CHECK_DATE} (EDGAR 8-K 2.02 + 91d), ranked by sigma63-predicted "
                     f"move size, fundamentals proxy >= median, <= {RB.MAX_SEMIS} semis, no pair "
                     f"rho > {RB.PAIR_RHO_MAX}. Declared sigma_21 {stA['sigma_21']:.1%} abs, "
                     f"{stA['rel_sigma_21_vs_spy']:.1%} vs SPY; E[rel] = 0. Stop: z < -2 on "
                     f"relative P&L. Checks on {RB.CHECK_DATE}: "
                     + "; ".join(RB.CHECKS_2026_10_26)),
        "horizon_days": [1, 5, 21],
        "positions": positions_a,
        "freeze_gate": gate_rec,
    }

    # ── Book B: Murat's core-satellite ──────────────────────────────────────
    sleeve = RB.sleeve_top(fund, U.index)
    closes_b = RB.wide_closes(bars, asof, symbols=set(sleeve) | {"SPY"}, n=260)
    te = RB.core_satellite_te(sleeve, closes_b)
    sw = (1 - RB.CORE_WEIGHT) / RB.SLEEVE_K
    fsub = fund.reindex(sleeve)
    declared_b = {
        "core": "SPY 80% as one position; it never stops",
        "satellite": f"xs fundamentals proxy top-{RB.SLEEVE_K} equal weight ({sw:.0%} each), small caps allowed, no cap",
        "tracking_error": te,
        "tracking_error_target_ann": 0.04,
        "stop": {"rule": ("satellite minus its random-sleeve twin, z = cumulative difference / "
                          "(sigma_ann(sleeve - SPY) x satellite x sqrt(t/252)); at the 126-session "
                          "check ACT (drop the satellite to SPY) only if z < -2 (2 sigma, not a "
                          "percent); the core never stops; never on 21 days"),
                 "z": RB.STOP_Z,
                 "threshold_at_126_as_book_return": round(RB.STOP_Z * te["tracking_error_ann"]
                                                           * np.sqrt(126 / 252), 4)},
        "horizon": f"{RB.PERSONAL_HORIZON} sessions, graded beside the 21-session read",
        "checks_2026_10_26": ["realised factor exposure within +/-0.3 of declared", "fills vs plan"],
        "worst_case": (f"largest single name to zero = -{sw:.0%} of equity = -${sw*1e6:,.0f}; the "
                       f"sleeve to zero = -$200,000; the core is the market"),
        "note_vs_review": ("the review sized the satellite at k=25 and <= 1% of equity per name; "
                           "Murat's instruction for this book is top-10 at 2% each, no cap"),
        "fundamentals_score": declared_a["fundamentals_score"],
        "licence": RB.LICENCE_SENTENCE}
    rc["book_b_sleeve"] = [{"symbol": s, "weight": sw, "fund_score": round(float(fsub.loc[s, "fund_score"]), 4),
                            "n_legs": int(fsub.loc[s, "n_legs"]), "fund_filed": fsub.loc[s, "fund_filed"],
                            "band": U.loc[s, "band"] if s in U.index else None} for s in sleeve]
    rc["book_b_declared"] = declared_b
    positions_b = ([{"ticker": "SPY", "weight": RB.CORE_WEIGHT, "is_etf": True,
                     "thesis": "core: the market", "falsifier": "none: the core never stops"}]
                   + [{"ticker": s, "weight": sw,
                       "thesis": (f"fundamentals proxy rank {i+1} of the eligible universe, score "
                                  f"{fsub.loc[s, 'fund_score']:.3f} ({int(fsub.loc[s, 'n_legs'])} legs)"),
                       "falsifier": ("the sleeve trails its random-sleeve twin by more than 2 sigma "
                                     "of their difference at the 126-session check")}
                      for i, s in enumerate(sleeve)]
                   + [{"ticker": "CASH", "weight": 0.0, "thesis": "declared: fully invested",
                       "falsifier": "n/a"}])
    book_b = {
        "name": name_b, "kind": "personal",
        "objective": (f"terminal wealth, balanced: 80% SPY + 20% fundamentals sleeve; tracking "
                      f"error ~{te['tracking_error_ann']:.1%}/yr vs SPY; graded at 21 and "
                      f"{RB.PERSONAL_HORIZON} sessions"),
        "model": "rule:rehearsal_book:core_satellite",
        "strategy": (f"{RB.LICENCE_SENTENCE} Murat's own money as a book (review 2026-09-27 §9 "
                     f"Book B): SPY 80% + fundamentals-proxy top-10 EW 20%. TE {te['tracking_error_ann']:.2%}/yr "
                     f"(0.2 x sigma(sleeve-SPY) {te['sleeve_minus_spy_sigma_ann']:.1%}; sleeve sigma "
                     f"{te['sleeve_sigma_ann']:.1%}, rho to SPY {te['sleeve_corr_spy']:.2f}). Stop: "
                     f"satellite-vs-twin z < -2 at 126 sessions; the core never stops."),
        "benchmark": "SPY",
        "horizon_days": [1, 5, 21, RB.PERSONAL_HORIZON],
        "positions": positions_b,
    }

    universe_syms = set(bars["symbol"].unique())
    recA = LP.freeze(book_a, today=asof, universe=universe_syms)
    recA["declared"] = declared_a
    recA["rehearsal_names"] = rows
    recB = LP.freeze(book_b, today=asof, universe=universe_syms)
    recB["declared"] = declared_b

    twA = LP.twins(recA, asof=asof, seed=_seed(name_a), bars=bars)
    twinsA = {"random_same_band": twA["random_same_band"],
              "next_k": _twin(recA, "next_k", [{"ticker": s, "weight": RB.WEIGHT,
                                                "thesis": f"rank {RB.K + i + 1} (k+1..2k twin)"}
                                               for i, s in enumerate(nxt)], asof,
                              "equal weight of ranks 11-20 under the same filters"),
              "iwm": _twin(recA, "iwm", [{"ticker": "IWM", "weight": 1.0, "thesis": "small caps"}],
                           asof, "IWM leg"),
              "spy": _twin(recA, "spy", [{"ticker": "SPY", "weight": 1.0, "thesis": "the market"}],
                           asof, "SPY leg")}
    rnd = random_same_band(sleeve, bars, asof, _seed(name_b), exclude={"SPY"})
    twinsB = {"spy": _twin(recB, "spy", [{"ticker": "SPY", "weight": 1.0, "thesis": "100% SPY"}],
                           asof, "100% SPY"),
              "random_sleeve": _twin(recB, "random_sleeve",
                                     [{"ticker": "SPY", "weight": RB.CORE_WEIGHT, "thesis": "core"}]
                                     + [{"ticker": s, "weight": sw,
                                         "thesis": f"random same-band replacement for {o}"}
                                        for o, s in zip(sorted(sleeve), rnd)]
                                     + [{"ticker": "CASH", "weight": 0.0, "thesis": "parent's cash"}],
                                     asof, "80% SPY + a random same-band sleeve")}
    rc["book_a"] = {"name": recA["name"], "book_id": recA["book_id"], "kind": recA["kind"],
                    "benchmark": recA["benchmark"],
                    "twins": {k: {"book_id": v["book_id"], "tickers": [p["ticker"] for p in v["positions"]]}
                              for k, v in twinsA.items()}}
    rc["book_b"] = {"name": recB["name"], "book_id": recB["book_id"], "kind": recB["kind"],
                    "twins": {k: {"book_id": v["book_id"], "tickers": [p["ticker"] for p in v["positions"]]}
                              for k, v in twinsB.items()}}
    say(f"BOOK A {recA['name']} {recA['book_id']}  sigma_21 {stA['sigma_21']:.2%} abs, "
        f"{stA['rel_sigma_21_vs_spy']:.2%} vs SPY")
    for x in rows[:RB.K]:
        say(f"  {x['symbol']:<6} 10%  sigma63 {x['sigma63_daily']:.2%}  pred|21| {x['pred_abs_move_21']:.1%}  "
            f"fund {x['fund_score']:.2f}  Q3 est {x['earnings_estimate']} (last 2.02 {x['last_202']})"
            f"{'  SEMI' if x['is_semi'] else ''}")
    say(f"  exposure: {json.dumps(fac.get('multi', {}), default=lambda v: round(v, 3))}")
    say(f"BOOK B {recB['name']} {recB['book_id']}  TE {te['tracking_error_ann']:.2%}/yr  sleeve {sleeve}")

    if a.freeze:
        for n in (name_a, name_b):
            if _already_frozen(n):
                rc["status"] = f"REFUSED: {n} is already in the ledger; not frozen twice"
                say(rc["status"])
                _write(rc, asof)
                return 2
        for r in [recA, *twinsA.values(), recB, *twinsB.values()]:
            LP.append_book(r)
        rc["status"] = "FROZEN"
        rc["ledger"] = str(LP.books_path())
        say(f"FROZEN -> {LP.books_path()}")
    else:
        rc["status"] = "DRY_RUN (pass --freeze to append)"
    _write(rc, asof)
    return 0


def RB_ETFS() -> tuple:
    return FACTOR_ETFS


def _write(rc: dict, asof: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / f"rehearsal_{asof}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rc, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)
    print(f"receipt -> {p}")
    return p


if __name__ == "__main__":
    raise SystemExit(main())
