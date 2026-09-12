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
    p = Path(dir_ or BRAIN) / f"LEARNED_{month}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_month(month, rows, meta), encoding="utf-8")
    return p


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
            payload["learned_md"] = str(write_month(month, [], {
                "noise_floor": {}, "shuffle_seed": shuffled.get("shuffle_seed"),
                "pairs_sampled": built["pairs_sampled"],
                "pairs_possible": built["pairs_possible"],
                "n_shuffled": len(shuffled["pairs"]),
                "dropped_degenerate": built["dropped_degenerate"],
                "model": f"{backend} (NOT ANSWERING)",
                "contract_hash": pool_hash,
                "pending_model": refusal,
            }, dir_=out_dir))
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
        payload["learned_md"] = str(write_month(month, out_rows, {
            "noise_floor": floor, "shuffle_seed": shuffled.get("shuffle_seed"),
            "pairs_sampled": built["pairs_sampled"],
            "pairs_possible": built["pairs_possible"],
            "n_shuffled": len(shuffled["pairs"]),
            "dropped_degenerate": built["dropped_degenerate"],
            "model": backend, "contract_hash": pool_hash,
        }, dir_=out_dir))
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
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
