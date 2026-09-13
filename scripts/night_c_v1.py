"""BOOK C v1 — the same book with the conditioner the paper actually uses.

WHAT MOVED, IN ONE SENTENCE
===========================
TRIAL-DRAFT-C Amendment 2 (ADOPTED 2026-09-13 13:05 HKT, before any read)
replaces the v0 event sign -- `sign(numup - numdown)`, a monthly IBES revision
COUNT -- with the sign of the [-1, +1] session CRSP-daily return around the
earnings announcement, which is the conditioner Frazzini (JF 2006) uses.
**Nothing else moves.** The Grinblatt-Han recursion, its 60-month window, the
top-tercile cut, k = 30, the unconditioned twin, the $3M primary and $10M
secondary floors and the flat 25 bps ruler are v0's, unchanged -- and this job
does not re-implement any of them: it imports `book_c_event_sign_v1` (which
calls v0's own `book_c_overhang`), `run_sign_flip_placebo`,
`momentum_overhang_rows`, `fama_macbeth_orthogonalisation`,
`read_momentum_verdict`, `registered_read_panel`, `january_split`, `decide`,
`era_stability` and `read_floor_pair` from the v0 job. What differs between this
file and `night_c_falsifiers.py` is the ASSEMBLY of the receipt and the INPUT,
which is exactly what the amendment says differs.

THE PIT RULE, WHICH IS NOT THE OBVIOUS ONE
==========================================
`actdats - anndats` has a median of 0 days and a 95th percentile of 91. "Usable
from the month after the announcement" is therefore true for the median row and
FALSE for the tail. The sign is attributed to the month it became KNOWABLE --
`max(the +1 session, actdats)` -- and read at that month's close, so the
earliest return it can touch is the following month's. `announcement_window_sign`
does that and this job does not second-guess it.

WHAT IS PRINTED BESIDE IT
=========================
`vs_v0`: the v0 registered read, +0.2438%/month at NW lag-2 t 1.3809 over 359
blocks at the $3M floor and +0.0728%/month at t 0.4481 at the $10M floor
(`C_floor10m_run02`, 2026-09-13). TRIAL-DRAFT-C section 3 says the v0-vs-v1
comparison is REPORTED, NEVER DECIDING, and Amendment 2 repeats it: a v1 that
pays where v0 did not is a finding about the conditioner's INPUT and is not a
promotion.

    python -m scripts.night_factory_jobs C_v1 --smoke
    NIGHT_QUEUE="C_v1:60" python -m scripts.night_factory

TIME: the two-floor v0 pass (`C_floor10m`) measured about two minutes. This adds
one full-window CRSP DAILY read (permno, date, ret over the replay years) and one
IBES announcement join, which is the expensive part; projection 15-30 minutes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from scripts.night_c_falsifiers import (
    DECLARED_EFFECT,
    DECLARED_MDE_MONTHLY,
    K,
    PRIMARY_FLOOR_USD,
    REGISTERED_READ_START,
    SECONDARY_FLOOR_USD,
    SEED,
    SMOKE_END,
    SMOKE_READ_START,
    SMOKE_START,
    T_ALIVE,
    decide,
    era_stability,
    fama_macbeth_orthogonalisation,
    january_split,
    momentum_overhang_rows,
    read_floor_pair,
    read_momentum_verdict,
    registered_read_panel,
    run_sign_flip_placebo,
)
from scripts.night_first_books_replay import (
    COST_BPS_PER_SIDE,
    COST_CURVE,
    EVENT_SIGN_V1,
    FLOOR_USD as REPLAY_FLOOR_USD,
    FULL_END,
    FULL_START,
    SMOKE_NAMES,
    book_c_event_sign_v1,
    book_c_selectors,
    by_era,
    holm,
    load_monthly_panel,
    run_monthly,
    wrds_dir,
)

logger = logging.getLogger("c_v1")

JOB = "C_v1"
BOOK = "disposition_overhang_conditioner_v1"
BOOK_ID = "book:a82e6e453c14c241"          # v0's; only the INPUT moved
PREREG = ("TRIAL-DRAFT-C-disposition-overhang-conditioner-v0 Amendment 2 "
          "(ADOPTED 2026-09-13, UNSIGNED as a RESEARCH_CLAIM)")

#: This read is the FOURTH declared primary of the 2026-09-13 family. It is
#: counted ONCE: Amendment 2 says v1 REPLACES v0's primary inside
#: `NIGHT_JOB_BOOKS_2026_09` rather than adding a fifth member there, and this
#: family declares it as one of four before any of the four was read.
FAMILY = "NIGHT_JOB_BOOKS_2026_09_13"

#: The v0 registered read, quoted from `C_floor10m_run02` (2026-09-13) so that
#: `vs_v0` is a difference against a receipt and not against a memory.
V0_REGISTERED = {
    "receipt": "night_factory_2026-09-13/C_floor10m_run02.json",
    "primary_floor": {"mean_excess_net_monthly": 0.002438, "nw_lag2_t": 1.3809,
                      "n_blocks": 359},
    "secondary_floor": {"mean_excess_net_monthly": 0.000728, "nw_lag2_t": 0.4481,
                        "n_blocks": 359},
    "verdict": "SECONDARY_FLOOR_DOES_NOT_CLEAR (the primary never cleared)",
    "era_stability": "positive in 4/4 eras at $3M, 2/4 at $10M",
}

#: IBES's own announcement table, and the filters the probe receipt named.
ANN_TABLE = "bulk/ibes__act_epsus.parquet"
ANN_PDICITY = "QTR"
ANN_MEASURE = "EPS"
LINK_TABLE = "link_ibes_crsp.parquet"


class AnnouncementDatesUnavailable(RuntimeError):
    """The IBES announcement table or its permno link is not on disk.

    Raised rather than returned: a v1 read that quietly fell back to the v0
    revision sign would be the amendment's own forbidden move, made invisible.
    """


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "first_books" / "replay"


# --------------------------------------------------------------------------
# the two panels v1 needs and v0 did not


def load_announcement_dates(start: int, end: int):
    """(permno, anndats, known_date) for every quarterly EPS announcement.

    `anndats` is the announcement date; `known_date` is `actdats`, when the row
    entered IBES -- NOT the same thing, and the difference is the whole PIT rule
    (median 0 days, 95th percentile 91). Both travel, because
    `announcement_window_sign` needs both to decide which month the sign became
    knowable in.

    The ticker -> permno link is `link_ibes_crsp`, applied on its own
    `sdate`/`edate` validity window. A ticker whose announcement falls outside
    every link row is DROPPED, not attached to the nearest permno: an IBES
    ticker is reused across companies and a nearest-match join would put one
    company's earnings on another company's tape.
    """
    import pandas as pd

    a_path = wrds_dir() / ANN_TABLE
    l_path = wrds_dir() / LINK_TABLE
    if not a_path.is_file() or not l_path.is_file():
        raise AnnouncementDatesUnavailable(
            f"v1's event sign is the announcement-window return and needs both "
            f"{a_path} and {l_path}. Missing: "
            f"{[str(p) for p in (a_path, l_path) if not p.is_file()]}. This job "
            f"does NOT fall back to v0's revision count -- that substitution is "
            f"exactly what TRIAL-DRAFT-C section 8 forbids.")

    a = pd.read_parquet(a_path, columns=["ticker", "anndats", "actdats",
                                         "pdicity", "measure"])
    a = a[(a["pdicity"].astype(str) == ANN_PDICITY)
          & (a["measure"].astype(str) == ANN_MEASURE)]
    a["anndats"] = pd.to_datetime(a["anndats"])
    a["actdats"] = pd.to_datetime(a["actdats"])
    a = a.dropna(subset=["ticker", "anndats"])
    a = a[(a["anndats"].dt.year >= int(start)) & (a["anndats"].dt.year <= int(end))]
    a = a.drop_duplicates(subset=["ticker", "anndats"], keep="last")

    link = pd.read_parquet(l_path, columns=["ticker", "permno", "sdate", "edate"])
    link = link.dropna(subset=["ticker", "permno"])
    link["permno"] = link["permno"].astype("int64")
    link["sdate"] = pd.to_datetime(link["sdate"])
    link["edate"] = pd.to_datetime(link["edate"])

    merged = a.merge(link, on="ticker", how="inner")
    merged = merged[(merged["anndats"] >= merged["sdate"])
                    & (merged["anndats"] <= merged["edate"])]
    merged = merged.rename(columns={"actdats": "known_date"})
    out = merged[["permno", "anndats", "known_date"]].drop_duplicates()
    return out.sort_values(["permno", "anndats"], kind="mergesort").reset_index(drop=True)


def load_daily_long(start: int, end: int, *, permnos=None):
    """Long-form CRSP daily rows (permno, date, ret) for the announcement window.

    Long form, not the wide frame Book B's BHAR uses: `announcement_window_sign`
    walks each name's own session index to find the [-1, +1] window, and a wide
    frame over 35 years x 6,000 permnos would be mostly NaN and much larger.

    `ret` is carried as float32 and `permno` as int32. The window is 35 years of
    daily rows and the difference is roughly half a gigabyte of resident memory
    for a sign that only ever gets compared to zero.
    """
    import numpy as np
    import pandas as pd

    keep = None if permnos is None else set(int(p) for p in permnos)
    frames = []
    for y in range(int(start), int(end) + 1):
        p = wrds_dir() / f"crsp_dsf_{y}.parquet"
        if not p.is_file():
            continue
        df = pd.read_parquet(p, columns=["permno", "date", "ret"])
        df = df.dropna(subset=["ret"])
        df["permno"] = df["permno"].astype("int32")
        if keep is not None:
            df = df[df["permno"].isin(keep)]
        df["ret"] = df["ret"].astype(np.float32)
        df["date"] = pd.to_datetime(df["date"])
        frames.append(df)
    if not frames:
        raise AnnouncementDatesUnavailable(
            f"no CRSP daily files under {wrds_dir()} for {start}-{end}; the "
            f"announcement window is a DAILY return and cannot be taken off a "
            f"monthly panel")
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------
# one floor


def v1_cell(read, inputs: dict, *, floor_usd, base: dict) -> dict:
    """Book C's registered read at ONE floor, with v1's sign and v0's everything.

    The shape matches `C_falsifiers`'s return value key for key, so
    `read_floor_pair` -- which is the v0 job's own floor arithmetic -- reads this
    without knowing which version produced it. That is deliberate: a floor
    comparison whose two halves came from two implementations is a comparison of
    two implementations.
    """
    sel = book_c_selectors(inputs)
    primary_res = run_monthly(read, sel["conditioned"], k=K, seed=SEED,
                              label="disposition_overhang_conditioner_v1",
                              twin="unconditioned_reaction_book_v0",
                              twin_select=sel["unconditioned"],
                              floor_usd=floor_usd)
    registered_primary = {
        "label": "primary_registered_construction",
        "what_it_is": ("Book C's OWN primary metric -- conditioned minus "
                       "unconditioned, the same k, the same twin, the same "
                       "engine, the same 60-month overhang window and the same "
                       "1995 start -- with ONE input changed: the event sign is "
                       "the announcement-window return instead of the monthly "
                       "revision count."),
        "result": {k2: v for k2, v in primary_res.items()
                   if k2 not in ("blocks", "excess")},
        "by_era": by_era(primary_res),
        "declared_effect_size": DECLARED_EFFECT,
        "declared_mde_monthly": DECLARED_MDE_MONTHLY,
        "january_diagnostic": january_split(primary_res),
        "vs_v0": {
            "v0_registered": V0_REGISTERED,
            "note": ("REPORTED, NEVER DECIDING. TRIAL-DRAFT-C section 3 lists "
                     "the v0-vs-v1 comparison among the things reported and not "
                     "deciding, and Amendment 2 repeats it: a v1 that pays where "
                     "v0 did not is a finding about the conditioner's INPUT and "
                     "is not a promotion."),
        },
    }
    placebo = run_sign_flip_placebo(read, inputs, floor_usd=floor_usd)
    rows = momentum_overhang_rows(read, inputs["cgo_by_month"],
                                  floor_usd=floor_usd)
    fm = fama_macbeth_orthogonalisation(rows)
    momentum = {"falsifier": "momentum_orthogonalisation",
                "registered_as": ("TRIAL-DRAFT-C section 1 quotes Grinblatt-Han: "
                                  "with overhang on the right-hand side, "
                                  "intermediate-horizon momentum DISAPPEARS. "
                                  "Section 5 makes its survival a FAILED_VARIANT "
                                  "trigger."),
                "construction": ("v0's own `momentum_overhang_rows` and "
                                 "`fama_macbeth_orthogonalisation`, unchanged. "
                                 "The overhang on the right-hand side is the "
                                 "same series the book traded, because "
                                 "`book_c_event_sign_v1` builds it by calling "
                                 "v0's `book_c_overhang`."),
                "fama_macbeth": {k2: v for k2, v in fm.items() if k2 != "blocks"},
                **read_momentum_verdict(fm)}

    for_decision = dict(registered_primary["result"])
    for_decision["declared_effect_size"] = DECLARED_EFFECT
    verdict = decide(placebo, momentum, for_decision)
    verdict["primary_read_against"] = "primary_registered_construction"
    mean = (placebo.get("vs_unconditioned") or {}).get("mean_excess_net_monthly")
    return {
        **base, "ran": True,
        "floor_usd": (float(REPLAY_FLOOR_USD) if floor_usd is None
                      else float(floor_usd)),
        "floor_is_registered_primary": floor_usd is None,
        "event_sign": inputs["event_sign"],
        "primary_registered_construction": registered_primary,
        "sign_flip_placebo": placebo,
        "momentum_orthogonalisation": momentum,
        "era_stability": era_stability(registered_primary),
        "decision_rule": ("TRIAL-DRAFT-C section 5, including Amendment 1's "
                          "`primary <= 0 closes it` clause. FAILED_VARIANT if "
                          "the placebo also pays OR momentum survives "
                          "orthogonalisation -- either clause alone, whatever "
                          "the primary metric did."),
        "headline": (
            f"v1 floor ${(REPLAY_FLOOR_USD if floor_usd is None else floor_usd):,.0f}: "
            f"{registered_primary['result'].get('mean_excess_net_monthly')}/month "
            f"t {registered_primary['result'].get('nw_lag2_t')} over "
            f"{registered_primary['result'].get('n_blocks')} blocks (v0: "
            f"{V0_REGISTERED['primary_floor']['mean_excess_net_monthly']} at $3M); "
            f"placebo {mean}/month (pays: {placebo.get('placebo_pays')}); "
            f"orthogonalised momentum t {momentum.get('t_resid_mom')} vs raw "
            f"{momentum.get('t_raw_mom')} ({momentum.get('verdict')})"),
        "verdict": verdict["verdict"] + " — " + verdict["reading"],
        "verdict_block": verdict,
    }


def vs_v0_block(primary: dict, secondary: dict) -> dict:
    """The v0 -> v1 difference at both floors. REPORTED, NEVER DECIDING."""
    def _read(cell, key):
        res = ((cell or {}).get("primary_registered_construction") or {}).get("result") or {}
        v0 = V0_REGISTERED[key]
        m, t = res.get("mean_excess_net_monthly"), res.get("nw_lag2_t")
        return {"v1_mean_excess_net_monthly": m, "v1_nw_lag2_t": t,
                "v1_n_blocks": res.get("n_blocks"),
                "v0_mean_excess_net_monthly": v0["mean_excess_net_monthly"],
                "v0_nw_lag2_t": v0["nw_lag2_t"], "v0_n_blocks": v0["n_blocks"],
                "delta_mean_v1_minus_v0": (None if m is None else
                                           round(m - v0["mean_excess_net_monthly"], 6))}
    return {
        "status": "REPORTED_NEVER_DECIDING",
        "primary_floor": _read(primary, "primary_floor"),
        "secondary_floor": _read(secondary, "secondary_floor"),
        "v0_receipt": V0_REGISTERED["receipt"],
        "why": ("TRIAL-DRAFT-C section 3 lists the v0-vs-v1 comparison among "
                "the things reported and never deciding, and Amendment 2 says "
                "it creates NO new way for the book to pass: v1 is a second "
                "reading of the same hypothesis with the conditioner the cited "
                "paper uses, and the two block counts differ because the two "
                "signs cover different sets of name-months -- so the delta is a "
                "difference of two reads and not a paired test."),
    }


def family_holm_block(c_v1_p) -> dict:
    """The complete four-leg Holm block for `NIGHT_JOB_BOOKS_2026_09_13`.

    `B_books_efg_replay` names this leg without a p-value because it cannot
    compute it. This job can, and it reads E, F and G's p-values off that job's
    own receipt rather than recomputing them, so the four numbers in one block
    come from one run each and not from two different checkouts.
    """
    from scripts.night_books_efg_replay import (
        DECLARED_FAMILY, find_run_receipt as find_efg,
    )

    pvals = {name: None for name in DECLARED_FAMILY}
    pvals[BOOK] = c_v1_p
    src = find_efg(smoke=False)
    if src is not None and src.is_file():
        payload = json.loads(src.read_text(encoding="utf-8"))
        for b in payload.get("books") or []:
            if b.get("ran"):
                cell = (b.get("cells") or {}).get("primary_floor") or {}
                pvals[b["book"]] = (cell.get("result") or {}).get("p_two_sided")
    block = holm(pvals, family=FAMILY)
    block["efg_receipt"] = (str(src) if src else None)
    block["note_on_completeness"] = (
        "E, F and G's p-values are read off `B_books_efg_replay`'s own receipt. "
        "If that receipt is absent they are NAMED here without a p-value and the "
        "correction is still against the DECLARED family size of four -- a leg "
        "that could not be read does not make the correction cheaper for the "
        "legs that could."
        if src else
        "NO `B_books_efg_replay` receipt was found on this checkout, so three of "
        "the four declared legs carry no p-value. The correction is still "
        "against four. Run that job first if you want the complete block.")
    return block


# --------------------------------------------------------------------------
# the job


def C_v1(*, smoke: bool = False) -> dict:                         # noqa: N802
    """TRIAL-DRAFT-C Amendment 2's read: the same book, the paper's conditioner."""
    start = SMOKE_START if smoke else FULL_START
    end = SMOKE_END if smoke else FULL_END
    base = {
        "job": JOB, "family": FAMILY, "licence": "PRODUCT_EXPERIMENT",
        "book": BOOK, "book_id": BOOK_ID, "prereg": PREREG,
        "window": [start, end], "smoke": bool(smoke),
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "cost_caveat": ("the interim flat ruler, pending chunk 5c's TAQ curve. "
                        "Both legs of every comparison pay it, so DIFFERENCES "
                        "are what may be read and no LEVEL may."),
        "question": ("Does the disposition-overhang conditioner read differently "
                     "when the conditioning sign is the announcement-window "
                     "return Frazzini (JF 2006) uses, instead of v0's monthly "
                     "revision count?"),
        "what_moved_from_v0": ("the event sign, and nothing else. The "
                               "Grinblatt-Han recursion, its 60-month window, "
                               "the tercile, k=30, the unconditioned twin, both "
                               "floors and the cost ruler are v0's, and this job "
                               "imports v0's own implementations of every "
                               "falsifier rather than writing second ones."),
        "amendment": ("TRIAL-DRAFT-C Amendment 2, adopted 2026-09-13 13:05 HKT "
                      "BEFORE any read, as Amendment 1 was. It licenses a "
                      "PRODUCT_EXPERIMENT read only; the book stays UNSIGNED as "
                      "a RESEARCH_CLAIM."),
        "family_note": ("this read is the FOURTH declared primary of "
                        "NIGHT_JOB_BOOKS_2026_09_13 and is counted ONCE: "
                        "Amendment 2 says v1 REPLACES v0's primary inside "
                        "NIGHT_JOB_BOOKS_2026_09 rather than adding a fifth "
                        "member there."),
    }

    panel = load_monthly_panel(start, end,
                              max_names=SMOKE_NAMES if smoke else None)
    base["months_in_panel"] = int(panel["ym"].nunique())
    base["permnos_in_panel"] = int(panel["permno"].nunique())
    try:
        ann = load_announcement_dates(start, end)
        daily = load_daily_long(start, end, permnos=panel["permno"].unique())
    except AnnouncementDatesUnavailable as exc:
        return {**base, "ran": False, "refused": str(exc),
                "headline": "v1 cannot run without the announcement dates",
                "verdict": "REFUSED: " + str(exc)}
    base["announcement_rows"] = int(len(ann))
    base["announcement_permnos"] = int(ann["permno"].nunique())
    base["daily_rows"] = int(len(daily))

    inputs = book_c_event_sign_v1(panel, daily, ann)
    del daily
    base["event_sign"] = EVENT_SIGN_V1
    base["event_sign_coverage"] = {
        "n_announcements_signed": inputs["n_announcements_signed"],
        "n_good": inputs["n_good"], "n_bad": inputs["n_bad"],
        "window_sessions": inputs["event_window_sessions"],
        "note": ("a window that runs off either end of a name's own tape is "
                 "DROPPED, not truncated, and a cumulative return of exactly "
                 "zero carries no sign and is dropped too. Both are the v1 "
                 "builder's own rules and this job does not relax them."),
    }

    want_start = SMOKE_READ_START if smoke else REGISTERED_READ_START
    read, read_start, first_cgo = registered_read_panel(panel, inputs,
                                                        read_start=want_start)
    base["registered_construction"] = {
        "cgo_min_history_months": inputs["cgo_min_history_months"],
        "cgo_lookback_months": inputs["cgo_lookback_months"],
        "cgo_window_is_full": inputs["cgo_window_is_full"],
        "registered_read_start": REGISTERED_READ_START,
        "read_start_used": read_start,
        "first_month_with_a_full_window": first_cgo,
        "months_read": int(read["ym"].nunique()) if len(read) else 0,
        "event_sign": "v1 (announcement window)",
        "honours_the_registration": bool(
            not smoke and read_start == REGISTERED_READ_START),
        "why": ("printed in full because run 1 of this book warmed a 60-month "
                "overhang at 24 months and its receipt said `confirm_slice "
                "1995-2024` anyway. A smoke window cannot honour the 1995 start "
                "and says so here rather than being mistaken for it."),
    }
    if len(read) == 0 or read["ym"].nunique() < 4:
        return {**base, "ran": False,
                "refused": (f"the registered construction leaves "
                            f"{0 if not len(read) else read['ym'].nunique()} "
                            f"readable month(s) from {read_start}"),
                "headline": "no month survives the registered 60-month window",
                "verdict": "REFUSED: the registered construction has no read window"}

    cells = {}
    for name, floor in (("primary_floor", PRIMARY_FLOOR_USD),
                        ("secondary_floor", SECONDARY_FLOOR_USD)):
        cells[name] = v1_cell(read, inputs, floor_usd=floor, base=base)
    pair = read_floor_pair(cells["primary_floor"], cells["secondary_floor"])
    p, s = pair["primary"], pair["secondary"]
    c_v1_p = ((cells["primary_floor"]["primary_registered_construction"]
               ["result"]).get("p_two_sided"))

    payload = {
        **base, "ran": bool(pair["both_floors_read"]),
        "floors_usd": {"primary": float(REPLAY_FLOOR_USD),
                       "secondary": float(SECONDARY_FLOOR_USD)},
        "floor_comparison": pair,
        "vs_v0": vs_v0_block(cells["primary_floor"], cells["secondary_floor"]),
        "era_stability": {
            "primary_floor": era_stability(
                cells["primary_floor"]["primary_registered_construction"]),
            "secondary_floor": era_stability(
                cells["secondary_floor"]["primary_registered_construction"])},
        "family_multiplicity": {
            "family": FAMILY, "declared_family_size": 4,
            "holm": family_holm_block(c_v1_p),
            "falsifiers_are_not_family_members": (
                "a falsifier is a registered TRIGGER, not a primary metric. "
                "Adding them to the Holm block would make the four declared "
                "tests cheaper or dearer depending on how many diagnostics a "
                "session happened to run."),
        },
        "cells": cells,
        "t_alive": T_ALIVE,
        "next_test": ("whichever of the family's four books carries a POSITIVE "
                      "$10M cell at |t| >= 2 is the one chunk 13b's allocator "
                      "question is about; and the TAQ cost curve, which is the "
                      "only thing that can make the two floors pay different "
                      "spreads."),
        "headline": (
            f"v1 $3M {p['mean_excess_net_monthly']}/month t {p['nw_lag2_t']} over "
            f"{p['n_blocks']} blocks | $10M {s['mean_excess_net_monthly']}/month "
            f"t {s['nw_lag2_t']} over {s['n_blocks']} blocks "
            f"(v0 was {V0_REGISTERED['primary_floor']['mean_excess_net_monthly']} "
            f"t {V0_REGISTERED['primary_floor']['nw_lag2_t']} at $3M) -> "
            f"{pair['verdict']}"),
        "verdict": pair["verdict"] + " — " + pair["reading"],
    }
    return payload


__all__ = ["AnnouncementDatesUnavailable", "BOOK", "C_v1", "FAMILY",
           "V0_REGISTERED", "family_holm_block", "load_announcement_dates",
           "load_daily_long", "v1_cell", "vs_v0_block"]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    print(json.dumps(C_v1(smoke=a.smoke), indent=1, default=str))
