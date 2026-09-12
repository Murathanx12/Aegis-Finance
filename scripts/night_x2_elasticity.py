"""X2_elasticity -- the belief-elasticity feature, cheap leg first.

Everything that does not need the model is arithmetic on C1's 6,935 rows and
runs in seconds: which pairs have a principled denominator, which do not and
why, the placebo pairing, and the feature table's shape. The forecasts
themselves need the reader, which is down, so this writes `PENDING_MODEL` with
the pair list frozen and hashed and the projected wall time stated.

THE WALL TIME, AND WHY `--max-cells` EXISTS
===========================================
Spec section 3.6: roughly 13,609 local calls for the primary pass (one cached
real-headline call per uid plus one per sign_flip), about 19,302 with the
escalation leg, plus a placebo call per uid -- around 26,000 calls at the
measured 4-12 s each (C1's own `latency_s` field, median ~5-6 s), which is
**36-43 hours of serial wall time on the laptop GPU**. That is a multi-night
`night_factory` batch, not an afternoon. `--max-cells` exists so the first run
can be 300 pairs and produce a real number the same night, and the receipt
prints both the sample and the full projection so nobody mistakes one for the
other.

    python -m scripts.night_x2_elasticity --max-cells 300 --run 1
    python -m scripts.night_factory_jobs X2_elasticity --run 1
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

from backend.services import belief_elasticity as be                    # noqa: E402
from backend.services import event_vocabulary as vocab                   # noqa: E402
from backend.services import protocol_p16 as pp                         # noqa: E402
from backend.services import x_lane_data as xd                          # noqa: E402
from backend.services.portfolio_intelligence.r2_trial import (          # noqa: E402
    COST_BPS_PER_SIDE, PROMPT, SYSTEM, fingerprint as prereg_fingerprint,
    verify_frozen)
from scripts.night_l3_lookahead import MODEL_CUTOFFS                    # noqa: E402
from scripts.night_r2_monthly_llm import _probe, _r, parse              # noqa: E402

RUN_DATE = "2026-09-12"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
JOB = "X2_elasticity"
PURPOSE = "x2_belief_elasticity"

#: Spec section 3.6's own projection, carried so the receipt states it rather than
#: leaving a reader to recompute it from a latency field.
FULL_PASS = {
    "real_headline_calls_cached_one_per_uid": 6935,
    "sign_flip_calls": 6674,
    "escalation_calls": 6026,
    "placebo_calls": 6935,
    "total_calls_primary_plus_secondary_plus_placebo": 26570,
    "measured_latency_s_per_call": "4-12 (C1's own latency_s; median ~5-6)",
    "projected_serial_wall_time_hours": "36-43",
    "reading": ("an OVERNIGHT-SCALE multi-night batch, not an afternoon job. "
                "--max-cells makes the first run a 300-pair sample that produces a "
                "real number the same night; the projection above is what the full "
                "pass costs in time. Dollars: $0.00, the backend is local_gguf"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- L2 vocabulary
#: C1's own event kinds, mapped onto L2's frozen 40-id vocabulary where the
#: mapping is a FUNCTION. Most of C1's kinds are not: `PRODUCT` is a launch or a
#: recall, `LEGAL` is a filing or a settlement, `FINANCING` is debt or dilution,
#: and the two have opposite direction priors. Those are recorded as ambiguous
#: with the candidates named, never collapsed to whichever id comes first -- a
#: forced mapping would put a positive prior on half the recalls in the file.
C1_KIND_TO_VOCABULARY: dict[str, str] = {
    "EARNINGS": "earnings_report",
    "GUIDANCE": "guidance_change",
    "M&A": "mergers_acquisitions",
}

#: Named, with the reason. `ANALYST` is the largest kind in C1 (1,218 of 6,935)
#: and the L2 vocabulary HAS NO ANALYST TYPE -- RavenPack's public taxonomy has
#: `price-target`, the spec's section 1.2 does not, and that is a gap in the
#: vocabulary rather than a defect in this mapping. Recorded here so the next
#: reader finds it instead of re-deriving it.
C1_KIND_UNMAPPED: dict[str, str] = {
    "ANALYST": ("no vocabulary id: the 40-id table has no analyst-action or "
                "price-target type. C1's LARGEST kind"),
    "MACRO": ("ambiguous over macro_rate_decision / macro_inflation_print / "
              "macro_labor_report / tariff_or_trade_policy / sanction"),
    "PRODUCT": "ambiguous over product_launch_or_innovation / product_recall_or_defect",
    "MANAGEMENT": ("ambiguous over management_change_departure / "
                   "management_change_appointment"),
    "REGULATORY": ("ambiguous over regulatory_approval / "
                   "regulatory_investigation_or_action"),
    "FINANCING": ("ambiguous over debt_issuance_or_obligation / "
                  "equity_issuance_dilution -- opposite direction priors"),
    "LEGAL": "ambiguous over litigation_filed / litigation_settlement",
    "OTHER": "unmapped by construction",
}

#: C1's magnitude words to the vocabulary's buckets. MEDIUM is MODERATE; C1 has
#: no NEGLIGIBLE and no EXTREME, so neither is ever produced from this file.
C1_MAGNITUDE_TO_BUCKET = {"SMALL": "SMALL", "MEDIUM": "MODERATE", "LARGE": "LARGE"}


def c1_vocabulary_mapping(rows: list[dict]) -> dict:
    """How much of C1 the L2 vocabulary can type, counted rather than asserted.

    `direction` is mapped only where C1 committed to a sign: `UNCLEAR` becomes
    `None` and is counted. It does NOT become 0 -- 0 means "real event, no
    directional implication by itself" in L2's contract, which is a different
    claim from "the reader could not tell".
    """
    mapped, unmapped, missing = {}, {}, 0
    directions = {"signed": 0, "unclear": 0, "missing": 0}
    buckets = {}
    for row in rows:
        kind = row.get("event_type")
        if not kind:
            missing += 1
        elif kind in C1_KIND_TO_VOCABULARY:
            vid = C1_KIND_TO_VOCABULARY[kind]
            mapped[vid] = mapped.get(vid, 0) + 1
        else:
            unmapped[str(kind)] = unmapped.get(str(kind), 0) + 1
        d = be.signed(row.get("direction"))
        if row.get("direction") is None:
            directions["missing"] += 1
        elif d in (-1, 1):
            directions["signed"] += 1
        else:
            directions["unclear"] += 1
        b = C1_MAGNITUDE_TO_BUCKET.get(str(row.get("magnitude") or "").upper())
        buckets[b or "unmapped"] = buckets.get(b or "unmapped", 0) + 1
    n = len(rows)
    return {
        "vocabulary_hash": vocab.VOCABULARY_HASH,
        "n_c1_rows": n,
        "mapped_rows": sum(mapped.values()),
        "mapped_share": _r(sum(mapped.values()) / n, 4) if n else None,
        "mapped_by_vocabulary_id": dict(sorted(mapped.items(), key=lambda kv: -kv[1])),
        "unmapped_kinds": dict(sorted(unmapped.items(), key=lambda kv: -kv[1])),
        "unmapped_reasons": {k: v for k, v in C1_KIND_UNMAPPED.items() if k in unmapped},
        "rows_with_no_kind": missing,
        "direction": directions,
        "magnitude_buckets": dict(sorted(buckets.items(), key=lambda kv: -kv[1])),
        "reading": ("only the three kinds whose mapping is a FUNCTION are mapped. The "
                    "rest name two or more vocabulary ids with different direction "
                    "priors, and ANALYST names none at all -- the 40-id table has no "
                    "analyst-action type, which is a gap in the vocabulary, not in "
                    "this mapping"),
    }



def digest_of(text: str) -> str:
    """One document in R2's exact digest format, so the frozen prompt sees the
    shape it was registered against."""
    return "- " + str(text).strip().replace("\n", " ")[:320]


def ask(text: str, backend: str, max_tokens: int = 48):
    """R2's prompt, R2's parser. Neither is re-implemented here."""
    import backend.services.free_inference as fi
    from backend.services.model_provider import LanguageRefused, ProviderRefusal

    try:
        rep = fi.complete(backend, PROMPT.format(digest=digest_of(text)), system=SYSTEM,
                          max_tokens=max_tokens, temperature=0.0, purpose=PURPOSE)
    except (ProviderRefusal, LanguageRefused) as exc:
        return None, 0.0, 0, 0, f"REFUSED {type(exc).__name__}"
    d, c = parse(rep.text)
    return d, c, int(getattr(rep, "tokens_in", 0) or 0), \
        int(getattr(rep, "tokens_out", 0) or 0), "ok"


def score_pairs(pair_rows: list[dict], answers: dict) -> list[dict]:
    """Elasticity and the flip test per pair, from already-collected answers.

    `answers` maps a text to its `(direction, confidence)` reply, so the real
    headline's call is made ONCE per uid and reused across that uid's
    counterfactuals -- the caching spec section 3.6 counts on.
    """
    out = []
    for p in pair_rows:
        real = answers.get(p["real_text"])
        cf = answers.get(p["cf_text"])
        if real is None or cf is None:
            continue
        p_real = be.signed_p(real[0], real[1])
        p_cf = be.signed_p(cf[0], cf[1])
        out.append({**p, "p_real": _r(p_real, 4), "p_cf": _r(p_cf, 4),
                    "elasticity": _r(be.elasticity(p_real, p_cf, p["delta_event"]), 5),
                    "flip_pass": be.flip_pass(p_real, p_cf, p["delta_event"])})
    return out


def summarise(scored: list[dict], placebo: list[dict]) -> dict:
    """The receipt's numbers: elasticity by kind, the placebo null, the paired t."""
    def stats(rows, kind=None):
        vals = [r["elasticity"] for r in rows
                if r.get("elasticity") is not None and (kind is None or r["kind"] == kind)]
        if not vals:
            return {"n": 0, "mean": None, "sd": None}
        a = np.asarray(vals, dtype="float64")
        return {"n": int(a.size), "mean": _r(float(a.mean()), 5),
                "sd": _r(float(a.std(ddof=1)), 5) if a.size > 1 else None}

    sf, esc = stats(scored, "sign_flip"), stats(scored, "escalation")
    pl = stats(placebo)
    by_uid_true = {r["uid"]: r["elasticity"] for r in scored
                   if r["kind"] == "sign_flip" and r.get("elasticity") is not None}
    by_uid_pl = {r["uid"]: r["elasticity"] for r in placebo
                 if r["kind"] == "sign_flip" and r.get("elasticity") is not None}
    shared = sorted(set(by_uid_true) & set(by_uid_pl))
    paired = None
    if len(shared) >= 6:
        d = np.array([by_uid_true[u] - by_uid_pl[u] for u in shared], dtype="float64")
        se = float(d.std(ddof=1)) / np.sqrt(len(d)) if len(d) > 1 else 0.0
        paired = {"n_uids": len(shared), "mean_difference": _r(float(d.mean()), 5),
                  "t": _r(float(d.mean() / se), 3) if se > 0 else None,
                  "note": ("paired on the SAME uid: the true pair's elasticity minus the "
                           "elasticity that uid's headline shows against an unrelated "
                           "headline's counterfactual")}
    flips = [r["flip_pass"] for r in scored
             if r["kind"] == "sign_flip" and r.get("flip_pass") is not None]
    two_sample = None
    if sf["n"] and pl["n"]:
        a = np.array([r["elasticity"] for r in scored
                      if r["kind"] == "sign_flip" and r.get("elasticity") is not None])
        b = np.array([r["elasticity"] for r in placebo
                      if r.get("elasticity") is not None])
        if a.size > 1 and b.size > 1:
            se = np.sqrt(a.var(ddof=1) / a.size + b.var(ddof=1) / b.size)
            two_sample = {"t": _r(float((a.mean() - b.mean()) / se), 3) if se > 0 else None,
                          "n_true": int(a.size), "n_placebo": int(b.size)}
    return {
        "elasticity_sign_flip": sf, "elasticity_escalation": esc,
        "elasticity_placebo": pl,
        "paired_t_true_vs_placebo": paired,
        "two_sample_t_true_vs_placebo": two_sample,
        "flip_test_pass_rate": _r(float(np.mean(flips)), 4) if flips else None,
        "flip_test_n": len(flips),
        "reading": ("the placebo distribution is the null, never zero: an elasticity "
                    "that looks large against 0 and identical to the placebo is the "
                    "arithmetic of the formula, not a property of the news"),
    }


def _protocol(*, evidence: str | None, placebo_evidence: str | None,
              flip_rate, flip_n, nothing_was_read: bool) -> dict:
    cut = MODEL_CUTOFFS["Qwen2.5-7B-Instruct"]
    return pp.block(
        anonymised=True,
        anonymised_evidence=str(be.C1_PATH),
        placebo_run=not nothing_was_read, placebo_evidence=placebo_evidence,
        time_locked_run=False,
        time_locked_model=("ChronoGPT is an OPTIONAL separate deliverable (spec section "
                           "1.6) and has no GGUF build"),
        cutoff=cut["cutoff"], cutoff_source=cut["source"],
        cutoff_confidence=cut["confidence"],
        universe_vintage_id=None, delisting_handled=False,
        universe_note=("X2 produces a FEATURE, not a book: it selects no universe and "
                       "holds no position, so there is no vintage to respect here. The "
                       "P7 vintage binds whichever book consumes the feature"),
        flip_pass_rate=flip_rate, flip_n=flip_n,
        flip_test=("sign_flip counterfactual: sign(p_cf - p_real) == sign(delta_event), "
                   "a tie counts as FAIL (spec section 3.5)"),
        ece=None, n_bins=10, brier=None, brier_decomposition={},
        cost_curve_id=("none: X2 emits a feature and prices no book. The consuming book "
                       "charges r2_trial.COST_BPS_PER_SIDE"),
        cost_bps_per_side=COST_BPS_PER_SIDE, realised_bps=None,
        costed=False, gross_reported_separately=False,
        single_agent_baseline_run=True,
        field_provenance={
            "anon, counterfactuals[].text": "C1's extraction (local_gguf), read from disk",
            "p_real, p_cf": f"Qwen2.5-7B via the frozen TRIAL-R2 prompt, purpose {PURPOSE}",
            "delta_event, elasticity, flip_pass":
                "deterministic arithmetic in backend.services.belief_elasticity"},
        homogeneity_metric=None)


def _stanzas(flip_rate, flip_n, nothing_was_read, placebo_evidence, evidence) -> dict:
    return {
        "P1_P6": _protocol(evidence=evidence, placebo_evidence=placebo_evidence,
                           flip_rate=flip_rate, flip_n=flip_n,
                           nothing_was_read=nothing_was_read),
        "LAP": pp.lap(False, reason=(
            "X2 reads C1's counterfactual REWRITES, which never existed before C1 wrote "
            "them, so no model can have memorised their outcome. The real headlines they "
            "perturb carry L3's own LAP; this job forecasts no dated outcome of its own")),
        "anonymisation_gap": pp.anonymisation_gap(reason=(
            "every text X2 reads is already anonymised (C1's `anon` field and its "
            "transforms), and there is no raw arm to compare against. X_anon_gap owns "
            "the gap")),
    }


def X2_elasticity(backend: str = "local_gguf", max_cells: int = 0, seed: int = be.SEED,
                  kinds: tuple[str, ...] = be.ELASTIC_KINDS, smoke: bool = False,
                  run: int = 1) -> dict:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    verify_frozen(SYSTEM, PROMPT)
    rows = be.load_c1()
    base = {
        "job": JOB, "lane": "X", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "backend": backend, "PREREGISTRATION": prereg_fingerprint(),
        "question": ("How much does the model's forecast move when the NEWS changes and "
                     "the calendar does not?"),
        "PIT_rule": be.pit_note(),
        "full_pass_projection": FULL_PASS,
        "purpose_tag": PURPOSE,
    }
    if not rows:
        return {**base, "verdict": f"REFUSED: no C1 rows at {be.C1_PATH} on this checkout",
                "headline": "C1's counterfactual file is not on this checkout",
                **_stanzas(None, 0, True, None, None),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    all_pairs = be.pairs(rows, kinds)
    drops = be.drop_reasons(rows, kinds)
    base["l2_vocabulary_mapping"] = c1_vocabulary_mapping(rows)
    base["construction"] = {
        "c1_rows_status_ok": len(rows), "uids": len({r["uid"] for r in rows}),
        "pairs_with_a_defined_denominator": len(all_pairs),
        "per_kind": drops,
        "why_actor_timing_is_excluded": (
            "it changes WHO or WHEN, not the event's sign or magnitude, so delta_event "
            "has no principled scale; it is kept for the flip diagnostic only"),
        "escalation_convention_MEASURED": (
            "the spec proposed delta = +1 fixed and asked for it to be re-verified. "
            f"Counted over all C1 rows: {drops.get('escalation', {}).get('kept', 0)} "
            "escalations agree with their parent's direction and "
            f"{drops.get('escalation', {}).get('escalation_points_the_other_way', 0)} "
            "point the other way. A fixed +1 would be wrong for the second group, so "
            "delta = +1 in the PARENT's signed frame and disagreeing cells are dropped "
            "and counted, never forced"),
    }

    n_draw = 12 if smoke else (min(max_cells, len(all_pairs)) if max_cells else len(all_pairs))
    drawn = _draw(all_pairs, n_draw, seed)
    placebo = be.placebo_pairs(drawn, seed=seed)
    fp = xd.cells_fingerprint([(p["uid"], p["kind"], p["cf_index"]) for p in drawn])
    cells_path = OUT / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}_cells.json"
    cells_path.write_text(json.dumps(
        {"job": JOB, "run": run, "seed": seed, "kinds": list(kinds), **fp,
         "pairs": [{k: p[k] for k in ("uid", "cf_index", "kind", "delta_event",
                                      "effective_at", "symbols")} for p in drawn],
         "written_utc": _now()}, indent=1), encoding="utf-8")
    base["cells_frozen"] = {**fp, "file": str(cells_path), "seed": seed,
                            "placebo_pairs": len(placebo)}

    refusal = _probe(backend)
    if refusal is not None:
        return {**base,
                "verdict": (
                    f"PENDING_MODEL: {len(all_pairs)} pairs have a defined denominator, "
                    f"{len(drawn)} are frozen for this run with {len(placebo)} placebo "
                    "pairs, and the elasticity arithmetic is tested; the forecasts need "
                    "the reader, which is not answering and which this job does not "
                    f"start. Probe said: {refusal}"),
                "headline": (
                    f"{len(all_pairs)} elastic pairs from {len(rows)} C1 rows "
                    f"({drops.get('sign_flip', {}).get('kept', 0)} sign_flip, "
                    f"{drops.get('escalation', {}).get('kept', 0)} escalation); "
                    f"{len(drawn)} frozen at sha256 {fp['cells_sha256'][:12]}; NO model "
                    f"call was made. Full pass is "
                    f"{FULL_PASS['projected_serial_wall_time_hours']} h serial"),
                "pending_when_the_reader_is_up": [
                    f"one cached forecast per unique text: {len({p['real_text'] for p in drawn}) + len({p['cf_text'] for p in drawn})} calls for this draw",
                    "elasticity = (p_cf - p_real) / delta_event per pair",
                    "the flip test per sign_flip cell (a tie is a FAIL)",
                    f"the placebo leg: {len(placebo)} mismatched pairs, seed {seed}",
                    f"one command: python -m scripts.night_x2_elasticity --max-cells "
                    f"{n_draw} --run {run}",
                ],
                **_stanzas(None, 0, True, str(cells_path), str(be.C1_PATH)),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    texts = sorted({p["real_text"] for p in drawn} | {p["cf_text"] for p in drawn}
                   | {p["cf_text"] for p in placebo})
    answers, tin, tout, refused = {}, 0, 0, 0
    for text in texts:
        d, c, ti, to, status = ask(text, backend)
        tin += ti
        tout += to
        if status != "ok":
            refused += 1
            continue
        answers[text] = (d, c)
    scored = score_pairs(drawn, answers)
    placebo_scored = score_pairs(placebo, answers)
    summary = summarise(scored, placebo_scored)
    features = be.feature_rows(scored, placebo_scored)
    table = be.write_feature_table(features, run_date=RUN_DATE, run=run)

    rate, n_flip = summary["flip_test_pass_rate"], summary["flip_test_n"]
    verdict = _verdict(summary)
    return {**base,
            "n_uids": len({p["uid"] for p in drawn}),
            "n_pairs_scored": len(scored), "n_placebo_scored": len(placebo_scored),
            "n_unique_texts_called": len(texts), "n_real_calls_cached": len(texts),
            "SUMMARY": summary,
            "feature_table": table,
            "usage": {"tokens_in": tin, "tokens_out": tout, "cost_usd": 0.0,
                      "refusals": refused, "purpose": PURPOSE},
            "verdict": verdict,
            "headline": (
                f"{len(scored)} pairs: sign_flip elasticity "
                f"{summary['elasticity_sign_flip']['mean']} vs placebo "
                f"{summary['elasticity_placebo']['mean']}, paired t "
                f"{(summary['paired_t_true_vs_placebo'] or {}).get('t')}; flip test "
                f"{rate} on {n_flip} cells"),
            "family_max_p": None,
            **_stanzas(rate, n_flip, False, str(cells_path), str(be.C1_PATH)),
            "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}


def _verdict(summary: dict) -> str:
    sf = summary["elasticity_sign_flip"]
    paired = summary["paired_t_true_vs_placebo"] or {}
    t = paired.get("t")
    rate = summary["flip_test_pass_rate"]
    if sf["n"] == 0:
        return "CANNOT DETERMINE: no pair produced a parsable answer on both legs"
    if t is None:
        return (f"EXPLORATORY: sign_flip elasticity {sf['mean']} on {sf['n']} pairs, "
                f"flip test {rate}; fewer than 6 uids carry both a true and a placebo "
                "leg, so there is no paired comparison and no claim")
    if t >= 2.0:
        return (f"PRODUCT_PROMISING: the true pair's elasticity exceeds its own placebo "
                f"by {paired.get('mean_difference')} on {paired.get('n_uids')} uids, "
                f"t {t}; flip test {rate} on {summary['flip_test_n']} cells")
    return (f"FAILED_VARIANT: the true pair's elasticity does not separate from its own "
            f"placebo (difference {paired.get('mean_difference')}, t {t} on "
            f"{paired.get('n_uids')} uids); flip test {rate}")


def _draw(pair_rows: list[dict], n: int, seed: int) -> list[dict]:
    """`n` pairs, stratified by KIND so a sample is never all of one leg."""
    keys = [(p["uid"], p["kind"], p["cf_index"]) for p in pair_rows]
    by_key = {k: p for k, p in zip(keys, pair_rows)}
    chosen = xd.stratified_cells(keys, n=n, seed=seed, block_of=lambda k: k[1])
    return [by_key[k] for k in chosen]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--max-cells", type=int, default=0,
                    help="pairs to score this run; 0 = every pair (36-43 h serial)")
    ap.add_argument("--seed", type=int, default=be.SEED)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    p = X2_elasticity(backend=a.backend, max_cells=a.max_cells, seed=a.seed,
                      smoke=a.smoke, run=a.run)
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
