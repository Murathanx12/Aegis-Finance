"""THE BACKTEST -> FORWARD BRIDGE: what the library said it would do, beside what it does.

    python -m scripts.bridge_report freeze            # freeze today's forward books (attended)
    python -m scripts.bridge_report freeze --dry-run  # print what would be frozen, write nothing
    python -m scripts.bridge_report                   # write docs/BRIDGE.md + bridge/bridge_<date>.json

Murat, 2026-09-26: "the GitHub still says Aegis ~30% vs benchmark ~110% ... we
need to show 'we made X on the backtest and this correlates to this on paper'."
The backtest number is HINDSIGHT (every library rule was registered 2026-09-26,
after every month it is scored on). The forward book is the only quotable
record, so each library row gets one, frozen once, never re-weighted, and this
report puts the two side by side.

ONE ROW PER LIBRARY FORWARD BOOK (`lib_*`, parents only):
  historical (dev) CAGR | sealed CAGR | historical max DD | expected turnover |
  forward return | forward SPY | forward relative | current regime |
  days since inception | status
Historical columns are read from `strategy_library/leaderboard_<date>.json`
(the receipt); forward columns from `llm_portfolio.grade` on the bars panel. A
book with no session since entry says `PENDING (entry <date>)` and the table
still renders.

THE INVESTIGATION RULE (declared here, before any book has traded):
  a forward book whose relative return trails its sealed expectation
  ( ((1+sealed CAGR)/(1+sealed SPY CAGR))^(sessions/252) - 1 ) by more than ONE
  historical monthly active sigma ( |mean_active_monthly| * sqrt(12) / |IR_annual|,
  from the same receipt ) on EACH of the last 21 sessions gets an
  `investigation` with one cause from TAXONOMY, chosen by the first declared
  test in INVESTIGATION_ORDER that fires. Every test's boolean is printed beside
  the verdict. An investigation, once opened, is appended to
  `bridge/investigations.jsonl` and carried forward -- never deleted.

PRODUCT_EXPERIMENT. No LLM, no broker, no network: $0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                        # noqa: E402

LIB_DIR = REPO / "backend" / "data" / "optimus" / "strategy_library"
BRIDGE_DIR = REPO / "backend" / "data" / "optimus" / "bridge"
PLAN_DIR = REPO / "backend" / "data" / "optimus" / "decisions" / "pc_plan"
DOC = REPO / "docs" / "BRIDGE.md"

TAXONOMY = ("REGIME_SHIFT", "CROWDING", "FACTOR_DECAY", "DATA_LEAK", "IMPLEMENTATION",
            "COST", "UNIVERSE_CHANGE", "RANDOMNESS", "UNKNOWN")
#: The first test that fires names the cause. Evidence that can be CHECKED on
#: the book itself (prices, membership, costs) comes first; RANDOMNESS comes
#: before any story about the world, because at a few months it is the likeliest.
INVESTIGATION_ORDER = ("IMPLEMENTATION", "UNIVERSE_CHANGE", "COST", "RANDOMNESS",
                       "REGIME_SHIFT", "CROWDING", "FACTOR_DECAY", "DATA_LEAK", "UNKNOWN")
TRAIL_SESSIONS = 21
TRAIL_SIGMAS = 1.0
RANDOMNESS_Z = 2.0          # |shortfall| < 2 sigma * sqrt(months): a random walk does that
DECAY_SESSIONS = 63
CROWDING_DAILY_SIGMAS = 3.0
UNIVERSE_DEAD_SHARE = 0.2
PROBE_BOOKS = ("probe_equal", "probe_inverse_vol", "probe_bigmove_tilt")


# ─────────────────────────────── receipts ───────────────────────────────────

def latest_leaderboard(lib_dir: Path = LIB_DIR) -> tuple[Path, dict]:
    ps = sorted(lib_dir.glob("leaderboard_*.json"))
    if not ps:
        raise FileNotFoundError(f"no leaderboard_*.json under {lib_dir}")
    return ps[-1], json.loads(ps[-1].read_text(encoding="utf-8"))


def rule_id_of(book: dict) -> Optional[str]:
    """The library rule a lib_ book forwards. `model` is authoritative
    (`rule:strategy_library:<id>`); the name is the fallback."""
    m = str(book.get("model") or "")
    if m.startswith("rule:strategy_library:"):
        return m.split(":", 2)[2]
    nm = str(book.get("name") or "")
    if nm.startswith("lib_"):
        core = nm[4:].rsplit("_", 1)[0]
        return core[: -len("_sealed")] if core.endswith("_sealed") else core
    return None


def sigma_active_monthly(row: dict) -> Optional[float]:
    """Historical monthly sigma of (net - SPY), recovered from the receipt:
    IR_annual = mean_active_monthly * 12 / (sigma_m * sqrt(12))."""
    m, ir = row.get("mean_active_monthly"), row.get("information_ratio_annual")
    if m is None or ir is None or not np.isfinite(ir) or abs(ir) < 1e-9:
        return None
    s = abs(m * math.sqrt(12.0) / ir)
    return s if np.isfinite(s) and s > 0 else None


def expected_relative(row: dict, sessions: int) -> Optional[float]:
    c, s = row.get("sealed_cagr"), row.get("sealed_spy_cagr")
    if c is None or s is None or sessions <= 0:
        return None
    return ((1.0 + c) / (1.0 + s)) ** (sessions / 252.0) - 1.0


# ─────────────────────────────── regime ─────────────────────────────────────

def regime(spy: pd.DataFrame) -> dict:
    """SPY vs its 200-session mean, and the 21-session realised-vol tercile
    (terciles over every session after the first 252) -- the factory's own
    regime definition, from SPY closes only."""
    s = spy.sort_values("date")
    c = s["close"].astype(float).to_numpy()
    if len(c) < 260:
        return {"status": "UNKNOWN", "why": f"{len(c)} SPY sessions < 260", "label": "UNKNOWN"}
    ma200 = pd.Series(c).rolling(200, min_periods=150).mean().to_numpy()
    r = np.r_[np.nan, c[1:] / c[:-1] - 1.0]
    v = pd.Series(r).rolling(21, min_periods=15).std().to_numpy()
    hist = v[252:]
    hist = hist[np.isfinite(hist)]
    q1, q2 = np.quantile(hist, [1 / 3, 2 / 3])
    trend = "above_200d" if c[-1] > ma200[-1] else "below_200d"
    terc = "high" if v[-1] >= q2 else ("low" if v[-1] <= q1 else "mid")
    return {"status": "OK", "asof": str(pd.Timestamp(s["date"].iloc[-1]).date()),
            "spy_vs_200d": trend, "spy_close": round(float(c[-1]), 2),
            "spy_ma200": round(float(ma200[-1]), 2), "vol_tercile": terc,
            "vol_21_annual": round(float(v[-1] * math.sqrt(252)), 4),
            "label": f"SPY {trend.replace('_', ' ')}, vol {terc}"}


# ───────────────────────────── the rule ─────────────────────────────────────

def investigate(*, path: list[dict], sigma_m: Optional[float], row: dict,
                book_grade: dict, twins: dict, regime_now: dict,
                regime_at_entry: Optional[dict], family_flags: Optional[list] = None,
                daily_sigma: Optional[float] = None) -> Optional[dict]:
    """None unless the book trails its sealed expectation by > TRAIL_SIGMAS
    monthly sigma on EACH of the last TRAIL_SESSIONS sessions; else the cause.

    `path`: one {"as_of", "sessions", "relative", "expected"} per session since
    entry. `twins`: {"random_same_band": relative-to-date, ...}.
    """
    if sigma_m is None or len(path) < TRAIL_SESSIONS:
        return None
    tail = path[-TRAIL_SESSIONS:]
    short = [p["relative"] - p["expected"] for p in tail
             if p.get("relative") is not None and p.get("expected") is not None]
    if len(short) < TRAIL_SESSIONS or not all(x < -TRAIL_SIGMAS * sigma_m for x in short):
        return None
    last = path[-1]
    n = int(last["sessions"])
    shortfall = last["relative"] - last["expected"]
    months = max(n / 21.0, 1.0)
    z = shortfall / (sigma_m * math.sqrt(months))
    rels = [p["relative"] for p in path if p.get("relative") is not None]
    worst5 = (min(rels[i] - rels[i - 5] for i in range(5, len(rels)))
              if len(rels) > 5 else None)
    caveat = str(row.get("caveat") or "")
    tests = {
        "IMPLEMENTATION": bool((book_grade.get("n_unpriceable") or 0) > 0
                               or (book_grade.get("weight_priced") or 1.0) < 0.99),
        "UNIVERSE_CHANGE": bool((book_grade.get("dead_share") or 0.0) >= UNIVERSE_DEAD_SHARE),
        "COST": bool((book_grade.get("entry_cost_bps") or 0.0) / 1e4 >= abs(shortfall) - sigma_m),
        "RANDOMNESS": bool(abs(z) < RANDOMNESS_Z),
        "REGIME_SHIFT": bool(regime_at_entry and regime_now.get("status") == "OK"
                             and regime_at_entry.get("label") != regime_now.get("label")),
        "CROWDING": bool(worst5 is not None and daily_sigma
                         and worst5 < -CROWDING_DAILY_SIGMAS * daily_sigma * math.sqrt(5)
                         and family_flags is not None and sum(bool(x) for x in family_flags) >= 2),
        "FACTOR_DECAY": bool(n >= DECAY_SESSIONS and twins.get("random_same_band") is not None
                             and twins["random_same_band"] > last["relative"]),
        "DATA_LEAK": bool("CURRENT" in caveat or "survivor-selected" in caveat),
        "UNKNOWN": True,
    }
    cause = next(k for k in INVESTIGATION_ORDER if tests[k])
    return {"opened_asof": last.get("as_of"), "cause": cause, "tests": tests,
            "shortfall": round(shortfall, 6), "sigma_monthly": round(sigma_m, 6),
            "z_random_walk": round(z, 3), "sessions": n,
            "rule": (f"trails expectation by > {TRAIL_SIGMAS:g} monthly sigma on each of the "
                     f"last {TRAIL_SESSIONS} sessions; cause = first True in "
                     f"{list(INVESTIGATION_ORDER)}")}


# ─────────────────────────────── bars ───────────────────────────────────────

_COLS = ["symbol", "date", "open", "high", "low", "close", "volume"]


def load_bars(symbols: Optional[set] = None, *, since: Optional[str] = None) -> pd.DataFrame:
    """Survivorship-free bars, first occurrence per (symbol, date) wins -- the
    factory's own convention. Filters are pushed into the parquet read."""
    from backend.services import xs_ranker as XR
    filt = []
    if symbols is not None:
        filt.append(("symbol", "in", sorted(symbols)))
    if since:
        filt.append(("date", ">=", pd.Timestamp(since)))
    fr = [pd.read_parquet(p, columns=_COLS, filters=filt or None)
          for p in XR.survivorship_free_paths()]
    df = pd.concat(fr, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates(["symbol", "date"], keep="first").sort_values(
        ["symbol", "date"]).reset_index(drop=True)


def next_session(asof: str, cal: pd.DatetimeIndex) -> str:
    a = pd.Timestamp(asof)
    later = cal[cal > a]
    if len(later):
        return str(later[0].date())
    return str((a + pd.offsets.BDay(1)).date())      # the panel has not reached it yet


# ─────────────────────────────── report ─────────────────────────────────────

def _path(book: dict, bars: pd.DataFrame, cal: pd.DatetimeIndex, row: dict) -> list[dict]:
    from backend.services import llm_portfolio as LP
    a = pd.Timestamp(book["asof"])
    out = []
    for d in cal[cal > a]:
        g = LP.grade(book, bars, today=d)
        td = g.get("to_date") or {}
        if g.get("status") != "OK" or td.get("vs_benchmark") is None:
            continue
        n = int(td.get("sessions") or 0)
        out.append({"as_of": str(d.date()), "sessions": n, "relative": td["vs_benchmark"],
                    "expected": expected_relative(row, n)})
    return out


def build_rows(books: list[dict], board: dict, bars: pd.DataFrame, *,
               today: date, regime_now: dict, prior: Optional[dict] = None) -> list[dict]:
    from backend.services import llm_portfolio as LP
    by_id = {r["id"]: r for r in board.get("all_rows", [])}
    cal = pd.DatetimeIndex(sorted(bars.loc[bars["symbol"] == "SPY", "date"].unique()))
    if not len(cal):
        cal = pd.DatetimeIndex(sorted(bars["date"].unique()))
    cal = cal[cal <= pd.Timestamp(today)]
    twins_of: dict = {}
    for b in books:
        if b.get("kind") == "twin":
            twins_of.setdefault(b.get("parent_book_id"), []).append(b)
    rows = []
    for b in books:
        nm = str(b.get("name") or "")
        if not nm.startswith("lib_") or b.get("kind") == "twin":
            continue
        rid = rule_id_of(b)
        r = by_id.get(rid) or {}
        entry = next_session(b["asof"], cal)
        g = LP.grade(b, bars, today=today)
        td = g.get("to_date") or {}
        started = g.get("status") == "OK" and int(td.get("sessions") or 0) > 0
        pend = f"PENDING (entry {entry})"
        tw = {}
        for t in twins_of.get(b.get("book_id"), []):
            tg = LP.grade(t, bars, today=today)
            tw[t.get("twin")] = ((tg.get("to_date") or {}).get("vs_benchmark")
                                 if tg.get("status") == "OK" else None)
        sessions = int(td.get("sessions") or 0) if started else 0
        sig = sigma_active_monthly(r)
        reg_entry = (prior or {}).get(nm, {}).get("regime_at_entry") or regime_now
        inv = None
        if started and r:
            path = _path(b, bars, cal, r)
            held = [p["ticker"] for p in b["positions"] if p["ticker"] != "CASH"]
            recent = set(bars.loc[bars["date"] >= cal[-5], "symbol"]) if len(cal) >= 5 else set()
            g["dead_share"] = (sum(1 for t in held if t not in recent) / len(held)) if held else 0.0
            inv = investigate(path=path, sigma_m=sig, row=r, book_grade=g, twins=tw,
                              regime_now=regime_now, regime_at_entry=reg_entry)
        status = ("FORWARD" if started else pend)
        if not r:
            status = f"FORWARD-ONLY (no backtest row); {status}"
        rows.append({
            "book": nm, "book_id": b.get("book_id"), "rule": rid, "asof": b.get("asof"),
            "entry": entry, "n_positions": b.get("n_positions"), "receipt_row": bool(r),
            "dev_cagr": r.get("dev_cagr"), "dev_spy_cagr": r.get("dev_spy_cagr"),
            "sealed_cagr": r.get("sealed_cagr"), "sealed_spy_cagr": r.get("sealed_spy_cagr"),
            "sealed_vs_spy": r.get("sealed_vs_spy"), "sealed_dsr": r.get("sealed_dsr"),
            "max_dd": r.get("max_dd"), "turnover_annual": r.get("turnover_annual"),
            "sigma_active_monthly": sig,
            "forward_return": td.get("net") if started else pend,
            "forward_spy": td.get("benchmark_return") if started else pend,
            "forward_relative": td.get("vs_benchmark") if started else pend,
            "expected_relative_to_date": expected_relative(r, sessions) if started else pend,
            "twins_relative": tw if started else pend,
            "regime_now": regime_now.get("label"), "regime_at_entry": reg_entry,
            "days_since_inception": max((pd.Timestamp(today) - pd.Timestamp(b["asof"])).days, 0),
            "sessions_since_entry": sessions, "status": status, "investigation": inv,
        })
    return rows


def probe_rows(books: list[dict], bars: pd.DataFrame, *, today: date) -> list[dict]:
    from backend.services import llm_portfolio as LP
    cal = pd.DatetimeIndex(sorted(bars.loc[bars["symbol"] == "SPY", "date"].unique()))
    out = []
    for b in books:
        nm = str(b.get("name") or "")
        if b.get("kind") == "twin" or not nm.startswith(PROBE_BOOKS):
            continue
        g = LP.grade(b, bars, today=today)
        td = g.get("to_date") or {}
        started = g.get("status") == "OK" and int(td.get("sessions") or 0) > 0
        pend = f"PENDING (entry {next_session(b['asof'], cal)})"
        out.append({"book": nm, "book_id": b.get("book_id"), "asof": b["asof"],
                    "weights": {p["ticker"]: round(p["weight"], 4) for p in b["positions"]
                                if p["ticker"] != "CASH"},
                    "forward_return": td.get("net") if started else pend,
                    "forward_spy": td.get("benchmark_return") if started else pend,
                    "forward_relative": td.get("vs_benchmark") if started else pend})
    return out


def _p(v: Any, nd: int = 1) -> str:
    if isinstance(v, str):
        return v
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v*100:+.{nd}f}%"


def render_md(doc: dict) -> str:
    reg = doc.get("regime") or {}
    L = [f"# The backtest -> forward bridge — {doc['date']}", "",
         "> Every historical number below is HINDSIGHT: the library's 254 rules were written "
         "on 2026-09-26, after every month they are scored on. The forward columns are the only "
         "quotable record; each row is a $1M long-only paper book frozen once and never "
         "re-weighted. Generated by `python -m scripts.bridge_report`; receipt "
         f"`{doc['receipt_json']}`; historical columns from `{doc['leaderboard']}`.", "",
         f"Current regime ({reg.get('asof', '?')}): **{reg.get('label', 'UNKNOWN')}** "
         "(SPY vs its 200-session mean; 21-session realised-vol tercile since 2017).", "",
         "| book | rule | dev CAGR | sealed CAGR (SPY) | hist max DD | turnover/yr | forward return "
         "| forward SPY | forward relative | expected rel. to date | regime | days | status |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in doc["rows"]:
        tv = r.get("turnover_annual")
        L.append(
            f"| `{r['book']}` | `{r['rule']}` | {_p(r['dev_cagr'])} | {_p(r['sealed_cagr'])} "
            f"({_p(r['sealed_spy_cagr'])}) | {_p(r['max_dd'])} | "
            f"{(f'{tv:.1f}x' if isinstance(tv, (int, float)) else 'n/a')} | "
            f"{_p(r['forward_return'], 2)} | {_p(r['forward_spy'], 2)} | "
            f"{_p(r['forward_relative'], 2)} | {_p(r['expected_relative_to_date'], 2)} | "
            f"{r['regime_now']} | {r['days_since_inception']} | {r['status']} |")
    L += ["", "## Investigations (never deleted)", ""]
    inv = ([{"book": r["book"], **r["investigation"]} for r in doc["rows"] if r.get("investigation")]
           + list(doc.get("carried_investigations", [])))
    L.append(f"The rule: a book whose forward relative return trails its sealed expectation by "
             f"more than {TRAIL_SIGMAS:g} historical monthly active sigma on each of the last "
             f"{TRAIL_SESSIONS} sessions is investigated; the cause is the first true test in "
             f"{', '.join(INVESTIGATION_ORDER)} (`scripts/bridge_report.py::investigate`). "
             "An opened investigation is appended to `backend/data/optimus/bridge/investigations.jsonl`.")
    L.append("")
    if not inv:
        L.append("None open.")
    for i in inv:
        L.append(f"- `{i.get('book')}`: **{i['cause']}** (shortfall {_p(i['shortfall'], 2)}, "
                 f"sigma {_p(i['sigma_monthly'], 2)}, z {i['z_random_walk']}); tests "
                 + ", ".join(f"{k}={'T' if v else 'f'}" for k, v in i["tests"].items()))
    L += ["", "## The PROBE weighting experiment (same names, three weightings)", "",
          doc.get("probe_note", ""), "",
          "| book | forward return | forward SPY | forward relative | weights |",
          "|---|---|---|---|---|"]
    for r in doc.get("probe_rows", []):
        w = ", ".join(f"{k} {v:.1%}" for k, v in r["weights"].items())
        L.append(f"| `{r['book']}` | {_p(r['forward_return'], 2)} | {_p(r['forward_spy'], 2)} | "
                 f"{_p(r['forward_relative'], 2)} | {w} |")
    L += ["", "## How to read it", "",
          "- **dev** = monthly periods entered 2017-02 → 2023-12; **sealed** = entered from "
          "2024-01-01 (32 monthly blocks), a split declared in `strategy_library.py` before the "
          "ranking. Ranking 762 cells on 32 months selects luck as readily as skill; no rule "
          "reaches DSR 0.95.",
          "- **expected rel. to date** = ((1 + sealed CAGR) / (1 + SPY sealed CAGR))^(sessions/252) − 1: "
          "what the sealed window says the book should be ahead of SPY by now.",
          "- A forward number is net of the entry half of the band round trip "
          "(`llm_portfolio.grade`), priced from the open of the session after the freeze.",
          "- `lib_*_2026-09-26` books without `_sealed` were frozen by the 02:00 factory from its "
          "DSR top-10; `FORWARD-ONLY` rows have no backtest on this panel.",
          f"- Independent (vectorbt) recomputation of the sealed top-10 series: "
          f"`{doc.get('replication') or 'not yet run'}`.", ""]
    return "\n".join(L)


def load_investigations(out_dir: Path = BRIDGE_DIR) -> dict:
    p = out_dir / "investigations.jsonl"
    out: dict = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                x = json.loads(line)
                out[x["book"]] = x
    return out


def _relpath(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(p)


def report(*, today: Optional[date] = None, out_md: Path = DOC,
           out_dir: Path = BRIDGE_DIR, books: Optional[list] = None,
           bars: Optional[pd.DataFrame] = None, board: Optional[dict] = None,
           board_path: Optional[str] = None) -> dict:
    from backend.services import llm_portfolio as LP
    today = today or date.today()
    if board is None:
        bp, board = latest_leaderboard()
        board_path = _relpath(bp)
    books = LP.read_books() if books is None else books
    lib = [b for b in books if str(b.get("name") or "").startswith(("lib_",) + PROBE_BOOKS)]
    if bars is None:
        syms = {p["ticker"] for b in lib for p in b["positions"]} | {"SPY"}
        syms.discard("CASH")
        bars = load_bars(syms, since="2016-01-01")
    reg = regime(bars[bars["symbol"] == "SPY"])
    prior: dict = {}
    prev = sorted(p for p in out_dir.glob("bridge_*.json") if p.stem != f"bridge_{today}") \
        if out_dir.exists() else []
    if prev:
        try:
            prior = {r["book"]: r for r in json.loads(prev[-1].read_text(encoding="utf-8"))["rows"]}
        except (ValueError, KeyError):
            prior = {}
    rows = build_rows(lib, board, bars, today=today, regime_now=reg, prior=prior)
    open_now = {r["book"] for r in rows if r.get("investigation")}
    carried = [v for k, v in load_investigations(out_dir).items() if k not in open_now]
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = out_dir / f"bridge_{today}.json"
    rep = sorted(LIB_DIR.glob("replication_vectorbt_*.json"))
    doc = {"schema": "bridge/1", "date": str(today), "licence": "PRODUCT_EXPERIMENT",
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "leaderboard": board_path or "(in-memory board)", "receipt_json": _relpath(receipt),
           "replication": _relpath(rep[-1]) if rep else None,
           "regime": reg,
           "rule": {"trail_sessions": TRAIL_SESSIONS, "trail_sigmas": TRAIL_SIGMAS,
                    "order": list(INVESTIGATION_ORDER), "taxonomy": list(TAXONOMY)},
           "rows": rows, "carried_investigations": carried,
           "probe_rows": probe_rows(books, bars, today=today),
           "probe_note": ("Reviewer H+I's highest-EV experiment (adjudication 2026-09-26 row 5): "
                          "the PROBE names of `decisions/pc_plan/2026-09-25.json` weighted equal / "
                          "inverse 63-session vol / big-move tilt, each $1M long-only with twins. "
                          "Read the arm DIFFERENCES regressed on USMV before calling any of them "
                          "skill: inverse-vol is partly low-vol beta.")}
    for r in rows:
        if r.get("investigation"):
            with (out_dir / "investigations.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"book": r["book"], **r["investigation"]}, default=str) + "\n")
    receipt.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_md(doc), encoding="utf-8")
    return doc


# ─────────────────────────────── README ─────────────────────────────────────

README_HEADING = "## Historical backtests: what worked, what didn't"
OLD_RECEIPT = "backend/BACKTEST_RESULTS.md"


def both_windows(board: dict) -> list[str]:
    """Rules in BOTH the sealed top-10 and the full-window DSR top-10."""
    sealed = [r["id"] for r in board["top_by_sealed_vs_spy"][:10]]
    dsr = {r["id"] for r in board["top_by_dsr"][:10]}
    return [i for i in sealed if i in dsr]


def library_facts(board: dict) -> dict:
    rows = [r for r in board["all_rows"] if not r.get("control")]
    sv = [r["sealed_vs_spy"] for r in rows if r.get("sealed_vs_spy") is not None]
    best = max(rows, key=lambda r: r.get("dsr") or -1)
    ctrl = board.get("controls") or []
    return {"n_rules": len(rows), "n_beat": sum(1 for x in sv if x > 0),
            "median_sealed_vs_spy": float(np.median(sv)),
            "best_dsr": best["dsr"], "best_dsr_id": best["id"],
            "n_cells": board["multiplicity"]["n_cells_looked_at"],
            "n_families": board["multiplicity"]["n_families"],
            "n_sealed": board["objective"]["n_sealed_months"],
            "ctrl_lo": min(c["sealed_vs_spy"] for c in ctrl) if ctrl else None,
            "ctrl_hi": max(c["sealed_vs_spy"] for c in ctrl) if ctrl else None,
            "both": both_windows(board)}


def readme_section(board: dict, board_path: str) -> str:
    """The README section, rendered from the leaderboard receipt only."""
    f = library_facts(board)
    lbmd = "backend/data/optimus/strategy_library/LEADERBOARD.md"
    top = board["top_by_sealed_vs_spy"][:10]
    L = [README_HEADING, "",
         "> 🔵 **HINDSIGHT BACKTEST — NOT FORWARD PERFORMANCE.** Every rule below was written "
         "down on 2026-09-26, after every month it is scored on. The quotable record starts at "
         f"registration. Receipt for every number in this section: `{board_path}` "
         f"(rendered as `{lbmd}`); forward results: `docs/BRIDGE.md`.", "",
         f"The strategy library ({f['n_rules']} rules in {f['n_families']} families, "
         f"{f['n_cells']} cells at k = 10/20/50 plus each rule's own k) was run on survivorship-free "
         "bars net of a band round-trip cost, with a split declared in code before the ranking: "
         f"**dev** = monthly periods entered through 2023-12-31, **sealed** = entered from "
         f"2024-01-01 ({f['n_sealed']} monthly blocks). Sorted by sealed net return vs SPY "
         f"(`{board_path}`, `top_by_sealed_vs_spy`):", "",
         "| rule (k=20) | dev CAGR | SPY dev | sealed CAGR | SPY sealed | sealed − SPY | DSR (762 cells) "
         "| LOO-worst mean active/mo | top-5-month share | max DD |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in top:
        t5 = r.get("top5_months_share_of_log_return")
        L.append(f"| `{r['id']}` | {_p(r['dev_cagr'])} | {_p(r['dev_spy_cagr'])} | "
                 f"{_p(r['sealed_cagr'])} | {_p(r['sealed_spy_cagr'])} | **{_p(r['sealed_vs_spy'])}** | "
                 f"{r['dsr']:.3f} | {_p(r['loo_worst_mean_active'], 2)} | "
                 f"{('n/a' if t5 is None else f'{t5:.2f}')} | {_p(r['max_dd'])} |")
    ctrl = ""
    if f["ctrl_lo"] is not None:
        ctrl = (f"Random controls (k=20 names drawn at random each month, never ranked) land at "
                f"{_p(f['ctrl_lo'])} to {_p(f['ctrl_hi'])} vs SPY sealed: that is the luck bar "
                f"(`{board_path}`, `controls`).")
    L += ["", ctrl, "",
          f"- **Nothing passes the multiplicity bar (best DSR {f['best_dsr']:.2f} at {f['n_cells']} "
          f"cells, `{f['best_dsr_id']}`, vs 0.95).** Ranking {f['n_cells']} cells on "
          f"{f['n_sealed']} sealed months selects luck as readily as skill (`{board_path}`, "
          "`multiplicity`).",
          f"- **{f['n_beat']} of {f['n_rules']} rules beat SPY sealed, median "
          f"{f['median_sealed_vs_spy']*100:+.1f}%** (`{board_path}`, `all_rows[].sealed_vs_spy`).",
          f"- **The only rows good in both windows are "
          f"{' and '.join(f'`{i}`' for i in f['both'])}**: the only rules in both the sealed "
          "top-10 and the full-window DSR top-10. The sealed top rows with a top-5-month share "
          "near or above 1 made their sealed return in a handful of months, and several were "
          f"flat or negative in dev (`{board_path}`).",
          "- **Each of these is a $1M forward paper book since 2026-09-28; `docs/BRIDGE.md` shows "
          "expectation vs result** (receipt `backend/data/optimus/bridge/bridge_<date>.json`; books "
          "in `backend/data/optimus/llm_portfolio/books.jsonl`, `lib_<id>_sealed_2026-09-26` with "
          "ew / sector-ETF / SPY / random-same-band twins; `mom_12_1_q`'s is the 02:00 factory's "
          "`lib_mom_12_1_q_2026-09-26`, same names; freeze log "
          "`backend/data/optimus/bridge/freeze_2026-09-26.json`).",
          "- The ten sealed series were recomputed by a second engine from their holdings and the "
          "raw bars: `backend/data/optimus/strategy_library/replication_vectorbt_2026-09-26.json`.",
          "", "### History: the timing strategy (not the library)", "",
          f"The row this section used to lead with measured the 2020-01 → 2025-06 signal-engine "
          f"TIMING strategy, not any library rule (receipt `{OLD_RECEIPT}`, re-measured "
          "2026-09-04):", "",
          "| Historical experiment (2020-01 → 2025-06) | Aegis | Benchmark | What we learned |",
          "|---|---:|---:|---|",
          "| Signal-engine timing strategy, total return (`backend/BACKTEST_RESULTS.md`) | **+28.3%** "
          "net | **+114.8%** (SPY total return) | Stress detection ≠ market timing — the "
          "strategy keeps a quarter of the market |", "",
          "The engine was good at detecting that the market was under stress and then "
          "translated *\"the market is dangerous\"* into *\"therefore sell\"* — two different "
          "predictions. It survives as a **risk-awareness system**, not a timing system "
          f"(`{OLD_RECEIPT}`, [`NEGATIVE_RESULTS.md §1`](NEGATIVE_RESULTS.md)).", ""]
    return "\n".join(L)


def splice_readme(readme: str, section: str) -> str:
    i = readme.index(README_HEADING)
    j = readme.index("\n## ", i + len(README_HEADING))
    return readme[:i] + section.rstrip("\n") + "\n" + readme[j:]


def readme_block(readme: str) -> str:
    i = readme.index(README_HEADING)
    j = readme.index("\n## ", i + len(README_HEADING))
    return readme[i:j]


# ─────────────────────────────── freeze ─────────────────────────────────────

def worst_case_weighted(name: str, weights: dict, capital: float,
                        daily_sigma: Optional[dict] = None) -> str:
    """CLAUDE.md protocol 4 for a weighted, long-only, no-stop book."""
    fill = abs(float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    gross = sum(weights.values())
    big = max(weights, key=weights.get)
    s = (f"WORST CASE {name}: {len(weights)} names, sum|notional|/equity {gross:.2f} of "
         f"${capital:,.0f}, no stop (monthly rebalance): every name at the {fill:.0%} "
         f"delisting fill = -${capital*gross*fill:,.0f}; largest name ({big} {weights[big]:.1%}) "
         f"to zero = -${capital*weights[big]:,.0f}; whole book to zero = -${capital*gross:,.0f}")
    if daily_sigma:
        k3 = sum(w * 3.0 * (daily_sigma.get(t) or 0.0) for t, w in weights.items())
        s += f"; every name down 3 daily sigma at once = -${capital*k3:,.0f}"
    return s


def probe_names(plan_path: Path) -> list[str]:
    d = json.loads(plan_path.read_text(encoding="utf-8"))
    seen: list[str] = []
    for r in d["rows"]:
        if r.get("direction") == "PROBE" and r["ticker"] not in seen:
            seen.append(r["ticker"])
    return seen


def sigma_63(bars: pd.DataFrame, names: list[str], asof: str) -> dict:
    """Daily close-to-close sigma over the last 63 sessions at or before asof."""
    out = {}
    b = bars[bars["date"] <= pd.Timestamp(asof)]
    for t in names:
        c = b.loc[b["symbol"] == t].sort_values("date")["close"].astype(float).to_numpy()
        r = c[1:] / c[:-1] - 1.0
        r = r[np.isfinite(r)][-63:]
        out[t] = float(np.std(r, ddof=1)) if len(r) >= 40 else None
    return out


def magnitude_rows(names: list[str], cutoff_utc: str, h: int = 5) -> dict:
    """Latest investigator P(|move| > threshold) at horizon h per name, made at
    or before `cutoff_utc`. A name with no row is absent from the result."""
    p = Path(_cfg.OPTIMUS_LEDGER_DIR) / "predictions.jsonl"
    out: dict = {}
    if not p.exists():
        return out
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if '"abs_move_exceeds"' not in line or "investigator" not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("ticker") in names and r.get("horizon_days") == h
                    and str(r.get("made_at")) <= cutoff_utc):
                if r["ticker"] not in out or str(r["made_at"]) >= out[r["ticker"]]["made_at"]:
                    out[r["ticker"]] = {"p": float(r["probability"]),
                                        "threshold": r.get("threshold"),
                                        "made_at": str(r["made_at"]),
                                        "specialist": r.get("specialist")}
    return out


def _norm(w: dict) -> dict:
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def probe_books(plan_path: Path, bars: pd.DataFrame, *, today: date,
                magnitude: Optional[dict] = None) -> tuple[list[dict], dict]:
    names = probe_names(plan_path)
    sig = sigma_63(bars, names, str(today))
    missing = [t for t in names if not sig.get(t)]
    if missing:
        raise RuntimeError(f"REFUSED: no 63-session sigma for {missing}")
    mag = magnitude if magnitude is not None else magnitude_rows(names, f"{today}T23:59:59+00:00")
    if all(t in mag for t in names):
        tilt = {t: mag[t]["p"] for t in names}
        tilt_basis = "investigator P(|r_5d| > threshold), latest row per name"
    else:
        tilt = {t: sig[t] for t in names}
        tilt_basis = (f"sigma_63 -- investigator magnitude rows cover {len(mag)} of {len(names)} "
                      f"names ({', '.join(sorted(mag)) or 'none'}); a partial tilt would mix two "
                      f"scales, so the declared fallback is used for all")
    n = len(names)
    schemes = {
        "probe_equal": ({t: 1.0 / n for t in names}, "equal weight"),
        "probe_inverse_vol": (_norm({t: 1.0 / sig[t] for t in names}),
                              "weights proportional to 1/sigma_63"),
        "probe_bigmove_tilt": (_norm(tilt), f"weights proportional to {tilt_basis}"),
    }
    books = []
    for key, (w, how) in schemes.items():
        books.append({
            "name": f"{key}_{today}", "kind": "personal",
            "objective": ("Relative P&L vs SPY over 21 sessions, long-only, $1M: the same PROBE "
                          "names weighted three ways"),
            "model": f"rule:probe_weighting:{key}",
            "strategy": (f"PRODUCT_EXPERIMENT; kind personal. The {n} PROBE names of "
                         f"{plan_path.name} (sim_run.u_plan.probe, c3-v0), {how}. Adjudication "
                         f"2026-09-26 row 5: the arms differ ONLY in weighting; read their "
                         f"differences regressed on USMV before calling any of them skill."),
            "horizon_days": [1, 5, 21, 63, 126],
            "positions": [{"ticker": t, "weight": round(w[t], 8),
                           "thesis": f"PROBE name from {plan_path.name}; {how}; sigma_63 {sig[t]:.4f}/day",
                           "falsifier": ("the arm trails probe_equal after 21 sessions by more "
                                         "than its USMV beta explains")} for t in names]
                         + [{"ticker": "CASH", "weight": 0.0, "thesis": "declared: fully invested",
                             "falsifier": "n/a"}],
        })
    return books, {"names": names, "sigma_63": sig, "tilt_basis": tilt_basis,
                   "magnitude_rows": mag}


def library_targets(board: dict) -> list[str]:
    """The sealed top-10, plus the two rows good in dev AND sealed."""
    ids = [r["id"] for r in board["top_by_sealed_vs_spy"][:10]]
    for extra in ("skill_mom", "mom_12_1_q"):
        if extra not in ids:
            ids.append(extra)
    return ids


def build_library_panel():
    """The factory's panel, exactly (same loader, same attachers, same tiebreak)."""
    from backend.services import xs_ranker as XR
    from backend.services import strategy_library as SL
    from scripts import night_backtest_factory as F
    W = F.load_wide(XR.survivorship_free_paths(), start=_cfg.STRATEGY_LIB_START)
    panel = F.build_panel(W, delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    panel, _ = F.attach_fundamentals(panel)
    panel, _ = F.attach_flow(panel)
    for nm, fn in (("ratings", lambda p: F.attach_ratings(p, W)), ("insider", F.attach_insider),
                   ("eightk", lambda p: F.attach_8k(p, W)),
                   ("short_interest", F.attach_short_interest), ("sector", F.attach_sector),
                   ("extension", lambda p: F.attach_extension(p, W))):
        try:
            panel, meta = fn(panel)
            print(f"  {nm}: {meta.get('status')}", flush=True)
        except Exception as e:                            # noqa: BLE001 -- printed, never silent
            print(f"  {nm}: REFUSED {type(e).__name__}: {e}", flush=True)
    panel["tiebreak"] = SL._tiebreak(panel)
    bars = F.recent_bars(W)
    return panel, bars


def library_books(board: dict, panel: pd.DataFrame, *, today: date, ids: list[str]) -> list[dict]:
    """One book per rule: the factory's `latest_selection` names at the RULE's
    own weights (`strategy_library._weights`: inv_amihud stays inv_amihud)."""
    from backend.services import strategy_library as SL
    by_row = {r["id"]: r for r in board["all_rows"]}
    out = []
    last = panel["date"].max()
    day = panel.index[(panel["date"] == last).to_numpy()]
    dpan = panel.loc[day].reset_index(drop=True)
    pos = {s: j for j, s in enumerate(dpan["symbol"])}
    for rid in ids:
        rule = SL.rule_by_id(rid)
        picks = SL.latest_selection(panel, rule)
        top = np.array([pos[p["symbol"]] for p in picks])
        w = SL._weights(rule, dpan, top)
        r = by_row[rid]
        note = (f"Backtest (HINDSIGHT, registered {r['first_registered_utc'][:10]}): dev CAGR "
                f"{_p(r['dev_cagr'])} (SPY {_p(r['dev_spy_cagr'])}), SEALED CAGR "
                f"{_p(r['sealed_cagr'])} (SPY {_p(r['sealed_spy_cagr'])}) over "
                f"{r['n_sealed_months']} months, sealed DSR {r['sealed_dsr']} at n=762, "
                f"top-5-month share {r['top5_months_share_of_log_return']}, max DD "
                f"{_p(r['max_dd'])}; bars asof {pd.Timestamp(last).date()}. Weight rule "
                f"{rule.weight_rule}, hold {rule.hold_months} month(s).")
        out.append({
            "name": f"lib_{rid}_sealed_{today}", "kind": "personal",
            "objective": ("Relative P&L vs SPY over 21 sessions, long-only, net of band round-trip "
                          "cost (strategy-library SEALED top-10 forward book)"),
            "model": f"rule:strategy_library:{rid}",
            "strategy": (f"PRODUCT_EXPERIMENT; kind personal. Strategy-library rule `{rid}`: "
                         f"{rule.description}. Top-{len(picks)}, {rule.weight_rule} weight. "
                         f"{note}")[:2000],
            "horizon_days": [1, 5, 21, 63, 126],
            "positions": [{"ticker": p["symbol"], "weight": round(float(wi), 8),
                           "thesis": (f"{rule.description}; score {p['score']:.4g}, rank {i+1} "
                                      f"of {len(picks)}"),
                           "falsifier": (f"drops out of the rule's top-{2*len(picks)} at the next "
                                         f"rebalance, or the book trails its sealed expectation "
                                         f"by > 1 monthly sigma for 21 sessions (docs/BRIDGE.md)")}
                          for i, (p, wi) in enumerate(zip(picks, w))]
                         + [{"ticker": "CASH", "weight": 0.0, "thesis": "declared: fully invested",
                             "falsifier": "n/a"}],
        })
    return out


def _same_positions(a: dict, b: dict) -> bool:
    ta = {p["ticker"]: round(p["weight"], 4) for p in a["positions"] if p["ticker"] != "CASH"}
    tb = {p["ticker"]: round(p["weight"], 4) for p in b["positions"] if p["ticker"] != "CASH"}
    return ta == tb


def _same_names(a: dict, b: dict) -> bool:
    return ({p["ticker"] for p in a["positions"] if p["ticker"] != "CASH"}
            == {p["ticker"] for p in b["positions"] if p["ticker"] != "CASH"})


def cmd_freeze(a) -> int:
    from backend.services import llm_portfolio as LP
    from scripts.llm_portfolio import freeze_with_twins
    today = date.fromisoformat(a.today) if a.today else date.today()
    _bp, board = latest_leaderboard()
    books = LP.read_books()
    names = {b.get("name") for b in books}
    ids = [i for i in library_targets(board) if f"lib_{i}_sealed_{today}" not in names]
    log: dict = {"date": str(today), "library": {}, "probe": {}}
    to_freeze: list[dict] = []
    bars = None
    if ids and not a.skip_library:
        print(f"building the factory panel for {ids} ...", flush=True)
        panel, bars = build_library_panel()
        for bk in library_books(board, panel, today=today, ids=ids):
            rid = bk["model"].split(":")[-1]
            dup = [b for b in books if b.get("kind") != "twin" and rule_id_of(b) == rid
                   and str(b.get("name", "")).endswith(str(today)) and _same_names(b, bk)]
            if dup:
                log["library"][rid] = {"status": "ALREADY_FROZEN_TODAY_SAME_POSITIONS",
                                       "book": dup[0]["name"]}
                print(f"  {rid}: already frozen today as {dup[0]['name']} with the same names; skipped")
                continue
            to_freeze.append(bk)
        del panel
    plan = PLAN_DIR / f"{a.plan}.json"
    if bars is None:
        bars = load_bars(since=str((pd.Timestamp(today) - pd.Timedelta(days=140)).date()))
    pb, meta = probe_books(plan, bars, today=today)
    log["probe"]["meta"] = meta
    print(f"PROBE names ({len(meta['names'])}): {meta['names']}; tilt basis: {meta['tilt_basis']}")
    for bk in pb:
        if bk["name"] in names:
            print(f"  {bk['name']}: already in books.jsonl, not refrozen")
            continue
        to_freeze.append(bk)
    for bk in to_freeze:
        w = {p["ticker"]: p["weight"] for p in bk["positions"] if p["ticker"] != "CASH"}
        ds = meta["sigma_63"] if bk["name"].startswith(PROBE_BOOKS) else None
        wc = worst_case_weighted(bk["name"], w, LP.START_CAPITAL, ds)
        print(wc)
        (log["probe"] if bk["name"].startswith(PROBE_BOOKS) else log["library"])[bk["name"]] = {
            "worst_case": wc, "weights": {k: round(v, 6) for k, v in w.items()}}
    if a.dry_run:
        print(f"DRY RUN: {len(to_freeze)} books would be frozen: {[b['name'] for b in to_freeze]}")
        return 0
    rc = 0
    for bk in to_freeze:
        seed = int(hashlib.sha256(bk["name"].encode()).hexdigest()[:8], 16)
        if bk["name"].startswith(PROBE_BOOKS):
            seed = 20260926                 # one seed: the three arms share one random-twin draw
        rc_i, frozen = freeze_with_twins([bk], us_bars=bars, twins=True, seed=seed,
                                         check_prices=True, accept_draft=True)
        rc = max(rc, rc_i)
        tgt = log["probe"] if bk["name"].startswith(PROBE_BOOKS) else log["library"]
        tgt[bk["name"]]["book_ids"] = {f["name"]: f["book_id"] for f in frozen}
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    out = BRIDGE_DIR / f"freeze_{today}.json"
    out.write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
    print(f"-> {out}")
    return rc


def cmd_report(a) -> int:
    today = date.fromisoformat(a.today) if getattr(a, "today", None) else date.today()
    doc = report(today=today)
    print(render_md(doc))
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")          # the report prints em dashes
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("freeze")
    f.add_argument("--today", default=None)
    f.add_argument("--plan", default="2026-09-25")
    f.add_argument("--dry-run", action="store_true")
    f.add_argument("--skip-library", action="store_true")
    r = sub.add_parser("report")
    r.add_argument("--today", default=None)
    sub.add_parser("readme", help="rewrite the README backtest section from the leaderboard receipt")
    a = ap.parse_args(argv)
    if a.cmd == "freeze":
        return cmd_freeze(a)
    if a.cmd == "readme":
        bp, board = latest_leaderboard()
        p = REPO / "README.md"
        txt = p.read_text(encoding="utf-8")
        p.write_text(splice_readme(txt, readme_section(board, _relpath(bp))), encoding="utf-8")
        print(f"-> {p} section '{README_HEADING}' rewritten from {_relpath(bp)}")
        return 0
    return cmd_report(a)


if __name__ == "__main__":
    raise SystemExit(main())
