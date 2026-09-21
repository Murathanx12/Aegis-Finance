"""J2_missed_opportunity — the biggest moves AEGIS did not capture, and whether
anything on our own disk said so BEFOREHAND.

Murat's night brief, 2026-09-21: *"every night, find the largest market moves
AEGIS did NOT capture, and for each ask whether the information was observable
beforehand"* — and make that the ONE paid DeepSeek question of the night, run
LOCAL vs DEEPSEEK on the SAME cases so the paid model has to earn its cost.

FOUR STEPS, and only the fourth costs money.

1. **THE MOVES.** `paper_books.load_bars()` (P6 refreshes them earlier in the
   queue, so this reads at RUN time, never at import). The trailing
   `config.MISSED_OPP_WINDOW_SESSIONS` sessions, ranked by |excess return vs
   SPY| over each name's BEST `config.MISSED_OPP_SUBWINDOW_SESSIONS`-session
   sub-window. Top `config.MISSED_OPP_TOP_K`. A dollar-volume floor is applied
   and PRINTED: without one this job reports the same sub-dollar tape every
   night and says nothing about anything we could have traded.

2. **WHAT AEGIS DID.** The day contracts (`decisions/<date>.json`) and
   `decisions/ledger.jsonl` crossed against each name: direction, authority,
   the refusal sentence. A name no contract in the window mentions is
   `not_in_the_universe`, which is a FINDING (the universe is the first
   filter), not a missing value.

3. **THE PRECURSOR CHECK** — deterministic, PIT, and it never asks a model.
   Only rows dated strictly BEFORE the move's first session count. Seven
   classes, each PRESENT / ABSENT / NOT_HELD **with the path it was read
   from**. NOT_HELD is not a soft ABSENT: "we hold no short-interest table" and
   "we hold one and it is flat" are different answers and a reader that
   conflates them learns nonsense (`docs/AEGIS_STRATEGIC_INVARIANTS.md`; a
   check that did not run is not a check that passed).

4. **THE PAIRED READ.** One masked, dated digest per case, built from the
   pre-move corpus rows only, masked with `r7_news_representation.mask_company`
   over `tokenise` — the SAME function `night_x_anonymisation_gap` and the
   scenario gym mask with. BOTH readers, `local_gguf` and `deepseek`, answer
   the SAME frozen schema on the SAME cases, and each reader's
   `precursor_class` is graded against step 3's PRESENT set. Hit rates, a
   PAIRED McNemar on the discordant pairs, and Brier of each reader's stated
   confidence. That is what "the paid model has to earn its cost" means as a
   number: DeepSeek is worth $4 if and only if it is measurably better than the
   free reader ON THESE CASES.

THE SCHEMA TRAVELS IN THE SYSTEM MESSAGE (2026-09-13, paid for at 54%
refusals: a prompt that REFERS to a schema it never sends is a prompt whose
enum the model invents). `prompt_fingerprint()` hashes what is actually sent
and carries `schema_in_system`, which goes false on the receipt if a future
edit moves the field list into a comment.

THE PAID LEG IS SWITCHED BY THE ENVIRONMENT, NOT BY A FLAG. `scripts.night_factory`
launches every job with NO per-job CLI arguments, so a leg that can only be
turned on with `--backend deepseek` can never run in the night queue. The
DeepSeek leg runs when BOTH:

    AEGIS_NIGHT_PAID_OK=1      is in the environment, and
    DEEPSEEK_API_KEY           is a NAME present in the environment

and otherwise it is REFUSED BY NAME on the receipt. The value of the key is
never read here and never printed. `--backend deepseek` still works for a hand
run (it sets the same intent explicitly); the LOCAL leg always runs.

COST. The DeepSeek leg goes through `night_l2_typed_events._RunCap` with
`purpose=PURPOSE` — chunk 22c (`c349c202`), and naming the purpose is NOT
optional: left off, the cap falls back to L2's purpose and spends the night
summing another job's rows ($0.013238 read against $10.047856 written, same
file, same instant). The cap's read and the receipt's read are printed side by
side after the FIRST flush as `cap_block.first_flush_agreement`, and a
disagreement wider than one call's worst case stops the run as
`REFUSED_CAP_READER_DISAGREES`. Two more run-level refusals:
`REFUSED_UNPRICED_CALL` (a model id `config.LLM_PRICE_PER_MTOK` cannot price
is summed as 0.0, so the cap over it is a lower bound of zero) and
`REFUSED_NO_LEDGER`.

TWO STOPS, ON PURPOSE. `config.MISSED_OPP_SOFT_STOP_USD` ($4.00) is where this
job stops asking; `config.MISSED_OPP_MAX_USD` ($4.50) is the `_RunCap` hard
backstop for billing that arrives after the last read. A single number would
have to be either too tight to finish or too loose to bind.

The provider BALANCE is the ground truth, not our telemetry: a snapshot is
taken before the first paid call and after the last, and both are on the
receipt with the delta.

    python -m scripts.night_factory_jobs J2_missed_opportunity --smoke
    python -m scripts.night_factory_jobs J2_missed_opportunity --backend deepseek --max-usd 4.5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config                                        # noqa: E402

JOB = "J2_missed_opportunity"
LICENCE = "PRODUCT_EXPERIMENT"
#: the ledger purpose. ONE string, read by the cap and written by every call.
PURPOSE = "j2_missed_opportunity"
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")

OPTIMUS = REPO / "backend" / "data" / "optimus"
DECISIONS = OPTIMUS / "decisions"
INSIDER = OPTIMUS / "sec_insider" / "insider_events_v1.parquet"
NEWS_PANEL = OPTIMUS / "text_return_panel" / "news_returns_2025_26.parquet"
TYPED_EVENTS = OPTIMUS / "typed_events"
ANALYST = REPO / "backend" / "data" / "analyst_snapshots.jsonl"
#: looked for and named whether or not it exists — "we hold none" is an answer.
TRENDS_CACHE = OPTIMUS / "trends_sentiment_cache.json"
SHORT_INTEREST = OPTIMUS / "short_interest" / "short_interest_v1.parquet"
SUPPLIER_GRAPH = OPTIMUS / "supply_chain" / "supplier_customer_edges.parquet"

#: the env NAMES this job reads. VALUES are never read and never printed.
PAID_OK_ENV = "AEGIS_NIGHT_PAID_OK"
KEY_ENV = "DEEPSEEK_API_KEY"

PRESENT, ABSENT, NOT_HELD = "PRESENT", "ABSENT", "NOT_HELD"

#: The frozen answer vocabulary. It is written out IN `SYSTEM` below; these
#: names exist so the grader and the prompt cannot drift apart silently.
PRECURSOR_CLASSES = ("insider_cluster", "revision_breadth", "coverage_change",
                     "news_volume", "typed_event", "search_interest",
                     "short_interest", "supplier_readthrough", "none")

#: the classes step 3 can actually adjudicate. `supplier_readthrough` is in the
#: reader's vocabulary and has no on-disk source: a reader naming it is graded
#: as a MISS and the receipt says which classes were unadjudicable, because a
#: grader that silently scores an unanswerable class is a broken grader.
ADJUDICABLE = ("insider_cluster", "revision_breadth", "coverage_change",
               "news_volume", "typed_event", "search_interest",
               "short_interest", "supplier_readthrough")

REFUSED_NO_BARS = "REFUSED_NO_BARS"
REFUSED_NO_LEDGER = "REFUSED_NO_LEDGER"
REFUSED_UNPRICED_CALL = "REFUSED_UNPRICED_CALL"
REFUSED_CAP_READER_DISAGREES = "REFUSED_CAP_READER_DISAGREES"
CAP_REFUSALS = (REFUSED_NO_LEDGER, REFUSED_UNPRICED_CALL,
                REFUSED_CAP_READER_DISAGREES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(x, n: int = 6):
    return None if x is None else round(float(x), n)


# ═══════════════════════════════════════════════════════ 1. the moves

def rank_missed(bars, *, window: int | None = None, top_k: int | None = None,
                sub: int | None = None, floor_usd: float | None = None,
                bench: str = "SPY") -> dict:
    """The trailing window's largest |excess vs SPY| over a best sub-window.

    Returns `{"moves": [...], "calendar": [...], "screen": {...}}`. Every
    number a caller might quote is in `screen`, because a headline number with
    no receipt is the failure this repository names most often.

    The sub-window is the point. A name that gave 20% back over the month and a
    name that never moved look identical on a 21-session total; the question
    "what did we miss" is about the MOVE, so each name is scored on its own
    best contiguous `sub`-session run of excess return.
    """
    import numpy as np
    import pandas as pd

    window = int(config.MISSED_OPP_WINDOW_SESSIONS if window is None else window)
    top_k = int(config.MISSED_OPP_TOP_K if top_k is None else top_k)
    sub = int(config.MISSED_OPP_SUBWINDOW_SESSIONS if sub is None else sub)
    floor = float(config.MISSED_OPP_MIN_DOLLAR_VOL if floor_usd is None
                  else floor_usd)

    b = bars[["symbol", "date", "close", "volume"]].copy()
    b["date"] = pd.to_datetime(b["date"])
    bench_rows = b[b["symbol"] == bench]
    if bench_rows.empty:
        raise ValueError(f"the bar panel carries no {bench} rows; an excess "
                         f"return with no benchmark is a raw return wearing a "
                         f"benchmark's label")
    cal = sorted(bench_rows["date"].unique())[-(window + 1):]
    if len(cal) < sub + 1:
        raise ValueError(f"only {len(cal)} sessions of {bench} in the panel; "
                         f"{sub + 1} are needed for one sub-window")
    b = b[b["date"].isin(cal)]

    px = b.pivot_table(index="date", columns="symbol", values="close",
                       aggfunc="last").sort_index()
    dv = (b.assign(dv=b["close"] * b["volume"])
            .pivot_table(index="date", columns="symbol", values="dv",
                         aggfunc="last").sort_index())
    ret = px.pct_change().iloc[1:]
    if bench not in ret.columns:
        raise ValueError(f"{bench} has no return on this calendar")
    ex = ret.sub(ret[bench], axis=0).drop(columns=[bench])
    # a name must be priced on EVERY session of the window: a partial series
    # makes a rolling sum over fewer days look like a smaller move.
    full = ex.columns[ex.notna().all(axis=0)]
    ex = ex[full]
    med_dv = dv[[c for c in full if c in dv.columns]].median(axis=0)
    liquid = [c for c in full if float(med_dv.get(c, 0.0) or 0.0) >= floor]
    ex = ex[liquid]

    roll = ex.rolling(sub).sum().iloc[sub - 1:]
    if roll.empty:
        raise ValueError("no complete sub-window on this calendar")

    dates = list(roll.index)
    # THE SUB-WINDOW'S FIRST SESSION, and getting this wrong is not cosmetic:
    # it is what the entire PIT precursor check is anchored on. `roll` was
    # sliced at `iloc[sub-1:]`, so its row `i` sums the returns of `ex` rows
    # `i .. i+sub-1` — the START is `ex.index[i]`, NOT `dates[i-sub+1]`, which
    # clamps to the END for the first window and would let the precursor check
    # read rows from inside the move.
    ex_dates = list(ex.index)
    moves = []
    arr = roll.to_numpy()
    for j, symbol in enumerate(roll.columns):
        col = arr[:, j]
        if not np.isfinite(col).any():
            continue
        i = int(np.nanargmax(np.abs(col)))
        val = float(col[i])
        end = pd.Timestamp(dates[i])
        start = pd.Timestamp(ex_dates[i])
        moves.append({
            "ticker": str(symbol),
            "window_start": start.date().isoformat(),
            "window_end": end.date().isoformat(),
            "excess_pct": _r(val * 100.0, 4),
            "abs_excess_pct": _r(abs(val) * 100.0, 4),
            "direction": "UP" if val > 0 else "DOWN",
            "median_dollar_vol": _r(float(med_dv.get(symbol, 0.0) or 0.0), 1),
        })
    moves.sort(key=lambda m: -(m["abs_excess_pct"] or 0.0))
    kept = moves[:top_k]
    return {
        "moves": kept,
        "calendar": [pd.Timestamp(d).date().isoformat() for d in cal],
        "screen": {
            "window_sessions": window,
            "subwindow_sessions": sub,
            "top_k": top_k,
            "benchmark": bench,
            "dollar_vol_floor": floor,
            "dollar_vol_floor_why": (
                "without a floor the same sub-dollar tape wins every night and "
                "the receipt says nothing about anything we could have traded"),
            "n_symbols_in_panel": int(px.shape[1]),
            "n_priced_every_session": int(len(full)),
            "n_over_the_floor": int(len(liquid)),
            "n_ranked": len(moves),
            "first_session": (pd.Timestamp(cal[0]).date().isoformat()
                              if len(cal) else None),
            "last_session": (pd.Timestamp(cal[-1]).date().isoformat()
                             if len(cal) else None),
            "excess_is": "sum of daily (r_symbol - r_SPY) over the sub-window",
        },
    }


# ═══════════════════════════════════════════════ 2. what AEGIS did

def _contract_rows(days: list[str], root: Path | None = None) -> dict:
    """`ticker -> [row, ...]` from the day contracts AND the decision ledger.

    Both are read because they answer different questions: a day contract is
    what the engine decided that morning, the ledger is the append-only record
    across days. A name in neither is not in the universe.
    """
    root = Path(root) if root is not None else DECISIONS
    by_ticker: dict[str, list[dict]] = {}
    files, missing = [], []
    for d in days:
        p = root / f"{d}.json"
        if p.is_file():
            files.append(str(p))
        else:
            missing.append(d)
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                          # noqa: BLE001
            continue
        for row in obj.get("rows") or []:
            t = str(row.get("ticker") or "").upper()
            if not t or ":" in t:                # AGENCY_BOOK:* are not names
                continue
            by_ticker.setdefault(t, []).append({
                "asof": row.get("asof") or obj.get("date"),
                "source": "day_contract",
                "direction": row.get("verdict"),
                "authority": row.get("authority"),
                "signal": row.get("signal"),
                "refusal_class": row.get("refusal_class"),
                "terminal_state": row.get("terminal_state"),
                "why": (row.get("refusal_sentence") or row.get("roi")
                        or row.get("authority_basis")),
            })
    led = root / "ledger.jsonl"
    n_ledger = 0
    if led.is_file():
        for line in led.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:                                      # noqa: BLE001
                continue
            if str(row.get("asof") or "")[:10] not in set(days):
                continue
            t = str(row.get("ticker") or "").upper()
            if not t or ":" in t:
                continue
            n_ledger += 1
            by_ticker.setdefault(t, []).append({
                "asof": row.get("asof"), "source": "ledger",
                "direction": row.get("verdict") or row.get("direction"),
                "authority": row.get("authority"),
                "signal": row.get("signal"),
                "refusal_class": row.get("refusal_class"),
                "terminal_state": row.get("terminal_state"),
                "why": row.get("refusal_sentence") or row.get("roi"),
            })
    return {"by_ticker": by_ticker, "files": files, "days_with_no_contract": missing,
            "ledger_rows_in_window": n_ledger,
            "ledger_path": str(led) if led.is_file() else None}


def what_aegis_did(ticker: str, contracts: dict, holdings: set | None = None) -> dict:
    """The one-line answer for a name, with the sentence that produced it."""
    rows = contracts["by_ticker"].get(ticker.upper()) or []
    held = bool(holdings and ticker.upper() in holdings)
    if not rows:
        return {
            "direction": "absent",
            "in_universe": False,
            "held_in_paper_books": held,
            "summary": ("not in the universe — no day contract and no ledger "
                        "row in this window names it"),
            "n_rows": 0, "rows": [],
        }
    order = {"BUY": 0, "SELL": 1, "WATCH": 2, "PROBE": 3, "REFUSED": 4}
    best = sorted(rows, key=lambda r: order.get(str(r.get("direction")), 9))[0]
    return {
        "direction": best.get("direction") or "absent",
        "in_universe": True,
        "held_in_paper_books": held,
        "authority": best.get("authority"),
        "signal": best.get("signal"),
        "refusal_class": best.get("refusal_class"),
        "terminal_state": best.get("terminal_state"),
        "summary": str(best.get("why") or "")[:400] or None,
        "n_rows": len(rows),
        "rows": rows[:4],
    }


def paper_holdings() -> dict:
    """The paper books' current names, if they are CHEAPLY readable.

    "Cheaply" is the whole contract: this job will not replay a book to answer
    a colour column. Unreadable is `NOT_HELD` with the reason, never an empty
    set dressed as "we hold nothing".
    """
    try:
        from backend.services import paper_books as pb
    except Exception as exc:                                       # noqa: BLE001
        return {"state": NOT_HELD, "detail": f"{type(exc).__name__}: {exc}",
                "symbols": []}
    try:
        books = pb.load_books() if hasattr(pb, "load_books") else None
    except Exception as exc:                                       # noqa: BLE001
        return {"state": NOT_HELD, "detail": f"{type(exc).__name__}: {exc}",
                "symbols": []}
    if not books:
        return {"state": NOT_HELD,
                "detail": ("backend.services.paper_books exposes no cheap "
                           "holdings reader; this column is NOT_HELD rather "
                           "than an empty set pretending we hold nothing"),
                "symbols": []}
    syms: set[str] = set()
    try:
        for bk in (books.values() if isinstance(books, dict) else books):
            for h in (bk.get("holdings") or []) if isinstance(bk, dict) else []:
                s = str(h.get("symbol") or h.get("ticker") or "").upper()
                if s:
                    syms.add(s)
    except Exception as exc:                                       # noqa: BLE001
        return {"state": NOT_HELD, "detail": f"{type(exc).__name__}: {exc}",
                "symbols": []}
    return {"state": PRESENT, "detail": None, "symbols": sorted(syms)}


# ═══════════════════════════════════════════════ 3. the precursor check

def _state(present: bool, source: Path | str, detail: str, **extra) -> dict:
    return {"state": PRESENT if present else ABSENT, "source": str(source),
            "detail": detail, **extra}


def _not_held(source: Path | str, detail: str, **extra) -> dict:
    return {"state": NOT_HELD, "source": str(source), "detail": detail, **extra}


def precursor_insider(ticker: str, before: str, *, lookback_days: int,
                      path: Path | None = None) -> dict:
    """Form 4 CLUSTER: >= 2 distinct filers buying in the lookback, PIT.

    `observed_at_utc` is the anchor, not `event_time_utc`: a trade done on
    Monday and filed on Wednesday was not knowable on Tuesday.
    """
    import pandas as pd

    p = Path(path) if path is not None else INSIDER
    if not p.is_file():
        return _not_held(p, "no Form 4 event panel on this checkout")
    try:
        d = pd.read_parquet(p, columns=["symbol", "event_type", "observed_at_utc",
                                        "insider_cik", "insider_trans_code",
                                        "insider_dollar_value"])
    except Exception as exc:                                       # noqa: BLE001
        return _not_held(p, f"unreadable: {type(exc).__name__}: {exc}")
    cut = pd.Timestamp(before, tz="UTC")
    lo = cut - pd.Timedelta(days=int(lookback_days))
    d = d[d["symbol"].astype(str).str.upper() == ticker.upper()]
    if d.empty:
        return _state(False, p, "the panel carries no Form 4 row for this name",
                      n_filers=0, n_rows=0)
    obs = pd.to_datetime(d["observed_at_utc"], utc=True, errors="coerce")
    win = d[(obs < cut) & (obs >= lo)]
    buys = win[win["insider_trans_code"].astype(str).str.upper() == "P"]
    filers = sorted({str(x) for x in buys["insider_cik"].dropna().unique()})
    n_min = int(config.MISSED_OPP_INSIDER_CLUSTER_MIN)
    return _state(
        len(filers) >= n_min, p,
        f"{len(filers)} distinct open-market buyer(s) filed in the "
        f"{lookback_days} days before {before}; a cluster is >= {n_min}",
        n_filers=len(filers), n_rows=int(len(win)),
        dollars=_r(float(buys["insider_dollar_value"].fillna(0.0).sum()), 2),
        anchor="observed_at_utc (the FILING, not the trade)")


def precursor_analyst(ticker: str, before: str, *, lookback_days: int,
                      path: Path | None = None) -> tuple[dict, dict]:
    """`(revision_breadth, coverage_change)` from OUR OWN snapshot ledger.

    Two observations straddling the window or nothing. A delta manufactured
    from one observation is the failure `analyst_ledger.target_revisions`
    refuses by name, and it is refused here too.
    """
    from backend.services import analyst_ledger as al

    p = Path(path) if path is not None else ANALYST
    if not p.is_file():
        nh = _not_held(p, "no analyst snapshot ledger on this checkout")
        return nh, dict(nh)
    rows = [r for r in al.read(ticker.upper(), path=p)
            if str(r.get("observed_at") or "")[:10] < str(before)[:10]]
    if len(rows) < 2:
        nh = _not_held(
            p, f"the ledger holds {len(rows)} pre-move observation(s) for "
               f"{ticker.upper()}; a revision needs two. NOT_HELD, not ABSENT: "
               f"'we never looked' and 'we looked and it was flat' are "
               f"different answers")
        return nh, dict(nh)
    cut = date.fromisoformat(str(before)[:10])
    lo = cut.toordinal() - int(lookback_days)
    win = [r for r in rows
           if date.fromisoformat(str(r.get("observed_at"))[:10]).toordinal() >= lo]
    if len(win) < 2:
        nh = _not_held(p, f"{len(win)} observation(s) inside the "
                          f"{lookback_days}-day window; two are needed")
        return nh, dict(nh)
    first, last = win[0], win[-1]

    def _f(row, key):
        v = row.get(key)
        return None if v is None else float(v)

    t0, t1 = _f(first, "target_median"), _f(last, "target_median")
    n0, n1 = _f(first, "n_analysts"), _f(last, "n_analysts")
    thr = float(config.MISSED_OPP_REVISION_PCT)
    if t0 and t1:
        move = (t1 / t0 - 1.0) * 100.0
        rev = _state(abs(move) >= thr, p,
                     f"median target {t0:.2f} -> {t1:.2f} ({move:+.2f}%) over "
                     f"{len(win)} pre-move observations; the bar is "
                     f"{thr:.1f}%", delta_pct=_r(move, 3), n_obs=len(win))
    else:
        rev = _not_held(p, "no pre-move snapshot carries a median target")
    if n0 is not None and n1 is not None:
        cov = _state(abs(n1 - n0) >= float(config.MISSED_OPP_COVERAGE_MIN), p,
                     f"analyst count {n0:.0f} -> {n1:.0f} before the move",
                     delta=_r(n1 - n0, 2), n_obs=len(win))
    else:
        cov = _not_held(p, "no pre-move snapshot carries an analyst count")
    return rev, cov


def _panel(path: Path | None = None):
    import pandas as pd

    p = Path(path) if path is not None else NEWS_PANEL
    if not p.is_file():
        return None, p
    return pd.read_parquet(p, columns=["symbol", "entry_date", "first_seen_utc",
                                       "title", "body", "source"]), p


def precursor_news_volume(ticker: str, before: str, *, lookback_days: int,
                          panel=None, path: Path | None = None) -> dict:
    """A pre-move burst against the NAME'S OWN base rate, never an absolute count.

    Ten stories is a quiet week for AAPL and a klaxon for a micro-cap. The
    comparison is the symbol's own median count over equal-length windows
    across the whole panel.
    """
    import pandas as pd

    if panel is None:
        panel, path = _panel(path)
    if panel is None:
        return _not_held(path or NEWS_PANEL, "no news/return panel on this checkout")
    d = panel[panel["symbol"].astype(str).str.upper() == ticker.upper()]
    if d.empty:
        return _not_held(path or NEWS_PANEL,
                         f"the panel carries no row for {ticker.upper()} at "
                         f"all; its news volume is unmeasured, not zero")
    ed = pd.to_datetime(d["entry_date"], errors="coerce")
    cut = pd.Timestamp(str(before)[:10])
    lo = cut - pd.Timedelta(days=int(lookback_days))
    n_win = int(((ed >= lo) & (ed < cut)).sum())
    # the name's own base rate: rows per `lookback_days` across its history
    span = max(1.0, float((ed.max() - ed.min()).days or 1))
    base = float(len(d)) * float(lookback_days) / span
    mult = float(config.MISSED_OPP_NEWS_BURST_MULT)
    floor = int(config.MISSED_OPP_NEWS_BURST_MIN_ROWS)
    return _state(n_win >= floor and n_win >= mult * base, path or NEWS_PANEL,
                  f"{n_win} pre-move row(s) in {lookback_days} days against a "
                  f"base rate of {base:.1f}; a burst is >= {floor} rows AND "
                  f">= {mult:.1f}x the base",
                  n_rows=n_win, base_rate=_r(base, 3), n_rows_total=int(len(d)))


def precursor_typed_event(ticker: str, before: str, *, lookback_days: int,
                          root: Path | None = None) -> dict:
    """A NON-negligible typed event dated before the move, from L2's rows."""
    root = Path(root) if root is not None else TYPED_EVENTS
    if not root.is_dir():
        return _not_held(root, "no typed-event rows on this checkout")
    cut = str(before)[:10]
    lo = (date.fromisoformat(cut).toordinal() - int(lookback_days))
    hits, scanned = [], 0
    for f in sorted(root.glob("*.jsonl")):
        if f.name.endswith("_refusals.jsonl"):
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:                                      # noqa: BLE001
                continue
            scanned += 1
            tk = [str(x).upper() for x in (row.get("tickers") or [])]
            if ticker.upper() not in tk:
                continue
            dd = str(row.get("document_date") or "")[:10]
            if not dd or dd >= cut:
                continue
            try:
                if date.fromisoformat(dd).toordinal() < lo:
                    continue
            except ValueError:
                continue
            if str(row.get("magnitude_bucket") or "").upper() == "NEGLIGIBLE":
                continue
            hits.append({"event_type": row.get("event_type"),
                         "document_date": dd,
                         "magnitude_bucket": row.get("magnitude_bucket"),
                         "direction": row.get("direction")})
    return _state(bool(hits), root,
                  f"{len(hits)} non-negligible typed event(s) dated in the "
                  f"{lookback_days} days before {before} ({scanned} rows scanned)",
                  events=hits[:5], n_events=len(hits))


def precursor_search(ticker: str, before: str, *, path: Path | None = None) -> dict:
    p = Path(path) if path is not None else TRENDS_CACHE
    if not p.is_file():
        return _not_held(p, "no search-interest cache on this checkout; "
                            "`trends_sentiment.get_ticker_attention` is a LIVE "
                            "fetch and this job makes no network call")
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                                       # noqa: BLE001
        return _not_held(p, f"unreadable: {type(exc).__name__}: {exc}")
    row = (obj.get(ticker.upper()) if isinstance(obj, dict) else None)
    if not row:
        return _not_held(p, f"the cache holds no series for {ticker.upper()}")
    return _state(False, p, "a series exists and this job does not yet score "
                            "its pre-move slope; reported as ABSENT rather "
                            "than invented")


def precursor_short_interest(ticker: str, before: str,
                             path: Path | None = None) -> dict:
    p = Path(path) if path is not None else SHORT_INTEREST
    if not p.is_file():
        return _not_held(p, "no short-interest table on this checkout")
    return _state(False, p, "table present; no pre-move rule is declared for "
                            "it yet, so it is ABSENT rather than invented")


def precursor_supplier(ticker: str, before: str,
                       path: Path | None = None) -> dict:
    p = Path(path) if path is not None else SUPPLIER_GRAPH
    if not p.is_file():
        return _not_held(p, "no supplier/customer edge table on this checkout. "
                            "It is in the reader's vocabulary anyway: a reader "
                            "naming a class we cannot adjudicate is graded a "
                            "MISS, and the receipt says so")
    return _state(False, p, "edges present; no pre-move read-through rule is "
                            "declared yet")


def precursors(ticker: str, before: str, *, lookback_days: int | None = None,
               panel=None) -> dict:
    """The seven classes for one case, each with its state and its path."""
    lb = int(config.MISSED_OPP_PRECURSOR_LOOKBACK_DAYS if lookback_days is None
             else lookback_days)
    rev, cov = precursor_analyst(ticker, before, lookback_days=lb)
    out = {
        "insider_cluster": precursor_insider(ticker, before, lookback_days=lb),
        "revision_breadth": rev,
        "coverage_change": cov,
        "news_volume": precursor_news_volume(ticker, before, lookback_days=lb,
                                             panel=panel),
        "typed_event": precursor_typed_event(ticker, before, lookback_days=lb),
        "search_interest": precursor_search(ticker, before),
        "short_interest": precursor_short_interest(ticker, before),
        "supplier_readthrough": precursor_supplier(ticker, before),
    }
    out["_present"] = sorted(k for k, v in out.items()
                             if not k.startswith("_") and v["state"] == PRESENT)
    out["_not_held"] = sorted(k for k, v in out.items()
                              if not k.startswith("_") and v["state"] == NOT_HELD)
    out["_lookback_days"] = lb
    out["_pit"] = (f"every row is dated strictly before {before}, the move's "
                   f"first session")
    return out


# ═══════════════════════════════════════════════ 4. the paired read

SYSTEM = (
    "You are a markets analyst reading a FICTIONAL case file. The company is "
    "called [co]: its name and ticker have been removed. Every report below "
    "was published BEFORE the period you are asked about, and nothing after "
    "it is included.\n"
    "\n"
    "The question is ONE question: was this move foreseeable from information "
    "that existed beforehand?\n"
    "\n"
    "Reply with a single JSON object and NOTHING else. No prose, no code "
    "fence, no explanation outside the JSON. Respond in English only.\n"
    "\n"
    "The object has exactly these six fields:\n"
    '  "foreseeable"   one of "yes", "no".\n'
    '  "precursor_class"  EXACTLY ONE of these nine strings, and no other: '
    '"insider_cluster", "revision_breadth", "coverage_change", '
    '"news_volume", "typed_event", "search_interest", "short_interest", '
    '"supplier_readthrough", "none". Use "none" when nothing observable '
    "beforehand would have carried it.\n"
    '  "which_of_our_sources_would_have_carried_it"  a list of strings from '
    "that SAME nine-item list. It may be empty.\n"
    '  "confidence"    a number from 0.0 to 1.0: your probability that the '
    "precursor_class you named is the right one. Not your enthusiasm.\n"
    '  "one_sentence_mechanism"  one short sentence, at most 240 characters: '
    "how that precursor would have led to this move.\n"
    '  "reader_note"   one short string, at most 120 characters, or "".\n'
    "\n"
    "Example of the exact shape (the values are an example, not an answer):\n"
    '{"foreseeable": "yes", "precursor_class": "insider_cluster", '
    '"which_of_our_sources_would_have_carried_it": ["insider_cluster", '
    '"news_volume"], "confidence": 0.61, "one_sentence_mechanism": '
    '"three officers bought in size two weeks before the guidance raise.", '
    '"reader_note": ""}'
)

PROMPT = (
    "FICTIONAL CASE {case_id}\n"
    "Reports on [co] published on or before {before}:\n"
    "{digest}\n"
    "\n"
    "Over the {sub} trading sessions beginning {window_start}, [co] moved "
    "{direction} sharply against the market.\n"
    "\n"
    "Was it foreseeable from the reports above and from the kinds of data "
    "listed in your instructions? JSON only."
)

ANSWER_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["foreseeable", "precursor_class",
                 "which_of_our_sources_would_have_carried_it",
                 "confidence", "one_sentence_mechanism"],
    "properties": {
        "foreseeable": {"enum": ["yes", "no"]},
        "precursor_class": {"enum": list(PRECURSOR_CLASSES)},
        "which_of_our_sources_would_have_carried_it": {
            "type": "array", "items": {"enum": list(PRECURSOR_CLASSES)}},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "one_sentence_mechanism": {"type": "string", "maxLength": 240},
        "reader_note": {"type": "string", "maxLength": 120},
    },
}


def prompt_fingerprint() -> dict:
    """The sha256 of what is actually sent, plus a proof the schema is in it.

    `schema_in_system` is the 2026-09-13 lesson made executable: if a later
    edit moves the field list or the nine-item enum out of `SYSTEM`, this flag
    goes FALSE on the receipt instead of the refusal rate going up three weeks
    later.
    """
    req = list(ANSWER_SCHEMA["required"])
    return {
        "system_sha256": hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(ANSWER_SCHEMA, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")).hexdigest(),
        "schema_in_system": (all(f'"{f}"' in SYSTEM for f in req)
                             and all(f'"{c}"' in SYSTEM
                                     for c in PRECURSOR_CLASSES)),
        "required_fields": req,
        "enum": list(PRECURSOR_CLASSES),
        "temperature": 0.0,
        "max_tokens": int(config.MISSED_OPP_MAX_TOKENS),
    }


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_answer(text: str) -> tuple[dict | None, list[str]]:
    """`(answer, reasons)`. Every reason NAMES the field it is about."""
    m = _JSON_RE.search(text or "")
    if not m:
        return None, ["no JSON object in the reply"]
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return None, [f"json.loads: {exc}"]
    if not isinstance(obj, dict):
        return None, [f"root: expected an object, got {type(obj).__name__}"]
    bad = []
    for f in ANSWER_SCHEMA["required"]:
        if f not in obj:
            bad.append(f"missing field {f!r}")
    if bad:
        return None, bad
    if str(obj["foreseeable"]).lower() not in ("yes", "no"):
        bad.append(f"foreseeable: {obj['foreseeable']!r} is not yes/no")
    cls = str(obj["precursor_class"]).strip().lower()
    if cls not in PRECURSOR_CLASSES:
        bad.append(f"precursor_class: {cls!r} is not one of the nine")
    src = obj["which_of_our_sources_would_have_carried_it"]
    if not isinstance(src, list):
        bad.append("which_of_our_sources_would_have_carried_it: not a list")
        src = []
    try:
        conf = float(obj["confidence"])
    except (TypeError, ValueError):
        bad.append(f"confidence: {obj['confidence']!r} is not a number")
        conf = None
    if conf is not None and not (0.0 <= conf <= 1.0):
        bad.append(f"confidence: {conf} is outside [0, 1]")
    if bad:
        return None, bad
    return {
        "foreseeable": str(obj["foreseeable"]).lower(),
        "precursor_class": cls,
        "which_of_our_sources_would_have_carried_it": [
            str(s).strip().lower() for s in src
            if str(s).strip().lower() in PRECURSOR_CLASSES],
        "confidence": float(conf),
        "one_sentence_mechanism": str(obj["one_sentence_mechanism"])[:240],
        "reader_note": str(obj.get("reader_note") or "")[:120],
    }, []


def _name_tokens() -> tuple[dict, str]:
    """`(ticker -> distinctive name tokens, the source that produced them)`.

    CRSP first (the same map X_anon_gap masks with), the issuer CSV second.
    Under-masking is the failure that matters, so a missing map is reported,
    not silently treated as "nothing to mask".
    """
    try:
        from scripts import r7_news_representation as r7
        return r7.company_name_map(), "crsp__stocknames_v2 (r7.company_name_map)"
    except Exception:                                              # noqa: BLE001
        pass
    p = REPO / "backend" / "data" / "news_entities" / "issuers.csv"
    if not p.is_file():
        return {}, f"NONE — neither CRSP stocknames nor {p.name} is readable"
    import csv

    from scripts.r7_news_representation import (_GENERIC_NAME_TOKENS,  # noqa
                                                tokenise)
    out: dict[str, set] = {}
    with p.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            sym = str(row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            names = [row.get("primary_name") or ""]
            names += str(row.get("aliases") or "").split("|")
            toks = set()
            for nm in names:
                toks |= {t for t in tokenise(nm)
                         if len(t) > 2 and t not in _GENERIC_NAME_TOKENS}
            if toks:
                out[sym] = toks
    return out, f"news_entities/issuers.csv ({len(out)} issuers)"


def build_digest(ticker: str, before: str, *, panel=None, name_tokens=None,
                 lookback_days: int | None = None, max_rows: int | None = None,
                 max_chars: int | None = None) -> dict:
    """One MASKED, DATED digest of the pre-move corpus rows for a name.

    PIT by construction: `entry_date < before`, where `before` is the move's
    FIRST session. The masking is `r7_news_representation.mask_company` over
    `tokenise` — the SAME function `night_x_anonymisation_gap` and
    `night_scenario_gym` mask with, so a digest here and a digest there hide
    the same things. Dates are NOT shifted: the question is about a dated
    window, and the gym shifts dates only because its cases are fiction.
    """
    import pandas as pd

    from scripts.r7_news_representation import CO_TOKEN, mask_company, tokenise

    lb = int(config.MISSED_OPP_PRECURSOR_LOOKBACK_DAYS if lookback_days is None
             else lookback_days)
    max_rows = int(config.MISSED_OPP_DIGEST_ROWS if max_rows is None else max_rows)
    max_chars = int(config.MISSED_OPP_DIGEST_CHARS if max_chars is None
                    else max_chars)
    if panel is None:
        panel, _ = _panel()
    if panel is None:
        return {"digest": "", "n_rows": 0, "masked_tokens": 0,
                "refused": "NO_PANEL"}
    d = panel[panel["symbol"].astype(str).str.upper() == ticker.upper()].copy()
    if d.empty:
        return {"digest": "", "n_rows": 0, "masked_tokens": 0,
                "refused": "NO_ROWS_FOR_SYMBOL"}
    d["_ed"] = pd.to_datetime(d["entry_date"], errors="coerce")
    cut = pd.Timestamp(str(before)[:10])
    d = d[(d["_ed"] < cut) & (d["_ed"] >= cut - pd.Timedelta(days=lb))]
    d = d.sort_values("_ed").tail(max_rows)
    if d.empty:
        return {"digest": "", "n_rows": 0, "masked_tokens": 0,
                "refused": "NO_PRE_MOVE_ROWS"}
    toks = set((name_tokens or {}).get(ticker.upper()) or set())
    lines, masked = [], 0
    for _, row in d.iterrows():
        raw = f"{row.get('title') or ''} . {row.get('body') or ''}"
        tk = tokenise(raw)
        mk = mask_company(tk, ticker, toks)
        masked += sum(1 for x in mk if x == CO_TOKEN)
        text = " ".join(mk)[:max_chars]
        lines.append(f"- {pd.Timestamp(row['_ed']).date().isoformat()}: {text}")
    return {"digest": "\n".join(lines), "n_rows": int(len(d)),
            "masked_tokens": int(masked),
            "any_mask": masked > 0, "refused": None}


def grade(answer: dict | None, present: list[str]) -> dict:
    """Did the reader name a class step 3 found PRESENT?

    `none` is a HIT when nothing was PRESENT — a reader that correctly says
    "nothing on our disk carried this" is right, and scoring that as a miss
    would teach the opposite of the lesson.
    """
    if not answer:
        return {"hit": None, "why": "no parseable answer"}
    cls = answer["precursor_class"]
    if cls == "none":
        return {"hit": not present,
                "why": (f"said none; PRESENT set is {present or '[]'}")}
    return {"hit": cls in present,
            "why": f"said {cls}; PRESENT set is {present or '[]'}"}


def mcnemar(rows: list[dict], a: str, b: str) -> dict:
    """Exact binomial McNemar over the cases BOTH readers answered.

    Paired, because that is the whole design: the readers see the same digest,
    so the only difference is the reader. Discordant pairs are the evidence;
    concordant ones carry none.
    """
    from math import comb

    both = [r for r in rows
            if (r.get(a) or {}).get("hit") is not None
            and (r.get(b) or {}).get("hit") is not None]
    n01 = sum(1 for r in both if not r[a]["hit"] and r[b]["hit"])
    n10 = sum(1 for r in both if r[a]["hit"] and not r[b]["hit"])
    n = n01 + n10
    if n == 0:
        p = None
        note = ("no discordant pair: the readers agreed on every case they "
                "both answered, so this test has nothing to weigh")
    else:
        k = min(n01, n10)
        tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
        p = min(1.0, 2.0 * tail)
        note = None
    return {"n_paired": len(both), "n_only_" + b: n01, "n_only_" + a: n10,
            "p_exact": _r(p, 6), "note": note,
            "test": "exact binomial McNemar on discordant pairs, two-sided"}


def brier(rows: list[dict], reader: str) -> dict:
    """Brier of the reader's OWN stated confidence against its hits."""
    vals = [(float(r[reader]["confidence"]), 1.0 if r[reader]["hit"] else 0.0)
            for r in rows
            if (r.get(reader) or {}).get("hit") is not None
            and (r.get(reader) or {}).get("confidence") is not None]
    if not vals:
        return {"brier": None, "n": 0,
                "note": "no graded answer carried a confidence"}
    s = sum((c - o) ** 2 for c, o in vals) / len(vals)
    base = sum(o for _, o in vals) / len(vals)
    return {"brier": _r(s, 6), "n": len(vals),
            "hit_rate": _r(base, 4),
            "brier_of_always_predicting_the_base_rate": _r(base * (1 - base), 6),
            "note": ("a Brier above the base-rate column means the stated "
                     "confidence is worse than a constant")}


# ═══════════════════════════════════════════════════════ the readers

class ReaderRefused(RuntimeError):
    """The reader is not answering. A property of the RUN, not of a case."""


def ask_reader(text: str, backend: str, *, max_tokens: int | None = None
               ) -> tuple[dict | None, str, dict, str | None]:
    """One completion. `(answer, class_or_ok, usage, why)` — never raises.

    A `LanguageRefused` reply is REFUSED, not repaired and not retried: the
    language pin lives in the provider layer and a repaired reply is a reply
    whose receipt is wrong (CLAUDE.md, the DeepSeek lesson).
    """
    from backend.services import free_inference as fi
    from backend.services.model_provider import LanguageRefused, ProviderRefusal

    mt = int(config.MISSED_OPP_MAX_TOKENS if max_tokens is None else max_tokens)
    try:
        rep = fi.complete(backend, text, system=SYSTEM, max_tokens=mt,
                          temperature=0.0, purpose=PURPOSE)
    except LanguageRefused as exc:
        return None, "REFUSED_LANGUAGE", {"tokens_in": 0, "tokens_out": 0}, str(exc)
    except ProviderRefusal as exc:
        return None, "PENDING_MODEL", {"tokens_in": 0, "tokens_out": 0}, str(exc)
    except Exception as exc:                                       # noqa: BLE001
        return None, "PENDING_MODEL", {"tokens_in": 0, "tokens_out": 0}, \
            f"{type(exc).__name__}: {exc}"
    usage = {"tokens_in": int(getattr(rep, "tokens_in", 0) or 0),
             "tokens_out": int(getattr(rep, "tokens_out", 0) or 0),
             "model": getattr(rep, "model", None)}
    ans, reasons = parse_answer(getattr(rep, "text", "") or "")
    if ans is None:
        return None, "REFUSED_SCHEMA", usage, "; ".join(reasons[:3])
    return ans, "ok", usage, None


def paid_leg_intent(backend_flag: str | None, env: dict | None = None) -> dict:
    """Is the DeepSeek leg allowed to run, and if not, WHY — by name.

    The night queue launches every job with NO per-job CLI arguments, so a
    paid leg switched only by `--backend` can never run in the queue. Both
    conditions are environment conditions; `--backend deepseek` states the same
    intent explicitly for a hand run and is NOT a way around the key check.

    The VALUE of the key is never read and never printed. Presence of the NAME
    is the whole test.
    """
    env = os.environ if env is None else env
    asked = (backend_flag or "").lower() in ("deepseek", "both")
    paid_ok = str(env.get(PAID_OK_ENV, "")).strip() == "1"
    has_key = bool(str(env.get(KEY_ENV, "")).strip())
    if not (asked or paid_ok):
        why = (f"REFUSED — {PAID_OK_ENV} not set (and no --backend deepseek). "
               f"The local leg runs; the paid leg does not.")
    elif not paid_ok:
        why = (f"REFUSED — --backend deepseek was asked for but {PAID_OK_ENV} "
               f"is not 1. The env gate is the switch the night queue can "
               f"reach; a flag alone is not enough.")
    elif not has_key:
        why = (f"REFUSED — no {KEY_ENV} in env. The name is checked; the value "
               f"is never read and never printed.")
    else:
        why = None
    return {
        "asked_by_flag": asked,
        f"{PAID_OK_ENV}_set": paid_ok,
        f"{KEY_ENV}_present": has_key,
        "value_read": False,
        "run": why is None,
        "refused": why,
        "why_env_not_flag": (
            "scripts.night_factory launches every job with NO per-job CLI "
            "arguments, so a paid leg switched only by --backend can never run "
            "in the night queue"),
    }


# ═══════════════════════════════════════════════════════ the job

def _spend(since: str, *, path: Path | None = None) -> dict:
    from scripts.night_l2_typed_events import spend_from_ledger
    return spend_from_ledger(since, purpose=PURPOSE, path=path)


def _balance(label: str) -> dict:
    """A provider balance read. The GROUND TRUTH; our telemetry is not."""
    try:
        from backend.services import deepseek_balance as bal
        row = bal.snapshot(f"{JOB}_{label}")
        return {"total_usd": _r(row.get("total_usd"), 4),
                "read_at": row.get("read_at"), "label": label, "error": None}
    except Exception as exc:                                       # noqa: BLE001
        return {"total_usd": None, "read_at": None, "label": label,
                "error": f"{type(exc).__name__}: {exc}"}


def unpriced_calls(since_utc: str, *, path: Path | None = None) -> dict:
    """Rows for THIS run whose `cost_usd` is None, and the models that wrote them.

    `cost_usd is None` means the served model id is not in
    `config.LLM_PRICE_PER_MTOK`. Every total that sums it adds 0.0, so the cap
    over it is a lower bound of ZERO — which is how 424 rows once cost $0.21 of
    real balance under a $1.00 cap reading $0.00. An unpriced call is a CAP
    BREACH by definition, not a rounding error.
    """
    from backend.services import llm_telemetry as tel

    cut = str(since_utc or "")[:19]
    models: dict[str, int] = {}
    n = 0
    for row in tel.read_calls(path=path):
        if str(row.get("purpose") or "") != PURPOSE:
            continue
        if str(row.get("ts") or "")[:19] < cut:
            continue
        if row.get("cost_usd") is None:
            n += 1
            m = str(row.get("model") or "<no model id>")
            models[m] = models.get(m, 0) + 1
    return {"n_unpriced": n, "models": models, "since_utc": since_utc,
            "purpose": PURPOSE,
            "why_it_is_a_breach": (
                "an unpriced row is summed as 0.0, so a cap over it is a lower "
                "bound of zero. Price the model id before running this again.")}


def J2_missed_opportunity(*, smoke: bool = False, run: int = 1,   # noqa: N802
                          backend: str | None = None,
                          max_usd: float | None = None,
                          top_k: int | None = None,
                          bars=None, env: dict | None = None,
                          decisions_root: Path | None = None,
                          ledger_path: Path | None = None,
                          local_ask=None, paid_ask=None) -> dict:
    """One receipt: the moves, what we did, the precursors, both readers, the bill."""
    t0 = time.time()
    since = _now()
    cap_usd = float(config.MISSED_OPP_MAX_USD if max_usd is None else max_usd)
    soft = float(config.MISSED_OPP_SOFT_STOP_USD)
    k = int(config.MISSED_OPP_TOP_K if top_k is None else top_k)
    if smoke:
        k = min(k, int(config.MISSED_OPP_SMOKE_TOP_K))

    paid = paid_leg_intent(backend, env)
    base = {
        "job": JOB, "licence": LICENCE, "run": int(run), "run_date": RUN_DATE,
        "smoke": bool(smoke),
        "stage": "pnl",
        "queue_stage": "screen",
        "queue_stage_note": (
            "'screen' is this job's place in the night QUEUE. Its STAGE "
            "CONTRACT stamp is `pnl`, because it reads the day decision "
            "contract — the latest artefact in the chain — and no stage may "
            "read one produced by a later one."),
        "question": (
            "Murat, 2026-09-21: every night, find the largest market moves "
            "AEGIS did NOT capture, and for each ask whether the information "
            "was observable beforehand. Then make that the ONE paid question "
            "of the night, asked of BOTH readers on the SAME cases, so the "
            "paid model has to earn its cost."),
        "prompt": prompt_fingerprint(),
        "deepseek_leg": paid["refused"] or "ARMED",
        "paid_leg_gate": paid,
        "cost_cap": {
            "hard_max_usd": cap_usd, "soft_stop_usd": soft,
            "config_keys": ["MISSED_OPP_MAX_USD", "MISSED_OPP_SOFT_STOP_USD"],
            "why_two": ("the soft stop is where this job stops asking; the "
                        "hard cap is the _RunCap backstop for billing that "
                        "lands after the last read. One number would be "
                        "either too tight to finish or too loose to bind"),
            "purpose_read": PURPOSE,
            "checked": "BEFORE every submission, never refunded after",
            "run_level_refusals": list(CAP_REFUSALS),
        },
        "precursor_classes": list(PRECURSOR_CLASSES),
        "unadjudicable_classes": [c for c in PRECURSOR_CLASSES
                                  if c not in ADJUDICABLE and c != "none"],
    }

    # ── 1. the moves ────────────────────────────────────────────────────────
    try:
        if bars is None:
            from backend.services import paper_books as pb
            bars = pb.load_bars()
        ranked = rank_missed(bars, top_k=k)
    except Exception as exc:                                       # noqa: BLE001
        why = (f"{REFUSED_NO_BARS}: {type(exc).__name__}: {exc}. A move list "
               f"from an empty fetch reports nothing missed and reads as full "
               f"coverage.")
        return {**base, "top_missed": [], "paired": None,
                "spend": _spend(since, path=ledger_path),
                "headline": why, "verdict": why,
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    moves = ranked["moves"]
    base["screen"] = ranked["screen"]

    # ── 2. what AEGIS did ───────────────────────────────────────────────────
    contracts = _contract_rows(ranked["calendar"], decisions_root)
    base["contracts"] = {k2: v for k2, v in contracts.items() if k2 != "by_ticker"}
    base["contracts"]["n_names_with_a_row"] = len(contracts["by_ticker"])
    holdings = paper_holdings()
    base["paper_holdings"] = {"state": holdings["state"],
                              "detail": holdings["detail"],
                              "n_symbols": len(holdings["symbols"])}
    held = set(holdings["symbols"])

    # ── 3. the precursor check ──────────────────────────────────────────────
    panel, panel_path = _panel()
    base["news_panel"] = {"path": str(panel_path),
                          "present": panel is not None,
                          "n_rows": (None if panel is None else int(len(panel)))}
    name_tokens, tok_source = _name_tokens()
    base["masking"] = {
        "function": ("scripts.r7_news_representation.mask_company over "
                     "tokenise — the SAME function night_x_anonymisation_gap "
                     "and night_scenario_gym mask with"),
        "name_token_source": tok_source,
        "n_tickers_with_tokens": len(name_tokens),
        "dates_shifted": False,
        "dates_why": ("the question is about a DATED window; the gym shifts "
                      "dates only because its cases are fiction"),
    }

    cases = []
    for m in moves:
        pre = precursors(m["ticker"], m["window_start"], panel=panel)
        dig = build_digest(m["ticker"], m["window_start"], panel=panel,
                           name_tokens=name_tokens)
        cases.append({
            **m,
            "aegis": what_aegis_did(m["ticker"], contracts, held),
            "precursors": {k2: v for k2, v in pre.items() if not k2.startswith("_")},
            "precursors_present": pre["_present"],
            "precursors_not_held": pre["_not_held"],
            "digest": dig,
        })

    # ── 4. the paired read ──────────────────────────────────────────────────
    askable = [c for c in cases if c["digest"]["n_rows"] > 0]
    legs: dict[str, dict] = {}
    rows: list[dict] = []

    local_fn = local_ask or (lambda text: ask_reader(text, "local_gguf"))
    legs["local_gguf"] = {"backend": "local_gguf", "refused": None,
                          "metered": False, "n_asked": 0, "n_ok": 0,
                          "refusals": {}}

    cap = None
    cap_block = None
    paid_stop = None
    legs["deepseek"] = {"backend": "deepseek", "refused": paid["refused"],
                        "metered": True, "n_asked": 0, "n_ok": 0,
                        "refusals": {}}
    # THE LEDGER COMES BEFORE THE FIRST SUBMISSION. A cap that reads a ledger
    # it cannot see is not a loose cap, it is NO cap: its total is a lower
    # bound of zero and it can never bind. MEASURED 2026-09-19 — N9's first
    # probe ran fifteen minutes under a $1.00 cap reading $0.00 the whole time.
    if paid["run"]:
        from scripts.night_n9_library_autopsy import ledger_writable
        led_ok = ledger_writable(ledger_path)
        base["ledger"] = led_ok
        if not led_ok["ok"]:
            paid["run"] = False
            paid["refused"] = (
                f"{REFUSED_NO_LEDGER}: {led_ok['detail']} This job will not "
                f"spend under a cap that cannot see what it is spending.")
            base["deepseek_leg"] = paid["refused"]
            base["paid_leg_gate"] = paid
            legs["deepseek"]["refused"] = paid["refused"]
    else:
        base["ledger"] = {"ok": True, "reason": None,
                          "checked": ("skipped: the paid leg is refused, so "
                                      "no cap has to bind")}

    if paid["run"]:
        from scripts.night_l2_typed_events import _RunCap
        # `purpose=PURPOSE` IS THE FIX OF 2026-09-21 AND IT IS NOT OPTIONAL.
        # Left off, `_RunCap.refresh()` falls back to `spend_from_ledger`'s
        # default — L2's purpose — and the cap spends the night summing another
        # job's rows: $0.013238 read against $10.047856 written, same file.
        cap = _RunCap(cap_usd, backend="deepseek", since_utc=since,
                      refresh_every=int(config.MISSED_OPP_FLUSH_EVERY),
                      ledger_path=ledger_path, purpose=PURPOSE)
    paid_fn = paid_ask or (lambda text: ask_reader(text, "deepseek"))

    balance_before = _balance("before") if paid["run"] else {
        "total_usd": None, "read_at": None, "label": "before",
        "error": "no paid call was made; no balance read was taken"}

    agreement_done = False
    for idx, c in enumerate(askable):
        case_id = hashlib.sha256(
            f"{c['ticker']}|{c['window_start']}|{c['window_end']}".encode()
        ).hexdigest()[:12]
        text = PROMPT.format(case_id=case_id, before=c["window_start"],
                             digest=c["digest"]["digest"],
                             sub=int(config.MISSED_OPP_SUBWINDOW_SESSIONS),
                             window_start=c["window_start"],
                             direction=("UP" if c["direction"] == "UP"
                                        else "DOWN"))
        row = {"case_id": case_id, "ticker": c["ticker"],
               "window_start": c["window_start"], "window_end": c["window_end"],
               "excess_pct": c["excess_pct"],
               "present": c["precursors_present"]}

        legs["local_gguf"]["n_asked"] += 1
        ans, cls, usage, why = local_fn(text)
        if ans is None:
            legs["local_gguf"]["refusals"][cls] = \
                legs["local_gguf"]["refusals"].get(cls, 0) + 1
            row["local_gguf"] = {"hit": None, "refused": cls, "why": why}
        else:
            legs["local_gguf"]["n_ok"] += 1
            g = grade(ans, c["precursors_present"])
            row["local_gguf"] = {**ans, **g, "usage": usage}

        if paid["run"] and paid_stop is None and cap is not None:
            # `may_submit()` FIRST, because it is what re-reads the ledger on
            # the flush schedule. Asking `spend_now()` before it compares the
            # soft stop against a STALE total and the stop never fires — the
            # same shape as a cap watching the wrong meter, one level down.
            fits = cap.may_submit()
            if cap.spend_now() >= soft:
                paid_stop = (f"SOFT_STOP at ${soft:.2f}: {idx} of "
                             f"{len(askable)} case(s) asked; the hard cap "
                             f"${cap_usd:.2f} was never reached")
            elif not fits:
                paid_stop = (f"CAP at ${cap_usd:.2f}: one more row does not "
                             f"fit under it")
        if paid["run"] and paid_stop is None:
            if cap is not None:
                cap.charge()
            legs["deepseek"]["n_asked"] += 1
            ans, cls, usage, why = paid_fn(text)
            if ans is None:
                legs["deepseek"]["refusals"][cls] = \
                    legs["deepseek"]["refusals"].get(cls, 0) + 1
                row["deepseek"] = {"hit": None, "refused": cls, "why": why}
            else:
                legs["deepseek"]["n_ok"] += 1
                g = grade(ans, c["precursors_present"])
                row["deepseek"] = {**ans, **g, "usage": usage}
            # THE FIRST FLUSH IS WHERE THE TWO READERS ARE COMPARED. A
            # disagreement is a property of the WIRING, so it is true at the
            # first flush or not at all and a later read cannot absolve it.
            if cap is not None and not agreement_done:
                agreement_done = True
                cap_block = cap.agreement(_spend(since, path=ledger_path))
                print(f"cap-reader agreement: CAP ${cap_block['cap_usd']:.6f} "
                      f"over {cap_block['cap_calls']} call(s) [purpose "
                      f"{cap_block['cap_purpose']}] vs RECEIPT "
                      f"${cap_block['receipt_usd']:.6f} over "
                      f"{cap_block['receipt_calls']} call(s) [purpose "
                      f"{cap_block['receipt_purpose']}] -> "
                      f"{'AGREE' if cap_block['agree'] else 'DISAGREE'}",
                      flush=True)
                if not cap_block["agree"]:
                    paid_stop = (f"{REFUSED_CAP_READER_DISAGREES}: cap read "
                                 f"${cap_block['cap_usd']:.6f} over "
                                 f"{cap_block['cap_calls']} call(s) while the "
                                 f"receipt read ${cap_block['receipt_usd']:.6f} "
                                 f"over {cap_block['receipt_calls']}")
                    rows.append(row)
                    continue
                u = unpriced_calls(since, path=ledger_path)
                if u["n_unpriced"]:
                    paid_stop = (f"{REFUSED_UNPRICED_CALL}: {u['models']} — "
                                 f"{u['why_it_is_a_breach']}")
        rows.append(row)

    # the readers' answers go BACK ONTO the case, so a reader of the receipt
    # sees ticker, window, excess, what we did, the precursors and both
    # answers in ONE object rather than having to join two lists by hand.
    for c, r in zip(askable, rows):
        c["readers"] = {k2: r.get(k2) for k2 in ("local_gguf", "deepseek")}
        c["case_id"] = r["case_id"]
    for c in cases:
        c.setdefault("case_id", None)
        c.setdefault("readers", {
            "local_gguf": None, "deepseek": None,
            "why": "no pre-move corpus row, so neither reader was asked"})
        # the digest TEXT is not on the receipt: it is the corpus, not a
        # finding, and it would make the file unreadable. Its shape is.
        c["digest"] = {k2: v for k2, v in c["digest"].items() if k2 != "digest"}

    balance_after = _balance("after") if paid["run"] else {
        "total_usd": None, "read_at": None, "label": "after",
        "error": "no paid call was made; no balance read was taken"}
    spend = _spend(since, path=ledger_path)
    unpriced = unpriced_calls(since, path=ledger_path)

    def _hit_rate(reader: str) -> dict:
        graded = [r for r in rows if (r.get(reader) or {}).get("hit") is not None]
        hits = sum(1 for r in graded if r[reader]["hit"])
        return {"n_graded": len(graded), "n_hit": hits,
                "hit_rate": _r(hits / len(graded), 4) if graded else None}

    local_rate, paid_rate = _hit_rate("local_gguf"), _hit_rate("deepseek")
    paired = {
        "local_gguf": {**local_rate, "brier": brier(rows, "local_gguf")},
        "deepseek": {**paid_rate, "brier": brier(rows, "deepseek")},
        "mcnemar": mcnemar(rows, "local_gguf", "deepseek"),
        "n_cases": len(cases), "n_askable": len(askable),
        "design": ("the SAME masked digest, the SAME frozen schema, the SAME "
                   "cases, graded against the SAME deterministic PRESENT set. "
                   "The only thing that differs is the reader"),
    }

    unforeseeable = [
        c["ticker"] for c, r in zip(askable, rows)
        if not c["precursors_present"]
        and str((r.get("local_gguf") or {}).get("foreseeable")) == "no"
        and str((r.get("deepseek") or {}).get("foreseeable")) == "no"]

    # the curriculum: a class PRESENT on >= N missed names is a hypothesis
    counts: dict[str, int] = {}
    for c in cases:
        for cl in c["precursors_present"]:
            counts[cl] = counts.get(cl, 0) + 1
    floor = int(config.MISSED_OPP_CURRICULUM_MIN_NAMES)
    curriculum = [
        {"precursor_class": cl, "n_missed_names": n,
         "experiment": _CURRICULUM.get(
             cl, f"score {cl} as a standalone selector on the trailing "
                 f"{config.MISSED_OPP_WINDOW_SESSIONS} sessions against a "
                 f"matched-date control, as its own PRODUCT_EXPERIMENT book")}
        for cl, n in sorted(counts.items(), key=lambda kv: -kv[1]) if n >= floor]

    n_captured = sum(1 for c in cases
                     if str(c["aegis"]["direction"]).upper() in ("BUY", "PROBE"))
    n_absent = sum(1 for c in cases if not c["aegis"]["in_universe"])
    diff = (None if (local_rate["hit_rate"] is None or paid_rate["hit_rate"] is None)
            else _r(paid_rate["hit_rate"] - local_rate["hit_rate"], 4))
    p = paired["mcnemar"]["p_exact"]
    if diff is None:
        closing = (f"NO_IMPROVEMENT: the paid leg produced no graded answer "
                   f"({base['deepseek_leg']}), so there is no paired "
                   f"difference to measure. The local leg graded "
                   f"{local_rate['n_graded']} case(s) at hit rate "
                   f"{local_rate['hit_rate']}.")
    elif p is not None and p <= float(config.MISSED_OPP_PAIRED_ALPHA):
        closing = (f"BELIEF_CHANGED: deepseek {paid_rate['hit_rate']} vs "
                   f"local_gguf {local_rate['hit_rate']} on "
                   f"{paired['mcnemar']['n_paired']} paired case(s), McNemar "
                   f"exact p={p}. The paid reader is measurably "
                   f"{'better' if diff > 0 else 'worse'} on THIS night's cases.")
    else:
        closing = (f"NO_IMPROVEMENT: deepseek {paid_rate['hit_rate']} vs "
                   f"local_gguf {local_rate['hit_rate']} "
                   f"(diff {diff:+}), McNemar exact p={p} against alpha "
                   f"{config.MISSED_OPP_PAIRED_ALPHA}"
                   f"{' — ' + paired['mcnemar']['note'] if paired['mcnemar']['note'] else ''}"
                   f". One night is one night: the standing question is whether "
                   f"the difference accumulates across nights, not whether it "
                   f"cleared a threshold tonight.")

    lower_bound = bool(unpriced["n_unpriced"])
    return {
        **base,
        "top_missed": cases,
        "paired": paired,
        "rows": rows,
        "legs": legs,
        "unforeseeable_count": len(unforeseeable),
        "unforeseeable": unforeseeable,
        "unforeseeable_definition": (
            "no precursor class was PRESENT and BOTH readers answered "
            "foreseeable=no. It is the honest residual, not a failure"),
        "curriculum": curriculum,
        "curriculum_floor_names": floor,
        "spend": spend,
        "llm_spend_usd": spend.get("usd"),
        "spend_is_a_lower_bound": lower_bound,
        "spend_caveat": (
            (f"UNPRICED CALLS: {unpriced['models']}. Every total that sums "
             f"them treats them as 0.0, so `llm_spend_usd` is a LOWER BOUND "
             f"and the real figure is the provider's balance.")
            if lower_bound else None),
        "cap_block": (cap.block() if cap is not None else {
            "max_usd": cap_usd, "backend": "none", "metered": False,
            "purpose": PURPOSE, "first_flush_agreement": None,
            "first_flush_agreement_note": (
                "no metered call was made, so the two readers of the ledger "
                "had nothing to disagree about")}),
        "paid_stop": paid_stop,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "balance_delta_usd": (
            _r(balance_before["total_usd"] - balance_after["total_usd"], 4)
            if (balance_before.get("total_usd") is not None
                and balance_after.get("total_usd") is not None) else None),
        "balance_is_the_ground_truth": (
            "our telemetry prices what it recognises; the provider's balance "
            "prices what it billed. When they disagree the balance is right."),
        "headline": (
            f"{len(cases)} largest unmatched move(s) over "
            f"{base['screen']['window_sessions']} sessions "
            f"(best {base['screen']['subwindow_sessions']}-session |excess vs "
            f"SPY|, floor ${base['screen']['dollar_vol_floor']:,.0f}); "
            f"{n_absent} not in the universe, {n_captured} carried a "
            f"BUY/PROBE; {len(unforeseeable)} with no precursor and both "
            f"readers saying unforeseeable; local {local_rate['hit_rate']} vs "
            f"deepseek {paid_rate['hit_rate']} hit rate; "
            f"${float(spend.get('usd') or 0.0):.4f}"
            f"{'+ (LOWER BOUND)' if lower_bound else ''} of ${cap_usd:.2f}"),
        "verdict": closing,
        "next_test": (
            "each curriculum line is a hypothesis, not a finding: it enters as "
            "its own PRODUCT_EXPERIMENT book with a matched-date control, "
            "never as a weight folded into arena_composite (CLAUDE.md, THE "
            "BOTTLENECK)."),
        "elapsed_s": round(time.time() - t0, 1),
        "written_utc": _now(),
    }


#: one sentence per class, naming the EXPERIMENT and not the observation.
_CURRICULUM = {
    "insider_cluster": (
        "score a >=2-filer open-market buy cluster as a standalone entry "
        "signal at 5/21/63 sessions against a matched-date control drawn from "
        "names with one filer, as its own PRODUCT_EXPERIMENT book"),
    "news_volume": (
        "score a >=2x-own-base-rate news burst as an entry signal at 5/21 "
        "sessions against a matched-date, matched-dollar-volume control — the "
        "burst is confounded with liquidity and the control has to hold it"),
    "typed_event": (
        "score the typed-event direction prior as a standalone selector at 5 "
        "and 21 sessions, with the L2 vocabulary version on the receipt, "
        "against the same names on days carrying no typed event"),
    "revision_breadth": (
        "back-fill the analyst snapshot ledger to two observations per name "
        "before scoring anything: today it holds too few rows to answer, and "
        "a revision manufactured from one observation is not a revision"),
    "coverage_change": (
        "the same back-fill: a coverage delta needs two dated snapshots, and "
        "NOT_HELD is the honest answer until the ledger carries them"),
    "search_interest": (
        "land a dated search-interest cache first — the live fetch is not PIT "
        "and this job makes no network call; then score the pre-move slope"),
    "short_interest": (
        "land a dated short-interest table first; until then the class is in "
        "the reader's vocabulary and unadjudicable, which the receipt says"),
    "supplier_readthrough": (
        "build the supplier/customer edge table the 09-21 Sonnet read ranked "
        "first and left OPEN; the class is askable today and unadjudicable"),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--backend", default=None,
                    choices=("local_gguf", "deepseek", "both"),
                    help="a HAND-RUN switch. The night queue passes no flags, "
                         "so the paid leg's real gate is the environment "
                         f"({PAID_OK_ENV}=1 and a {KEY_ENV} name).")
    ap.add_argument("--max-usd", type=float, default=None,
                    help=f"hard cap; default config.MISSED_OPP_MAX_USD "
                         f"({config.MISSED_OPP_MAX_USD})")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    payload = J2_missed_opportunity(smoke=a.smoke, run=a.run,
                                    backend=a.backend, max_usd=a.max_usd,
                                    top_k=a.top_k)
    out = Path(a.out) if a.out else (
        OPTIMUS / f"night_factory_{RUN_DATE}" /
        f"{JOB}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\n{JOB}: {payload.get('headline')}\n"
          f"  verdict: {payload.get('verdict')}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
