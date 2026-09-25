"""The daily pre-open review of every held name -- with a patience rule.

MURAT, 2026-09-25
=================
    "monitor the stock account before market once per day or once it hits the
     trigger but don't sell immediately when it jumps or drops, see what might
     happen and based on that make a decision"

So, once per session day (first sim cycle after 08:00 ET), and again when a
held name moves more than 2 sigma intraday:

* every held name in (a) Murat's book (`murat_book.yaml`), (b) the PC-PAPER
  account (`pc_broker.snapshot`), (c) every frozen `llm_portfolio` book;
* its last close, the 1-day and 5-day move **in sigma** (sigma = the 63-day
  daily standard deviation of the returns BEFORE the move being measured, so a
  shock cannot shrink its own z-score);
* the latest investigator forecast rows (h=1 / h=5) if any exist;
* the next dated catalyst;
* a label from `agency.decide_label` -- hold / trim / sell / buy_more --
  **wrapped by the patience rule**.

THE PATIENCE RULE
=================
A move beyond `SIGMA_TRIGGER` (2.0) on the day is labelled `WATCH`, never
`sell`, unless yesterday's review already said WATCH for that holding. The
next session decides with a day's more information. The rule applies to up
moves too ("don't sell immediately when it jumps or drops"): a +3 sigma day is
not a `buy_more` either, until it has survived a session.

It changes WHEN a label may act, never what the label is derived from: the
following session calls `decide_label` exactly as it would have, so SELL and
TRIM are reachable one session later.

WHAT IS NEVER SKIPPED
=====================
A held ticker absent from the price panel is reported `UNPRICED` with its
source, not dropped. A book whose positions cannot be read is reported
`UNAVAILABLE` with the reason. A review that silently shows eight of twelve
names is worse than one that shows twelve rows and four refusals.

EVERY LABEL IS A FORECAST
=========================
Each decisive label (hold / trim / sell / buy_more) is minted as a forecast row
(`specialist="review:v0"`, BEATS_BENCHMARK vs SPY, h=5) at the probability its
direction implies, so labels are GRADED like every other arm. `WATCH` and
`UNPRICED` carry no direction and mint nothing. Intraday re-reviews never
mint: one graded row per holding per day.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

from backend import config as _cfg

REVIEW_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "review"
MURAT_BOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "murat_book.yaml"
BOOKS_PATH = Path(_cfg.OPTIMUS_LEDGER_DIR) / "llm_portfolio" / "books.jsonl"
CATALYST_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "pm_catalysts"
PREDICTIONS_PATH = Path(_cfg.OPTIMUS_LEDGER_DIR) / "predictions.jsonl"

#: |1d move| above this many sigma sets WATCH for one session.
SIGMA_TRIGGER = 2.0
#: The sigma window, in daily returns.
SIGMA_WINDOW = 63
#: Fewer prior returns than this and sigma is UNKNOWN (no WATCH can be set).
MIN_SIGMA_OBS = 20

SPECIALIST = "review:v0"
REVIEW_HORIZON = 5
#: The probability each label's DIRECTION implies, for grading. `decide_label`
#: sells below 0.40 and buys above 0.60; these sit inside those bands.
LABEL_PROBABILITY: dict[str, float] = {"buy_more": 0.60, "hold": 0.50,
                                       "trim": 0.45, "sell": 0.35}

#: Per-source single-name cap handed to `decide_label`. Murat's own book has
#: NO cap on a good name (his order, 2026-09-25); PC-PAPER carries the broker
#: mandate's 12%; a competition book is capped at 10% by its rules.
MAX_SINGLE_NAME: dict[str, float] = {"murat_book": 1.0, "pc_paper": 0.12,
                                     "llm_personal": 1.0,
                                     "llm_competition": 0.10}

TAIL_BYTES = 16 * 1024 * 1024


# ─────────────────────────────── price arithmetic ───────────────────────────

def price_stats(closes: Any, *, live_price: float | None = None) -> dict | None:
    """Last close, 1d/5d move, sigma_63 and the z-scores, from a close series.

    `closes` is an ordered iterable of closes (oldest first) up to `asof`.
    With `live_price`, the 1-day move is live vs the last close and sigma is
    the last 63 closed-session returns.
    """
    c = [float(x) for x in closes if x is not None and math.isfinite(float(x))
         and float(x) > 0]
    if len(c) < 2:
        return None
    rets = [c[i] / c[i - 1] - 1.0 for i in range(1, len(c))]
    if live_price is not None and live_price > 0:
        r1 = live_price / c[-1] - 1.0
        prior = rets[-SIGMA_WINDOW:]
        last = float(live_price)
        r5 = (live_price / c[-5] - 1.0) if len(c) >= 5 else None
    else:
        r1 = rets[-1]
        prior = rets[-(SIGMA_WINDOW + 1):-1]
        last = c[-1]
        r5 = (c[-1] / c[-6] - 1.0) if len(c) >= 6 else None
    sigma = None
    if len(prior) >= MIN_SIGMA_OBS:
        m = sum(prior) / len(prior)
        var = sum((x - m) ** 2 for x in prior) / (len(prior) - 1)
        sigma = math.sqrt(var) if var > 0 else None
    z1 = (r1 / sigma) if sigma else None
    z5 = (r5 / (sigma * math.sqrt(5))) if (sigma and r5 is not None) else None
    return {"last_close": round(c[-1], 4), "price": round(last, 4),
            "ret_1d": round(r1, 5), "ret_5d": None if r5 is None else round(r5, 5),
            "sigma_63": None if sigma is None else round(sigma, 5),
            "z_1d": None if z1 is None else round(z1, 2),
            "z_5d": None if z5 is None else round(z5, 2)}


def closes_by_ticker(bars: Any, tickers: Iterable[str], asof: date | str) -> dict:
    """{ticker: [closes up to and including asof]} from a symbol/date/close frame."""
    import pandas as pd
    want = {str(t).upper() for t in tickers}
    if bars is None or len(bars) == 0:
        return {}
    b = bars[bars["symbol"].isin(want)]
    b = b[pd.to_datetime(b["date"]) <= pd.Timestamp(str(asof))]
    b = b.sort_values(["symbol", "date"])
    return {s: g["close"].tolist()[-(SIGMA_WINDOW + 10):]
            for s, g in b.groupby("symbol")}


# ─────────────────────────────── inputs ─────────────────────────────────────

def _tail_rows(path: Path, tail_bytes: int = TAIL_BYTES) -> list[dict]:
    if not Path(path).exists():
        return []
    with Path(path).open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - tail_bytes))
        lines = fh.read().decode("utf-8", errors="replace").splitlines()
    if size > tail_bytes and lines:
        lines = lines[1:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def latest_forecasts(tickers: Iterable[str], *, asof: date | str,
                     path: Path | None = None) -> dict[str, dict[int, dict]]:
    """The newest `investigator:*` row per ticker per horizon (1 and 5), made
    on or before `asof`."""
    want = {str(t).upper() for t in tickers}
    day = str(asof)[:10]
    out: dict[str, dict[int, dict]] = {}
    for r in _tail_rows(path or PREDICTIONS_PATH):
        t = str(r.get("ticker") or "").upper()
        if t not in want or not str(r.get("specialist") or "").startswith("investigator:"):
            continue
        h = r.get("horizon_days")
        if h not in (1, 5) or str(r.get("made_at") or "")[:10] > day:
            continue
        cur = out.setdefault(t, {}).get(h)
        if cur is None or str(r.get("made_at")) >= str(cur.get("made_at")):
            out[t][h] = {"probability": r.get("probability"),
                         "made_at": r.get("made_at"),
                         "specialist": r.get("specialist"),
                         "prediction_id": r.get("prediction_id")}
    return out


def prior_watch(asof: date | str, *, review_dir: Path | None = None) -> set[tuple[str, str]]:
    """(source, ticker) pairs labelled WATCH in the latest review BEFORE asof."""
    d = Path(review_dir or REVIEW_DIR)
    day = str(asof)[:10]
    files = sorted(p for p in d.glob("review_????-??-??.json") if p.stem[7:] < day)
    if not files:
        return set()
    try:
        r = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {(x.get("source"), x.get("ticker")) for x in r.get("rows") or []
            if x.get("label") == "WATCH"}


def load_catalysts(*, catalyst_dir: Path | None = None,
                   murat_book_path: Path | None = None) -> list[dict]:
    """Dated catalysts from the pm_catalysts YAMLs and the book file's own
    `catalysts:` entries. An unreadable file is skipped with a log line."""
    import yaml
    rows: list[dict] = []
    for p in sorted(Path(catalyst_dir or CATALYST_DIR).glob("*.y*ml")):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logger.warning("daily_review: catalyst file %s unreadable (%s)", p, exc)
            continue
        items = d.get("catalysts", d.get("rows", [])) if isinstance(d, dict) else d
        for c in items or []:
            if isinstance(c, dict) and c.get("ticker") and c.get("date"):
                rows.append({**c, "ticker": str(c["ticker"]).upper(),
                             "date": str(c["date"])[:10], "file": p.name})
    try:
        mb = yaml.safe_load(Path(murat_book_path or MURAT_BOOK_PATH)
                            .read_text(encoding="utf-8")) or {}
        for pos in mb.get("positions") or []:
            for c in (pos or {}).get("catalysts") or []:
                if isinstance(c, dict) and c.get("date"):
                    rows.append({**c, "ticker": str(pos["ticker"]).upper(),
                                 "date": str(c["date"])[:10],
                                 "file": "murat_book.yaml"})
    except (OSError, ValueError, yaml.YAMLError):
        pass
    return rows


def next_catalyst(catalysts: list[dict], ticker: str, asof: date | str) -> dict | None:
    day = str(asof)[:10]
    fut = sorted((c for c in catalysts
                  if c.get("ticker") == str(ticker).upper() and c["date"] >= day),
                 key=lambda c: c["date"])
    if not fut:
        return None
    c = fut[0]
    return {"date": c["date"], "kind": c.get("kind"), "what": c.get("what"),
            "verified_from": c.get("verified_from")}


# ─────────────────────────────── the books ──────────────────────────────────

def murat_book(path: Path | None = None) -> dict:
    """Murat's positions as shares; weights are filled in from prices later."""
    import yaml
    try:
        d = yaml.safe_load(Path(path or MURAT_BOOK_PATH).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {"source": "murat_book", "unavailable": f"unreadable: {exc}",
                "positions": []}
    return {"source": "murat_book", "max_single_name": MAX_SINGLE_NAME["murat_book"],
            "positions": [{"ticker": str(p["ticker"]).upper(),
                           "shares": float(p.get("shares") or 0)}
                          for p in d.get("positions") or []
                          if isinstance(p, dict) and p.get("ticker")]}


def pc_paper_book(snapshot: Mapping | None) -> dict:
    if not snapshot:
        return {"source": "pc_paper", "unavailable": "no broker snapshot",
                "positions": []}
    eq = float(snapshot.get("equity") or 0.0)
    return {"source": "pc_paper", "max_single_name": MAX_SINGLE_NAME["pc_paper"],
            "positions": [{"ticker": str(p["symbol"]).upper(),
                           "shares": float(p.get("qty") or 0),
                           "weight": (float(p.get("market_value") or 0) / eq
                                      if eq > 0 else None)}
                          for p in snapshot.get("positions") or []]}


def llm_books(path: Path | None = None) -> list[dict]:
    """Every frozen llm_portfolio book (twins excluded: they are controls)."""
    p = Path(path or BOOKS_PATH)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("parent_book_id") or r.get("parent_hash"):
            continue
        kind = r.get("kind") or "personal"
        cap = (r.get("constraints") or {}).get("max_weight")
        if cap is None:
            cap = MAX_SINGLE_NAME.get(f"llm_{kind}", 1.0)
        out.append({"source": f"llm:{r.get('name') or r.get('book_id')}",
                    "book_id": r.get("book_id"), "kind": kind,
                    "max_single_name": float(cap),
                    "positions": [{"ticker": str(x["ticker"]).upper(),
                                   "weight": x.get("weight")}
                                  for x in r.get("positions") or []
                                  if isinstance(x, dict) and x.get("ticker")
                                  and str(x["ticker"]).upper() not in ("CASH", "$CASH")]})
    return out


# ─────────────────────────────── the review ─────────────────────────────────

def _label(p: float | None, *, weight: float | None, cap: float,
           z1: float | None, watched_yesterday: bool) -> tuple[str, str, str]:
    """(label, reason, base_label). The patience rule wraps decide_label."""
    from backend.services.agency import decide_label
    pp = 0.5 if p is None else float(p)
    base, why = decide_label(pp, weight=float(weight or 0.0), max_single_name=cap)
    if p is None:
        why = f"no forecast row for this name (UNFORECAST); {why}"
    if z1 is not None and abs(z1) > SIGMA_TRIGGER and not watched_yesterday:
        return ("WATCH", f"moved {z1:+.1f}σ today; decide next session "
                         f"(the label would have been {base})", base)
    if watched_yesterday:
        why = f"WATCH last session; deciding now: {why}"
    return base, why, base


def review_holdings(asof: date | str, *, bars: Any, books: list[dict],
                    forecasts: Mapping[str, Mapping[int, Mapping]] | None = None,
                    watched: set[tuple[str, str]] | None = None,
                    catalysts: list[dict] | None = None,
                    live_prices: Mapping[str, float] | None = None) -> dict:
    """Pure: one row per (book, holding). Writes nothing.

    `books` is a list of `{source, max_single_name, positions: [{ticker,
    weight? , shares?}]}` (see `gather_books`); a book with `unavailable` is
    reported as such.
    """
    day = str(asof)[:10]
    forecasts = forecasts or {}
    watched = watched or set()
    catalysts = catalysts or []
    live_prices = live_prices or {}
    tickers = {p["ticker"] for b in books for p in b.get("positions") or []}
    closes = closes_by_ticker(bars, tickers, day)

    rows, unavailable = [], []
    for b in books:
        src = b.get("source")
        if b.get("unavailable"):
            unavailable.append({"source": src, "why": b["unavailable"]})
            continue
        stats = {p["ticker"]: price_stats(closes.get(p["ticker"], []),
                                          live_price=live_prices.get(p["ticker"]))
                 for p in b.get("positions") or []}
        # weights from shares x price where the book gives shares only
        vals = {t: (p.get("shares") or 0) * stats[t]["price"]
                for p in b.get("positions") or []
                for t in [p["ticker"]] if stats.get(t) and p.get("weight") is None}
        tot = sum(vals.values())
        cap = float(b.get("max_single_name") or 1.0)
        for p in b.get("positions") or []:
            t = p["ticker"]
            st = stats.get(t)
            row = {"source": src, "ticker": t, "shares": p.get("shares")}
            if st is None:
                rows.append({**row, "label": "UNPRICED",
                             "reason": "no price in the panel up to asof; "
                                       "reported, not skipped"})
                continue
            w = p.get("weight")
            if w is None:
                w = (vals.get(t, 0.0) / tot) if tot > 0 else None
            fc = forecasts.get(t) or {}
            p_used, h_used = None, None
            for h in (5, 1):
                v = (fc.get(h) or {}).get("probability")
                if isinstance(v, (int, float)):
                    p_used, h_used = float(v), h
                    break
            label, why, base = _label(p_used, weight=w, cap=cap, z1=st["z_1d"],
                                      watched_yesterday=(src, t) in watched)
            rows.append({**row, **st, "weight": None if w is None else round(w, 4),
                         "max_single_name": cap,
                         "forecast_h1": (fc.get(1) or {}).get("probability"),
                         "forecast_h5": (fc.get(5) or {}).get("probability"),
                         "probability_used": p_used,
                         "horizon_used": h_used,
                         "next_catalyst": next_catalyst(catalysts, t, day),
                         "label": label, "base_label": base, "reason": why,
                         "watched_last_session": (src, t) in watched})
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    return {"receipt": "daily_review", "asof": day,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "intraday": bool(live_prices), "sigma_trigger": SIGMA_TRIGGER,
            "sigma_window": SIGMA_WINDOW, "n_rows": len(rows),
            "counts": counts, "unavailable": unavailable, "rows": rows,
            "patience_rule": ("|1d move| > 2 sigma_63 with no WATCH last session "
                              "=> WATCH, never sell; the next session decides")}


def morning_md(review: dict, *, max_rows: int = 10) -> str:
    """A 15-line page: the table sorted by |z_1d|, then counts and refusals."""
    rows = sorted(review["rows"], key=lambda r: -abs(r.get("z_1d") or 0.0))
    lines = [f"# Morning review {review['asof']}"
             + (" (intraday)" if review.get("intraday") else ""),
             f"{review['n_rows']} holdings; labels {review['counts']}",
             "| src | ticker | close | 1d σ | 5d σ | p5/p1 | label | why |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows[:max_rows]:
        p = r.get("forecast_h5") if r.get("forecast_h5") is not None else r.get("forecast_h1")
        lines.append(f"| {r['source']} | {r['ticker']} | {r.get('last_close', '-')} | "
                     f"{r.get('z_1d', '-')} | {r.get('z_5d', '-')} | "
                     f"{'-' if p is None else round(p, 2)} | {r['label']} | "
                     f"{str(r.get('reason', ''))[:70]} |")
    more = len(rows) - max_rows
    unav = "; ".join(f"{u['source']}: {u['why']}" for u in review["unavailable"])
    lines.append(f"{max(0, more)} more row(s) in review_{review['asof']}.json"
                 + (f" | UNAVAILABLE: {unav}" if unav else ""))
    return "\n".join(lines[:15]) + "\n"


def mint_label_forecasts(review: dict, *, path: Path | None = None) -> list[str]:
    """Each decisive label becomes a graded h=5 row. WATCH/UNPRICED mint nothing."""
    from backend.services import belief_state as B
    recs = []
    for r in review["rows"]:
        prob = LABEL_PROBABILITY.get(r["label"])
        if prob is None:
            continue
        try:
            recs.append(B.make_prediction(
                ticker=r["ticker"], specialist=SPECIALIST,
                observable=B.Observable.BEATS_BENCHMARK,
                horizon_days=REVIEW_HORIZON, probability=prob, benchmark="SPY",
                thesis=str(r.get("reason"))[:800],
                counter_thesis=f"the label {r['label']} is wrong if the name "
                               f"{'lags' if prob > 0.5 else 'beats'} SPY over 5 sessions",
                next_observable="the next session's review",
                model="deterministic", model_version=SPECIALIST,
                prompt="agency.decide_label wrapped by the 2-sigma patience rule",
                input_snapshot={k: r.get(k) for k in (
                    "source", "ticker", "weight", "z_1d", "z_5d",
                    "probability_used", "label", "base_label")},
                decision_date=review["asof"], licence="PRODUCT_EXPERIMENT",
                notes_text=f"daily_review {review['asof']} source {r['source']}"))
        except ValueError as exc:
            logger.warning("daily_review: label row refused for %s: %s",
                           r["ticker"], exc)
    if recs:
        B.append(recs, path=path)
    return [x.prediction_id for x in recs]


# ─────────────────────────────── orchestration ─────────────────────────────

def gather_books(*, snapshot: Mapping | None = None,
                 snapshot_error: str | None = None,
                 murat_book_path: Path | None = None,
                 books_path: Path | None = None) -> list[dict]:
    pc = pc_paper_book(snapshot)
    if snapshot_error:
        pc["unavailable"] = snapshot_error
    return [murat_book(murat_book_path), pc, *llm_books(books_path)]


def review_paths(day: str, *, review_dir: Path | None = None,
                 intraday_tag: str | None = None) -> tuple[Path, Path]:
    d = Path(review_dir or REVIEW_DIR)
    suffix = f"_intraday_{intraday_tag}" if intraday_tag else ""
    return d / f"review_{day}{suffix}.json", d / f"morning_{day}{suffix}.md"


def run_daily(*, asof: str | None = None, live_prices: Mapping[str, float] | None = None,
              intraday_tag: str | None = None, bars: Any = None,
              snapshot: Mapping | None = None, review_dir: Path | None = None,
              ledger_path: Path | None = None, mint: bool | None = None) -> dict:
    """Load everything, review, write `review_<date>.json` + `morning_<date>.md`,
    mint the label rows (morning review only). Returns a summary."""
    day = asof or datetime.now(timezone.utc).date().isoformat()
    snap_err = None
    if snapshot is None:
        try:
            from backend.services import pc_broker as PB
            snapshot = PB.snapshot(tag="review",
                                   out_dir=Path(review_dir or REVIEW_DIR))
        except Exception as exc:                                   # noqa: BLE001
            snap_err = f"pc_broker.snapshot failed: {type(exc).__name__}: {exc}"[:200]
    books = gather_books(snapshot=snapshot, snapshot_error=snap_err)
    tickers = sorted({p["ticker"] for b in books for p in b.get("positions") or []})
    if bars is None:
        from backend.services import xs_ranker as XR
        bars = XR.load_bars(XR.survivorship_free_paths())
        bars = bars[bars["symbol"].isin(tickers)][["symbol", "date", "close"]]
    rev = review_holdings(day, bars=bars, books=books,
                          forecasts=latest_forecasts(tickers, asof=day),
                          watched=prior_watch(day, review_dir=review_dir),
                          catalysts=load_catalysts(), live_prices=live_prices)
    jpath, mpath = review_paths(day, review_dir=review_dir, intraday_tag=intraday_tag)
    mint = (not live_prices) if mint is None else mint
    rev["minted_prediction_ids"] = (mint_label_forecasts(rev, path=ledger_path)
                                    if mint else [])
    jpath.parent.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(rev, indent=1, default=str), encoding="utf-8")
    mpath.write_text(morning_md(rev), encoding="utf-8")
    return {"asof": day, "n_rows": rev["n_rows"], "counts": rev["counts"],
            "n_minted": len(rev["minted_prediction_ids"]),
            "unavailable": [u["source"] for u in rev["unavailable"]],
            "review": str(jpath), "morning": str(mpath)}


def held_sigma_table(review_path: Path) -> dict[str, dict]:
    """{ticker: {last_close, sigma_63}} from a written review -- what the
    intraday trigger needs, without reloading the bars."""
    try:
        r = json.loads(Path(review_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {x["ticker"]: {"last_close": x.get("last_close"),
                          "sigma_63": x.get("sigma_63")}
            for x in r.get("rows") or [] if x.get("sigma_63") and x.get("last_close")}


def intraday_triggers(table: Mapping[str, Mapping], live: Mapping[str, float], *,
                      already: Iterable[str] = ()) -> list[dict]:
    """Held names whose live move vs the last close exceeds SIGMA_TRIGGER."""
    done = set(already)
    out = []
    for t, s in table.items():
        px = live.get(t)
        if t in done or not px or not s.get("last_close") or not s.get("sigma_63"):
            continue
        z = (px / s["last_close"] - 1.0) / s["sigma_63"]
        if abs(z) > SIGMA_TRIGGER:
            out.append({"ticker": t, "z": round(z, 2), "price": px})
    return out
