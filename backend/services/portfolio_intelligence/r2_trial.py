"""TRIAL-R2 -- the monthly anonymised-news digest read: the FROZEN commitment.

Pre-registered 2026-09-10 (`docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`),
BEFORE the widened (PANEL-B) read is taken. This module is the machine-readable
half of that commitment and the SINGLE SOURCE of the prompt: `scripts/
night_r2_monthly_llm.py` imports `SYSTEM` and `PROMPT` from here and refuses to
run if their hashes have moved, the receipt records the hashes it ran under, and
`backend/tests/test_r2_prereg_and_costs.py` requires the doc, this module and the
receipt to agree. A silent prompt edit therefore turns the suite red instead of
quietly producing a different experiment under the same name.

Why the prompt is part of the commitment at all: the 2026-09-08 read
(`night_factory_2026-09-08/R2_monthly_llm_2015_2024_run01.json`, +16.189%/yr over
its shuffled-digest control, t 3.922 on 112 monthly blocks) is the programme's
only live lane, and its own amendment lists "one prompt, one digest construction,
one model, one horizon, and the prompt was not pre-registered" as the reason it
is CONDITIONAL rather than a claim. Freezing the prompt does not make that read a
claim -- nothing can, retroactively -- but it makes the NEXT read one that a
prompt search cannot quietly have preceded.

**A MODEL SWAP IS A NEW ARM, NOT AN UPGRADE.** The model identity below (file
name, byte size, sha256 of the GGUF, and the llama-server build that serves it)
is frozen for the same reason as the prompt: a 7B swapped for a 14B is a
different reader, and re-using this trial's decision rule for it would be metric
substitution with extra steps.

Descriptive only: this module reads no market data, places nothing, arms nothing.
"""

from __future__ import annotations

import hashlib
import json

TRIAL_PARAM = "r2-monthly-news-digest-read"
CANONICAL_DOC = "docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md"
PRE_REGISTERED = "2026-09-10"

# --------------------------------------------------------------------------
# THE PROMPT, byte for byte as it ran on 2026-09-08. Do not "improve" it: an
# improved prompt is a NEW arm with its own registration and its own place in
# the multiplicity count, not a better version of this one.
# --------------------------------------------------------------------------

SYSTEM = ("You are a careful financial analyst. You read only the text you are given and you never "
          "guess the company. Answer in English, in the exact format requested, and nothing else.")

PROMPT = """Below are news items about one company from a single month.

{digest}

Based ONLY on these items, state what you expect this company's stock to do over the NEXT month
relative to the overall market.

Answer on two lines, exactly:
DIRECTION: UP or DOWN or FLAT
CONFIDENCE: a number from 0.0 to 1.0
"""

# --------------------------------------------------------------------------
# THE DIGEST CONSTRUCTION. The prompt is only half the experiment; what is put
# into `{digest}` is the other half, and it is frozen to the same standard.
# --------------------------------------------------------------------------

DIGEST_SPEC: dict = {
    "unit": "one (name, calendar month) cell",
    "min_docs_per_cell": 3,
    "max_docs_in_digest": 8,
    "max_chars_per_doc": 320,
    "selection": ("the first `max_docs_in_digest` documents of that (name, month) group after "
                  "dropping empty text, in the panel's own stored order; PANEL-B sorts the group "
                  "ascending by published_utc then uid before taking the head, because a rebuilt "
                  "parquet has no stored order worth trusting"),
    "anonymisation": ("scripts.r7_news_representation.mask_company over "
                      "scripts.r7_news_representation.tokenise: the ticker and every distinctive "
                      "token of the issuer's CRSP name(s) are replaced by the literal '[co]'. "
                      "Masking is a UNION across name intervals, i.e. deliberately over-inclusive"),
    "item_format": "each item stripped, newlines replaced by single spaces, truncated to "
                   "max_chars_per_doc, prefixed '- ', items joined by a single newline",
    "temperature": 0.0,
    "max_tokens": 48,
    "parser": ("regex DIRECTION: (UP|DOWN|FLAT) -> +1/-1/0 and CONFIDENCE: float clipped to "
               "[0,1], defaulting to 0.5 when absent; an unparsable reply is dropped, not guessed"),
    "book": ("inside each month, w = direction * confidence normalised so sum|w| = 1 "
             "(self-financing, gross 1); the month's return is w . forward_excess"),
    "control": ("the identical pipeline on the identical cells, given the digest of a DIFFERENT "
                "month drawn with rng seed 20260909 -- same names, same dates, same parser, same "
                "book, zero information"),
    "canary": ("the AMNESIA canary of TRIAL-LLM-AMNESIA-1: the same cells read once with the REAL "
               "text and name and once masked. A POSITIVE accuracy gap (real better than masked) "
               "means recall, not reading"),
}

# --------------------------------------------------------------------------
# THE READER. Frozen; a different file, a different quantisation or a different
# server build is a different arm.
# --------------------------------------------------------------------------

MODEL_IDENTITY: dict = {
    "backend": "local_gguf",
    "file_name": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    "size_bytes": 4683074240,
    "sha256": "65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423",
    "served_by": "llama-server version 0.3.0-dev (build 10645, commit c5fc7e348), "
                 "built with Clang 20.1.8 for Windows x86_64",
    "endpoint": "127.0.0.1:8080 (OpenAI-compatible)",
    "note": "a model swap is a NEW ARM, not an upgrade -- it gets its own registration",
}

# --------------------------------------------------------------------------
# THE COST MODEL. "Net" means costs on REALISED turnover with the turnover
# printed (2026-09-10 must-not-regress rule 7), never a flat charge per date --
# C2 printed -237%/yr net on 2026-09-09 by charging 100 bps every day.
# --------------------------------------------------------------------------

COST_BPS_PER_SIDE = 25.0     # `scripts.night_factory_jobs.COST_BPS`, unchanged
COST_MODEL = ("turnover_t = sum_i |w_{t,i} - w_{t-1,i}| with w_{-1} = 0; "
              "cost_t = turnover_t * COST_BPS_PER_SIDE / 1e4; net_t = gross_t - cost_t. "
              "A full monthly replacement of a gross-1 long-short is turnover 2.0, i.e. "
              "50 bps a month or ~6%/yr, and that is the number to sanity-check against")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: The three hashes the doc, the receipt and the suite must all agree on.
SYSTEM_SHA256 = _sha(SYSTEM)
PROMPT_SHA256 = _sha(PROMPT)
DIGEST_SPEC_SHA256 = _sha(json.dumps(DIGEST_SPEC, sort_keys=True, ensure_ascii=True))


def fingerprint() -> dict:
    """What the receipt records, so a run can be tied to this commitment."""
    return {
        "trial": TRIAL_PARAM,
        "canonical_doc": CANONICAL_DOC,
        "pre_registered": PRE_REGISTERED,
        "system_sha256": SYSTEM_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "digest_spec_sha256": DIGEST_SPEC_SHA256,
        "model_identity": dict(MODEL_IDENTITY),
        "cost_bps_per_side": COST_BPS_PER_SIDE,
        "cost_model": COST_MODEL,
    }


class FrozenPromptViolation(RuntimeError):
    """The running prompt is not the registered one. Refuse; do not repair."""


def verify_frozen(system: str, prompt: str) -> dict:
    """Refuse rather than run a different experiment under this trial's name."""
    got_s, got_p = _sha(system), _sha(prompt)
    if got_s != SYSTEM_SHA256 or got_p != PROMPT_SHA256:
        raise FrozenPromptViolation(
            f"the prompt this run would send does not hash to the registered commitment "
            f"({CANONICAL_DOC}). system {got_s} vs {SYSTEM_SHA256}; prompt {got_p} vs "
            f"{PROMPT_SHA256}. An edited prompt is a NEW ARM: register it, do not run it here.")
    return fingerprint()


def ensure_r2_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-R2 in `rule_experiments`.

    Enters the cumulative trial count (the conservative direction for DSR/PBO).
    """
    from backend.services.portfolio_intelligence.trial_registry import (
        ensure_trial_registered,
    )

    notes = {
        "hypothesis": (
            "A local 7B model given ONLY an anonymised digest of one calendar month's news "
            "about one company calls that company's NEXT-month market-adjusted direction "
            "better than the identical pipeline reading a digest from a random other month, "
            "on a panel it was never selected on. Honest prior: PANEL-A (2015-2024, 135 "
            "names, 112 monthly blocks) measured +16.189%/yr gross over the control at "
            "t 3.922 with the AMNESIA canary passing (-0.0041) -- but gross of costs, on a "
            "mega-cap-skewed 135-name panel, from a prompt that was not registered when it "
            "ran. The prior on the widened read is therefore weak: the effect may be the "
            "135 names, the 2015-2024 era, or the prompt search that is not on the record."
        ),
        "purpose": "experimental",
        "canonical_doc": CANONICAL_DOC,
        "pre_registered": PRE_REGISTERED,
        "decision_rule": {
            "trial": "TRIAL-R2-monthly-news-digest-read",
            "primary_metric": (
                "read_minus_shuffled_control: the mean over monthly DATE BLOCKS of "
                "(arm month return - control month return), each NET of "
                "sum|dw| * 25 bps, annualised x12, on PANEL-B (the E1 2025-2026 "
                "text-and-return panel), with a Newey-West lag-2 t"),
            "adopt_threshold": (
                "net difference >= +14.4%/yr (the declared effect size) AND NW t "
                ">= 2.0 AND the AMNESIA gap <= +0.02 AND the sign positive in "
                "both calendar years present -> a 12-month zero-capital forward "
                "leg; earliest capital question 2027-09-10. Adoption never arms "
                "a book by itself"),
            "reject_threshold": (
                "net difference <= 0 OR NW t < 1.0 OR the AMNESIA gap > +0.05 "
                "(the read is recall, not reading) OR the shuffled control's own "
                "net level exceeds the arm's"),
            "power": {
                "dependence_unit": "one monthly date block of the long-short book; "
                                   "~975 cells a month are ONE observation",
                "n_available_blocks_panel_b": 19,
                "cells": 18501,
                "median_names_per_month": 912,
                "outcome_dispersion": "1.82 pp a month (implied long-short sd on "
                                      "PANEL-B's own cross-section, measured "
                                      "2026-09-10 before any model call)",
                "declared_effect_size": "1.20 pp a month = +14.4%/yr net",
                "mde_80pct": "1.17 pp a month = 14.0%/yr on 19 blocks. The same "
                             "estimator overstated PANEL-A's standard error by "
                             "1.61x, so the realised figure is likely nearer "
                             "8.7%/yr; the threshold stays at the conservative "
                             "number and the realised se is printed beside the "
                             "verdict",
            },
            "earliest_decision": (
                "the PANEL-B read is ONE computation, run ONCE by the named job "
                "`R2_monthly_llm --panel widened` after this registration's commit; "
                "the forward leg, if any, is a minimum of 12 monthly blocks"),
            "params_frozen": (
                f"system prompt sha256 {SYSTEM_SHA256}; user prompt sha256 "
                f"{PROMPT_SHA256}; digest spec sha256 {DIGEST_SPEC_SHA256}; model "
                f"{MODEL_IDENTITY['file_name']} sha256 {MODEL_IDENTITY['sha256']}; "
                f"temperature 0.0; max_tokens 48; min 3 docs, max 8 docs, 320 chars "
                f"a doc; 25 bps a side on realised turnover; NW lag 2; rng seed "
                f"20260909"),
            "crash_event_override": ("SPY drawdown >= 20% from its in-window peak defers "
                                     "any forward-leg decision until >= 6 months past the "
                                     "trough"),
            "contamination_clause": (
                "any defect in the panel (a symbol-basis, timestamp or mask-leak error) "
                "voids the read; the panel is rebuilt, the read is re-run once, and the "
                "registration date moves to that commit"),
            "hard_constraint": (
                "descriptive-only; PRODUCT_EXPERIMENT licence; never arms a book, never "
                "seals one, no buy/sell framing anywhere it surfaces, and the widened "
                "read may not restate what the 135-name PANEL-A read claims"),
        },
    }
    return ensure_trial_registered(TRIAL_PARAM, notes, db_path=db_path)
