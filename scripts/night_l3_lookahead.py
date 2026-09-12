"""L3 -- Lookahead Propensity: is the "skill" concentrated where the model
already knew the answer?

Gao, Jiang and Yan (arXiv:2512.23847, "A Test of Lookahead Bias in LLM
Forecasts") measure, per firm-date, *"the probability that the LLM has
internalized information about the realized outcome"* with a DATE-ONLY RECALL
PROBE -- ask the model what happened to that name in that month, showing it no
documents at all, and score how much of the true outcome it can produce from
the identifier alone. Then regress accuracy on the forecast, on LAP, and on
their interaction, and split the sample at the model's training cutoff. The
paper's own falsification is the split: significant inside the training window
and NOT significant outside it is lookahead; significant in both is something
else.

WHAT THIS JOB COMPUTES WITHOUT THE MODEL, AND WHAT IT CANNOT
============================================================
The accuracy side needs no new model calls -- R2's answers are on disk. The
probe does. So when `llama-server` is not answering, everything that does not
need it is computed (the accuracy panel, the cutoff split, the block counts,
the MDE) and the probe half is `PENDING_MODEL` with the cell list frozen and
hashed. A refusal is a finding.

TWO PLACES THIS DEPARTS FROM THE SPEC, BOTH STATED RATHER THAN SLID IN
======================================================================
1. **The verdict tests β2 AND β3 jointly; the receipt still reports β3 as the
   headline.** Spec section 1.1 names the interaction `β3` as the statistic, and
   it is reported. But the spec's own known-answer test (section 7, step 3)
   plants accuracy that is high wherever LAP is high pre-cutoff, with the
   forecast independent -- and that plants a LEVEL effect on `β2`, whose true
   `β3` is zero. A detector that fired only on `β3` would call that planted
   contamination CLEAN. A model that is right in high-LAP cells regardless of
   what it forecast is exactly as contaminated as one whose forecast only works
   there, so the verdict uses a Wald test on the pair and the receipt names
   which coefficient carried it.
2. **PANEL-B cannot run the paper's design at all.** Qwen2.5-7B's cutoff is
   ~2024-06/07 and PANEL-B is 2025-01..2026-07, so its pre-cutoff arm is EMPTY.
   That is not a CLEAN verdict -- it is a design that did not run, and it is
   reported as `INCONCLUSIVE_UNDERPOWERED` with the reason, because a CLEAN
   stamp that hides behind zero power is the thing spec section 1.5 explicitly
   forbids.

    python -m scripts.night_l3_lookahead --panel B --run 1
    python -m scripts.night_factory_jobs L3_lookahead --run 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import protocol_p16 as pp                         # noqa: E402
from backend.services import x_lane_data as xd                          # noqa: E402
from backend.services.portfolio_intelligence.r2_trial import (          # noqa: E402
    COST_BPS_PER_SIDE)
from scripts.night_r2_monthly_llm import _probe, _r                     # noqa: E402

RUN_DATE = "2026-09-12"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
JOB = "L3_lookahead"

#: Per-model cutoffs, spec section 1.3, WITH their source and confidence. None of
#: these is an official vendor page; the confidence column is the honest part.
MODEL_CUTOFFS: dict[str, dict] = {
    "Qwen2.5-7B-Instruct": {
        "cutoff": "2024-06-30",
        "source": ("triangulated from OpenRouter/Puter provider pages and the community "
                   "tracker github.com/HaoooWang/llm-knowledge-cutoff-dates; some secondary "
                   "sources say April 2024. NOT an official Alibaba cutoff page and NOT "
                   "verified against Qwen's own model card in this session"),
        "confidence": "MEDIUM"},
    "deepseek-chat": {
        "cutoff": "2024-07-01",
        "source": ("an EXTRACTED system prompt reported by knostic.ai -- unofficial. "
                   "DeepSeek publishes no cutoff date"),
        "confidence": "LOW"},
    "deepseek-reasoner": {
        "cutoff": None,
        "source": ("inconsistent self-report: R1 has stated 2023-10 in some sessions while "
                   "demonstrating knowledge into 2024 (x.com/yi_ding, "
                   "deepseek-ai/DeepSeek-R1 issue 615). No split is claimed on this model"),
        "confidence": "LOW"},
}

#: R2's two panels and the months they cover, from TRIAL-R2 section 2. PANEL-B is
#: entirely after Qwen2.5-7B's cutoff, which is the finding, not a footnote.
PANEL_WINDOWS = {"PANEL-A": ("2015-02", "2024-11"), "PANEL-B": ("2025-01", "2026-07")}

#: The probe, spec section 1.2. It is UN-masked on purpose: it is measuring
#: memorisation, never feeding the graded forecast, and it carries its own
#: `purpose` so its spend and refusals never mix with R2's own line.
LAP_PROBE_SYSTEM = ("You are a financial-history assistant. Answer only from what you "
                    "already know; you are given no documents. Respond in English only.")
LAP_PROBE_USER = (
    "For {ticker} in {month}, state what you recall happened to its stock price that "
    "month relative to the market: UP, DOWN, or FLAT, and your confidence 0.0-1.0. "
    "If you do not recall, say UNKNOWN.\n"
    "Answer in exactly two lines:\nRECALL: UP|DOWN|FLAT|UNKNOWN\nCONFIDENCE: 0.0-1.0")
LAP_PROBE_PURPOSE = "l3_lap_probe"

ALPHA = 0.05          # TRIAL-R2's own alpha, reused rather than re-chosen
Z_ALPHA = 1.959964
#: 2.8 = z(0.975) + z(0.80), the same two-sided-5%/80%-power constant
#: `night_r2_monthly_llm.power_check` uses. An MDE computed a different way here
#: could not be compared with R2's.
MDE_Z = 2.8
#: accuracy is in [0,1] and forecast x LAP is in [0,1], so a coefficient whose
#: MDE exceeds 1.0 cannot be resolved anywhere inside the data's own range. Not
#: a tuned threshold -- an arithmetic ceiling.
MDE_CEILING = 1.0
MIN_BLOCKS = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lap_of(recall_dir: int | None, recall_conf: float, fwd: float | None) -> float:
    """`LAP_i`, spec section 1.2.

    The probe's own confidence WHEN its recalled direction matches the realised
    outcome, and zero otherwise. A confident-but-wrong recall scores zero: that
    is evidence of a bad memory, not of lookahead, and letting it inflate LAP
    would make a hallucinating model look contaminated.
    """
    if recall_dir is None or fwd is None or recall_dir == 0:
        return 0.0
    if (float(fwd) > 0) != (int(recall_dir) > 0):
        return 0.0
    return float(min(max(recall_conf, 0.0), 1.0))


def parse_probe(text: str) -> tuple[int | None, float]:
    """(direction, confidence) from a probe reply. UNKNOWN -> (None, 0.0)."""
    import re

    m = re.search(r"RECALL\s*:\s*(UP|DOWN|FLAT|UNKNOWN)", text or "", re.I)
    if not m:
        return None, 0.0
    word = m.group(1).upper()
    if word == "UNKNOWN":
        return None, 0.0
    d = {"UP": 1, "DOWN": -1, "FLAT": 0}[word]
    c = re.search(r"CONFIDENCE\s*:\s*([01]?\.?\d*)", text or "", re.I)
    conf = 0.5
    if c:
        try:
            conf = min(max(float(c.group(1)), 0.0), 1.0)
        except ValueError:
            conf = 0.5
    return d, conf


# ------------------------------------------------------------- the regression

def cluster_ols(y, X, groups) -> dict:
    """OLS with cluster-robust (CR1) standard errors, clustered by DATE BLOCK.

    Cells inside one month share the market and are not independent draws
    (canon section 58): an OLS standard error over 435 cells in 18 months is a
    standard error over 18 observations wearing 435 hats. `statsmodels` is not
    a dependency of this path, so the sandwich is written out -- eight lines,
    and every term is visible.
    """
    y = np.asarray(y, dtype="float64").ravel()
    X = np.asarray(X, dtype="float64")
    groups = np.asarray(groups)
    n, k = X.shape
    uniq = np.unique(groups)
    g = len(uniq)
    if n <= k or g < 2:
        return {"beta": None, "se": None, "n": int(n), "n_groups": int(g),
                "note": f"{n} rows in {g} clusters cannot support {k} parameters"}
    xtx = X.T @ X
    if np.linalg.matrix_rank(xtx) < k:
        return {"beta": None, "se": None, "n": int(n), "n_groups": int(g),
                "note": ("the design matrix is rank deficient -- a regressor is constant "
                         "or collinear on this slice, so no coefficient is identified")}
    xtx_inv = np.linalg.inv(xtx)
    beta = xtx_inv @ (X.T @ y)
    u = y - X @ beta
    meat = np.zeros((k, k))
    for grp in uniq:
        sel = groups == grp
        xg = X[sel]
        ug = u[sel]
        s = xg.T @ ug
        meat += np.outer(s, s)
    c = (g / max(g - 1, 1)) * ((n - 1) / max(n - k, 1))
    V = xtx_inv @ meat @ xtx_inv * c
    se = np.sqrt(np.clip(np.diag(V), 0.0, None))
    return {"beta": beta.tolist(), "se": se.tolist(), "V": V.tolist(),
            "n": int(n), "n_groups": int(g), "note": "CR1, clustered by month block"}


def interaction_test(rows: list[dict]) -> dict:
    """The accuracy regression of spec section 1.1, plus the joint Wald test.

    `accuracy ~ 1 + forecast + LAP + forecast*LAP`, clustered by month. `beta3`
    is the paper's statistic and is reported; `joint_p` is the Wald test on
    (`beta2`, `beta3`) together, which is what the verdict uses -- see this
    module's docstring for why.
    """
    usable = [r for r in rows if r.get("accuracy") is not None]
    if len(usable) < 8:
        return {"n": len(usable), "beta3": None, "verdict_input": None,
                "note": f"{len(usable)} gradeable cells is too few to fit four parameters"}
    y = np.array([float(r["accuracy"]) for r in usable])
    f = np.array([float(r["forecast"]) for r in usable])
    lap = np.array([float(r["LAP"]) for r in usable])
    X = np.column_stack([np.ones_like(f), f, lap, f * lap])
    fit = cluster_ols(y, X, [r["block"] for r in usable])
    if fit.get("beta") is None:
        return {"n": len(usable), "beta3": None, "verdict_input": None,
                "note": fit.get("note")}
    beta, se = fit["beta"], fit["se"]
    V = np.asarray(fit["V"])
    out = {"n": len(usable), "n_blocks": fit["n_groups"],
           "beta0": _r(beta[0], 5), "beta1_forecast": _r(beta[1], 5),
           "beta2_LAP": _r(beta[2], 5), "beta3": _r(beta[3], 5),
           "beta2_se": _r(se[2], 5), "beta3_se": _r(se[3], 5),
           "beta2_t": _r(beta[2] / se[2], 3) if se[2] > 0 else None,
           "beta3_t": _r(beta[3] / se[3], 3) if se[3] > 0 else None,
           "mde_beta3": _r(MDE_Z * se[3], 4) if se[3] > 0 else None,
           "note": fit["note"]}
    out["beta3_p"] = _r(_two_sided_p(out["beta3_t"]), 5)
    out["beta2_p"] = _r(_two_sided_p(out["beta2_t"]), 5)
    # joint Wald on (beta2, beta3): b' V^-1 b, chi2 with 2 df
    b = np.array([beta[2], beta[3]])
    sub = V[2:4, 2:4]
    try:
        w = float(b @ np.linalg.inv(sub) @ b)
    except np.linalg.LinAlgError:
        w = float("nan")
    out["joint_wald_chi2_2df"] = _r(w, 4)
    out["joint_p"] = _r(_chi2_sf_2df(w), 5)
    if fit["n_groups"] < MIN_BLOCKS:
        # CR1 ON THREE CLUSTERS IS NOT A STANDARD ERROR.
        # Measured here on 2026-09-12: nine synthetic rows in three month
        # blocks, fitted with four parameters, returned joint p = 0.0 on data
        # generated with no relationship at all. A sandwich whose meat is a sum
        # over three outer products is estimating a 4x4 covariance from three
        # terms; the p it returns is arithmetic, not evidence. The coefficients
        # are still reported -- the significance is refused.
        out["joint_wald_chi2_2df"] = None
        out["joint_p"] = None
        out["note"] = (f"{fit['n_groups']} month blocks is below the {MIN_BLOCKS} a "
                       "cluster-robust covariance can be estimated from; the "
                       "coefficients are reported and their significance is REFUSED")
        out["carried_by"] = None
        return out
    out["carried_by"] = ("beta3 (the forecast x LAP interaction)"
                         if (out["beta3_p"] is not None and out["beta2_p"] is not None
                             and out["beta3_p"] <= out["beta2_p"])
                         else "beta2 (the LAP level: accuracy is higher where the model "
                              "already knew, whatever it forecast)")
    return out


def _two_sided_p(t: float | None) -> float | None:
    if t is None:
        return None
    return float(2.0 * 0.5 * _erfc(abs(t) / np.sqrt(2.0)))


def _erfc(x: float) -> float:
    import math

    return math.erfc(float(x))


def _chi2_sf_2df(w: float) -> float | None:
    """P(chi2_2 > w) = exp(-w/2). The 2-df survival function is closed form, so
    this needs no scipy -- and a closed form cannot drift from a table."""
    import math

    if w is None or not np.isfinite(w) or w < 0:
        return None
    return float(math.exp(-w / 2.0))


def verdict_of(pre: dict, post: dict, *, alpha: float = ALPHA) -> tuple[str, str]:
    """Spec section 1.5's four verdicts, with the underpowered one able to win.

    A CLEAN stamp that hides behind zero power is what section 1.5 forbids, so the
    MDE is checked BEFORE the null is accepted: an arm whose smallest resolvable
    coefficient exceeds the range the data can take is INCONCLUSIVE, not clean.
    """
    def fitted(d):
        return bool(d) and d.get("joint_p") is not None

    if not fitted(pre) and not fitted(post):
        return ("INCONCLUSIVE_UNDERPOWERED",
                "neither arm could be fitted: " + "; ".join(
                    x for x in (pre.get("note"), post.get("note")) if x))
    if not fitted(pre):
        return ("INCONCLUSIVE_UNDERPOWERED",
                "the PRE-cutoff arm could not be fitted, so the paper's own before/after "
                f"falsification cannot be run: {pre.get('note')}")
    if not fitted(post):
        return ("INCONCLUSIVE_UNDERPOWERED",
                "the POST-cutoff arm could not be fitted, so a pre-cutoff result has no "
                f"falsifier: {post.get('note')}")
    sig_pre = pre["joint_p"] < alpha
    sig_post = post["joint_p"] < alpha
    weak = [name for name, d in (("pre", pre), ("post", post))
            if (d.get("mde_beta3") is None or d["mde_beta3"] > MDE_CEILING
                or (d.get("n_blocks") or 0) < MIN_BLOCKS)]
    # THE POWER CHECK RUNS BEFORE THE CONFIRMATION (canon section 64), and it
    # binds a SIGNIFICANT result as hard as an insignificant one. Measured here
    # on 2026-09-12: an arm of 216 pure-noise rows in 18 blocks, whose MDE on
    # beta3 was 1.60 -- larger than accuracy's whole range -- returned a
    # significant joint p and would have been stamped CONTAMINATED. An arm that
    # cannot resolve a coefficient inside the data's own range cannot support a
    # verdict in either direction.
    if weak:
        return ("INCONCLUSIVE_UNDERPOWERED",
                f"the {', '.join(weak)} arm cannot resolve a coefficient inside the "
                f"data's own range (MDE on beta3 {pre.get('mde_beta3')} pre, "
                f"{post.get('mde_beta3')} post, against a ceiling of {MDE_CEILING}; "
                f"blocks {pre.get('n_blocks')}/{post.get('n_blocks')}), so neither a "
                f"CLEAN stamp nor a CONTAMINATED one is supported -- the joint p was "
                f"{pre['joint_p']} pre and {post['joint_p']} post, and zero power is "
                "the reason they are not being read")
    if sig_pre and not sig_post:
        return ("CONTAMINATED",
                f"accuracy loads on memorisation propensity INSIDE the training window "
                f"(joint p {pre['joint_p']}, carried by {pre['carried_by']}) and not "
                f"outside it (joint p {post['joint_p']}) -- the paper's own falsification "
                "pattern held")
    if not sig_pre and not sig_post:
        return ("CLEAN",
                f"accuracy is unrelated to memorisation propensity in both regimes "
                f"(joint p pre {pre['joint_p']}, post {post['joint_p']}; MDE on beta3 "
                f"{pre.get('mde_beta3')} pre, {post.get('mde_beta3')} post)")
    if sig_pre and sig_post:
        return ("AMBIGUOUS",
                f"significant in BOTH regimes (joint p {pre['joint_p']} pre, "
                f"{post['joint_p']} post) -- the paper's falsification did not hold, so "
                "this is not lookahead and is not clean either")
    return ("AMBIGUOUS",
            f"significant only AFTER the cutoff (joint p {post['joint_p']} post, "
            f"{pre['joint_p']} pre), which lookahead cannot produce")


# ------------------------------------------------------- the accuracy panel

def era_of(month: str, cutoff: str | None) -> str:
    """`pre`, `post`, or `boundary` -- and `boundary` is a real third answer.

    The cutoff's OWN month is partly inside the training window and partly
    outside it. Assigning it to either arm is a choice nobody made on evidence,
    and it is the kind of choice that decides a borderline verdict, so it is
    excluded from both regressions and COUNTED in the receipt. Found on
    2026-09-12 by a test: `month >= cutoff[:7]` had put 2024-06 -- a month
    entirely inside a 2024-06-30 cutoff -- into the POST arm, and the
    post-cutoff mean LAP came back non-zero for a probe that recalled nothing
    after the cutoff.
    """
    if cutoff is None:
        return "post"
    cm = cutoff[:7]
    if month < cm:
        return "pre"
    if month > cm:
        return "post"
    # the cutoff month itself: pre only if the cutoff falls on or after its end
    day = cutoff[8:10]
    return "pre" if day >= "28" and _is_month_end(cutoff) else "boundary"


def _is_month_end(cutoff: str) -> bool:
    import calendar

    y, m, d = int(cutoff[:4]), int(cutoff[5:7]), int(cutoff[8:10])
    return d >= calendar.monthrange(y, m)[1]


def accuracy_rows(answers: list[dict], cutoff: str | None, tag: str = "read_MASKED"
                  ) -> list[dict]:
    """R2's own answers as regression rows. NO model call.

    `accuracy` follows R2's grading convention exactly: FLAT is not a
    directional call and is dropped rather than scored as a miss. `forecast` is
    the model's stated confidence -- its own claim about how informative this
    read is -- which is the quantity the paper's interaction scales.
    """
    out = []
    for r in answers:
        if str(r.get("tag")) != tag:
            continue
        d, fwd = r.get("dir"), r.get("fwd")
        if d in (None, 0) or fwd is None:
            continue
        month = str(r.get("month"))
        out.append({
            "name": str(r.get("name")), "month": month, "block": month,
            "accuracy": 1.0 if (float(fwd) > 0) == (int(d) > 0) else 0.0,
            "forecast": float(r.get("conf") or 0.0),
            "dir": int(d), "fwd": float(fwd), "LAP": 0.0,
            "era": era_of(month, cutoff),
        })
    return out


def split_summary(rows: list[dict]) -> dict:
    """Accuracy per era and per block, computed from what is already on disk."""
    out = {}
    for era in ("pre", "post", "boundary"):
        sub = [r for r in rows if r["era"] == era]
        blocks = sorted({r["block"] for r in sub})
        out[era] = {
            "cells": len(sub), "date_blocks": len(blocks),
            "months": blocks,
            "sign_accuracy": _r(float(np.mean([r["accuracy"] for r in sub])), 4) if sub else None,
            "mean_confidence": _r(float(np.mean([r["forecast"] for r in sub])), 4) if sub else None,
            "mean_LAP": _r(float(np.mean([r["LAP"] for r in sub])), 4) if sub else None,
        }
    return out


# ------------------------------------------------------------- the annotation

def lap_annotation(job: str, payload: dict, l3: dict | None = None) -> str | None:
    """`[LAP ...]` for a board row that quotes a PRE-CUTOFF LLM number, else None.

    Roadmap MUST NOT REGRESS #24 binds the quote, and the board is where a
    number is quoted. A read whose window lies entirely after the model's
    cutoff is not annotated: LAP is structurally near zero there and a badge on
    every row is a badge nobody reads. A read whose window CANNOT be determined
    is annotated `LAP UNKNOWN` rather than assumed post-cutoff -- a guard
    derives its inputs or refuses.
    """
    model = str(payload.get("model") or payload.get("reader") or "")
    backend = str(payload.get("backend") or "")
    if not backend and not model:
        return None                       # not an LLM read at all
    cut = MODEL_CUTOFFS.get(model or "Qwen2.5-7B-Instruct", {}).get("cutoff")
    start, _, how = read_window(payload)
    if start is None:
        return f"[LAP UNKNOWN: {how}]"
    if cut is None:
        return "[LAP UNKNOWN: this model publishes no cutoff, so no pre/post split is claimed]"
    if start >= cut[:7]:
        return None
    if l3 and l3.get("verdict"):
        return (f"[LAP {l3['verdict']} (L3 on {l3.get('panel')}, beta3 "
                f"{l3.get('beta3_pre')})]")
    return "[LAP NOT MEASURED: this row quotes a pre-cutoff LLM read and L3 has not run on it]"


def read_window(payload: dict) -> tuple[str | None, str | None, str]:
    """(first month, last month, how it was determined) for an LLM read receipt.

    Derived, in order: the receipt's own `year`/`year_to`, then its declared
    panel. Never guessed -- an undeterminable window returns `None` and says so.
    """
    y, y2 = payload.get("year"), payload.get("year_to")
    if y:
        return (f"{int(y)}-01", f"{int(y2 or y)}-12", "the receipt's own year/year_to")
    panel = str(payload.get("panel") or "")
    if panel in PANEL_WINDOWS:
        a, b = PANEL_WINDOWS[panel]
        return (a, b, f"{panel}'s declared window (TRIAL-R2 section 2)")
    return (None, None, "the receipt declares neither a year span nor a known panel")


def latest_l3_receipt(base: Path | None = None) -> dict | None:
    """The most recent L3 receipt on disk, by night directory name (never mtime:
    a fresh checkout rewrites every mtime -- CLAUDE.md session protocol 7)."""
    base = base or (REPO / "backend" / "data" / "optimus")
    if not Path(base).is_dir():
        return None
    best = None
    for night in sorted(Path(base).glob("night_factory_*")):
        for p in sorted(night.glob(f"{JOB}_run*.json")):
            if p.name.endswith("_smoke.json"):
                continue
            best = p
    if best is None:
        return None
    try:
        return json.loads(best.read_text(encoding="utf-8"))
    except Exception:                                              # noqa: BLE001
        return None


# ------------------------------------------------------------------- the job

def L3_lookahead(panel: str = "B", backend: str = "local_gguf", max_cells: int = 0,
                 model: str = "Qwen2.5-7B-Instruct", smoke: bool = False,
                 run: int = 1) -> dict:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    panel_name = "PANEL-A" if str(panel).upper().endswith("A") else "PANEL-B"
    cut = MODEL_CUTOFFS.get(model, {})
    cutoff = cut.get("cutoff")
    answers = xd.read_answers() if panel_name == "PANEL-B" else []
    base = {
        "job": JOB, "lane": "X", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "panel": panel_name, "backend": backend, "model": model,
        "model_cutoff_date": cutoff, "model_cutoff_source": cut.get("source"),
        "model_cutoff_confidence": cut.get("confidence"),
        "question": ("Is R2's accuracy concentrated in the cells where the model, asked "
                     "directly and shown nothing, already knows the answer?"),
        "lap_probe": {"purpose_tag": LAP_PROBE_PURPOSE, "system": LAP_PROBE_SYSTEM,
                      "user_template": LAP_PROBE_USER, "spend_usd": 0.0,
                      "why_unmasked": ("the probe measures memorisation and never feeds a "
                                       "graded forecast; R2's own read never names the company")},
        "deviations_from_the_spec": [
            ("the verdict uses a joint Wald test on (beta2, beta3) while the receipt "
             "reports beta3 as the paper's statistic -- a model that is right in high-LAP "
             "cells regardless of what it forecast plants a LEVEL effect on beta2 with a "
             "true beta3 of zero, and a beta3-only detector would call that CLEAN"),
        ],
    }
    if panel_name == "PANEL-A":
        return {**base,
                "verdict": ("REFUSED: PANEL-A has no persisted per-cell answers (the "
                            "2026-09-08 run graded 15,000 answers in memory and wrote a "
                            "summary), so L3's accuracy side cannot be computed without "
                            "re-reading 5,854 seconds of inference. PANEL-A's L3 needs a "
                            "NEW read with the frozen R2 prompt first"),
                "headline": "PANEL-A carries no answers file; L3 cannot read what was not written",
                **_protocol_and_stanzas(base, None, None, cutoff, cut),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    if not answers:
        return {**base,
                "verdict": (f"REFUSED: no answers at {xd.R2_PANEL_B_ANSWERS} on this "
                            "checkout, so there is no accuracy side to compute"),
                "headline": "no R2 answers on this checkout",
                **_protocol_and_stanzas(base, None, None, cutoff, cut),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    rows = accuracy_rows(answers, cutoff)
    if smoke:
        rows = rows[:40]
    elif max_cells:
        rows = rows[:max_cells]
    summary = split_summary(rows)
    cells = sorted({(r["name"], r["month"]) for r in rows})
    fp = xd.cells_fingerprint(cells)
    cells_path = OUT / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}_cells.json"
    cells_path.write_text(json.dumps(
        {"job": JOB, "run": run, "panel": panel_name, "probe": LAP_PROBE_USER, **fp,
         "cells": [list(c) for c in cells], "written_utc": _now()}, indent=1),
        encoding="utf-8")
    base.update({
        "accuracy_side": {
            "source": str(xd.R2_PANEL_B_ANSWERS), "answer_rows": len(answers),
            "gradeable_cells": len(rows), "tag": "read_MASKED",
            "convention": ("FLAT is not a directional call and is dropped, exactly as "
                           "night_r2_monthly_llm.grade does"),
            **summary},
        "cells_frozen": {**fp, "file": str(cells_path)},
        "n_cells_pre_cutoff": summary["pre"]["cells"],
        "n_cells_post_cutoff": summary["post"]["cells"],
    })

    refusal = _probe(backend)
    if refusal is not None:
        pre_empty = summary["pre"]["cells"] == 0
        note = ("the PRE-cutoff arm is EMPTY: " + panel_name + " covers "
                f"{PANEL_WINDOWS[panel_name][0]}..{PANEL_WINDOWS[panel_name][1]} and the "
                f"model's cutoff is {cutoff}, so every cell here is already the "
                "post-cutoff arm of the split (spec section 1.3). The paper's own "
                "before/after design needs PANEL-A, which has no persisted answers"
                ) if pre_empty else ""
        return {**base,
                "verdict": (
                    f"PENDING_MODEL: the accuracy side is computed from "
                    f"{len(rows)} cells already on disk and the {len(cells)} probe cells "
                    "are frozen; the recall probe needs the reader, which is not "
                    f"answering and which this job does not start. Probe said: {refusal}."
                    + (" " + note if note else "")),
                "headline": (
                    f"{panel_name}: {len(rows)} gradeable cells over "
                    f"{summary['post']['date_blocks'] + summary['pre']['date_blocks']} "
                    f"month blocks, sign accuracy pre {summary['pre']['sign_accuracy']} "
                    f"({summary['pre']['cells']} cells) / post "
                    f"{summary['post']['sign_accuracy']} ({summary['post']['cells']} "
                    f"cells); LAP probe PENDING_MODEL on {len(cells)} cells "
                    f"(sha256 {fp['cells_sha256'][:12]})"),
                "pending_when_the_reader_is_up": [
                    f"the date-only recall probe on {len(cells)} frozen cells, purpose "
                    f"{LAP_PROBE_PURPOSE}, temperature 0.0",
                    "LAP_i per cell = the probe's confidence when its recalled direction "
                    "matches the realised fwd, else 0",
                    "the accuracy ~ forecast + LAP + forecast:LAP regression, clustered "
                    "by month block, pre- and post-cutoff",
                    f"one command: python -m scripts.night_l3_lookahead --panel "
                    f"{panel_name[-1]} --run {run}",
                ],
                **_protocol_and_stanzas(base, None, None, cutoff, cut),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    # ---- the reader is up: run the probe, then the regression
    import backend.services.free_inference as fi
    from backend.services.model_provider import LanguageRefused, ProviderRefusal

    probes, refused = {}, 0
    for name, month in cells:
        try:
            rep = fi.complete(backend,
                              LAP_PROBE_USER.format(ticker=name, month=month),
                              system=LAP_PROBE_SYSTEM, max_tokens=32, temperature=0.0,
                              purpose=LAP_PROBE_PURPOSE)
            probes[(name, month)] = parse_probe(rep.text)
        except (ProviderRefusal, LanguageRefused):
            refused += 1
            probes[(name, month)] = (None, 0.0)
    for r in rows:
        d, c = probes.get((r["name"], r["month"]), (None, 0.0))
        r["LAP"] = lap_of(d, c, r["fwd"])
    summary = split_summary(rows)
    pre = interaction_test([r for r in rows if r["era"] == "pre"])
    post = interaction_test([r for r in rows if r["era"] == "post"])
    verdict, why = verdict_of(pre, post)
    base["accuracy_side"].update(summary)
    base["lap_probe"]["cells_probed"] = len(cells)
    base["lap_probe"]["refusals"] = refused
    return {**base,
            "regression_pre_cutoff": pre, "regression_post_cutoff": post,
            "beta3_pre": pre.get("beta3"), "beta3_pre_se": pre.get("beta3_se"),
            "beta3_pre_t": pre.get("beta3_t"), "beta3_pre_p": pre.get("beta3_p"),
            "beta3_post": post.get("beta3"), "beta3_post_se": post.get("beta3_se"),
            "beta3_post_t": post.get("beta3_t"), "beta3_post_p": post.get("beta3_p"),
            "lap_mean_pre": summary["pre"]["mean_LAP"],
            "lap_mean_post": summary["post"]["mean_LAP"],
            "verdict": f"{verdict}: {why}",
            "L3_verdict": verdict,
            "headline": (f"{panel_name}: beta3 pre {pre.get('beta3')} "
                         f"(p {pre.get('beta3_p')}), post {post.get('beta3')} "
                         f"(p {post.get('beta3_p')}); mean LAP "
                         f"{summary['pre']['mean_LAP']} pre / "
                         f"{summary['post']['mean_LAP']} post -> {verdict}"),
            "family_max_p": None,
            **_protocol_and_stanzas(base, pre, post, cutoff, cut, verdict=verdict,
                                    lap_mean=summary["post"]["mean_LAP"]),
            "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}


def _protocol_and_stanzas(base: dict, pre, post, cutoff, cut, *, verdict=None,
                          lap_mean=None) -> dict:
    read = bool(base.get("accuracy_side"))
    return {
        "P1_P6": pp.block(
            anonymised=read,
            anonymised_evidence=(base.get("accuracy_side") or {}).get("source"),
            placebo_run=False,
            time_locked_run=False,
            time_locked_model=("ChronoGPT is the same-era control spec section 1.6 scopes as "
                               "an OPTIONAL separate deliverable; it has no GGUF build"),
            cutoff=cutoff, cutoff_source=cut.get("source"),
            cutoff_confidence=cut.get("confidence"),
            universe_vintage_id=None,
            delisting_handled=True,
            universe_note=("L3 reads cells R2 already graded; R2's label construction "
                           "requires the successor month to be literally the next one"),
            flip_pass_rate=None, flip_n=0,
            flip_test="not run in this job: the flip test belongs to X2's counterfactuals",
            ece=None, n_bins=10, brier=None, brier_decomposition={},
            cost_curve_id="r2_trial.COST_BPS_PER_SIDE (this job prices no book of its own)",
            cost_bps_per_side=COST_BPS_PER_SIDE, realised_bps=None,
            costed=False, gross_reported_separately=False,
            single_agent_baseline_run=True,
            field_provenance={
                "dir, conf": "Qwen2.5-7B via the frozen TRIAL-R2 prompt (read from disk)",
                "RECALL, CONFIDENCE": f"the same model via LAP_PROBE_USER, purpose "
                                      f"{LAP_PROBE_PURPOSE}",
                "accuracy, LAP, beta*": "deterministic arithmetic in night_l3_lookahead"}),
        "LAP": pp.lap(True, score=lap_mean, verdict=verdict,
                      reason=None) if verdict else pp.lap(
            False, reason=("the recall probe has not run (PENDING_MODEL), so no per-cell "
                           "LAP exists yet; the accuracy side and the frozen probe cells "
                           "are in this receipt")),
        "anonymisation_gap": pp.anonymisation_gap(
            reason=("L3 measures memorisation, not masking cost; X_anon_gap owns the gap "
                    "and this receipt does not restate it")),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", choices=("A", "B"), default="B")
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--model", default="Qwen2.5-7B-Instruct", choices=sorted(MODEL_CUTOFFS))
    ap.add_argument("--max-cells", type=int, default=0)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    p = L3_lookahead(panel=a.panel, backend=a.backend, model=a.model,
                     max_cells=a.max_cells, smoke=a.smoke, run=a.run)
    p["run"] = a.run
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"{JOB}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\n{JOB}: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    reasons = pp.refuse_reasons(JOB, p)
    if reasons:
        print("  PROTOCOL INCOMPLETE: " + "; ".join(reasons))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
