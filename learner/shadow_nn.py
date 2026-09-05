"""THE FROZEN `nn_pre_causal` SHADOW. Zero capital. It writes a file, every night.

WHY THIS FILE EXISTS
====================
On 2026-09-05 `W3b_neural_floored_run01` judged the 8-seed `nn_pre_causal`
ensemble against a decision rule that had been declared and hashed BEFORE the
first fit (`428a7148...`). The ensemble cleared three of the rule's four
clauses -- +4.75%/yr over `lgbm_clf` at 10 bps, +5.06% at 25 bps, terminal
wealth 49.0 against 22.6 and 36.2, positive in 3 of 3 eras, on a training
universe that was already floored -- and failed the fourth: DSR 0.1726 against
a 0.95 bar, SPA p 0.108. The rule said STOP THE NEURAL LOOP, and the loop is
stopped.

Fable's 2026-09-06 review reversed the CONSEQUENCE, not the verdict:

    "Right verdict for capital and for claims. But the three licences say a
     PRODUCT_EXPERIMENT shadow needs a frozen contract, not a significance
     gate. Stopping the loop is right; refusing shadow accrual is
     over-closing."

So the arm is frozen here as a zero-capital shadow. It is the first candidate
for a SECOND INDEPENDENT SELECTOR since the bottleneck was diagnosed
(`docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`: all ten arena books select on
ONE signal), and it earns that description only because its errors are
different from `lgbm_clf`'s -- which is a claim this shadow's forward record is
what will eventually adjudicate.

WHAT IS FROZEN, AND WHAT A FREEZE MEANS FOR A WALK-FORWARD ARM
==============================================================
`learner.neural_long.run_neural` does not produce a serialised model file. It
produces WALK-FORWARD OUT-OF-SAMPLE predictions: 21 folds, each fitted on the
tape that had matured before its test year opened. There is no single object to
persist, and persisting the last fold's net would be a DIFFERENT experiment
(one model, one vintage) from the one that was measured.

What is frozen is therefore the CONTRACT -- the recipe -- and it is frozen by
hash:

  * the eight seeds, named, in order, no seed selection ever;
  * the architecture and every hyperparameter (`neural_long` constants,
    snapshotted BY VALUE into the contract so a later edit to that module is
    DETECTED rather than silently inherited);
  * the causal pre-training scope;
  * the tradable floor applied to the TRAINING universe as well as the graded
    book ($3m/day, >= $5);
  * the object judged: the SEED-MEAN ensemble, never the best cell;
  * the book: top-50, value-weighted, monthly, 10 and 25 bps per side;
  * the grader and the benchmark.

A contract whose hash moves is a different experiment wearing the same name,
and `verify_contract()` refuses rather than grading under a changed recipe.

WHY THE CADENCE IS MONTHLY AND THE RECEIPT IS NIGHTLY
=====================================================
The arm predicts a ONE-MONTH forward excess return on the research panel. It
cannot be scored on the nightly tracker day file at all: the day file supplies
`dataset.SHADOW_MAPPABLE` (14 base features), and this arm reads 50. Scoring it
on a median-imputed third of its inputs and calling the output a prediction is
the house failure mode -- code that runs green and silently does nothing.

So the BOOK is monthly and the RECEIPT is nightly. Every invocation writes a
file. On a night with no new panel month that file says `NO_NEW_MONTH` and
names the last book; on a night before the first monthly artefact exists it
says `PENDING_ARTEFACT` and names the exact command that would produce one.
"Receipt every night even when empty" is the mandate, and a heartbeat that
says nothing happened is the honest form of an empty night.

ZERO BROKER AUTHORITY, BY CONSTRUCTION
======================================
Same guarantee as `learner/shadow.py`: no Alpaca client, no ledger write, no
import from the execution repo, and the execution repo does not import
`learner`. This module writes one JSON file into this repository's data
directory and that is the whole of its effect.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "backend" / "data" / "optimus" / "learner"
CONTRACT_DIR = OUT_DIR / "contracts"
RECEIPT_DIR = OUT_DIR / "nn_shadow"
BOOK_DIR = RECEIPT_DIR / "books"

CONTRACT_ID = "nn_pre_causal_shadow_v1"
CONTRACT_PATH = CONTRACT_DIR / f"{CONTRACT_ID}.json"

#: The signal_registry row this shadow accrues under.
SIGNAL_ID = "neural_pre_causal_ensemble_v1"

#: The date the contract was frozen and grading begins. Not the date the
#: research ran -- a shadow's forward record starts at the freeze, and
#: back-dating it would readmit the very evidence the freeze exists to exclude.
FIRST_GRADE_DATE = "2026-09-05"

#: The rule that was declared and hashed BEFORE the first fit, on 2026-09-05
#: at 11:55:48 UTC. Copied here so the shadow's provenance does not depend on a
#: receipt file staying where it is.
DECISION_RULE_SHA256 = (
    "428a7148f61942b0934765ae192090d63942c0a60d219469fdbdc22bdb0fb4af")

#: The receipt that measured the arm and refused it for capital.
SOURCE_RECEIPT = ("backend/data/optimus/continuation_2026-09-06/"
                  "W3b_neural_floored_run01.json")

_STATUS_OK = "OK"
_STATUS_NO_NEW_MONTH = "NO_NEW_MONTH"
_STATUS_PENDING = "PENDING_ARTEFACT"
_STATUS_REFUSED = "REFUSED"


# --------------------------------------------------------------- the contract

def _neural_constants() -> dict:
    """Snapshot the hyperparameters BY VALUE.

    Freezing by reference to `learner.neural_long` would mean a later edit to
    that module silently changed the frozen experiment. Snapshotting by value
    means the edit is DETECTED: `verify_contract` compares the live constants
    with the frozen ones and reports every drift by name.
    """
    from learner import neural_long as N          # noqa: PLC0415 - lazy: torch
    return {
        "seed_base": int(N.SEED_BASE),
        "n_seeds": int(N.N_SEEDS),
        "horizon_months": int(N.HORIZON),
        "clip_sd": float(N.CLIP_SD),
        "target_clip_sd": float(N.TARGET_CLIP_SD),
        "dropout": float(N.DROPOUT),
        "lr": float(N.LR),
        "weight_decay": float(N.WEIGHT_DECAY),
        "max_epochs": int(N.MAX_EPOCHS),
        "patience": int(N.PATIENCE),
        "batch": int(N.BATCH),
        "mask_fraction": float(N.MASK_FRACTION),
        "pretrain_epochs": int(N.PRETRAIN_EPOCHS),
        "pretrain_lr": float(N.PRETRAIN_LR),
        "tradable_floor_usd": float(N.TRADABLE_FLOOR_USD),
        "tradable_min_close": float(N.TRADABLE_MIN_CLOSE),
        "first_test_year": int(N.FIRST_TEST_YEAR),
        "last_test_year": int(N.LAST_TEST_YEAR),
    }


def build_contract() -> dict:
    """The frozen contract, as a dict. `freeze()` writes it; nothing mutates it."""
    return {
        "artefact": "AEGIS_SHADOW_CONTRACT",
        "contract_id": CONTRACT_ID,
        "schema": "shadow-contract-1",
        "licence": "PRODUCT_EXPERIMENT",
        "capital": "ZERO. No order path imports learner/. This contract confers "
                   "no broker authority and no sizing authority of any kind.",
        "signal_id": SIGNAL_ID,
        "frozen_utc": "2026-09-05T00:00:00+00:00",
        "first_grade_date": FIRST_GRADE_DATE,
        "arm": "nn_pre_causal",
        "what_is_frozen": (
            "the RECIPE, not a serialised net. run_neural produces walk-forward "
            "OOS predictions over 21 folds; there is no single model object, and "
            "persisting the last fold would be a different experiment. The eight "
            "seeds, the architecture, the pre-training scope, the training-universe "
            "floor, the object judged (seed-mean ensemble, never the best cell), "
            "the book and the grader are frozen by the hash of this file."),
        "seeds": [20260906, 20260907, 20260908, 20260909,
                  20260910, 20260911, 20260912, 20260913],
        "seed_selection": "FORBIDDEN. The graded object is the seed-mean over all "
                          "eight. Reporting the best seed would be the maximum of "
                          "eight draws quoted as one.",
        "pretrain_scope": "causal",
        "width": "base",
        "hyperparameters": _neural_constants(),
        "training_universe": {
            "applied_to": "the TRAINING universe as well as the graded book",
            "dollar_volume_floor_usd_per_day": 3_000_000.0,
            "min_close_usd": 5.0,
            "source": "learner.neural_long.tradable_universe",
        },
        "book": {
            "k": 50, "weight": "vw", "cadence": "monthly",
            "cost_bps_per_side": [10.0, 25.0],
            "ret_col": "fwd_1m", "mkt_col": "mkt_vw_1m",
            "grader": "learner.evaluate.book",
        },
        "benchmark": {
            "primary": "the panel's own mkt_vw_1m (vw_crsp_common_main)",
            "also_required": "beta_matched -- an excess that is a LOADING is not "
                             "an intercept; see continuation_2026-09-06b/"
                             "C1_beta_matched_regrade_run01.json",
            "module": "learner.benchmark",
        },
        "decision_rule_sha256": DECISION_RULE_SHA256,
        "source_receipt": SOURCE_RECEIPT,
        "evidence_at_freeze": {
            "vs_lgbm_clf_annualised_10bps": 0.0475,
            "vs_lgbm_clf_annualised_25bps": 0.0506,
            "terminal_wealth_net_10bps": 49.0082,
            "terminal_wealth_lgbm_clf": 22.6076,
            "terminal_wealth_lgbm_raw": 36.2448,
            "terminal_wealth_market_same_months": 14.3778,
            "t_stat_paired_vs_market": 2.243,
            "deflated_sharpe_vs_bar": {"dsr": 0.1726, "bar": 0.95},
            "spa_p": 0.1078,
            "eras_positive": "3 of 3",
            "months": 251,
            "B10_not_earned": True,
            "reading": "clears three clauses of the pre-declared rule and fails the "
                       "family correction. Not earned for CAPITAL and not a "
                       "RESEARCH_CLAIM; permitted as a zero-capital shadow under "
                       "the PRODUCT_EXPERIMENT licence.",
        },
        "cadence": {
            "book": "monthly -- the arm predicts a one-month forward excess",
            "receipt": "nightly -- a receipt is written every invocation, "
                       "including nights with no new month",
            "why_not_nightly_book": (
                "the tracker day file supplies dataset.SHADOW_MAPPABLE (14 base "
                "features); this arm reads 50. Median-imputing a third of a "
                "model's inputs and calling the output a prediction is the house "
                "failure mode."),
        },
        "promotion": "A shadow is promoted by changing its GRADE in "
                     "backend/data/signal_registry.yaml, attended, under CANON. "
                     "Nothing in this module can do that.",
    }


def canonical_json(obj: dict) -> str:
    """Stable bytes for hashing: sorted keys, no whitespace drift, LF only.

    CRLF changes a content hash ([[reference-crlf-changes-a-content-hash]]), so
    the hash is taken over a string this function produces and never over the
    bytes of a file read back in text mode.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def contract_sha256(contract: Optional[dict] = None) -> str:
    c = dict(contract or build_contract())
    c.pop("sha256", None)
    return hashlib.sha256(canonical_json(c).encode("utf-8")).hexdigest()


def freeze(force: bool = False) -> Path:
    """Write the contract once. Refuses to overwrite a DIFFERENT contract."""
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    c = build_contract()
    c["sha256"] = contract_sha256(c)
    if CONTRACT_PATH.exists() and not force:
        old = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        if old.get("sha256") != c["sha256"]:
            raise SystemExit(
                f"REFUSED: {CONTRACT_PATH} already holds a contract with hash "
                f"{str(old.get('sha256'))[:16]} and this one hashes to "
                f"{c['sha256'][:16]}. Overwriting a frozen contract in place is "
                f"how a forward record silently changes the experiment it is a "
                f"record of. Freeze a NEW contract id instead, or pass force=True "
                f"and say why in a receipt.")
        return CONTRACT_PATH
    CONTRACT_PATH.write_text(json.dumps(c, indent=1, ensure_ascii=False),
                             encoding="utf-8", newline="\n")
    return CONTRACT_PATH


def load_contract() -> dict:
    if not CONTRACT_PATH.exists():
        raise SystemExit(f"REFUSED: no frozen contract at {CONTRACT_PATH}. "
                         f"Run `python -m scripts.learner_shadow_seal --freeze-nn`.")
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def verify_contract() -> dict:
    """Compare the frozen contract against the live code. Names every drift.

    Two independent checks, because they catch different failures:
      * the stored `sha256` against a re-hash of the stored body -- catches a
        hand edit of the file;
      * the frozen `hyperparameters` against `learner.neural_long`'s live
        constants -- catches an edit to the MODULE, which would leave the
        contract file untouched and byte-identical while changing what the
        recipe means.
    """
    out: dict = {"contract_path": str(CONTRACT_PATH), "ok": False,
                 "checks": {}, "drift": []}
    try:
        c = load_contract()
    except SystemExit as exc:
        out["checks"]["contract_present"] = False
        out["drift"].append(str(exc))
        return out
    out["checks"]["contract_present"] = True
    stored = c.get("sha256")
    rehash = contract_sha256(c)
    out["stored_sha256"] = stored
    out["recomputed_sha256"] = rehash
    out["checks"]["hash_matches_body"] = bool(stored == rehash)
    if stored != rehash:
        out["drift"].append(
            f"the contract file's stored hash {str(stored)[:16]} does not match a "
            f"re-hash of its own body {rehash[:16]} -- it has been edited in place")

    try:
        live = _neural_constants()
    except Exception as exc:                       # noqa: BLE001
        out["checks"]["live_constants_readable"] = False
        out["drift"].append(f"could not read learner.neural_long constants: {exc}")
        return out
    out["checks"]["live_constants_readable"] = True
    frozen = c.get("hyperparameters") or {}
    moved = {k: {"frozen": frozen.get(k), "live": v}
             for k, v in live.items() if frozen.get(k) != v}
    out["checks"]["hyperparameters_unchanged"] = not moved
    if moved:
        out["hyperparameter_drift"] = moved
        out["drift"].append(
            f"{len(moved)} hyperparameter(s) in learner.neural_long have moved "
            f"since the freeze: {sorted(moved)}. The contract file is untouched "
            f"and the recipe is not.")
    out["ok"] = not out["drift"]
    return out


# ------------------------------------------------------------- the nightly job

def _rel(p: Path) -> str:
    """Repo-relative if it is under the repo, absolute otherwise.

    `Path.relative_to` RAISES on a path outside the repo, and a receipt writer
    that raises while explaining why tonight was empty is worse than a receipt
    with an absolute path in it.
    """
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return p.as_posix()


def _books() -> list[Path]:
    if not BOOK_DIR.exists():
        return []
    return sorted(BOOK_DIR.glob("nn_pre_causal_book_*.json"))


def latest_book() -> Optional[dict]:
    """The most recent monthly book, or None if none has ever been produced."""
    books = _books()
    if not books:
        return None
    return json.loads(books[-1].read_text(encoding="utf-8"))


def build_nn_shadow_receipt(day: Optional[str] = None) -> dict:
    """One night's receipt. ALWAYS returns a dict; never raises for an empty night.

    Statuses, and what each one means:
      OK               a new monthly book was produced for this month
      NO_NEW_MONTH     heartbeat -- the last book is still the current one
      PENDING_ARTEFACT frozen, registered, and no monthly book exists yet; the
                       command that would produce one is named
      REFUSED          the contract drifted, or an input the grader needs is
                       missing. A refusal is a finding.
    """
    day = day or date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: dict = {
        "artefact": "AEGIS_NN_SHADOW_RECEIPT",
        "licence": "PRODUCT_EXPERIMENT",
        "signal_id": SIGNAL_ID,
        "contract_id": CONTRACT_ID,
        "broker_authority": "NONE -- zero capital by contract. This file is "
                            "written, never sent.",
        "day": day,
        "generated_at_utc": now,
        "first_grade_date": FIRST_GRADE_DATE,
        "decision_rule_sha256": DECISION_RULE_SHA256,
    }
    ver = verify_contract()
    out["contract_verification"] = ver
    out["contract_sha256"] = ver.get("stored_sha256")
    if not ver.get("ok"):
        out["status"] = _STATUS_REFUSED
        out["reasons"] = ver.get("drift") or ["contract verification failed"]
        return out

    books = _books()
    out["books_to_date"] = len(books)
    book = latest_book()
    if book is None:
        out["status"] = _STATUS_PENDING
        out["reasons"] = [
            "no monthly book has been produced under this contract yet. The arm "
            "is FROZEN and REGISTERED; its forward record starts at the first "
            "book. This is not a failure and not an empty book -- it is the "
            "night before the first month.",
        ]
        out["how_to_produce_one"] = (
            "python -m scripts.w3_neural_floored --stage nn_pre_causal, then "
            "--stage combine, with the seeds and years named in the contract; the "
            "seed-mean book is written to "
            f"{_rel(BOOK_DIR)}/nn_pre_causal_book_<YYYY-MM>.json")
        return out

    out["latest_book"] = {
        "month": book.get("month"),
        "n_holdings": len(book.get("holdings") or []),
        "k": book.get("k"),
        "weight": book.get("weight"),
    }
    if book.get("month") == day[:7]:
        out["status"] = _STATUS_OK
        out["holdings"] = book.get("holdings")
    else:
        out["status"] = _STATUS_NO_NEW_MONTH
        out["reasons"] = [
            f"the newest book is for {book.get('month')} and today is {day}. The "
            f"cadence is monthly; a nightly receipt on a night with no new month "
            f"is a heartbeat, not an empty book."]
    return out


def write_nn_shadow_receipt(rec: dict) -> Path:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = RECEIPT_DIR / f"nn_shadow_{rec.get('day')}.json"
    path.write_text(json.dumps(rec, indent=2, default=str),
                    encoding="utf-8", newline="\n")
    return path


__all__ = ["CONTRACT_ID", "CONTRACT_PATH", "SIGNAL_ID", "FIRST_GRADE_DATE",
           "DECISION_RULE_SHA256", "SOURCE_RECEIPT", "BOOK_DIR", "RECEIPT_DIR",
           "build_contract", "canonical_json", "contract_sha256", "freeze",
           "load_contract", "verify_contract", "latest_book",
           "build_nn_shadow_receipt", "write_nn_shadow_receipt"]
