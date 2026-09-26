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
    """The newest RUN receipt (`leaderboard_<date>T<HHMMSS>Z.json`). The
    date-named file is a 'latest' copy a second run overwrites (review
    2026-09-26 finding 0), so it is read only when no run receipt exists."""
    ps = sorted(lib_dir.glob("leaderboard_*T*Z.json"))
    if not ps:
        ps = sorted(lib_dir.glob("leaderboard_*.json"))
    if not ps:
        raise FileNotFoundError(f"no leaderboard_*.json under {lib_dir}")
    return ps[-1], json.loads(ps[-1].read_text(encoding="utf-8"))


def latest_replication(lib_dir: Path = LIB_DIR, run_id: Optional[str] = None) -> Optional[Path]:
    """The re-implementation receipt for `run_id` if it exists, else the newest."""
    if run_id:
        p = lib_dir / f"replication_vectorbt_{run_id}.json"
        if p.exists():
            return p
    ps = sorted(lib_dir.glob("replication_vectorbt_*.json"))
    return ps[-1] if ps else None


def git_head(repo: Path = REPO) -> str:
    """HEAD's short hash at render time (the commit a reader checks the receipt at)."""
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo),
                             capture_output=True, text=True, timeout=20)
        h = out.stdout.strip()
        return h if out.returncode == 0 and h else "UNKNOWN"
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


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


def book_weights(book: dict) -> dict:
    return {p["ticker"]: float(p["weight"]) for p in book.get("positions", [])
            if p["ticker"] != "CASH" and float(p["weight"]) > 0}


def gates_for(books: list[dict], board: dict, bars: pd.DataFrame, *,
              earnings: Optional[dict] = None) -> dict:
    """book name -> freeze-gate result, for every lib_ parent (and the ew twin of
    a voided parent). A book frozen WITH a gate carries it (`freeze_gate`); a
    book frozen before the gate existed is evaluated now on bars at or before
    its own as-of date, with the family cap counted in ledger order."""
    from scripts import night_backtest_factory as F
    by_id = {r["id"]: r for r in board.get("all_rows", [])}
    cal = pd.DatetimeIndex(sorted(bars.loc[bars["symbol"] == "SPY", "date"].unique()))
    fam_n: dict = {}
    out: dict = {}
    parents = [b for b in books if str(b.get("name") or "").startswith("lib_")
               and b.get("kind") != "twin"]
    voided = {b["book_id"] for b in parents if b.get("void")}
    ew_of_voided = [b for b in books if b.get("kind") == "twin" and b.get("twin") == "ew"
                    and b.get("parent_book_id") in voided]
    for b in parents + ew_of_voided:
        nm = b["name"]
        if b.get("freeze_gate"):
            out[nm] = {**b["freeze_gate"], "evaluated": "at freeze"}
            continue
        rid = rule_id_of(b) if b.get("kind") != "twin" else rule_id_of(
            {"name": nm.split("__")[0]})
        row = by_id.get(rid)
        fam = (row or {}).get("family")
        g = F.freeze_gate(row, book_weights(b), bars, cal, decision_date=b["asof"],
                          family_books_before=fam_n.get(fam, 0), earnings=earnings)
        g["evaluated"] = "retroactively (frozen before the gate existed)"
        out[nm] = g
        if g["verdict"] == "PASS" and not b.get("void") and b.get("kind") != "twin":
            fam_n[fam] = fam_n.get(fam, 0) + 1
    return out


def build_rows(books: list[dict], board: dict, bars: pd.DataFrame, *,
               today: date, regime_now: dict, prior: Optional[dict] = None,
               gates: Optional[dict] = None) -> list[dict]:
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
    voided_ids = {b["book_id"] for b in books if b.get("void")}
    rows = []
    for b in books:
        nm = str(b.get("name") or "")
        if not nm.startswith("lib_") or b.get("void"):
            continue
        strategy_test = (b.get("kind") == "twin" and b.get("twin") == "ew"
                         and b.get("parent_book_id") in voided_ids)
        if b.get("kind") == "twin" and not strategy_test:
            continue
        rid = rule_id_of(b) if not strategy_test else rule_id_of({"name": nm.split("__")[0]})
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
        if strategy_test:
            status = f"STRATEGY TEST (ew twin of the voided parent); {status}"
        g_ = (gates or {}).get(nm) or {}
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
            "kind": b.get("kind"), "strategy_test_for_voided": strategy_test,
            "gate": g_.get("label"), "gate_verdict": g_.get("verdict"),
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


FIRST_READING = ("No forward day graded yet; the first 21-session reading is the "
                 "2026-10-26 close.")


def render_md(doc: dict) -> str:
    from backend.services import strategy_library as SL
    reg = doc.get("regime") or {}
    lab = SL.SELECTION_WINDOW_LABEL
    fx = doc.get("library_facts") or {}
    dse = doc.get("dev_selected") or {}
    t10 = dse.get("top_10") or {}
    sp = dse.get("spearman_dev_vs_selection_window") or {}
    n_rules = fx.get("n_rules", "the library's")
    L = [f"# The backtest -> forward bridge — {doc['date']}", "",
         f"> Every historical number below is HINDSIGHT: the library's {n_rules} rules were "
         "written on 2026-09-26, after every month they are scored on. The forward columns are the "
         "only quotable record; each row is a $1M long-only paper book frozen once and never "
         "re-weighted. Generated by `python -m scripts.bridge_report report` at commit "
         f"`{doc.get('git_head', 'UNKNOWN')}`; receipt `{doc['receipt_json']}`; historical "
         f"columns from `{doc['leaderboard']}`.", ""]
    ng = doc.get("n_forward_graded", 0)
    if not ng:
        L += [f"**{FIRST_READING}**", ""]
    if t10:
        L += [f"The one out-of-sample read the backtest holds: choosing the top 10 rules by dev "
              f"(pre-2024) results alone gave **{t10['mean_selection_window_vs_spy']*100:+.1f} pp/yr** "
              f"mean vs SPY in the {lab} (median {t10['median_selection_window_vs_spy']*100:+.1f} pp; "
              f"{t10['n_beat_spy']} of {t10['n']} beat SPY); dev-to-2024-26 rank Spearman "
              f"**{sp.get('rho', float('nan')):.2f}** over {sp.get('n')} rules "
              f"(`{doc['leaderboard']}`, `dev_selected_sealed_evaluated`).", ""]
    L += [f"Current regime ({reg.get('asof', '?')}): **{reg.get('label', 'UNKNOWN')}** "
          "(SPY vs its 200-session mean; 21-session realised-vol tercile since 2017).", "",
          "| book | rule | gate | dev CAGR | 2024-26 CAGR (SPY) | hist max DD | turnover/yr | "
          "forward return | forward SPY | forward relative | expected rel. to date (2024-26 window) "
          "| regime | days | status |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in doc["rows"]:
        tv = r.get("turnover_annual")
        L.append(
            f"| `{r['book']}` | `{r['rule']}` | {r.get('gate') or 'n/a'} | {_p(r['dev_cagr'])} | "
            f"{_p(r['sealed_cagr'])} ({_p(r['sealed_spy_cagr'])}) | {_p(r['max_dd'])} | "
            f"{(f'{tv:.1f}x' if isinstance(tv, (int, float)) else 'n/a')} | "
            f"{_p(r['forward_return'], 2)} | {_p(r['forward_spy'], 2)} | "
            f"{_p(r['forward_relative'], 2)} | {_p(r['expected_relative_to_date'], 2)} | "
            f"{r['regime_now']} | {r['days_since_inception']} | {r['status']} |")
    gl = doc.get("gate_summary") or {}
    if gl:
        L += ["", f"**The freeze gate** (`scripts/night_backtest_factory.py::freeze_gate`): "
                  f"{gl.get('n_pass', 0)} of {gl.get('n_books', 0)} books PASS; the rest are "
                  "CONTROLs -- they accrue forward, and they are not headline books. "
                  + (f"Failing ONLY on timing (picks on bars older than 1 session at the decision): "
                     f"{', '.join('`' + b + '`' for b in gl.get('pass_but_timing') or [])}. "
                     if gl.get("pass_but_timing") else "")
                  + 
                  f"Rule: {gl.get('rule')}. Booleans per book: `{gl.get('log')}`. "
                  f"{gl.get('todo', '')}"]
    vd = doc.get("voided_before_entry") or []
    L += ["", "## Voided before entry (never graded, never deleted)", ""]
    if not vd:
        L.append("None.")
    for v in vd:
        L.append(f"- `{v.get('name')}` (`{v.get('book_id')}`), voided {v.get('voided_utc')} by "
                 f"{v.get('who')}: {v.get('reason')}. Its `__ew` twin stays as the strategy test "
                 "(the row marked STRATEGY TEST above).")
    L += ["", "## Investigations (never deleted)", ""]
    inv = ([{"book": r["book"], **r["investigation"]} for r in doc["rows"] if r.get("investigation")]
           + list(doc.get("carried_investigations", [])))
    L.append(f"The rule: a book whose forward relative return trails its 2024-26-window expectation by "
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
    reg_tab = doc.get("semis_umd_regression") or {}
    L += ["", "## Semis and momentum decomposition of the 2024-26 top-10", ""]
    if reg_tab.get("status") != "OK":
        L.append(f"`{reg_tab.get('status', 'NOT_RUN')}`: {reg_tab.get('why', '')}")
    else:
        L += [reg_tab["note"], "", "| rule | n | alpha/mo | t(alpha) | beta SPY | beta SMH | beta MOM | R2 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for x in reg_tab["rows"]:
            L.append(f"| `{x['id']}` | {x['n']} | {_p(x['alpha'], 2)} | {x['t_alpha']:.2f} | "
                     f"{x['beta_spy']:.2f} | {x['beta_smh']:.2f} | {x['beta_mom']:.2f} | {x['r2']:.2f} |")
    L += ["", "## How to read it", "",
          f"- **dev** = monthly periods entered 2017-02 → 2023-12; the **{lab}** = entered from "
          f"2024-01-01 ({fx.get('n_sealed', 32)} monthly blocks). The split was declared in "
          "`strategy_library.py` before the ranking, but every rule was written in 2026 and the "
          f"board sorts on this window, so it is not a holdout. Ranking {fx.get('n_cells', 'n')} "
          f"cells on {fx.get('n_sealed', 32)} months selects luck as readily as skill; no rule "
          "reaches DSR 0.95.",
          "- **expected rel. to date** = ((1 + 2024-26 CAGR) / (1 + SPY 2024-26 CAGR))^(sessions/252) − 1: "
          "what the selection window says the book should be ahead of SPY by now -- the window the "
          "row was selected on, so it is an optimistic expectation.",
          "- **gate** = the freeze rule as code: PASS, or CONTROL(the failed booleans). A CONTROL "
          "row accrues forward like any book and is never a headline.",
          "- A forward number is net of the entry half of the band round trip "
          "(`llm_portfolio.grade`), priced from the open of the session after the freeze.",
          "- `lib_*_2026-09-26` books without `_sealed` were frozen by the 02:00 factory from its "
          "DSR top-10; `_sealed` books were frozen from the 2024-26 sort (the suffix is the "
          "2026-09-26 name, kept because a book's name is part of its id); `FORWARD-ONLY` rows "
          "have no backtest on this panel.",
          "- The 2024-26 top-10 series were recomputed from raw bars "
          f"(`{doc.get('replication') or 'not yet run'}`): a re-implementation of the arithmetic "
          "from raw bars, not an independent engine (shares holdings, fills, cost formula).", ""]
    return "\n".join(L)


def _facts_or_none(board: dict) -> Optional[dict]:
    try:
        return library_facts(board)
    except (KeyError, ValueError, TypeError):
        return None


def _ols(y: np.ndarray, X: np.ndarray) -> dict:
    """OLS with an intercept; the intercept's classical t."""
    n = len(y)
    A = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    dof = n - A.shape[1]
    s2 = float(resid @ resid) / dof if dof > 0 else float("nan")
    cov = s2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"beta": beta, "t": beta / se, "r2": 1.0 - float(resid @ resid) / ss_tot if ss_tot else float("nan")}


def semis_umd_regression(board: dict, bars: Optional[pd.DataFrame] = None, *,
                         rep_doc: Optional[dict] = None, smh: Optional[pd.DataFrame] = None,
                         etf: str = "SMH") -> dict:
    """Review idea 1: regress each 2024-26 top-10 monthly net series (the
    selection-window blocks) on SPY, SMH and the library's own `mom_12_1`
    equal-weight series; print the intercept and its t. SMH is looked up in the
    bars panel and the `global_prices` cache; absent -> `SMH_NOT_IN_PANEL`."""
    if rep_doc is None:
        rid = board.get("run_id")
        cand = ([LIB_DIR / f"top10_for_replication_{rid}.json"] if rid else []) + \
            sorted(LIB_DIR.glob("top10_for_replication_*.json"))[-1:]
        path = next((c for c in cand if c.exists()), None)
        if path is None:
            return {"status": "NO_REPLICATION_FILE", "why": "no top10_for_replication_*.json"}
        rep_doc = json.loads(path.read_text(encoding="utf-8"))
    mom = (rep_doc.get("reference_series") or {}).get("mom_12_1")
    if not mom:
        return {"status": "NO_MOM_REFERENCE",
                "why": "the top-10 file predates `reference_series.mom_12_1` (factory run id >= this build)"}
    if smh is None:
        frames = []
        if bars is not None and len(bars):
            frames.append(bars[bars["symbol"] == etf])
        try:
            from backend.services import global_prices as GP
            g = GP.read_cache()
            if len(g):
                frames.append(g[g["symbol"] == etf])
        except Exception:                                  # noqa: BLE001 -- absence is the answer
            pass
        smh = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if smh is None or not len(smh):
        return {"status": "SMH_NOT_IN_PANEL",
                "why": (f"{etf} has no bars in the survivorship-free panel or the global_prices "
                        "cache; the regression is not run rather than run without the sector leg")}
    smh = smh.assign(date=pd.to_datetime(smh["date"])).sort_values("date").drop_duplicates("date")
    sd = smh["date"].to_numpy()
    so = smh["open"].astype(float).to_numpy()

    def period(entry: str, nxt: Optional[str]) -> Optional[float]:
        if nxt is None:
            return None
        a = int(np.searchsorted(sd, np.datetime64(pd.Timestamp(entry)), "left"))
        b = int(np.searchsorted(sd, np.datetime64(pd.Timestamp(nxt)), "left"))
        if a >= len(sd) or b >= len(sd) or b <= a:
            return None
        return float(so[b] / so[a] - 1.0)
    mom_by = {x["date"]: x["net"] for x in mom}
    out = []
    for r in rep_doc["rows"]:
        ser = r["monthly_return_series"]
        ys, xs = [], []
        for j, x in enumerate(ser):
            if not x["window"].startswith("sealed") or x.get("spy") is None:
                continue
            nxt = ser[j + 1]["entry"] if j + 1 < len(ser) else None
            sm = period(x["entry"], nxt)
            mm = mom_by.get(x["date"])
            if sm is None or mm is None:
                continue
            ys.append(x["net"])
            xs.append([x["spy"], sm, mm])
        if len(ys) < 12:
            out.append({"id": r["id"], "n": len(ys), "status": "TOO_FEW_BLOCKS"})
            continue
        f = _ols(np.array(ys), np.array(xs))
        out.append({"id": r["id"], "n": len(ys), "alpha": float(f["beta"][0]),
                    "t_alpha": float(f["t"][0]), "beta_spy": float(f["beta"][1]),
                    "beta_smh": float(f["beta"][2]), "beta_mom": float(f["beta"][3]),
                    "r2": float(f["r2"])})
    ok = [x for x in out if "alpha" in x]
    return {"status": "OK" if ok else "TOO_FEW_BLOCKS", "rows": ok, "etf": etf,
            "note": (f"net monthly return ~ a + b1 SPY + b2 {etf} + b3 mom_12_1 (library, k=20 ew), "
                     "over the 2024-26 selection-window blocks. An intercept that dies after "
                     f"{etf} and momentum means the window rewarded a sector, not a mechanism.")}


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
           board_path: Optional[str] = None, earnings: Optional[dict] = None,
           semis: Optional[dict] = None) -> dict:
    from backend.services import llm_portfolio as LP
    today = today or date.today()
    if board is None:
        bp, board = latest_leaderboard()
        board_path = _relpath(bp)
    books = LP.read_books(include_voided=True) if books is None else books
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
    gates = gates_for(lib, board, bars, earnings=earnings)
    rows = build_rows(lib, board, bars, today=today, regime_now=reg, prior=prior, gates=gates)
    open_now = {r["book"] for r in rows if r.get("investigation")}
    carried = [v for k, v in load_investigations(out_dir).items() if k not in open_now]
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = out_dir / f"bridge_{today}.json"
    rep = latest_replication(LIB_DIR, board.get("run_id"))
    from scripts import night_backtest_factory as F
    voided = [{"book_id": b["book_id"], "name": b.get("name"), **{
        k: b["void"].get(k) for k in ("reason", "voided_utc", "who")}}
        for b in lib if b.get("void")]
    heads = [r for r in rows if not r.get("strategy_test_for_voided")]
    gate_log = out_dir / f"freeze_gate_{today}.json"
    gate_doc = {"schema": "bridge/freeze_gate/1", "date": str(today),
                "leaderboard": board_path, "rule": F.freeze_gate.__doc__.split("\n")[0],
                "notes": [F.GATE_TODO], "gates": gates}
    doc = {"schema": "bridge/1", "date": str(today), "licence": "PRODUCT_EXPERIMENT",
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "git_head": git_head(),
           "leaderboard": board_path or "(in-memory board)", "receipt_json": _relpath(receipt),
           "replication": _relpath(rep) if rep else None,
           "library_facts": _facts_or_none(board),
           "dev_selected": board.get("dev_selected_sealed_evaluated"),
           "n_forward_graded": sum(1 for r in rows if r.get("sessions_since_entry")),
           "voided_before_entry": voided,
           "gate_summary": {"n_books": len(heads),
                            "n_pass": sum(1 for r in heads if r.get("gate_verdict") == "PASS"),
                            "pass_but_timing": [r["book"] for r in heads
                                                if r.get("gate_verdict") == "CONTROL"
                                                and (gates.get(r["book"]) or {}).get("reasons") == ["STALE_BARS"]],
                            "rule": gates and next(iter(gates.values())).get("rule"),
                            "log": _relpath(gate_log), "todo": F.GATE_TODO},
           "semis_umd_regression": (semis if semis is not None
                                    else semis_umd_regression(board, bars)),
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
    gate_log.write_text(json.dumps(gate_doc, indent=1, default=str), encoding="utf-8")
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
    # the LUCK BAR is the random-k controls only; a diagnostic control is a rule's returns
    ctrl = [c for c in (board.get("controls") or [])
            if c.get("family") == "control" and c.get("sealed_vs_spy") is not None]
    return {"n_rules": len(rows), "n_beat": sum(1 for x in sv if x > 0),
            "median_sealed_vs_spy": float(np.median(sv)),
            "best_dsr": best["dsr"], "best_dsr_id": best["id"],
            "n_cells": board["multiplicity"]["n_cells_looked_at"],
            "n_families": board["multiplicity"]["n_families"],
            "n_sealed": board["objective"]["n_sealed_months"],
            "ctrl_lo": min(c["sealed_vs_spy"] for c in ctrl) if ctrl else None,
            "ctrl_hi": max(c["sealed_vs_spy"] for c in ctrl) if ctrl else None,
            "both": both_windows(board)}


def readme_section(board: dict, board_path: str, *, git_hash: Optional[str] = None,
                   bridge: Optional[dict] = None, replication: Optional[str] = None,
                   bridge_path: Optional[str] = None) -> str:
    """The README section, rendered from the leaderboard receipt (plus the
    bridge receipt for the gate/void lines and the re-implementation path)."""
    from backend.services import strategy_library as SL
    f = library_facts(board)
    lab = SL.SELECTION_WINDOW_LABEL
    lbmd = "backend/data/optimus/strategy_library/LEADERBOARD.md"
    top = board["top_by_sealed_vs_spy"][:10]
    gh = git_hash or git_head()
    dse = board.get("dev_selected_sealed_evaluated") or {}
    L = [README_HEADING, "",
         "> 🔵 **HINDSIGHT BACKTEST — NOT FORWARD PERFORMANCE.** Every rule below was written "
         "down on 2026-09-26, after every month it is scored on. The quotable record starts at "
         f"registration. Receipt for every number in this section: `{board_path}` at commit "
         f"`{gh}` (run `{board.get('run_id', 'n/a')}`; rendered as `{lbmd}`, which the next run "
         "refreshes -- the receipt it cites is never overwritten); forward results: `docs/BRIDGE.md`.", "",
         f"The strategy library ({f['n_rules']} rules in {f['n_families']} families, "
         f"{f['n_cells']} cells at k = 10/20/50 plus each rule's own k) was run on survivorship-free "
         "bars net of a band round-trip cost, with a split declared in code before the ranking: "
         f"**dev** = monthly periods entered through 2023-12-31, and the **{lab}** = entered from "
         f"2024-01-01 ({f['n_sealed']} monthly blocks). Every rule was written in 2026, so the "
         "second window is where the board SORTS, not a holdout. Sorted by net return vs SPY in "
         f"that window (`{board_path}`, `top_by_sealed_vs_spy`):", "",
         f"| rule (k=20) | dev CAGR | SPY dev | 2024-26 CAGR | SPY 2024-26 | 2024-26 − SPY | DSR ({f['n_cells']} cells) "
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
                f"{_p(f['ctrl_lo'])} to {_p(f['ctrl_hi'])} vs SPY in the 2024-26 window: that is "
                f"the luck bar (`{board_path}`, `controls`, family `control`).")
    L += ["", ctrl, ""]
    t10 = dse.get("top_10") or {}
    sp = dse.get("spearman_dev_vs_selection_window") or {}
    md = dse.get("mde") or {}
    if t10:
        L.append(
            f"- **The one out-of-sample number the backtest holds:** choosing the top 10 rules by "
            f"dev (pre-2024) results alone gave **{t10['mean_selection_window_vs_spy']*100:+.1f} pp/yr** "
            f"mean vs SPY in the {lab} (median **{t10['median_selection_window_vs_spy']*100:+.1f} pp**; "
            f"{t10['n_beat_spy']} of {t10['n']} beat SPY); dev-to-2024-26 rank Spearman "
            f"**{sp.get('rho', float('nan')):.2f}** over {sp.get('n')} rules"
            + (f"; at a median active sigma of {md['active_sigma_monthly_median']*100:.1f}%/month, "
               f"{md['n_blocks']} blocks give an MDE of {md['mde_monthly_80pct_power']*100:.1f}%/month "
               "at 80% power -- the window can kill a rule, not certify one"
               if "mde_monthly_80pct_power" in md else "")
            + f" (`{board_path}`, `dev_selected_sealed_evaluated`). {FIRST_READING}")
    both_n = dse.get("n_beat_spy_in_both_windows")
    strict_n = dse.get("n_beat_spy_in_both_windows_top5_lt_0_6_dd_gt_m40")
    L += [f"- **Nothing passes the multiplicity bar (best DSR {f['best_dsr']:.2f} at {f['n_cells']} "
          f"cells, `{f['best_dsr_id']}`, vs 0.95).** Ranking {f['n_cells']} cells on "
          f"{f['n_sealed']} months of the 2024-26 window selects luck as readily as skill "
          f"(`{board_path}`, `multiplicity`).",
          f"- **{f['n_beat']} of {f['n_rules']} rules beat SPY in the 2024-26 window, median "
          f"{f['median_sealed_vs_spy']*100:+.1f}%** (`{board_path}`, `all_rows[].sealed_vs_spy`).",
          (f"- **{both_n} of {f['n_rules']} rules beat SPY in both windows** (dev and 2024-26); "
           f"{strict_n} of them also have a top-5-month share < 0.6 and max DD better than -40%. "
           if both_n is not None else "- ")
          + f"Only {', '.join(f'`{i}`' for i in f['both'])} are in both the 2024-26 top-10 and "
          "the full-window DSR top-10. The 2024-26 top rows with a top-5-month share near or above "
          f"1 made their return in a handful of months, and several were flat or negative in dev "
          f"(`{board_path}`)."]
    gs = (bridge or {}).get("gate_summary") or {}
    vd = (bridge or {}).get("voided_before_entry") or []
    booked = {r.get("rule") for r in (bridge or {}).get("rows", [])} | {
        rule_id_of({"name": v.get("name")}) for v in vd}
    top_ids = [r["id"] for r in top]
    have = [i for i in top_ids if i in booked] if bridge else top_ids
    lack = [i for i in top_ids if i not in have]
    fwd = (f"- **{len(have)} of these {len(top_ids)} rows have a $1M forward paper book frozen "
           "2026-09-26; entry is the 2026-09-28 open**"
           + (f" ({', '.join(f'`{i}`' for i in lack)} entered this top-10 after the freeze and "
              "have none)" if lack else "")
           + " (books in `backend/data/optimus/llm_portfolio/books.jsonl`, "
           "`lib_<id>_sealed_2026-09-26` with ew / sector-ETF / SPY / random-same-band twins; "
           "`mom_12_1_q`'s is the 02:00 factory's `lib_mom_12_1_q_2026-09-26`, same names; freeze "
           "log `backend/data/optimus/bridge/freeze_2026-09-26.json`). `docs/BRIDGE.md` shows "
           "expectation vs result.")
    if gs:
        fwd += (f" The freeze gate (selection, construction and timing booleans, "
                f"`{gs.get('log')}`) passes {gs.get('n_pass')} of {gs.get('n_books')} library "
                f"books (bridge receipt `{bridge_path}`); the rest are CONTROLs, not headlines.")
    for v in vd:
        fwd += (f" `{v.get('name')}` was **voided before entry** ({v.get('reason')}); its `__ew` "
                "twin is the strategy test.")
    L.append(fwd)
    L.append("- The 2024-26 top-10 monthly series were recomputed from their holdings and the raw "
             "bars -- a re-implementation of the arithmetic from raw bars, not an independent "
             f"engine (shares holdings, fills, cost formula): `{replication or 'not yet run'}`.")
    L += ["", "### History: the timing strategy (not the library)", "",
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
        n_cells = (board.get("multiplicity") or {}).get("n_cells_looked_at")
        note = (f"Backtest (HINDSIGHT, registered {r['first_registered_utc'][:10]}): dev CAGR "
                f"{_p(r['dev_cagr'])} (SPY {_p(r['dev_spy_cagr'])}), 2024-26 selection-window CAGR "
                f"{_p(r['sealed_cagr'])} (SPY {_p(r['sealed_spy_cagr'])}) over "
                f"{r['n_sealed_months']} months, 2024-26 DSR {r['sealed_dsr']} at n={n_cells}, "
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


def gate_book(bk: dict, board: dict, bars: pd.DataFrame, *, today: date,
              books: list[dict]) -> dict:
    """Run the freeze gate on a library book; a failure becomes a CONTROL
    (`__control`, `kind: control`) carrying every boolean in `freeze_gate`."""
    from scripts import night_backtest_factory as F
    by_id = {r["id"]: r for r in board.get("all_rows", [])}
    rid = bk["model"].split(":")[-1]
    row = by_id.get(rid)
    fam = (row or {}).get("family")
    fam_n = sum(1 for b in books if b.get("kind") == "personal" and not b.get("void")
                and str(b.get("name", "")).startswith("lib_") and str(b.get("asof")) == str(today)
                and (by_id.get(rule_id_of(b)) or {}).get("family") == fam
                and (b.get("freeze_gate") or {}).get("verdict", "PASS") == "PASS")
    cal = pd.DatetimeIndex(sorted(bars.loc[bars["symbol"] == "SPY", "date"].unique()))
    g = F.freeze_gate(row, book_weights(bk), bars, cal, decision_date=today,
                      family_books_before=fam_n)
    out = {**bk, "freeze_gate": g}
    out["strategy"] = (out["strategy"] + f" Freeze gate: {g['label']}.")[:2000]
    if g["verdict"] != "PASS":
        out["name"] = bk["name"] + "__control"
        out["kind"] = "control"
    return out


def cmd_freeze(a) -> int:
    from backend.services import llm_portfolio as LP
    from scripts.llm_portfolio import freeze_with_twins
    today = date.fromisoformat(a.today) if a.today else date.today()
    _bp, board = latest_leaderboard()
    books = LP.read_books(include_voided=True)          # a voided book is never re-frozen
    names = {b.get("name") for b in books}
    ids = [i for i in library_targets(board) if f"lib_{i}_sealed_{today}" not in names
           and f"lib_{i}_sealed_{today}__control" not in names]
    from scripts import night_backtest_factory as F
    log: dict = {"date": str(today), "library": {}, "probe": {}, "notes": [F.GATE_TODO]}
    to_freeze: list[dict] = []
    bars = None
    if ids and not a.skip_library:
        print(f"building the factory panel for {ids} ...", flush=True)
        panel, bars = build_library_panel()
        for bk in library_books(board, panel, today=today, ids=ids):
            rid = bk["model"].split(":")[-1]
            dup = [b for b in books if b.get("kind") != "twin" and rule_id_of(b) == rid
                   and str(b.get("name", "")).replace("__control", "").endswith(str(today))
                   and _same_names(b, bk)]
            if dup:
                log["library"][rid] = {"status": "ALREADY_FROZEN_TODAY_SAME_POSITIONS",
                                       "book": dup[0]["name"]}
                print(f"  {rid}: already frozen today as {dup[0]['name']} with the same names; skipped")
                continue
            bk = gate_book(bk, board, bars, today=today, books=books + to_freeze)
            log["library"][bk["name"]] = {"gate": bk["freeze_gate"]}
            print(f"  FREEZE GATE {bk['name']}: {bk['freeze_gate']['label']}")
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
        tgt_ = log["probe"] if bk["name"].startswith(PROBE_BOOKS) else log["library"]
        tgt_.setdefault(bk["name"], {}).update(
            {"worst_case": wc, "weights": {k: round(v, 6) for k, v in w.items()}})
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
        brs = sorted(BRIDGE_DIR.glob("bridge_*.json"))
        bridge = json.loads(brs[-1].read_text(encoding="utf-8")) if brs else None
        rp = latest_replication(LIB_DIR, board.get("run_id"))
        gh = git_head()
        p.write_text(splice_readme(txt, readme_section(
            board, _relpath(bp), git_hash=gh, bridge=bridge,
            replication=_relpath(rp) if rp else None,
            bridge_path=_relpath(brs[-1]) if brs else None)), encoding="utf-8")
        print(f"-> {p} section '{README_HEADING}' rewritten from {_relpath(bp)} at {gh}")
        return 0
    return cmd_report(a)


if __name__ == "__main__":
    raise SystemExit(main())
