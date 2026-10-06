"""The regret ledger: frozen alternatives priced on real bars (chunk C11,
2026-10-06; rebuilt the same night after the adversarial review,
`docs/reviews/REVIEW_2026-10-06_C11_DECISION_STORY_REGRET.md`).

`decision_story.freeze_plan` writes, at decision time, what the plan did and
what it could have done instead, keyed on the XNYS SESSION whose price it could
first trade at. This module waits for each horizon (5/21/63 sessions) and
prices the frozen alternatives on the survivorship-free daily panel
(`xs_ranker.load_bars` over `survivorship_free_paths`), net of the liquidity-band
cost model the plan's ranker uses (`xs_ranker.round_trip_bps`). Zero cost is
refused.

WHAT THE REVIEW CHANGED, AND WHY
--------------------------------
* F1. No regret is a `max` over alternatives picked after the outcome. Under a
  zero-drift random walk a best-of-two is positive on every draw (+5.6 bps
  sizing on 100% of draws in the review's probe). Every type is now a SIGNED
  difference of two frozen alternatives, mean zero under the null apart from
  a deterministic cost term, and `test_every_regret_type_is_mean_zero_under_the_null`
  pins it over 1,000 draws. "Enter one session earlier" is gone: the plan could
  not have taken it.
* F2. Abstentions are never summed into one dollar line. They are four cohorts
  that answer four questions; each cohort's book is scaled to the PROBE gross cap
  and reported as net EXCESS over SPY and over a same-liquidity-band control, by
  session (date block), with t and MDE.
* F3. One observation per (session, ticker); n counts sessions.
* F6. A hold window containing a step larger than max(25%, 8 sigma) is REFUSED
  (a raw split or a two-basis splice), never graded OK. Returns are computed on
  ONE basis (one panel, entry and exit from the same series), and the panel's
  entry price against the frozen decision-time quote is printed as
  `basis_factor`.
* F7. `mdc_news_tilt` = utility(plan + SHADOW_NEWS_v0 tilt) - utility(plan).
* F8. Selection regret is ONE row per (session, selector): the taken book vs
  the next-ranked name not taken, each at its own cost band.

CONVENTIONS (printed on every receipt)
--------------------------------------
* Entry at the reference session's OPEN or CLOSE (`entry_basis` on the story;
  always a price that printed after the decision). Exit at the close h sessions
  later: h full sessions of exposure.
* P&L of weight w with held weight w0: ``w*r - (|w - w0| + |w|) * rt/2``.
* Every regret = outcome(alternative) - outcome(actual); positive means the
  alternative would have done better. Signed diagnostics, not reward signals.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend import config as _cfg
from backend.services import decision_story as DS

logger = logging.getLogger(__name__)

REGRET_SUBDIR = "regret"
TRUST_SESSIONS = 63
REGRET_TYPES = ("direction_regret", "sizing_regret", "timing_regret",
                "exit_regret", "abstention_regret")
SESSION_TYPES = ("selection_regret",)
COHORTS = ("picked_blocked", "shortlist_not_taken", "ranker_pool", "held_resize", "acted")
#: A step inside a hold window larger than BOTH of these is a basis break
#: (raw split, splice), not a return: the row is REFUSED (review F6).
BREAK_ABS_LOG = 0.25
BREAK_SIGMA = 8.0
#: The panel's entry price vs the frozen decision-time quote: printed above this.
BASIS_NOTE_LOG = 0.15
MDE_Z = 2.8          # 80% power, 5% two-sided


class CostRefused(ValueError):
    """A grade was about to be priced at zero cost."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pnl(w: float, ret: float, *, w_held: float, rt_bps: float) -> float:
    """Net P&L as a fraction of equity. Refuses a non-positive cost."""
    if not (rt_bps and rt_bps > 0):
        raise CostRefused(f"round trip {rt_bps!r} bps: costs are never zero")
    half = float(rt_bps) / 2.0 / 1e4
    return float(w) * float(ret) - (abs(float(w) - float(w_held)) + abs(float(w))) * half


# ───────────────────────────────── the window ───────────────────────────────

def series_of(bars: Any, sym: str) -> dict:
    sub = bars[bars["symbol"] == sym]
    if sub.empty:
        return {"dates": [], "open": [], "close": [], "volume": []}
    return {"dates": [d.strftime("%Y-%m-%d") for d in sub["date"]],
            "open": [float(x) for x in sub["open"]],
            "close": [float(x) for x in sub["close"]],
            "volume": [float(x) for x in sub["volume"]] if "volume" in sub else []}


def hold_window(s: dict, session: str, basis: str, h: int, *, asof_cut: str) -> dict:
    """Entry at `session`'s open/close, exit at the close h sessions of exposure
    later, both from ONE series. Also the next-open entry (same exit) for the
    timing diagnostic. REFUSED on a basis break inside the window."""
    dates, op, cl = s["dates"], s["open"], s["close"]
    i0 = next((i for i, d in enumerate(dates) if d >= session), None)
    if i0 is None:
        return {"matured": False, "status": "PENDING", "why": "reference session not yet in the panel"}
    usable = [i for i, d in enumerate(dates) if d <= asof_cut]
    last = usable[-1] if usable else -1
    ix = i0 + int(h) - (1 if basis == "open" else 0)
    if ix > last:
        return {"matured": False, "status": "PENDING",
                "why": f"{max(0, last - i0)} of {h} sessions elapsed"}
    entry = op[i0] if basis == "open" else cl[i0]
    if not (entry and entry > 0 and cl[ix] > 0):
        return {"matured": True, "status": "REFUSED", "why": "non-positive price in the window"}
    # the window's steps, entry -> each close -> exit
    path = [entry] + cl[i0:ix + 1] if basis == "open" else cl[i0:ix + 1]
    steps = [math.log(b / a) for a, b in zip(path[:-1], path[1:]) if a > 0 and b > 0]
    pre = [math.log(cl[i] / cl[i - 1]) for i in range(max(1, i0 - 63), i0) if cl[i - 1] > 0 and cl[i] > 0]
    sigma = float(np.std(pre, ddof=1)) if len(pre) >= 10 else None
    lim = max(BREAK_ABS_LOG, BREAK_SIGMA * sigma) if sigma else BREAK_ABS_LOG
    big = [x for x in steps if abs(x) > lim]
    out = {"matured": True, "entry_date": dates[i0], "exit_date": dates[ix],
           "entry_px": entry, "exit_px": cl[ix], "ret": cl[ix] / entry - 1.0,
           "sigma_d": sigma, "max_abs_step_log": max((abs(x) for x in steps), default=0.0)}
    if big:
        out.update(status="REFUSED",
                   why=(f"a step of {max(big, key=abs):+.3f} log inside the hold window exceeds "
                        f"max({BREAK_ABS_LOG}, {BREAK_SIGMA}σ): a raw split or a two-basis "
                        f"splice, not a return. Not graded"))
        return out
    out["status"] = "OK"
    out["review_flag"] = bool(sigma and abs(math.log(1 + out["ret"])) > BREAK_SIGMA * sigma * math.sqrt(h))
    j = i0 + 1
    out["ret_next_open"] = (cl[ix] / op[j] - 1.0) if (j <= ix and op[j] > 0) else None
    return out


def _mdv_from_panel(s: dict, before: str, n: int = 60) -> float | None:
    dv = [c * v for d, c, v in zip(s["dates"], s["close"], s["volume"] or [])
          if d < before and c > 0 and v >= 0][-n:]
    return float(np.median(dv)) if len(dv) >= 10 else None


# ───────────────────────────── the per-name regrets ───────────────────────────

def row_regrets(d: dict, a_by: dict, win: dict, *, rt_bps: float,
                bench_ret: float | None) -> dict:
    """PURE. Every per-name regret for one matured (decision, horizon), signed:
    outcome(alternative) - outcome(actual). `_gross` drops the cost term (the
    part that must be mean zero under the null); `_excess` is gross over the
    benchmark."""
    r = float(win["ret"])
    w0 = float(d.get("held_weight") or 0.0)
    eff = float(d.get("effective_weight") or 0.0)
    act = d["action"]
    cohort = d.get("cohort")

    def W(name: str) -> float | None:
        a = a_by.get(name)
        return None if (a is None or a.get("target_weight") is None) else float(a["target_weight"])

    out: dict = {}

    def put(kind: str, w_alt: float | None, w_act: float, r_alt: float = r, r_act: float = r) -> None:
        if w_alt is None:
            out[kind] = out[f"{kind}_gross"] = out[f"{kind}_excess"] = None
            return
        out[kind] = (pnl(w_alt, r_alt, w_held=w0, rt_bps=rt_bps)
                     - pnl(w_act, r_act, w_held=w0, rt_bps=rt_bps))
        out[f"{kind}_gross"] = w_alt * r_alt - w_act * r_act
        out[f"{kind}_excess"] = (None if bench_ret is None else
                                 w_alt * (r_alt - bench_ret) - w_act * (r_act - bench_ret))
    for k in REGRET_TYPES:
        out[k] = out[f"{k}_gross"] = out[f"{k}_excess"] = None
    if act in ("BUY", "SELL"):
        put("direction_regret", W("no_trade"), eff)
        put("sizing_regret", W("buy_default"), eff)
        rn = win.get("ret_next_open")
        if rn is not None:
            # timing of the TRADED delta only: enter at the next open vs the
            # reference entry, same exit; costs identical, so net == gross
            dw = eff - w0
            out["timing_regret"] = out["timing_regret_gross"] = dw * (float(rn) - r)
            out["timing_regret_excess"] = dw * (float(rn) - r)
    if w0 > 0:
        put("exit_regret", W("hold") if act == "EXIT" else W("exit_now"), eff)
    if act in DS.ABSTENTION_ACTIONS and cohort != "held_resize":
        cf = W("plan_full") if cohort == "picked_blocked" else W("buy_default")
        put("abstention_regret", cf, eff)
    return out


# ───────────────────────────────── loading ────────────────────────────────────

def _load_frozen(story_dir: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    stories: list[dict] = []
    alts: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(Path(story_dir).glob("stories_*.jsonl")):
        stories += [r for r in DS.read_jsonl(p) if r.get("kind") == "decision"]
    for p in sorted(Path(story_dir).glob("alternatives_*.jsonl")):
        for r in DS.read_jsonl(p):
            alts[str(r.get("decision_id"))].append(r)
    # ONE observation per (session, ticker): the last decision frozen for it
    final: dict[tuple, dict] = {}
    for s in sorted(stories, key=lambda r: str(r.get("built_utc") or "")):
        final[(str(s.get("session") or s["asof"]), s["ticker"])] = s
    return list(final.values()), alts


def _load_universe(lo: str, hi: str) -> Any:
    """The whole panel between two dates (controls only), survivorship-free."""
    import pandas as pd
    from backend.services import xs_ranker as XR
    frames = []
    for p in XR.survivorship_free_paths():
        frames.append(pd.read_parquet(
            p, columns=["symbol", "date", "open", "close", "volume"],
            filters=[("date", ">=", pd.Timestamp(lo)), ("date", "<=", pd.Timestamp(hi))]))
    u = pd.concat(frames, ignore_index=True)
    u["date"] = pd.to_datetime(u["date"])
    return u.drop_duplicates(subset=["symbol", "date"], keep="first")


class _Control:
    """Equal-weight mean return of every panel name in the same liquidity band
    over the same window: the expectation of a random same-band portfolio."""

    def __init__(self, universe: Any) -> None:
        import pandas as pd
        u = universe.copy()
        u["date"] = pd.to_datetime(u["date"])
        self.close = u.pivot_table(index="date", columns="symbol", values="close", aggfunc="first")
        self.open = u.pivot_table(index="date", columns="symbol", values="open", aggfunc="first")
        dv = (u.assign(dv=u["close"] * u["volume"])
              .pivot_table(index="date", columns="symbol", values="dv", aggfunc="first"))
        self.mdv = dv.rolling(60, min_periods=10).median().shift(1)
        self.cache: dict = {}

    def ret(self, band: str, entry_date: str, basis: str, exit_date: str) -> tuple[float | None, int]:
        from backend.services import xs_ranker as XR
        key = (band, entry_date, basis, exit_date)
        if key in self.cache:
            return self.cache[key]
        import pandas as pd
        e, x = pd.Timestamp(entry_date), pd.Timestamp(exit_date)
        if e not in self.close.index or x not in self.close.index:
            self.cache[key] = (None, 0)
            return self.cache[key]
        mdv = self.mdv.loc[e]
        names = [s for s, v in mdv.items() if np.isfinite(v) and XR.liquidity_band(float(v)) == band]
        ent = (self.open if basis == "open" else self.close).loc[e, names]
        ex = self.close.loc[x, names]
        r = (ex / ent - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
        self.cache[key] = ((float(r.mean()), int(len(r))) if len(r) else (None, 0))
        return self.cache[key]


# ───────────────────────────────── grading ────────────────────────────────────

def grade_due(asof: str | None = None, *, story_dir: Path | None = None,
              bars: Any = None, bars_paths: list[Path] | None = None,
              universe: Any = None, out_dir: Path | None = None, write: bool = True,
              run_id: str | None = None) -> dict:
    """Price every matured (decision, horizon) and write `regret_<run_id>.json`.

    `asof` bounds the bars read (nothing later is used); default today (UTC).
    `bars` (tests) also serves as the control universe unless `universe` is
    given. Re-running is safe: each receipt has its own run id."""
    from backend.services import xs_ranker as XR
    story_dir = Path(story_dir or DS.STORY_DIR)
    asof = asof or _now().date().isoformat()
    run_id = run_id or (_now().strftime("%Y%m%dT%H%M%SZ") + "_" + DS._h(asof, n=6))
    out_dir = Path(out_dir or (story_dir / REGRET_SUBDIR))
    decisions, alts = _load_frozen(story_dir)
    gross_cap = float(_cfg.PROBE_GROSS_CAP)
    bench = str(_cfg.DECISION_BENCHMARK_SYMBOL)
    receipt: dict = {
        "receipt": "regret_ledger", "schema": 2, "run_id": run_id, "asof": asof,
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "story_dir": str(story_dir), "n_decisions_frozen": len(decisions),
        "live_stories": DS.live_stories_on_disk(story_dir),
        "conventions": {
            "key": "one observation per (XNYS session, ticker); n counts sessions",
            "entry": "the reference session's open or close (story.entry_basis), a price "
                     "printed after the decision",
            "exit": "close after h sessions of exposure, same series as the entry",
            "pnl": "w*r - (|w - w_held| + |w|) * round_trip/2 (fraction of equity)",
            "regret": "outcome(alternative) - outcome(actual): signed, never a max",
            "cohorts": "each scaled to PROBE_GROSS_CAP; net excess over SPY and over the "
                       "same-band equal-weight panel mean; by session with t and MDE",
            "cost_model": "xs_ranker.round_trip_bps (frozen mdv, else the panel's 60-bar "
                          "median before the session); zero refused",
            "breaks": f"a window step > max({BREAK_ABS_LOG} log, {BREAK_SIGMA} sigma) is REFUSED",
            "bars": "xs_ranker.load_bars(survivorship_free_paths(), symbols=...), cut at asof"},
    }
    if not decisions:
        receipt.update(status="NOTHING_FROZEN", rows=[], refused_rows=[], summary={},
                       line=("no decision story is frozen yet: "
                             f"{receipt['live_stories']['n']} stories on disk"))
        return _write(receipt, out_dir, write)

    syms = {d["ticker"] for d in decisions} | {a["ticker"] for v in alts.values() for a in v}
    syms.add(bench)
    if bars is None:
        try:
            paths = bars_paths or XR.survivorship_free_paths()
            bars = XR.load_bars(paths, symbols=sorted(syms))
            receipt["bars_paths"] = [str(p) for p in paths]
        except Exception as exc:                                   # noqa: BLE001
            receipt.update(status="REFUSED", rows=[], refused_rows=[], summary={},
                           line=f"REFUSED: bars unreadable: {type(exc).__name__}: {str(exc)[:200]}")
            return _write(receipt, out_dir, write)
        if universe is None:
            try:
                lo = (date.fromisoformat(min(str(d.get("session") or d["asof"]) for d in decisions))
                      - timedelta(days=120)).isoformat()
                universe = _load_universe(lo, asof)
            except Exception as exc:                               # noqa: BLE001
                receipt["control_refused"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    elif universe is None:
        universe = bars
    bars = DS.cut_bars(bars, asof)
    ctrl = _Control(DS.cut_bars(universe, asof)) if universe is not None else None
    cache: dict[str, dict] = {}

    def ser(s: str) -> dict:
        if s not in cache:
            cache[s] = series_of(bars, s)
        return cache[s]

    rows: list[dict] = []
    refused: list[dict] = []
    pending = 0
    cohort_cells: dict[tuple, list] = defaultdict(list)       # (session, cohort, h) -> names
    sel_cells: dict[tuple, dict] = {}                         # (session, state, h)
    mdc_sess: dict[tuple, dict] = defaultdict(lambda: {"full": 0.0, "alt": 0.0, "n": 0,
                                                         "n_not_sep": 0, "status": set()})
    for d in decisions:
        a_by = {a["alt"]: a for a in alts.get(d["decision_id"], [])}
        if "actual" not in a_by:
            continue
        session = str(d.get("session") or d["asof"])
        basis = str(d.get("entry_basis") or "close")
        s = ser(d["ticker"])
        mdv = d.get("median_dollar_vol")
        if mdv is None:
            mdv = _mdv_from_panel(s, session)
        rt = float(XR.round_trip_bps(mdv))
        eq = float(d.get("equity") or 0.0)
        for h in DS.HORIZONS:
            win = hold_window(s, session, basis, h, asof_cut=asof)
            if not win["matured"]:
                pending += 1
                continue
            base = {"decision_id": d["decision_id"], "outcome_id": DS.outcome_id(d["decision_id"], h),
                    "attribution_id": DS.attribution_id(d["decision_id"], h),
                    "session": session, "asof": d["asof"], "ticker": d["ticker"], "horizon": h}
            if win["status"] != "OK":
                refused.append({**base, "status": "REFUSED", "why": win["why"]})
                continue
            bw = hold_window(ser(bench), session, basis, h, asof_cut=asof)
            rb = bw.get("ret") if bw.get("status") == "OK" else None
            reg = row_regrets(d, a_by, win, rt_bps=rt, bench_ret=rb)
            band = XR.liquidity_band(mdv)
            c_ret, c_n = (ctrl.ret(band, win["entry_date"], basis, win["exit_date"])
                          if ctrl is not None else (None, 0))
            ref_px = d.get("reference_price")
            bf = (win["entry_px"] / float(ref_px)) if ref_px else None
            row = {**base, "status": "OK", "action": d["action"], "state": d.get("state"),
                   "cohort": d.get("cohort"), "acting": d.get("acting"),
                   "entry_basis": basis, "entry": win["entry_date"], "exit": win["exit_date"],
                   "realised_return": win["ret"], "benchmark_return": rb,
                   "control_return": c_ret, "control_n": c_n, "band": band,
                   "cost_round_trip_bps": rt,
                   "cost_source": "frozen" if d.get("median_dollar_vol") is not None else "panel",
                   "equity": eq, "review_flag": win.get("review_flag"),
                   "basis_factor": bf,
                   "basis_note": (f"the panel's entry price is {bf:.3f}x the decision-time quote "
                                  f"(a later adjustment or a quote/close gap); returns use the "
                                  f"panel's ONE basis" if bf and abs(math.log(bf)) > BASIS_NOTE_LOG
                                  else None)}
            for k, v in reg.items():
                row[f"{k}_bps"] = None if v is None else v * 1e4
            for k in REGRET_TYPES:
                row[f"{k}_usd"] = None if reg.get(k) is None else reg[k] * eq
            rows.append(row)
            # ---- cohort books (review F2) --------------------------------------
            coh = d.get("cohort") or "acted"
            def _w(n: str) -> float | None:                         # noqa: E306
                a = a_by.get(n)
                return None if a is None or a.get("target_weight") is None else float(a["target_weight"])
            cw = (_w("plan_full") if coh in ("picked_blocked", "held_resize") else
                  _w("buy_default") if coh in ("shortlist_not_taken", "ranker_pool") else
                  float(d.get("effective_weight") or 0.0))
            if cw and cw > 0:
                cohort_cells[(session, coh, h)].append(
                    {"w": cw, "r": win["ret"], "rb": rb, "rc": c_ret, "rt": rt, "eq": eq})
            # ---- selection, once per (session, selector) (review F8) -----------
            sa = a_by.get("selection_next_ranked")
            if sa is not None and d.get("state") in ("PROBE", "EXPLOIT"):
                key = (session, d["state"], h)
                cell = sel_cells.setdefault(key, {"alt": sa["ticker"], "alt_mdv": sa.get("median_dollar_vol"),
                                                  "taken": [], "basis": basis, "eq": eq})
                cell["taken"].append({"w": float(_w("plan_full") or 0.0), "r": win["ret"], "rt": rt})
            # ---- MDC: plan_full vs leave-one-out / news tilt -------------------
            p_full = (None if _w("plan_full") is None else
                      pnl(_w("plan_full"), win["ret"], w_held=float(d.get("held_weight") or 0.0), rt_bps=rt))
            for label in [f"loo_{x}" for x in DS.LOO_SOURCES] + ["plan_plus_shadow_news",
                                                                  "plan_plus_shadow_news_full"]:
                a = a_by.get(label)
                if a is None:
                    continue
                key = label.replace("loo_", "mdc_") if label.startswith("loo_") else \
                    ("mdc_news_tilt" if label == "plan_plus_shadow_news" else "mdc_news_tilt_full")
                cell = mdc_sess[(key, h, session)]
                cell["status"].add(a["status"])
                if a.get("target_weight") is None or p_full is None:
                    cell["n_not_sep"] += 1
                    continue
                p_alt = pnl(float(a["target_weight"]), win["ret"],
                            w_held=float(d.get("held_weight") or 0.0), rt_bps=rt)
                # LOO: utility(full) - utility(without); tilt: utility(with news) - utility(full)
                if label.startswith("loo_"):
                    cell["full"] += p_full
                    cell["alt"] += p_alt
                else:
                    cell["full"] += p_alt
                    cell["alt"] += p_full
                cell["n"] += 1

    sessions_rows = _selection_rows(sel_cells, ser, asof)
    cohort_rows = _cohort_rows(cohort_cells, gross_cap)
    receipt["rows"] = rows
    receipt["refused_rows"] = refused
    receipt["selection_rows"] = sessions_rows
    receipt["cohort_rows"] = cohort_rows
    receipt["pending_not_matured"] = pending
    receipt["summary"] = _summarise(rows, cohort_rows, sessions_rows, mdc_sess)
    receipt["status"] = "OK" if rows else ("REFUSED_ALL" if refused else "NOTHING_MATURED")
    receipt["line"] = _line(receipt["summary"], pending, len(refused), receipt["live_stories"])
    return _write(receipt, out_dir, write)


def _selection_rows(cells: dict, ser, asof: str) -> list[dict]:
    from backend.services import xs_ranker as XR
    out = []
    for (session, state, h), c in sorted(cells.items()):
        taken = [x for x in c["taken"] if x["w"] > 0] or c["taken"]
        if not taken:
            continue
        w = float(np.mean([x["w"] for x in taken])) or 0.0
        s_alt = ser(c["alt"])
        win = hold_window(s_alt, session, c["basis"], h, asof_cut=asof)
        if not win["matured"] or win["status"] != "OK" or w <= 0:
            continue
        alt_mdv = c["alt_mdv"] if c["alt_mdv"] is not None else _mdv_from_panel(s_alt, session)
        rt_alt = float(XR.round_trip_bps(alt_mdv))
        taken_pnl = float(np.mean([pnl(w, x["r"], w_held=0.0, rt_bps=x["rt"]) for x in taken]))
        v = pnl(w, win["ret"], w_held=0.0, rt_bps=rt_alt) - taken_pnl
        out.append({"session": session, "selector": state, "horizon": h, "alt": c["alt"],
                    "n_taken": len(taken), "weight": w, "alt_cost_bps": rt_alt,
                    "selection_regret_bps": v * 1e4, "selection_regret_usd": v * c["eq"]})
    return out


def _cohort_rows(cells: dict, cap: float) -> list[dict]:
    out = []
    for (session, coh, h), names in sorted(cells.items()):
        gross = sum(x["w"] for x in names)
        s = min(1.0, cap / gross) if gross > 0 else 0.0
        cost = sum(s * x["w"] * x["rt"] / 1e4 for x in names)
        ex_spy = (None if any(x["rb"] is None for x in names) else
                  sum(s * x["w"] * (x["r"] - x["rb"]) for x in names) - cost)
        ctl = [x for x in names if x["rc"] is not None]
        ex_ctl = (sum(s * x["w"] * (x["r"] - x["rc"]) for x in ctl) if len(ctl) == len(names)
                  else None)
        eq = names[0]["eq"]
        out.append({"session": session, "cohort": coh, "horizon": h, "n_names": len(names),
                    "book_gross_raw": gross, "scale_to_cap": s, "book_gross_scaled": gross * s,
                    "net_excess_vs_spy_bps": None if ex_spy is None else ex_spy * 1e4,
                    "excess_vs_band_control_bps": None if ex_ctl is None else ex_ctl * 1e4,
                    "net_excess_vs_spy_usd": None if ex_spy is None else ex_spy * eq})
    return out


def _stat(vals: list[float]) -> dict:
    v = [x for x in vals if x is not None]
    n = len(v)
    if not n:
        return {"n_sessions": 0, "mean_bps": None, "sd_bps": None, "t": None, "mde_bps": None}
    m = float(np.mean(v))
    if n < 2:
        return {"n_sessions": n, "mean_bps": m, "sd_bps": None, "t": None, "mde_bps": None,
                "mde_note": "CANNOT DETERMINE: fewer than 2 date blocks"}
    sd = float(np.std(v, ddof=1))
    se = sd / math.sqrt(n)
    return {"n_sessions": n, "mean_bps": m, "sd_bps": sd,
            "t": (m / se) if se > 0 else None, "mde_bps": MDE_Z * se}


def _summarise(rows: list[dict], cohort_rows: list[dict], sel_rows: list[dict],
               mdc_sess: dict) -> dict:
    by_h: dict = {}
    by_week: dict = {}
    for h in DS.HORIZONS:
        rh = [r for r in rows if r["horizon"] == h]
        if not rh and not any(c["horizon"] == h for c in cohort_rows):
            continue
        types = {}
        for k in REGRET_TYPES:
            # one number per SESSION (mean over its names), then across sessions
            per_s: dict = defaultdict(list)
            for r in rh:
                if r.get(f"{k}_bps") is not None:
                    per_s[r["session"]].append(r[f"{k}_bps"])
            types[k] = {**_stat([float(np.mean(v)) for v in per_s.values()]),
                        "n_rows": sum(len(v) for v in per_s.values())}
        types["selection_regret"] = {**_stat([r["selection_regret_bps"] for r in sel_rows
                                              if r["horizon"] == h]),
                                     "note": "one row per (session, selector)"}
        cohorts = {}
        for coh in COHORTS:
            cr = [c for c in cohort_rows if c["horizon"] == h and c["cohort"] == coh]
            if not cr:
                continue
            cohorts[coh] = {"vs_spy": _stat([c["net_excess_vs_spy_bps"] for c in cr]),
                            "vs_band_control": _stat([c["excess_vs_band_control_bps"] for c in cr]),
                            "mean_names": float(np.mean([c["n_names"] for c in cr])),
                            "mean_gross_scaled": float(np.mean([c["book_gross_scaled"] for c in cr]))}
        by_h[f"h{h}"] = {"n_rows": len(rh), "n_sessions": len({r["session"] for r in rh}),
                         "regret": types, "cohorts": cohorts,
                         "abstention_is_reward_signal": False}
        weeks: dict = defaultdict(list)
        for c in cohort_rows:
            if c["horizon"] == h and c["net_excess_vs_spy_bps"] is not None:
                y, w, _ = date.fromisoformat(c["session"]).isocalendar()
                weeks[(f"{y}-W{w:02d}", c["cohort"])].append(c["net_excess_vs_spy_bps"])
        by_week[f"h{h}"] = {f"{wk} {coh}": {"n_sessions": len(v), "mean_net_excess_vs_spy_bps":
                                            float(np.mean(v))}
                            for (wk, coh), v in sorted(weeks.items())}
    mdc: dict = {}
    for (key, h, session), c in mdc_sess.items():
        m = mdc.setdefault(key, {}).setdefault(f"h{h}", {"per_session": [], "n_names": 0,
                                                          "n_not_separable": 0, "status": set()})
        m["status"] |= c["status"]
        m["n_not_separable"] += c["n_not_sep"]
        if c["n"]:
            m["per_session"].append((c["full"] - c["alt"]) * 1e4)
            m["n_names"] += c["n"]
    for key, hs in mdc.items():
        for h, m in hs.items():
            st = _stat(m.pop("per_session"))
            m.update(st)
            m["status"] = sorted(m["status"])
            m["label"] = (f"TRUST_AT_{TRUST_SESSIONS} ({st['n_sessions']}/{TRUST_SESSIONS})"
                          if st["n_sessions"] < TRUST_SESSIONS else "TRUSTED_SAMPLE")
            if m["status"] == ["IDENTICAL_NOT_READ"]:
                m["note"] = "zero by construction: the plan does not read this source"
            if key.startswith("mdc_news_tilt"):
                m["note"] = ("utility(plan + SHADOW_NEWS_v0 tilt) - utility(plan): what news "
                             "WOULD add" + (" at full trust (diagnostic)" if key.endswith("full")
                                            else " at the contract's earned trust"))
    return {"by_horizon": by_h, "by_week": by_week, "mdc": mdc}


def _fmt(x: Any, nd: int = 1) -> str:
    return "n/a" if x is None else f"{x:+.{nd}f}"


def _line(summary: dict, pending: int, n_refused: int, live: dict) -> str:
    parts = []
    for h, v in summary.get("by_horizon", {}).items():
        pb = (v.get("cohorts") or {}).get("picked_blocked")
        if pb:
            s = pb["vs_spy"]
            parts.append(f"{h} picked-but-blocked book (scaled to the gross cap): "
                         f"{_fmt(s['mean_bps'])} bps/session net excess vs SPY, "
                         f"{_fmt(pb['vs_band_control']['mean_bps'])} vs same-band control, "
                         f"n={s['n_sessions']} sessions, MDE {_fmt(s['mde_bps'])} bps")
    tail = (f"{pending} (decision, horizon) pairs pending; {n_refused} refused on a basis "
            f"break; live stories on disk: {live.get('n')}, oldest session {live.get('oldest_session')}")
    return "; ".join(parts + [tail]) if parts else "nothing matured yet; " + tail


def _write(receipt: dict, out_dir: Path, write: bool) -> dict:
    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"regret_{receipt['run_id']}.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))
        tmp.replace(p)
        receipt["path"] = str(p)
    return receipt


def h_table(receipt: dict, h: int = 5) -> list[dict]:
    """The owner's table (review §'the table the owner should see'): one row per
    cohort at horizon h, read from a receipt."""
    v = ((receipt.get("summary") or {}).get("by_horizon") or {}).get(f"h{h}") or {}
    out = []
    for coh, c in (v.get("cohorts") or {}).items():
        out.append({"cohort": coh, "mean_names": c["mean_names"],
                    "book_scaled_gross": c["mean_gross_scaled"],
                    "mean_net_excess_vs_spy_bps": c["vs_spy"]["mean_bps"],
                    "vs_band_control_bps": c["vs_band_control"]["mean_bps"],
                    "t_vs_spy": c["vs_spy"]["t"],
                    "n_date_blocks": c["vs_spy"]["n_sessions"], "mde_bps": c["vs_spy"]["mde_bps"]})
    return out


def format_summary(receipt: dict) -> str:
    lines = [f"regret {receipt.get('run_id')} asof {receipt.get('asof')}: {receipt.get('line')}"]
    for h in DS.HORIZONS:
        for r in h_table(receipt, h):
            lines.append(f"  h{h} {r['cohort']:<20} names~{r['mean_names']:.1f} "
                         f"gross {r['book_scaled_gross']:.1%} vsSPY {_fmt(r['mean_net_excess_vs_spy_bps'])}bps "
                         f"vsCtrl {_fmt(r['vs_band_control_bps'])}bps n={r['n_date_blocks']} "
                         f"MDE {_fmt(r['mde_bps'])}")
    for key, hs in (receipt.get("summary") or {}).get("mdc", {}).items():
        for h, m in hs.items():
            lines.append(f"  {key} {h}: {_fmt(m['mean_bps'], 2)} bps/session "
                         f"n_sessions={m['n_sessions']} not_separable={m['n_not_separable']} "
                         f"{m['label']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """`python -m backend.services.regret_ledger --json`: the daily-pass child.
    Prints `<<<{summary}>>>`; rc 2 when the grade REFUSED."""
    import argparse
    ap = argparse.ArgumentParser(prog="regret_ledger")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--asof", default=None)
    a = ap.parse_args(argv)
    try:
        r = grade_due(a.asof)
    except Exception as exc:                                       # noqa: BLE001
        r = {"status": "REFUSED", "line": f"{type(exc).__name__}: {str(exc)[:300]}"}
    summ = {"status": ("refused" if r.get("status") == "REFUSED" else
                       "ok" if r.get("status") == "OK" else "nothing_to_do"),
            "grade_status": r.get("status"), "line": r.get("line"), "path": r.get("path"),
            "n_rows": len(r.get("rows") or []), "n_refused": len(r.get("refused_rows") or []),
            "pending": r.get("pending_not_matured"), "live_stories": r.get("live_stories")}
    if a.json:
        print("<<<" + json.dumps(summ, default=str) + ">>>")
    else:
        print(format_summary(r) if r.get("summary") is not None else r.get("line"))
    return 2 if summ["status"] == "refused" else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["COHORTS", "REGRET_TYPES", "TRUST_SESSIONS", "CostRefused", "format_summary",
           "grade_due", "h_table", "hold_window", "pnl", "row_regrets", "series_of"]
