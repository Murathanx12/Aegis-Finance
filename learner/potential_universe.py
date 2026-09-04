"""POTENTIAL UNIVERSE v1 -- one scorecard per observable company-vintage.

WHY THIS OBJECT EXISTS (the starved-seal incident, 2026-09-03)
==============================================================
On the night of 2026-09-03 the authority's first solo seal was VALID and
EMPTY: `days_to_catalyst` derives from the observation corpus, which lives
only on the laptop and never on the authority's volume, so `d_catalyst` was
UNREADABLE on all 810 candidates. hack4 (`requires_catalyst=True`) sealed
zero names, and the exit pass then treated "dropped out of the book" as SELL
-- **a data gap became a sell decision** -- and the books drifted to ~15-30%
deployed on competition eve. Nothing in the pipeline could SAY "this field is
unreadable on the whole universe tonight"; the starvation was invisible until
the book was already empty and the sells already queued.

This module is the cheap structural fix the incident demands: a per-name
scorecard in which every input the program has an opinion about is either a
VALUE or a NAMED REFUSAL, and whole-universe refusals are counted in the
header where a seal-time reader (human or gate) cannot miss them. A field
that is unreadable on 810 of 810 names shows up here as
`field_readability.days_to_catalyst.unreadable = 810` BEFORE anything
downstream turns that absence into an action.

WHAT THIS IS IN THE PIPELINE (review 2026-09-03, PART B)
========================================================
    WORLD MODEL -> POTENTIAL UNIVERSE -> STRATEGY SLEEVES -> CAPITAL ALLOCATOR
        -> DECISION ARTIFACT -> EXECUTION (sealed, gates-only cuts)

The PotentialUniverse is the INPUT of the coming Capital Allocator: for every
observable name it answers "what does each layer of the program currently
believe about this name, what can it NOT say, and what observation would flip
it". It is persisted daily beside the shadow books and is graded like any
book -- the header carries `graded_like_a_book: "pending"` until a grader
exists.

ZERO BROKER AUTHORITY, BY CONSTRUCTION
======================================
Same contract as `learner/shadow.py`, whose readers and mappers this module
reuses: it READS `aegis-alpha-terminal/state/tracker/<day>.jsonl` read-only
and WRITES one JSONL file into this repository's data directory. No Alpaca
client, no ledger write, no import from the execution repo. The execution
repo does not import `learner`.

REFUSALS ARE PER-NAME FIELDS, NOT CRASHES
=========================================
The house failure mode is code that runs green and silently does nothing.
Its inverse -- refusing the whole day because one name is missing one column
-- is just as useless to an allocator. So every scorecard section carries a
`status`, and a section that cannot be computed says REFUSED (or
CANNOT_DETERMINE) with the missing inputs NAMED. Three refusals are known in
advance and stated here rather than discovered per row:

* **learner_v2**: the frozen champion (`encoder_clf__residual`, 1m, receipt
  `tracker_backtest/learner_v2_20260903.json`, frozen by the 2026-09-03
  review: ONE champion, one metric, graded forward) is sealed against the
  FULL 49-column panel schema. A tracker day file can only supply the
  SHADOW_MAPPABLE subset; median-imputing the rest and calling the output a
  prediction is exactly the failure this repo keeps paying for. So v2 is a
  whole-universe refusal with the missing columns named, until a v2 champion
  is retrained on the shadow schema.
* **state**: the unsupervised states were fitted on 18 PIT features of which
  a day file supplies only 10; assignment would require imputing the other 8
  (the revision and short-momentum families). Refused, named, semantics
  receipt referenced so a reader can still see what state 0 MEANS.
* **v1 per-name**: the sealed shadow champion scores any name carrying the
  CORE features; a name missing some of them gets a per-name refusal naming
  exactly which.

PIT DISCIPLINE
==============
Every tracker row carries `observed_at`. A row stamped at or after its own
day's market close is POST-CLOSE information wearing a vintage's clothes; it
is marked PIT-refused and nothing in its scorecard is scored. The close is
approximated as 20:00 UTC (16:00 ET under EDT) -- the STRICTER of the two
DST readings, refusing an extra hour under EST rather than admitting one.
A row with no `observed_at` at all cannot prove it is pre-close and is
refused too: an unverifiable vintage is not a vintage.

THE ENGINE PRIOR IS AN EXCLUSION RULE (S36)
===========================================
`band_horizon_20260903.json` demoted the band prior: only `toxic_ge_5`
survives BH-FDR, the <1.5 floor is the other surviving content, and the 3-5
band's positive claim is dead in 2022-2024. So the engine verdicts here are
exclusion-shaped: `toxic_ge_5` and `sub_floor` EXCLUDE, `unreadable` and
`no_opinion` name why no opinion exists, and `admitted_shadow` explicitly
says the admission is a SHADOW/CONTROL statement, not an alpha claim.

UPDATE 2026-09-05 -- THAT RECEIPT IS VOID, AND THE CONCLUSION GOT STRONGER
=========================================================================
`band_horizon_20260903.json` was computed on a tape whose `ratio` divided the
SPLIT-ADJUSTED IBES consensus by the RAW close, so `toxic_ge_5` was largely a
FUTURE-REVERSE-SPLIT detector. Re-issued point-in-time
(`band_horizon_20260905.json`), the four bands are -2.17 / -6.82 / -5.26 /
+40.07 pp/yr at one month and **ZERO** survive BH-FDR over a 32-cell screen
(family max p 0.808, min p 0.0517). The exclusion-shaped verdicts below are
therefore MORE right than when they were written, and for a different reason:
not "one band is reliably terrible" but "no band premium exists at all, so the
only defensible content is hygiene". The `toxic_ge_5` reason string has been
corrected in place; retiring `learner/prior.py`'s constants to hygiene-only is
roadmap B1 task 5 and is ATTENDED, so the THRESHOLDS here are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from learner import dataset as D
from learner import models as M
from learner import prior as P
from learner import shadow as S
from learner import states as ST

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "backend" / "data" / "optimus" / "potential_universe"

CODE_VERSION = "potential_universe_v1/2026-09-03"

#: The ONE frozen v2 champion, per the external review (PART A Q3: pre-register
#: one champion + one metric, grade forward only). Identity is declared here;
#: its NUMBERS live in the receipt and are read from it, never retyped.
V2_FROZEN_CHAMPION = {
    "name": "encoder_clf__residual",
    "horizon_months": 1,
    "receipt": "backend/data/optimus/tracker_backtest/learner_v2_20260903.json",
    "frozen_by": "docs/REVIEW_2026-09-03_GPT_VERDICTS_AND_CAPITAL_ALLOCATOR.md",
}
V2_RECEIPT_PATH = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
                   / "learner_v2_20260903.json")
STATES_RECEIPT = "backend/data/optimus/tracker_backtest/unsupervised_states_20260903.json"

#: State semantics tags, from the states receipt + S36 scoreboard. Stored so a
#: scorecard reader sees what a state MEANS even while assignment is refused.
STATE_SEMANTICS = {
    "0": "broken-lottery-ticket: mean -4.9%/3m t -3.4, worst-5% -75%, "
         "big-upside freq 21.7% -- the lost-winners address",
    "receipt": STATES_RECEIPT,
    "note": "4 OOS states, k=4, p=0.000 vs 200 random partitions; "
            "half the panel kills every model except lgbm_clf",
}

# ------------------------------------------------------- execution capacity
#
# Re-derived from the tracker day file's own liquidity column
# (`median_dollar_volume`), with the semantics of
# `aegis-alpha-terminal/alpha/universe.py::execution_authority` (read-only,
# 2026-09-03) -- NOT imported from the execution repo. The convention, named:
#   mdv missing            -> CANNOT_DETERMINE (the column is named; an absent
#                             dollar volume is not a dollar volume of zero)
#   mdv <  $20k/day        -> NONE (below even the observation floor)
#   mdv <  $3.0m/day       -> OBSERVE_ONLY (observable and gradeable, at most
#                             1% of ADV transactable -- a fact about our size,
#                             not about the company)
#   mdv >= $3.0m/day       -> FULL (clears the terminal universe floor)
OBSERVE_FLOOR_USD = 20_000.0
EXECUTE_FLOOR_USD = 3_000_000.0          # == shadow.MIN_DOLLAR_VOL, the house floor
MAX_ADV_PARTICIPATION = 0.01
LIQUIDITY_COLUMN = "median_dollar_volume"

CAPACITY_CONVENTION = (
    f"re-derived from the day file's `{LIQUIDITY_COLUMN}` with the semantics of "
    "aegis-alpha-terminal/alpha/universe.py::execution_authority (read 2026-09-03): "
    f"missing -> CANNOT_DETERMINE; < ${OBSERVE_FLOOR_USD:,.0f}/day -> NONE; "
    f"< ${EXECUTE_FLOOR_USD:,.0f}/day -> OBSERVE_ONLY (max {MAX_ADV_PARTICIPATION:.0%} "
    "of ADV); otherwise FULL. Never imported from the execution repo."
)

#: PIT close approximation, said once. 16:00 ET is 20:00 UTC under EDT and
#: 21:00 UTC under EST; 20:00 is the STRICTER reading and is used year-round.
PIT_CLOSE_UTC_HOUR = 20

ENGINE_VERDICTS = ("unreadable", "no_opinion", "toxic_ge_5", "sub_floor",
                   "admitted_shadow")
CAPACITY_TIERS = ("CANNOT_DETERMINE", "NONE", "OBSERVE_ONLY", "FULL")

#: Golden keys: the scorecard's top-level shape, pinned so a consumer (the
#: Capital Allocator) can rely on it. Changing this list is a schema change
#: and must bump CODE_VERSION.
SCORECARD_KEYS = (
    "symbol", "day", "observed_at", "pit", "identity",
    "engine_prior", "learner_v1", "learner_v2", "p_beat", "state",
    "disagreement", "execution", "days_to_catalyst", "falsifiers",
)
HEADER_KEYS = (
    "artefact", "version", "licence", "day", "generated_at_utc",
    "broker_authority", "motivation", "source", "champion", "conventions",
    "field_readability", "whole_universe_refusals", "counts",
    "graded_like_a_book", "schema",
)


def schema_hash() -> str:
    blob = json.dumps({"scorecard": list(SCORECARD_KEYS),
                       "header": list(HEADER_KEYS),
                       "version": CODE_VERSION}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# ----------------------------------------------------------------- helpers

def _f(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _r(v, nd: int = 5):
    f = _f(v)
    return round(f, nd) if f is not None else None


def pit_check(day: str, observed_at) -> dict:
    """A row must PROVE it was observed before its own day's close.

    Returns {"status": "OK"} or {"status": "REFUSED", "reason": ...}. The
    refusal direction is deliberate: an unstamped or post-close row could be
    tomorrow's information, and a scorecard built on it would train the
    allocator on the future.
    """
    if not observed_at:
        return {"status": "REFUSED",
                "reason": "no observed_at stamp; a row that cannot prove it is "
                          "pre-close is refused, not assumed"}
    try:
        ts = datetime.fromisoformat(str(observed_at))
    except ValueError:
        return {"status": "REFUSED",
                "reason": f"observed_at unparseable: {observed_at!r}"}
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    try:
        d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return {"status": "REFUSED", "reason": f"day unparseable: {day!r}"}
    close = d.replace(hour=PIT_CLOSE_UTC_HOUR)
    if ts >= close:
        return {"status": "REFUSED",
                "reason": f"observed_at {ts.isoformat(timespec='seconds')} is at/after "
                          f"the {day} close ({PIT_CLOSE_UTC_HOUR:02d}:00 UTC, 16:00 ET "
                          "under EDT -- the stricter DST reading): post-close information"}
    return {"status": "OK"}


def v2_missing_inputs() -> list[str]:
    """The full-schema columns a tracker day file cannot supply -- DERIVED from
    the two schema functions, never retyped, so it cannot drift from them."""
    shadow_cols = set(D.feature_columns(shadow_only=True))
    return [c for c in D.feature_columns(shadow_only=False) if c not in shadow_cols]


def state_missing_inputs(frame_columns) -> list[str]:
    """STATE_FEATURES the mapped day frame does not carry."""
    have = set(frame_columns)
    return [c for c in ST.STATE_FEATURES if c not in have]


def capacity_of(mdv) -> dict:
    """Execution capacity from the day file's own liquidity column. See
    CAPACITY_CONVENTION for the named semantics."""
    v = _f(mdv)
    if v is None:
        return {"tier": "CANNOT_DETERMINE", "observe_only": None, "max_usd": None,
                "median_dollar_volume": None,
                "reason": f"`{LIQUIDITY_COLUMN}` missing from the row; an absent "
                          "dollar volume is not a dollar volume of zero"}
    cap = round(v * MAX_ADV_PARTICIPATION, 2)
    if v < OBSERVE_FLOOR_USD:
        return {"tier": "NONE", "observe_only": True, "max_usd": 0.0,
                "median_dollar_volume": v,
                "reason": f"${v:,.0f}/day is below the ${OBSERVE_FLOOR_USD:,.0f} observation floor"}
    if v < EXECUTE_FLOOR_USD:
        return {"tier": "OBSERVE_ONLY", "observe_only": True, "max_usd": cap,
                "median_dollar_volume": v,
                "reason": f"${v:,.0f}/day is under the ${EXECUTE_FLOOR_USD:,.0f} execute "
                          f"floor: observable and gradeable, at most ${cap:,.0f} transactable"}
    return {"tier": "FULL", "observe_only": False, "max_usd": cap,
            "median_dollar_volume": v,
            "reason": f"${v:,.0f}/day clears the execute floor"}


def engine_verdict(ratio, close, coverage) -> dict:
    """The band prior as an EXCLUSION rule (S36), per name, with the missing
    inputs named when it cannot even be read."""
    r, c, n = _f(ratio), _f(close), _f(coverage)
    missing = []
    if r is None:
        missing += [x for x, v in (("mean_target/close -> ratio", r),) if v is None]
    if c is None:
        missing.append("close")
    if n is None:
        missing.append("coverage (rec_counts empty or absent)")
    if missing:
        return {"verdict": "unreadable", "band": "no_opinion",
                "reasons": [f"missing inputs: {missing}"]}
    if c < P.MIN_PRICE or n < P.MIN_COVERAGE:
        why = []
        if c < P.MIN_PRICE:
            why.append(f"close ${c:.2f} < ${P.MIN_PRICE:.2f} hygiene floor -- the sub-$2 "
                       "band prior is UNINFORMATIVE (t 0.39, S30b): no opinion, "
                       "never 'historically bad'")
        if n < P.MIN_COVERAGE:
            why.append(f"coverage {n:.0f} < {P.MIN_COVERAGE} recommenders")
        return {"verdict": "no_opinion", "band": "no_opinion", "reasons": why}
    band = str(P.band_label([r]).iloc[0])
    if band == "toxic_ge_5":
        # The exclusion STANDS; the reason it used to give is void. On the
        # corrupted split-adjusted tape this cell measured -37.77%/yr t -7.75 and
        # was the only band surviving BH-FDR. On the point-in-time panel
        # (`band_horizon_20260905.json`) it measures **+40.07%/yr t_b +1.97** and
        # ZERO bands survive BH-FDR -- the old number was a future-reverse-split
        # detector (74.4% of its rows carried one). The exclusion is now
        # HYGIENE-shaped, and it is a better-supported exclusion for that: the
        # cell holds ~7 names a month at a median close of $3.08, 84% of it under
        # $5, 86% below $3m/day, and its sign FLIPS to -34.29%/yr under a $5
        # floor. Retiring the band prior to hygiene-only is roadmap B1 task 5 and
        # is ATTENDED; this string is corrected now so a live surface stops
        # printing a withdrawn number.
        return {"verdict": "toxic_ge_5", "band": band,
                "reasons": [f"ratio {r:.2f} >= 5: EXCLUDED on HYGIENE. ~7 names/month, "
                            "median close $3.08, 84% under $5, 86% below $3m/day, and "
                            "27.6% still carry a future reverse split "
                            "(band_horizon_20260905.json). The old rationale "
                            "(-37.77%/yr t -7.75, 'the only band surviving BH-FDR') is "
                            "VOID: on a point-in-time ratio the cell is +40.07%/yr "
                            "t_b +1.97 and NO band survives BH-FDR. Not a short either -- "
                            "see toxic_band_short_20260905.json."]}
    if band == "lt_1_5":
        return {"verdict": "sub_floor", "band": band,
                "reasons": [f"ratio {r:.2f} < {P.ADMISSIBLE_RATIO_LO}: below the admission "
                            "floor. EXCLUDED."]}
    return {"verdict": "admitted_shadow", "band": band,
            "reasons": [f"ratio {r:.2f} in [{P.ADMISSIBLE_RATIO_LO}, {P.ADMISSIBLE_RATIO_HI}): "
                        "admitted as SHADOW/CONTROL only -- S36 demoted the band to an "
                        "exclusion rule (3-5 band +2.3%/yr t 0.12 in 2022-24); this is "
                        "not an alpha claim."]}


def _stance_of_prior(prior_1m, verdict: str) -> str:
    if verdict in ("unreadable", "no_opinion"):
        return "none"
    p = _f(prior_1m)
    if p is None or p == 0.0:
        return "none"
    return "positive" if p > 0 else "negative"


def disagreement_of(engine_stance: str, p_beat_raw, base_rate,
                    prior_rank, score_rank) -> dict:
    """Engine vs learner, EXPLICITLY encoded. The learner's reference is the
    realised base rate, never 0.5 (most names lose to a cap-weighted market
    most months -- learner_v2 receipt, `the_shadow_book_question`)."""
    p, b = _f(p_beat_raw), _f(base_rate)
    if p is None:
        learner_stance = "refused"
    elif b is None:
        learner_stance = "no_base_rate"
    else:
        learner_stance = "above_base_rate" if p > b else "at_or_below_base_rate"
    sign_dis = None
    if engine_stance in ("positive", "negative") and learner_stance in (
            "above_base_rate", "at_or_below_base_rate"):
        sign_dis = ((engine_stance == "positive") !=
                    (learner_stance == "above_base_rate"))
    rank_gap = None
    if prior_rank is not None and score_rank is not None:
        rank_gap = round(float(prior_rank - score_rank), 4)
    return {"engine_stance": engine_stance, "learner_stance": learner_stance,
            "sign_disagreement": sign_dis, "rank_gap": rank_gap,
            "verdict": ("UNDEFINED" if sign_dis is None
                        else ("DISAGREE" if sign_dis else "AGREE"))}


def falsifiers_of(card: dict) -> list[dict]:
    """What observation flips this scorecard -- machine-checkable where the
    flip is a threshold, prose where it is a data-availability event."""
    out: list[dict] = []
    ep = card["engine_prior"]
    if ep["verdict"] == "toxic_ge_5":
        out.append({"field": "ratio", "op": "<", "value": 5.0,
                    "then": "leaves the toxic band (target cut or price rise); "
                            "verdict becomes admitted_shadow or sub_floor"})
    elif ep["verdict"] == "sub_floor":
        out.append({"field": "ratio", "op": ">=", "value": P.ADMISSIBLE_RATIO_LO,
                    "then": "clears the admission floor; verdict becomes admitted_shadow"})
    elif ep["verdict"] == "admitted_shadow":
        out.append({"field": "ratio", "op": ">=", "value": P.ADMISSIBLE_RATIO_HI,
                    "then": "enters the toxic band; verdict becomes toxic_ge_5 (EXCLUDED)"})
        out.append({"field": "ratio", "op": "<", "value": P.ADMISSIBLE_RATIO_LO,
                    "then": "falls below the floor; verdict becomes sub_floor"})
    elif ep["verdict"] == "no_opinion":
        out.append({"field": "close", "op": ">=", "value": P.MIN_PRICE,
                    "then": "price hygiene passes (coverage hygiene must also pass)"})
        out.append({"field": "coverage", "op": ">=", "value": float(P.MIN_COVERAGE),
                    "then": "coverage hygiene passes (price hygiene must also pass)"})
    elif ep["verdict"] == "unreadable":
        out.append({"field": "mean_target,close,rec_counts", "op": "present", "value": None,
                    "then": "the ratio/coverage become readable; a band verdict exists"})
    ex = card["execution"]
    if ex["tier"] == "OBSERVE_ONLY":
        out.append({"field": LIQUIDITY_COLUMN, "op": ">=", "value": EXECUTE_FLOOR_USD,
                    "then": "clears the execute floor; tier becomes FULL"})
    elif ex["tier"] == "CANNOT_DETERMINE":
        out.append({"field": LIQUIDITY_COLUMN, "op": "present", "value": None,
                    "then": "capacity becomes derivable"})
    if card["learner_v1"]["status"] == "REFUSED":
        out.append({"field": ",".join(card["learner_v1"].get("missing_inputs", [])),
                    "op": "present", "value": None,
                    "then": "the v1 champion can score this name"})
    if not card["days_to_catalyst"]["readable"]:
        out.append({"field": "days_to_catalyst", "op": "present", "value": None,
                    "then": "catalyst-gated sleeves (hack4-shaped) can admit this name; "
                            "tonight this field was unreadable on the WHOLE universe and "
                            "a book sealed empty"})
    return out


# ------------------------------------------------------------------- build

def _load_v2_receipt() -> dict | None:
    if V2_RECEIPT_PATH.exists():
        try:
            return json.loads(V2_RECEIPT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _calibration_reference(v2_receipt: dict | None, champ_kind: str) -> dict:
    """Base rate + model-level bias for the v1 probability, read from the v2
    receipt (never retyped). The LITERAL calibrated head belongs to the frozen
    v2 champion, which is refused at shadow time -- so what a scorecard can
    honestly carry is the raw probability, the base-rate reference, and the
    receipt's measured model-level bias."""
    if champ_kind != M.CLASSIFIER:
        return {"status": "NOT_APPLICABLE",
                "reason": f"v1 champion kind {champ_kind!r} does not emit a probability"}
    if v2_receipt is None:
        return {"status": "REFUSED",
                "reason": f"calibration receipt unreadable at {V2_RECEIPT_PATH.name}; "
                          "raw probability reported without a base-rate reference"}
    try:
        blk = v2_receipt["calibration"]["1m"]["lgbm_clf"]["raw_all_rows"]
        return {"status": "OK",
                "base_rate": float(blk["base_rate_realised"]),
                "model_level_bias": float(blk["mean_predicted_minus_base_rate"]),
                "source": V2_FROZEN_CHAMPION["receipt"],
                "note": "reference is the realised base rate, never 0.5; debiased = raw - "
                        "model_level_bias; LITERAL calibration is the frozen v2 head, "
                        "refused at shadow time (see learner_v2)"}
    except (KeyError, TypeError, ValueError):
        return {"status": "REFUSED",
                "reason": "calibration.1m.lgbm_clf.raw_all_rows absent from the receipt"}


def build_potential_universe(day: str | None = None, *,
                             rows: list[dict] | None = None,
                             provenance: dict | None = None,
                             champion: dict | None = None,
                             band_map: dict | None = None,
                             v2_receipt: dict | None = None) -> dict:
    """One scorecard per observable name for `day`. Returns
    {"header": ..., "scorecards": [...]}. Every keyword is injectable so the
    tests run offline on synthetic day files; the defaults read the real
    substrate. Places NOTHING either way."""
    day = day or S.latest_tracker_day()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header: dict = {
        "artefact": "AEGIS_POTENTIAL_UNIVERSE",
        "version": CODE_VERSION,
        "licence": "PRODUCT_EXPERIMENT",
        "day": day,
        "generated_at_utc": now,
        "broker_authority": "NONE -- this file is written, never sent. No order path "
                            "imports learner/; the execution repo does not depend on it.",
        "motivation": "starved-seal incident 2026-09-03: d_catalyst UNREADABLE on all 810 "
                      "candidates, hack4 sealed empty, the exit pass turned the data gap "
                      "into sells. Named per-name refusal fields + whole-universe refusal "
                      "counts make that starvation visible AT SEAL TIME.",
        "graded_like_a_book": "pending",
    }
    if day is None:
        header.update(status="REFUSED",
                      reasons=["no tracker day file exists at all"],
                      schema={"scorecard_keys": list(SCORECARD_KEYS),
                              "header_keys": list(HEADER_KEYS),
                              "schema_hash": schema_hash()})
        return {"header": header, "scorecards": []}

    if rows is None:
        rows, provenance = S.read_tracker_day(day)
    header["source"] = provenance or {"note": "rows injected directly"}

    # --- the v1 scorer (sealed shadow champion), with its identity in the header
    champ_reasons: list[str] = []
    if champion is None:
        try:
            champion = S.load_champion("shadow")
        except SystemExit as exc:
            champion, champ_reasons = None, [str(exc)]
    if champion is not None and champion.get("schema_hash") != D.schema_hash(shadow_only=True):
        champ_reasons.append(
            f"schema hash mismatch: sealed against {champion.get('schema_hash')}, current "
            f"shadow schema is {D.schema_hash(shadow_only=True)}. Retrain before scoring.")
        champion = None

    header["champion"] = {
        "v2_frozen": {**V2_FROZEN_CHAMPION,
                      "status": "REFUSED_AT_SHADOW_TIME",
                      "reason": "sealed against the FULL panel schema "
                                f"({D.schema_hash(shadow_only=False)}); a tracker day file "
                                "supplies only the SHADOW_MAPPABLE subset"},
        "v1_scorer_in_use": (
            {k: champion.get(k) for k in
             ("kind", "arm", "horizon_months", "schema_hash", "prior_version",
              "model_vintage_sha256_16", "trained_rows", "trained_through_month")}
            if champion is not None else
            {"status": "REFUSED", "reasons": champ_reasons}),
        "prior_version": P.PRIOR_VERSION,
    }
    header["conventions"] = {
        "pit_close": f"{PIT_CLOSE_UTC_HOUR:02d}:00 UTC on the row's own day (16:00 ET "
                     "under EDT; the stricter DST reading, applied year-round)",
        "capacity": CAPACITY_CONVENTION,
        "coverage": "sum(rec_counts) -- a RECOMMENDATION count (IBES numrec analogue); "
                    "never substituted for n_analysts_yf (the numest analogue, ~1.8x)",
        "consensus": "rebuilt from the histogram on the 5=STRONG-BUY scale",
        "unit": "ratio = mean_target / close; upside = ratio - 1",
        "band_status": "the band is an EXCLUSION rule and now a HYGIENE one: on the "
                       "point-in-time panel NO band survives BH-FDR (0 of 32 cells, "
                       "family max p 0.808, min p 0.0517; band_horizon_20260905.json). "
                       "The S36 rationale (only toxic_ge_5 survives FDR, -37.77%/yr) is "
                       "VOID -- it was measured on a split-adjusted numerator over a raw "
                       "close. Admission remains shadow/control; thresholds unchanged "
                       "pending the attended B1 task 5 retirement of learner/prior.py",
    }

    if not rows:
        header.update(status="REFUSED",
                      reasons=[f"tracker day file for {day} is missing or empty"],
                      schema={"scorecard_keys": list(SCORECARD_KEYS),
                              "header_keys": list(HEADER_KEYS),
                              "schema_hash": schema_hash()})
        return {"header": header, "scorecards": []}

    band_map = band_map if band_map is not None else S._band_map()
    df, caveats = S.map_to_features(rows, band_map)
    header["conventions"]["mapping_caveats"] = caveats

    # --- PIT per row, before anything is scored
    obs = [r.get("observed_at") for r in rows]
    pit = [pit_check(day, o) for o in obs]
    pit_ok = np.array([p["status"] == "OK" for p in pit])

    # --- whole-universe refusals, counted where a seal-time reader must see them
    v2_missing = v2_missing_inputs()
    st_missing = state_missing_inputs(df.columns)
    header["whole_universe_refusals"] = {
        "learner_v2": {
            "refused_on": int(len(df)), "of": int(len(df)),
            "missing_inputs": v2_missing,
            "reason": "the frozen champion needs the full panel schema; these columns do "
                      "not exist in a tracker day file"},
        "state": {
            "refused_on": int(len(df)), "of": int(len(df)),
            "missing_inputs": st_missing,
            "reason": f"{len(st_missing)} of {len(ST.STATE_FEATURES)} STATE_FEATURES are "
                      "unmappable from a day file; imputing them and assigning a state "
                      "would be the house failure mode",
            "semantics": STATE_SEMANTICS},
    }

    # --- field readability: the starved-seal sensor
    def _readability(col: str) -> dict:
        if col not in df.columns:
            return {"readable": 0, "unreadable": int(len(df)), "column_absent": True}
        n_ok = int(df[col].notna().sum())
        return {"readable": n_ok, "unreadable": int(len(df) - n_ok), "column_absent": False}

    header["field_readability"] = {
        "days_to_catalyst": _readability("days_to_catalyst"),
        LIQUIDITY_COLUMN: _readability("dollar_vol_20d"),
        "mean_target": _readability("mean_target"),
        "coverage_rec_counts": _readability("coverage"),
        "realised_vol_20d": _readability("vol_20d"),
        "note": "a field unreadable on the WHOLE universe is a data gap, not a market "
                "opinion; tonight's incident is what happens when nothing counts these",
    }

    # --- v1 scoring on PIT-clean rows carrying the core features
    core_ok = pd.Series(True, index=df.index)
    for c in S.CORE_FEATURES:
        core_ok &= df[c].notna() if c in df.columns else False
    core_ok &= pd.Series(pit_ok, index=df.index)

    v1_universe_reasons = list(champ_reasons)
    scores = pd.Series(np.nan, index=df.index)
    if champion is not None:
        cols = list(champion["feature_cols"])
        absent = [c for c in cols if c not in df.columns]
        if absent:
            v1_universe_reasons.append(f"model columns absent from the mapped frame: {absent}")
        elif core_ok.any():
            sub = df[core_ok]
            scores.loc[sub.index] = M.predict_with(
                champion["kind"], champion["model"], champion["arm"], sub, cols,
                champion["horizon_months"])
    v1_unit = M.prediction_unit(champion["kind"]) if champion is not None else None
    is_prob = champion is not None and champion["kind"] == M.CLASSIFIER

    calib = _calibration_reference(v2_receipt if v2_receipt is not None
                                   else _load_v2_receipt(),
                                   champion["kind"] if champion is not None else "none")
    base_rate = calib.get("base_rate")
    bias = calib.get("model_level_bias")

    # --- cross-sectional ranks over the SCORED names, for rank disagreement
    scored_mask = scores.notna()
    prior_rank = df["prior_1m"].where(scored_mask).rank(pct=True)
    score_rank = scores.where(scored_mask).rank(pct=True)

    # --- one scorecard per row
    cards: list[dict] = []
    for i in df.index:
        row = df.loc[i]
        raw = rows[i]
        p = pit[i]
        if p["status"] != "OK":
            ep = {"verdict": "unreadable", "band": "no_opinion",
                  "reasons": [f"PIT refused: {p['reason']}"]}
        else:
            ep = engine_verdict(row.get("ratio"), row.get("close"), row.get("coverage"))
        ep["ratio"] = _r(row.get("ratio"))
        ep["upside"] = _r(row.get("upside"))
        ep["prior_1m"] = _r(row.get("prior_1m")) if p["status"] == "OK" else None

        if p["status"] != "OK":
            v1 = {"status": "REFUSED", "score": None, "unit": v1_unit,
                  "missing_inputs": [], "reasons": ["PIT refused; not scored"]}
        elif v1_universe_reasons:
            v1 = {"status": "REFUSED", "score": None, "unit": v1_unit,
                  "missing_inputs": [],
                  "reasons": ["whole-universe: " + r for r in v1_universe_reasons]}
        elif not core_ok.loc[i]:
            miss = [c for c in S.CORE_FEATURES
                    if c not in df.columns or pd.isna(row.get(c))]
            v1 = {"status": "REFUSED", "score": None, "unit": v1_unit,
                  "missing_inputs": miss,
                  "reasons": [f"core features missing: {miss}"]}
        else:
            v1 = {"status": "OK", "score": _r(scores.loc[i]), "unit": v1_unit,
                  "missing_inputs": [], "reasons": []}

        sc = _f(scores.loc[i])
        if is_prob and sc is not None:
            p_beat = {"status": "OK", "raw": _r(sc),
                      "base_rate": _r(base_rate) if base_rate is not None else None,
                      "vs_base_rate": (_r(sc - base_rate) if base_rate is not None else None),
                      "debiased": (_r(sc - bias) if bias is not None else None),
                      "calibration": calib}
        else:
            p_beat = {"status": "REFUSED", "raw": None, "base_rate": None,
                      "vs_base_rate": None, "debiased": None,
                      "calibration": {"status": "REFUSED",
                                      "reason": "no v1 probability for this name "
                                                "(see learner_v1)"}}

        n_miss_v2 = len(v2_missing)
        card = {
            "symbol": raw.get("symbol"),
            "day": day,
            "observed_at": raw.get("observed_at"),
            "pit": p,
            "identity": {"exchange": raw.get("exchange"),
                         "sector": raw.get("sector"),
                         "tradable": bool(raw.get("tradable", False)),
                         "shortable": bool(raw.get("shortable", False))},
            "engine_prior": ep,
            "learner_v1": v1,
            "learner_v2": {"status": "REFUSED",
                           "champion": V2_FROZEN_CHAMPION["name"],
                           "reason": f"day file cannot supply {n_miss_v2} full-schema "
                                     "columns (named once in "
                                     "header.whole_universe_refusals.learner_v2)"},
            "p_beat": p_beat,
            "state": {"status": "CANNOT_DETERMINE",
                      "reason": f"{len(st_missing)} of {len(ST.STATE_FEATURES)} state "
                                "features unmappable (missing inputs and state "
                                "semantics named once in "
                                "header.whole_universe_refusals.state)",
                      "semantics_receipt": STATES_RECEIPT},
            "disagreement": disagreement_of(
                _stance_of_prior(row.get("prior_1m"),
                                 ep["verdict"]) if p["status"] == "OK" else "none",
                sc, base_rate,
                _f(prior_rank.loc[i]), _f(score_rank.loc[i])),
            "execution": capacity_of(row.get("dollar_vol_20d")),
            "days_to_catalyst": {
                "readable": _f(row.get("days_to_catalyst")) is not None,
                "value": _f(row.get("days_to_catalyst")),
                "units": raw.get("days_to_catalyst_units", "calendar_days")},
        }
        card["falsifiers"] = falsifiers_of(card)
        cards.append(card)

    cards.sort(key=lambda c: (c["symbol"] is None, str(c["symbol"])))

    # --- counts: every headline number the run script prints lives HERE
    by_verdict = {v: 0 for v in ENGINE_VERDICTS}
    by_tier = {t: 0 for t in CAPACITY_TIERS}
    v1_refusal_reasons: dict[str, int] = {}
    n_sign_dis = n_pit_refused = n_v1_ok = 0
    for c in cards:
        by_verdict[c["engine_prior"]["verdict"]] += 1
        by_tier[c["execution"]["tier"]] += 1
        if c["pit"]["status"] != "OK":
            n_pit_refused += 1
        if c["learner_v1"]["status"] == "OK":
            n_v1_ok += 1
        else:
            for r in c["learner_v1"]["reasons"]:
                v1_refusal_reasons[r] = v1_refusal_reasons.get(r, 0) + 1
        if c["disagreement"]["sign_disagreement"]:
            n_sign_dis += 1
    top_refusals = sorted(v1_refusal_reasons.items(), key=lambda kv: -kv[1])[:5]
    header["counts"] = {
        "n_rows": int(len(rows)),
        "n_scorecards": int(len(cards)),
        "pit_refused": n_pit_refused,
        "by_engine_verdict": by_verdict,
        "by_capacity_tier": by_tier,
        "observe_only": int(sum(1 for c in cards if c["execution"]["observe_only"])),
        "v1_scored": n_v1_ok,
        "v1_refused": int(len(cards) - n_v1_ok),
        "v1_top_refusal_reasons": [{"reason": r, "n": n} for r, n in top_refusals],
        "sign_disagreements": n_sign_dis,
        "d_catalyst_unreadable": header["field_readability"]["days_to_catalyst"]["unreadable"],
    }
    header["status"] = "OK"
    header["schema"] = {"scorecard_keys": list(SCORECARD_KEYS),
                        "header_keys": list(HEADER_KEYS),
                        "schema_hash": schema_hash()}
    return {"header": header, "scorecards": cards}


# ----------------------------------------------------------------- writing

def write_potential_universe(pu: dict, out_dir: Path | None = None) -> Path:
    """JSONL: header first line, then one scorecard per line, sorted by symbol.
    JSONL rather than one JSON object because a real day is ~3k scorecards
    (a few MB) and a consumer should be able to stream it."""
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    day = pu["header"].get("day") or "unknown-day"
    path = out_dir / f"{day}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(pu["header"], default=str) + "\n")
        for card in pu["scorecards"]:
            fh.write(json.dumps(card, default=str) + "\n")
    return path


def read_potential_universe(path: Path) -> dict:
    """Round-trip reader, so the grader and the tests share one parser."""
    with Path(path).open("r", encoding="utf-8") as fh:
        header = json.loads(fh.readline())
        cards = [json.loads(line) for line in fh if line.strip()]
    return {"header": header, "scorecards": cards}


__all__ = [
    "CODE_VERSION", "V2_FROZEN_CHAMPION", "STATE_SEMANTICS",
    "OBSERVE_FLOOR_USD", "EXECUTE_FLOOR_USD", "MAX_ADV_PARTICIPATION",
    "CAPACITY_CONVENTION", "LIQUIDITY_COLUMN", "PIT_CLOSE_UTC_HOUR",
    "ENGINE_VERDICTS", "CAPACITY_TIERS", "SCORECARD_KEYS", "HEADER_KEYS",
    "schema_hash", "pit_check", "v2_missing_inputs", "state_missing_inputs",
    "capacity_of", "engine_verdict", "disagreement_of", "falsifiers_of",
    "build_potential_universe", "write_potential_universe",
    "read_potential_universe", "OUT_DIR",
]
