"""Stitched tickers: two companies' price histories joined under one reused ticker.

WHY (review 2026-09-29 F4)
==========================
`prices_deep/bars.parquet` serves a reused ticker's histories under ONE symbol:
JAN was a $2.21 stock until 2024-07-12 and a $23.34 IPO (Janus Living) from
2026-03-20. `bars_delisted.parquet` has 46 more: it was pulled by TICKER for
Alpaca's inactive assets, and the bars endpoint answers every listing ever made
under a ticker (MLPI: a dead fund at $9.98 in 2020, a new listing at $44.08
from 2025-12-18, still trading). 63 gaps in the survivorship-free panel.
Every trailing feature that reaches across the hole -- 12-1 momentum above all --
compared a new company with a dead one, and the 2026-09-28 live ranking put JAN
at #2 and MLPI at #4.

WHAT THIS MODULE DECIDES, FROM THE DATA
=======================================
A CANDIDATE is a symbol whose consecutive bars are more than
`STITCH_GAP_SESSIONS` market sessions apart. The gap alone never decides,
because a genuine suspension (NBIS: Yandex halted 2024-08, the same registrant
resumed as Nebius 2024-10) is one company. Evidence, per gap:

  same_registrant   the ticker's CURRENT SEC registrant (CIK) has filings on
                    disk dated on/before the old segment's last bar -> the same
                    legal company traded on both sides -> SUSPENSION (kept).
  new_registrant    the current CIK's first filing on disk is AFTER the old
                    segment ended -> a registrant that did not exist then.
  cik_band_after    no filings on disk for the current CIK, but CIKs are issued
                    in sequence and the ones numbered near it first filed well
                    after the old segment ended (an estimate; labelled so).
  inactive_source   the old segment comes from the inactive-asset pull
                    (`bars_delisted`), which asked the bars endpoint for a TICKER
                    and got every listing made under it (46 of the 63 gaps are
                    inside that file: MLPI's dead 2020 fund + a 2025 listing).
  price_jump        the price level changes by >= STITCH_PRICE_JUMP_RATIO.

Verdict: SUSPENSION if same_registrant; else STITCHED if any other evidence;
else GAP_UNRESOLVED. STITCHED and GAP_UNRESOLVED are both CUT (a trailing
window across a >20-session hole is not the quantity its name claims either
way); the receipt counts them apart so an unresolved gap is never silent.

THE CUT
=======
`split_stitched(bars)` renames every segment before the last cut to `SYM#k`
(k = 1 for the oldest). The living symbol's history then STARTS at the new
company's first bar, so every feature that needs a longer window is NaN for it
(never zero, never the old company's prices), and the dead company stays in the
panel as its own dead name -- survivorship is not lost by the fix. The bar files
themselves are never rewritten.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _cfg

logger = logging.getLogger(__name__)

_OPTIMUS = _cfg.OPTIMUS_LEDGER_DIR
SEC_FACTS_PATH = _OPTIMUS / "fundamentals_sec" / "sec_facts_history.parquet"
COMPANY_TICKERS_PATH = _OPTIMUS / "edgar_8k" / "company_tickers.json"
INACTIVE_SOURCE_STEMS = frozenset({"bars_delisted"})

GAP_SESSIONS = int(getattr(_cfg, "STITCH_GAP_SESSIONS", 20))
PRICE_JUMP_RATIO = float(getattr(_cfg, "STITCH_PRICE_JUMP_RATIO", 3.0))
CIK_BAND_MARGIN_DAYS = int(getattr(_cfg, "STITCH_CIK_BAND_MARGIN_DAYS", 180))
CIK_BAND_HALF_WIDTH = 25_000
CIK_BAND_MIN_N = 5
CUT_VERDICTS = frozenset({"STITCHED", "GAP_UNRESOLVED"})

#: The last audit `split_stitched` produced, for receipts that want to print it.
LAST_AUDIT: dict = {}


# ─────────────────────────────── registrants ─────────────────────────────────

def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return -1.0


@lru_cache(maxsize=4)
def _registrants_cached(facts: str, facts_m: float, tickers: str, tickers_m: float) -> dict:
    out: dict = {"by_ticker": {}, "cik_first": pd.Series(dtype="datetime64[ns]"),
                 "sources": []}
    fp, tp = Path(facts), Path(tickers)
    if fp.exists():
        f = pd.read_parquet(fp, columns=["ticker", "cik", "filed"])
        f["filed"] = pd.to_datetime(f["filed"], errors="coerce")
        f = f.dropna(subset=["filed", "cik"])
        first = f.groupby(["ticker", "cik"])["filed"].min().reset_index()
        for t, c, d in first.itertuples(index=False):
            prev = out["by_ticker"].get(t)
            if prev is None or d < prev["first_filed"]:
                out["by_ticker"][str(t)] = {"cik": int(c), "first_filed": pd.Timestamp(d),
                                            "source": "sec_facts_history"}
        out["cik_first"] = f.groupby("cik")["filed"].min().sort_index()
        out["sources"].append(str(fp.name))
    if tp.exists():
        try:
            raw = json.loads(tp.read_text(encoding="utf-8"))
            rows = raw.values() if isinstance(raw, dict) else raw
            for r in rows:
                t, c = str(r.get("ticker", "")), r.get("cik_str")
                if t and c is not None and t not in out["by_ticker"]:
                    out["by_ticker"][t] = {"cik": int(c), "first_filed": None,
                                           "source": "company_tickers"}
            out["sources"].append(str(tp.name))
        except (OSError, ValueError) as e:
            logger.warning("stitched_tickers: company_tickers unreadable: %r", e)
    return out


def registrants(facts_path: Path | None = None, tickers_path: Path | None = None) -> dict:
    """ticker -> {cik, first_filed (on disk, or None), source}; plus cik -> first filed."""
    fp = Path(facts_path or SEC_FACTS_PATH)
    tp = Path(tickers_path or COMPANY_TICKERS_PATH)
    return _registrants_cached(str(fp), _mtime(fp), str(tp), _mtime(tp))


def cik_band_first_filed(cik: int, cik_first: pd.Series) -> Optional[pd.Timestamp]:
    """10th percentile first-filing date of the CIKs numbered near `cik` (an ESTIMATE
    of when a registrant with that number came to exist). None if too few neighbours."""
    if cik_first is None or not len(cik_first):
        return None
    idx = cik_first.index.values
    lo, hi = np.searchsorted(idx, cik - CIK_BAND_HALF_WIDTH), np.searchsorted(idx, cik + CIK_BAND_HALF_WIDTH)
    band = cik_first.iloc[lo:hi]
    if len(band) < CIK_BAND_MIN_N:
        return None
    return pd.Timestamp(np.quantile(band.values.astype("datetime64[ns]").astype("int64"), 0.10))


# ─────────────────────────────── detection ───────────────────────────────────

def _calendar(bars: pd.DataFrame, market: str) -> np.ndarray:
    """The market's sessions; without the market in the frame, BUSINESS DAYS.

    Falling back to the frame's own dates made detection a silent no-op for a
    reader that loads a few symbols (2026-09-29): for one symbol alone every
    consecutive pair of its own dates is one "session" apart, whatever the hole.
    Business days over-count a gap by its holidays, which only moves a gap near
    the threshold."""
    m = bars.loc[bars["symbol"] == market, "date"]
    if len(m):
        return np.sort(pd.to_datetime(m).unique())
    d = pd.to_datetime(bars["date"])
    return np.asarray(pd.bdate_range(d.min().normalize(), d.max().normalize()).values)


def detect(bars: pd.DataFrame, *, src_col: str = "src", regs: dict | None = None,
           market: str = "SPY", gap_sessions: int | None = None) -> pd.DataFrame:
    """One row per candidate gap, with its evidence and verdict. `bars` sorted by (symbol, date)."""
    gap_sessions = GAP_SESSIONS if gap_sessions is None else int(gap_sessions)
    cols = ["symbol", "gap_index", "last_before", "close_before", "first_after", "close_after",
            "gap_sessions", "price_ratio", "old_src", "new_src", "cik", "cik_source",
            "cik_first_filed", "cik_band_first_filed", "evidence", "verdict"]
    if bars.empty:
        return pd.DataFrame(columns=cols)
    b = bars.sort_values(["symbol", "date"], kind="mergesort")
    cal = _calendar(b, market)
    d = pd.to_datetime(b["date"]).values
    pos = np.searchsorted(cal, d)
    sym = b["symbol"].astype(str).values
    same = sym[1:] == sym[:-1]
    gaps = np.diff(pos)
    idx = np.flatnonzero(same & (gaps > gap_sessions))
    if not len(idx):
        return pd.DataFrame(columns=cols)
    regs = regs if regs is not None else registrants()
    close = b["close"].astype("float64").values
    src = b[src_col].astype(str).values if src_col in b.columns else np.full(len(b), "")
    # the source of a whole SEGMENT: every row between two gaps of that symbol
    seg_id = np.r_[0, np.cumsum(~same | (gaps > gap_sessions))]
    pairs = pd.DataFrame({"seg": seg_id, "src": src}).drop_duplicates()
    seg_src = pairs.groupby("seg")["src"].agg(lambda s: ",".join(sorted(set(s))))
    rows = []
    k_by_sym: dict[str, int] = {}
    for i in idx:
        s = sym[i]
        k_by_sym[s] = k_by_sym.get(s, 0) + 1
        old_end = pd.Timestamp(d[i])
        ratio = close[i + 1] / close[i] if close[i] > 0 else np.inf
        reg = regs.get("by_ticker", {}).get(s)
        ev: list[str] = []
        cik = reg["cik"] if reg else None
        ff = reg["first_filed"] if reg else None
        band = None
        same_reg = ff is not None and ff <= old_end
        if ff is not None and ff > old_end:
            ev.append(f"new_registrant: CIK {cik} first filed {ff.date()} after the old segment ended {old_end.date()}")
        if reg is not None and ff is None:
            band = cik_band_first_filed(int(cik), regs.get("cik_first"))
            if band is not None and band > old_end + pd.Timedelta(days=CIK_BAND_MARGIN_DAYS):
                ev.append(f"cik_band_after: CIK {cik} (no filings on disk); CIKs numbered near it first "
                          f"filed ~{band.date()} (ESTIMATE), after the old segment ended {old_end.date()}")
        o_src, n_src = seg_src.get(seg_id[i], ""), seg_src.get(seg_id[i + 1], "")
        o_stems = set(o_src.split(",")) - {""}
        if o_stems and o_stems <= INACTIVE_SOURCE_STEMS:
            # the inactive-asset pull asks the bars endpoint for a TICKER, which
            # answers every listing ever made under it; two listing periods under a
            # symbol the vendor names as one inactive asset are two assets.
            ev.append(f"inactive_source: old segment from the inactive-asset pull ({o_src}); "
                      f"a second listing period under the ticker follows (in {n_src})")
        if (not np.isfinite(ratio)) or ratio >= PRICE_JUMP_RATIO or ratio <= 1.0 / PRICE_JUMP_RATIO:
            ev.append(f"price_jump: {close[i]:.4g} -> {close[i + 1]:.4g} (x{ratio:.2f})")
        if same_reg:
            verdict = "SUSPENSION"
            ev.insert(0, f"same_registrant: CIK {cik} filed from {ff.date()}, before the old segment ended")
        elif ev:
            verdict = "STITCHED"
        else:
            verdict = "GAP_UNRESOLVED"
        rows.append({"symbol": s, "gap_index": k_by_sym[s], "last_before": old_end,
                     "close_before": float(close[i]), "first_after": pd.Timestamp(d[i + 1]),
                     "close_after": float(close[i + 1]), "gap_sessions": int(gaps[i]),
                     "price_ratio": float(ratio), "old_src": o_src, "new_src": n_src,
                     "cik": cik, "cik_source": reg["source"] if reg else None,
                     "cik_first_filed": ff, "cik_band_first_filed": band,
                     "evidence": ev, "verdict": verdict})
    return pd.DataFrame(rows, columns=cols)


def split_stitched(bars: pd.DataFrame, *, src_col: str = "src", regs: dict | None = None,
                   market: str = "SPY", gaps: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """Cut every STITCHED / GAP_UNRESOLVED symbol at its gap(s): earlier segments become
    `SYM#k` (dead names), the symbol itself starts at the new company's first bar.

    Returns (bars, audit). Rows are never dropped and prices never changed."""
    global LAST_AUDIT
    b = bars.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    g = gaps if gaps is not None else detect(b, src_col=src_col, regs=regs, market=market)
    cut = g[g["verdict"].isin(CUT_VERDICTS)] if len(g) else g
    audit = {"gap_sessions_threshold": GAP_SESSIONS, "candidates": int(len(g)),
             "by_verdict": {k: int(v) for k, v in g["verdict"].value_counts().items()} if len(g) else {},
             "cut_symbols": sorted(cut["symbol"].unique().tolist()) if len(cut) else [],
             "kept_as_suspension": sorted(g.loc[g["verdict"] == "SUSPENSION", "symbol"].unique().tolist())
             if len(g) else [],
             "registrant_sources": list((regs or registrants()).get("sources", [])) if len(g) else []}
    if not len(cut):
        LAST_AUDIT = audit
        return b, audit
    sym = b["symbol"].astype(str).values.copy()
    dates = pd.to_datetime(b["date"]).values
    for s, gg in cut.groupby("symbol"):
        rows = np.flatnonzero(sym == s)
        cuts = sorted(pd.to_datetime(gg["first_after"]).values)
        seg = np.searchsorted(np.asarray(cuts, dtype="datetime64[ns]"), dates[rows], side="right")
        last = len(cuts)
        early = seg < last
        sym[rows[early]] = [f"{s}#{k + 1}" for k in seg[early]]
    b = b.copy()
    b["symbol"] = sym
    b = b.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    LAST_AUDIT = audit
    return b, audit


# ───────────────────────── the one call every bar reader makes ─────────────────

#: The column a reader tags each file's rows with (the file's stem), so the
#: inactive-source evidence (`INACTIVE_SOURCE_STEMS`) survives the concat.
SRC_COL = "_src"


def tag_source(df: pd.DataFrame, stem: str) -> pd.DataFrame:
    """Tag one file's rows with its stem (in place; returns `df`)."""
    df[SRC_COL] = pd.Categorical.from_codes(np.zeros(len(df), dtype="int8"), [str(stem)])
    return df


def cut_reader_bars(bars: pd.DataFrame, *, src_col: str = SRC_COL,
                    market: str = "SPY") -> pd.DataFrame:
    """THE reader fix (2026-09-29): every reader of the daily bar files that does
    not go through `xs_ranker.load_bars` calls this after its own concat and
    dedupe. A reused ticker's history starts at the new company's first bar;
    the old company's rows are renamed `SYM#k`, never dropped, no price changes,
    no file rewritten. Drops `src_col` when present. Returns long bars sorted by
    (symbol, date)."""
    if bars is None or not len(bars):
        return bars.drop(columns=[src_col], errors="ignore") if bars is not None else bars
    b = bars
    if not pd.api.types.is_datetime64_any_dtype(b["date"]):
        b = b.copy()
        b["date"] = pd.to_datetime(b["date"])
    out, _ = split_stitched(b, src_col=src_col, market=market)
    return out.drop(columns=[src_col], errors="ignore")


def base_symbol(sym: str) -> str:
    """`JAN#1` -> `JAN`."""
    return str(sym).split("#", 1)[0]


def is_split_segment(sym: str) -> bool:
    return "#" in str(sym)


def report_rows(gaps: pd.DataFrame, panel_end: pd.Timestamp, cal: Iterable) -> list[dict]:
    """JSON-ready evidence rows, with whether the new company resumed inside the
    12-1 momentum window (the last 252 + 21 sessions)."""
    cal = np.sort(pd.to_datetime(pd.Index(cal)).values)
    end_pos = int(np.searchsorted(cal, np.datetime64(pd.Timestamp(panel_end)), side="right")) - 1
    out = []
    for r in gaps.to_dict("records"):
        p = int(np.searchsorted(cal, np.datetime64(pd.Timestamp(r["first_after"]))))
        out.append({**{k: (str(v.date()) if isinstance(v, pd.Timestamp) else v) for k, v in r.items()},
                    "sessions_since_resume": end_pos - p,
                    "resumed_inside_12_1_window": bool(end_pos - p < 252 + 21)})
    return out


# ─────────────────────────────── blast radius ────────────────────────────────

def _load_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _symbols_in(o, keys=("symbol", "ticker")) -> set[str]:
    out: set[str] = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in keys and isinstance(v, str):
                    out.add(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(o)
    return out


def blast_radius(stitched: Iterable[str], *, optimus: Path | None = None,
                 asof_dir: str | None = None) -> dict:
    """READ-ONLY: where the stitched symbols sit in today's ranking, candidates,
    paper positions, tonight's intended book and the frozen books. Mutates nothing."""
    opt = Path(optimus or _OPTIMUS)
    S = set(stitched)
    out: dict = {}
    pcb = opt / "pc_book"
    days = sorted(p.name for p in pcb.glob("20??-??-??") if p.is_dir()) if pcb.exists() else []
    day = asof_dir or (days[-1] if days else None)
    if day:
        r = _load_json(pcb / day / "ranking.json") or {}
        top = r.get("top") or []
        out["ranking"] = {"path": str(pcb / day / "ranking.json"), "asof": r.get("asof"),
                          "n_top": len(top),
                          "stitched_in_top": [{"rank": t.get("rank"), "symbol": t.get("symbol")}
                                              for t in top if t.get("symbol") in S]}
        ib = _load_json(pcb / day / "intended_book.json") or {}
        book = ib.get("book") or []
        out["intended_book"] = {"path": str(pcb / day / "intended_book.json"), "t": ib.get("t"),
                                "symbols": sorted({b.get("symbol") for b in book if isinstance(b, dict)}),
                                "stitched": sorted({b.get("symbol") for b in book
                                                    if isinstance(b, dict) and b.get("symbol") in S}),
                                "probe_weights_stitched": sorted(set(ib.get("probe_weights") or {}) & S)}
        dec = pcb / day / "decisions.jsonl"
        hits: set[str] = set()
        if dec.exists():
            for line in dec.read_text(encoding="utf-8").splitlines():
                try:
                    hits |= _symbols_in(json.loads(line)) & S
                except ValueError:
                    continue
        out["decisions_jsonl_stitched_mentions"] = sorted(hits)
    pos = {}
    rels = ["paper_accounts/pc_snapshot/state_latest.json", "review/state_latest.json",
            "pc_book/state_latest.json"] + ([f"pc_book/{day}/state_latest.json"] if day else [])
    for rel in rels:
        d = _load_json(opt / rel)
        if d:
            syms = sorted({p.get("symbol") for p in d.get("positions") or [] if isinstance(p, dict)})
            pos[rel] = {"t": d.get("t"), "positions": syms, "stitched": sorted(set(syms) & S)}
    out["paper_positions"] = pos
    fun = sorted((opt.parent / "funnel_history").glob("funnel_*.json"))
    if fun:
        c = _symbols_in(_load_json(fun[-1]) or {})
        out["candidate_funnel"] = {"path": str(fun[-1]), "n_symbols": len(c), "stitched": sorted(c & S)}
    books = []
    n_books = 0
    bp = opt / "llm_portfolio" / "books.jsonl"
    if bp.exists():
        for line in bp.read_text(encoding="utf-8").splitlines():
            try:
                b = json.loads(line)
            except ValueError:
                continue
            n_books += 1
            ps = [p for p in b.get("positions") or [] if isinstance(p, dict)]
            hit = [(p.get("ticker") or p.get("symbol"), float(p.get("weight") or 0.0)) for p in ps
                   if (p.get("ticker") or p.get("symbol")) in S]
            if hit:
                books.append({"book_id": b.get("book_id"), "name": b.get("name"), "kind": b.get("kind"),
                              "frozen_utc": b.get("frozen_utc"),
                              "stitched_holdings": {t: round(w, 4) for t, w in hit},
                              "stitched_weight": round(sum(w for _, w in hit), 4)})
    out["frozen_books"] = {"path": str(bp), "n_books_total": n_books,
                           "n_books_holding_stitched": len(books),
                           "books": sorted(books, key=lambda x: -x["stitched_weight"])}
    trials = [t for t in sorted((opt / "trials").glob("lib_forward_trial_20*Z.json"))
              if "amendment" not in t.name]
    if trials:
        tr = _load_json(trials[0]) or {}
        ids = {b["book_id"] for b in books}
        affected = []
        for p in tr.get("pairs") or []:
            side = [s for s, k in (("book", "book_id"), ("twin", "twin_book_id")) if p.get(k) in ids]
            if side:
                affected.append({"book_id": p["book_id"], "name": p.get("name"),
                                 "twin_book_id": p.get("twin_book_id"), "twin_type": p.get("twin_type"),
                                 "stitched_on": side})
        out["trial_lib_fwd_twin_1"] = {"receipt": str(trials[0]), "n_pairs": len(tr.get("pairs") or []),
                                       "n_pairs_affected": len(affected), "pairs_affected": affected}
    return out


def main(argv=None) -> int:
    """`python -m backend.services.stitched_tickers` -> a receipt with the evidence
    per ticker and the blast radius. Reads only; writes one new receipt file."""
    import argparse
    from datetime import datetime, timezone
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(_OPTIMUS / "stitched_tickers"))
    a = ap.parse_args(argv)
    from backend.services import xs_ranker as XR
    paths = XR.survivorship_free_paths()
    frames = []
    for p in paths:
        d = pd.read_parquet(p, columns=["symbol", "date", "close"])
        d["_src"] = p.stem
        frames.append(d)
    b = (pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"], keep="first")
         .sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True))
    b["date"] = pd.to_datetime(b["date"])
    g = detect(b, src_col="_src")
    cal = _calendar(b, "SPY")
    rows = report_rows(g, b["date"].max(), cal)
    recent = XR.BARS_PATH   # the nightly-refreshed file: a first trade there that contradicts older history
    if recent.exists() and len(g):
        rr = pd.read_parquet(recent, columns=["symbol", "date"],
                             filters=[("symbol", "in", sorted(set(g["symbol"])))])
        first = rr.groupby("symbol")["date"].min()
        file_start = pd.read_parquet(recent, columns=["date"])["date"].min()
        for r in rows:
            f0 = first.get(r["symbol"])
            # only a first trade AFTER the file's own start says anything (the file starts
            # 2025-01 for every name)
            if (f0 is not None and pd.Timestamp(f0) > pd.Timestamp(file_start)
                    and pd.Timestamp(f0) >= pd.Timestamp(r["first_after"]) - pd.Timedelta(days=7)):
                r["evidence"].append(f"recent_file_first_trade: {recent.parent.name} starts "
                                     f"{pd.Timestamp(f0).date()} (the older file has history to {r['last_before']})")
    cut = sorted({r["symbol"] for r in rows if r["verdict"] in CUT_VERDICTS})
    run = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    rec = {"artefact": "STITCHED_TICKERS", "run_id": run, "licence": "PRODUCT_EXPERIMENT",
           "sources": [str(p) for p in paths], "panel_last_session": str(b["date"].max().date()),
           "gap_sessions_threshold": GAP_SESSIONS, "price_jump_ratio": PRICE_JUMP_RATIO,
           "registrant_sources": registrants().get("sources", []),
           "n_candidate_gaps": len(rows),
           "by_verdict": {k: int(v) for k, v in g["verdict"].value_counts().items()} if len(g) else {},
           "cut_symbols": cut,
           "cut_and_resumed_inside_12_1_window": sorted({r["symbol"] for r in rows
                                                        if r["verdict"] in CUT_VERDICTS
                                                        and r["resumed_inside_12_1_window"]}),
           "gaps": rows, "blast_radius": blast_radius(cut),
           "mutated": "NOTHING: bar files, frozen books, ledgers and receipts are read only",
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    od = Path(a.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    p = od / f"stitched_{run}.json"
    p.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("run_id", "n_candidate_gaps", "by_verdict",
                                            "cut_and_resumed_inside_12_1_window")}, default=str))
    print(str(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
