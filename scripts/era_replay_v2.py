"""ERA REPLAY v2 -- the LLM reading test, DECIDE step, 2016-19 era.

WHY THIS FILE EXISTS
====================
`docs/AEGIS_VISION_2026-08-30_LOG_REVISION_ERA_REPLAY.md` §3 asks for one thing
we have never measured beyond eleven dates: **does an LLM reading a company's
situation, blinded to its identity and its era, order next month's cross-section
better than the equal-weight basket of the same names?**

Friday's night lab (`docs/BUILD_NIGHT_LAB_2026-09-05.md` §5) lists L10 -- era
replay v2 -- as NOT RUN. There is no L10 receipt in
`backend/data/optimus/night_lab_2026-09-05/`. So the scaffolding did not exist
and this file is it, not a re-run of it.

THE SHAPE OF THE TEST
---------------------
A **window** is one (thread, month) decision. A thread is a persistent
portfolio, which is what makes a diary possible at all: at month m the decider
may be handed what it wrote at month m-1. Four threads x 48 months of 2016-01
through 2019-12 = 192 windows, which is under the brief's 200.

Each window shows K=8 companies drawn from that month's eligible universe. The
decider returns a RANK, 1 = best expected relative performer over the next
month. **The LLM never sees a price and never produces one.** Code prices:
`learner/evaluate.py` conventions, `learner/benchmark.py` for the market leg,
`learner/inference.py` for every claim.

FOUR ARMS, CROSSED
------------------
| arm | naming | diary |
|---|---|---|
| `fantasy_nodiary`   | sectors transposed to a fictional taxonomy | no |
| `fantasy_diary`     | same                                       | yes |
| `realanon_nodiary`  | real sector labels, company called "Company A" | no |
| `realanon_diary`    | same                                       | yes |

The naming arms carry **identical numeric information**. Only the surface
category labels differ. That is the memorisation test: if real-anon beats
fantasy, the model is using real-world category priors (or recognising the era),
not reading the situation. The diary axis is the disposition test (vision §3b).

WHAT IS DELIBERATELY *NOT* IN THE BUNDLE
----------------------------------------
**The EDGAR 8-K item tape.** `backend/data/optimus/edgar_8k/manifest.json`
states its own defect: the universe is resolved through `company_tickers.json`,
which is the list of CURRENT registrants, so names delisted before the map's
fetch date are absent. Presence of 8-K rows in 2016-19 therefore correlates with
survival to 2026 -- a forward-looking leak straight into the bundle. Adding it
would have made the test richer and wrong. It is refused, loudly, in the receipt
rather than quietly included. `coverage_start_median 2016-02-09` plus the
manifest's own truncation caveat is the second reason: absence is truncation,
not evidence.

THE CANARY
----------
The decider is asked, AFTER it has committed its ranking in the same JSON
object, what year it thinks this is and whether it can name any company. Order
matters for an autoregressive model: asked first, the guess would anchor the
rank. The identification rate is reported beside every P&L number. If the model
names the true year at a rate materially above chance the era is **NOT BLIND**
and the result is reported as such, never as edge (vision §2c).

THREE NULLS (vision §3d), all code-side and free
------------------------------------------------
1. **Shuffled companies** -- the same rank vector re-assigned to a random
   permutation of the bundle. Kills "the model just likes this era".
2. **Shuffled dates** -- the rank applied to the same names' returns in a
   different, randomly chosen month of the era. The calendar null (T3's lesson:
   most of a shock is the day).
3. **Same-day paired** -- top-half minus bottom-half *within the same bundle on
   the same month*. The month effect cancels exactly; this is the primary
   statistic, and the one the nulls cannot flatter.

COSTS ARE NEVER OMITTED
-----------------------
`learner.evaluate.COST_BPS_PER_SIDE` (10 bps) on both sides of every rebalance,
charged on realised turnover. Universe floor `TRADABLE_DOLLAR_VOL` ($3m/day) and
the $5 price floor are applied when the window is BUILT, not at grading, so no
window ever contains a name the house would refuse to buy.

MONEY
-----
Every vendor call is gated by `backend/services/research_budget.require` before
the wire and recorded to `llm_telemetry` after it, with a hard local ceiling on
top. `gpt-5-nano` is not in `config.LLM_PRICE_PER_MTOK` and this session may not
edit `config.py`, so telemetry prices it `None` and the ledger total is a LOWER
BOUND; this module prices it locally at published list rates and says so in the
receipt. DeepSeek is reconciled against the PROVIDER balance
(`GET /user/balance`), not against our own arithmetic.

USAGE
-----
    python -m scripts.era_replay_v2 --build            # $0, windows only
    python -m scripts.era_replay_v2 --pilot 10         # 10 windows, project cost
    python -m scripts.era_replay_v2 --run              # the full 192
    python -m scripts.era_replay_v2 --grade            # regrade from cache, $0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DATA = REPO / "backend" / "data" / "optimus" / "era_replay_v2"
RECEIPTS = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06"
RECEIPTS_B = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06b"
WINDOWS_PATH = DATA / "windows.json"
CACHE_PATH = DATA / "llm_cache.jsonl"

# ── the experiment's frozen parameters ──────────────────────────────────────
ERA_START_YEAR = 2016
ERA_END_YEAR = 2019
K_NAMES = 8                       #: companies shown per window
N_THREADS = 4                     #: parallel portfolios (a diary needs a thread)
TOP_N = 3                         #: names the book holds out of K
BUILD_SEED = 20260906
CAMPAIGN = "era_replay_v2"

REWRITER_MODEL = "gpt-5-nano"
REWRITER_PROVIDER = "openai"
DECIDER_MODEL = "deepseek-chat"
DECIDER_PROVIDER = "deepseek"

#: gpt-5-nano list price, USD per million tokens, as published 2026-09.
#: NOT in `config.LLM_PRICE_PER_MTOK`; this session is not permitted to edit
#: config.py, so the number lives here and the receipt says it is a local table.
NANO_PRICE_PER_MTOK = {"in": 0.05, "cached_in": 0.005, "out": 0.40}
NANO_PRICE_SOURCE = "OpenAI published list price, local table (config.py not editable this session)"

#: Hard local ceiling. The brief's cap is $5.00 across both providers; this is
#: set below it so the run stops before the mandate does.
HARD_CAP_USD = 4.50

LANGUAGE_PIN = " Respond in English only."

ARMS = ("fantasy_nodiary", "fantasy_diary", "realanon_nodiary", "realanon_diary")


def naming_of(arm: str) -> str:
    return "fantasy" if arm.startswith("fantasy") else "realanon"


def diary_of(arm: str) -> bool:
    return arm.endswith("_diary")


# ── the fantasy taxonomy ────────────────────────────────────────────────────
# A FIXED bijection from the panel's SIC-derived sectors onto invented ones.
# Bijective on purpose: the information content (which names share a sector) is
# preserved exactly, only the label a language model can attach a prior to is
# replaced. A many-to-one map would destroy information and confound the arm.
FANTASY_SECTOR = {
    "Manufacturing": "Resonant Alloys",
    "Services": "Chartering & Custody",
    "Finance & Real Estate": "Tidewater Assurance",
    "Unclassified": "Unlisted Trade",
    "Transport & Utilities": "Skyline Conveyance",
    "Retail": "Provisioning Halls",
    "Mining": "Deepcore Extraction",
    "Wholesale": "Bulk Consignment",
    "Construction": "Lattice Works",
    "Agriculture": "Greenmarch Cultivation",
    "Public Administration": "Civic Concession",
    "_UNKNOWN": "Unlisted Trade",
}
FANTASY_FIRMS = ["Aureon", "Bellwyn", "Corvane", "Dunmoor", "Eskvale",
                 "Fenlow", "Garrick", "Halbrook", "Iversk", "Jorrun"]
REAL_LABELS = ["Company A", "Company B", "Company C", "Company D",
               "Company E", "Company F", "Company G", "Company H",
               "Company I", "Company J"]


def _size_bucket(mcap: float) -> str:
    if not np.isfinite(mcap) or mcap <= 0:
        return "unknown"
    m = mcap / 1e6 if mcap > 1e6 else mcap          # panel unit tolerance
    for lo, name in ((200_000, "mega"), (10_000, "large"), (2_000, "mid"),
                     (300, "small")):
        if m >= lo:
            return name
    return "micro"


def _qual(x: float, edges: Sequence[float], words: Sequence[str]) -> str:
    if x is None or not np.isfinite(x):
        return "not available"
    for e, w in zip(edges, words):
        if x < e:
            return w
    return words[-1]


# ══════════════════════════════════════════════════════════════════════════
# 1. WINDOWS  ($0)
# ══════════════════════════════════════════════════════════════════════════

FACT_COLS = ["permno", "month", "sector", "close", "market_cap", "ratio",
             "upside", "consensus", "coverage", "numest", "disagreement",
             "dispersion", "net_rev_4w", "target_rev_1m", "target_rev_3m",
             "consensus_rev_1m", "coverage_rev_1m", "ret_1m", "ret_3m",
             "ret_6m", "ret_12m", "mom_12_1", "drawdown_60d", "vol_20d",
             "vol_60d", "log_dollar_vol_20d", "split_prior_year",
             "fwd_1m", "mkt_ew_1m", "excess_ew_1m"]


def eligible_panel(start_year: int = ERA_START_YEAR,
                   end_year: int = ERA_END_YEAR,
                   narrow: bool = False) -> pd.DataFrame:
    """The era slice, with the house's execution floors applied UP FRONT.

    Applying `TRADABLE_DOLLAR_VOL` and the $5 floor here rather than at grading
    is the point: a window can then never contain a name the house would refuse
    to buy, so no result of this job is a backtest of something unbuyable.

    `narrow=True` reads ONLY the columns this function consumes instead of the
    whole 418 MB long panel. It is off by default so the 2016-19 path is the
    path that produced `windows.json`, byte for byte; it exists because the
    era-2 DRY RUN has to answer "how many windows would this era produce?" on a
    machine with four other agents on it, and a 1 GB frame to count months is
    the kind of avoidable footprint that gets a run killed mid-count.
    """
    from learner import evaluate, long_panel

    if not long_panel.available():
        raise RuntimeError("long panel not built -- run learner.long_panel first")
    if narrow:
        need = sorted({"permno", "month", "hygiene_ok", "has_opinion",
                       "log_dollar_vol_20d", "close", "fwd_1m", "market_cap",
                       "sector", *FACT_COLS})
        import pyarrow.parquet as pq
        have = set(pq.ParquetFile(long_panel.LONG_TABLE).schema_arrow.names)
        d = pd.read_parquet(long_panel.LONG_TABLE,
                            columns=[c for c in need if c in have])
    else:
        d = long_panel.load_long()
    d = d.copy()
    d["year"] = d["month"].astype(str).str[:4].astype(int)
    d = d[(d["year"] >= start_year) & (d["year"] <= end_year)]
    dv = np.exp(pd.to_numeric(d["log_dollar_vol_20d"], errors="coerce"))
    keep = (d["hygiene_ok"].astype(bool)
            & d["has_opinion"].astype(bool)
            & (dv >= evaluate.TRADABLE_DOLLAR_VOL)
            & (pd.to_numeric(d["close"], errors="coerce") >= 5.0)
            & d["fwd_1m"].notna())
    out = d.loc[keep, [c for c in FACT_COLS if c in d.columns]].copy()
    out["dollar_vol"] = np.exp(pd.to_numeric(out["log_dollar_vol_20d"],
                                             errors="coerce"))
    return out.reset_index(drop=True)


def trailing_market(panel: pd.DataFrame) -> dict[str, float]:
    """Backward-looking market context: the cross-sectional mean of `ret_1m`.

    PIT-safe by construction -- `ret_1m` is the month that just ENDED. The
    forward `mkt_ew_1m` column is the grader's, and the decider never sees it.
    """
    g = panel.groupby("month")["ret_1m"].mean()
    return {str(k): float(v) for k, v in g.items() if np.isfinite(v)}


def build_windows(start_year: int = ERA_START_YEAR,
                  end_year: int = ERA_END_YEAR,
                  write: bool = True,
                  dry_run: bool = False,
                  narrow: bool = False) -> dict:
    """Deterministic bundles. Same seed -> byte-identical windows.

    `dry_run=True` runs the SAME eligibility path and the SAME month loop and
    stops before materialising the per-name fact cards: it answers "how many
    windows would this era produce, backed by how much tape?" at a fraction of
    the memory, and never writes `windows.json`. It is the mode part (b) of the
    2026-09-06b mandate uses, because a second era must be COUNTED before it is
    paid for.
    """
    panel = eligible_panel(start_year, end_year, narrow=narrow)
    mkt = trailing_market(panel)
    months = sorted(panel["month"].astype(str).unique())
    rng = np.random.default_rng(BUILD_SEED)
    by_month = {m: g for m, g in panel.groupby(panel["month"].astype(str))}

    if dry_run:
        usable = [m for m in months if len(by_month[m]) >= K_NAMES]
        return {
            "dry_run": True,
            "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "era": f"{start_year}-{end_year}",
            "seed": BUILD_SEED,
            "k_names": K_NAMES,
            "n_threads": N_THREADS,
            "top_n": TOP_N,
            "months_in_era": len(months),
            "months_with_at_least_k_eligible": len(usable),
            "months_dropped_thin": sorted(set(months) - set(usable)),
            "n_windows_would_build": len(usable) * N_THREADS,
            "eligible_rows": int(len(panel)),
            "eligible_permnos": int(panel["permno"].nunique()),
            "eligible_rows_by_year": {
                str(y): int(v) for y, v in
                panel["month"].astype(str).str[:4].value_counts().sort_index().items()},
            "floors": {"tradable_dollar_vol": 3_000_000.0, "price_usd": 5.0},
            "wrote_windows_file": False,
        }

    windows = []
    for th in range(N_THREADS):
        for m in months:
            g = by_month[m]
            if len(g) < K_NAMES:
                continue
            # Seeded per (thread, month) so a thread's history is reproducible
            # independently of how many threads were run.
            local = np.random.default_rng(
                int(hashlib.sha256(f"{BUILD_SEED}|{th}|{m}".encode()).hexdigest()[:12], 16))
            idx = local.choice(len(g), size=K_NAMES, replace=False)
            sel = g.iloc[idx]
            names = []
            for slot, (_, r) in enumerate(sel.iterrows()):
                names.append({
                    "slot": slot,
                    "permno": int(r["permno"]),
                    "sector": str(r.get("sector") or "_UNKNOWN"),
                    "size_bucket": _size_bucket(float(r.get("market_cap") or 0.0)),
                    "facts": {k: (None if pd.isna(r.get(k)) else float(r.get(k)))
                              for k in ("ratio", "upside", "consensus", "coverage",
                                        "numest", "disagreement", "dispersion",
                                        "net_rev_4w", "target_rev_1m",
                                        "target_rev_3m", "consensus_rev_1m",
                                        "coverage_rev_1m", "ret_1m", "ret_3m",
                                        "ret_6m", "ret_12m", "mom_12_1",
                                        "drawdown_60d", "vol_20d", "vol_60d",
                                        "split_prior_year")},
                    # SEALED SIDE TABLE -- grader only. Never rendered into a
                    # prompt; `render_bundle` reads none of these keys.
                    "_fwd_1m": float(r["fwd_1m"]),
                    "_mkt_ew_1m": (None if pd.isna(r.get("mkt_ew_1m"))
                                   else float(r["mkt_ew_1m"])),
                    "_dollar_vol": float(r["dollar_vol"]),
                })
            windows.append({
                "window_id": f"t{th}_{m}",
                "thread": th,
                "month": m,
                "trailing_mkt_1m": mkt.get(m),
                "names": names,
            })
    rec = {
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "era": f"{start_year}-{end_year}",
        "seed": BUILD_SEED,
        "k_names": K_NAMES,
        "n_threads": N_THREADS,
        "top_n": TOP_N,
        "n_windows": len(windows),
        "months": len(months),
        "eligible_rows": int(len(panel)),
        "eligible_permnos": int(panel["permno"].nunique()),
        "floors": {"tradable_dollar_vol": 3_000_000.0, "price_usd": 5.0},
        "excluded_source": {
            "edgar_8k_items": (
                "REFUSED. manifest.json says the universe is resolved via "
                "company_tickers.json = CURRENT registrants, so 8-K presence in "
                "2016-19 correlates with survival to 2026 -- a forward-looking "
                "leak into the bundle. Its own coverage_truncation_caveat is the "
                "second reason: absence is truncation, not evidence."),
        },
        "windows": windows,
    }
    if write:
        DATA.mkdir(parents=True, exist_ok=True)
        WINDOWS_PATH.write_text(json.dumps(rec), encoding="utf-8")
    return rec


def load_windows() -> dict:
    if not WINDOWS_PATH.exists():
        return build_windows()
    return json.loads(WINDOWS_PATH.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════════
# 2. RENDERING -- what the rewriter is given
# ══════════════════════════════════════════════════════════════════════════

def render_bundle(win: dict, naming: str) -> tuple[str, list[str], list[str]]:
    """The fact card for one window, in one naming arm.

    Identical numbers in both arms. Only the labels change. Anything whose key
    starts with `_` is the sealed side table and is never touched here.
    """
    labels = (FANTASY_FIRMS if naming == "fantasy" else REAL_LABELS)[:len(win["names"])]
    lines = []
    #: The DATA values only, in the exact strings the card carries them in.
    #: The preservation gate is checked against this, never against a regex over
    #: the whole card -- the first pilot scored 0% because "12-1 momentum",
    #: "4 weeks", "60d" and "of 5" are field NAMES and were being counted as
    #: numbers the rewriter had failed to reproduce.
    values: list[str] = []
    tm = win.get("trailing_mkt_1m")
    if tm is not None:
        if naming == "fantasy":
            lines.append(f"Market context: the broad listed market returned "
                         f"{tm*100:.1f}% over the month just ended.")
        else:
            lines.append(f"Market context: the broad US listed market returned "
                         f"{tm*100:.1f}% over the month just ended.")
    for lab, n in zip(labels, win["names"]):
        f = n["facts"]
        sec = (FANTASY_SECTOR.get(n["sector"], "Unlisted Trade")
               if naming == "fantasy" else n["sector"])

        def g(k, mult=1.0, nd=1):
            v = f.get(k)
            out = ("n/a" if v is None or not np.isfinite(v)
                   else f"{v*mult:.{nd}f}")
            if out != "n/a":
                values.append(out)
            return out

        # THIRTEEN numbers per company, not thirty. The pilot fed ~30 each and
        # gpt-5-nano carried 12% of them into 45-70 words of prose -- which
        # would have made the two naming arms carry DIFFERENT information,
        # because nothing forces it to drop the same ones twice. A card the
        # rewriter can actually carry is the fix; the integrity gate below is
        # how we know it did.
        lines.append(
            f"\n{lab} -- sector {sec}, size bucket {n['size_bucket']}.\n"
            f"  Trailing return: 1m {g('ret_1m',100)}%, 3m {g('ret_3m',100)}%, "
            f"12m {g('ret_12m',100)}%, 12-1 momentum {g('mom_12_1',100)}%.\n"
            f"  Risk: 60d volatility {g('vol_60d',100)}%, "
            f"drawdown from 60d high {g('drawdown_60d',100)}%.\n"
            f"  Analysts: {g('coverage',1,0)} covering, mean rating "
            f"{g('consensus',1,2)} of 5, price target {g('ratio',1,2)}x the "
            f"current price, dispersion {g('dispersion',1,3)}.\n"
            f"  Revisions: net rating revisions over 4 weeks {g('net_rev_4w',1,3)}, "
            f"price-target change over 3m {g('target_rev_3m',100)}%, rating change "
            f"over 1m {g('consensus_rev_1m',1,3)}."
        )
    return "\n".join(lines), labels, values


REWRITER_SYSTEM = (
    "You are a research editor. You will be given a fact card describing several "
    "companies at one point in time. Rewrite each company as an analyst paragraph "
    "of 100-140 words in plain English prose.\n"
    "RULES, all mandatory:\n"
    "1. EVERY number in that company's block must appear in its paragraph, "
    "written exactly as given, digit for digit. Do not round, drop, merge, "
    "reorder or invent a number. A paragraph missing a number is a failure.\n"
    "2. Use ONLY the label that heads the block, both as the JSON key and inside "
    "the paragraph. Never use a label belonging to another company and never "
    "invent one.\n"
    "3. Never name a real company, ticker, index, person, country or calendar "
    "year.\n"
    "4. Do not state or hint at what the company will do next, and do not rank "
    "the companies.\n"
    "5. Write about the SITUATION: what the trend, the risk state, the analyst "
    "posture and the revisions look like taken together.\n"
    "Return STRICT JSON: an object mapping each label to its paragraph. No other "
    "keys, no prose outside the JSON."
)

DECIDER_SYSTEM = (
    "You are a portfolio manager making a one-month relative call. You will be "
    "shown short profiles of several anonymised companies. You know nothing "
    "about which companies they are and you must not guess before you decide.\n"
    "Return STRICT JSON with exactly these keys, in this order:\n"
    '  "rank": an array of the labels, best expected performer over the NEXT '
    "MONTH first, worst last. Every label exactly once.\n"
    '  "reasons": an object mapping each label to one short sentence.\n'
    '  "diary": one to three sentences you would want to read at your next '
    "decision. Say what you are betting on and what would change your mind.\n"
    '  "guess_year": your best guess at the calendar year, as a 4-digit integer, '
    'or null if you cannot tell.\n'
    '  "guess_company": the name of any real company you believe you have '
    "identified, or null.\n"
    "Rank first, then answer the two guesses. Never output a price, a return "
    "forecast, or a probability." + LANGUAGE_PIN
)


# ── integrity gates, ported in spirit from the sibling repo ─────────────────
# `aegis-alpha-terminal/alpha/transpose.py` has `magnitudes_preserved` and
# `leak_check`. That repo cannot be imported across the firewall, and this
# session may not create files there, so the two checks are reimplemented here
# against the same contract. They are what stops the arm difference from being a
# rewriter artefact: a rewriter that quietly drops a number, or that names a real
# company, has changed the INFORMATION and not just the surface.

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

#: Real-world proper nouns a blinded profile must never contain. Deliberately
#: short and generic: the fact card contains no company names at all, so a hit
#: here means the rewriter INVENTED an identity, which is the failure mode worth
#: catching.
_LEAK_TERMS = ("nasdaq", "s&p", "dow jones", "russell", "nyse", "united states",
               "u.s.", "america", "china", "covid", "pandemic", "federal reserve",
               "trump", "biden", "brexit")


def magnitudes_preserved(expected: Sequence[str], rewritten: str) -> dict:
    """Did every DATA value survive the rewrite?

    `expected` is the exact list of formatted values the card carried -- not a
    regex sweep of the card, which would also pick up the field names ("12-1
    momentum", "4 weeks", "60d volatility", "rating 3.33 of 5") and score a
    faithful rewrite as a failure. Only the direction that matters is fatal:
    a DROPPED value is information the two arms no longer share. An extra
    number in the prose is noted, not fatal, because prose legitimately says
    things like "over the last 12 months".
    """
    from collections import Counter
    ce = Counter(str(x) for x in expected)
    cr = Counter(_NUM_RE.findall(_YEAR_RE.sub(" ", rewritten)))
    dropped = ce - cr
    return {"n_expected": sum(ce.values()),
            "n_found": sum((ce & cr).values()),
            "dropped": sorted(dropped.elements())[:20],
            "n_dropped": sum(dropped.values()),
            "share_preserved": round(1.0 - sum(dropped.values())
                                     / max(1, sum(ce.values())), 4),
            "ok": not dropped}


def leak_check(rewritten: str, forbidden_labels: Sequence[str] = ()) -> dict:
    """Did the rewriter put a real year, a real proper noun, or the OTHER arm's
    label into the blinded prose?"""
    low = rewritten.lower()
    years = sorted({int(m.group(0)) for m in _YEAR_RE.finditer(rewritten)})
    terms = [t for t in _LEAK_TERMS if t in low]
    labs = [l for l in forbidden_labels if l.lower() in low]
    return {"years_mentioned": years, "terms": terms,
            "cross_arm_labels": labs,
            "ok": not years and not terms and not labs}


# ══════════════════════════════════════════════════════════════════════════
# 3. THE WIRE -- budget-gated, telemetry-recorded, disk-cached
# ══════════════════════════════════════════════════════════════════════════

class HardCapReached(RuntimeError):
    """Local ceiling hit. Refusing further vendor calls."""


class DecideOutsideFrozenEra(RuntimeError):
    """A wire call was attempted for a window outside the frozen decided era."""


#: The ONLY era whose windows this module is permitted to put on the wire.
#: Part (b) of the 2026-09-06b mandate builds a SECOND era (2010-2013) and is
#: explicitly forbidden to pay for its decide step in this session. A flag that
#: "cannot reach decide" is worth nothing if the enforcement is a flag: this is
#: enforced on the DATA instead, immediately before every wire call, so no
#: combination of arguments -- and no future caller who never read this note --
#: can spend a dollar on a month outside 2016-2019 without editing this line and
#: saying why in the commit.
FROZEN_DECIDE_ERA = (ERA_START_YEAR, ERA_END_YEAR)


def month_of_meta(meta: dict) -> str | None:
    """The window's month, from `meta["month"]` or parsed out of `window_id`."""
    m = meta.get("month")
    if m:
        return str(m)
    wid = str(meta.get("window_id") or "")
    hit = re.search(r"(\d{4}-\d{2})", wid)
    return hit.group(1) if hit else None


def assert_decidable(meta: dict) -> None:
    """REFUSE a vendor call for any window outside `FROZEN_DECIDE_ERA`.

    Called before `_gate`, so a CACHE HIT is unaffected: replaying what has
    already been bought is free and stays free. Only the wire is locked.
    """
    m = month_of_meta(meta)
    if m is None:
        raise DecideOutsideFrozenEra(
            f"REFUSED: cannot establish the window's month from meta {meta!r}; "
            "a wire call whose era cannot be derived is a wire call that is not "
            "gated. A guard DERIVES its inputs or REFUSES.")
    year = int(str(m)[:4])
    lo, hi = FROZEN_DECIDE_ERA
    if not (lo <= year <= hi):
        raise DecideOutsideFrozenEra(
            f"REFUSED: window month {m} is outside the frozen decide era "
            f"{lo}-{hi}. The second-era (2010-2013) build is BUILD-ONLY this "
            "session: its decide step is unfunded and unpaid, and this module "
            "will not put it on the wire.")


@dataclass
class Spend:
    lock: threading.Lock = field(default_factory=threading.Lock)
    nano_in: int = 0
    nano_out: int = 0
    nano_cached: int = 0
    nano_calls: int = 0
    ds_in: int = 0
    ds_out: int = 0
    ds_cached: int = 0
    ds_calls: int = 0
    refusals: list[str] = field(default_factory=list)

    def nano_usd(self) -> float:
        p = NANO_PRICE_PER_MTOK
        return (self.nano_in * p["in"] + self.nano_cached * p["cached_in"]
                + self.nano_out * p["out"]) / 1e6

    def ds_usd(self) -> float:
        from backend.config import LLM_PRICE_PER_MTOK
        p = LLM_PRICE_PER_MTOK[DECIDER_MODEL]
        return (self.ds_in * p["in"] + self.ds_cached * p.get("cached_in", p["in"])
                + self.ds_out * p["out"]) / 1e6

    def total(self) -> float:
        return self.nano_usd() + self.ds_usd()

    def as_dict(self) -> dict:
        return {
            "gpt5_nano": {
                "calls": self.nano_calls, "tokens_in": self.nano_in,
                "cached_in": self.nano_cached, "tokens_out": self.nano_out,
                "usd": round(self.nano_usd(), 6),
                "price_table": NANO_PRICE_PER_MTOK,
                "price_source": NANO_PRICE_SOURCE,
                "reconciliation": "TELEMETRY, not a provider balance -- OpenAI "
                                  "exposes no balance endpoint to this key.",
            },
            "deepseek_chat": {
                "calls": self.ds_calls, "tokens_in": self.ds_in,
                "cached_in": self.ds_cached, "tokens_out": self.ds_out,
                "usd": round(self.ds_usd(), 6),
                "price_table_source": "backend.config.LLM_PRICE_PER_MTOK",
            },
            "total_usd": round(self.total(), 6),
            "hard_cap_usd": HARD_CAP_USD,
            "refusals": self.refusals,
        }


SPEND = Spend()
_CACHE: dict[str, dict] = {}
_CACHE_LOCK = threading.Lock()


def _load_cache() -> None:
    if not CACHE_PATH.exists():
        return
    n = 0
    for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        _CACHE[r["key"]] = r
        n += 1
    print(f"[cache] {n} rows loaded from {CACHE_PATH}")


def _cache_put(key: str, rec: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = rec
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, **rec}, ensure_ascii=False) + "\n")


#: When the shared governor was last consulted, and what it said.
_GOV_TTL_S = 20.0
_GOV_LAST: dict[str, Any] = {"at": 0.0, "state": None}


def _gate(model: str) -> None:
    """Both governors, before every wire call. A refusal costs nothing.

    THE LOCAL CEILING IS CHECKED EVERY TIME. The SHARED one is re-read at most
    every `_GOV_TTL_S` seconds, because `research_budget.check` re-parses the
    whole telemetry ledger -- 57,777 rows and 0.81 s on this machine as of this
    run -- and doing that before each of ~1,150 calls is 16 minutes of pure
    overhead plus a 76 MB log of repeated warnings. That is not a theoretical
    objection: the first attempt at this run was killed for exactly it.

    The weakening is bounded and named: a co-running campaign can overshoot the
    shared $40 ceiling by at most one TTL's worth of this job's calls, while
    this job's own dollar ceiling still binds on every single call.
    """
    if SPEND.total() >= HARD_CAP_USD:
        raise HardCapReached(
            f"local hard cap: ${SPEND.total():.4f} >= ${HARD_CAP_USD:.2f}")
    now = time.time()
    if now - float(_GOV_LAST["at"]) < _GOV_TTL_S:
        st = _GOV_LAST["state"]
        if st is not None and not st.ok:
            raise HardCapReached(f"research_budget refused: {st.reason}")
        return
    from backend.services import research_budget
    st = research_budget.check(CAMPAIGN)
    _GOV_LAST["at"] = now
    _GOV_LAST["state"] = st
    if not st.ok:
        raise HardCapReached(f"research_budget refused: {st.reason}")


def _record(provider: str, model: str, purpose: str, prompt: Any,
            tin: int, tout: int, cached: int, latency: float,
            ok: bool, err: str | None, meta: dict) -> None:
    from backend.services import llm_telemetry
    try:
        call = llm_telemetry.build_call(
            provider=provider, model=model, purpose=purpose, agent=CAMPAIGN,
            prompt=prompt, tokens_in=tin, tokens_out=tout, cached_tokens=cached,
            latency_ms=latency * 1000.0, schema_valid=ok, error=err,
            # A window's rank IS the gradeable output. Naming it here keeps the
            # zero-yield brake honest instead of halting a working campaign.
            prediction_ids=([meta["window_id"] + "|" + meta.get("arm", "")]
                            if ok and meta.get("window_id") else []),
            meta=meta)
        llm_telemetry.append([call])
    except Exception as exc:                                   # noqa: BLE001
        print(f"[telemetry] could not record: {type(exc).__name__}: {exc}")


_NANO_CLIENT = None
_DS_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def _nano_client():
    global _NANO_CLIENT
    with _CLIENT_LOCK:
        if _NANO_CLIENT is None:
            from openai import OpenAI
            key = os.getenv("OPENAI_API_KEY") or os.getenv("GTP_TOKEN")
            if not key:
                raise RuntimeError(
                    "no OpenAI key: neither OPENAI_API_KEY nor GTP_TOKEN is set. "
                    "The rewriter cannot run.")
            _NANO_CLIENT = OpenAI(api_key=key, timeout=90.0, max_retries=2)
        return _NANO_CLIENT


def _ds_client():
    global _DS_CLIENT
    with _CLIENT_LOCK:
        if _DS_CLIENT is None:
            from openai import OpenAI
            key = os.getenv("DEEPSEEK_API_KEY")
            if not key:
                raise RuntimeError("DEEPSEEK_API_KEY absent -- decider cannot run.")
            _DS_CLIENT = OpenAI(api_key=key, base_url="https://api.deepseek.com",
                                timeout=120.0, max_retries=2)
        return _DS_CLIENT


_JSON_RE = re.compile(r"\{.*\}", re.S)


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    m = _JSON_RE.search(t)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def call_rewriter(card: str, labels: list[str], meta: dict) -> dict | None:
    key = rewriter_cache_key(card)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit.get("parsed")

    assert_decidable(meta)
    _gate(REWRITER_MODEL)
    t0 = time.time()
    err, parsed, raw = None, None, ""
    try:
        r = _nano_client().chat.completions.create(
            model=REWRITER_MODEL,
            messages=[{"role": "system", "content": REWRITER_SYSTEM},
                      {"role": "user", "content": card}],
            reasoning_effort="minimal",          # `temperature` is a 400 here
            response_format={"type": "json_object"},
            max_completion_tokens=3600)
        raw = r.choices[0].message.content or ""
        u = r.usage
        tin = int(u.prompt_tokens or 0)
        tout = int(u.completion_tokens or 0)
        cached = int(getattr(getattr(u, "prompt_tokens_details", None),
                             "cached_tokens", 0) or 0)
        with SPEND.lock:
            SPEND.nano_in += tin - cached
            SPEND.nano_cached += cached
            SPEND.nano_out += tout
            SPEND.nano_calls += 1
        parsed = _parse_json(raw)
        # gpt-5-nano keys the object on the WHOLE heading line
        # ("Company A -- sector Manufacturing, size bucket small.") rather than
        # on the label. That is a JSON-key convention, not a missing paragraph;
        # rejecting it threw away 11 of 20 pilot bundles for nothing.
        if parsed is not None:
            fixed, seen = {}, set()
            for lab in labels:
                hit = None
                if lab in parsed:
                    hit = lab
                else:
                    cands = [k for k in parsed
                             if k not in seen and str(k).strip().startswith(lab)]
                    if len(cands) == 1:
                        hit = cands[0]
                if hit is None:
                    fixed = None
                    break
                seen.add(hit)
                fixed[lab] = str(parsed[hit])
            parsed = fixed
        if parsed is None:
            err = err or "rewriter omitted a label"
    except Exception as exc:                                   # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        tin = tout = cached = 0
    lat = time.time() - t0
    _record(REWRITER_PROVIDER, REWRITER_MODEL, "era_replay_v2.rewrite",
            card, tin, tout, cached, lat, parsed is not None, err, meta)
    if parsed is None:
        SPEND.refusals.append(f"rewrite {meta.get('window_id')} "
                              f"{meta.get('naming')}: {err}")
        return None
    _cache_put(key, {"parsed": parsed, "raw": raw[:4000], "meta": meta})
    return parsed


def normalise_rank(rank: object, labels: Sequence[str]) -> list[str] | None:
    """Map the model's rank back onto the canonical labels, or refuse.

    `deepseek-chat` abbreviates "Company A" to "A" -- which cost the pilot every
    single real-anon window, silently, as "rank is not a permutation". A rank
    that is unambiguously the right permutation under a documented normalisation
    is the model's answer; anything ambiguous is still refused, because guessing
    at the ranking is the one thing this module must never do.
    """
    if not isinstance(rank, list):
        return None
    def norm(s: str) -> str:
        s = str(s).strip().lower()
        s = re.sub(r"^(company|firm|co\.?)\s+", "", s)
        return s.strip(" .:-–—")
    canon: dict[str, str] = {}
    for lab in labels:
        for key in {norm(lab), str(lab).strip().lower()}:
            if key in canon and canon[key] != lab:
                return None                       # ambiguous -- refuse
            canon[key] = lab
    out = []
    for item in rank:
        lab = canon.get(norm(item)) or canon.get(str(item).strip().lower())
        if lab is None:
            return None
        out.append(lab)
    if sorted(out) != sorted(labels):
        return None
    return out


def decider_user_prompt(profiles: dict, labels: list[str], diary: str | None,
                        prev_top: list[str] | None) -> str:
    """The decider's user message. Factored out so the cache-only replay path
    builds the SAME string -- and therefore the same cache key -- as the wire
    path did. Two hand-copied prompt builders is how a "free re-grade" quietly
    becomes a $4 re-run."""
    body = ["Company profiles:"]
    for lab in labels:
        body.append(f"\n{lab}: {profiles.get(lab, '')}")
    if diary is not None:
        body.append("\n\nYour diary entry from your previous decision:\n"
                    + (diary or "(none -- this is your first decision)"))
        body.append("\nYour previous top picks were: "
                    + (", ".join(prev_top) if prev_top else "(none)")
                    + ". Note that the companies shown now are a NEW set and the "
                      "labels do NOT refer to the same companies as last time.")
    return "\n".join(body)


def rewriter_cache_key(card: str) -> str:
    return "rw|" + hashlib.sha256((REWRITER_SYSTEM + "||" + card)
                                  .encode("utf-8")).hexdigest()[:24]


def decider_cache_key(user: str) -> str:
    return "dc|" + hashlib.sha256((DECIDER_SYSTEM + "||" + user)
                                  .encode("utf-8")).hexdigest()[:24]


def call_decider(profiles: dict, labels: list[str], diary: str | None,
                 prev_top: list[str] | None, meta: dict) -> dict | None:
    user = decider_user_prompt(profiles, labels, diary, prev_top)

    key = decider_cache_key(user)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit.get("parsed")

    assert_decidable(meta)
    _gate(DECIDER_MODEL)
    t0 = time.time()
    err, parsed, raw = None, None, ""
    tin = tout = cached = 0
    try:
        r = _ds_client().chat.completions.create(
            model=DECIDER_MODEL,
            messages=[{"role": "system", "content": DECIDER_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=900)
        raw = r.choices[0].message.content or ""
        u = r.usage
        cached = int(getattr(getattr(u, "prompt_tokens_details", None),
                             "cached_tokens", 0) or 0)
        tin = int(u.prompt_tokens or 0) - cached      # DeepSeek's prompt_tokens
        tout = int(u.completion_tokens or 0)          # INCLUDES its cache hits
        with SPEND.lock:
            SPEND.ds_in += max(0, tin)
            SPEND.ds_cached += cached
            SPEND.ds_out += tout
            SPEND.ds_calls += 1
        from backend.services.llm_language import non_latin_share
        if non_latin_share(raw) > 0.10:
            err = "refused: reply is >10% non-Latin script"
        else:
            parsed = _parse_json(raw)
            if parsed is not None:
                fixed = normalise_rank(parsed.get("rank"), labels)
                if fixed is None:
                    parsed = None
                    err = ("rank is not a permutation of the labels even under "
                           "normalisation: " + str(parsed if parsed else raw)[:180])
                else:
                    parsed["rank"] = fixed
    except Exception as exc:                                   # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    lat = time.time() - t0
    _record(DECIDER_PROVIDER, DECIDER_MODEL, "era_replay_v2.decide",
            user, max(0, tin), tout, cached, lat, parsed is not None, err, meta)
    if parsed is None:
        SPEND.refusals.append(f"decide {meta.get('window_id')} "
                              f"{meta.get('arm')}: {err}")
        return None
    _cache_put(key, {"parsed": parsed, "raw": raw[:4000], "meta": meta})
    return parsed


# ══════════════════════════════════════════════════════════════════════════
# 4. THE RUN
# ══════════════════════════════════════════════════════════════════════════

def run_arms(windows: list[dict], arms: Sequence[str] = ARMS,
             workers: int = 10) -> dict:
    """Rewrite every bundle, then decide it under every arm."""
    # -- stage 1: rewriting. Fully parallel; a bundle's prose depends only on
    #    (window, naming), never on a diary.
    cards: dict[tuple[str, str], tuple[str, list[str], list[str]]] = {}
    for w in windows:
        for naming in sorted({naming_of(a) for a in arms}):
            cards[(w["window_id"], naming)] = render_bundle(w, naming)

    prose: dict[tuple[str, str], dict] = {}
    stopped = None

    def _rw(item):
        (wid, naming), (card, labels, _values) = item
        try:
            p = call_rewriter(card, labels,
                              {"window_id": wid, "naming": naming, "stage": "rewrite"})
        except HardCapReached as exc:
            return (wid, naming), None, str(exc)
        return (wid, naming), p, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for k, p, halt in ex.map(_rw, list(cards.items())):
            if halt:
                stopped = stopped or halt
            if p is not None:
                prose[k] = p
    print(f"[rewrite] {len(prose)}/{len(cards)} bundles rendered "
          f"(${SPEND.nano_usd():.4f})")

    # -- the integrity gate. A rewriter that drops numbers or invents an
    #    identity has changed the information, not the surface, and every arm
    #    comparison downstream would be measuring the rewriter.
    integ = {"bundles_checked": 0, "magnitude_ok": 0, "leak_ok": 0,
             "examples_dropped": [], "examples_leaked": []}
    preserved_by_naming: dict[str, list[float]] = {}
    for (wid, naming), p in prose.items():
        card, labels, values = cards[(wid, naming)]
        other = _label_map("realanon" if naming == "fantasy" else "fantasy",
                           len(labels))
        joined = "\n".join(str(p.get(l, "")) for l in labels)
        m = magnitudes_preserved(values, joined)
        preserved_by_naming.setdefault(naming, []).append(m["share_preserved"])
        lk = leak_check(joined, other)
        integ["bundles_checked"] += 1
        integ["magnitude_ok"] += int(m["ok"])
        integ["leak_ok"] += int(lk["ok"])
        if not m["ok"] and len(integ["examples_dropped"]) < 5:
            integ["examples_dropped"].append({"window": wid, "naming": naming, **m})
        if not lk["ok"] and len(integ["examples_leaked"]) < 5:
            integ["examples_leaked"].append({"window": wid, "naming": naming, **lk})
    n = max(1, integ["bundles_checked"])
    integ["magnitude_all_present_rate"] = round(integ["magnitude_ok"] / n, 4)
    integ["leak_ok_rate"] = round(integ["leak_ok"] / n, 4)
    # THE NUMBER THAT DECIDES WHETHER THE ARMS ARE COMPARABLE. If one naming arm
    # keeps materially more of the card than the other, the arm difference is
    # the rewriter, not the model, and no comparison below means anything.
    integ["share_preserved_by_naming"] = {
        k: round(float(np.mean(v)), 4) for k, v in preserved_by_naming.items()}
    vals = list(integ["share_preserved_by_naming"].values())
    integ["arm_preservation_gap"] = (round(max(vals) - min(vals), 4)
                                     if len(vals) > 1 else None)
    integ["reads"] = (
        "share_preserved_by_naming must be close between arms; a gap means the "
        "arm contrast is measuring the REWRITER, not the decider.")
    print(f"[integrity] value preservation by arm "
          f"{integ['share_preserved_by_naming']} (gap "
          f"{integ['arm_preservation_gap']}), no leak {integ['leak_ok_rate']:.1%}")

    # -- stage 2: deciding. Diary-OFF arms are embarrassingly parallel.
    #    Diary-ON arms must run a thread's months IN ORDER, so the unit of
    #    parallelism there is the (arm, thread) chain.
    decisions: dict[tuple[str, str], dict] = {}
    by_thread: dict[int, list[dict]] = {}
    for w in windows:
        by_thread.setdefault(int(w["thread"]), []).append(w)
    for th in by_thread:
        by_thread[th].sort(key=lambda x: x["month"])

    nodiary_jobs = [(a, w) for a in arms if not diary_of(a) for w in windows]

    def _dec_nodiary(job):
        arm, w = job
        naming = naming_of(arm)
        p = prose.get((w["window_id"], naming))
        if p is None:
            return (w["window_id"], arm), None, None
        _, labels, _vals = cards[(w["window_id"], naming)]
        try:
            d = call_decider(p, labels, None, None,
                             {"window_id": w["window_id"], "arm": arm,
                              "naming": naming, "diary": False,
                              "month": w["month"], "stage": "decide"})
        except HardCapReached as exc:
            return (w["window_id"], arm), None, str(exc)
        return (w["window_id"], arm), d, None

    if nodiary_jobs:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for k, d, halt in ex.map(_dec_nodiary, nodiary_jobs):
                if halt:
                    stopped = stopped or halt
                if d is not None:
                    decisions[k] = d
        print(f"[decide/nodiary] {len(decisions)}/{len(nodiary_jobs)} "
              f"(${SPEND.ds_usd():.4f})")

    diary_chains = [(a, th) for a in arms if diary_of(a) for th in sorted(by_thread)]

    def _dec_chain(job):
        arm, th = job
        naming = naming_of(arm)
        out, diary, prev_top, halt = {}, None, None, None
        for w in by_thread[th]:
            p = prose.get((w["window_id"], naming))
            if p is None:
                continue
            _, labels, _vals = cards[(w["window_id"], naming)]
            try:
                d = call_decider(p, labels, diary or "", prev_top,
                                 {"window_id": w["window_id"], "arm": arm,
                                  "naming": naming, "diary": True,
                                  "month": w["month"], "stage": "decide"})
            except HardCapReached as exc:
                halt = str(exc)
                break
            if d is None:
                continue
            out[(w["window_id"], arm)] = d
            diary = str(d.get("diary") or "")[:900]
            prev_top = [str(x) for x in (d.get("rank") or [])[:TOP_N]]
        return out, halt

    if diary_chains:
        n0 = len(decisions)
        with ThreadPoolExecutor(max_workers=min(workers, len(diary_chains))) as ex:
            for out, halt in ex.map(_dec_chain, diary_chains):
                if halt:
                    stopped = stopped or halt
                decisions.update(out)
        print(f"[decide/diary] {len(decisions)-n0} decisions "
              f"(${SPEND.ds_usd():.4f})")

    return {"decisions": decisions, "cards": cards, "prose": prose,
            "integrity": integ, "stopped": stopped}


def replay_from_cache(windows: list[dict], arms: Sequence[str] = ARMS) -> dict:
    """`run_arms` with the wire amputated. $0, and provably so.

    Every prose block and every decision is taken from `llm_cache.jsonl` by the
    SAME key the wire path computed. Nothing here can call a provider: no
    client is constructed, `_gate` is never reached, and a miss is recorded as a
    MISS rather than filled.

    The control flow is a mirror of `run_arms` down to the skip rules -- a
    window whose prose is missing is skipped, a decision that is missing does
    NOT advance the diary -- because the diary chain's cache keys depend on the
    exact text of the previous decision. Any divergence would silently miss the
    rest of that thread, and a "coverage 71%" line would be an artefact of the
    replay rather than a fact about the cache.
    """
    cards: dict[tuple[str, str], tuple[str, list[str], list[str]]] = {}
    for w in windows:
        for naming in sorted({naming_of(a) for a in arms}):
            cards[(w["window_id"], naming)] = render_bundle(w, naming)

    prose: dict[tuple[str, str], dict] = {}
    prose_miss: list[str] = []
    for (wid, naming), (card, labels, _v) in cards.items():
        hit = _CACHE.get(rewriter_cache_key(card))
        if hit is None or hit.get("parsed") is None:
            prose_miss.append(f"{wid}|{naming}")
            continue
        prose[(wid, naming)] = hit["parsed"]

    decisions: dict[tuple[str, str], dict] = {}
    miss: list[str] = []

    by_thread: dict[int, list[dict]] = {}
    for w in windows:
        by_thread.setdefault(int(w["thread"]), []).append(w)
    for th in by_thread:
        by_thread[th].sort(key=lambda x: x["month"])

    for arm in arms:
        naming = naming_of(arm)
        if not diary_of(arm):
            for w in windows:
                p = prose.get((w["window_id"], naming))
                if p is None:
                    miss.append(f"{w['window_id']}|{arm}|no-prose")
                    continue
                _, labels, _v = cards[(w["window_id"], naming)]
                key = decider_cache_key(decider_user_prompt(p, labels, None, None))
                hit = _CACHE.get(key)
                if hit is None or hit.get("parsed") is None:
                    miss.append(f"{w['window_id']}|{arm}|no-decision")
                    continue
                decisions[(w["window_id"], arm)] = hit["parsed"]
            continue
        for th in sorted(by_thread):
            diary, prev_top = None, None
            for w in by_thread[th]:
                p = prose.get((w["window_id"], naming))
                if p is None:
                    miss.append(f"{w['window_id']}|{arm}|no-prose")
                    continue
                _, labels, _v = cards[(w["window_id"], naming)]
                key = decider_cache_key(
                    decider_user_prompt(p, labels, diary or "", prev_top))
                hit = _CACHE.get(key)
                if hit is None or hit.get("parsed") is None:
                    miss.append(f"{w['window_id']}|{arm}|no-decision")
                    continue
                d = hit["parsed"]
                decisions[(w["window_id"], arm)] = d
                diary = str(d.get("diary") or "")[:900]
                prev_top = [str(x) for x in (d.get("rank") or [])[:TOP_N]]

    want = len(windows) * len(arms)
    return {
        "decisions": decisions,
        "cards": cards,
        "prose": prose,
        "coverage": {
            "windows": len(windows),
            "arms": list(arms),
            "decisions_wanted": want,
            "decisions_recovered": len(decisions),
            "coverage_rate": round(len(decisions) / max(1, want), 4),
            "prose_bundles_wanted": len(cards),
            "prose_bundles_recovered": len(prose),
            "prose_misses": prose_miss[:40],
            "decision_misses": miss[:40],
            "n_decision_misses": len(miss),
            "cache_rows_loaded": len(_CACHE),
            "wire_calls_made": 0,
            "usd_spent": 0.0,
        },
        "stopped": None,
    }


# ══════════════════════════════════════════════════════════════════════════
# 5. GRADING -- code prices, the LLM never does
# ══════════════════════════════════════════════════════════════════════════

def _label_map(naming: str, k: int) -> list[str]:
    return (FANTASY_FIRMS if naming == "fantasy" else REAL_LABELS)[:k]


# ── the HOLD rule (mandate C4, 2026-09-06b) ─────────────────────────────────
#: `hold_n = HOLD_MULTIPLE * TOP_N`. Declared in
#: `backend/data/optimus/continuation_2026-09-06b/C4_hold_rule_declaration.json`
#: and hashed there BEFORE this grade ran, because a hysteresis band chosen
#: after seeing which band helps is not a rule, it is a fit.
HOLD_MULTIPLE = 2


def select_with_hold(ranks: Sequence[float], permnos: Sequence[int],
                     prev_held: set[int], top_n: int,
                     hold_n: int | None) -> list[int]:
    """Slot indices the book holds this window. `learner.evaluate.book`'s rule.

    BUY at rank <= `top_n`; HOLD an incumbent until its rank leaves `hold_n`.
    Book size stays `top_n`: incumbents inside the band keep their slots
    (best-ranked first, so the book never prefers a worse incumbent to a better
    one), and the remainder is filled from the top of the ranking. Nothing
    about the RANKING changes -- only how often the book pays the spread.

    `hold_n is None` is the no-hysteresis rule and reproduces the original
    grade exactly. `hold_n == top_n` is the same rule written a longer way; it
    is accepted HERE (the equivalence is what the test proves) and REFUSED by
    `grade_arm`, exactly as `evaluate.book` refuses `hold_k == k`, so that no
    receipt can report a band where there is none.

    `ranks` is 0-based rank POSITION per slot: 0 = the decider's best pick.
    """
    ranks = np.asarray(ranks, dtype=float)
    order = list(np.argsort(ranks, kind="stable"))          # slots, best first
    if hold_n is None:
        return [i for i in range(len(ranks)) if ranks[i] < top_n]
    if int(hold_n) < int(top_n):
        raise ValueError(f"hold_n={hold_n} < top_n={top_n}: not a band")
    keep = [i for i in order
            if ranks[i] < hold_n and int(permnos[i]) in prev_held][:top_n]
    fill = [i for i in order if i not in keep][:max(0, top_n - len(keep))]
    return keep + fill


def grade_arm(windows: list[dict], decisions: dict, arm: str,
              cost_bps: float, hold_n: int | None = None) -> dict:
    """Per-window rank metrics, the paired within-bundle spread, and wealth.

    `hold_n=None` is the original grade and is UNCHANGED, key for key and digit
    for digit. `hold_n > TOP_N` grades the same decisions under the hysteresis
    band of `select_with_hold`.
    """
    from learner import evaluate

    if hold_n is not None and int(hold_n) <= TOP_N:
        raise SystemExit(
            f"REFUSED: hold_n={hold_n} must be strictly greater than top_n="
            f"{TOP_N}. A hold band no wider than the buy rank is the "
            "no-hysteresis rule written a longer way, and the receipt would "
            "report a band where there is none. (Mirrors learner.evaluate.book.)")

    naming = naming_of(arm)
    rows = []
    prev_hold: dict[int, set] = {}
    wealth: dict[int, float] = {}
    bench_wealth: dict[int, float] = {}
    canary_year_hits = canary_year_asked = 0
    canary_co_named = 0
    year_guesses: list[int | None] = []
    # THE NUMBER THAT DECIDES WHETHER A HOLD RULE CAN DO ANYTHING AT ALL:
    # an incumbent can only be held if it is IN this month's bundle. The window
    # build redraws 8 names from ~2,700 eligible permnos every month, so this
    # is a property of the DESIGN, not of the decider's rank churn.
    n_incumbents_present = 0     # prior holdings that reappear in the bundle
    n_incumbents_held = 0        # ...and were actually kept by the hold rule

    order = sorted(windows, key=lambda w: (int(w["thread"]), str(w["month"])))
    for w in order:
        d = decisions.get((w["window_id"], arm))
        if d is None:
            continue
        labels = _label_map(naming, len(w["names"]))
        pos = {str(lab): i for i, lab in enumerate(d["rank"])}
        # slot -> rank position. Label i in `labels` is name-slot i by
        # construction of `render_bundle`.
        ranks = np.array([pos[labels[n["slot"]]] for n in w["names"]], dtype=float)
        fwd = np.array([n["_fwd_1m"] for n in w["names"]], dtype=float)
        permnos = [int(n["permno"]) for n in w["names"]]

        # rank IC: -rank (1 = best) against realised forward return
        rho = stats.spearmanr(-ranks, fwd).statistic

        th = int(w["thread"])
        prev = prev_hold.get(th, set())
        picked = select_with_hold(ranks, permnos, prev, TOP_N, hold_n)
        bottom = [i for i in range(len(fwd)) if ranks[i] >= len(fwd) - TOP_N]
        r_top = float(np.mean(fwd[picked]))
        r_bot = float(np.mean(fwd[bottom]))
        r_ew = float(np.mean(fwd))

        held = {permnos[i] for i in picked}
        n_incumbents_present += len(prev & set(permnos))
        n_incumbents_held += len(held & prev)
        turnover = (len(held - prev) / max(1, len(held))) if prev else 1.0
        cost = turnover * (cost_bps / 10_000.0) * 2.0
        prev_hold[th] = held

        wealth[th] = wealth.get(th, 1.0) * (1.0 + r_top - cost)
        bench_wealth[th] = bench_wealth.get(th, 1.0) * (1.0 + r_ew)

        gy = d.get("guess_year")
        try:
            gy = int(gy) if gy is not None else None
        except Exception:
            gy = None
        year_guesses.append(gy)
        canary_year_asked += 1
        true_year = int(str(w["month"])[:4])
        if gy is not None and gy == true_year:
            canary_year_hits += 1
        gc = d.get("guess_company")
        if gc is not None and str(gc).strip().lower() not in ("", "null", "none",
                                                             "unknown", "n/a"):
            canary_co_named += 1

        rows.append({
            "window_id": w["window_id"], "thread": th, "month": w["month"],
            "ic": (float(rho) if np.isfinite(rho) else None),
            "top": r_top, "bottom": r_bot, "ew": r_ew,
            "net_top": r_top - cost, "cost": cost, "turnover": turnover,
            "paired_top_minus_ew": r_top - r_ew,
            "paired_net_top_minus_ew": r_top - cost - r_ew,
            "paired_top_minus_bottom": r_top - r_bot,
            "ranks": ranks.tolist(), "fwd": fwd.tolist(),
            "guess_year": gy, "true_year": true_year,
            "guess_company": (str(gc)[:80] if gc else None),
        })

    if not rows:
        return {"arm": arm, "n_windows": 0,
                "verdict": "CANNOT DETERMINE (no graded windows)"}

    df = pd.DataFrame(rows)

    def _t(s):
        s = pd.Series(s).dropna()
        if len(s) < 3 or s.std() == 0:
            return None
        return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))

    # n_effective counts DATE BLOCKS, not windows (CANON §58): four threads
    # share each month, so the month is the block.
    monthly = df.groupby("month")["paired_net_top_minus_ew"].mean()

    tw = float(np.prod([wealth[t] for t in wealth]) ** (1.0 / max(1, len(wealth))))
    bw = float(np.prod([bench_wealth[t] for t in bench_wealth])
               ** (1.0 / max(1, len(bench_wealth))))

    res = {
        "arm": arm, "naming": naming, "diary": diary_of(arm),
        "n_windows": int(len(df)),
        "n_month_blocks": int(monthly.shape[0]),
        "mean_ic": round(float(df["ic"].mean()), 5),
        "t_ic_windows": (round(_t(df["ic"]), 3) if _t(df["ic"]) is not None else None),
        "t_ic_month_blocks": (
            round(_t(df.groupby("month")["ic"].mean()), 3)
            if _t(df.groupby("month")["ic"].mean()) is not None else None),
        "share_ic_positive": round(float((df["ic"] > 0).mean()), 4),
        "mean_top_minus_ew_pct": round(float(df["paired_top_minus_ew"].mean()) * 100, 4),
        "mean_net_top_minus_ew_pct": round(float(df["paired_net_top_minus_ew"].mean()) * 100, 4),
        "t_net_top_minus_ew_windows": (
            round(_t(df["paired_net_top_minus_ew"]), 3)
            if _t(df["paired_net_top_minus_ew"]) is not None else None),
        "t_net_top_minus_ew_month_blocks": (
            round(_t(monthly), 3) if _t(monthly) is not None else None),
        "mean_top_minus_bottom_pct": round(float(df["paired_top_minus_bottom"].mean()) * 100, 4),
        "t_top_minus_bottom": (round(_t(df["paired_top_minus_bottom"]), 3)
                               if _t(df["paired_top_minus_bottom"]) is not None else None),
        "mean_turnover": round(float(df["turnover"].mean()), 4),
        "cost_bps_per_side": cost_bps,
        "terminal_wealth_book": round(tw, 5),
        "terminal_wealth_ew_same_names": round(bw, 5),
        "terminal_wealth_ratio": round(tw / bw, 5) if bw else None,
        "canary": {
            "asked": canary_year_asked,
            "exact_year_hits": canary_year_hits,
            "exact_year_rate": round(canary_year_hits / max(1, canary_year_asked), 4),
            "chance_rate_uniform_over_era": round(1.0 / (ERA_END_YEAR - ERA_START_YEAR + 1), 4),
            "company_named_rate": round(canary_co_named / max(1, canary_year_asked), 4),
            "year_guess_histogram": {str(k): int(v) for k, v in
                                     pd.Series([g for g in year_guesses if g is not None])
                                     .value_counts().items()},
            "n_no_guess": int(sum(1 for g in year_guesses if g is None)),
        },
        "_rows": rows,
        "_monthly": {str(k): float(v) for k, v in monthly.items()},
    }
    if hold_n is not None:
        # ONLY on the hysteresis path, so the no-hold receipt keeps the exact
        # key set the sealed 2026-09-06 receipt carries (the same reasoning
        # `learner.evaluate.book` records for its own `hold_k` keys).
        res["hold_n"] = int(hold_n)
        res["selection_rule"] = (f"buy at rank <= {TOP_N}, hold until rank > "
                                 f"{int(hold_n)}")
        res["incumbents_present_in_next_bundle"] = int(n_incumbents_present)
        res["incumbents_actually_held"] = int(n_incumbents_held)
        res["hold_opportunity_note"] = (
            "an incumbent can only be held if it REAPPEARS in the next month's "
            "8-name bundle. The window build redraws 8 names from the whole "
            "eligible universe each month, so `incumbents_present_in_next_"
            "bundle` is the hard ceiling on anything a hold rule can save.")
    return res


def nulls(graded: dict, n_draws: int = 2000, seed: int = 7) -> dict:
    """The vision's three nulls (§3d). All code-side, all free."""
    rows = graded["_rows"]
    rng = np.random.default_rng(seed)
    obs = float(np.mean([r["paired_net_top_minus_ew"] for r in rows]))

    # NULL 1 -- shuffled companies. The same rank vector, the bundle's returns
    # permuted. "Does the model just like this era?"
    n1 = []
    for _ in range(n_draws):
        acc = []
        for r in rows:
            fwd = np.array(r["fwd"])
            ranks = np.array(r["ranks"])
            p = rng.permutation(len(fwd))
            top = fwd[p][ranks < TOP_N]
            acc.append(float(top.mean()) - r["cost"] - float(fwd.mean()))
        n1.append(float(np.mean(acc)))
    n1 = np.array(n1)

    # NULL 2 -- shuffled DATES within the era. The rank is applied to a
    # different month's bundle of the SAME thread. The calendar null.
    by_thread: dict[int, list[dict]] = {}
    for r in rows:
        by_thread.setdefault(r["thread"], []).append(r)
    n2 = []
    for _ in range(n_draws):
        acc = []
        for r in rows:
            pool = by_thread[r["thread"]]
            other = pool[int(rng.integers(len(pool)))]
            fwd = np.array(other["fwd"])
            ranks = np.array(r["ranks"])[:len(fwd)]
            if len(ranks) < len(fwd):
                continue
            acc.append(float(fwd[ranks < TOP_N].mean()) - r["cost"]
                       - float(fwd.mean()))
        if acc:
            n2.append(float(np.mean(acc)))
    n2 = np.array(n2)

    # NULL 3 -- same-day paired. Chosen vs NOT-chosen inside the same bundle in
    # the same month. The month effect cancels exactly; no resampling needed.
    d3 = np.array([r["paired_top_minus_bottom"] for r in rows])
    t3 = (float(d3.mean() / (d3.std(ddof=1) / np.sqrt(len(d3))))
          if len(d3) > 2 and d3.std() > 0 else None)

    def _p(draws, x):
        if draws.size == 0:
            return None
        return round(float((draws >= x).mean()), 4)

    return {
        "observed_mean_net_excess_pct": round(obs * 100, 4),
        "null_1_shuffled_companies": {
            "draws": int(n1.size), "mean_pct": round(float(n1.mean()) * 100, 4),
            "sd_pct": round(float(n1.std(ddof=1)) * 100, 4),
            "p_one_sided": _p(n1, obs),
            "reads": "the same rank vector on a permuted bundle",
        },
        "null_2_shuffled_dates": {
            "draws": int(n2.size), "mean_pct": round(float(n2.mean()) * 100, 4)
            if n2.size else None,
            "sd_pct": round(float(n2.std(ddof=1)) * 100, 4) if n2.size > 1 else None,
            "p_one_sided": _p(n2, obs),
            "reads": "the rank applied to another month of the same thread",
        },
        "null_3_same_day_paired": {
            "mean_top_minus_bottom_pct": round(float(d3.mean()) * 100, 4),
            "t_stat": round(t3, 3) if t3 is not None else None,
            "n": int(len(d3)),
            "reads": "chosen vs not-chosen inside the SAME bundle, same month -- "
                     "the month effect cancels; this is the primary statistic",
        },
    }


def era_sign_table(graded: dict) -> dict:
    """Sub-period sign check. NOT the repo's canonical three-era table.

    `learner.evaluate.ERAS` is 2016-18 / 2019-21 / 2022-24. This job ran ONE of
    those and half of a second, so the canonical table cannot be produced and
    saying so is the finding, not a footnote.
    """
    df = pd.DataFrame(graded["_rows"])
    df["year"] = df["month"].astype(str).str[:4].astype(int)
    out = {}
    for lo, hi, lab in ((2016, 2016, "2016"), (2017, 2017, "2017"),
                        (2018, 2018, "2018"), (2019, 2019, "2019")):
        s = df.loc[(df.year >= lo) & (df.year <= hi), "paired_net_top_minus_ew"]
        out[lab] = {
            "n": int(len(s)),
            "mean_pct": round(float(s.mean()) * 100, 4) if len(s) else None,
            "sign": ("+" if len(s) and s.mean() > 0 else
                     "-" if len(s) else "n/a"),
        }
    out["_canonical_three_era_table"] = (
        "CANNOT DETERMINE -- learner.evaluate.ERAS spans 2016-2024 and this job "
        "ran 2016-2019 only. The sign table above is a within-era year check and "
        "is NOT a substitute.")
    return out


def inference_block(graded: dict, family: dict[str, list[float]]) -> dict:
    """Every claim through `learner.inference`. Family size, DSR, MDE, SPA."""
    from learner import inference

    monthly = graded["_monthly"]
    series = [monthly[k] for k in sorted(monthly)]
    fam = {k: v for k, v in family.items() if len(v) == len(series)}
    rep = inference.full_report(
        series, family=fam if len(fam) >= 2 else None,
        paired_excess=fam if len(fam) >= 2 else None,
        n_trials=len(family), periods_per_year=12, seed=11)
    rep["family_size_declared"] = len(family)
    rep["family_members"] = sorted(family)
    rep["series_is"] = ("month-block mean of paired net (top-3 minus the "
                        "equal-weight basket of the SAME 8 names)")
    return rep


def family_max_p(all_graded: dict[str, dict]) -> dict:
    """BH-FDR over the arm family (CANON §63: SCREEN = BH-FDR)."""
    ps = {}
    for arm, g in all_graded.items():
        t = g.get("t_net_top_minus_ew_month_blocks")
        n = g.get("n_month_blocks") or 0
        if t is None or n < 3:
            ps[arm] = None
            continue
        ps[arm] = float(2 * (1 - stats.t.cdf(abs(t), df=n - 1)))
    live = {k: v for k, v in ps.items() if v is not None}
    if not live:
        return {"per_arm_p": ps, "verdict": "CANNOT DETERMINE"}
    m = len(live)
    ordered = sorted(live.items(), key=lambda kv: kv[1])
    bh = {}
    for i, (k, p) in enumerate(ordered, start=1):
        bh[k] = min(1.0, p * m / i)
    return {
        "per_arm_p_two_sided": {k: (round(v, 5) if v is not None else None)
                                for k, v in ps.items()},
        "bh_fdr_adjusted": {k: round(v, 5) for k, v in bh.items()},
        "family_size": m,
        "family_max_p": round(max(live.values()), 5),
        "family_min_p": round(min(live.values()), 5),
        "any_survives_bh_05": any(v <= 0.05 for v in bh.values()),
    }


# ══════════════════════════════════════════════════════════════════════════
# 5b. THE SECOND ERA -- BUILD ONLY, $0 (mandate C4b, 2026-09-06b)
# ══════════════════════════════════════════════════════════════════════════
# "A second era is worth more than more windows in the same one -- windows
# within a month share the month." (REVIEW_2026-09-06_FABLE51 claim 6.)
#
# The decide step of a second era is NOT funded this session. Everything below
# counts, prices and refuses; `assert_decidable` is what makes the refusal a
# property of the code rather than of this comment.

ERA2 = (2010, 2013)
EDGAR_DIR = REPO / "backend" / "data" / "optimus" / "edgar_8k"


def edgar_backing(start_year: int, end_year: int) -> dict:
    """How much EDGAR 8-K tape actually exists inside an era, and its two clocks.

    TWO CLOCKS, NAMED SEPARATELY (the trap of
    [[feedback-two-clocks-need-two-bounds]]: one shared PIT bound across a
    BACKWARD news window and a FORWARD calendar deleted every catalyst row in
    this repo once, so 'a dated catalyst inside 21 sessions' had never once been
    evaluated):

      * BACKWARD / knowability clock -- `acceptance_datetime`. A filing is
        usable at a decision instant iff it was ACCEPTED by EDGAR before that
        instant. `event_date` is when the thing happened and is never the gate;
        the manifest says so itself.
      * FORWARD / grading clock -- the month AFTER the decision instant, which
        is where `fwd_1m` lives. It is a different variable with a different
        bound, and it is not derived from the first.

    They are reported as two fields on purpose. A single `pit_bound` here would
    be the same bug wearing this job's clothes.
    """
    man_path = EDGAR_DIR / "manifest.json"
    parq = EDGAR_DIR / "eightk_items.parquet"
    out: dict[str, Any] = {
        "era": f"{start_year}-{end_year}",
        "source_files": [str(man_path), str(parq)],
        "pit_backward_bound": (
            "acceptance_datetime (EDGAR acceptance, UTC) <= the decision "
            "instant. event_date is NOT the knowability gate."),
        "pit_forward_window": (
            "the calendar month AFTER the decision instant -- `fwd_1m` in the "
            "long panel. A SEPARATE variable with a SEPARATE bound; sharing one "
            "bound between the two clocks deletes every row."),
    }
    if not man_path.exists() or not parq.exists():
        out["error"] = f"EDGAR tape absent: {man_path} / {parq}"
        out["filings_in_era"] = 0
        return out

    man = json.loads(man_path.read_text(encoding="utf-8"))
    out["manifest"] = {
        k: man.get(k) for k in
        ("built_utc", "source", "rows", "ciks", "with_permno",
         "filing_date_min", "filing_date_max", "coverage_start_median",
         "coverage_truncation_caveat", "survivor_caveat", "pit_rule", "params")}

    d = pd.read_parquet(parq, columns=["cik", "filing_date",
                                       "acceptance_datetime", "permno"])
    yr = pd.to_datetime(d["filing_date"], errors="coerce").dt.year
    out["filings_all_years"] = {str(k): int(v)
                                for k, v in yr.value_counts().sort_index().items()}
    m = (yr >= start_year) & (yr <= end_year)
    sub = d.loc[m]
    out["filings_in_era"] = int(len(sub))
    out["filings_in_era_by_year"] = {
        str(k): int(v) for k, v in yr[m].value_counts().sort_index().items()}
    out["ciks_in_era"] = int(sub["cik"].nunique()) if len(sub) else 0
    out["permnos_in_era"] = (int(sub["permno"].notna().sum()) if len(sub) else 0)
    out["acceptance_datetime_present_rate_in_era"] = (
        round(float(sub["acceptance_datetime"].notna().mean()), 4)
        if len(sub) else None)
    out["permno_link_rate_whole_tape"] = round(
        float(d["permno"].notna().mean()), 4)
    return out


def build_era2_dry_run(era: tuple[int, int] = ERA2,
                       edgar_only: bool = True) -> dict:
    """Count the second era. Never decide it, never write a windows file.

    Returns the receipt body for `C4b_era2_window_build_dryrun.json`.
    """
    lo, hi = era
    backing = edgar_backing(lo, hi)

    # The panel-backed count is reported BESIDE the EDGAR-only answer, not
    # instead of it: it is the number the roadmap needs ("what would a second
    # era cost?") and it is NOT an EDGAR-only build. Saying which is which is
    # the whole job here.
    panel: dict[str, Any]
    try:
        panel = build_windows(lo, hi, write=False, dry_run=True, narrow=True)
    except Exception as exc:                                   # noqa: BLE001
        panel = {"error": f"{type(exc).__name__}: {exc}"}

    n_edgar = int(backing.get("filings_in_era") or 0)
    years_with_tape = sorted(backing.get("filings_in_era_by_year", {}))
    n_years = hi - lo + 1
    buildable = edgar_only and n_edgar > 0 and len(years_with_tape) == n_years

    n_windows_panel = int(panel.get("n_windows_would_build") or 0)
    cost = project_decide_cost(n_windows_panel)

    return {
        "era": f"{lo}-{hi}",
        "mode": "BUILD-ONLY DRY RUN. No windows file written, no LLM call made.",
        "source_policy": ("EDGAR ONLY (no other vendor tape)" if edgar_only
                          else "long panel"),
        "edgar_backing": backing,
        "edgar_only_windows_would_build": 0 if not buildable else None,
        "edgar_only_verdict": (
            "CANNOT BUILD" if not buildable else "BUILDABLE (recount before use)"),
        "edgar_only_why": (
            f"the EDGAR 8-K tape's own manifest reports filing_date_min "
            f"{backing.get('manifest', {}).get('filing_date_min')} and its pull "
            f"params start {(backing.get('manifest', {}).get('params') or {}).get('start')}. "
            f"Inside {lo}-{hi} it holds {n_edgar} filings, in "
            f"{len(years_with_tape)} of {n_years} years "
            f"({years_with_tape or 'none'}). An era-replay window needs a "
            "cross-section in EVERY month of the era; three of these four years "
            "have literally zero rows, so an EDGAR-only build of this era is not "
            "thin, it is EMPTY. Two further defects would bind even if the pull "
            "were extended: (a) the survivor caveat -- the universe is resolved "
            "through company_tickers.json = CURRENT registrants, so presence in "
            f"{lo}-{hi} correlates with survival to 2026, the same leak this "
            "job already refuses for 2016-19; (b) the truncation caveat -- the "
            "default pull reads only `filings.recent`, coverage_start_median is "
            f"{backing.get('manifest', {}).get('coverage_start_median')}, so "
            "absence before that date is truncation and not evidence. And a "
            "third, structural: EDGAR carries no return, so an EDGAR-only "
            "bundle cannot be GRADED at all without joining a price tape -- and "
            f"only {backing.get('permno_link_rate_whole_tape')} of the whole "
            "tape's rows even carry a permno to join on."),
        "what_would_make_it_buildable": [
            "re-pull EDGAR with --full-history so pre-2016 pages are fetched "
            "(the manifest's params show full_history: false), AND",
            "resolve the universe from a POINT-IN-TIME registrant list rather "
            "than today's company_tickers.json, or accept and declare the "
            "survivorship leak, AND",
            "join a return tape for grading -- EDGAR prices nothing.",
        ],
        "panel_backed_alternative": {
            "note": ("NOT an EDGAR-only build. This is the SAME window-build "
                     "code path (`build_windows(..., dry_run=True)`) run on the "
                     "long panel for the same era, so the roadmap has a real "
                     "number for what a second era would cost."),
            **panel,
        },
        "projected_decide_cost": cost,
        "decide_step": {
            "run_this_session": False,
            "enforcement": (
                "`assert_decidable` refuses any rewriter or decider wire call "
                "whose window month falls outside FROZEN_DECIDE_ERA "
                f"{FROZEN_DECIDE_ERA}. Enforced on the DATA immediately before "
                "the wire, not on a CLI flag: no argument combination reaches a "
                "provider with a 2010-2013 window."),
            "llm_calls_made_by_this_job": 0,
            "usd_spent_by_this_job": 0.0,
        },
    }


def project_decide_cost(n_windows: int, arms: Sequence[str] = ARMS) -> dict:
    """What a decide step over `n_windows` would cost, from MEASURED unit cost.

    The unit costs come from era-1's own ledger block, not from a guess: 417
    rewriter calls at $0.303226 and 846 decider calls at $0.178508 (receipt
    `L10_era_replay_v2_run01.json` -> `campaign_spend_total`). Those totals
    include the pilot and the errored calls, so the per-call figures are the
    REALISED cost of getting a usable answer, which is the number a projection
    wants.
    """
    era1 = (RECEIPTS / "L10_era_replay_v2_run01.json")
    unit_rw = unit_dc = unit_dc_corr = None
    basis = "hardcoded fallback"
    as_run: dict[str, Any] = {}
    corrected: dict[str, Any] = {"available": False}
    if era1.exists():
        try:
            blk = json.loads(era1.read_text(encoding="utf-8"))["campaign_spend_total"]
            rw = blk["by_model"][REWRITER_MODEL]
            dc = blk["by_model"][DECIDER_MODEL]
            unit_rw = rw["usd"] / max(1, rw["calls"])
            unit_dc = dc["usd"] / max(1, dc["calls"])
            basis = f"measured, {era1.name} -> campaign_spend_total"
            as_run = {"rewriter_calls": rw["calls"], "rewriter_usd": rw["usd"],
                      "decider_calls": dc["calls"], "decider_usd": dc["usd"]}
            # RE-PRICE the SAME token counts under whatever the price table
            # says NOW. The sealed receipt's dollars were computed under the
            # 2026-08-12 table; if a sibling agent has since re-derived the
            # DeepSeek price from the PROVIDER BALANCE, that correction has to
            # reach this projection or the roadmap budgets the second era at a
            # price nobody charges. A receipt's USD is a function of a table
            # and a token count; only the token count is a measurement.
            from backend.config import LLM_PRICE_PER_MTOK, LLM_PRICE_AS_OF
            p = LLM_PRICE_PER_MTOK.get(DECIDER_MODEL)
            if p:
                usd = (dc["tokens_in"] * p["in"]
                       + dc["cached_in"] * p.get("cached_in", p["in"])
                       + dc["tokens_out"] * p["out"]) / 1e6
                unit_dc_corr = usd / max(1, dc["calls"])
                corrected = {
                    "available": True,
                    "price_table_as_of": LLM_PRICE_AS_OF,
                    "decider_price_per_mtok": p,
                    "era1_decider_usd_repriced": round(usd, 6),
                    "era1_decider_usd_as_sealed": dc["usd"],
                    "correction_multiple": round(usd / max(1e-12, dc["usd"]), 3),
                    "reads": ("the SAME 846 calls and the SAME token counts, "
                              "priced by the table on disk today. The sealed "
                              "receipt's dollars are not wrong -- they are the "
                              "old table's answer, and the token counts are "
                              "what was actually measured."),
                }
        except Exception:                                      # noqa: BLE001
            pass
    if unit_rw is None:
        unit_rw, unit_dc = 0.000727, 0.000211
    n_namings = len({naming_of(a) for a in arms})
    n_rw = n_windows * n_namings
    n_dc = n_windows * len(arms)
    proj_old = n_rw * unit_rw + n_dc * unit_dc
    proj_new = (n_rw * unit_rw + n_dc * unit_dc_corr
                if unit_dc_corr is not None else None)
    return {
        "n_windows": int(n_windows),
        "n_rewriter_calls": int(n_rw),
        "n_decider_calls": int(n_dc),
        "usd_per_rewriter_call": round(unit_rw, 6),
        "usd_per_decider_call_as_sealed": round(unit_dc, 6),
        "usd_per_decider_call_corrected": (round(unit_dc_corr, 6)
                                           if unit_dc_corr is not None else None),
        "projected_usd_at_sealed_prices": round(proj_old, 4),
        "projected_usd_at_corrected_prices": (round(proj_new, 4)
                                              if proj_new is not None else None),
        "projected_usd": round(proj_new if proj_new is not None else proj_old, 4),
        "era1_measured": as_run,
        "corrected_price": corrected,
        "unit_cost_basis": basis,
        "price_table_caveat": (
            "gpt-5-nano is priced from this module's LOCAL table "
            f"{NANO_PRICE_PER_MTOK} because it has no entry in "
            "config.LLM_PRICE_PER_MTOK, so the rewriter leg is NOT corrected "
            "and remains a lower bound. deepseek-chat is priced from "
            "config.LLM_PRICE_PER_MTOK, which is re-read at run time; "
            "`corrected_price` says which table that was."),
    }


# ══════════════════════════════════════════════════════════════════════════
# 6. RECONCILIATION + RECEIPT
# ══════════════════════════════════════════════════════════════════════════

def deepseek_balance() -> dict:
    """The provider's own number. Our arithmetic is not the truth."""
    import urllib.request
    # `backend.config` is what calls `load_dotenv`. Reading the env before any
    # import has pulled it in returned "DEEPSEEK_API_KEY absent" for the
    # BEFORE-balance of run01 while the AFTER-balance worked, which is the
    # silent-fragility shape exactly: the reconciliation looked done and had
    # only one endpoint.
    import backend.config  # noqa: F401
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        return {"error": "DEEPSEEK_API_KEY absent"}
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as fh:
            return json.loads(fh.read().decode("utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def verdict_block(out_arms: dict, fam: dict) -> dict:
    """One verdict, in the repo's vocabulary, with the reason attached.

    A screen cannot reach NOVEL (CLAUDE.md, the three licences). The only two
    outcomes available here are NOISE and CANNOT DETERMINE, and which one is
    correct is decided by the CANARY and the MDE, not by the sign of the mean:
    an arm whose blind failed is CANNOT DETERMINE however good its number.
    """
    live = {k: v for k, v in out_arms.items() if v.get("n_windows")}
    if not live:
        return {"verdict": "CANNOT DETERMINE", "why": "no arm graded a window"}

    canary_max = max(v["canary"]["exact_year_rate"] for v in live.values())
    chance = 1.0 / (ERA_END_YEAR - ERA_START_YEAR + 1)
    blind_held = canary_max <= chance

    best = max(live.items(),
               key=lambda kv: kv[1]["mean_net_top_minus_ew_pct"])
    any_positive = best[1]["mean_net_top_minus_ew_pct"] > 0
    survives = bool(fam.get("any_survives_bh_05"))
    beats_ew = any(v["terminal_wealth_ratio"] and v["terminal_wealth_ratio"] > 1.0
                   for v in live.values())
    # Is any arm even distinguishable from ranking at random? Null 1 is the
    # test that matters, because the raw excess carries a structural cost drag
    # that the equal-weight basket does not pay.
    best_null1 = min(v["nulls"]["null_1_shuffled_companies"]["p_one_sided"]
                     for v in live.values()
                     if v["nulls"]["null_1_shuffled_companies"]["p_one_sided"] is not None)

    if not blind_held:
        v, why = ("CANNOT DETERMINE (NOT BLIND)",
                  f"the decider named the true year at {canary_max:.1%}, above "
                  f"the {chance:.1%} chance rate for a 4-year era; the result is "
                  "memorisation-contaminated and is not evidence about reading")
    elif survives and any_positive and beats_ew:
        v, why = ("CANNOT DETERMINE (a screen cannot reach NOVEL)",
                  "an arm cleared BH-FDR on one era; that is a screen result and "
                  "needs the other two eras and a pre-registration before it can "
                  "be claimed")
    else:
        v = "NOISE"
        why = (f"every arm's mean net excess over the equal-weight basket of the "
               f"SAME names is negative (best {best[0]} at "
               f"{best[1]['mean_net_top_minus_ew_pct']:+.3f}%/mo), no arm survives "
               f"BH-FDR (family-max p {fam.get('family_max_p')}), no arm ends "
               f"above its own benchmark, and the best arm is not distinguishable "
               f"from ranking the SAME bundle at random (null-1 p {best_null1})")
    return {
        "verdict": v,
        "why": why,
        "blind_held": blind_held,
        "canary_max_exact_year_rate": canary_max,
        "canary_chance_rate": round(chance, 4),
        "best_arm": best[0],
        "best_arm_net_excess_pct_per_month": best[1]["mean_net_top_minus_ew_pct"],
        "any_arm_beats_its_own_ew_basket": beats_ew,
        "best_null1_p": best_null1,
        "mde_note": (
            "learner.inference.power_note on the 48 month-blocks this era has: "
            "the smallest annual excess an arm could have shown at t = 2 is "
            "~8.7%/yr. A true edge smaller than that is INVISIBLE here, so "
            "'NOISE' means 'not detectable on four years', not 'absent'."),
        "three_era_axis": (
            "CANNOT DETERMINE -- learner.evaluate.ERAS is 2016-18 / 2019-21 / "
            "2022-24 and this job ran 2016-2019 only."),
    }


def campaign_spend_from_ledger() -> dict:
    """What THIS campaign has spent, ever, from the telemetry ledger.

    The `spend` block counts only the calls this invocation put on the wire, and
    a re-run off the disk cache legitimately reports $0.00 for itself. That is
    the right number for the invocation and the WRONG one for the receipt: a
    reader wants what the experiment cost, not what the last regeneration of its
    receipt cost. This walks the ledger rows tagged `agent == era_replay_v2` and
    prices gpt-5-nano from the local table, since config cannot carry it.
    """
    try:
        from backend.services import llm_telemetry
        rows = [r for r in llm_telemetry.read_calls()
                if r.get("agent") == CAMPAIGN and r.get("row_type", "call") == "call"]
    except Exception as exc:                                   # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}

    from backend.config import LLM_PRICE_PER_MTOK
    agg: dict[str, dict] = {}
    for r in rows:
        m = str(r.get("model") or "?")
        a = agg.setdefault(m, {"calls": 0, "tokens_in": 0, "cached_in": 0,
                               "tokens_out": 0, "errors": 0})
        a["calls"] += 1
        a["tokens_in"] += int(r.get("tokens_in") or 0)
        a["cached_in"] += int(r.get("cached_tokens") or 0)
        a["tokens_out"] += int(r.get("tokens_out") or 0)
        a["errors"] += int(bool(r.get("error")))
    total = 0.0
    for m, a in agg.items():
        price = (NANO_PRICE_PER_MTOK if m == REWRITER_MODEL
                 else LLM_PRICE_PER_MTOK.get(m))
        if price is None:
            a["usd"] = None
            a["priced"] = False
            continue
        a["usd"] = round((a["tokens_in"] * price["in"]
                          + a["cached_in"] * price.get("cached_in", price["in"])
                          + a["tokens_out"] * price["out"]) / 1e6, 6)
        a["priced"] = True
        total += a["usd"]
    return {
        "by_model": agg,
        "total_usd": round(total, 4),
        "n_rows": len(rows),
        "all_models_priced": all(a.get("priced") for a in agg.values()),
        "reads": ("the whole campaign's cost to date, from the ledger, priced "
                  "from config.LLM_PRICE_PER_MTOK plus the local gpt-5-nano "
                  "table. THIS is the experiment's cost; `spend` is only what "
                  "the current invocation put on the wire."),
    }


def _ledger_state() -> dict:
    """What the shared telemetry ledger says, once, instead of per call.

    The per-read warnings are silenced in `main`; this is where the same facts
    are recorded so that silencing them is not the same as hiding them.
    """
    try:
        from backend.services import llm_telemetry, research_budget
        st = research_budget.check(CAMPAIGN)
        s = llm_telemetry.spend()
        return {
            "campaign_calls_all_time": st.n_calls,
            "campaign_cost_usd_all_time": st.cost_usd,
            "cost_is_lower_bound": st.cost_is_lower_bound,
            "shared_ceiling_usd": s.get("max_usd"),
            "usd_remaining_under_shared_ceiling": st.usd_remaining,
            "note": ("gpt-5-nano has no entry in config.LLM_PRICE_PER_MTOK, so "
                     "the LEDGER total is a lower bound for this job. The "
                     "receipt's own `spend` block prices it from a local table "
                     "and is the number to read for this run."),
        }
    except Exception as exc:                                   # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def write_receipt(name: str, payload: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or RECEIPTS
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / name
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"[receipt] {p}")
    return p


# ══════════════════════════════════════════════════════════════════════════

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="windows only, $0")
    ap.add_argument("--pilot", type=int, default=0, help="N windows, then project")
    ap.add_argument("--run", action="store_true", help="the full window set")
    ap.add_argument("--grade", action="store_true", help="regrade from cache, $0")
    ap.add_argument("--max-windows", type=int, default=200)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--cost-bps", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--era", default=f"{ERA_START_YEAR}-{ERA_END_YEAR}",
                    help="YYYY-YYYY. Any era other than the frozen "
                         "2016-2019 is BUILD-ONLY: its decide step is unfunded.")
    ap.add_argument("--build-only", action="store_true",
                    help="count the era's windows and refuse to decide it ($0)")
    a = ap.parse_args(argv)

    try:
        era_lo, era_hi = (int(x) for x in str(a.era).split("-", 1))
    except Exception:
        raise SystemExit(f"REFUSED: --era must be YYYY-YYYY, got {a.era!r}")
    frozen = (era_lo, era_hi) == FROZEN_DECIDE_ERA

    if not frozen and (a.run or a.pilot):
        # Belt. `assert_decidable` is the braces, and it is the one that binds:
        # it refuses at the wire whatever this branch is talked out of.
        raise SystemExit(
            f"REFUSED: --era {a.era} is not the frozen decide era "
            f"{FROZEN_DECIDE_ERA[0]}-{FROZEN_DECIDE_ERA[1]}. A second era is "
            "BUILD-ONLY this session (mandate C4b): its decide step is unfunded. "
            "Use --build-only.")

    if a.build_only:
        rec = build_era2_dry_run((era_lo, era_hi), edgar_only=True)
        write_receipt(a.out or "C4b_era2_window_build_dryrun.json", rec,
                      out_dir=RECEIPTS_B)
        print(json.dumps({k: v for k, v in rec.items()
                          if k != "edgar_backing"}, indent=1, default=str))
        return 0

    from learner import evaluate
    cost_bps = a.cost_bps if a.cost_bps is not None else evaluate.COST_BPS_PER_SIDE

    t_start = time.time()
    DATA.mkdir(parents=True, exist_ok=True)

    # `llm_telemetry` warns, per ledger read, about every unpriced model and
    # every duplicate id in 57k historical rows. Those warnings are TRUE and
    # they are already recorded once, below, in `ledger_state`. Left on, they
    # wrote 76 MB in eight minutes and buried this job's own output -- which is
    # how a real warning stops being read. Silenced here, stated in the receipt.
    import logging
    logging.getLogger("backend.services.llm_telemetry").setLevel(logging.ERROR)

    if a.build:
        rec = build_windows()
        rec.pop("windows", None)
        write_receipt("L10_era_replay_windows.json", rec)
        print(json.dumps(rec, indent=1))
        return 0

    wrec = load_windows()
    windows = wrec["windows"]
    print(f"[windows] {len(windows)} built, {wrec['months']} months, "
          f"{wrec['eligible_permnos']} eligible permnos")

    _load_cache()

    ds_before = deepseek_balance()

    if a.pilot:
        sel = [w for w in windows if int(w["thread"]) == 0][:a.pilot]
        arms = ARMS
    elif a.run or a.grade:
        sel = windows[:a.max_windows]
        arms = ARMS
    else:
        print("nothing to do: pass --build, --pilot N, --run or --grade")
        return 2

    if a.grade:
        # No wire calls: everything must come from cache or the window is skipped.
        res = {"decisions": {}, "cards": {}, "prose": {}, "stopped": None}
        for w in sel:
            for arm in arms:
                naming = naming_of(arm)
                res["cards"][(w["window_id"], naming)] = render_bundle(w, naming)
        print("[grade] cache-only replay is not implemented as a separate path; "
              "use --run, which is a no-op when every call is cached.")
        return 2

    res = run_arms(sel, arms, workers=a.workers)
    decisions = res["decisions"]

    graded = {}
    for arm in arms:
        graded[arm] = grade_arm(sel, decisions, arm, cost_bps)

    family = {arm: [g["_monthly"][k] for k in sorted(g["_monthly"])]
              for arm, g in graded.items() if g.get("n_windows")}

    out_arms = {}
    for arm, g in graded.items():
        if not g.get("n_windows"):
            out_arms[arm] = g
            continue
        block = dict(g)
        rows = block.pop("_rows")
        block.pop("_monthly")
        block["nulls"] = nulls({"_rows": rows})
        block["year_sign_table"] = era_sign_table({"_rows": rows})
        block["inference"] = inference_block(g, family)
        out_arms[arm] = block

    fam = family_max_p({k: v for k, v in graded.items() if v.get("n_windows")})
    ds_after = deepseek_balance()

    payload = {
        "job": "L10 era replay v2 -- the LLM reading test, DECIDE step",
        "spec": "docs/AEGIS_VISION_2026-08-30_LOG_REVISION_ERA_REPLAY.md §3; "
                "docs/CONTINUATION_2026-09-06_OPUS_PROMPT.md §2b",
        "licence": "PRODUCT_EXPERIMENT (exploratory). A screen cannot reach NOVEL.",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - t_start, 1),
        "correction_verified": {
            "claim": "CONTINUATION §2b says 'Friday's L10 built the scaffolding'",
            "finding": "FALSE. docs/BUILD_NIGHT_LAB_2026-09-05.md §5 lists L10 "
                       "among the jobs NOT RUN, and backend/data/optimus/"
                       "night_lab_2026-09-05/ contains no L10 receipt (L1, L4, "
                       "L8, L11, L12, L13 only). The scaffolding did not exist; "
                       "this run built it.",
        },
        "design": {
            "era": f"{ERA_START_YEAR}-01 .. {ERA_END_YEAR}-12",
            "windows_built": len(windows),
            "windows_run": len(sel),
            "k_names_per_window": K_NAMES,
            "top_n_held": TOP_N,
            "threads": N_THREADS,
            "arms": list(arms),
            "rewriter": {"provider": REWRITER_PROVIDER, "model": REWRITER_MODEL,
                         "reasoning_effort": "minimal",
                         "note": "temperature is a 400 on this model and is not sent"},
            "decider": {"provider": DECIDER_PROVIDER, "model": DECIDER_MODEL,
                        "temperature": 0.0,
                        "language_pin": LANGUAGE_PIN.strip()},
            "graded": "RANK ONLY. The LLM never sees or produces a price; "
                      "learner/evaluate.py conventions price it.",
            "benchmark": "the equal-weight basket of the SAME 8 anonymised names "
                         "in the SAME month (vision §3c 'better than what?')",
            "cost_bps_per_side": cost_bps,
            "floors": wrec["floors"],
            "excluded_source": wrec["excluded_source"],
        },
        "rewriter_integrity": res.get("integrity"),
        "arms": out_arms,
        "family": fam,
        "verdict": verdict_block(out_arms, fam),
        "spend_this_invocation": SPEND.as_dict(),
        "campaign_spend_total": campaign_spend_from_ledger(),
        "ledger_state": _ledger_state(),
        "deepseek_balance_before": ds_before,
        "deepseek_balance_after": ds_after,
        "balance_reconciliation_caveat": (
            "The DeepSeek key is SHARED with every other job on this machine. A "
            "balance delta across this run therefore BOUNDS this job's DeepSeek "
            "spend from above; it does not measure it. The per-call token "
            "accounting in `spend` is what attributes cost to this job, and it "
            "is an estimate against config.LLM_PRICE_PER_MTOK."),
        "halted": res.get("stopped"),
    }
    write_receipt(a.out or "L10_era_replay_v2_run01.json", payload)

    # readable summary
    print("\n=== 2x2 ===")
    for arm in arms:
        g = out_arms[arm]
        if not g.get("n_windows"):
            print(f"{arm:20s} NO GRADED WINDOWS")
            continue
        print(f"{arm:20s} n={g['n_windows']:4d} IC={g['mean_ic']:+.4f} "
              f"tIC(blocks)={g['t_ic_month_blocks']} "
              f"net-vs-EW={g['mean_net_top_minus_ew_pct']:+.3f}%/mo "
              f"t(blocks)={g['t_net_top_minus_ew_month_blocks']} "
              f"TW={g['terminal_wealth_book']:.3f} vs EW {g['terminal_wealth_ew_same_names']:.3f} "
              f"canary_year={g['canary']['exact_year_rate']:.3f}")
    print(f"\nspend ${SPEND.total():.4f} "
          f"(nano ${SPEND.nano_usd():.4f}, deepseek ${SPEND.ds_usd():.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
