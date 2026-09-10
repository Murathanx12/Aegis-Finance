"""R2 -- can a local model READ a month of news and say what happens next?

Roadmap 2026-09-08 section 10.5, Murat's words: *"use the LLM to convert the news
of that time ... validate it in monthly intervals or six-monthly intervals"*.

The joined text-and-return panel (`r7_news_representation/panel.parquet`) is the
scarce object in this programme: **9,457 (permno, month) cells over 135 names**,
2015-02..2024-11. Everything below is bounded by that, and the bound is measured
before anything is asked of the model rather than discovered afterwards.

Four arms, and the ORDER matters:

1. **POWER FIRST** (canon section 64). With `n` monthly DATE BLOCKS -- not cells,
   blocks (canon section 58) -- and the observed dispersion of the target, what
   effect could this pilot even detect? If the minimum detectable effect is
   larger than anything a news reader plausibly produces, the run is stamped
   UNDERPOWERED and its result is exploratory whatever it says.
2. **The AMNESIA canary** (TRIAL-LLM-AMNESIA-1, measured 2026-08-08). The same
   month, twice: once with the REAL text and the company's real name, once with
   the masked text. A model trained through 2024 may simply REMEMBER what NVDA
   did in 2022. If the real-name arm scores BETTER, the pilot is measuring
   recall, not reading, and the anonymised arm is the only readable one.
3. **The read**: for each cell, the masked digest of that month's documents ->
   direction (UP / DOWN / FLAT) + confidence. Graded on `excess_vw_1m`, the
   market-adjusted forward month already in the panel.
4. **The shuffled-digest control**: the same name and month, given a digest
   drawn from a DIFFERENT month. Identical prompt, identical parser, identical
   grading, zero information. Every headline number is reported as the arm
   MINUS this control, never against zero (the 2026-09-08 D1 lesson).

$0: the backend is `local_gguf` (llama-server on the laptop GPU). The receipt
carries the DeepSeek-equivalent price of the same tokens so the saving is
legible, and `cost_usd` stays 0.00.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import free_inference as fi                        # noqa: E402
from backend.services.model_provider import LanguageRefused, ProviderRefusal   # noqa: E402

# THE PROMPT IS NOT DEFINED HERE ANY MORE. It is the pre-registered commitment
# of TRIAL-R2 (`docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`) and lives in
# `r2_trial`, which also carries its sha256. This module imports it and calls
# `verify_frozen` before the first completion, so an edited prompt REFUSES here
# instead of quietly becoming a different experiment under the same job name.
from backend.services.portfolio_intelligence.r2_trial import (               # noqa: E402
    COST_BPS_PER_SIDE,
    DIGEST_SPEC,
    PROMPT,
    SYSTEM,
    fingerprint as prereg_fingerprint,
    verify_frozen,
)

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
OUT.mkdir(parents=True, exist_ok=True)
#: The widened (PANEL-B) read is a DIFFERENT experiment on a different panel and
#: files its own receipt beside the day it ran, never on top of PANEL-A's.
WIDE_RUN_DATE = "2026-09-10"
OUT_WIDE = REPO / "backend" / "data" / "optimus" / f"night_factory_{WIDE_RUN_DATE}"
R7 = REPO / "backend" / "data" / "optimus" / "r7_news_representation"
PANEL = R7 / "panel.parquet"
DOCS_MASKED = R7 / "docs_masked.parquet"
DOCS_REAL = R7 / "docs.parquet"
#: PANEL-B: E1's joined text-and-return panel (2026-09-09) and the Alpaca bars
#: the monthly forward label is built from.
WIDE_PANEL = REPO / "backend" / "data" / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet"
BARS = REPO / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
MARKET_SYMBOL = "SPY"
STOP = OUT / "STOP"

MIN_DOCS = int(DIGEST_SPEC["min_docs_per_cell"])
MAX_DOCS_IN_DIGEST = int(DIGEST_SPEC["max_docs_in_digest"])
MAX_CHARS_PER_DOC = int(DIGEST_SPEC["max_chars_per_doc"])
NW_LAG = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    try:
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)
    except Exception:  # noqa: BLE001
        return None


def _nw_t(x: np.ndarray, lag: int = NW_LAG) -> float | None:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 6:
        return None
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - L / (lag + 1.0)) * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return float(x.mean() / se) if se > 0 else None


# --------------------------------------------------------------- the power

def power_check(cells: pd.DataFrame) -> dict:
    """What could this pilot detect, before it asks the model anything?

    The unit is the monthly DATE BLOCK: cells inside one month share the market,
    so 1,054 cells across 12 months is 12 observations wearing 1,054 hats
    (canon section 58). The MDE is quoted on the monthly mean of a long-short
    spread built from those cells.
    """
    per_month = cells.groupby("month")["excess_vw_1m"].agg(["mean", "std", "count"])
    n_blocks = int(len(per_month))
    # a decile long-short inside a month has roughly the cross-sectional sd
    # divided by sqrt(names per leg); take the median month as representative
    names = float(per_month["count"].median())
    xs_sd = float(cells.groupby("month")["excess_vw_1m"].std().median())
    leg = max(int(names // 5), 1)
    spread_sd = xs_sd * math.sqrt(2.0 / leg)
    mde_monthly = 2.8 * spread_sd / math.sqrt(max(n_blocks, 1))     # two-sided 5%, 80% power
    return {"date_blocks": n_blocks, "cells": int(len(cells)),
            "median_names_per_month": _r(names, 1),
            "median_cross_sectional_sd": _r(xs_sd),
            "implied_long_short_monthly_sd": _r(spread_sd),
            "MDE_monthly_pct": _r(mde_monthly * 100, 3),
            "MDE_annualised_pct": _r(mde_monthly * 12 * 100, 2),
            "note": ("the unit is the monthly date block, not the cell: names inside one month share "
                     "the market and are not independent draws")}


# ------------------------------------------------------------- the digests

def build_digests(cells: pd.DataFrame, docs: pd.DataFrame, text_col: str) -> dict:
    """One digest per (permno, month), from at most MAX_DOCS_IN_DIGEST items."""
    keys = set(zip(cells["permno"].astype(int), cells["month"].astype(str)))
    out: dict[tuple[int, str], str] = {}
    d = docs[docs["month"].isin(cells["month"].unique())]
    for (permno, month), g in d.groupby(["permno", "month"], sort=False):
        k = (int(permno), str(month))
        if k not in keys:
            continue
        items = [str(t)[:MAX_CHARS_PER_DOC].strip().replace("\n", " ")
                 for t in g[text_col].dropna().head(MAX_DOCS_IN_DIGEST)]
        if items:
            out[k] = "\n".join(f"- {t}" for t in items)
    return out


DIR_RE = re.compile(r"DIRECTION\s*:\s*(UP|DOWN|FLAT)", re.I)
CONF_RE = re.compile(r"CONFIDENCE\s*:\s*([01]?\.?\d*)", re.I)


def parse(text: str) -> tuple[int | None, float]:
    m = DIR_RE.search(text or "")
    if not m:
        return None, 0.0
    d = {"up": 1, "down": -1, "flat": 0}[m.group(1).lower()]
    c = CONF_RE.search(text or "")
    conf = 0.5
    if c:
        try:
            conf = min(max(float(c.group(1)), 0.0), 1.0)
        except ValueError:
            conf = 0.5
    return d, conf


def ask(digest: str, backend: str, max_tokens: int) -> tuple[int | None, float, int, int, str]:
    try:
        rep = fi.complete(backend, PROMPT.format(digest=digest), system=SYSTEM,
                          max_tokens=max_tokens, temperature=0.0, purpose="R2_monthly_llm")
    except (ProviderRefusal, LanguageRefused) as exc:
        return None, 0.0, 0, 0, f"REFUSED {type(exc).__name__}"
    d, c = parse(rep.text)
    return d, c, int(getattr(rep, "tokens_in", 0) or 0), int(getattr(rep, "tokens_out", 0) or 0), "ok"


# ------------------------------------------------------------- the grading

def grade(rows: list[dict], label: str, cost_bps: float = COST_BPS_PER_SIDE) -> dict:
    """Sign accuracy, and a confidence-weighted long-short by MONTH BLOCK.

    GROSS AND NET, with the TURNOVER PRINTED. The 2026-09-09 C2 job charged a
    flat 100 bps on every date -- full daily turnover on both legs of a book
    that rebalances MONTHLY -- and printed -237%/yr net, which is not a number a
    book can produce. So the charge here is on REALISED turnover:

        turnover_t = sum_i |w[t,i] - w[t-1,i]|      (the first month buys from 0)
        cost_t     = turnover_t * cost_bps / 1e4
        net_t      = gross_t - cost_t

    A gross-1 self-financing long-short that replaces every name each month has
    turnover 2.0, i.e. 50 bps a month, ~6%/yr. That is the sanity check, and the
    receipt carries `turnover_per_rebalance` so the reader can run it.
    """
    df = pd.DataFrame([r for r in rows if r.get("dir") is not None])
    if df.empty:
        return {"label": label, "verdict": "CANNOT DETERMINE: no parsable answer"}
    # A cell with no forward label cannot be graded, and one NaN inside a month
    # would poison that whole block silently. Drop them and COUNT them.
    n_before = len(df)
    df = df[np.isfinite(pd.to_numeric(df["fwd"], errors="coerce"))].copy()
    dropped_unlabelled = int(n_before - len(df))
    if df.empty:
        return {"label": label, "verdict": "CANNOT DETERMINE: no cell carried a forward label",
                "dropped_unlabelled": dropped_unlabelled}
    df["hit"] = np.where(df["dir"] == 0, np.nan, (np.sign(df["fwd"]) == df["dir"]).astype(float))
    key = "name" if "name" in df.columns else "permno"
    months, gross, turn = [], [], []
    prev: dict = {}
    for m, g in df.groupby("month", sort=True):
        w = g["dir"].to_numpy(dtype="float64") * g["conf"].to_numpy(dtype="float64")
        if np.abs(w).sum() < 1e-9:
            continue
        w = w / np.abs(w).sum()                       # self-financing, gross 1
        cur = dict(zip(g[key].astype(str).tolist(), w.tolist()))
        names = set(cur) | set(prev)
        turn.append(float(sum(abs(cur.get(n, 0.0) - prev.get(n, 0.0)) for n in names)))
        months.append(str(m))
        gross.append(float(np.dot(w, g["fwd"].to_numpy(dtype="float64"))))
        prev = cur
    gross = np.array(gross, dtype="float64")
    turn = np.array(turn, dtype="float64")
    net = gross - turn * (cost_bps / 1e4)
    graded = df["hit"].notna()
    return {"label": label, "cells": int(len(df)), "date_blocks": int(len(gross)),
            "dropped_unlabelled": dropped_unlabelled,
            "directional_calls": int(graded.sum()),
            "share_flat": _r(float((df["dir"] == 0).mean()), 3),
            "sign_accuracy": _r(float(df.loc[graded, "hit"].mean()), 4) if graded.any() else None,
            "long_short_monthly_mean_pct": _r(float(gross.mean()) * 100, 4) if len(gross) else None,
            "long_short_ann_pct": _r(float(gross.mean()) * 12 * 100, 3) if len(gross) else None,
            "long_short_ann_pct_NET": _r(float(net.mean()) * 12 * 100, 3) if len(net) else None,
            "t_nw_blocks": _r(_nw_t(gross), 3),
            "t_nw_blocks_NET": _r(_nw_t(net), 3),
            "monthly_sd_pp": _r(float(gross.std(ddof=1)) * 100, 3) if len(gross) > 1 else None,
            "turnover_per_rebalance": _r(float(turn.mean()), 4) if len(turn) else None,
            "cost_bps_per_side": cost_bps,
            "cost_drag_ann_pct": _r(float((turn * (cost_bps / 1e4)).mean()) * 12 * 100, 3) if len(turn) else None,
            "_monthly": [float(v) for v in gross], "_monthly_net": [float(v) for v in net],
            "_months": months}


def paired_vs(arm: dict, ctl: dict, label: str) -> dict:
    """The PRIMARY: arm minus control, block by block, GROSS and NET.

    The two books rebalance on the same dates over the same cells, so the cost
    line very largely cancels in the difference -- but that is an argument until
    it is measured, and both turnovers and both differences are printed here so
    that it is measured.
    """
    a, c = np.array(arm.get("_monthly") or []), np.array(ctl.get("_monthly") or [])
    an, cn = np.array(arm.get("_monthly_net") or []), np.array(ctl.get("_monthly_net") or [])
    n = min(len(a), len(c))
    if n < 6:
        return {"label": label, "verdict": "CANNOT DETERMINE: fewer than 6 paired blocks"}
    if arm.get("_months") and ctl.get("_months") and arm["_months"][:n] != ctl["_months"][:n]:
        return {"label": label,
                "verdict": "REFUSED: the arm and the control do not share their month blocks, "
                           "so a paired difference would pair different dates"}
    d = a[:n] - c[:n]
    dn = (an[:n] - cn[:n]) if (len(an) >= n and len(cn) >= n) else None
    out = {"label": label, "blocks": n,
           "mean_ann_pct": _r(float(d.mean()) * 12 * 100, 3), "t_nw": _r(_nw_t(d), 3),
           "arm_ann_pct": arm.get("long_short_ann_pct"), "control_ann_pct": ctl.get("long_short_ann_pct"),
           "monthly_sd_of_difference_pp": _r(float(d.std(ddof=1)) * 100, 3) if n > 1 else None}
    if dn is not None:
        out.update({
            "mean_ann_pct_NET": _r(float(dn.mean()) * 12 * 100, 3), "t_nw_NET": _r(_nw_t(dn), 3),
            "arm_ann_pct_NET": arm.get("long_short_ann_pct_NET"),
            "control_ann_pct_NET": ctl.get("long_short_ann_pct_NET"),
            "cost_cancellation": {
                "arm_turnover_per_rebalance": arm.get("turnover_per_rebalance"),
                "control_turnover_per_rebalance": ctl.get("turnover_per_rebalance"),
                "arm_cost_drag_ann_pct": arm.get("cost_drag_ann_pct"),
                "control_cost_drag_ann_pct": ctl.get("cost_drag_ann_pct"),
                "cost_effect_on_the_difference_ann_pct":
                    _r(float(dn.mean() - d.mean()) * 12 * 100, 3),
                "reading": ("the two books rebalance identically on the same dates, so the cost "
                            "line cancels in the DIFFERENCE to the extent the turnovers match; "
                            "the levels are NOT cost-robust and are reported gross beside net"),
            },
        })
    return out


# ══════════════════════════════════════════════════ PANEL-B, the widened read
#
# TRIAL-R2 section 2: the E1 panel (339,657 text-and-return cells over 3,031
# symbols, 2025-01-02..2026-09-08) instead of r7's 135 names. Three things are
# DIFFERENT and are declared in the registration rather than discovered here:
# the market proxy is SPY (CRSP ends 2024-12), the month return is open-to-open
# (entry at the first open of M+1, exit at the first open of M+2, so every
# document of month M is public before the position exists), and the cells are
# keyed by SYMBOL, not permno.


def _month_of(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, utc=True, errors="coerce").dt.strftime("%Y-%m")


def widened_forward_excess() -> tuple[pd.DataFrame, dict]:
    """(symbol, month) -> next month's SPY-excess open-to-open return.

    The position for month M is taken at the FIRST OPEN of M+1 and closed at the
    first open of M+2. Nothing in month M's digest is published after that open,
    so the label cannot be contaminated by the text it grades.
    """
    if not BARS.is_file():
        raise FileNotFoundError(f"no 2025-26 bars at {BARS}")
    bars = pd.read_parquet(BARS, columns=["symbol", "date", "open"])
    bars["date"] = pd.to_datetime(bars["date"])
    bars["month"] = bars["date"].dt.strftime("%Y-%m")
    bars = bars.sort_values(["symbol", "date"])
    first = bars.groupby(["symbol", "month"], as_index=False).first()   # first session of the month
    first = first.sort_values(["symbol", "month"])
    first["open_next"] = first.groupby("symbol")["open"].shift(-1)
    first["month_next"] = first.groupby("symbol")["month"].shift(-1)
    first["ret"] = first["open_next"] / first["open"] - 1.0             # M+1 open -> M+2 open
    mkt = first[first["symbol"] == MARKET_SYMBOL].set_index("month")["ret"]
    if mkt.dropna().empty:
        raise ValueError(f"{MARKET_SYMBOL} is not in the bar file; there is no market proxy")
    # the return earned by a position ENTERED at the first open of M+1 is the
    # `ret` recorded against month M+1, so month M's label is that row shifted
    # back by one month index.
    first["entry_month"] = first["month"]
    lab = first[["symbol", "entry_month", "ret", "month_next"]].dropna(subset=["ret"]).copy()
    # A GAP IS NOT A MONTH. `shift(-1)` happily hands back the next month that
    # EXISTS, so a delisted or halted name would contribute a two-month return
    # labelled as one. Require the successor month to be literally the next one.
    exp_next = (pd.PeriodIndex(lab["entry_month"], freq="M") + 1).astype(str)
    gaps = int((lab["month_next"].astype(str) != exp_next).sum())
    lab = lab[lab["month_next"].astype(str) == exp_next]
    lab["mkt"] = lab["entry_month"].map(mkt)
    lab = lab.dropna(subset=["mkt"])
    lab["excess_vw_1m"] = lab["ret"] - lab["mkt"]
    # month M (the READ month) is the month BEFORE the entry month
    em = pd.PeriodIndex(lab["entry_month"], freq="M")
    lab["month"] = (em - 1).astype(str)
    prov = {"bars": str(BARS), "market_symbol": MARKET_SYMBOL,
            "convention": "enter at the first open of M+1, exit at the first open of M+2, minus "
                          f"{MARKET_SYMBOL} over the same two opens",
            "symbols_with_a_label": int(lab["symbol"].nunique()),
            "label_rows": int(len(lab)),
            "dropped_for_a_calendar_gap": gaps}
    return lab[["symbol", "month", "excess_vw_1m"]], prov


def widened_cells_and_docs() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Cells with a forward label, and the documents that make their digests."""
    if not WIDE_PANEL.is_file():
        raise FileNotFoundError(f"no widened panel at {WIDE_PANEL} (E1 builds it)")
    news = pd.read_parquet(WIDE_PANEL, columns=["uid", "symbol", "published_utc", "title", "body"])
    news["month"] = _month_of(news["published_utc"])
    news["text"] = (news["title"].fillna("").astype(str) + " " +
                    news["body"].fillna("").astype(str)).str.strip()
    news = news[news["text"].str.len() > 0]
    news = news.sort_values(["symbol", "month", "published_utc", "uid"])
    n_docs = news.groupby(["symbol", "month"], as_index=False).size().rename(columns={"size": "n_docs"})
    lab, prov = widened_forward_excess()
    cells = n_docs.merge(lab, on=["symbol", "month"], how="inner")
    cells = cells[cells["n_docs"] >= MIN_DOCS].copy()
    cells["name"] = cells["symbol"].astype(str)
    funnel = {"news_rows": int(len(news)), "symbol_month_groups": int(len(n_docs)),
              "with_a_forward_label": int(len(n_docs.merge(lab, on=["symbol", "month"]))),
              "cells_at_min_docs": int(len(cells)),
              "min_docs_per_cell": MIN_DOCS, **prov}
    return cells, news, funnel


def widened_digests(cells: pd.DataFrame, news: pd.DataFrame) -> tuple[dict, dict, dict]:
    """Masked and real digests for every cell, plus the masking coverage.

    The mask is r7's, unchanged: the ticker and every distinctive token of the
    issuer's CRSP name(s) become the literal `[co]`. A symbol CRSP never carried
    still loses its ticker, and the share of documents that lost NOTHING is
    reported -- an unmasked name is a leak, and a leak is the contamination
    clause of the registration, not a rounding error.
    """
    from scripts.r7_news_representation import CO_TOKEN, company_name_map, mask_company, tokenise

    names = company_name_map()
    keys = set(zip(cells["symbol"].astype(str), cells["month"].astype(str)))
    dig_mask: dict[tuple[str, str], str] = {}
    dig_real: dict[tuple[str, str], str] = {}
    n_docs = n_masked = 0
    symbols_in_crsp = 0
    for (sym, month), g in news.groupby(["symbol", "month"], sort=False):
        k = (str(sym), str(month))
        if k not in keys:
            continue
        head = g.head(MAX_DOCS_IN_DIGEST)
        tic = str(sym).upper()
        name_toks = names.get(tic, set())
        symbols_in_crsp += 1 if name_toks else 0
        m_items, r_items = [], []
        for t in head["text"].tolist():
            toks = mask_company(tokenise(str(t)), tic, name_toks)
            n_docs += 1
            n_masked += 1 if CO_TOKEN in toks else 0
            m_items.append(" ".join(toks)[:MAX_CHARS_PER_DOC].strip())
            r_items.append(str(t)[:MAX_CHARS_PER_DOC].strip().replace("\n", " "))
        if m_items:
            dig_mask[k] = "\n".join(f"- {t}" for t in m_items)
            dig_real[k] = "\n".join(f"- {t}" for t in r_items)
    cov = {"documents_in_digests": n_docs,
           "documents_with_at_least_one_masked_token": n_masked,
           "mask_hit_rate": _r(n_masked / max(n_docs, 1), 4),
           "cells_whose_symbol_has_a_CRSP_issuer_name": symbols_in_crsp,
           "note": ("a document with no masked token is one where neither the ticker nor an "
                    "issuer-name token appeared in its text -- common for a headline that never "
                    "names the company -- but a HIGH rate of them would be a mask leak")}
    return dig_mask, dig_real, cov


def _probe(backend: str) -> str | None:
    """Is the reader actually answering? A refusal is a finding, not a crash."""
    try:
        fi.complete(backend, "Answer with the single word OK.", system="Answer in English.",
                    max_tokens=4, temperature=0.0, purpose="R2_probe")
        return None
    except (ProviderRefusal, LanguageRefused) as exc:
        return f"{type(exc).__name__}: {exc}"


def _run_digests(digests: dict, tag: str, *, backend: str, max_tokens: int, rng: random.Random,
                 fwd: dict, t0: float, shuffle: bool = False, limit: int = 0,
                 rows_path: Path | None = None) -> tuple[list[dict], dict]:
    """Ask the model, and WRITE EVERY ANSWER DOWN AS IT ARRIVES.

    The 2026-09-08 PANEL-A run held 15,000 answers in memory, graded them once
    and wrote a summary; its per-cell answers do not exist, so its NET line
    cannot be computed today without re-running 5,854 seconds of inference. Same
    shape as the G3 crash of 2026-09-09: a long job that writes once at the end
    has no result until it has all of it. Here every row is appended to
    `rows_path` as it is produced, and `--regrade` re-grades that file at any
    cost rate, for free, forever.
    """
    rows, tin, tout, refused = [], 0, 0, 0
    fh = rows_path.open("a", encoding="utf-8") if rows_path is not None else None
    keys = sorted(digests)
    if limit:
        keys = rng.sample(keys, min(limit, len(keys))) if shuffle else keys[:limit]
    for i, k in enumerate(keys):
        if STOP.exists():
            print(f"    STOP file present; {tag} ends after {i} cells", flush=True)
            break
        text = digests[k]
        if shuffle:
            other = [(p_, m_) for (p_, m_) in digests if m_ != k[1]]
            if not other:
                continue
            text = digests[rng.choice(other)]
        d, c, ti, to, status = ask(text, backend, max_tokens)
        tin += ti
        tout += to
        if status != "ok":
            refused += 1
        row = {"tag": tag, "name": k[0], "month": k[1], "dir": d, "conf": c,
               "fwd": fwd.get(k, np.nan)}
        rows.append(row)
        if fh is not None:
            fv = row["fwd"]
            fh.write(json.dumps({**row, "fwd": None if not np.isfinite(fv) else float(fv)}) + "\n")
            if (i + 1) % 200 == 0:
                fh.flush()
        if (i + 1) % 200 == 0:
            print(f"    {tag}: {i + 1}/{len(keys)} cells, {time.time() - t0:.0f}s", flush=True)
    if fh is not None:
        fh.close()
    return rows, {"tokens_in": tin, "tokens_out": tout, "refused": refused, "asked": len(rows)}


def regrade(rows_path: Path, cost_bps: float = COST_BPS_PER_SIDE) -> dict:
    """Re-grade a saved answer file at any cost rate. No model, no tokens.

    This is what makes "net beside gross" answerable after the fact instead of
    an argument: the answers are data, the cost rate is a parameter, and the
    receipt can be re-derived at 5, 10 or 25 bps without asking anything.
    """
    rows = [json.loads(ln) for ln in rows_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for r in rows:
        r["fwd"] = np.nan if r.get("fwd") is None else float(r["fwd"])
    by_tag: dict[str, list[dict]] = {}
    for r in rows:
        by_tag.setdefault(str(r.get("tag", "unknown")), []).append(r)
    graded = {t: grade(v, t, cost_bps=cost_bps) for t, v in by_tag.items()}
    arm = graded.get("read_MASKED")
    ctl = graded.get("control_SHUFFLED")
    out = {"job": "R2_regrade", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "PREREGISTRATION": prereg_fingerprint(), "rows_file": str(rows_path),
           "rows": len(rows), "cost_bps_per_side": cost_bps,
           "by_tag": {t: {k: v for k, v in g.items() if not k.startswith("_")}
                      for t, g in graded.items()},
           "written_utc": _now()}
    if arm and ctl:
        out["PRIMARY_read_minus_control"] = paired_vs(arm, ctl, "read minus shuffled control")
    return out



def R2_widened(backend: str = "local_gguf", max_cells: int = 0, canary_cells: int = 300,
               max_tokens: int = 48, seed: int = 20260909, smoke: bool = False) -> dict:
    """The registered PANEL-B read. Run ONCE (TRIAL-R2 section 5).

    Everything that does not need the model is built FIRST, so that a reader
    that is not listening produces a receipt describing the whole design rather
    than a traceback: `verdict: PENDING_MODEL`. This job never starts
    llama-server -- the desktop shell owns that lifecycle, and a research job
    that silently boots an 8 GB server is a job that can collide with another
    one mid-run.
    """
    t0 = time.time()
    prereg = verify_frozen(SYSTEM, PROMPT)
    base = {"job": "R2_monthly_llm_widened", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
            "panel": "PANEL-B", "backend": backend, "trial": prereg["trial"],
            "PREREGISTRATION": prereg,
            "question": ("Given only that month's ANONYMISED news, does a local 7B call the next "
                         "month's SPY-adjusted direction better than the identical pipeline "
                         "reading a digest from a random other month -- on a panel the 135-name "
                         "read never saw?"),
            "does_not_restate": ("PANEL-A (2015-2024, 135 names) keeps exactly the claim its own "
                                 "amendment gave it; this receipt is a separate experiment")}
    try:
        cells, news, funnel = widened_cells_and_docs()
    except (FileNotFoundError, ValueError) as exc:
        return {**base, "verdict": f"REFUSED: {exc}", "headline": "the widened panel could not be built",
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}
    if smoke:
        cells = cells.head(40)
    elif max_cells:
        cells = cells.head(max_cells)
    pw = power_check(cells)
    dig_mask, dig_real, cov = widened_digests(cells, news)
    fwd = {(str(r.symbol), str(r.month)): float(r.excess_vw_1m) for r in cells.itertuples()}
    print(f"    PANEL-B: {pw['cells']} cells, {pw['date_blocks']} month blocks, "
          f"{len(dig_mask)} digests, MDE {pw['MDE_annualised_pct']}%/yr", flush=True)
    base.update({"construction": funnel, "POWER_FIRST": pw, "masking": cov,
                 "digests": {"masked": len(dig_mask), "real": len(dig_real)},
                 "cost_model": {"cost_bps_per_side": COST_BPS_PER_SIDE,
                                "charged_on": "realised turnover sum|dw| per monthly rebalance"}})

    base["cost_bound_before_the_read"] = {
        "max_turnover_per_rebalance": 2.0,
        "why": ("each month's weights satisfy sum|w| = 1, so sum_i |w_t,i - w_t-1,i| <= 2 "
                "however different the two months are"),
        "max_cost_drag_ann_pct_per_leg": _r(2.0 * (COST_BPS_PER_SIDE / 1e4) * 12 * 100, 3),
        "max_cost_effect_on_the_DIFFERENCE_ann_pct": _r(2.0 * (COST_BPS_PER_SIDE / 1e4) * 12 * 100, 3),
        "reading": ("the levels cannot lose more than 6%/yr to costs and the difference cannot "
                    "move by more than 6%/yr either -- and it will move by far less, because the "
                    "arm and the control rebalance the same cells on the same dates. The bound is "
                    "arithmetic; the realised numbers are measured by the read and printed beside "
                    "the gross ones"),
    }

    refusal = _probe(backend)
    if refusal is not None:
        base["pending_when_the_reader_is_up"] = [
            "the AMNESIA canary on the WIDENED cells (300 real-name reads against 300 masked "
            "reads of the same cells) -- a widened result with no re-run canary is not a result",
            f"the arm: {len(dig_mask)} masked digests -> DIRECTION/CONFIDENCE",
            f"the shuffled-digest control: the same {len(dig_mask)} cells, each given a digest "
            "from a different month (rng seed 20260909)",
            "the primary: arm minus control by monthly block, gross AND net of 25 bps a side on "
            "realised turnover, with both turnovers printed",
            "one command: python -m scripts.night_r2_monthly_llm --panel widened --run 1",
        ]
        return {**base,
                "verdict": ("PENDING_MODEL: everything that does not need the reader is built and "
                            "checked; the reader is not answering, and this job does not start it "
                            f"(the desktop shell owns llama-server). Probe said: {refusal}"),
                "headline": (f"PANEL-B ready: {pw['cells']} cells over {pw['date_blocks']} month "
                             f"blocks, {len(dig_mask)} masked digests, mask hit rate "
                             f"{cov['mask_hit_rate']}; NO model call was made"),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    rng = random.Random(seed)
    canary_n = 8 if smoke else min(canary_cells, len(dig_real))
    OUT_WIDE.mkdir(parents=True, exist_ok=True)
    rows_path = OUT_WIDE / ("R2_widened_panelB_answers" + ("_smoke" if smoke else "") + ".jsonl")
    if rows_path.exists():
        rows_path.unlink()
    kw = {"backend": backend, "max_tokens": max_tokens, "rng": rng, "fwd": fwd, "t0": t0,
          "rows_path": rows_path}
    base["answers_file"] = str(rows_path)
    rows_real, u_real = _run_digests({k: v for k, v in sorted(dig_real.items())[:canary_n]},
                                     "canary_REAL_names", **kw)
    rows_mask_c, u_mask_c = _run_digests({k: v for k, v in sorted(dig_mask.items())[:canary_n]},
                                         "canary_MASKED", **kw)
    g_real = grade(rows_real, "AMNESIA canary: REAL text")
    g_mask_c = grade(rows_mask_c, "AMNESIA canary: MASKED text")
    recall_gap = None
    if g_real.get("sign_accuracy") is not None and g_mask_c.get("sign_accuracy") is not None:
        recall_gap = _r(g_real["sign_accuracy"] - g_mask_c["sign_accuracy"], 4)

    rows_arm, u_arm = _run_digests(dig_mask, "read_MASKED", **kw)
    rows_ctl, u_ctl = _run_digests(dig_mask, "control_SHUFFLED", shuffle=True, **kw)
    g_arm = grade(rows_arm, "masked digest -> direction")
    g_ctl = grade(rows_ctl, "shuffled digest (control)")
    diff = paired_vs(g_arm, g_ctl, "read minus shuffled control")

    tin = sum(u["tokens_in"] for u in (u_real, u_mask_c, u_arm, u_ctl))
    tout = sum(u["tokens_out"] for u in (u_real, u_mask_c, u_arm, u_ctl))
    ds = fi.counterfactual_deepseek(tin, tout) if hasattr(fi, "counterfactual_deepseek") else None
    net, t_net = diff.get("mean_ann_pct_NET"), diff.get("t_nw_NET")
    se = abs(net / t_net) if (t_net not in (None, 0) and net is not None) else None
    pw["realised_se_ann_pct"] = _r(se, 3)
    pw["MDE_from_realised_se_ann_pct"] = _r(2.8 * se, 2) if se else None

    # THE REGISTERED DECISION RULE, applied literally (TRIAL-R2 section 5).
    if net is None or t_net is None:
        verdict = f"CANNOT DETERMINE: {diff.get('verdict', 'no paired blocks')}"
    elif recall_gap is not None and recall_gap > 0.05:
        verdict = (f"REJECT (registered clause): the AMNESIA gap is {recall_gap:+.4f} > +0.05 -- the "
                   f"read is recall of names, not reading of text. Net difference {net}%/yr t {t_net}.")
    elif net <= 0 or t_net < 1.0 or (g_ctl.get("long_short_ann_pct_NET") or -1e9) > (
            g_arm.get("long_short_ann_pct_NET") or -1e9):
        verdict = (f"REJECT (registered clause): net difference {net}%/yr, t {t_net}, arm net "
                   f"{g_arm.get('long_short_ann_pct_NET')}%/yr vs control net "
                   f"{g_ctl.get('long_short_ann_pct_NET')}%/yr.")
    elif net >= 14.4 and t_net >= 2.0 and (recall_gap is None or recall_gap <= 0.02):
        verdict = (f"ADOPT to a 12-month ZERO-CAPITAL forward leg (registered clause): net "
                   f"{net}%/yr, t {t_net} on {diff['blocks']} month blocks. Promotion stays "
                   f"ATTENDED; this adopts nothing by itself.")
    else:
        verdict = (f"CONDITIONAL (registered): net difference {net}%/yr, t {t_net} on "
                   f"{diff['blocks']} month blocks -- between the reject clauses and the "
                   f"declared +14.4%/yr the design resolves at 19 blocks. Reported, not "
                   f"adopted; PANEL-A's claim is unchanged.")

    return {**base,
            "AMNESIA_canary": {"real_names": {k: v for k, v in g_real.items() if not k.startswith("_")},
                               "masked": {k: v for k, v in g_mask_c.items() if not k.startswith("_")},
                               "accuracy_gap_real_minus_masked": recall_gap,
                               "reading": ("a POSITIVE gap means the model does better when it can "
                                           "see who the company is: recall, not reading")},
            "arm_masked_read": {k: v for k, v in g_arm.items() if not k.startswith("_")},
            "control_shuffled_digest": {k: v for k, v in g_ctl.items() if not k.startswith("_")},
            "PRIMARY_read_minus_control": diff,
            "usage": {"tokens_in": tin, "tokens_out": tout, "cost_usd": 0.0,
                      "deepseek_equivalent_usd": ds,
                      "refusals": {k: u["refused"] for k, u in
                                   (("canary_real", u_real), ("canary_masked", u_mask_c),
                                    ("arm", u_arm), ("control", u_ctl))}},
            "headline": (f"PANEL-B {pw['date_blocks']} blocks: masked read "
                         f"{g_arm.get('long_short_ann_pct')}%/yr gross / "
                         f"{g_arm.get('long_short_ann_pct_NET')}%/yr net vs shuffled control "
                         f"{g_ctl.get('long_short_ann_pct')} / {g_ctl.get('long_short_ann_pct_NET')} "
                         f"-> {diff.get('mean_ann_pct')} gross, {net} net, t {t_net}; "
                         f"AMNESIA gap {recall_gap}"),
            "verdict": verdict, "family_max_p": None,
            "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}


def R2_monthly_llm(year: int = 2022, backend: str = "local_gguf", max_cells: int = 0,
                   canary_cells: int = 120, max_tokens: int = 48, seed: int = 20260909,
                   smoke: bool = False, year_to: int | None = None) -> dict:
    """`year` alone reads one year; `year_to` widens it to a span.

    The 2022 pilot resolved 12 monthly DATE BLOCKS and an MDE of 51%/yr, which
    is larger than any effect a news reader plausibly produces -- so the pilot
    could only ever be exploratory. Blocks are what buys power here, and the
    joined panel holds 112 of them, so the span form is the one that can
    actually answer the question."""
    t0 = time.time()
    verify_frozen(SYSTEM, PROMPT)
    if not PANEL.exists():
        return {"job": "R2_monthly_llm", "verdict": f"REFUSED: no joined panel at {PANEL}",
                "headline": "the text-and-return panel is not on this checkout", "written_utc": _now()}
    panel = pd.read_parquet(PANEL)
    panel["year"] = panel["month"].str.slice(0, 4).astype(int)
    hi = year_to or year
    cells = panel[(panel["year"] >= year) & (panel["year"] <= hi) & (panel["n_docs"] >= MIN_DOCS)].copy()
    cells["permno"] = cells["permno"].astype(int)
    if smoke:
        cells = cells.head(24)
    elif max_cells:
        cells = cells.head(max_cells)
    pw = power_check(cells)
    span = f"{year}" if hi == year else f"{year}-{hi}"
    print(f"    {span}: {pw['cells']} cells, {pw['date_blocks']} month blocks, "
          f"MDE {pw['MDE_annualised_pct']}%/yr", flush=True)

    # The panel is keyed by permno; the document frames carry tickers. Rather
    # than invent a mapping, this reuses the SAME point-in-time interval join
    # `r7_news_representation` used to BUILD panel.parquet (CRSP stocknames,
    # ticker valid between namedt and nameenddt). A ticker reused by a different
    # company later must not inherit the earlier permno, and a flat ticker->permno
    # dict would do exactly that -- the share-basis failure this programme
    # already paid for once (2026-09-04).
    from scripts.r7_news_representation import _crosswalk, resolve_permnos

    sn = _crosswalk()
    masked = pd.read_parquet(DOCS_MASKED, columns=["uid", "month", "masked", "ticker", "observed_at"])
    masked["symbols"] = masked["ticker"].astype(str)
    masked["observed_at"] = pd.to_datetime(masked["observed_at"], utc=True, errors="coerce")
    masked = resolve_permnos(masked, sn)
    real = pd.read_parquet(DOCS_REAL, columns=["uid", "month", "text", "symbols", "observed_at"])
    real["observed_at"] = pd.to_datetime(real["observed_at"], utc=True, errors="coerce")
    real = resolve_permnos(real, sn)
    for frame, name in ((masked, "masked"), (real, "real")):
        frame["permno"] = pd.to_numeric(frame["permno"], errors="coerce")
        print(f"    {name} docs: {len(frame):,} rows, {frame['permno'].notna().mean():.1%} linked to a permno",
              flush=True)
    masked = masked[masked["permno"].notna()]
    real = real[real["permno"].notna()]

    dig_masked = build_digests(cells, masked, "masked")
    dig_real = build_digests(cells, real, "text")
    print(f"    digests: {len(dig_masked)} masked, {len(dig_real)} real", flush=True)

    fwd = {(int(r.permno), str(r.month)): float(r.excess_vw_1m) for r in cells.itertuples()}
    rng = random.Random(seed)

    rows_path = OUT / f"R2_monthly_llm_{span.replace('-', '_')}_answers.jsonl"
    if rows_path.exists():
        rows_path.unlink()

    def run(digests: dict, tag: str, shuffle: bool = False, limit: int = 0) -> tuple[list[dict], dict]:
        rows, tin, tout, refused = [], 0, 0, 0
        fh = rows_path.open("a", encoding="utf-8")
        keys = sorted(digests)
        if limit:
            keys = keys[:limit] if not shuffle else rng.sample(keys, min(limit, len(keys)))
        for i, k in enumerate(keys):
            if STOP.exists():
                print(f"    STOP file present; {tag} ends after {i} cells", flush=True)
                break
            text = digests[k]
            if shuffle:
                other = [(p, m) for (p, m) in digests if m != k[1]]
                if not other:
                    continue
                text = digests[rng.choice(other)]
            d, c, ti, to, status = ask(text, backend, max_tokens)
            tin += ti
            tout += to
            if status != "ok":
                refused += 1
            row = {"tag": tag, "name": str(k[0]), "permno": k[0], "month": k[1],
                   "dir": d, "conf": c, "fwd": fwd.get(k, np.nan)}
            rows.append(row)
            fv = row["fwd"]
            fh.write(json.dumps({**row, "fwd": None if not np.isfinite(fv) else float(fv)}) + "\n")
            if (i + 1) % 100 == 0:
                fh.flush()
                print(f"    {tag}: {i + 1}/{len(keys)} cells, {time.time() - t0:.0f}s", flush=True)
        fh.close()
        return rows, {"tokens_in": tin, "tokens_out": tout, "refused": refused, "asked": len(rows)}

    canary_n = min(canary_cells, len(dig_real)) if not smoke else 8
    rows_real, u_real = run({k: v for k, v in sorted(dig_real.items())[:canary_n]}, "canary_REAL_names")
    rows_mask_c, u_mask_c = run({k: v for k, v in sorted(dig_masked.items())[:canary_n]}, "canary_MASKED")
    g_real, g_mask_c = grade(rows_real, "AMNESIA canary: REAL text"), grade(rows_mask_c, "AMNESIA canary: MASKED text")
    recall_gap = None
    if g_real.get("sign_accuracy") is not None and g_mask_c.get("sign_accuracy") is not None:
        recall_gap = _r(g_real["sign_accuracy"] - g_mask_c["sign_accuracy"], 4)

    rows_arm, u_arm = run(dig_masked, "read_MASKED")
    rows_ctl, u_ctl = run(dig_masked, "control_SHUFFLED", shuffle=True)
    g_arm, g_ctl = grade(rows_arm, "masked digest -> direction"), grade(rows_ctl, "shuffled digest (control)")
    diff = paired_vs(g_arm, g_ctl, "read minus shuffled control")

    tin = sum(u["tokens_in"] for u in (u_real, u_mask_c, u_arm, u_ctl))
    tout = sum(u["tokens_out"] for u in (u_real, u_mask_c, u_arm, u_ctl))
    ds = fi.counterfactual_deepseek(tin, tout) if hasattr(fi, "counterfactual_deepseek") else None

    # RECONCILE THE PRE-HOC MDE AGAINST THE REALISED STANDARD ERROR.
    # `power_check` estimates the long-short's dispersion from the cross-sectional
    # sd divided by sqrt(names per leg) -- a proxy that treats names inside a
    # month as independent draws. Measured on the 2015-2024 read it overstated
    # the standard error by 1.61x (assumed 6.63%/yr, realised 4.13%/yr), so the
    # design was better powered than the pre-hoc number said and the run was
    # stamped UNDERPOWERED while carrying a t of 3.9. A power check is a DESIGN
    # quantity; once the effect is measured, its own standard error is the honest
    # one, and both belong in the receipt.
    se_realised = (abs(diff["mean_ann_pct"] / diff["t_nw"])
                   if diff.get("t_nw") not in (None, 0) and diff.get("mean_ann_pct") is not None else None)
    mde_realised = 2.8 * se_realised if se_realised else None
    pw["realised_se_ann_pct"] = _r(se_realised, 3)
    pw["MDE_from_realised_se_ann_pct"] = _r(mde_realised, 2)
    pw["prehoc_se_overstated_by"] = _r((pw["MDE_annualised_pct"] / 2.8) / se_realised, 2) if se_realised else None
    underpowered = (mde_realised or pw["MDE_annualised_pct"] or 0) > abs(diff.get("mean_ann_pct") or 0)
    if diff.get("t_nw") is None:
        verdict = f"CANNOT DETERMINE: {diff.get('verdict', 'no paired blocks')}"
    elif recall_gap is not None and recall_gap > 0.05:
        verdict = (f"MEMORY_SUSPECTED: the model scores {recall_gap:+.3f} BETTER with real company names than "
                   f"with masked text on the same months, so this pilot is partly measuring recall of "
                   f"{span}, not reading. Only the masked arm is readable, and its own control-relative "
                   f"result is {diff['mean_ann_pct']}%/yr t {diff['t_nw']}.")
    elif underpowered:
        verdict = (f"UNDERPOWERED, EXPLORATORY: {pw['date_blocks']} month blocks resolve "
                   f"{pw['MDE_from_realised_se_ann_pct'] or pw['MDE_annualised_pct']}%/yr; the measured "
                   f"control-relative effect is "
                   f"{diff['mean_ann_pct']}%/yr t {diff['t_nw']}. That is a number, not evidence -- "
                   f"the panel, not the model, is the binding constraint.")
    elif (diff["t_nw"] or 0) > 2.0 and (diff["mean_ann_pct"] or 0) > 0:
        verdict = (f"PRODUCT_PROMISING: reading the month's masked news beats the shuffled-digest control by "
                   f"{diff['mean_ann_pct']}%/yr, t {diff['t_nw']} on {diff['blocks']} month blocks")
    else:
        verdict = (f"FAILED_VARIANT: the model's monthly direction call does not beat a digest from a random "
                   f"other month ({diff['mean_ann_pct']}%/yr, t {diff['t_nw']})")

    return {
        "job": "R2_monthly_llm", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "panel": "PANEL-A", "PREREGISTRATION": prereg_fingerprint(),
        "cost_model": {"cost_bps_per_side": COST_BPS_PER_SIDE,
                       "charged_on": "realised turnover sum|dw| per monthly rebalance"},
        "backend": backend, "year": year, "year_to": hi, "span": span, "min_docs_per_cell": MIN_DOCS,
        "question": ("Given only that month's news, can a local model call the next month's market-adjusted "
                     "direction better than the identical pipeline reading a digest from a random other month?"),
        "POWER_FIRST": pw,
        "AMNESIA_canary": {"real_names": {k: v for k, v in g_real.items() if not k.startswith("_")},
                           "masked": {k: v for k, v in g_mask_c.items() if not k.startswith("_")},
                           "accuracy_gap_real_minus_masked": recall_gap,
                           "reading": ("a POSITIVE gap means the model does better when it can see who the "
                                       "company is, which is recall of a year inside its training data, not "
                                       "reading of the text")},
        "arm_masked_read": {k: v for k, v in g_arm.items() if not k.startswith("_")},
        "control_shuffled_digest": {k: v for k, v in g_ctl.items() if not k.startswith("_")},
        "PRIMARY_read_minus_control": diff,
        "usage": {"tokens_in": tin, "tokens_out": tout,
                  "cost_usd": 0.0, "deepseek_equivalent_usd": ds,
                  "refusals": {k: u["refused"] for k, u in
                               (("canary_real", u_real), ("canary_masked", u_mask_c),
                                ("arm", u_arm), ("control", u_ctl))}},
        "headline": (f"{span}: {g_arm.get('cells')} cells over {g_arm.get('date_blocks')} month blocks; "
                     f"masked read {g_arm.get('long_short_ann_pct')}%/yr vs shuffled control "
                     f"{g_ctl.get('long_short_ann_pct')}%/yr -> {diff.get('mean_ann_pct')}%/yr "
                     f"t {diff.get('t_nw')}; AMNESIA gap {recall_gap}; MDE {pw['MDE_annualised_pct']}%/yr"),
        "verdict": verdict, "family_max_p": None,
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", choices=("legacy", "widened"), default="legacy",
                    help="legacy = PANEL-A (r7, 135 names, 2015-2024); "
                         "widened = PANEL-B (E1, 2025-26), the registered read")
    ap.add_argument("--year", type=int, default=2022)
    ap.add_argument("--year-to", type=int, default=None, help="read a SPAN; blocks are what buy power")
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--max-cells", type=int, default=0)
    ap.add_argument("--canary-cells", type=int, default=120)
    ap.add_argument("--max-tokens", type=int, default=48)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--regrade", default=None,
                    help="re-grade a saved answers jsonl at --cost-bps; no model, no tokens")
    ap.add_argument("--cost-bps", type=float, default=COST_BPS_PER_SIDE)
    a = ap.parse_args(argv)
    if a.regrade:
        p = regrade(Path(a.regrade), cost_bps=a.cost_bps)
        out = Path(a.out) if a.out else Path(a.regrade).with_suffix(".regrade.json")
        out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
        pri = p.get("PRIMARY_read_minus_control") or {}
        print(f"\nR2 regrade at {a.cost_bps} bps: gross {pri.get('mean_ann_pct')}%/yr "
              f"net {pri.get('mean_ann_pct_NET')}%/yr t {pri.get('t_nw_NET')}\n  -> {out}")
        return 0
    if a.panel == "widened":
        p = R2_widened(backend=a.backend, max_cells=a.max_cells,
                       canary_cells=max(a.canary_cells, 300), max_tokens=a.max_tokens,
                       smoke=a.smoke)
        OUT_WIDE.mkdir(parents=True, exist_ok=True)
        default_out = OUT_WIDE / f"R2_widened_panelB_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    else:
        p = R2_monthly_llm(year=a.year, year_to=a.year_to, backend=a.backend, max_cells=a.max_cells,
                           canary_cells=a.canary_cells, max_tokens=a.max_tokens, smoke=a.smoke)
        tag = f"{a.year}" if not a.year_to else f"{a.year}_{a.year_to}"
        default_out = OUT / f"R2_monthly_llm_{tag}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    p["run"] = a.run
    out = Path(a.out) if a.out else default_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\nR2: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
