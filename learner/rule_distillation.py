"""M2 -- DISTILL A RULE FROM A WINNER AND ITS MATCHED LOSER, THEN SCORE IT.

The literature agrees on the shape. ExpeL (Zhao et al., AAAI 2024,
arXiv:2308.10144) diffs SUCCESS against FAILURE trajectory PAIRS and extracts
cross-task natural-language insights; FactorMiner (arXiv:2602.14670) stores
both successful patterns AND failure constraints; Reflexion (arXiv:2303.11366)
supplies the small-buffer baseline and the caveat that verbal feedback needs a
verifiable success signal. M2 is that pattern applied to graded ledger rows,
with one addition nothing in the surveyed literature does:

    A DISTILLED RULE IS A FORECASTER AND IS SCORED WITH A PROPER SCORING RULE.

Not "the model said it was confident". Not "it was retrieved, so it applies".
The rule states a direction under stated conditions, the ledger later says what
happened, and the rule gets its own Brier through the same
`calibration.brier_decomposition` every other forecaster here is scored by.
Tetlock's persistence result (r ~ 0.65 year over year) is why scoring a rule
this way is not a category error: forecasting skill is a stable trait, so a
skill number computed on one window says something about the next.

THE OVER-TRUST GUARD, AND THE PAPER IT COMES FROM
=================================================
arXiv:2505.16067 (Xiong, Lin, Xie, He, Tang, Lakkaraju, Xiang -- "How Memory
Management Impacts LLM Agents", 2025) measures **experience-following**: the
more similar a retrieved memory looks to the current task, the more similar the
agent's output becomes -- WHETHER OR NOT the retrieved memory was correct. So a
retrieval score is exactly the wrong thing to weight a memory by. Here a rule's
weight in a live prompt is capped by its MEASURED Brier skill against the base
rate (`prompt_weight = clamp(bss, 0, MAX_RULE_WEIGHT)`), never by similarity,
never by recency, and a rule indistinguishable from the shuffled-pair noise
floor is never injected at all no matter how well it matches.

FIVE STATES, AND NONE OF THEM IS DELETION
=========================================
`CANDIDATE` (too few firings to score) -> `GENERALISED` / `NOT_GENERALISED`
(does it survive on a mechanism family it was not distilled from) /
`NOT_BETTER_THAN_NOISE` (a random pairing would have produced it) / `STALE` (it
stopped firing). A `NOT_GENERALISED` rule is kept, scored and printed as
prominently as a `GENERALISED` one -- CLAUDE.md rule 4, study losers as hard as
winners. Nothing is ever removed from `learned_rules.jsonl`.

WHAT THIS MODULE DOES WHEN THE MODEL IS DOWN
============================================
Everything except write rule TEXT. Pairing, the leaked-field guard, scoring,
the generalisation gate, the noise floor, the over-trust cap and both writers
run offline; only `candidates_from_pairs` needs the local reader, and when it
is not answering the job records `PENDING_MODEL` by name with the pair list
frozen. It does NOT start the model server: `llama-server` is owned by the
desktop shell and a research job that boots an 8 GB server collides with
whatever else is running.

    python -m learner.rule_distillation --month 2026-09
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import logging
import math
import os
import random
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import calibration as CAL                      # noqa: E402

# ---------------------------------------------------------------- constants

SCHEMA_VERSION = "learned-rule-1.0.0"

#: A mechanism with 40 favourable and 3 unfavourable resolutions is not 120
#: independent pairs. Sampled without replacement, seeded, and both the
#: sampled and the possible count travel in the receipt.
MAX_PAIRS_PER_KEY = 12

#: Firings on a family the rule was NOT distilled from, before the
#: generalisation question can be answered at all.
MIN_HELDOUT_FIRINGS = 15

#: A rule that has not fired in this many months is STALE -- a receipt that a
#: condition stopped mattering, never a deletion.
RULE_STALE_MONTHS = 6

#: The hard cap on how much a distilled rule may move a live forecast, even
#: with a perfect Brier skill score. The guard is the CAP, not the number.
MAX_RULE_WEIGHT = 0.6

#: Two consecutive non-overlapping windows beating climatology, reusing
#: `evidence_memory`'s own "a single observation can neither promote nor kill".
MIN_PASSES_TO_PROMOTE = 2

#: Where the rules live. `ledger_retrieval.LEARNED_RULES` already points here
#: and reads it; M2 is the writer.
BRAIN = REPO / "backend" / "data" / "optimus" / "brain"
LEARNED_RULES = BRAIN / "learned_rules.jsonl"

#: Fields the model may see on the INPUT side of a pair. Never a raw dict dump:
#: one stray `outcome` in the "applies_when" side and the rule memorises the
#: answer key.
ALLOWED_INPUT_FIELDS = (
    "mechanism_id", "ticker", "specialist", "observable", "horizon_days",
    "thesis", "counter_thesis", "next_observable", "arm", "cell",
    "era_tag", "control_construction", "job", "run", "variant",
    "made_at", "resolves_after", "family_id",
)

#: Tokens that may never appear inside a returned `applies_when`. These are the
#: OUTCOME side; a condition written on them is a condition on the answer.
LEAKED_OUTCOME_FIELDS = frozenset({
    "outcome", "resolved_at", "brier", "vs_benchmark", "vs_control",
    "net_beats_market", "gross_beats_market", "verdict", "sharpe", "dsr",
})

#: The typed condition vocabulary. `applies_when` is a list of these, not free
#: text, so retrieval can evaluate a rule mechanically -- an LLM-evaluated
#: "does this rule apply" check would reintroduce the over-trust failure this
#: module exists to prevent.
CONDITION_FIELDS = ("mechanism_id", "ticker_sector", "specialist", "observable",
                    "horizon_days_bucket", "arm", "era_tag",
                    "control_construction", "regime_tag")
CONDITION_OPS = ("eq", "in", "gte", "lte", "between")

DIRECTIONS = ("higher", "lower", "unchanged_vs_control")


class DistillationRefused(ValueError):
    """The distillation cannot proceed and says which input is missing."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return round(float(v), nd)


# ------------------------------------------------------------- families

def mechanism_family(mechanism_id: Any) -> str:
    """The coarse family a mechanism belongs to.

    `signal_registry.py` has no family grouping to reuse (checked 2026-09-12),
    so the spec's documented fallback applies: the leading underscore-delimited
    token of the mechanism id, which is what makes `momentum_12_1` and
    `momentum_6_1` ONE family. (The spec's prose says "the first two tokens"
    and its worked example says `momentum`; two tokens would put those two ids
    in different families and defeat the held-out test, so the example is what
    is implemented and this sentence is why.)
    """
    text = str(mechanism_id or "").strip()
    if not text:
        return "unstated"
    return text.split("_", 1)[0] or "unstated"


def horizon_bucket(days: Any) -> str:
    """A horizon bucket a condition can be written on. Never a raw integer:
    `horizon_days == 21` is a condition that fires on one horizon and looks
    like a rule about a month."""
    try:
        d = int(days)
    except (TypeError, ValueError):
        return "unstated"
    for edge, name in ((2, "1-2d"), (5, "5d"), (21, "21d"), (63, "63d"),
                       (252, "252d")):
        if d <= edge:
            return name
    return "over_252d"


# ---------------------------------------------------------------- pairing

def _resolved(rows: Iterable[dict]) -> list[dict]:
    """Graded and un-voided. `calibration.resolved_rows` also requires a usable
    `probability`, which an `evidence_memory` row does not have, so the
    ledger's own predicate is reused for ledger rows and relaxed for memory
    rows -- stated rather than silently widened."""
    out = []
    for r in rows:
        if r.get("void_reason"):
            continue
        if r.get("outcome") is None and r.get("verdict") is None:
            continue
        out.append(r)
    return out


def _won(row: dict) -> bool | None:
    """Did this row clear its own bar? None when the row does not say.

    THREE SOURCES, ONE QUESTION. A ledger row says `outcome` and `vs_control`;
    an `evidence_memory` row says `verdict` and `net_beats_market`. Reading
    either as "success" is the same judgement, and making the mapping explicit
    here is what keeps a pair from being built out of two different meanings of
    winning.
    """
    if row.get("vs_control") is not None and row.get("outcome") is not None:
        return bool(float(row["vs_control"]) > 0 and int(row["outcome"]) == 1)
    if row.get("outcome") is not None:
        return bool(int(row["outcome"]) == 1)
    if row.get("net_beats_market") is not None:
        return bool(row["net_beats_market"])
    verdict = str(row.get("verdict") or "").upper()
    if verdict:
        if any(k in verdict for k in ("NOVEL", "SUPPORTED", "CLEARS",
                                      "SURVIVES")):
            return True
        if any(k in verdict for k in ("DOES NOT CLEAR", "NOISE", "REFUTED",
                                      "COST_KILLED", "FAILED")):
            return False
    return None


def _key_for(row: dict, kind: str) -> tuple | None:
    if kind == "book_vs_twin":
        mech = row.get("mechanism_id")
        if not mech:
            return None
        return (mech, row.get("control_construction"))
    if kind == "era_split":
        fam = row.get("family_id") or row.get("mechanism_id")
        if not fam:
            return None
        return (fam, row.get("arm"))
    if kind == "arm_vs_control":
        if not row.get("job"):
            return None
        return (row.get("job"), row.get("run"), row.get("cell"))
    raise DistillationRefused(f"unknown pair kind {kind!r}")


def _row_id(row: dict) -> str:
    for k in ("prediction_id", "rule_id", "id"):
        if row.get(k):
            return str(row[k])
    blob = json.dumps({k: row.get(k) for k in sorted(row)}, default=str,
                      sort_keys=True)
    return "h" + hashlib.sha1(blob.encode()).hexdigest()[:12]


def make_pairs(rows: Iterable[dict], *, kinds=("book_vs_twin", "era_split",
                                               "arm_vs_control"),
               seed: int = 20260912,
               max_per_key: int = MAX_PAIRS_PER_KEY) -> dict:
    """(winner, loser) pairs sharing a key, one side cleared its bar and one did not.

    Sampling is SEEDED and both counts are reported: `pairs_sampled` beside
    `pairs_possible`, so a reader can see how much of the pool a rule saw.
    A degenerate self-pair -- the same row on both sides, which a sloppy key
    produces -- is dropped and counted rather than distilled from.
    """
    rows = _resolved(rows)
    rng = random.Random(seed)
    out: list[dict] = []
    possible = 0
    degenerate = 0
    per_kind: dict[str, int] = {}
    for kind in kinds:
        buckets: dict[tuple, dict[str, list[dict]]] = {}
        for r in rows:
            key = _key_for(r, kind)
            if key is None:
                continue
            won = _won(r)
            if won is None:
                continue
            buckets.setdefault(key, {"win": [], "lose": []})[
                "win" if won else "lose"].append(r)
        for key, sides in sorted(buckets.items(), key=lambda kv: str(kv[0])):
            wins, loses = sides["win"], sides["lose"]
            if not wins or not loses:
                continue
            # THE CROSS PRODUCT IS COUNTED, NEVER MATERIALISED. One
            # `evidence_memory` family carries 19,032 rows, so a key with
            # 9,000 winners and 9,000 losers is 81 MILLION tuples -- the first
            # version built that list and the test run hung. The count is
            # arithmetic and the sample is drawn on INDICES, so the work is
            # `max_per_key` regardless of how large the bucket is.
            n_possible = len(wins) * len(loses)
            possible += n_possible
            kept = []
            if n_possible <= max_per_key:
                pairs_here = [(w, ll) for w in wins for ll in loses]
            else:
                seen_idx: set[tuple[int, int]] = set()
                pairs_here = []
                guard = 0
                while len(pairs_here) < max_per_key and guard < 40 * max_per_key:
                    guard += 1
                    ij = (rng.randrange(len(wins)), rng.randrange(len(loses)))
                    if ij in seen_idx:
                        continue
                    seen_idx.add(ij)
                    pairs_here.append((wins[ij[0]], loses[ij[1]]))
            for w, ll in pairs_here:
                if _row_id(w) == _row_id(ll):
                    degenerate += 1
                    continue
                kept.append((w, ll))
            if len(kept) > max_per_key:
                kept = rng.sample(kept, max_per_key)
            for w, ll in kept:
                out.append({
                    "pair_kind": kind,
                    "pairing_key": "::".join(str(x) for x in key),
                    "winner": w, "loser": ll,
                    "winner_id": _row_id(w), "loser_id": _row_id(ll),
                    "mechanism_family": mechanism_family(
                        w.get("mechanism_id") or w.get("family_id")),
                })
                per_kind[kind] = per_kind.get(kind, 0) + 1
    return {"pairs": out, "pairs_possible": possible,
            "pairs_sampled": len(out), "dropped_degenerate": degenerate,
            "by_kind": per_kind, "seed": seed,
            "max_pairs_per_key": max_per_key}


def shuffled_pairs(built: dict, *, seed: int | None = None) -> dict:
    """THE NOISE FLOOR. The same winners and losers, RE-PAIRED ACROSS KEYS.

    A winner from mechanism A against a loser from unrelated mechanism B has no
    mechanism in common to explain, so whatever the pipeline extracts from it
    is what the pipeline extracts from nothing. Every real rule's Brier is read
    against this as well as against climatology, and the two say different
    things: climatology says "better than the base rate", the noise floor says
    "better than what a random pairing would have produced".

    Seeded from the month rather than hand-picked -- a shuffle seed chosen
    after seeing which shuffle flatters the result is not a shuffle.
    """
    pairs = list(built["pairs"])
    if len(pairs) < 2:
        return {**built, "pairs": [], "shuffled": True,
                "reason": "fewer than two pairs; a permutation of one pair is "
                          "that pair"}
    seed = int(seed if seed is not None else built.get("seed", 0)) + 1
    rng = random.Random(seed)
    losers = [p["loser"] for p in pairs]
    for _ in range(64):
        rng.shuffle(losers)
        if all(_key_for(p["winner"], p["pair_kind"])
               != _key_for(ll, p["pair_kind"])
               for p, ll in zip(pairs, losers)):
            break
    out = []
    for p, ll in zip(pairs, losers):
        out.append({**p, "loser": ll, "loser_id": _row_id(ll),
                    "pairing_key": p["pairing_key"] + "::SHUFFLED"})
    return {**built, "pairs": out, "shuffled": True, "shuffle_seed": seed}


# ------------------------------------------------------- the prompt contract

def serialize_row(row: dict) -> dict:
    """The allowlisted view of one row. Nothing else reaches the model."""
    return {k: row[k] for k in ALLOWED_INPUT_FIELDS
            if row.get(k) not in (None, "")}


def pair_prompt(pair: dict) -> str:
    """One pair, one call. NEVER batched across pairs: batching lets the model
    average over mechanisms and return a rule that fits none of them."""
    winner = serialize_row(pair["winner"])
    loser = serialize_row(pair["loser"])
    return (
        "Two research records that share a key. One cleared its bar and one "
        "did not. Name the DIFFERENCE that a future forecaster could have "
        "observed BEFOREHAND, as a single conditional rule.\n\n"
        f"PAIR KIND: {pair['pair_kind']}\nPAIRING KEY: {pair['pairing_key']}\n\n"
        f"WINNER_INPUTS: {json.dumps(winner, sort_keys=True, default=str)}\n"
        f"WINNER_OUTCOME: cleared its bar\n\n"
        f"LOSER_INPUTS: {json.dumps(loser, sort_keys=True, default=str)}\n"
        f"LOSER_OUTCOME: did not clear its bar\n\n"
        "Reply with ONE JSON object and nothing else, with keys: rule_text "
        "(<=400 chars), applies_when (1-5 objects of {field, op, value} where "
        f"field is one of {list(CONDITION_FIELDS)} and op is one of "
        f"{list(CONDITION_OPS)}), predicts ({{observable, direction}} where "
        f"direction is one of {list(DIRECTIONS)}), evidence_pairs (list of "
        "strings), confidence (0..1). applies_when may only use fields that "
        "were knowable BEFORE the outcome; a condition on the outcome is "
        "rejected."
    )


def prompt_hash(pair: dict) -> str:
    return hashlib.sha256(pair_prompt(pair).encode()).hexdigest()[:16]


def validate_candidate(obj: Any) -> tuple[dict | None, str | None]:
    """(candidate, refusal). Schema first, THEN the leaked-outcome-field guard.

    The leak check is not a schema clause on purpose: `REJECTED_LEAKED_OUTCOME_
    FIELD` and `SCHEMA_INVALID` are different findings about the model and are
    counted separately, and a schema that merely enumerated allowed fields
    would report a leak as a typo.
    """
    if not isinstance(obj, dict):
        return None, "SCHEMA_INVALID: not an object"
    for k in ("rule_text", "applies_when", "predicts", "evidence_pairs",
              "confidence"):
        if k not in obj:
            return None, f"SCHEMA_INVALID: missing {k!r}"
    if not isinstance(obj["rule_text"], str) or not 0 < len(obj["rule_text"]) <= 400:
        return None, "SCHEMA_INVALID: rule_text must be 1..400 chars"
    conds = obj["applies_when"]
    if not isinstance(conds, list) or not 1 <= len(conds) <= 5:
        return None, "SCHEMA_INVALID: applies_when must hold 1..5 conditions"
    for c in conds:
        if not isinstance(c, dict) or set(c) < {"field", "op", "value"}:
            return None, "SCHEMA_INVALID: a condition needs field, op, value"
        if str(c["field"]).lower() in LEAKED_OUTCOME_FIELDS:
            return None, (f"REJECTED_LEAKED_OUTCOME_FIELD: {c['field']!r} is "
                          f"known only AFTER the outcome; a condition on it "
                          f"memorises the answer key")
        if c["field"] not in CONDITION_FIELDS:
            return None, (f"SCHEMA_INVALID: condition field {c['field']!r} is "
                          f"not one of {list(CONDITION_FIELDS)}")
        if c["op"] not in CONDITION_OPS:
            return None, f"SCHEMA_INVALID: unknown op {c['op']!r}"
    pred = obj["predicts"]
    if not isinstance(pred, dict) or "observable" not in pred or "direction" not in pred:
        return None, "SCHEMA_INVALID: predicts needs observable and direction"
    if pred["direction"] not in DIRECTIONS:
        return None, f"SCHEMA_INVALID: direction {pred['direction']!r}"
    if str(pred["observable"]).lower() in LEAKED_OUTCOME_FIELDS:
        return None, ("REJECTED_LEAKED_OUTCOME_FIELD: predicts.observable "
                      f"{pred['observable']!r} is an outcome field")
    if not isinstance(obj["evidence_pairs"], list) or not obj["evidence_pairs"]:
        return None, "SCHEMA_INVALID: evidence_pairs must be a non-empty list"
    try:
        conf = float(obj["confidence"])
    except (TypeError, ValueError):
        return None, "SCHEMA_INVALID: confidence must be a number"
    if not 0.0 <= conf <= 1.0:
        return None, "SCHEMA_INVALID: confidence must be in [0, 1]"
    return {**obj, "confidence": conf}, None


def _parse_json(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def candidates_from_pairs(pairs: Sequence[dict], *, complete_fn: Callable,
                          backend: str = "local_gguf",
                          max_tokens: int = 400) -> dict:
    """One model call per pair, schema-validated, counted by refusal reason.

    `complete_fn` is injected so the offline suite never touches a server and
    so the known-answer tests can plant a KNOWN response. A response that fails
    the schema is retried ONCE at a higher temperature and then discarded as
    `SCHEMA_INVALID` -- counted, never silently dropped.
    """
    rules, refusals = [], {"SCHEMA_INVALID": 0, "REJECTED_LEAKED_OUTCOME_FIELD": 0,
                           "PROVIDER_REFUSED": 0}
    detail: list[dict] = []
    for pair in pairs:
        prompt = pair_prompt(pair)
        obj = refusal = None
        for temperature in (0.0, 0.3):
            try:
                reply = complete_fn(backend, prompt, max_tokens=max_tokens,
                                    temperature=temperature,
                                    purpose="M2_distill")
            except Exception as exc:                          # noqa: BLE001
                refusals["PROVIDER_REFUSED"] += 1
                detail.append({"pairing_key": pair["pairing_key"],
                               "refusal": f"PROVIDER_REFUSED: {exc}"})
                obj = None
                break
            obj, refusal = validate_candidate(
                _parse_json(getattr(reply, "text", reply)))
            if obj is not None:
                break
        if obj is None:
            if refusal:
                kind = refusal.split(":")[0]
                refusals[kind] = refusals.get(kind, 0) + 1
                detail.append({"pairing_key": pair["pairing_key"],
                               "refusal": refusal})
            continue
        rules.append({**obj, "pair_kind": pair["pair_kind"],
                      "pairing_key": pair["pairing_key"],
                      "distilled_from": [pair["winner_id"], pair["loser_id"]],
                      "mechanism_family": pair["mechanism_family"],
                      "prompt_hash": prompt_hash(pair)})
    return {"candidates": rules, "refusals": refusals, "refusal_detail": detail,
            "n_pairs": len(pairs)}


# ------------------------------------------------------------- the scoring

def _field_of(row: dict, field: str) -> Any:
    if field == "horizon_days_bucket":
        return horizon_bucket(row.get("horizon_days"))
    if field == "ticker_sector":
        return row.get("ticker_sector") or row.get("sector")
    return row.get(field)


def condition_holds(cond: dict, row: dict) -> bool:
    """One typed condition against one row. A MISSING field is False, never
    True: a rule that fires on rows which do not carry the field it conditions
    on is a rule with no condition."""
    value = _field_of(row, cond.get("field"))
    if value is None:
        return False
    op, target = cond.get("op"), cond.get("value")
    try:
        if op == "eq":
            return str(value) == str(target)
        if op == "in":
            return str(value) in {str(t) for t in (target or [])}
        if op == "gte":
            return float(value) >= float(target)
        if op == "lte":
            return float(value) <= float(target)
        if op == "between":
            lo, hi = target
            return float(lo) <= float(value) <= float(hi)
    except (TypeError, ValueError):
        return False
    return False


def applies_to(rule: dict, row: dict) -> bool:
    """Every condition holds. Evaluated MECHANICALLY, with no model in the loop
    -- an LLM asked "does this rule apply" is the experience-following failure
    arriving through the door this module locked."""
    conds = rule.get("applies_when") or []
    return bool(conds) and all(condition_holds(c, row) for c in conds)


def _direction_matched(rule: dict, row: dict) -> bool | None:
    """Did the row go the way the rule said? None when the row cannot say."""
    direction = (rule.get("predicts") or {}).get("direction")
    if row.get("outcome") is None:
        return None
    out = int(row["outcome"]) == 1
    if direction == "higher":
        return out
    if direction == "lower":
        return not out
    if direction == "unchanged_vs_control":
        vc = row.get("vs_control")
        if vc is None:
            return None
        return abs(float(vc)) < 1e-9
    return None


def _firings(rule: dict, rows: Iterable[dict]) -> list[tuple[dict, bool]]:
    """(row, did the stated direction hold) for every row the rule fires on."""
    out = []
    for row in rows:
        if not applies_to(rule, row):
            continue
        matched = _direction_matched(rule, row)
        if matched is None:
            continue
        out.append((row, bool(matched)))
    return out


def pool_match_rate(rule: dict, rows: Iterable[dict]) -> float | None:
    """How often the rule's stated direction holds across the WHOLE pool.

    This is the probability a forecaster with no rule would have quoted, and it
    is what the rule has to beat. Pass `pool_rate` to `score_rule` computed
    from rows resolved BEFORE the scoring window when the run is
    point-in-time; the default here is the whole pool, which is right for a
    synthetic or a retrospective read and is what the payload says it did.
    """
    hits = tot = 0
    for row in rows:
        matched = _direction_matched(rule, row)
        if matched is None:
            continue
        tot += 1
        hits += int(bool(matched))
    return (hits / tot) if tot else None


def score_rule(rule: dict, rows: Iterable[dict], *,
               pool_rate: float | None = None) -> dict:
    """The rule's OWN Brier over the rows it fires on, against the base rate.

    The rule is a forecaster that says `confidence` for "the stated direction
    holds", and the outcome is whether it did: `p = confidence` on every
    firing, `o = 1` when the direction held.

    WHY THE BAR IS THE POOL BASE RATE AND NOT THE FIRED SUBSET'S OWN
    CLIMATOLOGY. The spec scores a rule against `brier_decomposition`'s
    `beats_climatology`, which is computed on the SAME fired rows. Work the
    algebra: for a CONSTANT forecast `c` on a subset whose hit rate is `b`, the
    Brier is `b(1-c)^2 + (1-b)c^2`, minimised at `c = b` where it equals
    exactly `b(1-b)` -- that subset's own climatology. A constant-probability
    rule can therefore TIE that bar and never beat it, so `GENERALISED` would
    be unreachable and the gate could not go green, which this repository
    treats as a broken gate rather than a strict one. What a rule genuinely
    does is SELECT a subset where the direction holds more often than it does
    in general, so the comparison that carries information is against the base
    rate of the WHOLE POOL, quoted on the same fired rows. Both numbers are
    reported and the pool one is the gate.
    """
    rows = list(rows)
    conf = float(rule.get("confidence") or 0.5)
    fired = _firings(rule, rows)
    ps = [conf] * len(fired)
    os_ = [1.0 if m else 0.0 for _, m in fired]
    dec = CAL.brier_decomposition(ps, os_) if ps else {
        "n": 0, "brier": None, "decomposition": "insufficient_n",
        "reason": "the rule never fired", "climatology_brier": None,
        "base_rate": None}
    rate = pool_rate if pool_rate is not None else pool_match_rate(rule, rows)
    brier = dec.get("brier")
    base_brier = (None if (rate is None or not ps)
                  else sum((rate - o) ** 2 for o in os_) / len(os_))
    bss = (1.0 - brier / base_brier) if (base_brier and brier is not None
                                         and base_brier > 0) else None
    return {"n_fired": len(fired), "p_values": ps, "outcomes": os_,
            "brier": _r(brier, 6),
            "pool_base_rate": _r(rate, 6),
            "base_rate_brier": _r(base_brier, 6),
            "beats_base_rate": (None if (brier is None or base_brier is None)
                                else bool(brier < base_brier)),
            "fired_subset_climatology_brier": _r(dec.get("climatology_brier"), 6),
            "fired_subset_hit_rate": _r(dec.get("base_rate"), 6),
            "climatology_note": (
                "`fired_subset_climatology_brier` is a bar a constant forecast "
                "can only TIE; the gate is `beats_base_rate`, which asks "
                "whether the rule's conditions selected a subset where the "
                "direction holds more often than in the pool"),
            "decomposition": dec.get("decomposition"),
            "reliability": _r(dec.get("reliability"), 6),
            "resolution": _r(dec.get("resolution"), 6),
            "uncertainty": _r(dec.get("uncertainty"), 6),
            "bss": _r(bss, 6),
            "fired_rows": [r for r, _ in fired]}


def prompt_weight(bss: float | None, *, state: str = "CANDIDATE") -> float:
    """How much a rule may move a live forecast. THE GUARD IS THE CAP.

    Never retrieval similarity, never recency, never the model's own stated
    confidence: a measured Brier skill score against the base rate, clamped to
    [0, MAX_RULE_WEIGHT]. A `CANDIDATE` (too few firings to have a skill
    number) weighs ZERO -- it may be shown, labelled unproven, and contributes
    nothing to a stated confidence. `NOT_BETTER_THAN_NOISE` likewise, no matter
    how closely it matches the situation in front of it.
    """
    if state in ("CANDIDATE", "NOT_BETTER_THAN_NOISE", "STALE"):
        return 0.0
    if bss is None or not math.isfinite(float(bss)):
        return 0.0
    return float(max(0.0, min(float(bss), MAX_RULE_WEIGHT)))


def generalisation_state(rule: dict, fired_rows: Sequence[dict], *,
                         pool_rate: float | None = None) -> dict:
    """Does the rule survive on a mechanism family it was NOT distilled from?

    Four states and every one of them can be reached, which is the point:
    `UNTESTED` (distilled from a single family, so it has not been given the
    chance), `INSUFFICIENT_HELDOUT_N` (it has, but not enough firings yet),
    `GENERALISED`, `NOT_GENERALISED`. The last is a STATE, not a deletion: the
    rule keeps firing and keeps being scored in-family.
    """
    home = set(rule.get("evidence_families") or [])
    if not home:
        home = {rule.get("mechanism_family")} - {None}
    held = [r for r in fired_rows
            if mechanism_family(r.get("mechanism_id") or r.get("family_id"))
            not in home]
    out = {"n_families_in_evidence": len(home),
           "evidence_families": sorted(home),
           "n_heldout_firings": len(held),
           "held_out_hit_rate": (round(len(held) / len(fired_rows), 4)
                                 if fired_rows else None)}
    if len(home) < 2:
        return {**out, "generalisation": "UNTESTED",
                "why": ("distilled from a single mechanism family; the "
                        "held-out question has not been asked yet")}
    if len(held) < MIN_HELDOUT_FIRINGS:
        return {**out, "generalisation": "INSUFFICIENT_HELDOUT_N",
                "why": (f"{len(held)} held-out firings, {MIN_HELDOUT_FIRINGS} "
                        f"needed. A gate that can go green, once it fires.")}
    scored = score_rule(rule, held, pool_rate=pool_rate)
    return {**out, "generalisation": ("GENERALISED" if scored["beats_base_rate"]
                                      else "NOT_GENERALISED"),
            "held_out_brier": scored["brier"],
            "held_out_base_rate_brier": scored["base_rate_brier"],
            "why": ("held-out Brier beats the pool base rate"
                    if scored["beats_base_rate"]
                    else "held-out Brier does not beat the pool base rate; the "
                         "rule is KEPT and keeps being scored in-family "
                         "(losers are studied as hard as winners)")}


def noise_floor(shuffled_rules: Sequence[dict], rows: Sequence[dict]) -> dict:
    """The aggregate Brier of rules distilled from randomly RE-PAIRED rows.

    Expected to land on climatology within sampling noise. A real rule whose
    own Brier interval covers this number is `NOT_BETTER_THAN_NOISE`, which
    says something different from `NOT_GENERALISED`: one says the rule does
    not transfer, this one says the PIPELINE extracted nothing a random
    pairing would not also have produced.
    """
    rows = list(rows)
    ps, os_ = [], []
    for rule in shuffled_rules:
        scored = score_rule(rule, rows)
        ps.extend(scored["p_values"])
        os_.extend(scored["outcomes"])
    if not ps:
        return {"noise_floor_brier": None, "n": 0,
                "status": ("no shuffled rule ever fired; the floor is "
                           "UNMEASURED and a rule cannot be compared to it")}
    dec = CAL.brier_decomposition(ps, os_)
    return {"noise_floor_brier": _r(dec["brier"], 6), "n": dec["n"],
            "climatology_brier": _r(dec["climatology_brier"], 6),
            "status": "ok"}


def _bootstrap_ci(ps, os_, *, n_boot: int = 400, seed: int = 7) -> tuple:
    rng = random.Random(seed)
    n = len(ps)
    if n < 2:
        return (None, None)
    draws = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        draws.append(sum((ps[i] - os_[i]) ** 2 for i in idx) / n)
    draws.sort()
    return (round(draws[int(0.025 * n_boot)], 6),
            round(draws[int(0.975 * n_boot) - 1], 6))


def against_noise(scored: dict, floor: dict) -> str:
    """`NOT_BETTER_THAN_NOISE` says something different from `NOT_GENERALISED`.

    One says the rule does not transfer; this one says the PIPELINE extracted
    nothing a random pairing would not have produced. A rule whose Brier sits
    inside the floor's interval is the second.
    """
    fl = floor.get("noise_floor_brier")
    if fl is None or scored.get("brier") is None:
        return "UNMEASURED"
    lo, hi = scored.get("brier_ci_lo"), scored.get("brier_ci_hi")
    if lo is None or hi is None:
        return "UNMEASURED"
    return "NOT_BETTER_THAN_NOISE" if lo <= fl <= hi else "BETTER_THAN_NOISE"


# ----------------------------------------------------------------- writers

def rule_row(candidate: dict, scored: dict, gen: dict, *, month: str,
             rule_id: str, state: str, weight: float,
             noise: dict | None = None) -> dict:
    """One `learned_rules.jsonl` row.

    The field NAMES echo `PredictionRecord` on purpose: `resolution_date`,
    `resolved_at`, `outcome`. That is what lets `ledger_retrieval.visible_at`
    gate a rule row with the code that already gates a forecast, instead of a
    second predicate that can drift from the first.
    """
    last = _month_end(month)
    return {
        "rule_id": rule_id,
        "created_utc": _now(),
        "rule_text": candidate.get("rule_text"),
        "applies_when": candidate.get("applies_when") or [],
        "predicts": candidate.get("predicts") or {},
        "confidence": _r(candidate.get("confidence"), 4),
        "state": state,
        "brier": scored.get("brier"),
        "climatology_brier": scored.get("climatology_brier"),
        "noise_floor_brier": (noise or {}).get("noise_floor_brier"),
        "bss": scored.get("bss"),
        "n_fired": scored.get("n_fired"),
        "resolution_date": last,
        "resolved_at": _now()[:10],
        "outcome": None,
        "generalisation": gen.get("generalisation"),
        "held_out_hit_rate": gen.get("held_out_hit_rate"),
        "evidence_families": gen.get("evidence_families"),
        "prompt_weight": _r(weight, 4),
        "evidence_pairs": candidate.get("evidence_pairs") or [],
        "pair_kind": candidate.get("pair_kind"),
        "pairing_key": candidate.get("pairing_key"),
        "prompt_hash": candidate.get("prompt_hash"),
        "month": month,
        "schema_version": SCHEMA_VERSION,
    }


def _month_end(month: str) -> str:
    """The last calendar day of `month`. `calendar.monthrange` rather than an
    arithmetic guess, because February is where a hand-rolled one fails and a
    resolution date that is one day wrong is a retrieval gate that is one day
    wrong."""
    y, m = (int(x) for x in str(month).split("-")[:2])
    return str(date(y, m, calendar.monthrange(y, m)[1]))


def append_rules(rows: Sequence[dict], path: Path | None = None) -> Path:
    """Append-only. A rule is never rewritten and never removed; a changed
    verdict is a NEW row and the reader takes the latest per `rule_id`."""
    p = Path(path or LEARNED_RULES)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    return p


def render_month(month: str, rows: Sequence[dict], meta: dict) -> str:
    """`LEARNED_<YYYY-MM>.md` -- plain markdown, no new Optimus parser needed.

    `NOT_GENERALISED` and `NOT_BETTER_THAN_NOISE` get the same block shape and
    the same prominence as `GENERALISED`. A file that printed only the winners
    would be the gallery of survivors CLAUDE.md rule 4 exists to forbid.
    """
    out = [f"# LEARNED_{month}.md -- distilled rules from {month}'s graded ledger",
           ""]
    floor = meta.get("noise_floor") or {}
    out.append(f"Noise floor (shuffled-pair distillation, seed "
               f"{meta.get('shuffle_seed')}): Brier "
               f"{floor.get('noise_floor_brier')} (climatology "
               f"{floor.get('climatology_brier')})")
    out.append(f"Pairs: {meta.get('pairs_sampled')} real of "
               f"{meta.get('pairs_possible')} possible, "
               f"{meta.get('n_shuffled', 0)} shuffled, "
               f"{meta.get('dropped_degenerate', 0)} dropped as degenerate")
    out.append(f"Distillation model: {meta.get('model')}, prompt contract "
               f"{meta.get('contract_hash')}")
    if meta.get("pending_model"):
        out.append("")
        out.append(f"**PENDING_MODEL** -- {meta['pending_model']}")
    out.append("")
    for state in ("GENERALISED", "NOT_GENERALISED", "NOT_BETTER_THAN_NOISE",
                  "CANDIDATE", "STALE"):
        block = [r for r in rows if r.get("state") == state]
        out.append(f"## {state} (n={len(block)})")
        out.append("")
        for r in block:
            out.append(f"### {r['rule_id']}")
            out.append(f"- Text: \"{r.get('rule_text')}\"")
            out.append(f"- Applies when: {json.dumps(r.get('applies_when'), default=str)}")
            pred = r.get("predicts") or {}
            out.append(f"- Predicts: {pred.get('observable')} -> "
                       f"{pred.get('direction')}")
            out.append(f"- Brier: {r.get('brier')} (n={r.get('n_fired')}, "
                       f"climatology {r.get('climatology_brier')}, noise floor "
                       f"{r.get('noise_floor_brier')})")
            out.append(f"- Held-out families: {r.get('evidence_families')}, "
                       f"hit rate {r.get('held_out_hit_rate')}")
            out.append(f"- Confidence cap (prompt_weight): {r.get('prompt_weight')}")
            out.append(f"- Evidence pairs: {json.dumps(r.get('evidence_pairs'), default=str)}")
            out.append("")
        if not block:
            out.append("(none this month)")
            out.append("")
    return "\n".join(out) + "\n"


def write_month(month: str, rows: Sequence[dict], meta: dict,
                dir_: Path | None = None) -> Path:
    """The M2 pair block, written INSIDE the one month file.

    Until 2026-09-26 this overwrote `LEARNED_<month>.md` with the pair block
    alone, so a PENDING_MODEL night would have erased every graded-ledger rule
    the same file listed. The file is now regenerated from `learned_rules.jsonl`
    and `learn_runs.jsonl` (in `dir_`), with this block as its M2 section.
    """
    d = Path(dir_ or BRAIN)
    return write_learned(month, rules_path=d / "learned_rules.jsonl",
                         runs_path=d / "learn_runs.jsonl", dir_=d,
                         pair_text=render_month(month, rows, meta))


def _log_m2_run(month: str, status: str, reason: str | None, meta: dict,
                n_rules: int, dir_: Path | None) -> None:
    _append_jsonl(Path(dir_ or BRAIN) / "learn_runs.jsonl", {
        "job": "M2_pairs", "as_of": f"{month}-01" if len(month) == 7 else month,
        "written_utc": _now(), "status": status, "reason": reason,
        "n_rules_written": n_rules, "meta": meta})


# ------------------------------------------------------------- the night job

def _probe(backend: str) -> str | None:
    """Is the local reader answering? A refusal is a finding, not a crash.
    This never STARTS the server -- the desktop shell owns llama-server."""
    try:
        from backend.services import free_inference as FI
        FI.complete(backend, "Answer with the single word OK.",
                    system="Answer in English.", max_tokens=4,
                    temperature=0.0, purpose="M2_probe")
        return None
    except Exception as exc:                                   # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


def _ledger_and_memory() -> tuple[list[dict], list[dict], dict]:
    from backend.services import belief_state as BS
    from learner import evidence_memory as EM
    ledger = BS.read_predictions()
    memory = [r for r in EM.read_all() if isinstance(r, dict)]
    resolved = [r for r in ledger
                if r.get("outcome") is not None and not r.get("void_reason")]
    return ledger, memory, {
        "ledger_rows": len(ledger), "ledger_resolved": len(resolved),
        "memory_rows": len(memory),
        "min_n_for_decomposition": CAL.MIN_N_FOR_DECOMPOSITION,
        "has_enough_resolved_for_a_first_brier":
            len(resolved) >= CAL.MIN_N_FOR_DECOMPOSITION,
    }


def M2_distill(smoke: bool = False, run: int = 1, *, month: str | None = None,
               backend: str = "local_gguf", complete_fn: Callable | None = None,
               out_dir: Path | None = None, rules_path: Path | None = None,
               write: bool = True) -> dict:
    """The night job. Pairs, distils if the reader is up, scores, writes.

    With the reader DOWN this still does everything that does not need it and
    says `PENDING_MODEL` by name, with the pair pool frozen and hashed so the
    run that happens when the model is up asks the same question.
    """
    month = month or f"{datetime.now(timezone.utc):%Y-%m}"
    # DERIVED FROM THE MONTH, not chosen: a shuffle seed picked after seeing
    # which shuffle flatters the result is not a shuffle. `AEGIS_RULE_SHUFFLE_
    # SEED` overrides it for a reproduction, and a non-numeric override is a
    # REFUSAL rather than a silent fall back to the derived seed -- a run that
    # believed it was reproducing and was not is the worse failure.
    env = os.getenv("AEGIS_RULE_SHUFFLE_SEED")
    if env:
        try:
            seed = int(env)
        except ValueError as exc:
            raise DistillationRefused(
                f"AEGIS_RULE_SHUFFLE_SEED={env!r} is not an integer; a seed "
                f"the code cannot read is a run that cannot be reproduced"
            ) from exc
    else:
        seed = int(hashlib.sha1(month.encode()).hexdigest()[:6], 16)
    ledger, memory, counts = _ledger_and_memory()
    rows = ledger + memory
    if smoke:
        rows = rows[:4000]
    built = make_pairs(rows, seed=seed)
    shuffled = shuffled_pairs(built, seed=seed)
    pool_hash = hashlib.sha256(
        json.dumps([p["pairing_key"] + "|" + p["winner_id"] + "|" + p["loser_id"]
                    for p in built["pairs"]], sort_keys=True).encode()
    ).hexdigest()[:16]

    payload = {
        "job": "M2_distill", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "month": month, "run": run,
        "pairs": {k: v for k, v in built.items() if k != "pairs"},
        "n_shuffled_pairs": len(shuffled["pairs"]),
        "pair_pool_sha256": pool_hash,
        "ledger": counts,
        "first_rule_with_its_own_brier": None,
        "written_utc": _now(),
    }

    refusal = None if complete_fn else _probe(backend)
    if complete_fn is None and refusal is not None:
        payload.update({
            "model_state": "PENDING_MODEL",
            "model_refusal": refusal,
            "first_rule_with_its_own_brier": (
                "CANNOT DETERMINE: no rule TEXT was generated because the "
                "local reader is not answering, and this job does not start "
                "it (the desktop shell owns llama-server)."),
            "pending_when_the_reader_is_up": [
                f"distil {built['pairs_sampled']} real pairs (pool frozen at "
                f"sha256 {pool_hash})",
                f"distil {len(shuffled['pairs'])} SHUFFLED pairs at seed "
                f"{shuffled.get('shuffle_seed')} for the noise floor",
                "score every candidate on the NEXT month's rows, gate on the "
                "held-out mechanism family, cap the prompt weight by the Brier "
                "skill score",
                f"one command: python -m learner.rule_distillation --month {month}",
            ],
            "headline": (
                f"{built['pairs_sampled']} real pairs of "
                f"{built['pairs_possible']} possible across "
                f"{len(built['by_kind'])} pair kinds, frozen at sha256 "
                f"{pool_hash}; NO model call was made"),
            "verdict": (
                "PENDING_MODEL: the pairing, the leaked-field guard, the "
                "scoring, the generalisation gate and both writers are built "
                "and exercised; only the rule TEXT needs the reader. "
                + ("The ledger also has %d resolved rows against the %d a "
                   "decomposition needs, so the first rule's own Brier is "
                   "CANNOT DETERMINE on this checkout regardless of the model."
                   % (counts["ledger_resolved"],
                      CAL.MIN_N_FOR_DECOMPOSITION))),
        })
        if write:
            meta = {
                "noise_floor": {}, "shuffle_seed": shuffled.get("shuffle_seed"),
                "pairs_sampled": built["pairs_sampled"],
                "pairs_possible": built["pairs_possible"],
                "n_shuffled": len(shuffled["pairs"]),
                "dropped_degenerate": built["dropped_degenerate"],
                "model": f"{backend} (NOT ANSWERING)",
                "contract_hash": pool_hash,
                "pending_model": refusal,
            }
            _log_m2_run(month, "LEARN_DEGRADED",
                        f"model refused (M2 pairs): {refusal}", meta, 0, out_dir)
            payload["learned_md"] = str(write_month(month, [], meta, dir_=out_dir))
        return payload

    fn = complete_fn
    if fn is None:
        from backend.services import free_inference as FI
        fn = FI.complete
    real = candidates_from_pairs(built["pairs"], complete_fn=fn, backend=backend)
    shuf = candidates_from_pairs(shuffled["pairs"], complete_fn=fn,
                                 backend=backend)
    floor = noise_floor(shuf["candidates"], rows)

    out_rows = []
    for i, cand in enumerate(real["candidates"], start=1):
        scored = score_rule(cand, rows)
        gen = generalisation_state(
            {**cand, "evidence_families": sorted(
                {mechanism_family(r.get("mechanism_id") or r.get("family_id"))
                 for r in scored["fired_rows"]} or {cand["mechanism_family"]})},
            scored["fired_rows"])
        state = "CANDIDATE"
        if scored["n_fired"] >= CAL.MIN_N_FOR_DECOMPOSITION:
            lo, hi = _bootstrap_ci(scored["p_values"], scored["outcomes"],
                                   seed=seed)
            scored["brier_ci_lo"], scored["brier_ci_hi"] = lo, hi
            if against_noise(scored, floor) == "NOT_BETTER_THAN_NOISE":
                state = "NOT_BETTER_THAN_NOISE"
            else:
                state = gen["generalisation"] if gen["generalisation"] in (
                    "GENERALISED", "NOT_GENERALISED") else "CANDIDATE"
        weight = prompt_weight(scored["bss"], state=state)
        out_rows.append(rule_row(cand, scored, gen, month=month,
                                 rule_id=f"RULE-{month}-{i:04d}",
                                 state=state, weight=weight, noise=floor))
    if write and out_rows:
        payload["learned_rules"] = str(append_rules(out_rows, rules_path))
    if write:
        meta = {
            "noise_floor": floor, "shuffle_seed": shuffled.get("shuffle_seed"),
            "pairs_sampled": built["pairs_sampled"],
            "pairs_possible": built["pairs_possible"],
            "n_shuffled": len(shuffled["pairs"]),
            "dropped_degenerate": built["dropped_degenerate"],
            "model": backend, "contract_hash": pool_hash,
        }
        _log_m2_run(month, "LEARNED" if out_rows else "LEARN_DEGRADED",
                    None if out_rows else "model returned no valid pair rule",
                    meta, len(out_rows), out_dir)
        payload["learned_md"] = str(write_month(month, out_rows, meta,
                                                dir_=out_dir))
    scored_rules = [r for r in out_rows if r.get("brier") is not None]
    payload.update({
        "model_state": "ok", "refusals": real["refusals"],
        "shuffled_refusals": shuf["refusals"],
        "n_candidates": len(real["candidates"]),
        "n_shuffled_candidates": len(shuf["candidates"]),
        "noise_floor": floor,
        "rules": out_rows,
        "first_rule_with_its_own_brier": (
            scored_rules[0]["rule_id"] if scored_rules else
            f"CANNOT DETERMINE: no rule reached "
            f"{CAL.MIN_N_FOR_DECOMPOSITION} firings; the ledger holds "
            f"{counts['ledger_resolved']} resolved rows"),
        "headline": (f"{len(out_rows)} rules from {built['pairs_sampled']} "
                     f"pairs; {len(scored_rules)} carry their own Brier; "
                     f"noise floor {floor.get('noise_floor_brier')}"),
        "verdict": ("DISTILLED: rules are FORECASTS with their own Brier, "
                    "never allocations, and none of them sizes anything."),
    })
    return payload


# ======================================================================
# LANE M: DISTIL THE GRADED LEDGER (2026-09-26, adjudication row 9)
# ======================================================================
#
# THE FAILURE THIS CLOSES
# -----------------------
# For a month the only writer of `learned_rules.jsonl` was the pair path above,
# and it needs the local reader for rule TEXT. The reader refused the
# connection, the job said PENDING_MODEL, and `LEARNED_2026-09.md` distilled
# **0 rules** while 17,484 graded forecasts sat in the ledger. The 126 daily
# `LEARNED_<date>.md` lines were heartbeats. A learning layer that learns only
# when one process on one laptop is up has learned nothing.
#
# WHAT THIS PATH DOES DIFFERENTLY
# -------------------------------
# * The NUMBERS are computed here, never by a model: every graded row, grouped
#   by (group x observable x horizon), scored with `forecast_reputation`'s own
#   held-out convention (later half by `made_at`, climatology = the scored
#   rows' base rate) so a rule's skill and the reputation receipt's skill are
#   one number, not two implementations of it.
# * The model writes only the SENTENCE, and a sentence that quotes a
#   percentage the cited fact does not contain is REFUSED (invented numbers).
# * Local first; when the local reader refuses, times out or answers with
#   nothing usable, the same batch goes to DeepSeek through
#   `llm_analyzer._call_llm` (the one API path, language pin central). Every
#   batch records which model answered, `local_status`, and the spend.
# * Hindsight-safe by construction: only rows with `resolved_at` STRICTLY
#   BEFORE the rule's date are read, and each rule says so.
# * A night that writes 0 rules writes `LEARN_DEGRADED` with the reason --
#   model refused / no new graded rows / cap -- never a heartbeat.

LEDGER_RULE_SCHEMA = "learned-rule-ledger-1.0.0"
LEARN_RUNS = BRAIN / "learn_runs.jsonl"

#: Families that are a PROCESS (a pipeline with tools), not a thematic persona.
#: Everything else in the ledger is pooled as `personas` at class level, which
#: is the split §64 found (+8.97% vs -27.98%).
PROCESS_FAMILIES = ("investigator",)
EXCLUDED_FROM_PERSONAS = ("investigator", "why_moved", "review", "thesis_card")

_PCT = re.compile(r"([+\-−]?\d+(?:\.\d+)?)\s*%")


def _cfg():
    from backend import config as C
    return C


def _family_of(arm: str) -> str:
    arm = str(arm or "")
    return "investigator" if arm.startswith("investigator:") else arm.split(":")[0]


def graded_rows_before(rows: Iterable[dict], as_of: str) -> list[dict]:
    """Graded, un-voided, scorable rows RESOLVED STRICTLY BEFORE `as_of`.

    The same asymmetry `ledger_retrieval.visible_at` enforces: a row graded on
    the rule's own date is not yet evidence for it.
    """
    from backend.services.ledger_retrieval import _as_date
    from backend.services import forecast_reputation as FR
    cut = _as_date(as_of)
    if cut is None:
        raise DistillationRefused(f"as_of {as_of!r} is not a date")
    out = []
    for r in rows:
        if r.get("void_reason") or FR._outcome01(r.get("outcome")) is None:
            continue
        if not 0.0 <= FR._num(r.get("probability")) <= 1.0:
            continue
        g = _as_date(r.get("resolved_at") or r.get("graded_at"))
        if g is None or not g < cut:
            continue
        out.append(r)
    return out


def ledger_facts(rows: Sequence[dict], *, as_of: str,
                 min_n: int | None = None) -> list[dict]:
    """Every (group x observable x horizon) cell with >= `min_n` graded rows.

    Two levels: CLASS (`investigator` = the process; `personas` = every thematic
    specialist pooled) and FAMILY (each non-process specialist family). Numbers
    only -- no model is involved in anything this function returns.
    """
    import numpy as np
    from backend.services import forecast_reputation as FR
    min_n = int(min_n if min_n is not None else _cfg().LEARN_MIN_GROUP_N)
    usable = graded_rows_before(rows, as_of)
    g = FR.graded_frame_from_rows(usable)
    if g.empty:
        return []
    # graded_frame_from_rows keeps exactly the rows graded_rows_before kept
    # (same outcome and probability predicates), in order.
    g["resolved_on"] = [str(r.get("resolved_at") or r.get("graded_at"))[:10]
                        for r in usable]
    g["family"] = g["arm"].map(_family_of)
    g["klass"] = np.where(g["family"].isin(PROCESS_FAMILIES), g["family"],
                          np.where(g["family"].isin(EXCLUDED_FROM_PERSONAS),
                                   "", "personas"))
    facts: list[dict] = []
    for level, col in (("class", "klass"), ("family", "family")):
        sub = g[g[col].astype(str) != ""]
        if level == "family":
            sub = sub[~sub["family"].isin(PROCESS_FAMILIES)]
        for (grp, obs, h), cell in sub.groupby([col, "observable", "horizon_days"],
                                               sort=True, dropna=False):
            if len(cell) < min_n:
                continue
            full = FR._score(cell["p"].to_numpy(float), cell["y"].to_numpy(float))
            cell = cell.sort_values("made_at", kind="stable")
            test = cell.iloc[len(cell) // 2:]
            held = FR._score(test["p"].to_numpy(float), test["y"].to_numpy(float))
            days = sorted(str(d) for d in cell["made_day"].dropna().unique())
            try:
                hd = int(h)
            except (TypeError, ValueError):
                hd = None
            facts.append({
                "fact_key": f"{level}:{grp}|{obs}|h{hd}",
                "source": "graded_ledger", "level": level, "group": str(grp),
                "n_arms": int(cell["arm"].nunique()), "observable": obs,
                "kind": ("direction" if obs in ("return_sign", FR.DIRECTION_OBSERVABLE)
                         else "magnitude" if obs in (FR.MAGNITUDE_OBSERVABLE,
                                                     "drawdown_exceeds")
                         else "other"),
                "horizon_days": hd,
                "n": int(len(cell)), "n_heldout": int(held["n"]),
                "brier": _r(held["brier"], 5), "climatology_brier": _r(held["clim"], 5),
                "skill": _r(held["skill"], 4), "skill_all": _r(full["skill"], 4),
                "brier_all": _r(full["brier"], 5),
                "disc": _r(held["disc"], 4), "base_rate": _r(full["base_rate"], 4),
                "made_from_dates": days, "n_date_blocks": len(days),
                "resolved_through": max(cell["resolved_on"]),
                "split": ("held out: later half by made_at; climatology = base "
                          "rate of the scored rows"),
            })
    return facts


def autopsy_facts(autopsy: dict | None, *, as_of: str,
                  path: str | None = None) -> list[dict]:
    """The decision grade (PROBE vs REFUSED), from `decisions/autopsy_*.json`.

    Not a probability forecast, so `brier`/`skill` are None and the metric is
    named. Hindsight-safe only if the autopsy was written before `as_of`.
    """
    if not isinstance(autopsy, dict):
        return []
    written = str(autopsy.get("written_utc") or "")[:10]
    if not written or not written < str(as_of)[:10]:
        return []
    out = []
    for h, row in sorted((autopsy.get("headline") or {}).items(),
                         key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0):
        if not isinstance(row, dict) or not row.get("n_date_blocks"):
            continue
        out.append({
            "fact_key": f"decision:{row.get('pair')}|excess_vs_universe_median|h{h}",
            "source": "decision_autopsy", "level": "decision",
            "group": str(row.get("pair")), "n_arms": None,
            "observable": "excess_vs_universe_median",
            "kind": "decision_grade", "horizon_days": int(h),
            "n": int((row.get("n_rows_PROBE") or 0) + (row.get("n_rows_REFUSED") or 0)),
            "n_heldout": None, "brier": None, "climatology_brier": None,
            "skill": None, "skill_all": None, "disc": None, "base_rate": None,
            "mean_gap_per_day": _r(row.get("pooled_vs_universe_median"), 5),
            "day_matched_t": _r(row.get("day_matched_t"), 3),
            "made_from_dates": sorted((row.get("day_matched_by_day") or {}).keys()),
            "n_date_blocks": int(row.get("n_date_blocks") or 0),
            "resolved_through": written, "receipt": path,
            "metric": "mean excess return per decision day, PROBE minus REFUSED",
        })
    return out


#: Below this many distinct decision dates a POSITIVE number is not a result
#: (CANON §58: n_effective counts date blocks, not rows).
LEARN_MIN_DATE_BLOCKS = 5
#: |discrimination| under this (2pp) is "cannot tell cases apart".
NO_DISCRIMINATION = 0.02

VERDICTS = {
    "SKILL": "beats the base rate held out on enough date blocks: may be weighted "
             "at its measured skill",
    "UNPROVEN": "positive but on too few date blocks: not a result yet, weight 0",
    "NO_DISCRIMINATION": "cannot tell cases apart: weight 0",
    "NO_SKILL": "worse than always predicting the base rate: weight 0",
    "NOT_A_RESULT": "too few date blocks to read either way",
}


def fact_verdict(f: dict) -> str:
    """The verdict is COMPUTED; the model may only phrase it.

    The first real run (2026-09-26) let a 7B model pick the stance and it wrote
    "Trust the forecast; skill -74.08%". Numbers can be checked against the
    fact; so can the stance, once the stance is a number's function.
    """
    blocks = int(f.get("n_date_blocks") or 0)
    if f.get("source") == "decision_autopsy":
        return "NOT_A_RESULT" if blocks < LEARN_MIN_DATE_BLOCKS else (
            "SKILL" if (f.get("mean_gap_per_day") or 0) > 0 else "NO_SKILL")
    skill = f.get("skill")
    if skill is not None and skill > 0:
        return "SKILL" if blocks >= LEARN_MIN_DATE_BLOCKS else "UNPROVEN"
    if f.get("disc") is not None and abs(float(f["disc"])) < NO_DISCRIMINATION:
        return "NO_DISCRIMINATION"
    return "NO_SKILL"


_NEG = re.compile(r"\b(do not|don't|never|not trust|zero|ignore|not a result|"
                  r"anti-?signal|no skill|no discrimination|cannot|distrust|"
                  r"weight 0|0 weight|not yet|unproven|discard|worse)\b", re.I)
_POS = re.compile(r"\b(trust|trusted|rely|use|used|usable|may be|weight|size|keep)\b",
                  re.I)
_VERDICT_WORD = re.compile(r"\b(NO_SKILL|NO_DISCRIMINATION|NOT_A_RESULT|UNPROVEN|SKILL)\b")
#: An arm label (`D_all`, `A_snapshot`): the model saw them in context and
#: pinned them onto persona rules on the first real run. A rule is about its
#: fact's GROUP, never an arm the fact does not name.
_ARM_LABEL = re.compile(r"\b[A-Z]_[a-z][a-z_]*\b")


def stance_mismatch(text: str, verdict: str) -> str | None:
    """None if the sentence's stance agrees with the computed verdict.

    The second real run (2026-09-26) wrote "SKILL: may be used at -74.08%" for
    a NO_DISCRIMINATION fact: a named verdict must be the fact's verdict.
    """
    named = set(_VERDICT_WORD.findall(text or ""))
    if named and named != {verdict}:
        return f"names verdict {sorted(named)} for a {verdict} fact"
    arm = _ARM_LABEL.search(text or "")
    if arm:
        return f"names arm {arm.group(0)!r}, not the fact's group"
    neg = bool(_NEG.search(text or ""))
    if verdict == "SKILL" and neg:
        return f"says do-not-use for a {verdict} fact"
    if verdict != "SKILL" and not neg and _POS.search(text or ""):
        return f"says use/trust for a {verdict} fact"
    return None


def _fact_numbers_pct(f: dict) -> list[float]:
    """Every number of a fact a rule may quote as a percentage."""
    return [float(f[k]) * 100.0
            for k in ("skill", "skill_all", "base_rate", "mean_gap_per_day", "disc")
            if f.get(k) is not None]


def select_facts(facts: Sequence[dict], *, max_facts: int | None = None) -> list[dict]:
    """Class cells and decision grades first, then the strongest family cells."""
    max_facts = int(max_facts if max_facts is not None else _cfg().LEARN_MAX_FACTS)
    first = [f for f in facts if f["level"] in ("class", "decision")]
    rest = [f for f in facts if f["level"] not in ("class", "decision")]
    rest.sort(key=lambda f: -(abs(f.get("skill") or 0.0) * math.sqrt(f["n"])))
    return (first + rest)[:max_facts]


def _fact_line(i: int, f: dict) -> str:
    if f["source"] == "decision_autopsy":
        return (f"F{i} | decision grade {f['group']} | h={f['horizon_days']} "
                f"session(s) | n={f['n']} rows over {f['n_date_blocks']} date blocks "
                f"| mean gap {(f['mean_gap_per_day'] or 0) * 100:+.2f}% per day vs "
                f"universe median | day-matched t {f['day_matched_t']} | "
                f"VERDICT {fact_verdict(f)}")
    who = ("investigator (a tool-using PROCESS, %d arms)" % f["n_arms"]
           if f["group"] == "investigator" else
           "personas (all thematic specialists pooled, %d arms)" % f["n_arms"]
           if f["group"] == "personas" else f"specialist family {f['group']}")
    return (f"F{i} | {who} | {f['observable']} ({f['kind']}) | h={f['horizon_days']} "
            f"| n={f['n']} graded (held-out {f['n_heldout']}) | base rate "
            f"{(f['base_rate'] or 0) * 100:.1f}% | held-out skill vs climatology "
            f"{(f['skill'] or 0) * 100:+.2f}% | discrimination "
            f"{(f['disc'] or 0) * 100:+.1f}pp | {f['n_date_blocks']} date blocks | "
            f"VERDICT {fact_verdict(f)}")


LEARN_SYSTEM = (
    "You distil forecasting lessons for a trading research system from GRADED "
    "forecast statistics. Every number is already computed; you only write the "
    "sentence. Reply with JSON only.")


def learn_prompt(batch: Sequence[dict], context: str) -> str:
    lines = "\n".join(_fact_line(i, f) for i, f in enumerate(batch, start=1))
    return (
        f"Context: {context}\n\n"
        "Skill is the Brier skill score against always predicting the base rate "
        "(positive = better than the base rate, negative = worse). "
        "Discrimination is the mean stated probability when the event happened "
        "minus when it did not (near 0 = the forecaster cannot tell cases apart).\n\n"
        f"FACTS:\n{lines}\n\n"
        "Each fact ends with a VERDICT that is already decided: "
        + "; ".join(f"{k} = {v}" for k, v in VERDICTS.items()) + ".\n\n"
        "Write ONE rule per fact, at most 35 words, that states the verdict in "
        "plain words (SKILL: may be used at its measured weight; every other "
        "verdict: weight 0 / do not use / not a result yet), names who and which "
        "observable and horizon, and quotes the held-out skill (or the mean gap) "
        "copied exactly as printed. Quote no number that is not in that fact. "
        'Reply exactly: {"rules": [{"fact": "F1", "rule": "..."}, ...]}')


def verify_rule_numbers(text: str, fact: dict, *,
                        tol_pp: float | None = None) -> str | None:
    """None if every percentage in `text` is a number of `fact`; else why not."""
    tol = float(tol_pp if tol_pp is not None else _cfg().LEARN_NUMBER_TOL_PP)
    allowed = _fact_numbers_pct(fact)
    for m in _PCT.finditer(text or ""):
        raw = m.group(1).replace("−", "-")
        v = float(raw)
        signed = raw.startswith(("+", "-"))
        ok = any(abs(abs(v) - abs(a)) <= tol
                 and (not signed or (v >= 0) == (a >= 0) or abs(a) <= tol)
                 for a in allowed)
        if not ok:
            return f"quotes {m.group(0)!r}, which is not a number of {fact['fact_key']}"
    return None


def parse_rules(text: str | None,
                batch: Sequence[dict]) -> tuple[list[dict], list[str]]:
    """(valid [{fact, rule_text}], refusal reasons). Never raises."""
    obj = _parse_json(text or "")
    if not isinstance(obj, dict) or not isinstance(obj.get("rules"), list):
        return [], ['reply is not {"rules": [...]} JSON']
    ok, bad, seen = [], [], set()
    for item in obj["rules"]:
        if not isinstance(item, dict):
            bad.append("rule is not an object")
            continue
        fid = str(item.get("fact") or "").strip().upper()
        txt = str(item.get("rule") or "").strip()
        if (not fid.startswith("F") or not fid[1:].isdigit()
                or not 1 <= int(fid[1:]) <= len(batch)):
            bad.append(f"cites unknown fact {fid!r}")
            continue
        if fid in seen:
            bad.append(f"second rule for {fid}")
            continue
        if not txt or len(txt) > 400:
            bad.append(f"{fid}: empty or over-long rule")
            continue
        fact = batch[int(fid[1:]) - 1]
        why = verify_rule_numbers(txt, fact)
        if why is None and not _PCT.search(txt):
            why = "quotes no number (a rule must carry its skill)"
        if why is None:
            why = stance_mismatch(txt, fact_verdict(fact))
        if why:
            bad.append(f"{fid}: {why}")
            continue
        seen.add(fid)
        ok.append({"fact": fact, "rule_text": txt})
    return ok, bad


def _default_local(prompt: str) -> tuple[str, dict]:
    from backend.services import free_inference as FI
    C = _cfg()
    rep = FI.complete(C.LEARN_LOCAL_BACKEND, prompt, system=LEARN_SYSTEM,
                      max_tokens=int(C.LEARN_LOCAL_MAX_TOKENS), temperature=0.0,
                      timeout=int(C.LEARN_LOCAL_TIMEOUT_S), purpose=C.LEARN_PURPOSE)
    return rep.text, {"model": f"{rep.backend}/{rep.model}", "cost_usd": rep.cost_usd}


def _default_remote(prompt: str) -> tuple[str | None, dict]:
    """DeepSeek through `llm_analyzer._call_llm`: the one API path, whose
    language pin, refusal and telemetry are central (CLAUDE.md)."""
    from backend.services import llm_analyzer as LA
    C = _cfg()
    text = LA._call_llm(LEARN_SYSTEM, prompt, purpose=C.LEARN_PURPOSE,
                        validate=lambda t: _parse_json(t) is not None)
    return text, {"model": f"{LA._get_provider()}/{LA._DEEPSEEK_MODEL}"}


def _default_spend(since: str) -> dict:
    from backend.services import llm_telemetry as T
    return T.spend(since=since, purpose=_cfg().LEARN_PURPOSE)


def _hash_rule(row: dict) -> str:
    body = {k: v for k, v in row.items() if k not in ("rule_hash", "created_utc")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str)
                          .encode()).hexdigest()[:20]


def ledger_rule_row(fact: dict, rule_text: str, *, as_of: str, answered_by: str,
                    local_status: str, receipts: dict) -> dict:
    """One hashed `learned_rules.jsonl` row. Every number is the FACT's, never
    the model's; the model contributed `rule_text` only."""
    skill = fact.get("skill")
    resolved_through = fact.get("resolved_through")
    row = {
        "rule_id": f"LRULE-{as_of}-" + hashlib.sha1(
            fact["fact_key"].encode()).hexdigest()[:8],
        "created_utc": _now(),
        "rule_text": rule_text,
        "fact_key": fact["fact_key"], "source": fact["source"],
        "group": fact["group"], "observable": fact["observable"],
        "kind": fact["kind"], "horizon_days": fact["horizon_days"],
        "n": fact["n"], "n_heldout": fact.get("n_heldout"),
        "brier": fact.get("brier"), "climatology_brier": fact.get("climatology_brier"),
        "skill": skill, "skill_all": fact.get("skill_all"),
        "disc": fact.get("disc"), "base_rate": fact.get("base_rate"),
        "mean_gap_per_day": fact.get("mean_gap_per_day"),
        "day_matched_t": fact.get("day_matched_t"),
        "n_date_blocks": fact.get("n_date_blocks"),
        "made_from_dates": fact.get("made_from_dates") or [],
        "hindsight_safe": bool(resolved_through is not None
                               and str(resolved_through)[:10] < as_of),
        # `ledger_retrieval.visible_at` gates a rule on these, like a forecast.
        "resolution_date": resolved_through,
        "resolved_at": as_of, "outcome": None,
        "state": "MEASURED", "verdict": fact_verdict(fact),
        # THE CAP, not the number: a measured skill clamped to MAX_RULE_WEIGHT;
        # a negative or absent skill weighs 0.0 (shown, never weighted).
        "prompt_weight": _r(prompt_weight(skill, state="GENERALISED"), 4),
        "answered_by": answered_by, "local_status": local_status,
        "receipts": receipts, "as_of": as_of, "month": as_of[:7],
        "schema_version": LEDGER_RULE_SCHEMA,
    }
    if not row["hindsight_safe"]:
        raise DistillationRefused(
            f"{fact['fact_key']} was resolved through {resolved_through}, not "
            f"before {as_of}: a rule on its own date's grades is hindsight")
    row["rule_hash"] = _hash_rule(row)
    return row


def _read_jsonl(p: Path) -> list[dict]:
    if not Path(p).is_file():
        return []
    out = []
    for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _append_jsonl(p: Path, row: dict) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def render_learned(month: str, rules: Sequence[dict], runs: Sequence[dict],
                   pair_text: str | None = None) -> str:
    """`LEARNED_<month>.md`, regenerated from `learned_rules.jsonl` + the run log.

    The ledger rules come first because they are the ones that exist; the M2
    pair section follows, unchanged in shape.
    """
    out = [f"# LEARNED_{month}.md -- rules distilled from {month}'s graded ledger", ""]
    mine = [r for r in runs if str(r.get("as_of", ""))[:7] == month]
    last: dict[str, dict] = {}
    for r in mine:
        last[str(r.get("job"))] = r
    lr = last.get("ledger_distill")
    if lr:
        out.append(f"Last ledger distillation: {lr.get('as_of')} -- "
                   f"**{lr.get('status')}**"
                   + (f" -- {lr.get('reason')}" if lr.get("reason") else "")
                   + f" ({lr.get('n_rules_written', 0)} rules written; answered by "
                   f"{lr.get('answered_by')}; local {lr.get('local_status')}; "
                   f"DeepSeek ${lr.get('cost_usd')}"
                   + (" (lower bound)" if lr.get("cost_is_lower_bound") else "")
                   + ")")
    else:
        out.append("Last ledger distillation: never ran this month")
    for r in [r for r in mine if r.get("status") == "LEARN_DEGRADED"][-10:]:
        out.append(f"- LEARN_DEGRADED {r.get('as_of')} ({r.get('job')}): "
                   f"{r.get('reason')}")
    out.append("")
    led = [r for r in rules if r.get("schema_version") == LEDGER_RULE_SCHEMA
           and r.get("month") == month]
    latest: dict[str, dict] = {}
    for r in led:
        latest[r["fact_key"]] = r      # append-only file; the newest wins
    rows = sorted(latest.values(),
                  key=lambda r: ({"investigator": 0, "personas": 1}.get(
                                     str(r.get("group")),
                                     2 if r.get("source") == "decision_autopsy" else 3),
                                 -(abs(r.get("skill") or 0)
                                   * math.sqrt(r.get("n") or 0))))
    out.append(f"## MEASURED -- graded-ledger rules (n={len(rows)} current, "
               f"{len(led)} rows written this month)")
    out.append("")
    if not rows:
        out.append("(none this month)")
        out.append("")
    for r in rows:
        out.append(f"### {r['rule_id']} ({r['fact_key']})")
        out.append(f"- Rule ({r.get('verdict')}): \"{r['rule_text']}\"")
        if r.get("source") == "decision_autopsy":
            out.append(f"- Numbers: n={r['n']}, mean gap {r.get('mean_gap_per_day')}"
                       f"/day, t {r.get('day_matched_t')}, "
                       f"{r.get('n_date_blocks')} date blocks; Brier n/a (not a "
                       f"probability forecast)")
        else:
            out.append(f"- Numbers: n={r['n']} (held-out {r.get('n_heldout')}), "
                       f"Brier {r.get('brier')} vs climatology "
                       f"{r.get('climatology_brier')}, skill {r.get('skill')} "
                       f"(all rows {r.get('skill_all')}), disc {r.get('disc')}, "
                       f"{r.get('n_date_blocks')} date blocks")
        out.append(f"- Made from: {', '.join(r.get('made_from_dates') or [])}; "
                   f"resolved through {r.get('resolution_date')}; hindsight_safe "
                   f"{r.get('hindsight_safe')}; as of {r.get('as_of')}")
        out.append(f"- Written by {r.get('answered_by')} (local: "
                   f"{r.get('local_status')}); prompt_weight "
                   f"{r.get('prompt_weight')}; hash {r.get('rule_hash')}")
        out.append("")
    if pair_text is None:
        pr = last.get("M2_pairs")
        pair_rows = [r for r in rules if r.get("schema_version") == SCHEMA_VERSION
                     and r.get("month") == month]
        pair_text = render_month(month, pair_rows, (pr or {}).get("meta") or {
            "model": "the M2 pair path has not run this month"})
    out.append("---")
    out.append("")
    out.append(pair_text.replace(
        f"# LEARNED_{month}.md -- distilled rules from {month}'s graded ledger",
        "# M2 -- winner vs matched-loser pairs"))
    return "\n".join(out) + "\n"


def write_learned(month: str, *, rules_path: Path | None = None,
                  runs_path: Path | None = None, dir_: Path | None = None,
                  pair_text: str | None = None) -> Path:
    rules = _read_jsonl(Path(rules_path or LEARNED_RULES))
    runs = _read_jsonl(Path(runs_path or LEARN_RUNS))
    p = Path(dir_ or BRAIN) / f"LEARNED_{month}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(render_learned(month, rules, runs, pair_text), encoding="utf-8")
    tmp.replace(p)
    return p


def _latest_receipt(dir_: Path, pattern: str,
                    before: str) -> tuple[dict | None, str | None]:
    """The newest `<stem>_<YYYY-MM-DD>.json` whose date is < `before`."""
    best = None
    for f in sorted(Path(dir_).glob(pattern)):
        if f.stem.split("_")[-1] < before:
            best = f
    if best is None:
        return None, None
    try:
        return json.loads(best.read_text(encoding="utf-8")), str(best)
    except (OSError, ValueError):
        return None, str(best)


def distill_ledger(*, as_of: str | None = None, rows: Sequence[dict] | None = None,
                   reputation: dict | None = None, reputation_path: str | None = None,
                   autopsy: dict | None = None, autopsy_path: str | None = None,
                   local_fn: Callable | None = None, remote_fn: Callable | None = None,
                   spend_fn: Callable | None = None,
                   rules_path: Path | None = None, runs_path: Path | None = None,
                   md_dir: Path | None = None, write: bool = True,
                   force: bool = False) -> dict:
    """The night's distillation of the GRADED ledger into hashed, scored rules.

    Returns a receipt. Writes `learned_rules.jsonl` (append-only), one line of
    `learn_runs.jsonl`, and regenerates `LEARNED_<month>.md`. Zero rules is a
    `LEARN_DEGRADED` receipt naming the reason, never a silent heartbeat.
    """
    C = _cfg()
    as_of = str(as_of or date.today().isoformat())[:10]
    rules_path = Path(rules_path or LEARNED_RULES)
    runs_path = Path(runs_path or LEARN_RUNS)
    led = Path(C.OPTIMUS_LEDGER_DIR)
    if rows is None:
        from backend.services import forecast_reputation as FR
        rows = FR.load_ledger()
    if reputation is None and reputation_path is None:
        reputation, reputation_path = _latest_receipt(
            led / "reputation", "reputation_*.json", as_of + "~")
    if autopsy is None and autopsy_path is None:
        autopsy, autopsy_path = _latest_receipt(
            led / "decisions", "autopsy_*.json", as_of)
    usable = graded_rows_before(rows, as_of)
    fingerprint = {"n_graded_before": len(usable),
                   "resolved_through": max((str(r.get("resolved_at"))[:10]
                                            for r in usable), default=None),
                   "autopsy": autopsy_path}
    receipt: dict[str, Any] = {
        "receipt": "ledger_distill", "job": "ledger_distill", "as_of": as_of,
        "licence": "PRODUCT_EXPERIMENT", "written_utc": _now(),
        "input": {"ledger_rows": len(rows), **fingerprint,
                  "reputation_receipt": reputation_path},
        "cap_usd": float(C.LEARN_DAILY_CAP_USD), "cost_usd": 0.0,
        "cost_is_lower_bound": False, "batches": [], "refused_rules": [],
        "n_rules_written": 0, "answered_by": None, "local_status": None,
    }

    def _finish(status: str, reason: str | None, new_rules: list[dict]) -> dict:
        receipt.update({"status": status, "reason": reason,
                        "n_rules_written": len(new_rules),
                        "rules": [{k: r[k] for k in ("rule_id", "fact_key",
                                                     "rule_text", "n", "brier",
                                                     "skill", "rule_hash")}
                                  for r in new_rules]})
        if write:
            for r in new_rules:
                _append_jsonl(rules_path, r)
            _append_jsonl(runs_path, {k: receipt.get(k) for k in (
                "job", "as_of", "written_utc", "status", "reason",
                "n_rules_written", "answered_by", "local_status", "cost_usd",
                "cost_is_lower_bound", "input")})
            receipt["learned_md"] = str(write_learned(
                as_of[:7], rules_path=rules_path, runs_path=runs_path, dir_=md_dir))
        if status == "LEARN_DEGRADED":
            logger.warning("LEARN_DEGRADED %s: %s", as_of, reason)
        return receipt

    facts = select_facts(ledger_facts(rows, as_of=as_of)
                         + autopsy_facts(autopsy, as_of=as_of, path=autopsy_path))
    receipt["n_facts"] = len(facts)
    if not facts:
        return _finish("LEARN_DEGRADED",
                       f"no new graded rows: no (group x observable x horizon) cell "
                       f"has {C.LEARN_MIN_GROUP_N} rows resolved before {as_of}", [])
    prev_ok = [r for r in _read_jsonl(runs_path)
               if r.get("job") == "ledger_distill" and r.get("status") == "LEARNED"]
    if prev_ok and not force:
        pin = prev_ok[-1].get("input") or {}
        if all(pin.get(k) == fingerprint[k] for k in fingerprint):
            return _finish("LEARN_DEGRADED",
                           f"no new graded rows since {prev_ok[-1].get('as_of')} "
                           f"({fingerprint['n_graded_before']} graded, resolved "
                           f"through {fingerprint['resolved_through']})", [])

    rep_ctx = "no reputation receipt"
    if isinstance(reputation, dict) and reputation.get("arms"):
        # FAMILY totals, never arm labels: on the second real run the model
        # copied arm ids from this line onto rules about other groups.
        fam: dict[str, float] = {}
        for a in reputation["arms"]:
            k = ("investigator" if _family_of(a.get("arm")) == "investigator"
                 else "personas")
            fam[k] = fam.get(k, 0.0) + float(a.get("weight") or 0.0)
        rep_ctx = ("reputation refit %s: total pooling weight on the investigator "
                   "process %.2f, on all personas %.2f."
                   % (reputation.get("date"), fam.get("investigator", 0.0),
                      fam.get("personas", 0.0)))
    local_fn = local_fn or _default_local
    remote_fn = remote_fn or _default_remote
    spend_fn = spend_fn or _default_spend
    per = max(1, int(C.LEARN_FACTS_PER_CALL))
    local_status, local_dead, cap_hit = "not tried", False, False
    new_rules: list[dict] = []
    answered: set[str] = set()
    t_start = _now()
    for b0 in range(0, len(facts), per):
        batch = facts[b0:b0 + per]
        entry: dict[str, Any] = {"facts": [f["fact_key"] for f in batch]}
        got: list[dict] = []
        if not local_dead:
            try:
                text, meta = local_fn(learn_prompt(batch, rep_ctx))
                got, bad = parse_rules(text, batch)
                for g in got:
                    g["by"] = meta.get("model")
                entry["local"] = {"model": meta.get("model"), "valid": len(got),
                                  "refused": bad}
                local_status = "ok" if got else f"INVALID: {'; '.join(bad)[:200]}"
                receipt["refused_rules"] += [f"local {x}" for x in bad]
            except Exception as exc:                            # noqa: BLE001
                # Refused / timed out: the reader is down for the night; do not
                # wait on it once per batch.
                local_status = f"REFUSED: {type(exc).__name__}: {str(exc)[:160]}"
                local_dead = True
                entry["local"] = {"error": local_status}
        entry["local_status"] = local_status
        # PAIRED FALLBACK: every fact the local reader left without a valid rule
        # goes to DeepSeek -- the whole batch when it refused, the remainder when
        # it answered part of it.
        covered = {g["fact"]["fact_key"] for g in got}
        missing = [f for f in batch if f["fact_key"] not in covered]
        if missing:
            spent = spend_fn(t_start[:10])
            if not spent:
                entry["remote"] = {"skipped": "spend UNKNOWN (telemetry unreadable)"}
                cap_hit = True
            elif float(spent.get("total_cost_usd") or 0.0) >= float(C.LEARN_DAILY_CAP_USD):
                entry["remote"] = {"skipped": f"cap ${C.LEARN_DAILY_CAP_USD} reached "
                                              f"(${spent.get('total_cost_usd')} today)"}
                cap_hit = True
            else:
                try:
                    text, meta = remote_fn(learn_prompt(missing, rep_ctx))
                except Exception as exc:                        # noqa: BLE001
                    text, meta = None, {"error": f"{type(exc).__name__}: {exc}"[:200]}
                rgot, bad = parse_rules(text, missing) if text else (
                    [], ["no reply (provider refused, budget or breaker)"])
                for g in rgot:
                    g["by"] = meta.get("model")
                got += rgot
                entry["remote"] = {"model": meta.get("model"),
                                   "facts": [f["fact_key"] for f in missing],
                                   "valid": len(rgot), "refused": bad,
                                   **({"error": meta["error"]} if "error" in meta
                                      else {})}
                receipt["refused_rules"] += [f"deepseek {x}" for x in bad]
        entry["answered_by"] = sorted({str(g.get("by")) for g in got})
        for g in got:
            new_rules.append(ledger_rule_row(
                g["fact"], g["rule_text"], as_of=as_of,
                answered_by=str(g.get("by") or "?"),
                local_status=local_status,
                receipts={"reputation": reputation_path,
                          "autopsy": (autopsy_path if g["fact"]["source"]
                                      == "decision_autopsy" else None)}))
            answered.add(str(g.get("by")))
        receipt["batches"].append(entry)
    spent_run = spend_fn(t_start) or {}
    receipt["cost_usd"] = float(spent_run.get("total_cost_usd") or 0.0)
    receipt["cost_is_lower_bound"] = bool(spent_run.get("total_is_lower_bound")
                                          or not spent_run)
    receipt["answered_by"] = ", ".join(sorted(answered)) or None
    receipt["local_status"] = local_status
    if not new_rules:
        if cap_hit:
            reason = (f"cap: DeepSeek spend reached ${C.LEARN_DAILY_CAP_USD} "
                      f"today (or is unknown)")
        else:
            reason = (f"model refused: local {local_status}; DeepSeek returned no "
                      f"valid rule ({len(receipt['refused_rules'])} refused)")
        return _finish("LEARN_DEGRADED", reason, [])
    return _finish("LEARNED", None, new_rules)


def night_learn(*, as_of: str | None = None, refit: bool = True,
                write: bool = True) -> dict:
    """The one nightly entry point: reputation refit -> distil -> policy_state.

    Each stage's failure is recorded and does not stop the next: a policy file
    written from the newest receipt beats no policy file.
    """
    C = _cfg()
    as_of = str(as_of or date.today().isoformat())[:10]
    out: dict[str, Any] = {"as_of": as_of}
    rep, rpath = None, None
    if refit:
        try:
            from backend.services import forecast_reputation as FR
            rep = FR.refit(today=as_of)
            rpath = str(Path(C.OPTIMUS_LEDGER_DIR) / "reputation"
                        / f"reputation_{as_of}.json")
            out["reputation"] = rep.get("status")
        except Exception as exc:                                # noqa: BLE001
            out["reputation"] = f"FAILED {type(exc).__name__}: {exc}"[:200]
    try:
        d = distill_ledger(as_of=as_of, write=write)
        out["distill"] = {k: d.get(k) for k in (
            "status", "reason", "n_rules_written", "answered_by", "local_status",
            "cost_usd", "cost_is_lower_bound", "learned_md", "rules")}
    except Exception as exc:                                    # noqa: BLE001
        out["distill"] = f"FAILED {type(exc).__name__}: {exc}"[:200]
    try:
        from backend.services import policy_state as PS
        if rep is None:
            rep, rpath = _latest_receipt(Path(C.OPTIMUS_LEDGER_DIR) / "reputation",
                                         "reputation_*.json", as_of + "~")
        ps = PS.refresh(rep, receipt_path=rpath, write=write)
        out["policy_state"] = {"changed_since_last": ps.get("changed_since_last"),
                               "path": str(PS.STATE_PATH)}
    except Exception as exc:                                    # noqa: BLE001
        out["policy_state"] = f"FAILED {type(exc).__name__}: {exc}"[:200]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--out", default=None)
    ap.add_argument("--ledger", action="store_true",
                    help="the nightly graded-ledger distillation + policy_state")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--no-refit", action="store_true")
    a = ap.parse_args(argv)
    if a.ledger:
        res = night_learn(as_of=a.as_of, refit=not a.no_refit)
        print(json.dumps(res, indent=1, default=str))
        d = res.get("distill")
        return 0 if isinstance(d, dict) and d.get("status") == "LEARNED" else 3
    payload = M2_distill(smoke=a.smoke, run=a.run, month=a.month,
                         backend=a.backend)
    dest = (Path(a.out) if a.out else
            REPO / "backend" / "data" / "optimus"
            / f"night_factory_{datetime.now(timezone.utc):%Y-%m-%d}"
            / f"M2_distill_run{a.run:02d}{'_smoke' if a.smoke else ''}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"M2_distill: {payload.get('headline')}\n"
          f"  first rule with its own Brier: "
          f"{payload.get('first_rule_with_its_own_brier')}\n  -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
