"""PC-PAPER worst case priced on the names each sleeve would actually buy (2026-10-06, C2 F1).

WHY
===
The first C2 gate priced the whole book at one constant, `PROBE_REF_DAILY_SIGMA`
(2.16%/day, the median name on 2026-09-24): 1.00 gross x 3 x 2.16% = 6.48%,
PASS against the 10% line. The adversarial review recomputed sigma on the bars
panel the same day: the universe median was already 2.51%, the p90 4.90%, and
the ranker's top eight -- the names EXPLOIT would buy -- 2.4% to 7.8%. On those
names the same arithmetic is ~14% of equity: REFUSE. The gate measured the calm
sleeve and approved the volatile one.

So each sleeve is priced on its OWN names, one daily sigma per name from the
same panel and window the fleet manager uses for its stops
(`FLEET_MANAGER_SIGMA_WINDOW` sessions of close-to-close returns, at least 40):

* EXPLOIT -- the ranker's top names (`pc_book/<day>/ranking.json`, newest), at
  `ER_EXPLOIT_MAX_WEIGHT` each up to the sleeve's gross;
* PROBE   -- the names the account HOLDS (the broker read), scaled to the PROBE
  gross cap.

A name with no sigma is priced at the universe p90 (never the median), and the
universe median and p90 figures are printed beside the sleeve figure. The 10%
line is never widened: when the largest admissible book fails it, EXPLOIT is
SIZED DOWN (`exploit_gross_cap`) until the book passes, and `cap_book` applies
the same arithmetic to the plan's actual targets on every cycle, before any
order is sent.

The loss model is rho = 1 (every name moves k sigma against the book on the
same day): conservative across names, blind to a single-name gap.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Iterable, Optional

from backend import config

logger = logging.getLogger(__name__)

_CACHE: dict = {}


def _bars_path() -> Path:
    return Path(config.OPTIMUS_LEDGER_DIR) / "prices_2025_26" / "bars.parquet"


def panel_sigmas(path: Optional[Path] = None, *, window: Optional[int] = None) -> dict:
    """{symbol: daily sigma} over the newest `window` returns of every name in
    the bars panel; {} when the panel is absent or unreadable (the caller then
    prices at the declared fallback and says so). Cached on the file's size and
    stamp so a sim cycle does not re-read 1.3M rows."""
    p = Path(path or _bars_path())
    w = int(window or config.FLEET_MANAGER_SIGMA_WINDOW)
    try:
        st = p.stat()
    except OSError:
        return {}
    key = (str(p), st.st_size, int(st.st_mtime), w)
    if key in _CACHE:
        return _CACHE[key]
    try:
        import pandas as pd                                        # noqa: PLC0415
        df = pd.read_parquet(p, columns=["symbol", "date", "close"])
        last = df["date"].max()
        df = df[df["date"] >= last - pd.Timedelta(days=int(w * 1.6) + 10)]
        wide = df.pivot_table(index="date", columns="symbol", values="close").sort_index()
        rets = wide.pct_change(fill_method=None).iloc[-w:]
        cnt = rets.count()
        sd = rets.std(ddof=1)
        out = {str(s): float(v) for s, v in sd.items()
               if cnt.get(s, 0) >= min(w, 40) and math.isfinite(v) and v > 0}
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("pc_risk: panel sigmas unreadable (%s: %s)", type(exc).__name__, exc)
        out = {}
    _CACHE.clear()
    _CACHE[key] = out
    return out


def universe_stats(sigmas: dict) -> dict:
    vals = sorted(v for v in sigmas.values() if v and v > 0)
    if not vals:
        return {"n": 0, "p50": None, "p90": None}

    def q(p: float) -> float:
        return vals[min(len(vals) - 1, int(p * (len(vals) - 1) + 0.5))]
    return {"n": len(vals), "p50": q(0.50), "p75": q(0.75), "p90": q(0.90)}


def fallback_sigma(stats: dict) -> tuple[float, str]:
    """The sigma a name without its own is priced at: the universe p90, else the
    declared constant. Never the median."""
    if stats.get("p90"):
        return float(stats["p90"]), "universe p90"
    return float(config.PC_SIGMA_FALLBACK_DAILY), "config.PC_SIGMA_FALLBACK_DAILY"


def exploit_candidates(n: int, *, root: Optional[Path] = None) -> dict:
    """The ranker's top `n` symbols from the newest `pc_book/<day>/ranking.json`."""
    base = Path(root or (Path(config.OPTIMUS_LEDGER_DIR) / "pc_book"))
    days = sorted((p for p in base.glob("20??-??-??") if (p / "ranking.json").is_file()),
                  reverse=True) if base.is_dir() else []
    for d in days:
        try:
            r = json.loads((d / "ranking.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        top = [str(x.get("symbol")) for x in (r.get("top") or []) if x.get("symbol")]
        if top:
            return {"symbols": top[:n], "asof": r.get("asof"), "source": f"pc_book/{d.name}/ranking.json"}
    return {"symbols": [], "asof": None, "source": None}


def sleeve_loss(weights: dict[str, float], sigmas: dict, *, k: float,
                fallback: float) -> dict:
    """PURE. One-day k-sigma loss of a sleeve, rho = 1: sum w_i x k x sigma_i."""
    rows = []
    frac = 0.0
    n_fb = 0
    for s, w in weights.items():
        sig = sigmas.get(s)
        fb = not (isinstance(sig, (int, float)) and sig > 0)
        if fb:
            sig, n_fb = fallback, n_fb + 1
        frac += float(w) * k * float(sig)
        rows.append({"symbol": s, "weight": float(w), "sigma": float(sig), "fallback": fb})
    return {"frac": frac, "gross": sum(float(w) for w in weights.values()),
            "n_names": len(weights), "n_sigma_fallback": n_fb, "names": rows}


def largest_admissible(*, equity: float, exploit_syms: list[str], held_weights: dict[str, float],
                       sigmas: dict, ex_w: float, ex_gross: float, probe_gross: float,
                       k: float, limit: float, source: str = "") -> dict:
    """PURE. The worst case of the largest admissible PC-PAPER book, per sleeve.

    EXPLOIT: the first `ex_gross / ex_w` ranked names at `ex_w` each. PROBE: the
    held names scaled to `probe_gross` (or `probe_gross` at the fallback sigma
    when nothing is held). Verdict on the sleeve-specific total; when it fails,
    the EXPLOIT gross that passes (`exploit_gross_cap`) beside it.
    """
    stats = universe_stats(sigmas)
    fb, fb_src = fallback_sigma(stats)
    n_ex = int(ex_gross / ex_w + 1e-9) if ex_w > 0 else 0
    ex_names = list(exploit_syms)[:n_ex]
    ex_weights = {s: ex_w for s in ex_names}
    if len(ex_names) < n_ex:
        # fewer ranked names than slots: the empty slots are priced at the fallback
        for i in range(n_ex - len(ex_names)):
            ex_weights[f"<unranked slot {i + 1}>"] = ex_w
    tot_h = sum(v for v in held_weights.values() if v > 0)
    pr_weights = ({s: probe_gross * v / tot_h for s, v in held_weights.items() if v > 0}
                  if tot_h > 0 else {"<no held names>": probe_gross})
    ex = sleeve_loss(ex_weights, sigmas, k=k, fallback=fb)
    pr = sleeve_loss(pr_weights, sigmas, k=k, fallback=fb)
    total = ex["frac"] + pr["frac"]
    gross = ex["gross"] + pr["gross"]
    verdict = "PASS" if total <= limit + 1e-12 else "REFUSE"
    ex_unit = (ex["frac"] / ex["gross"]) if ex["gross"] > 0 else 0.0
    if pr["frac"] > limit + 1e-12:
        cap, trading = 0.0, "REFUSE"
    elif verdict == "PASS":
        cap, trading = ex["gross"], "PASS"
    else:
        cap = max(0.0, min(ex["gross"], (limit - pr["frac"]) / ex_unit)) if ex_unit > 0 else 0.0
        trading = "PASS_EXPLOIT_CAPPED" if cap > 0 else "PASS_EXPLOIT_OFF"

    def _row(label: str, s: dict, note: str) -> dict:
        avg = (s["frac"] / (k * s["gross"])) if s["gross"] > 0 else 0.0
        return {"sleeve": label, "n_names": s["n_names"], "gross_over_equity": s["gross"],
                "avg_sigma": avg, "stop_sigma": k, "worst_case_k_sigma_frac": s["frac"],
                "worst_case_k_sigma_usd": -s["frac"] * equity,
                "worst_case_no_stop_usd": -s["gross"] * equity,
                "n_sigma_fallback": s["n_sigma_fallback"], "names": s["names"],
                "line": (f"{label}: {s['n_names']} names, gross {s['gross']:.2f}, avg sigma "
                         f"{avg:.2%} x {k:g} = -${s['frac'] * equity:,.0f} "
                         f"({s['frac']:.2%} of equity){note}")}

    uni = {}
    for q in ("p50", "p90"):
        sq = stats.get(q)
        uni[q] = ({"sigma": sq, "frac": gross * k * sq, "usd": -gross * k * sq * equity}
                  if sq else {"sigma": None, "frac": None, "usd": None})
    line = (f"WORST CASE {verdict} (largest admissible book, sleeve names): "
            f"{total:.2%} of equity (-${total * equity:,.0f}) vs limit {limit:.0%}"
            + (f"; universe median {uni['p50']['frac']:.2%}, p90 {uni['p90']['frac']:.2%}"
               if uni["p50"]["frac"] is not None else "; universe sigma UNREAD")
            + ("" if verdict == "PASS" else
               f"; TRADING {trading}: EXPLOIT gross capped at {cap:.2%} "
               f"(~{int(cap / ex_w + 1e-9) if ex_w else 0} names at {ex_w:.0%}) in u_plan, every cycle"))
    return {
        "equity_usd": float(equity), "k_sigma": k, "limit_frac_of_equity": limit,
        "sigma_source": f"panel daily sigma, {config.FLEET_MANAGER_SIGMA_WINDOW} sessions; "
                        f"missing -> {fb_src} {fb:.2%}",
        "exploit_source": source,
        "rows": [_row("EXPLOIT", ex, f" (ranker top {len(ex_names)} at {ex_w:.0%})"),
                 _row("PROBE", pr, " (held names, scaled to the PROBE cap)")],
        "total_frac": total, "total_usd": -total * equity, "gross_over_equity": gross,
        "universe": {"stats": stats, "median": uni["p50"], "p90": uni["p90"]},
        "verdict": verdict, "trading_verdict": trading,
        "exploit_gross_cap": cap, "line": line,
    }


def cap_book(weights: dict[str, float], sleeve_of: dict[str, str], sigmas: dict, *,
             k: float, limit: float, fallback: float) -> dict:
    """PURE. The order-path gate: the plan's ACTING weights, priced per name.

    Over the limit -> EXPLOIT weights are scaled down (never PROBE's, never a
    limit) until the book passes; if PROBE alone is over, `block` names it and
    nothing is sent. Returns the (possibly scaled) weights."""
    ex = {s: w for s, w in weights.items() if sleeve_of.get(s) == "EXPLOIT"}
    other = {s: w for s, w in weights.items() if sleeve_of.get(s) != "EXPLOIT"}
    lo = sleeve_loss(other, sigmas, k=k, fallback=fallback)
    le = sleeve_loss(ex, sigmas, k=k, fallback=fallback)
    before = lo["frac"] + le["frac"]
    scale, block = 1.0, None
    if lo["frac"] > limit + 1e-12:
        scale, block = 0.0, (f"WORST CASE REFUSE: the non-EXPLOIT book alone is "
                             f"{lo['frac']:.2%} of equity > {limit:.0%}")
    elif before > limit + 1e-12 and le["frac"] > 0:
        scale = max(0.0, (limit - lo["frac"]) / le["frac"])
    out = {**other, **{s: w * scale for s, w in ex.items()}}
    after = lo["frac"] + le["frac"] * scale
    return {"weights": out, "scale_exploit": scale, "block": block,
            "before_frac": before, "after_frac": after if not block else lo["frac"],
            "limit": limit,
            "line": (f"order-path worst case {before:.2%} -> {after:.2%} of equity "
                     f"(limit {limit:.0%}, {k:g} sigma per name)"
                     + (f"; EXPLOIT scaled x{scale:.3f}" if scale < 1.0 and not block else "")
                     + (f"; {block}" if block else ""))}
