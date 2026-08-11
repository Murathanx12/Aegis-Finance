"""CONVICTION-REPLAY-1 — did his selection beat the pool he selected it from?

THE QUESTION, AND WHY IT IS ANSWERABLE AT ALL
=============================================

Murat's record is +73.7% over a year. That number on its own supports no
inference: it is one draw from a high-variance process, over a window, with
unknown weights and unknown cash. What makes his sheets unusual is that they
record **both the picks and the pool the picks came from, priced on the same
day**. That converts the interesting question —

    did his thematic judgment add information beyond the analyst spreadsheet,
    or did the spreadsheet do the work?

— from a story into a measurement, because the counterfactual is written down.

THE INSTRUMENT
--------------
13 picks against 48 non-picks is far too small for a t-test on independent
names, and the names are not independent: his picks cluster in clinical biotech
and quantum/semis, so a single sector move moves most of one side together. A
t-statistic would treat that concentration as 13 independent draws and overstate
its own precision — the exact error CANON §19 exists to stop.

So the test is a **label permutation**. Under the null that his labels carry no
information, any 13 of the 61 names were equally likely to be the picks; the
null distribution is built by reassigning the labels across the ACTUAL return
vectors, which carries the real cross-correlation with it at no assumption cost.

The MDE is **measured, not derived**: for a grid of planted effects, plant the
effect in a random 13 and count how often the test fires. That mirrors what
NIGHT-11 did to the Layer-1 instrument, where an MDE that had been an unchecked
formula turned out to have been fed the wrong standard error for months.

WHAT THIS CANNOT DO
-------------------
It cannot produce his NAV. The sheets carry no share counts, no cash and no
transactions, so every basket here is EQUAL-WEIGHTED and none of these numbers
is his return. It cannot separate skill from one lucky window: n is 13 names
over one nine-month period, and the MDE printed beside every result says what
that design can and cannot see. A null here is the instrument stating its
limits — NOT a finding that he has no skill (CANON §19).

EXPLORE / OBSERVATIONAL. Rules designed after seeing a history can never be
confirmation of it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.services.conviction_prices import (load_prices, path_stats,
                                                price_on, synthetic_names,
                                                total_return)
from backend.services.conviction_sheets import Holding, load_sheet

logger = logging.getLogger(__name__)

#: Same convention as the rest of the programme: z(0.975) + z(0.80).
MDE_Z = 2.8
SIG_Z = 1.96
N_PERM = 20_000
N_POWER = 2_000
SEED = 20260811


@dataclass
class GroupReturn:
    """One equal-weighted basket over one window."""
    name: str
    n: int
    mean_return: float
    median_return: float
    members: list[str] = field(default_factory=list)
    per_name: dict = field(default_factory=dict)
    #: names asked for that produced no return. A dropped name is removed from
    #: one side of a comparison and moves the answer invisibly — APLT did
    #: exactly that and cost ten points before anyone noticed.
    excluded: list[str] = field(default_factory=list)


def basket(prices: pd.DataFrame, tickers: list[str], start: str, end: str,
           name: str, *, require_all: bool = False) -> GroupReturn:
    """Equal-weighted mean total return over `tickers`.

    Set `require_all=True` where a dropped name would change the verdict. The
    default is permissive because ranking rules legitimately name securities
    that did not trade for the whole window — but the exclusions are always
    recorded on the result, never merely logged.
    """
    per, dropped = {}, []
    for t in tickers:
        r = total_return(prices, t, start, end)
        if r is not None:
            per[t] = r
        else:
            dropped.append(t)
            logger.warning("%s: %s has no return over %s..%s and is EXCLUDED",
                           name, t, start, end)
    if dropped and require_all:
        raise ValueError(
            f"{name}: {dropped} produced no return. This basket decides a "
            f"verdict, so a silently missing name is not acceptable — resolve "
            f"the price or record a corporate action for it")
    vals = np.array(list(per.values()), dtype=float)
    return GroupReturn(name=name, n=len(vals),
                       mean_return=float(vals.mean()) if len(vals) else float("nan"),
                       median_return=float(np.median(vals)) if len(vals) else float("nan"),
                       members=sorted(per), per_name=per, excluded=dropped)


def permutation_test(pick_returns: np.ndarray, pool_returns: np.ndarray, *,
                     n_perm: int = N_PERM, seed: int = SEED) -> dict:
    """Mean(picks) - mean(non-picks), against a label-permutation null.

    The null reassigns the pick label across the observed return vectors, so the
    cross-correlation among the names is carried into the null distribution
    instead of being assumed away.
    """
    rng = np.random.default_rng(seed)
    k = len(pick_returns)
    allr = np.concatenate([pick_returns, pool_returns])
    n = len(allr)
    observed = float(pick_returns.mean() - pool_returns.mean())

    idx = np.argsort(rng.random((n_perm, n)), axis=1)[:, :k]
    tot = allr.sum()
    picked = allr[idx].sum(axis=1)
    null = picked / k - (tot - picked) / (n - k)

    p_two = float((np.abs(null) >= abs(observed) - 1e-15).mean())
    return {
        "observed_difference": observed,
        "p_value_two_sided": p_two,
        "null_mean": float(null.mean()),
        "null_sd": float(null.std(ddof=1)),
        "null_p05": float(np.percentile(null, 5)),
        "null_p95": float(np.percentile(null, 95)),
        "n_picks": k, "n_pool": n - k, "n_permutations": n_perm,
        "significant_at_5pct": bool(p_two < 0.05),
    }


def measure_mde(pool_returns: np.ndarray, k: int, *, grid: np.ndarray | None = None,
                n_power: int = N_POWER, n_perm: int = 2_000,
                target_power: float = 0.80, seed: int = SEED) -> dict:
    """The smallest planted effect this design detects 80% of the time.

    Measured the way NIGHT-11 measured the Layer-1 instrument's: plant an effect
    of known size in a random `k` of the observed names, run the real test, and
    count. An MDE derived from a formula is a promise nothing has checked.
    """
    rng = np.random.default_rng(seed + 1)
    if grid is None:
        grid = np.arange(0.0, 2.01, 0.10)
    n = len(pool_returns)
    rows = []
    for delta in grid:
        fires = 0
        for _ in range(n_power):
            who = rng.choice(n, size=k, replace=False)
            r = pool_returns.copy()
            r[who] += delta
            mask = np.zeros(n, dtype=bool)
            mask[who] = True
            res = permutation_test(r[mask], r[~mask], n_perm=n_perm,
                                   seed=int(rng.integers(1 << 31)))
            fires += res["significant_at_5pct"]
        rows.append({"planted": float(delta), "power": fires / n_power})
        if rows[-1]["power"] >= target_power:
            break
    achieved = [r for r in rows if r["power"] >= target_power]
    return {
        "mde_at_80pct_power": achieved[0]["planted"] if achieved else None,
        "grid": rows,
        "target_power": target_power,
        "note": ("measured by planting effects of known size in a random k of "
                 "the observed names, not derived from a formula"),
        "if_none": ("no effect on the grid reached 80% power: this design "
                    "cannot reliably detect ANY selection edge, and a null is "
                    "a statement about the design (CANON §19)"),
    }


def rank_alternative(holdings: list[Holding], key: str, k: int) -> dict:
    """The top k of the pool by a rule he could have followed instead.

    `sheet_upside` uses the prices and targets AS HE RECORDED THEM, because the
    question is what HIS spreadsheet would have picked, not what a clean feed
    would have. His transcription is part of the strategy being tested.

    TIES ARE NOT A RANKING. Consensus rating is capped at 5.0 and fourteen names
    on this sheet sit at exactly 5.0 with NONE strictly above — so a "top 13 by
    consensus" is thirteen names drawn arbitrarily from a fourteen-way tie, and
    whatever order the sort happened to produce would be reported as if the rule
    had chosen it. NIGHT-10 shipped exactly that defect once already. This
    returns the tie structure so the caller can price the ambiguity instead of
    hiding it behind a sorted list.
    """
    scored = []
    for h in holdings:
        v = h.sheet_upside if key == "sheet_upside" else h.consensus_rating
        if v is not None:
            scored.append((float(v), h.ticker))
    scored.sort(key=lambda vt: (-vt[0], vt[1]))
    if len(scored) <= k:
        return {"strict": [t for _, t in scored], "tied_at_cutoff": [],
                "n_slots_left": 0, "cutoff": None, "is_a_real_ranking": True}
    cutoff = scored[k - 1][0]
    strict = [t for v, t in scored if v > cutoff]
    tied = sorted(t for v, t in scored if v == cutoff)
    return {
        "strict": strict, "tied_at_cutoff": tied, "cutoff": cutoff,
        "n_slots_left": k - len(strict),
        # a rule that fills most of its book from a tie is not ordering anything
        "is_a_real_ranking": len(strict) >= k // 2,
    }


def tie_aware_basket(prices: pd.DataFrame, ranking: dict, start: str, end: str,
                     name: str, *, n_draws: int = 2_000,
                     seed: int = SEED) -> dict:
    """The rule's return, averaged over every way its ties could break.

    When a rule fills slots from a tie, ONE tie-break is one arbitrary draw from
    a distribution the rule never chose between. Reporting it as the rule's
    result attributes a range of outcomes to a decision nothing made. The mean
    over random tie-breaks is the rule's honest expected return, and the spread
    says how much of the headline was the coin rather than the rule.
    """
    strict = basket(prices, ranking["strict"], start, end, f"{name} strict")
    slots, tied = ranking["n_slots_left"], ranking["tied_at_cutoff"]
    if slots <= 0 or not tied:
        return {"mean_return": strict.mean_return, "n": strict.n,
                "tie_break_p05": None, "tie_break_p95": None,
                "members_strict": strict.members, "tied_at_cutoff": [],
                "spread_from_ties": 0.0, "is_a_real_ranking": True}

    tie_b = basket(prices, tied, start, end, f"{name} tied")
    tie_vals = np.array([tie_b.per_name[t] for t in tie_b.members])
    strict_vals = np.array([strict.per_name[t] for t in strict.members])
    rng = np.random.default_rng(seed)
    take = min(slots, len(tie_vals))
    draws = np.array([
        np.concatenate([strict_vals, rng.choice(tie_vals, take, replace=False)]).mean()
        for _ in range(n_draws)])
    return {
        "mean_return": float(draws.mean()), "n": len(strict_vals) + take,
        "tie_break_p05": float(np.percentile(draws, 5)),
        "tie_break_p95": float(np.percentile(draws, 95)),
        "members_strict": strict.members, "tied_at_cutoff": tie_b.members,
        "n_slots_filled_from_the_tie": take,
        "spread_from_ties": float(np.percentile(draws, 95)
                                  - np.percentile(draws, 5)),
        "is_a_real_ranking": ranking["is_a_real_ranking"],
        "whole_tied_group_return": tie_b.mean_return,
    }


def up_down_capture(prices: pd.DataFrame, tickers: list[str], start: str,
                    end: str, benchmark: str = "SPY") -> dict:
    """Capture split by the sign of the benchmark's day.

    His claim about the engine — strong when the market falls, unable to keep up
    when it rises — is a statement about these two numbers, and they are only
    meaningful side by side. A book that captures 40% of the upside and 40% of
    the downside has no timing skill; it has less risk.
    """
    px = prices.loc[pd.Timestamp(start):pd.Timestamp(end)]
    # Reconstructed names have no daily path; their single synthetic jump on the
    # deal date would land in whichever bucket that day fell into.
    synth = synthetic_names()
    have = [t for t in tickers
            if t in px.columns and t not in synth and px[t].notna().sum() > 20]
    rets = px[have].pct_change(fill_method=None)
    book = rets.mean(axis=1).dropna()
    bench = px[benchmark].pct_change(fill_method=None).reindex(book.index).dropna()
    book = book.reindex(bench.index)

    up, dn = bench > 0, bench < 0

    def _cap(m):
        b, k = bench[m], book[m]
        if len(b) < 5 or abs(b.mean()) < 1e-12:
            return None
        return float(k.mean() / b.mean())

    return {
        "benchmark": benchmark, "n_days": int(len(book)),
        "n_up_days": int(up.sum()), "n_down_days": int(dn.sum()),
        "up_capture": _cap(up), "down_capture": _cap(dn),
        "book_total": float((1 + book).prod() - 1),
        "benchmark_total": float((1 + bench).prod() - 1),
        "book_vol_annual": float(book.std(ddof=1) * np.sqrt(252)),
        "benchmark_vol_annual": float(bench.std(ddof=1) * np.sqrt(252)),
        "beta": float(np.cov(book, bench)[0, 1] / np.var(bench, ddof=1)),
        "reading": ("up_capture below 1 with down_capture also below 1 is lower "
                    "risk, not timing skill; the pair must be read together"),
    }


def exit_audit(prices: pd.DataFrame, sheet_date: str, end: str) -> list[dict]:
    """What each sale was worth, against holding it instead.

    His self-diagnosis is that he exits too early. That is measurable per exit
    and it is NOT uniform — TVTX and ALMS point in opposite directions — which
    is why it needs measuring rather than a rule invented from two anecdotes.
    """
    sheet = load_sheet(sheet_date)
    out = []
    for h in sheet.holdings:
        if h.sold_at is None:
            continue
        held_to_end = price_on(prices, h.ticker, end)
        entry = h.price
        row = {
            "ticker": h.ticker, "sheet_entry_price": entry,
            "sold_at": h.sold_at, "price_at_end": held_to_end,
            "realised_return_vs_sheet_price": (
                h.sold_at / entry - 1.0 if entry else None),
            "return_if_held_to_end": (
                held_to_end / entry - 1.0 if entry and held_to_end else None),
            "cost_of_selling_pct_of_entry": (
                (held_to_end - h.sold_at) / entry if entry and held_to_end else None),
        }
        row["verdict"] = (
            "GOOD_EXIT" if row["cost_of_selling_pct_of_entry"] is not None
            and row["cost_of_selling_pct_of_entry"] < 0 else "EARLY_EXIT")
        out.append(row)
    return out
