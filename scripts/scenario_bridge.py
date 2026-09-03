"""SCENARIO BRIDGE -- the LLM proposes, code retrieves, REALITY grades.

    python -m scripts.scenario_bridge --write-schema
    python -m scripts.scenario_bridge --generate 20          # costs money
    python -m scripts.scenario_bridge --generate 20 --second-opinion 10
    python -m scripts.scenario_bridge_grade                  # retrieve + grade

WHAT THIS IS
============
A language model invents STRUCTURED CAUSAL SCENARIOS -- "a capacity bottleneck
at an incumbent supplier, after a deep drawdown, while analysts are cutting
targets, held six months". Code then goes and finds the REAL company-months in
the 2013-2024 point-in-time panel that actually looked like that, plus matched
controls that looked like everything else about them EXCEPT the scenario's
distinguishing configuration, and grades both with the returns that actually
happened.

THE THREE RULES THIS FILE EXISTS TO ENFORCE
===========================================
1. **The LLM never labels its own hypothesis correct.** Nothing in the grading
   path reads the model's `direction` except to decide the SIGN of a spread that
   was computed from realised returns. The model cannot move the number.
2. **A synthetic scenario NEVER gets a synthetic return.** There is no code path
   in this file that attaches an outcome to a scenario that was not measured on
   a real (permno, month). If a scenario matches nothing, it is reported as
   matching nothing. An invented return would inject fiction straight into the
   alpha target, which is the one failure that cannot be undone downstream.
3. **The unmappable rate is a DELIVERABLE, not an embarrassment.** Most of what
   an LLM says about the world -- demand, supply, capacity, who the actors are
   -- has no column in this panel. Counting exactly which concepts fall through
   is how the next data acquisition gets chosen. See `FIELD_MAP`.

NO NUMBER APPEARS IN THE PROMPT
===============================
House rule, paid for on 2026-08-30: telling a model "move p_up by at most 0.10"
made eleven of thirteen answers come back at exactly 0.100, while the same bound
applied in CODE produced a mean move of 0.024. **A bound the model can see is an
anchor.** So the scenario vocabulary is ORDINAL WORDS -- `deep_drawdown`,
`neglected`, `targets_cut` -- and every quantile that turns a word into a filter
lives in `_BANDS` in this file, where the model cannot read it.

WHAT "MAPPED" MEANS, AND THE THREE GRADES OF IT
===============================================
`FIELD_MAP` grades every schema field:

    DIRECT      the panel has the quantity itself (drawdown, momentum, revisions)
    PROXY       the panel has a stand-in, named as one (analyst coverage rank
                standing in for "attention"; a 13F event aggregate standing in
                for "holder action")
    COARSE      the panel has a much blunter version (SIC division standing in
                for a sector THEME -- "semiconductor capex" and "furniture" are
                both `Manufacturing`)
    UNMAPPABLE  nothing in the panel answers it

A PROXY is not a mapping and this file never counts it as one in the headline
rate. The honest sentence is "N of M fields are DIRECT".

A SECTOR LABEL THAT MEANS "WE DON'T KNOW"
=========================================
`tracker_ibes_backtest.SIC_DIVISIONS` sends SIC 9000-9999 to
"Public Administration". In CRSP that range is **98.8% code 9999 =
NONCLASSIFIABLE ESTABLISHMENTS** (3,580 of 3,625 name-rows, measured here), so
the panel's second-largest "sector" -- 99,334 of 441,278 rows, 22.5% -- is a
label for absence of information. It is renamed `_UNCLASSIFIED_SIC9999` on the
way in, a scenario is never allowed to map ONTO it, and it still works as a
matching stratum (unknowns are compared with unknowns).

COSTS ARE NEVER OMITTED
=======================
`train_table` targets are GROSS excess returns. Every spread this file reports
carries both a gross line and a net line at a NAMED round-trip rate
(`COST_BPS_ROUND_TRIP_PER_LEG`), charged once per leg because a treated-minus-
control spread is a two-legged position if it is ever traded. Quote the rate or
don't quote the number.

LICENCE: PRODUCT_EXPERIMENT. This is exploration -- post-hoc, many variants, no
significance gate and no multiplicity control. It may NOT be quoted as a
RESEARCH_CLAIM. The paired statistics are printed so the reader can see how thin
the evidence is, not so a p-value can be harvested from twenty scenarios.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "backend" / "data" / "optimus" / "scenario_bridge"
SCHEMA_PATH = OUT_DIR / "schema.json"
HOLDER_CACHE = OUT_DIR / "holder_action_quarterly.parquet"
RECEIPT_PATH = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
                / "scenario_bridge_20260903.json")

TRAIN_TABLE = REPO / "backend" / "data" / "optimus" / "learner" / "train_table.parquet"
HOLDER_EVENTS = REPO / "backend" / "data" / "optimus" / "wrds" / "holder_events"

SCHEMA_VERSION = "scenario-bridge-1"
RUN_TAG = "20260903"

#: One side, in basis points. The house's own figure from
#: `docs`/commit "the thin-coverage edge survives 25bps". A treated-minus-control
#: spread is two legs, so the spread pays this TWICE.
COST_BPS_ROUND_TRIP_PER_LEG = 25.0

#: The label CRSP's 9999 "nonclassifiable" gets renamed to. See module docstring.
UNCLASSIFIED_SECTOR = "_UNCLASSIFIED_SIC9999"

#: 13F quarter indexing, imported in spirit from `scripts/holder_fingerprint.py`
#: (qidx 0 == 1995Q1) and the statutory 45-day filing deadline it applies.
Q0_YEAR = 1995
FILING_LAG_DAYS = 45


# ============================================================ the schema

#: Every value the model is allowed to emit. ORDINAL WORDS ONLY -- see the
#: module docstring on why no number may appear in a prompt.
ENUMS: dict[str, tuple[str, ...]] = {
    "event_type": (
        "capacity_bottleneck", "input_substitution", "regulatory_shift",
        "customer_switch", "input_cost_shock", "installed_base_obsolescence",
        "channel_disruption", "new_entrant_price_war", "demand_pull_forward",
        "supply_chain_relocation", "exclusivity_expiry", "labour_constraint",
        "energy_cost_step", "currency_competitiveness", "liability_shock",
        "standards_replacement_cycle", "consolidation", "preference_shift",
        "credit_tightening", "physical_supply_disruption", "other",
    ),
    "company_role": (
        "incumbent_supplier", "new_entrant", "customer", "substitute_provider",
        "bottleneck_holder", "commodity_producer", "distributor",
        "service_provider", "unaffected_peer",
    ),
    "demand_change": ("surge", "rising", "flat", "falling", "collapse", "unknown"),
    "supply_change": ("surge", "rising", "flat", "falling", "collapse", "unknown"),
    "capacity_constraint": ("binding", "tightening", "loosening", "none", "unknown"),
    "holder_action": (
        "institutional_accumulation", "institutional_distribution",
        "activist_stake", "insider_buying", "insider_selling", "none", "unknown",
    ),
    "analyst_change": (
        "targets_raised", "targets_cut", "upgrades", "downgrades",
        "coverage_initiated", "coverage_dropped", "none", "unknown",
    ),
    "drawdown_state": (
        "at_highs", "mild_pullback", "deep_drawdown", "near_lows", "unknown",
    ),
    "momentum_12_1_sign": ("positive", "negative", "unknown"),
    "attention_state": ("spiking", "elevated", "normal", "neglected", "unknown"),
    "expected_horizon_months": ("1", "3", "6", "12"),
    "direction": ("long", "short"),
    #: The ten SIC divisions, MINUS "Public Administration" -- a scenario may
    #: never map onto the label that means "CRSP did not classify this".
    "sic_division_hint": (
        "Agriculture", "Mining", "Construction", "Manufacturing",
        "Transport & Utilities", "Wholesale", "Retail",
        "Finance & Real Estate", "Services",
    ),
}

#: (field, required, kind). `kind` is "enum", "str", "list[str]" or "nested".
_FIELDS: tuple[tuple[str, bool, str], ...] = (
    ("scenario_id", True, "str"),
    ("event_type", True, "enum"),
    ("actors", True, "list[str]"),
    ("company_role", True, "enum"),
    ("sector_theme", True, "str"),
    ("sic_division_hint", True, "enum"),
    ("demand_change", True, "enum"),
    ("supply_change", True, "enum"),
    ("capacity_constraint", True, "enum"),
    ("holder_action", True, "enum"),
    ("analyst_change", True, "enum"),
    ("price_state", True, "nested"),
    ("attention_state", True, "enum"),
    ("expected_horizon_months", True, "enum"),
    ("direction", True, "enum"),
    ("falsifier", True, "str"),
    ("mechanism", False, "str"),
)

_PRICE_STATE_FIELDS = ("drawdown_state", "momentum_12_1_sign")


def scenario_schema() -> dict:
    """The persisted contract. Written to `schema.json`; read by the test."""
    return {
        "schema_version": SCHEMA_VERSION,
        "licence": "PRODUCT_EXPERIMENT",
        "purpose": (
            "A structured causal scenario an LLM may invent. It carries NO "
            "prices, NO returns, NO dates and NO company names -- only causal "
            "structure and observable state. Outcomes are attached ONLY by "
            "retrieving real (permno, month) rows from the point-in-time panel."),
        "prompt_rule": (
            "No number may appear in the prompt that generates one of these. "
            "Every quantile that turns an ordinal word into a filter lives in "
            "scripts/scenario_bridge._BANDS, which the model never sees. "
            "A bound the model can see is an anchor (house rule, 2026-08-30)."),
        "fields": [
            {"name": n, "required": r, "kind": k,
             "values": list(ENUMS[n]) if k == "enum" else None}
            for n, r, k in _FIELDS
        ],
        "price_state": {
            "drawdown_state": list(ENUMS["drawdown_state"]),
            "momentum_12_1_sign": list(ENUMS["momentum_12_1_sign"]),
        },
        "field_map": {k: dict(v) for k, v in FIELD_MAP_DOC.items()},
        "retrieval_bands": {
            "note": ("The quantile cut-points that turn each ordinal word into a "
                     "panel predicate. Recorded so the receipt is reproducible; "
                     "NEVER placed in a prompt."),
            "bands": _BANDS_DOC(),
        },
        "cost_convention": {
            "bps_round_trip_per_leg": COST_BPS_ROUND_TRIP_PER_LEG,
            "legs_charged": 2,
            "why": ("a treated-minus-control spread is a two-legged position if "
                    "it is ever traded; the panel's targets are gross"),
        },
    }


def validate_scenario(obj: Any) -> tuple[bool, list[str]]:
    """(ok, errors). Strict: an unknown enum value is an ERROR, not a coercion.

    A model that answers `"demand_change": "increasing"` when the contract says
    `rising` has not answered the contract, and silently mapping it to the
    nearest legal value is how a schema stops being one.
    """
    errs: list[str] = []
    if not isinstance(obj, dict):
        return False, ["not a JSON object"]
    for name, required, kind in _FIELDS:
        if name not in obj or obj[name] is None:
            if required:
                errs.append(f"missing required field {name!r}")
            continue
        v = obj[name]
        if kind == "enum":
            if not isinstance(v, str) or v not in ENUMS[name]:
                errs.append(f"{name}={v!r} not in {ENUMS[name]}")
        elif kind == "str":
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{name} must be a non-empty string")
        elif kind == "list[str]":
            if (not isinstance(v, list) or not v
                    or not all(isinstance(x, str) and x.strip() for x in v)):
                errs.append(f"{name} must be a non-empty list of strings")
        elif kind == "nested":
            if not isinstance(v, dict):
                errs.append(f"{name} must be an object")
                continue
            for sub in _PRICE_STATE_FIELDS:
                sv = v.get(sub)
                if not isinstance(sv, str) or sv not in ENUMS[sub]:
                    errs.append(f"price_state.{sub}={sv!r} not in {ENUMS[sub]}")
    return (not errs), errs


# =================================================== the mapping (the deliverable)

#: What each schema field can and cannot become in the 2013-2024 IBES+CRSP panel.
#: `grade` is one of DIRECT / PROXY / COARSE / UNMAPPABLE. The headline
#: "mappable-field rate" counts DIRECT only; PROXY and COARSE are reported
#: separately and never folded in.
FIELD_MAP_DOC: dict[str, dict[str, str]] = {
    "price_state.drawdown_state": {
        "grade": "DIRECT", "panel": "drawdown_60d__xs (within-month percentile)",
        "note": "the panel holds the quantity itself"},
    "price_state.momentum_12_1_sign": {
        "grade": "DIRECT", "panel": "sign(mom_12_1)",
        "note": "the house's own 12-1 definition"},
    "analyst_change": {
        "grade": "DIRECT",
        "panel": "target_rev_1m__xs / net_rev_4w__xs / coverage_rev_1m",
        "note": "IBES revisions and coverage changes are in the panel"},
    "expected_horizon_months": {
        "grade": "DIRECT", "panel": "selects excess_vw_{h}m",
        "note": "a control on the grading, not a retrieval filter"},
    "direction": {
        "grade": "DIRECT", "panel": "sign applied to the realised spread",
        "note": "the ONLY place the model's opinion touches the number, and it "
                "only flips a sign computed from real returns"},
    "sic_division_hint": {
        "grade": "COARSE", "panel": "sector (10 SIC divisions)",
        "note": "'semiconductor capex cycle' and 'office furniture' are both "
                "Manufacturing; a sector THEME does not survive this"},
    "attention_state": {
        "grade": "PROXY", "panel": "coverage__xs (analyst coverage percentile)",
        "note": "analyst attention stands in for attention. No news counts, no "
                "search volume, no filing counts exist before 2026-08-30 "
                "(learner/dataset.company_state_schema)"},
    "holder_action": {
        "grade": "PROXY",
        "panel": "13F holder_events aggregate, quarterly, +45d filing lag",
        "note": "NEW_POSITION+LARGE_ADD minus LARGE_TRIM+COMPLETE_EXIT, ranked "
                "within month. Covers accumulation/distribution ONLY: "
                "activist_stake, insider_buying and insider_selling are "
                "UNMAPPABLE (no 13D/G, no Form 4)"},
    "event_type": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "no dated event tape covers 2013-2024 in this repo"},
    "actors": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "no entity graph links a named actor to a permno"},
    "company_role": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "supplier / customer / substitute is a SUPPLY-CHAIN RELATION; "
                "the panel has no customer-supplier edges"},
    "demand_change": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "needs revenue/unit fundamentals (Compustat fundq is on disk "
                "but is NOT joined to permno here)"},
    "supply_change": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "needs industry capacity/utilisation series"},
    "capacity_constraint": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "needs utilisation, backlog or lead-time data"},
    "sector_theme": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "the free-text theme itself; only its division hint maps"},
    "falsifier": {
        "grade": "UNMAPPABLE", "panel": "-",
        "note": "not a retrieval field -- it is what a future test would look "
                "for, recorded so the scenario is refutable at all"},
}

#: Fields that participate in RETRIEVAL at all (falsifier/scenario_id/mechanism
#: are excluded: they are prose, not state).
RETRIEVAL_FIELDS: tuple[str, ...] = tuple(
    k for k in FIELD_MAP_DOC if k != "falsifier")


def mappability_summary() -> dict:
    grades = [FIELD_MAP_DOC[f]["grade"] for f in RETRIEVAL_FIELDS]
    n = len(grades)
    return {
        "retrieval_fields": n,
        "direct": grades.count("DIRECT"),
        "proxy": grades.count("PROXY"),
        "coarse": grades.count("COARSE"),
        "unmappable": grades.count("UNMAPPABLE"),
        "direct_rate": round(grades.count("DIRECT") / n, 4),
        "any_mapping_rate": round(
            (n - grades.count("UNMAPPABLE")) / n, 4),
        "headline": (
            f"{grades.count('DIRECT')} of {n} retrieval fields map DIRECTLY; "
            f"{grades.count('PROXY')} map through a NAMED PROXY, "
            f"{grades.count('COARSE')} only coarsely, "
            f"{grades.count('UNMAPPABLE')} not at all."),
    }


# ---------------------------------------------------- word -> quantile bands
#
# THE NUMBERS LIVE HERE AND NOWHERE THE MODEL CAN SEE THEM.
# `__xs` columns are within-month percentile ranks in [0, 1].

_BANDS: dict[str, dict[str, tuple[float, float]]] = {
    "drawdown_state": {
        # drawdown_60d is <= 0; a HIGH percentile means a SMALL drawdown.
        "at_highs": (0.80, 1.01),
        "mild_pullback": (0.40, 0.80),
        "deep_drawdown": (0.10, 0.40),
        "near_lows": (-0.01, 0.10),
    },
    "attention_state": {
        "spiking": (0.85, 1.01),
        "elevated": (0.70, 1.01),
        "normal": (0.30, 0.70),
        "neglected": (-0.01, 0.30),
    },
    "analyst_change": {
        "targets_raised": (0.70, 1.01),
        "targets_cut": (-0.01, 0.30),
        "upgrades": (0.70, 1.01),
        "downgrades": (-0.01, 0.30),
    },
    "holder_action": {
        "institutional_accumulation": (0.70, 1.01),
        "institutional_distribution": (-0.01, 0.30),
    },
}

#: Grading refuses below these. A spread over eleven months is not a finding,
#: and a cell of forty rows spread over a decade is a gallery, not a sample.
MIN_TREATED_ROWS = 100
MIN_MONTH_BLOCKS = 24
#: A stratum needs this many controls before its difference means anything.
MIN_CONTROLS_PER_STRATUM = 3


def _BANDS_DOC() -> dict:
    return {k: {kk: list(vv) for kk, vv in v.items()} for k, v in _BANDS.items()}


# ======================================================== the panel

_PANEL_COLS = [
    "permno", "month", "vintage", "sector", "band", "close", "ratio",
    "coverage", "numest",
    "drawdown_60d__xs", "mom_12_1", "vol_20d__xs", "ratio__xs",
    "log_market_cap__xs", "log_dollar_vol_20d__xs", "coverage__xs",
    "net_rev_4w__xs", "target_rev_1m__xs", "coverage_rev_1m",
    "excess_vw_1m", "excess_vw_3m", "excess_vw_6m", "excess_vw_12m",
]

HORIZONS = (1, 3, 6, 12)


def quarter_end(qidx: int) -> date:
    y = Q0_YEAR + qidx // 4
    q = qidx % 4 + 1
    m = q * 3
    last = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        last = 29
    return date(y, m, last)


def public_date_of(qidx: int) -> date:
    """The statutory 13F deadline. Anything earlier would be look-ahead."""
    return quarter_end(qidx) + timedelta(days=FILING_LAG_DAYS)


def build_holder_action(force: bool = False) -> pd.DataFrame:
    """(permno, qidx, public_date, holder_net) from the 13F event files.

    `holder_net` = (NEW_POSITION + LARGE_ADD) - (LARGE_TRIM + COMPLETE_EXIT),
    a manager COUNT, not a dollar figure -- 74.7M position-quarters said
    identity is thin and stake size is adverse, so the count is the honest
    aggregate to carry here.

    REFUSES to invent: a permno-quarter with no filing row is ABSENT, never
    zero. Absent means "no 13F manager reported a material change", which is a
    different statement from "the net was zero", and only the first is true.
    """
    if HOLDER_CACHE.exists() and not force:
        return pd.read_parquet(HOLDER_CACHE)
    if not HOLDER_EVENTS.exists():
        raise SystemExit(
            f"REFUSED: {HOLDER_EVENTS} does not exist, so `holder_action` cannot "
            "be mapped at all. It must be reported UNMAPPABLE rather than "
            "silently dropped from the conjunction -- a filter that vanishes "
            "makes every scenario look better matched than it is.")
    frames = []
    for f in sorted(HOLDER_EVENTS.glob("q*.parquet")):
        q = int(f.stem[1:])
        if q < 72 or q > 119:            # 2013Q1 .. 2024Q4
            continue
        d = pd.read_parquet(f, columns=["permno", "qidx", "etype"])
        # 0 NEW_POSITION, 1 LARGE_ADD, 2 LARGE_TRIM, 3 COMPLETE_EXIT
        d["_in"] = d["etype"].isin((0, 1)).astype("int32")
        d["_out"] = d["etype"].isin((2, 3)).astype("int32")
        g = d.groupby(["permno", "qidx"], as_index=False)[["_in", "_out"]].sum()
        frames.append(g)
    if not frames:
        raise SystemExit("REFUSED: no 13F event quarters inside 2013-2024.")
    out = pd.concat(frames, ignore_index=True)
    out["holder_net"] = out["_in"] - out["_out"]
    out["holder_events"] = out["_in"] + out["_out"]
    out["public_date"] = pd.to_datetime(
        [public_date_of(int(q)) for q in out["qidx"]])
    out = out[["permno", "qidx", "public_date", "holder_net", "holder_events"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(HOLDER_CACHE, index=False)
    return out


def load_panel(with_holders: bool = True) -> tuple[pd.DataFrame, dict]:
    """The retrieval panel + a provenance receipt. READ-ONLY on learner/*."""
    if not TRAIN_TABLE.exists():
        raise SystemExit(
            f"REFUSED: {TRAIN_TABLE} is absent. Build it with the learner "
            "before running the bridge -- an empty panel would report every "
            "scenario as 'no analogue found', which reads as a finding and is "
            "an absent file.")
    p = pd.read_parquet(TRAIN_TABLE, columns=_PANEL_COLS)
    prov: dict = {"train_table": str(TRAIN_TABLE), "rows_raw": int(len(p))}

    # The label that means "CRSP did not classify this". See module docstring.
    n_pa = int((p["sector"] == "Public Administration").sum())
    p["sector"] = p["sector"].replace(
        {"Public Administration": UNCLASSIFIED_SECTOR,
         "_UNKNOWN": UNCLASSIFIED_SECTOR})
    prov["sector_relabel"] = {
        "from": ["Public Administration", "_UNKNOWN"],
        "to": UNCLASSIFIED_SECTOR, "rows": n_pa,
        "evidence": ("3,580 of 3,625 CRSP name-rows in SIC 9000-9999 are code "
                     "9999 = NONCLASSIFIABLE ESTABLISHMENTS (98.8%)"),
    }

    # Matching strata. Terciles WITHIN MONTH so the stratum means the same thing
    # in 2013 and 2024 -- a raw cap cut-off would drift a decade of inflation
    # into the definition of "small".
    for src, dst in (("log_market_cap__xs", "size_tercile"),
                     ("log_dollar_vol_20d__xs", "liq_tercile")):
        v = p[src]
        p[dst] = np.where(v.isna(), -1, np.where(v < 1 / 3, 0, np.where(v < 2 / 3, 1, 2)))
        p[dst] = p[dst].astype("int8")

    if with_holders:
        h = build_holder_action()
        # PIT: the latest 13F quarter whose STATUTORY DEADLINE has passed by the
        # row's vintage. merge_asof on public_date, never on quarter_end.
        left = p[["permno", "vintage"]].copy()
        left["permno"] = left["permno"].astype("int64")
        left["_i"] = np.arange(len(left))
        left = left.sort_values("vintage")
        right = h.copy()
        right["permno"] = right["permno"].astype("int64")
        right = right.sort_values("public_date")
        m = pd.merge_asof(left, right, left_on="vintage", right_on="public_date",
                          by="permno", direction="backward")
        m = m.sort_values("_i")
        p["holder_net"] = m["holder_net"].to_numpy()
        p["holder_qidx"] = m["qidx"].to_numpy()
        # Within-month percentile of the net count. NaN stays NaN: a name with
        # no 13F row is not "average", it is unobserved.
        p["holder_net__xs"] = p.groupby("month")["holder_net"].rank(pct=True)
        prov["holder_action"] = {
            "source": str(HOLDER_EVENTS),
            "rows_with_holder_row": int(p["holder_net"].notna().sum()),
            "coverage": round(float(p["holder_net"].notna().mean()), 4),
            "pit_rule": "merge_asof backward on quarter_end + 45 days",
        }
    else:
        p["holder_net"] = np.nan
        p["holder_net__xs"] = np.nan
        prov["holder_action"] = {"source": None, "coverage": 0.0}

    prov["rows"] = int(len(p))
    prov["months"] = int(p["month"].nunique())
    prov["names"] = int(p["permno"].nunique())
    prov["window"] = [str(p["month"].min()), str(p["month"].max())]
    return p, prov


# ======================================================== the retriever

def _band_mask(col: pd.Series, lo: float, hi: float) -> np.ndarray:
    v = col.to_numpy(dtype="float64")
    return (v >= lo) & (v < hi)


#: BACK-OFF ORDER, declared once. A five-way conjunction of quantile bands cuts
#: a sector down to a few dozen name-months, and a grade computed there is a
#: number without a sample. So when the floor is not met the LEAST CENTRAL
#: predicate is dropped and the attempt repeated, and the receipt says exactly
#: which concepts had to go. The order runs PROXIES first (they were never the
#: quantity anyway) and the price state last (it is the only DIRECT observable
#: most scenarios carry).
#:
#: This is a relaxation, not a rescue: a spread found at level 3 is a spread
#: about a DIFFERENT, weaker configuration than the one the model proposed, and
#: `predicates_dropped` on every row is what stops the two being confused.
BACKOFF_ORDER: tuple[str, ...] = (
    "attention_state",                    # PROXY
    "holder_action",                      # PROXY
    "price_state.momentum_12_1_sign",
    "analyst_change",
    "price_state.drawdown_state",
)


def scenario_predicates(s: dict, drop: Iterable[str] = ()) -> tuple[dict, dict]:
    """Which schema fields became a predicate, and which fell through.

    Returns (builders, report). `builders` maps a field name to a callable
    taking the panel and returning a boolean mask. `drop` names predicates the
    back-off has removed; they are reported as DROPPED, never silently absent --
    a filter that vanishes makes a scenario look better matched than it is.
    """
    used: dict[str, str] = {}
    skipped: dict[str, str] = {}
    unmappable: list[str] = []
    builders: dict[str, Callable[[pd.DataFrame], np.ndarray]] = {}

    ps = s.get("price_state") or {}

    dd = ps.get("drawdown_state", "unknown")
    if dd in _BANDS["drawdown_state"]:
        lo, hi = _BANDS["drawdown_state"][dd]
        builders["price_state.drawdown_state"] = (
            lambda p, lo=lo, hi=hi: _band_mask(p["drawdown_60d__xs"], lo, hi))
        used["price_state.drawdown_state"] = f"drawdown_60d__xs in [{lo},{hi})"
    else:
        skipped["price_state.drawdown_state"] = f"value {dd!r} carries no filter"

    mom = ps.get("momentum_12_1_sign", "unknown")
    if mom == "positive":
        builders["price_state.momentum_12_1_sign"] = (
            lambda p: p["mom_12_1"].to_numpy() > 0)
        used["price_state.momentum_12_1_sign"] = "mom_12_1 > 0"
    elif mom == "negative":
        builders["price_state.momentum_12_1_sign"] = (
            lambda p: p["mom_12_1"].to_numpy() < 0)
        used["price_state.momentum_12_1_sign"] = "mom_12_1 < 0"
    else:
        skipped["price_state.momentum_12_1_sign"] = "unknown"

    ac = s.get("analyst_change", "unknown")
    _AC_COL = {"targets_raised": "target_rev_1m__xs", "targets_cut": "target_rev_1m__xs",
               "upgrades": "net_rev_4w__xs", "downgrades": "net_rev_4w__xs"}
    if ac in _AC_COL:
        lo, hi = _BANDS["analyst_change"][ac]
        col = _AC_COL[ac]
        builders["analyst_change"] = (
            lambda p, c=col, lo=lo, hi=hi: _band_mask(p[c], lo, hi))
        used["analyst_change"] = f"{col} in [{lo},{hi})"
    elif ac == "coverage_initiated":
        builders["analyst_change"] = lambda p: p["coverage_rev_1m"].to_numpy() > 0
        used["analyst_change"] = "coverage_rev_1m > 0"
    elif ac == "coverage_dropped":
        builders["analyst_change"] = lambda p: p["coverage_rev_1m"].to_numpy() < 0
        used["analyst_change"] = "coverage_rev_1m < 0"
    else:
        skipped["analyst_change"] = f"value {ac!r} carries no filter"

    at = s.get("attention_state", "unknown")
    if at in _BANDS["attention_state"]:
        lo, hi = _BANDS["attention_state"][at]
        builders["attention_state"] = (
            lambda p, lo=lo, hi=hi: _band_mask(p["coverage__xs"], lo, hi))
        used["attention_state"] = f"PROXY coverage__xs in [{lo},{hi})"
    else:
        skipped["attention_state"] = "unknown"

    ha = s.get("holder_action", "unknown")
    if ha in _BANDS["holder_action"]:
        lo, hi = _BANDS["holder_action"][ha]
        builders["holder_action"] = (
            lambda p, lo=lo, hi=hi: _band_mask(p["holder_net__xs"], lo, hi))
        used["holder_action"] = f"PROXY holder_net__xs in [{lo},{hi})"
    elif ha in ("activist_stake", "insider_buying", "insider_selling"):
        unmappable.append(f"holder_action={ha}")
        skipped["holder_action"] = (
            f"{ha} needs 13D/G or Form 4; neither is in the panel")
    else:
        skipped["holder_action"] = f"value {ha!r} carries no filter"

    # The sector hint is a STRATUM, not a treatment: it narrows the universe the
    # comparison runs inside, so it is applied to treated AND control alike.
    for f in RETRIEVAL_FIELDS:
        if FIELD_MAP_DOC[f]["grade"] == "UNMAPPABLE":
            unmappable.append(f)

    dropped = {}
    for f in drop:
        if f in builders:
            dropped[f] = used.pop(f, None)
            builders.pop(f)

    report = {
        "predicates_used": used,
        "predicates_dropped_by_backoff": dropped,
        "fields_present_but_no_filter": skipped,
        "unmappable_fields": sorted(set(unmappable)),
        "n_predicates": len(builders),
    }
    return builders, report


def treated_mask(panel: pd.DataFrame, s: dict,
                 drop: Iterable[str] = ()) -> tuple[np.ndarray, dict]:
    builders, report = scenario_predicates(s, drop=drop)
    m = np.ones(len(panel), dtype=bool)
    for fn in builders.values():
        m &= fn(panel)
    return m, report


def universe_mask(panel: pd.DataFrame, s: dict) -> tuple[np.ndarray, dict]:
    """The sector slice the comparison lives in (stratum, applied to both sides)."""
    hint = s.get("sic_division_hint")
    if hint in ENUMS["sic_division_hint"]:
        return (panel["sector"] == hint).to_numpy(), {
            "sector_stratum": hint, "grade": "COARSE"}
    return np.ones(len(panel), dtype=bool), {
        "sector_stratum": None,
        "grade": "COARSE",
        "why": f"sic_division_hint={hint!r} is not one of the nine usable divisions "
               f"(Public Administration is excluded: it means SIC 9999 unclassified)"}


def retrieve(panel: pd.DataFrame, s: dict, k: int = 20,
             drop: Iterable[str] = ()) -> dict:
    """Treated rows, matched controls, K nearest exemplars, and matched losers.

    The control set is the SAME (month x sector x size tercile x liquidity
    tercile) strata as the treated rows, MINUS the treated configuration. That
    is the whole point: a control that differs in era, sector, size or liquidity
    is not a control, it is a different question.
    """
    uni, uni_rep = universe_mask(panel, s)
    treat, pred_rep = treated_mask(panel, s, drop=drop)
    treat = treat & uni
    if pred_rep["n_predicates"] == 0:
        # Nothing separates treated from control, so every control is a treated
        # row and the difference is zero BY CONSTRUCTION. Reporting 0.000 here
        # would be the worst kind of number: arithmetically correct and about
        # nothing. The scenario named no observable state this panel holds.
        return {"scenario_id": s.get("scenario_id"), "universe": uni_rep,
                "mapping": pred_rep, "n_universe": int(uni.sum()),
                "n_treated": 0, "backoff_level": len(tuple(drop)),
                "backoff_dropped": list(drop), "status": "NO_OBSERVABLE_STATE",
                "note": ("the scenario carries no field this panel can turn into "
                         "a filter, so there is no configuration to retrieve")}

    idx_t = np.flatnonzero(treat)
    out: dict = {
        "scenario_id": s.get("scenario_id"),
        "universe": uni_rep,
        "mapping": pred_rep,
        "n_universe": int(uni.sum()),
        "n_treated": int(len(idx_t)),
        "backoff_level": len(tuple(drop)),
        "backoff_dropped": list(drop),
    }
    if len(idx_t) == 0:
        out["status"] = "NO_ANALOGUE"
        out["note"] = ("no real company-month in 2013-2024 satisfied this "
                       "configuration. That is a finding about the scenario, "
                       "not a zero.")
        return out

    t = panel.iloc[idx_t]
    strata_cols = ["month", "sector", "size_tercile", "liq_tercile"]
    t_keys = set(map(tuple, t[strata_cols].itertuples(index=False, name=None)))

    # Controls: inside the universe, inside a stratum that actually contains a
    # treated row, and NOT treated.
    cand = np.flatnonzero(uni & ~treat)
    c = panel.iloc[cand]
    ckeys = list(map(tuple, c[strata_cols].itertuples(index=False, name=None)))
    keep = np.fromiter((kk in t_keys for kk in ckeys), dtype=bool, count=len(ckeys))
    idx_c = cand[keep]

    out["n_control"] = int(len(idx_c))
    out["n_strata"] = len(t_keys)
    out["n_month_blocks"] = int(t["month"].nunique())
    out["treated_index"] = idx_t
    out["control_index"] = idx_c
    out["status"] = "RETRIEVED"

    # ---- K nearest exemplars: closest to the CENTRE of every banded predicate.
    h = int(s.get("expected_horizon_months", "3"))
    tgt = f"excess_vw_{h}m"
    centre: dict[str, float] = {}
    ps = s.get("price_state") or {}
    if (ps.get("drawdown_state") in _BANDS["drawdown_state"]):
        lo, hi = _BANDS["drawdown_state"][ps["drawdown_state"]]
        centre["drawdown_60d__xs"] = (max(lo, 0.0) + min(hi, 1.0)) / 2
    if s.get("attention_state") in _BANDS["attention_state"]:
        lo, hi = _BANDS["attention_state"][s["attention_state"]]
        centre["coverage__xs"] = (max(lo, 0.0) + min(hi, 1.0)) / 2
    if s.get("holder_action") in _BANDS["holder_action"]:
        lo, hi = _BANDS["holder_action"][s["holder_action"]]
        centre["holder_net__xs"] = (max(lo, 0.0) + min(hi, 1.0)) / 2
    if centre:
        d = np.zeros(len(t))
        for col, mid in centre.items():
            v = t[col].to_numpy(dtype="float64")
            d += np.where(np.isnan(v), 1.0, (v - mid) ** 2)
        order = np.argsort(d)
    else:
        # No banded predicate: order by month so the exemplars span the window
        # rather than clustering wherever the frame happens to start.
        order = np.argsort(t["month"].to_numpy().astype(str))
    ex = t.iloc[order[:k]]
    out["exemplars"] = [
        {"permno": int(r.permno), "month": str(r.month), "sector": str(r.sector),
         "drawdown_xs": _f(r.drawdown_60d__xs), "coverage_xs": _f(r.coverage__xs),
         "holder_net_xs": _f(r.holder_net__xs),
         f"excess_vw_{h}m": _f(getattr(r, tgt))}
        for r in ex.itertuples(index=False)
    ]

    # ---- MATCHED LOSERS. Study losers as hard as winners: inside the treated
    # cell, what separated the worst quartile from the best?
    y = t[tgt].to_numpy(dtype="float64")
    ok = np.isfinite(y)
    if ok.sum() >= 40:
        q1, q3 = np.nanquantile(y[ok], [0.25, 0.75])
        lo_m, hi_m = ok & (y <= q1), ok & (y >= q3)
        feats = ["drawdown_60d__xs", "coverage__xs", "log_market_cap__xs",
                 "log_dollar_vol_20d__xs", "mom_12_1", "ratio__xs", "holder_net__xs",
                 "vol_20d__xs"]
        out["losers"] = {
            "horizon_months": h,
            "n_losers": int(lo_m.sum()), "n_winners": int(hi_m.sum()),
            "loser_mean_excess": _f(np.nanmean(y[lo_m])),
            "winner_mean_excess": _f(np.nanmean(y[hi_m])),
            "winner_minus_loser_feature_means": {
                f: _f(np.nanmean(t[f].to_numpy(dtype="float64")[hi_m])
                      - np.nanmean(t[f].to_numpy(dtype="float64")[lo_m]))
                for f in feats},
            "note": ("a feature gap here is DESCRIPTIVE and in-sample -- it is "
                     "where to look next, not a signal"),
        }
    else:
        out["losers"] = {"status": "TOO_THIN", "n_with_outcome": int(ok.sum())}
    return out


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(v) else round(v, 6)


# ======================================================== the grader

def grade(panel: pd.DataFrame, ret: dict, direction: str = "long") -> dict:
    """Realised outcomes, paired by MONTH BLOCK inside matched strata.

    n_effective counts DATE BLOCKS, never rows (CANON §58): 40,000 company-months
    inside 144 calendar months carry 144 independent draws at most, and treating
    them as 40,000 is how a t of 2 becomes a t of 30.
    """
    if ret.get("status") != "RETRIEVED":
        return {"status": ret.get("status", "NO_ANALOGUE")}
    t = panel.iloc[ret["treated_index"]]
    c = panel.iloc[ret["control_index"]]
    sign = -1.0 if direction == "short" else 1.0

    if len(t) < MIN_TREATED_ROWS or t["month"].nunique() < MIN_MONTH_BLOCKS:
        return {
            "status": "REFUSED_TOO_THIN",
            "n_treated": int(len(t)), "n_month_blocks": int(t["month"].nunique()),
            "floors": {"min_treated_rows": MIN_TREATED_ROWS,
                       "min_month_blocks": MIN_MONTH_BLOCKS},
            "why": ("a spread computed here would be a number without a sample "
                    "behind it. A refusal is a finding."),
        }

    strata = ["month", "sector", "size_tercile", "liq_tercile"]
    out: dict = {"status": "GRADED", "direction": direction,
                 "sign_applied": sign, "horizons": {}}
    for h in HORIZONS:
        col = f"excess_vw_{h}m"
        tg = t.groupby(strata, observed=True)[col].agg(["mean", "count"])
        cg = c.groupby(strata, observed=True)[col].agg(["mean", "count"])
        j = tg.join(cg, how="inner", lsuffix="_t", rsuffix="_c")
        j = j[(j["count_c"] >= MIN_CONTROLS_PER_STRATUM)
              & j["mean_t"].notna() & j["mean_c"].notna()]
        if j.empty:
            out["horizons"][str(h)] = {"status": "NO_MATCHED_STRATA"}
            continue
        j = j.assign(_d=(j["mean_t"] - j["mean_c"]) * sign)
        # One number per month: treated-count-weighted mean of stratum diffs.
        j = j.reset_index()
        wm = (j.assign(_w=j["count_t"], _wd=j["_d"] * j["count_t"])
                .groupby("month")[["_w", "_wd"]].sum())
        per_month = (wm["_wd"] / wm["_w"]).to_numpy(dtype="float64")
        per_month = per_month[np.isfinite(per_month)]
        n = len(per_month)
        mu = float(np.mean(per_month)) if n else float("nan")
        sd = float(np.std(per_month, ddof=1)) if n > 1 else float("nan")
        tstat = mu / (sd / math.sqrt(n)) if (n > 1 and sd > 0) else float("nan")
        cost = 2.0 * COST_BPS_ROUND_TRIP_PER_LEG / 10_000.0
        n_t_used = int(j["count_t"].sum())
        # THE FLOOR BINDS ON WHAT WAS ACTUALLY DIFFERENCED, not on what was
        # retrieved. Checking it upstream let SB-18 through with 233 treated
        # rows over 120 months and then report a t of 1.78 built from SIX month
        # blocks and SIX treated rows -- because only six strata ever held
        # enough controls to form a difference. A check that did not run on the
        # quantity being reported is not a check that passed.
        if n < MIN_MONTH_BLOCKS or n_t_used < MIN_TREATED_ROWS:
            out["horizons"][str(h)] = {
                "status": "REFUSED_TOO_THIN_AFTER_MATCHING",
                "n_month_blocks": n, "n_treated_rows": n_t_used,
                "n_control_rows": int(j["count_c"].sum()),
                "n_strata_used": int(len(j)),
                "n_treated_retrieved": int(len(t)),
                "n_month_blocks_retrieved": int(t["month"].nunique()),
                "floors": {"min_month_blocks": MIN_MONTH_BLOCKS,
                           "min_treated_rows": MIN_TREATED_ROWS},
                "why": ("the retrieved set cleared the floor but the MATCHED set "
                        "did not: most treated rows sat in strata with too few "
                        "controls to difference against. No spread is reported."),
            }
            continue
        out["horizons"][str(h)] = {
            "status": "GRADED",
            "spread_gross": _f(mu),
            "spread_net": _f(mu - cost),
            "cost_charged": _f(cost),
            "sd_across_months": _f(sd),
            "t_paired_by_month": _f(tstat),
            "n_month_blocks": n,
            "n_strata_used": int(len(j)),
            "n_treated_rows": n_t_used,
            "n_control_rows": int(j["count_c"].sum()),
            "treated_mean_raw": _f(t[col].mean()),
            "control_mean_raw": _f(c[col].mean()),
            "share_months_positive": _f(float(np.mean(per_month > 0)) if n else np.nan),
        }
    if not any(c.get("status") == "GRADED" for c in out["horizons"].values()):
        out["status"] = "NO_MATCHED_STRATA"
        out["why"] = ("every (month x sector x size x liquidity) stratum holding "
                      "a treated row held fewer than "
                      f"{MIN_CONTROLS_PER_STRATUM} controls, so no difference "
                      "could be formed. Not a zero.")
    out["cost_convention"] = {
        "bps_round_trip_per_leg": COST_BPS_ROUND_TRIP_PER_LEG, "legs": 2,
        "total_charged_decimal": 2 * COST_BPS_ROUND_TRIP_PER_LEG / 10_000.0,
        "note": ("charged ONCE per horizon, i.e. a hold-to-horizon convention. A "
                 "monthly-rebalanced version of the 12m column would pay this "
                 "twelve times and is NOT what is reported."),
    }
    return out


def retrieve_and_grade(panel: pd.DataFrame, s: dict, k: int = 20) -> tuple[dict, dict]:
    """Walk the back-off ladder until the evidence floor is met, or run out.

    Returns (retrieval, grade) for the FIRST level that clears the floor, and
    the level-0 (full conjunction) result if none does -- because "the exact
    configuration the model proposed matched 31 rows" is the more informative
    answer when even the loosest relaxation is thin.

    The ladder is reported on every row. A reader comparing two scenarios at
    different levels is comparing two different questions, and the receipt says
    so rather than letting the ranking imply otherwise.
    """
    attempts: list[dict] = []
    first_ret = first_g = None
    for n_drop in range(len(BACKOFF_ORDER) + 1):
        drop = BACKOFF_ORDER[:n_drop]
        ret = retrieve(panel, s, k=k, drop=drop)
        g = grade(panel, ret, direction=s.get("direction", "long"))
        attempts.append({"level": n_drop, "dropped": list(drop),
                         "n_treated": ret.get("n_treated", 0),
                         "n_month_blocks": ret.get("n_month_blocks", 0),
                         "status": g.get("status", ret.get("status"))})
        if first_ret is None:
            first_ret, first_g = ret, g
        graded_h = sum(1 for c in (g.get("horizons") or {}).values()
                       if c.get("status") == "GRADED")
        attempts[-1]["horizons_graded"] = graded_h
        if g.get("status") == "GRADED" and graded_h:
            ret["backoff_attempts"] = attempts
            g["backoff_level"] = n_drop
            g["backoff_dropped"] = list(drop)
            return ret, g
    first_ret["backoff_attempts"] = attempts
    first_g["backoff_level"] = 0
    first_g["backoff_dropped"] = []
    first_g["note"] = ("no level of the back-off ladder cleared the evidence "
                       "floor; the full conjunction is reported so the reader "
                       "sees how rare the proposed configuration actually is")
    return first_ret, first_g


# ======================================================== the generator

#: Neutral cues. A division and a mechanism family -- no numbers, no companies,
#: no direction. The model invents the scenario; these only spread the sample so
#: twenty calls do not return twenty variants of one idea.
_SEEDS: tuple[tuple[str, str], ...] = (
    ("Manufacturing", "a physical capacity bottleneck at one stage of production"),
    ("Manufacturing", "a substitution away from an incumbent input"),
    ("Mining", "an input cost shock that passes through unevenly"),
    ("Services", "a regulatory shift that changes who is allowed to sell"),
    ("Retail", "a distribution channel that stops working"),
    ("Transport & Utilities", "an energy cost step change"),
    ("Finance & Real Estate", "a credit tightening that starves capital spending"),
    ("Manufacturing", "an installed base becoming obsolete"),
    ("Services", "a new entrant undercutting on price"),
    ("Wholesale", "a large customer changing supplier"),
    ("Manufacturing", "a demand pull-forward that later reverses"),
    ("Mining", "a physical disruption to supply"),
    ("Services", "an exclusivity or protection period ending"),
    ("Construction", "a labour shortage constraining output"),
    ("Retail", "a shift in what end customers prefer"),
    ("Manufacturing", "a supply chain relocating between regions"),
    ("Transport & Utilities", "a standards change forcing replacement of equipment"),
    ("Finance & Real Estate", "a consolidation that removes a competitor"),
    ("Agriculture", "a currency move changing competitiveness"),
    ("Services", "a liability or insurance shock"),
)

_SYSTEM = (
    "You are a causal-mechanism analyst for an equity research system. Your job "
    "is to invent ONE structured causal scenario: a chain running from a "
    "real-world change to a change in a company's future returns, described "
    "entirely in observable states. "
    "You must NEVER state a price, a return, a percentage, a date, a real "
    "company name or a ticker -- you describe STRUCTURE, and other code finds "
    "the real historical companies that matched it. "
    "Reply with ONE JSON object and nothing else: no markdown fence, no prose "
    "before or after."
)


def _user_prompt(seed_division: str, seed_family: str, sid: str) -> str:
    def opts(name: str) -> str:
        return " | ".join(ENUMS[name])
    return (
        f"Domain cue: {seed_division}. Mechanism family: {seed_family}.\n\n"
        f"Invent one scenario. Fill EXACTLY this JSON shape, choosing values "
        f"only from the listed options where options are given:\n"
        "{\n"
        f'  "scenario_id": "{sid}",\n'
        f'  "event_type": one of [{opts("event_type")}],\n'
        '  "actors": [two to four short generic role names, e.g. "upstream fabricator"],\n'
        f'  "company_role": one of [{opts("company_role")}],\n'
        '  "sector_theme": a short free-text theme,\n'
        f'  "sic_division_hint": one of [{opts("sic_division_hint")}],\n'
        f'  "demand_change": one of [{opts("demand_change")}],\n'
        f'  "supply_change": one of [{opts("supply_change")}],\n'
        f'  "capacity_constraint": one of [{opts("capacity_constraint")}],\n'
        f'  "holder_action": one of [{opts("holder_action")}],\n'
        f'  "analyst_change": one of [{opts("analyst_change")}],\n'
        '  "price_state": {\n'
        f'      "drawdown_state": one of [{opts("drawdown_state")}],\n'
        f'      "momentum_12_1_sign": one of [{opts("momentum_12_1_sign")}]\n'
        '  },\n'
        f'  "attention_state": one of [{opts("attention_state")}],\n'
        f'  "expected_horizon_months": one of [{opts("expected_horizon_months")}] (a string),\n'
        f'  "direction": one of [{opts("direction")}],\n'
        '  "mechanism": one sentence naming the causal chain,\n'
        '  "falsifier": one sentence naming an observation that would refute it\n'
        "}\n\n"
        "Choose the state fields to describe the company AT THE MOMENT the "
        "scenario is entered, not afterwards. Use \"unknown\" whenever the "
        "mechanism genuinely does not imply a state -- a guessed state is worse "
        "than an absent one."
    )


def _extract_json(text: str) -> dict | None:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```")[1] if "```" in t[3:] else t[3:]
        t = t.split("\n", 1)[1] if t.lower().startswith("json") else t
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(t[i:j + 1])
    except ValueError:
        return None


def generate_scenarios(n: int = 20, *, second_opinion: int = 0,
                       verbose: bool = True) -> dict:
    """Call the LLM. DeepSeek through the repo's own `_call_llm`.

    Everything about the house LLM contract comes along by REUSING `_call_llm`:
    the English language pin, the >10% non-Latin refusal, the daily call budget,
    the billing breaker, and one telemetry row per wire call with a real
    `cost_usd` from `config.LLM_PRICE_PER_MTOK`. A thin private client would
    have had none of that, and its spend would not appear in
    `scripts.llm_cost_audit`.

    Two module globals are raised for the duration and restored: `_MAX_TOKENS`
    (500 is not enough for this JSON) and the temperature (the second pass runs
    warm so self-disagreement is a real measurement, not a rounding artefact).
    """
    from backend.services import llm_analyzer as LA
    from backend.services import llm_telemetry as tel

    log = (lambda *a: print(*a)) if verbose else (lambda *a: None)
    if LA._get_provider() == "none":
        raise SystemExit(
            "REFUSED: no LLM provider is configured. Generation cannot fall "
            "back to hand-written scenarios -- the whole point is that the "
            "MODEL proposed them.")

    def _valid(txt: str) -> bool:
        o = _extract_json(txt)
        return bool(o) and validate_scenario(o)[0]

    old_max, old_temp = LA._MAX_TOKENS, LA._llm_cfg.get("temperature", 0.3)
    rows: list[dict] = []
    raw_lines: list[dict] = []
    try:
        LA._MAX_TOKENS = 1200
        LA._llm_cfg["temperature"] = 0.7
        seeds = [_SEEDS[i % len(_SEEDS)] for i in range(n)]
        for i, (div, fam) in enumerate(seeds):
            sid = f"SB-{RUN_TAG}-{i:02d}"
            txt = LA._call_llm(_SYSTEM, _user_prompt(div, fam, sid),
                               purpose="scenario_bridge_generate", validate=_valid)
            obj = _extract_json(txt or "")
            ok, errs = validate_scenario(obj) if obj else (False, ["no JSON in reply"])
            if obj is not None:
                obj["scenario_id"] = sid          # never let the model rename its row
            raw_lines.append({
                "kind": "generation", "scenario_id": sid, "pass": "A",
                "provider": "deepseek", "model": LA._DEEPSEEK_MODEL,
                "temperature": 0.7, "seed_division": div, "seed_family": fam,
                "raw": txt, "parsed": obj, "schema_valid": ok, "errors": errs,
            })
            if ok:
                obj["_seed"] = {"division": div, "family": fam}
                rows.append(obj)
            log(f"  [{sid}] {'ok' if ok else 'INVALID: ' + '; '.join(errs[:2])}")

        # ---- the second opinion
        if second_opinion > 0:
            dis = _second_opinion(rows[:second_opinion], raw_lines, log)
        else:
            dis = {"status": "NOT_RUN"}
    finally:
        LA._MAX_TOKENS = old_max
        LA._llm_cfg["temperature"] = old_temp

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"scenarios_{RUN_TAG}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in raw_lines:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        for r in rows:
            fh.write(json.dumps({"kind": "scenario", **r},
                                ensure_ascii=False, default=str) + "\n")

    spend = _spend_for_purposes(tel, ("scenario_bridge_generate",
                                      "scenario_bridge_second_opinion"))
    return {"path": str(path), "n_requested": n, "n_valid": len(rows),
            "scenarios": rows, "disagreement": dis, "spend": spend}


def _second_opinion(rows: list[dict], raw_lines: list[dict], log) -> dict:
    """A SECOND model answers the same seeds; agreement is measured per field.

    Preference order, and why: a genuinely different model is a stronger test
    than the same model twice, so `model_provider` (NVIDIA NIM, already in this
    repo and free-tier) is tried first. It is not the backend's provider and
    never becomes one -- `docs/CLAUDE.md` is unambiguous that DeepSeek is the
    sole PROVISIONED backend provider, and nothing here changes that. If NVIDIA
    refuses, the fallback is DeepSeek at a hot temperature, which measures
    SELF-disagreement and is labelled as such rather than as two models.
    """
    from backend.services import llm_analyzer as LA
    from backend.services import llm_telemetry as tel
    from backend.services import model_provider as mp

    mode, provider, model = None, None, None
    try:
        if mp.configured("nvidia"):
            probe = mp.complete("nvidia", "Reply with the single word: ready.",
                                max_tokens=300, timeout=60)
            mode, provider, model = "cross_model", "nvidia", probe.model
            log(f"  second opinion: nvidia/{model} answered in {probe.latency_s}s")
            tel.record_call(provider="nvidia", model=probe.model,
                            purpose="scenario_bridge_second_opinion",
                            prompt="probe", tokens_in=probe.prompt_tokens or 0,
                            tokens_out=probe.completion_tokens or 0,
                            latency_ms=probe.latency_s * 1000.0, schema_valid=True)
    except Exception as exc:                                  # noqa: BLE001
        log(f"  second opinion: nvidia refused ({type(exc).__name__}: "
            f"{str(exc)[:120]}) -- falling back to self-disagreement")
    if mode is None:
        mode, provider, model = "self_disagreement", "deepseek", LA._DEEPSEEK_MODEL

    pairs, per_field = [], {}
    fields = [n for n, _, k in _FIELDS if k == "enum"]
    for r in rows:
        sid = r["scenario_id"]
        div = r.get("_seed", {}).get("division", "Manufacturing")
        fam = r.get("_seed", {}).get("family", "a capacity bottleneck")
        prompt = _user_prompt(div, fam, sid + "-B")
        txt = None
        if mode == "cross_model":
            try:
                rep = mp.complete(provider, prompt, system=_SYSTEM, max_tokens=1200,
                                  temperature=0.7, timeout=120)
                txt = rep.text
                tel.record_call(provider=provider, model=rep.model,
                                purpose="scenario_bridge_second_opinion",
                                prompt=_SYSTEM + "\n" + prompt,
                                tokens_in=rep.prompt_tokens or 0,
                                tokens_out=rep.completion_tokens or 0,
                                latency_ms=rep.latency_s * 1000.0,
                                schema_valid=bool(_extract_json(rep.text)))
            except Exception as exc:                          # noqa: BLE001
                log(f"  [{sid}] second opinion failed: {str(exc)[:100]}")
        else:
            old = LA._llm_cfg.get("temperature", 0.3)
            LA._llm_cfg["temperature"] = 1.3      # the hot pass
            try:
                txt = LA._call_llm(_SYSTEM, prompt,
                                   purpose="scenario_bridge_second_opinion")
            finally:
                LA._llm_cfg["temperature"] = old
        obj = _extract_json(txt or "")
        raw_lines.append({"kind": "second_opinion", "scenario_id": sid,
                          "pass": "B", "mode": mode, "provider": provider,
                          "model": model, "raw": txt, "parsed": obj})
        if not obj:
            continue
        agree = {f: (r.get(f) == obj.get(f)) for f in fields if f in r}
        ps_a, ps_b = r.get("price_state") or {}, obj.get("price_state") or {}
        for sub in _PRICE_STATE_FIELDS:
            agree[f"price_state.{sub}"] = ps_a.get(sub) == ps_b.get(sub)
        pairs.append({"scenario_id": sid, "agree": agree,
                      "a": {f: r.get(f) for f in fields},
                      "b": {f: obj.get(f) for f in fields}})
        for f, v in agree.items():
            per_field.setdefault(f, [0, 0])
            per_field[f][0] += int(bool(v))
            per_field[f][1] += 1
        log(f"  [{sid}] pass B agreement "
            f"{sum(agree.values())}/{len(agree)}")

    rates = {f: round(a / max(b, 1), 4) for f, (a, b) in per_field.items()}
    overall = (round(sum(a for a, _ in per_field.values())
                     / max(sum(b for _, b in per_field.values()), 1), 4)
               if per_field else None)
    return {
        "status": "MEASURED" if pairs else "NO_PAIRS",
        "mode": mode, "provider": provider, "model": model,
        "n_pairs": len(pairs),
        "field_agreement_rate": rates,
        "overall_agreement_rate": overall,
        "reading": (
            "Agreement is NOT correctness. Two models agreeing on "
            "`demand_change=rising` says the concept is easy to guess, not that "
            "any company's demand rose. Only the panel grades."),
        "pairs": pairs,
    }


def _spend_for_purposes(tel, purposes: Iterable[str]) -> dict:
    """What this run actually cost, read back from the LEDGER, not estimated."""
    want = set(purposes)
    total, n, unpriced = 0.0, 0, 0
    try:
        rows = tel.read_calls()
    except Exception:                                          # noqa: BLE001
        return {"status": "LEDGER_UNREADABLE"}
    for r in rows:
        p = r.get("purpose") if isinstance(r, dict) else getattr(r, "purpose", None)
        if p not in want:
            continue
        n += 1
        c = r.get("cost_usd") if isinstance(r, dict) else getattr(r, "cost_usd", None)
        if c is None:
            unpriced += 1
        else:
            total += float(c)
    return {"n_calls": n, "usd_priced": round(total, 6),
            "n_unpriced_calls": unpriced,
            "is_lower_bound": unpriced > 0,
            "note": ("unpriced calls are models absent from "
                     "config.LLM_PRICE_PER_MTOK (NVIDIA NIM free tier); a None "
                     "priced as 0 is how a total becomes a lie that sums")}


#: The five fields that actually BUILD the retrieval filter. Everything else is
#: narrative, a stratum, or a grading control.
PREDICATE_FIELDS: tuple[str, ...] = (
    "analyst_change", "attention_state", "holder_action",
    "price_state.drawdown_state", "price_state.momentum_12_1_sign",
)


def disagreement_summary(path: Path | None = None) -> dict:
    """Re-derive per-field agreement from the persisted jsonl.

    Split PREDICATE fields from the rest, because that split is the finding: if
    two models agree on the story and disagree on the state, then the analogue
    set a scenario retrieves is largely an artefact of WHICH MODEL WAS ASKED,
    and every spread below inherits that.
    """
    path = path or (OUT_DIR / f"scenarios_{RUN_TAG}.jsonl")
    if not path.exists():
        return {"status": "NO_FILE"}
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    A = {r["scenario_id"]: r for r in rows if r.get("kind") == "scenario"}
    fields = [n for n, _, k in _FIELDS if k == "enum"]
    per: dict[str, list[int]] = {}
    n_pairs, mode, model = 0, None, None
    for r in rows:
        if r.get("kind") != "second_opinion":
            continue
        mode, model = r.get("mode", mode), r.get("model", model)
        b = r.get("parsed")
        a = A.get(r.get("scenario_id"))
        if not b or not a:
            continue
        n_pairs += 1
        ag = {f: (a.get(f) == b.get(f)) for f in fields}
        pa, pb = a.get("price_state") or {}, b.get("price_state") or {}
        for sub in _PRICE_STATE_FIELDS:
            ag[f"price_state.{sub}"] = pa.get(sub) == pb.get(sub)
        for f, v in ag.items():
            per.setdefault(f, [0, 0])
            per[f][0] += int(bool(v))
            per[f][1] += 1
    if not per:
        return {"status": "NO_PAIRS", "mode": mode}

    def _rate(names) -> tuple[float | None, int, int]:
        hit = sum(per[f][0] for f in names if f in per)
        tot = sum(per[f][1] for f in names if f in per)
        return (round(hit / tot, 4) if tot else None), hit, tot

    pred_rate, ph, pt = _rate(PREDICATE_FIELDS)
    rest = [f for f in per if f not in PREDICATE_FIELDS]
    rest_rate, rh, rt = _rate(rest)
    all_rate, ah, at_ = _rate(list(per))
    return {
        "status": "MEASURED", "mode": mode, "model_b": model, "n_pairs": n_pairs,
        "per_field": {f: {"agree": a, "n": b, "rate": round(a / b, 4)}
                      for f, (a, b) in sorted(per.items(), key=lambda kv: kv[1][0] / kv[1][1])},
        "predicate_fields": {"fields": list(PREDICATE_FIELDS), "agree": ph,
                             "n": pt, "rate": pred_rate},
        "non_predicate_fields": {"fields": sorted(rest), "agree": rh, "n": rt,
                                 "rate": rest_rate},
        "overall": {"agree": ah, "n": at_, "rate": all_rate},
        "reading": (
            "Agreement is NOT correctness -- two models agreeing that demand "
            "rose says the concept is easy to guess, not that it rose. What "
            "matters is WHERE they agree: if the predicate fields agree far "
            "less than the narrative fields, then the analogue set a scenario "
            "retrieves is substantially an artefact of which model was asked, "
            "and every spread in this receipt inherits that."),
    }


def load_scenarios(path: Path | None = None) -> list[dict]:
    path = path or (OUT_DIR / f"scenarios_{RUN_TAG}.jsonl")
    if not path.exists():
        raise SystemExit(f"REFUSED: {path} does not exist. Run --generate first.")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("kind") == "scenario":
            out.append(r)
    return out


def write_schema() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(
        json.dumps(scenario_schema(), indent=2) + "\n", encoding="utf-8")
    return SCHEMA_PATH


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-schema", action="store_true")
    ap.add_argument("--generate", type=int, default=0,
                    help="number of scenarios to generate (COSTS MONEY)")
    ap.add_argument("--second-opinion", type=int, default=0,
                    help="how many scenarios also get a second model's answer")
    a = ap.parse_args(argv)
    if a.write_schema:
        print(f"schema -> {write_schema()}")
    if a.generate:
        r = generate_scenarios(a.generate, second_opinion=a.second_opinion)
        print(f"\n{r['n_valid']}/{r['n_requested']} valid -> {r['path']}")
        print("spend:", json.dumps(r["spend"]))
        print("disagreement:", r["disagreement"].get("status"),
              r["disagreement"].get("overall_agreement_rate"))
    if not (a.write_schema or a.generate):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
