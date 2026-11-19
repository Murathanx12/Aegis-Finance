"""family_scorecard -- one row per strategy FAMILY, not per book (CH-55, 2026-11-16).

Licence: PRODUCT_EXPERIMENT diagnostics ($0, no LLM, no network, no order, no broker call).

WHY
===
An audit of the paper fleet found 65 books that were about 3.7 effective bets, 62 of
which fell on the same day. "N books ahead of SPY" therefore says little, and "ahead of SPY"
could not be told apart from "holds more market" because the owner-facing block ranked on raw
excess. The evidence labels printed beside the books also fire on about a third of random
books nobody selected (roadmap CH-53, `scripts.paper_tables`).

WHAT IT DOES -- AND WHAT IT REUSES
==================================
Nothing here is a second definition of anything:

* the strategy accounts, the control/twin exclusions, each row's exposure view, flags and
  twin are `results_voice.build`'s;
* a FAMILY is one component of `results_voice.bets_after_same_bet` -- the strategy accounts
  joined by holdings Jaccard (`RESULTS_VOICE_BET_JACCARD`) or by `book_dna`'s SAME_BET
  daily-excess correlation. The number of holdings-distinct bets inside a family is
  `results_voice.cluster_bets`';
* beta, the beta-adjusted excess, their SE / MDE and the CANNOT DETERMINE reasons are
  `book_dna.market_exposure`'s. The beta-adjusted excess printed here is the RESIDUAL
  (`series_beta_adjusted_pp`: r_book - beta x r_SPY compounded session by session), a number
  only when book_dna calls the beta window comparable with the receipt window. `return - beta
  x SPY leg` is kept beside it: it also carries the compounding of beta itself, so a book that
  is exactly 2 x SPY shows a positive figure in a rising window and a residual of 0; the drawdown is
  `book_dna.drawdown_of`'s; the labels are `book_dna.evidence_label`'s, unchanged;
* each label's false-fire rate is the CH-53 measurement (`results_voice.label_false_fire`).

A family's figures are the EQUAL-WEIGHT MEAN OF ITS MEMBERS, each over its own window (the
members are one bet, so this is a description of that bet, not a portfolio that was held).
Every mean prints how many members it is over; the beta-adjusted mean prints the raw excess
of the SAME members beside it. The worst member's drawdown stands for the family.

REFUSALS (`results_voice.ResultsVoiceRefused`; the CLI exits non-zero)
======================================================================
No roi/book_dna pair, no rows, no live strategy account; an ROI receipt whose own
`generated_utc` is older than `FAMILY_SCORECARD_STALE_DAYS` or cannot be dated; a book_dna
receipt that predates the market-exposure block (rebuild it into the out folder).
A scorecard that builds but in which a live book has neither a number nor an explicit
CANNOT DETERMINE with a reason, or a label has no false-fire rate, is written with
`status: FAILED` and its `failures` named; the CLI exits non-zero for it too.

FIX ROUND (review of PR #164)
=============================
* A family count is NOT a count of independent bets: families distinct under the join rule
  still move together. `effective_bets` prints the participation ratio of the family
  correlation matrix (raw and excess returns), the components at a looser join and the share
  of families whose worst day is the same date -- in the top line.
* The newest mark older than `FAMILY_SCORECARD_MARK_STALE_DAYS` refuses, as does a stamp or a
  mark dated in the future; an unparseable receipt is a named refusal, not a traceback.
* The false-fire measurement expires (`LABEL_FALSE_FIRE_MAX_AGE_DAYS`).
* |t| >= `FAMILY_SCORECARD_T_NAMED` families are counted and named beside the count expected
  by chance; the SE treats daily residuals as independent.

CH-65 (2026-11-19)
==================
The header carries `results_voice.coverage_changes`' line (NOT IN THE COUNTS): the accounts and
source families that exist and are in none of the counts -- frozen because their source was
retired, unreadable at the broker, or absent since the previous run's ROI receipt. It is the
results voice's function and sentence, not a second copy; nothing is printed when nothing is missing.

Nothing here is a skill claim. Families are ranked after the fact.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from backend import config as _config
from backend.services import book_dna as _dna
from backend.services import results_voice as RV

SCHEMA = "family_scorecard/1"
CD = _dna.CANNOT_DETERMINE
Refused = RV.ResultsVoiceRefused


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def params() -> dict:
    return {"stale_days": float(_cfg("FAMILY_SCORECARD_STALE_DAYS", 4)),
            "mark_stale_days": float(_cfg("FAMILY_SCORECARD_MARK_STALE_DAYS", 4)),
            "future_tolerance_min": float(_cfg("FAMILY_SCORECARD_FUTURE_TOLERANCE_MIN", 5)),
            "effective_min_dates": int(_cfg("FAMILY_SCORECARD_EFFECTIVE_MIN_DATES", 30)),
            "effective_min_families": int(_cfg("FAMILY_SCORECARD_EFFECTIVE_MIN_FAMILIES", 3)),
            "loose_join_corr": float(_cfg("FAMILY_SCORECARD_LOOSE_JOIN_CORR", 0.50)),
            "t_named": float(_cfg("FAMILY_SCORECARD_T_NAMED", 2.0)),
            "n_ends": int(_cfg("FAMILY_SCORECARD_N_ENDS", 3)),
            "bet_jaccard": RV.params()["bet_jaccard"],
            "same_bet_corr": _dna.params()["flag_same_bet_corr"],
            "min_beta_obs": _dna.params()["min_beta_obs"],
            "random_twin_kinds": RV.params()["random_twin_kinds"]}


def _f(x: Any) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else None


def _mean(xs: list) -> Optional[float]:
    return round(statistics.fmean(xs), 3) if xs else None


# ───────────────────────────────────────────────────────────── input checks

def _parse_utc(s: Any) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def receipt_age(roi: dict, run_id: Optional[str], now: datetime, stale_days: float) -> dict:
    """Age of the ROI receipt by ITS OWN stamp (`generated_utc`, else the run id in its file
    name) -- never the file's mtime, which is checkout time. FRESH / STALE / UNKNOWN; an
    undateable receipt is UNKNOWN, never fresh."""
    stamp = _parse_utc(roi.get("generated_utc")) if isinstance(roi, dict) else None
    src = "roi.generated_utc"
    if stamp is None and run_id and RV.RUN_ID_RE.match(str(run_id)):
        try:
            stamp = datetime.strptime(str(run_id), "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            src = "the run id in the file name"
        except ValueError:
            stamp = None
    if stamp is None:
        return {"status": "UNKNOWN", "generated_utc": None, "age_days": None, "stale_days": stale_days,
                "why": "the ROI receipt has no parseable generated_utc and no run-id stamp"}
    age = (now - stamp).total_seconds() / 86400.0
    if age < -float(_cfg("FAMILY_SCORECARD_FUTURE_TOLERANCE_MIN", 5)) / 1440.0:
        # fix round: a stamp from the future is not "0 days old"
        return {"status": "UNKNOWN", "generated_utc": stamp.isoformat(timespec="seconds"), "age_days": round(age, 2),
                "stale_days": stale_days, "now_utc": now.isoformat(timespec="seconds"),
                "why": f"the ROI receipt is stamped {stamp.isoformat(timespec='seconds')}, which is in the FUTURE "
                       f"of {now.isoformat(timespec='seconds')}"}
    return {"status": "STALE" if age > stale_days else "FRESH", "generated_utc": stamp.isoformat(timespec="seconds"),
            "stamp_source": src, "age_days": round(age, 2), "stale_days": stale_days,
            "now_utc": now.isoformat(timespec="seconds")}


def marks_age(as_of_mark: Any, now: datetime, stale_days: float) -> dict:
    """Age in calendar days of the NEWEST last_mark among the strategy books (fix round: a
    receipt generated today over marks from weeks ago passed as fresh). FRESH / STALE /
    UNKNOWN; a mark that cannot be read as a date, or lies after `now`, is UNKNOWN."""
    try:
        m = date.fromisoformat(str(as_of_mark)[:10])
    except (TypeError, ValueError):
        return {"status": "UNKNOWN", "as_of_mark": as_of_mark, "age_days": None, "stale_days": stale_days,
                "why": f"the newest mark {as_of_mark!r} is not a date"}
    age = (now.astimezone(timezone.utc).date() - m).days
    if age < 0:
        return {"status": "UNKNOWN", "as_of_mark": m.isoformat(), "age_days": age, "stale_days": stale_days,
                "why": f"the newest mark {m.isoformat()} is in the FUTURE of {now.date().isoformat()}"}
    return {"status": "STALE" if age > stale_days else "FRESH", "as_of_mark": m.isoformat(), "age_days": age,
            "stale_days": stale_days}


def exposure_audit(roi: dict, dna: dict, dna_name: str) -> dict:
    """EVERY live book of the ROI receipt (twins and controls included): does its book_dna row
    carry beta and the beta-adjusted excess as a number, or as CANNOT DETERMINE with a reason?
    `missing` lists the books with neither -- a scorecard with any is FAILED."""
    books = {str(b.get("account")): b for b in dna.get("books") or []}
    n_num = n_cd = n_no_row = 0
    missing: list[dict] = []
    reasons: dict[str, int] = {}
    live = [r for r in roi.get("rows") or [] if r.get("status") == "LIVE"]
    for r in live:
        a = str(r.get("account"))
        b = books.get(a)
        if b is None:
            n_no_row += 1                      # exposure_view says so with its reason; counted apart
        elif not isinstance(b.get("market_exposure"), dict):
            missing.append({"account": a, "why": "the book_dna row has no market_exposure block"})
            continue
        x = RV.exposure_view(b, dna_name)
        bad = [k for k, w in (("beta", "beta_why"), ("residual_pp", "residual_why"))
               if not isinstance(x.get(k), float) and not (x.get(k) == CD and str(x.get(w) or "").strip())]
        if bad:
            missing.append({"account": a, "why": f"{', '.join(bad)}: neither a number nor CANNOT DETERMINE with a reason"})
        elif isinstance(x.get("beta"), float) and isinstance(x.get("residual_pp"), float):
            n_num += 1
        else:
            n_cd += 1
            why = str(x.get("residual_why") or x.get("beta_why") or "")
            key = why.split(":")[0][:80] if why else "?"
            reasons[key] = reasons.get(key, 0) + 1
    return {"n_live_books": len(live), "n_beta_and_residual": n_num, "n_cannot_determine_with_reason": n_cd,
            "n_without_a_book_dna_row": n_no_row, "n_missing": len(missing), "missing": missing,
            "cannot_determine_reasons": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])))}


# ───────────────────────────────────────────────────────────── families

def families_of(voice: dict) -> list[list[str]]:
    """The components `results_voice.bets_after_same_bet` built (holdings Jaccard joined with
    SAME_BET peers), singletons included, each in the voice's own account order."""
    accounts = [r["account"] for r in voice["beta_adjusted_ranking"]["rows"]]
    order = {a: i for i, a in enumerate(accounts)}
    multi = [list(m) for m in (voice["headline"].get("same_bet_clustering") or {}).get("bets") or []]
    seen = {a for m in multi for a in m}
    fams = multi + [[a] for a in accounts if a not in seen]
    return sorted((sorted(m, key=lambda a: order.get(a, 1 << 30)) for m in fams), key=lambda m: m[0])


def _family_series(members: list[str], books: dict) -> dict:
    """{period-end date: (mean r_book, mean r_book - r_SPY)} over the members that have that date
    (book_dna `period_returns`)."""
    acc: dict = {}
    for a in members:
        for row in (books.get(a) or {}).get("period_returns") or []:
            try:
                d, b, x = str(row[0])[:10], float(row[1]), float(row[2])
            except (TypeError, ValueError, IndexError):
                continue
            acc.setdefault(d, []).append((b, b - x))
    return {d: (statistics.fmean(q[0] for q in v), statistics.fmean(q[1] for q in v)) for d, v in acc.items()}


def _components(corr: np.ndarray, thr: float) -> int:
    n = corr.shape[0]
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if corr[i, j] == corr[i, j] and corr[i, j] >= thr:
                parent[find(i)] = find(j)
    return len({find(i) for i in range(n)})


def effective_bets(fams: list[dict], books: dict, P: Optional[dict] = None) -> dict:
    """How many bets the families really are (fix round, review of PR #164).

    The participation ratio (`book_dna.participation_ratio`: N for N uncorrelated series, 1
    for N copies) of the correlation matrix of the families' period returns, on RAW returns and
    on EXCESS returns (r - r_SPY), over the families that share at least `effective_min_dates`
    period-end dates: the `effective_min_dates` most widely shared dates are taken (ties: the
    later date) and every family that has all of them is used, on the dates they all share;
    a family whose series never moves on those dates is dropped (no correlation). Beside it:
    the median pairwise correlation, the number of components when families are joined at
    `loose_join_corr` (excess, the join rule's own quantity; raw beside it), and the share of
    families whose worst raw day is the same date. CANNOT DETERMINE with the reason when fewer
    than `effective_min_families` families remain. Periods are matched on their end date."""
    P = P or params()
    md, mf, thr = int(P["effective_min_dates"]), int(P["effective_min_families"]), float(P["loose_join_corr"])
    base = {"method": ("participation ratio (sum of eigenvalues)^2 / sum of squared eigenvalues of the family "
                       "correlation matrix; a family's return on a date is the equal-weight mean of its members; "
                       "periods matched on their end date"),
            "min_common_dates": md, "min_families": mf, "loose_join_corr": thr, "n_families_total": len(fams)}

    def cd(why: str, **extra: Any) -> dict:
        return {**base, "status": CD, "why": why, "raw": CD, "excess": CD, **extra}

    if not any(isinstance((books.get(a) or {}).get("period_returns"), list) for f in fams for a in f["members"]):
        return cd("the book_dna receipt carries no period_returns (it predates the CH-55 fix round); rebuild "
                  "book_dna on this ROI receipt")
    ser = {f["family"]: _family_series(f["members"], books) for f in fams}
    cand = sorted((k for k, v in ser.items() if len(v) >= md), key=lambda k: (-len(ser[k]), k))
    short = sorted(k for k in ser if k not in cand)

    def common(keys: list) -> list:
        return sorted(set.intersection(*(set(ser[k]) for k in keys))) if keys else []
    # the `md` most widely shared period-end dates (ties: the later date), then every family
    # that has all of them; the common dates of those families are the sample. Dropping
    # families fewest-dates-first kept 6 of 45 on live data: the many short books went first.
    count = Counter(d for k in cand for d in ser[k])
    ranked = sorted(count, key=lambda d: (count[d], d), reverse=True)[:md]
    core = set(ranked)
    dropped = [k for k in cand if not core <= set(ser[k])] if len(core) >= md else list(cand)
    cand = [k for k in cand if k not in dropped]
    dates = common(cand)
    if len(cand) < mf or len(dates) < md:
        return cd(f"{len(cand)} families share {len(dates)} period-end dates (needs >= {mf} families on >= {md} "
                  f"dates); {len(short)} families have fewer than {md} dates",
                  n_families=len(cand), n_dates=len(dates))
    raw = np.array([[ser[k][d][0] for k in cand] for d in dates])
    exc = np.array([[ser[k][d][1] for k in cand] for d in dates])
    keep = [i for i in range(len(cand)) if np.ptp(raw[:, i]) > 1e-12 and np.ptp(exc[:, i]) > 1e-12]
    flat = [cand[i] for i in range(len(cand)) if i not in keep]
    used = [cand[i] for i in keep]
    if len(used) < mf:
        return cd(f"{len(used)} families move on the {len(dates)} common dates (needs >= {mf})",
                  n_families=len(used), n_dates=len(dates))
    raw, exc = raw[:, keep], exc[:, keep]
    cr, cx = np.corrcoef(raw, rowvar=False), np.corrcoef(exc, rowvar=False)
    iu = np.triu_indices(len(used), 1)
    worst = Counter(dates[int(np.argmin(raw[:, i]))] for i in range(len(used)))
    wd, wn = sorted(worst.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return {**base, "status": "OK", "why": None,
            "raw": round(_dna.participation_ratio(cr), 2), "excess": round(_dna.participation_ratio(cx), 2),
            "n_families": len(used), "n_dates": len(dates), "from": dates[0], "to": dates[-1],
            "median_pairwise_corr_raw": round(float(np.median(cr[iu])), 3),
            "median_pairwise_corr_excess": round(float(np.median(cx[iu])), 3),
            "components_at_loose_join_excess": _components(cx, thr),
            "components_at_loose_join_raw": _components(cr, thr),
            "worst_day": {"date": wd, "n_families": wn, "share": round(wn / len(used), 3)},
            "families_used": used,
            "families_left_out": {"fewer_than_min_dates": short, "dropped_to_reach_common_dates": sorted(dropped),
                                  "never_moved_on_the_common_dates": flat}}


def _name_of(members: list[str], rows: dict) -> str:
    """Named after the member with the LONGEST window (ties: alphabetical) -- never the best."""
    return sorted(members, key=lambda a: (-(rows[a].get("sessions_graded") or 0), a))[0]


def _drawdown(book: Optional[dict], dna_name: str) -> dict:
    d = (book or {}).get("max_drawdown")
    if not isinstance(d, dict):
        why = ("no book_dna row for this account" if not book else
               f"{dna_name} predates the max_drawdown field (CH-55, 2026-11-16); rebuild book_dna on this ROI receipt")
        return {"value": CD, "why": why}
    v = _f(d.get("value"))
    if v is None:
        return {"value": CD, "why": str(d.get("why") or "not computed by book_dna")}
    return {"value": v, "peak": d.get("peak"), "trough": d.get("trough"), "n_periods": d.get("n_periods")}


def family_row(members: list[str], rows: dict, books: dict, ff: dict, voice: dict, dna_name: str) -> dict:
    P = RV.params()
    name = _name_of(members, rows)
    mrows = []
    for a in members:
        r, b = rows[a], books.get(a)
        x = r["market_exposure"]
        tw = RV.twin_of([a], books, b or {}, P["random_twin_kinds"], a)
        gap = _f((tw or {}).get("gap_pp"))
        if gap is None:
            gap = _f(((b or {}).get("fair_twin") or {}).get("excess_over_twin_pp"))
            gsrc = "book_dna fair_twin.excess_over_twin_pp" if gap is not None else None
        else:
            gsrc = f"return minus the return of {tw['account']} ({tw['kind']})"
        mrows.append({
            "account": a, "source_family": r.get("family"), "sessions": r.get("sessions_graded"),
            "inception": r.get("inception"), "last_mark": r.get("last_mark"),
            "return_pct": r.get("roi_pct"), "spy_same_window_pct": r.get("spy_same_window_pct"),
            "raw_excess_pp": r.get("vs_spy_pp"),
            "beta": x.get("beta"), "beta_se": x.get("beta_se"), "beta_why": x.get("beta_why"),
            "beta_n_obs": x.get("n_obs"), "beta_window": x.get("window_label"),
            "beta_adjusted_excess_pp": x.get("residual_pp"),
            "beta_adjusted_excess_se_pp": x.get("residual_se_pp"),
            "beta_adjusted_excess_mde_pp": x.get("residual_mde_pp"),
            "beta_adjusted_excess_why": x.get("residual_why"),
            "residual_over_the_beta_window_pp": x.get("residual_window_pp"),
            "coverage_by_periods": x.get("coverage"), "coverage_note": x.get("coverage_note"),
            "return_minus_beta_x_spy_leg_pp": x.get("beta_adjusted_excess_pp"),
            "max_drawdown_pct": _drawdown(b, dna_name),
            "twin_gap_pp": gap, "twin_gap_source": gsrc,
            "label": r.get("evidence_label"), "label_false_fire": RV.label_rate(r.get("evidence_label"), ff),
            "label_tag": RV.label_tag(r.get("evidence_label"), ff),
            "flags_set": list((r.get("flags") or {}).get("set") or []),
            "bet_members": list(r.get("bet_members") or [a]),
        })
    n = len(mrows)

    def over(key: str) -> list[float]:
        return [float(m[key]) for m in mrows if _f(m[key]) is not None]

    ret, spy, raw = over("return_pct"), over("spy_same_window_pct"), over("raw_excess_pp")
    det_b = [m for m in mrows if isinstance(m["beta"], float)]
    det_x = [m for m in mrows if isinstance(m["beta_adjusted_excess_pp"], float)]

    def whys(key: str, det: list) -> Optional[str]:
        w = sorted({str(m[key] or "no reason recorded") for m in mrows if m not in det})
        return "; ".join(x[:400] for x in w) or None

    beta = ({"value": _mean([m["beta"] for m in det_b]), "n_members_determined": len(det_b), "n_members": n,
             "range": [min(m["beta"] for m in det_b), max(m["beta"] for m in det_b)],
             "why_others": whys("beta_why", det_b)} if det_b else
            {"value": CD, "why": whys("beta_why", det_b), "n_members_determined": 0, "n_members": n})
    if det_x:
        ses = [m["beta_adjusted_excess_se_pp"] for m in det_x if _f(m["beta_adjusted_excess_se_pp"]) is not None]
        mdes = [m["beta_adjusted_excess_mde_pp"] for m in det_x if _f(m["beta_adjusted_excess_mde_pp"]) is not None]
        bax = {"value": _mean([m["beta_adjusted_excess_pp"] for m in det_x]),
               "n_members_determined": len(det_x), "n_members": n,
               "raw_excess_pp_of_the_same_members": _mean([float(m["raw_excess_pp"]) for m in det_x
                                                           if _f(m["raw_excess_pp"]) is not None]),
               "range": [min(m["beta_adjusted_excess_pp"] for m in det_x),
                         max(m["beta_adjusted_excess_pp"] for m in det_x)],
               "return_minus_beta_x_spy_leg_pp": _mean([m["return_minus_beta_x_spy_leg_pp"] for m in det_x
                                                        if isinstance(m["return_minus_beta_x_spy_leg_pp"], float)]),
               "se_pp_member_median": round(statistics.median(ses), 3) if ses else None,
               "mde_pp_member_median": round(statistics.median(mdes), 3) if mdes else None,
               "se_note": ("one member's SE (the median across members): the members are one bet, so "
                           "averaging them does not shrink it. The SE treats the daily residuals as "
                           "independent; autocorrelation would widen it"),
               "min_member_coverage_by_periods": min((m["coverage_by_periods"] for m in det_x
                                                      if m["coverage_by_periods"] is not None), default=None),
               "coverage_notes": sorted({str(m["coverage_note"]) for m in det_x if m["coverage_note"]}),
               "why_others": whys("beta_adjusted_excess_why", det_x)}
    else:
        bax = {"value": CD, "why": whys("beta_adjusted_excess_why", det_x), "n_members_determined": 0, "n_members": n}
    dds = [(m["max_drawdown_pct"]["value"], m["account"]) for m in mrows if _f(m["max_drawdown_pct"]["value"]) is not None]
    if dds:
        worst = min(dds)
        dd = {"value": worst[0], "member": worst[1], "n_members_determined": len(dds), "n_members": n,
              "basis": "the worst member's largest peak-to-trough fall over its own series"}
    else:
        dd = {"value": CD, "n_members_determined": 0, "n_members": n,
              "why": "; ".join(sorted({str(m["max_drawdown_pct"].get("why"))[:300] for m in mrows}))}
    gaps = [m["twin_gap_pp"] for m in mrows if m["twin_gap_pp"] is not None]
    twin = ({"value": _mean(gaps), "n_members_with_a_twin": len(gaps), "n_members": n,
             "basis": "member return minus its random twin's return, mean over the members that have one"}
            if gaps else {"value": None, "n_members_with_a_twin": 0, "n_members": n, "why": "no random twin seeded"})
    lab: dict[str, dict] = {}
    for m in mrows:
        rung = m["label_false_fire"]["rung"]
        e = lab.setdefault(rung, {"label": rung, "n": 0, "false_fire": m["label_false_fire"],
                                  "text": f"{rung} [{m['label_false_fire']['tag']}]"})
        e["n"] += 1
    ladder = list(_dna.LABEL_LADDER)
    labels = sorted(lab.values(), key=lambda e: (-(ladder.index(e["label"]) if e["label"] in ladder else -1), e["label"]))
    sess = [int(m["sessions"]) for m in mrows if isinstance(m["sessions"], int)]
    flags: dict[str, int] = {}
    for m in mrows:
        for f in m["flags_set"]:
            k = str(f).split(" ")[0].split("(")[0]
            k = k if k.isupper() else str(f)[:48]          # a flag that is a sentence keeps its words
            flags[k] = flags.get(k, 0) + 1
    marks = sorted({str(m["last_mark"]) for m in mrows if m["last_mark"]})
    incs = sorted({str(m["inception"]) for m in mrows if m["inception"]})
    mech, msrc = RV.mechanism(name, books.get(name), rows[name].get("family"))
    sbs = [((((books.get(a) or {}).get("flags") or {}).get("SAME_BET")) or {}).get("status") for a in members]
    untested = sum(1 for x in sbs if x != "OK")
    return {
        "family": name, "n_members": n, "members": members,
        "n_distinct_bets_by_holdings": len({tuple(m["bet_members"]) for m in mrows}),
        "source_families": sorted({str(m["source_family"]) for m in mrows}),
        "mechanism": mech, "mechanism_source": msrc,
        "return_pct": _mean(ret), "spy_same_window_pct": _mean(spy), "raw_excess_pp": _mean(raw),
        "raw_excess_range_pp": [min(raw), max(raw)] if raw else None,
        "beta": beta, "beta_adjusted_excess_pp": bax, "max_drawdown_pct": dd, "twin_gap_pp": twin,
        "labels": labels,
        "sessions": ({"min": min(sess), "max": max(sess), "median": statistics.median(sess)} if sess else
                     {"min": None, "max": None, "median": None}),
        "window": {"first_inception": incs[0] if incs else None, "last_mark": marks[-1] if marks else None},
        "flags_set": dict(sorted(flags.items())),
        # a member whose daily excess could not be compared with the others (too few common
        # sessions) is its own family by DEFAULT, not because it was found to be different
        "compared_with_the_others": untested == 0,
        "n_members_same_bet_not_comparable": untested,
        "ahead_raw": bool(raw and statistics.fmean(raw) > 0),
        "ahead_beta_adjusted": (bool(bax["value"] > 0) if isinstance(bax["value"], float) else None),
        "member_rows": mrows,
    }


# ───────────────────────────────────────────────────────────── build

def build(roi: Optional[dict], dna: Optional[dict], *, roi_path: str, dna_path: str, now: datetime,
          run_id: Optional[str] = None, false_fire: Optional[dict] = None, voice: Optional[dict] = None) -> dict:
    """The scorecard dict. REFUSES (ResultsVoiceRefused) on empty, stale or undateable input and
    on a book_dna receipt without the market-exposure block; otherwise returns it with
    `status` OK or FAILED (`failures` named)."""
    P = params()
    if not isinstance(roi, dict) or not roi.get("rows"):
        raise Refused("EMPTY_INPUT: the ROI receipt is missing or has no rows")
    if not isinstance(dna, dict) or not isinstance(dna.get("books"), list) or not dna["books"]:
        raise Refused("EMPTY_INPUT: the book_dna receipt is missing or has no books")
    age = receipt_age(roi, run_id, now, P["stale_days"])
    if age["status"] == "UNKNOWN":
        raise Refused(f"UNDATED_INPUT: {age['why']}; an undateable receipt is never treated as fresh")
    if age["status"] == "STALE":
        raise Refused(f"STALE_INPUT: the ROI receipt is {age['age_days']:.1f} days old (generated "
                      f"{age['generated_utc']}, limit {P['stale_days']:g} days); run the paper-accounts pass first")
    dna_name = Path(str(dna_path)).name
    if not any(isinstance(b.get("market_exposure"), dict) for b in dna["books"]):
        raise Refused(f"NO_EXPOSURE_BLOCK: {dna_name} predates the market_exposure block (no book carries one); "
                      "rebuild book_dna on this ROI receipt (--rebuild-dna, into the out folder)")
    v = voice if voice is not None else RV.build(roi, dna, roi_path=roi_path, dna_path=dna_path,
                                                 false_fire=false_fire, now=now)
    mk = marks_age(v["headline"].get("as_of_mark"), now, P["mark_stale_days"])
    if mk["status"] == "UNKNOWN":
        raise Refused(f"UNDATED_INPUT: {mk['why']}; never treated as fresh")
    if mk["status"] == "STALE":
        raise Refused(f"STALE_MARKS: the newest mark among the strategy books is {mk['as_of_mark']}, "
                      f"{mk['age_days']} days before {now.date().isoformat()} (limit {P['mark_stale_days']:g} days); "
                      f"the receipt was generated {age['generated_utc']} over old marks")
    ff = v["label_false_fire"]
    rows = {r["account"]: r for r in v["beta_adjusted_ranking"]["rows"]}
    books = {str(b.get("account")): b for b in dna["books"]}
    fams = [family_row(m, rows, books, ff, v, dna_name) for m in families_of(v)]
    fams.sort(key=lambda f: (-(f["raw_excess_pp"] if f["raw_excess_pp"] is not None else -1e9), f["family"]))
    for i, f in enumerate(fams, 1):
        f["rank_raw_excess"] = i
    det = sorted((f for f in fams if isinstance(f["beta_adjusted_excess_pp"]["value"], float)),
                 key=lambda f: (-f["beta_adjusted_excess_pp"]["value"], f["family"]))
    for i, f in enumerate(det, 1):
        f["rank_beta_adjusted"] = i
    audit = exposure_audit(roi, dna, dna_name)
    failures: list[str] = []
    if audit["n_missing"]:
        failures.append(f"{audit['n_missing']} live book(s) carry neither beta and residual nor an explicit "
                        f"CANNOT DETERMINE with a reason: "
                        + ", ".join(m["account"] for m in audit["missing"][:10]))
    ladder = set(_dna.LABEL_LADDER)
    bare = sorted({f"{f['family']}: {e['label']}" for f in fams for e in f["labels"]
                   if e["label"] in ladder and e["false_fire"]["rate"] == CD})
    if bare:
        failures.append(f"{len(bare)} label(s) have no false-fire rate ({ff.get('why') or 'see the rows'}): "
                        + "; ".join(bare[:10]))
    n = len(fams)
    n_raw = sum(1 for f in fams if f["ahead_raw"])
    n_bax = sum(1 for f in det if f["ahead_beta_adjusted"])

    def beyond(f: dict, sign: int) -> bool:
        x = f["beta_adjusted_excess_pp"]
        mde = x.get("mde_pp_member_median")
        return mde is not None and sign * x["value"] > mde
    n_up, n_dn = sum(1 for f in det if beyond(f, 1)), sum(1 for f in det if beyond(f, -1))
    betas = sorted(f["beta"]["value"] for f in fams if isinstance(f["beta"]["value"], float))
    hb = float(_dna.params()["flag_high_beta"])
    n_untested = sum(1 for f in fams if not f["compared_with_the_others"])
    eb = effective_bets(fams, books, P)
    tn = float(P["t_named"])
    with_t = []
    for f in det:
        x = f["beta_adjusted_excess_pp"]
        se = x.get("se_pp_member_median")
        x["t"] = round(x["value"] / se, 2) if se else None
        if x["t"] is not None:
            with_t.append(f)
    t_up = [f for f in with_t if f["beta_adjusted_excess_pp"]["t"] >= tn]
    t_dn = [f for f in with_t if f["beta_adjusted_excess_pp"]["t"] <= -tn]
    p_two = math.erfc(tn / math.sqrt(2.0))                      # P(|z| >= tn)
    exp_each = 0.5 * p_two * len(with_t)
    sbc = v["headline"].get("same_bet_clustering") or {}
    h = v["headline"]
    summ = dna.get("summary") or {}
    rule = (f"holdings-Jaccard >= {P['bet_jaccard']:g} / excess-correlation >= {P['same_bet_corr']:g}")
    if eb["status"] == "OK":
        wdy = eb["worst_day"]
        ebs = (f"effective number of bets (participation ratio, {eb['n_families']} families on {eb['n_dates']} common "
               f"dates): {eb['raw']:.1f} on raw returns, {eb['excess']:.1f} on excess returns; "
               f"{eb['components_at_loose_join_excess']} components at a {eb['loose_join_corr']:g} join; "
               f"{wdy['n_families']} of those {eb['n_families']} families ({100 * wdy['share']:.0f}%) had their worst "
               f"day on {wdy['date']}")
    else:
        ebs = f"effective number of bets {CD} ({eb['why']})"
    top = (f"FAMILY SCORECARD as of the {h['as_of_mark']} marks (run {run_id or v.get('run_id')}): {n} families "
           f"distinct under the {rule} rule (an upper bound) from {h['n_strategy_accounts']} live strategy books "
           f"({h['n_excluded_controls']} controls/twins excluded); {ebs}; ahead of SPY on raw excess: {n_raw} of {n}; "
           f"ahead on beta-adjusted excess: {n_bax} of {len(det)} determinable ({n - len(det)} {CD}, not counted "
           f"as behind)")

    def named(fs: list) -> str:
        return (" (" + ", ".join(f"{f['family']} t {f['beta_adjusted_excess_pp']['t']:+.2f}" for f in fs) + ")") if fs else ""
    second = (f"Of the {len(det)} determinable ({len(with_t)} with an SE), |t| >= {tn:g}: {len(t_up)} ahead"
              f"{named(t_up)} and {len(t_dn)} behind{named(t_dn)}; about {exp_each:.1f} expected in each direction by "
              f"chance at that count ({2 * exp_each:.1f} in all). Beyond the MDE ({_dna.params()['mde_z']:g} x SE): "
              f"{n_up} ahead, {n_dn} behind. The SE treats daily residuals as independent draws; autocorrelation "
              f"would widen it, and these families are not {len(with_t)} separate tests (see the effective number "
              f"of bets). "
              + (f"Family beta: median {statistics.median(betas):.2f} over {len(betas)} with a beta, "
                 f"{sum(1 for b in betas if b > 1.0)} above 1.0, {sum(1 for b in betas if b > hb)} above {hb:g}. "
                 if betas else "No family has a determinable beta. ")
              + f"{n_untested} of the {n} families could not be compared with the others (too few common sessions) "
                f"and are distinct by default")
    sc = {
        "schema": SCHEMA, "receipt": "family_scorecard", "licence": roi.get("licence") or "PRODUCT_EXPERIMENT",
        "status": "FAILED" if failures else "OK", "failures": failures,
        "run_id": run_id or v.get("run_id"), "receipts": [roi_path, dna_path],
        "input_age": age, "params": P,
        "top_line": top, "second_line": second,
        # CH-65: who is in none of the counts above (results_voice.coverage_changes, reused)
        "coverage_line": (v.get("coverage") or {}).get("line"), "coverage": v.get("coverage"),
        "effective_bets": eb, "marks_age": mk,
        "counts": {"n_families": n, "n_strategy_books": h["n_strategy_accounts"],
                   "n_excluded_controls_twins": h["n_excluded_controls"],
                   "n_ahead_raw_excess": n_raw, "n_beta_adjusted_determinable": len(det),
                   "n_ahead_beta_adjusted": n_bax, "n_beta_adjusted_cannot_determine": n - len(det),
                   "n_families_with_more_than_one_book": sum(1 for f in fams if f["n_members"] > 1),
                   "largest_family_books": max((f["n_members"] for f in fams), default=0),
                   "n_beta_adjusted_ahead_beyond_mde": n_up, "n_beta_adjusted_behind_beyond_mde": n_dn,
                   "n_families_with_a_beta": len(betas),
                   "family_beta_median": round(statistics.median(betas), 3) if betas else None,
                   "n_family_beta_above_1": sum(1 for b in betas if b > 1.0),
                   "n_family_beta_above_high_beta_flag": sum(1 for b in betas if b > hb),
                   "n_families_not_comparable_with_the_others": n_untested,
                   "effective_bets_raw": eb["raw"], "effective_bets_excess": eb["excess"],
                   "effective_bets_n_families": eb.get("n_families"), "effective_bets_n_dates": eb.get("n_dates"),
                   "components_at_loose_join_excess": eb.get("components_at_loose_join_excess"),
                   "worst_day_share": (eb.get("worst_day") or {}).get("share"),
                   "worst_day_date": (eb.get("worst_day") or {}).get("date"),
                   "n_with_t": len(with_t), "n_t_named_ahead": len(t_up), "n_t_named_behind": len(t_dn),
                   "t_named": [{"family": f["family"], "t": f["beta_adjusted_excess_pp"]["t"]} for f in t_up + t_dn],
                   "t_named_expected_by_chance_each_direction": round(exp_each, 2),
                   # the results voice counts a bet ahead when ANY member is ahead; here: the mean
                   "results_voice_n_bets_ahead_any_member": sbc.get("n_bets_ahead"),
                   "book_dna_effective_bets_exante": summ.get("effective_bets_exante")},
        "family_definition": (
            f"one component of results_voice.bets_after_same_bet: strategy accounts joined when their holdings "
            f"Jaccard >= {P['bet_jaccard']:g} (results_voice.cluster_bets) or their daily excess over SPY "
            f"correlates >= {P['same_bet_corr']:g} (book_dna SAME_BET). Books that cannot be compared (too few "
            f"common sessions, no holdings) stay their own family. The count is an UPPER bound: families "
            f"distinct under this rule still move together -- read the effective number of bets"),
        "aggregation": ("each family figure is the equal-weight mean of its members, each over its own window; "
                        "the drawdown is the worst member's; the beta-adjusted mean prints the raw excess of the "
                        "same members beside it"),
        "beta_adjusted_definition": (
            "the residual: r_book - beta x r_SPY compounded session by session over the beta window "
            "(book_dna series_beta_adjusted_pp), a number only when that window covers the receipt window "
            "(book_dna's comparability rule). `return_minus_beta_x_spy_leg_pp` (what the results voice ranks) "
            "is kept beside it; it also carries the compounding of beta, which is not selection: a book that "
            "is exactly 2 x SPY has residual 0 and a positive return - beta x SPY leg in a rising window"),
        "label_false_fire": ff,
        "exposure_audit": audit,
        "families": fams,
        "results_voice_headline_lines": v.get("headline_lines"),
        "read_me_first": ("Families are ranked after the fact, each over its own short window; beta is in-sample "
                          "(rf = 0). A positive beta-adjusted excess says the return was not only SPY exposure -- "
                          "not that it is skill. Every label fires on random books at the rate printed beside it. "
                          "Nothing here is a claim."),
    }
    return sc


# ───────────────────────────────────────────────────────────── render

def _num(v: Any, unit: str = "", signed: bool = True) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (RV._signed(float(v)) if signed else f"{float(v):.2f}") + unit
    return CD if v == CD else "n/a"


def _of(d: dict) -> str:
    k, n = d.get("n_members_determined"), d.get("n_members")
    return f" ({k} of {n})" if isinstance(d.get("value"), float) and k is not None and n and k < n else ""


def _cov(x: dict) -> str:
    """' (coverage 76% by periods)' when a member was accepted below the period-coverage rule."""
    c = x.get("min_member_coverage_by_periods")
    return f" (coverage {100 * c:.0f}% by periods)" if x.get("coverage_notes") and c is not None else ""


def _t(x: dict) -> str:
    return f" (t {x['t']:+.2f})" if isinstance(x.get("t"), float) else ""


def family_line(f: dict) -> str:
    """One family in one line: the figures the brief names, CANNOT DETERMINE spelled out."""
    b, x, dd, tw = f["beta"], f["beta_adjusted_excess_pp"], f["max_drawdown_pct"], f["twin_gap_pp"]
    s = f["sessions"]
    sess = f"{s['min']}" if s["min"] == s["max"] else f"{s['min']}-{s['max']}"
    return (f"{f['family']} ({f['n_members']} book(s), {f['n_distinct_bets_by_holdings']} by holdings): return "
            f"{_num(f['return_pct'], '%')} vs SPY {_num(f['spy_same_window_pct'], '%')} = {_num(f['raw_excess_pp'], ' pp')} "
            f"raw; beta {_num(b['value'], signed=False)}{_of(b)}; beta-adjusted {_num(x['value'], ' pp')}{_of(x)}"
            f"{_cov(x)}{_t(x)}; "
            f"max drawdown {_num(dd['value'], '%')}; twin gap "
            f"{_num(tw['value'], ' pp') if tw['value'] is not None else 'none seeded'}; "
            f"{sess} sessions; {', '.join(e['text'] + (' x' + str(e['n']) if f['n_members'] > 1 else '') for e in f['labels'])}")


def ends(sc: dict) -> tuple[list[dict], list[dict]]:
    """(leading, worst) by raw excess, `n_ends` each, never the same family at both ends: with
    fewer than 2 x n_ends families each end gets half (the leading end takes the odd one)."""
    fams = sc["families"]
    k = min(int(sc["params"]["n_ends"]), (len(fams) + 1) // 2)
    w = min(int(sc["params"]["n_ends"]), len(fams) - k)
    return fams[:k], list(reversed(fams[len(fams) - w:])) if w else []


def render_md(sc: dict) -> str:
    rc = ", ".join(f"`{p}`" for p in sc["receipts"])
    c, P = sc["counts"], sc["params"]
    out = [f"# FAMILY SCORECARD {sc['run_id']}", "",
           f"Licence {sc['licence']}; paper books. Receipts: {rc}. Input age {sc['input_age']['age_days']} days "
           f"(limit {P['stale_days']:g}). Status **{sc['status']}**.", ""]
    if sc["failures"]:
        out += [f"FAILED: {x}" for x in sc["failures"]] + [""]
    out += [sc["top_line"] + ".", ""]
    if sc.get("coverage_line"):
        out += [sc["coverage_line"] + ".", ""]
    out += [sc["second_line"] + ".", "",
            f"Families holding more than one book: {c['n_families_with_more_than_one_book']}; the largest holds "
            f"{c['largest_family_books']}. {sc['label_false_fire'].get('line')}.", "",
            f"- A family: {sc['family_definition']}.",
            f"- Figures: {sc['aggregation']}.",
            f"- Beta-adjusted excess: {sc['beta_adjusted_definition']}.",
            f"- {sc['read_me_first']}", ""]
    eb = sc["effective_bets"]
    out += ["## How many bets these families are", ""]
    if eb["status"] == "OK":
        lo = eb["families_left_out"]
        out += [f"- Effective number of bets (participation ratio): **{eb['raw']:.2f} on raw returns, "
                f"{eb['excess']:.2f} on excess returns**, over {eb['n_families']} of the {eb['n_families_total']} "
                f"families on {eb['n_dates']} common period-end dates ({eb['from']}..{eb['to']}).",
                f"- Median pairwise correlation: {eb['median_pairwise_corr_raw']:+.2f} raw, "
                f"{eb['median_pairwise_corr_excess']:+.2f} excess.",
                f"- Components when families are joined at a correlation of {eb['loose_join_corr']:g}: "
                f"{eb['components_at_loose_join_excess']} on excess returns, {eb['components_at_loose_join_raw']} on "
                f"raw returns (the scorecard's rule joins at {sc['params']['same_bet_corr']:g}).",
                f"- Worst day: {eb['worst_day']['n_families']} of {eb['n_families']} families "
                f"({100 * eb['worst_day']['share']:.0f}%) had their worst raw return on {eb['worst_day']['date']}.",
                f"- Left out: {len(lo['fewer_than_min_dates'])} with fewer than {eb['min_common_dates']} dates, "
                f"{len(lo['dropped_to_reach_common_dates'])} dropped to reach the common dates, "
                f"{len(lo['never_moved_on_the_common_dates'])} that never moved on them.",
                f"- Method: {eb['method']}.", ""]
    else:
        out += [f"- Effective number of bets: {CD} ({eb['why']}).", ""]
    fams = sc["families"]
    lead, worst = ends(sc)
    out += [f"## Leading {len(lead)} and worst {len(worst)} by raw excess (chosen after the fact)", ""]
    out += [f"- LEADING {i}: {family_line(f)}" for i, f in enumerate(lead, 1)]
    out += [f"- WORST {i}: {family_line(f)}" for i, f in enumerate(worst, 1)]
    out += ["", f"## Every family — receipts: {rc}", "",
            "| # | family | books | bets by holdings | return | SPY same window | raw excess | beta | "
            "beta-adjusted excess (± member SE) | # by beta-adj | max drawdown | twin gap | sessions | "
            "labels [false-fire] | flags (members) |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for f in fams:
        b, x, dd, tw, s = f["beta"], f["beta_adjusted_excess_pp"], f["max_drawdown_pct"], f["twin_gap_pp"], f["sessions"]
        se = x.get("se_pp_member_median")
        sess = f"{s['min']}" if s["min"] == s["max"] else f"{s['min']}-{s['max']}"
        labels = "; ".join(f"{e['text']} x{e['n']}" for e in f["labels"])
        out.append(
            f"| {f['rank_raw_excess']} | {f['family']} | {f['n_members']} | {f['n_distinct_bets_by_holdings']} | "
            f"{_num(f['return_pct'], '%')} | {_num(f['spy_same_window_pct'], '%')} | {_num(f['raw_excess_pp'], ' pp')} | "
            f"{_num(b['value'], signed=False)}{_of(b)} | {_num(x['value'], ' pp')}"
            f"{(' ±' + format(se, '.2f')) if se is not None else ''}{_of(x)}{_cov(x)}{_t(x)} | "
            f"{f.get('rank_beta_adjusted', '—')} | "
            f"{_num(dd['value'], '%')} | {_num(tw['value'], ' pp') if tw['value'] is not None else 'none seeded'} | "
            f"{sess} | {labels} | "
            f"{', '.join(f'{k} x{n_}' for k, n_ in f['flags_set'].items()) or 'none'}"
            f"{'' if f['compared_with_the_others'] else '; not comparable with the others'} |")
    cds = []
    for f in fams:
        for key, label in (("beta", "beta"), ("beta_adjusted_excess_pp", "beta-adjusted excess"),
                           ("max_drawdown_pct", "max drawdown")):
            d = f[key]
            if d["value"] == CD:
                cds.append(f"- {f['family']} — {label} {CD}: {str(d.get('why') or 'no reason recorded')[:600]}")
            elif d.get("why_others"):
                cds.append(f"- {f['family']} — {label} over {d['n_members_determined']} of {d['n_members']} members; "
                           f"the others {CD}: {str(d['why_others'])[:600]}")
    if cds:
        out += ["", "## CANNOT DETERMINE, with the reason", ""] + cds
    multi = [f for f in fams if f["n_members"] > 1]
    if multi:
        out += ["", "## Families with more than one book", ""]
        out += [f"- **{f['family']}** ({f['n_members']}; sources {', '.join(f['source_families'])}): "
                + ", ".join(m for m in f["members"] if m != f["family"]) for f in multi]
    a = sc["exposure_audit"]
    out += ["", "## Exposure audit: every live book (twins and controls included)", "",
            f"- {a['n_live_books']} live books: {a['n_beta_and_residual']} with beta and residual, "
            f"{a['n_cannot_determine_with_reason']} {CD} with a reason, {a['n_missing']} with neither "
            f"({a['n_without_a_book_dna_row']} have no book_dna row and say so).",
            f"- reasons: {a['cannot_determine_reasons'] or 'none'}", ""]
    return "\n".join(out)


def write(sc: dict, out_dir: Path, run_id: str) -> tuple[Path, Path]:
    """temp -> verify -> replace, named by the INPUT run id (a rerun over the same pair writes
    the same bytes)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / f"family_scorecard_{run_id}.json", out_dir / f"family_scorecard_{run_id}.md"
    for p, text in ((jp, json.dumps(sc, indent=1, sort_keys=False, default=str)), (mp, render_md(sc))):
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        if tmp.read_text(encoding="utf-8") != text:
            tmp.unlink(missing_ok=True)
            raise Refused(f"write verification failed for {p.name}")
        tmp.replace(p)
    return jp, mp


def _load(p: Path) -> dict:
    """A receipt as a dict, or a named refusal: a truncated or unparseable file is not a traceback."""
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"UNREADABLE_INPUT: {Path(p).name} cannot be read as JSON ({type(e).__name__}: "
                      f"{str(e)[:120]}); a truncated receipt is not an empty one") from e
    if not isinstance(d, dict):
        raise Refused(f"UNREADABLE_INPUT: {Path(p).name} is JSON but not a receipt object ({type(d).__name__})")
    return d


def run(folder: Path, out_dir: Path, *, run_id: Optional[str] = None, now: Optional[datetime] = None,
        rebuild_dna: bool = False, false_fire: Optional[dict] = None, bars: Any = None) -> dict:
    """Read the newest shared roi/book_dna pair in `folder` (or `run_id`), build, and write the
    scorecard AND the regenerated results voice into `out_dir` -- never into `folder`.
    `rebuild_dna`: re-run book_dna on the ROI receipt with the current code into `out_dir`
    (lanes not fetched, the paper-books database opened read-only), for a receipt written
    before the exposure block existed."""
    folder, out_dir = Path(folder), Path(out_dir)
    now = now or datetime.now(timezone.utc)
    if not folder.is_dir():
        raise Refused(f"EMPTY_INPUT: {folder} is not a folder")
    if out_dir.resolve() == folder.resolve() or out_dir.resolve().is_relative_to(folder.resolve()):
        raise Refused("OUT_INSIDE_INPUT: the out folder must not be the receipts folder or inside it")
    if rebuild_dna:
        rid = run_id or max(RV.run_ids(folder, "roi") or {""})
        rp = folder / f"roi_{rid}.json"
        if not RV.RUN_ID_RE.match(str(rid)) or not rp.is_file():
            raise Refused(f"EMPTY_INPUT: no roi_<run>.json for run id {rid!r} in {folder.name}")
        roi = _load(rp)
        # dated BEFORE the rebuild: a stale receipt is refused without reading the panel
        age = receipt_age(roi, rid, now, params()["stale_days"])
        if age["status"] != "FRESH":
            raise Refused(f"{'STALE' if age['status'] == 'STALE' else 'UNDATED'}_INPUT: the ROI receipt {rp.name} is "
                          f"{age.get('age_days')} days old (limit {params()['stale_days']:g}) or cannot be dated")
        if not roi.get("rows"):
            raise Refused("EMPTY_INPUT: the ROI receipt has no rows")
        marks = sorted(str(r.get("last_mark"))[:10] for r in roi["rows"]
                       if isinstance(r, dict) and r.get("status") == "LIVE" and r.get("last_mark"))
        mk = marks_age(marks[-1] if marks else None, now, params()["mark_stale_days"])
        if mk["status"] != "FRESH":            # before the rebuild writes anything
            raise Refused(f"STALE_MARKS: the newest mark in {rp.name} is {mk.get('as_of_mark')}, {mk.get('age_days')} "
                          f"days old (limit {mk['stale_days']:g})" if mk["status"] == "STALE"
                          else f"UNDATED_INPUT: {mk['why']}")
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            dna, dp = _dna.run(roi, out_dir=out_dir, run_id=rid, fetch_lanes=False, read_only_db=True, bars=bars)
        except Exception as exc:                                   # noqa: BLE001 -- refused with its reason
            raise Refused(f"REBUILD_FAILED: book_dna rebuild failed: {type(exc).__name__}: {str(exc)[:240]}") from exc
    else:
        try:
            rid = run_id or RV.newest_shared_run_id(folder)
        except Refused as exc:
            raise Refused(f"EMPTY_INPUT: {exc}") from exc
        rp, dp = folder / f"roi_{rid}.json", folder / f"book_dna_{rid}.json"
        if not RV.RUN_ID_RE.match(str(rid)) or not rp.is_file() or not dp.is_file():
            raise Refused(f"EMPTY_INPUT: run id {rid!r} has no roi/book_dna pair in {folder.name}")
        roi, dna = _load(rp), _load(dp)
    roi_path, dna_path = RV.rel(rp), RV.rel(dp)
    sizes = {rp.name: rp.stat().st_size, dp.name: dp.stat().st_size}
    # the scorecard's own checks run first: a stale or empty input writes nothing at all
    v = None
    if isinstance(roi, dict) and roi.get("rows") and isinstance(dna, dict) and dna.get("books"):
        age = receipt_age(roi, rid, now, params()["stale_days"])
        if age["status"] == "FRESH" and any(isinstance(b.get("market_exposure"), dict) for b in dna["books"]):
            v = RV.build(roi, dna, roi_path=roi_path, dna_path=dna_path, prev=RV.previous_dna(folder, rid),
                         history=RV.label_history(folder, rid, RV.params()["promotion_hold_runs"]),
                         false_fire=false_fire, now=now, prev_roi=RV.previous_roi(folder, rid),
                         memory=RV.frozen_memory(folder))
            v["run_id"] = rid
            v["headline_lines"] = RV.headline_lines(v)
    sc = build(roi, dna, roi_path=roi_path, dna_path=dna_path, now=now, run_id=rid, false_fire=false_fire, voice=v)
    sc["input_files"] = {"folder": folder.name, "bytes": sizes, "book_dna_rebuilt": bool(rebuild_dna)}
    jp, mp = write(sc, out_dir, rid)
    vj, vm = RV.write(v, out_dir, rid)
    return {"status": sc["status"], "run_id": rid, "json": str(jp), "md": str(mp),
            "results_voice_json": str(vj), "results_voice_md": str(vm), "scorecard": sc}


__all__ = ["SCHEMA", "build", "effective_bets", "ends", "marks_age", "exposure_audit", "families_of", "family_line", "family_row", "params",
           "receipt_age", "render_md", "run", "write"]
