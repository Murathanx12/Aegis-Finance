"""Dated amendment to CRSP_BLEND_v0's kill rule (2026-09-29), written BEFORE any read.

    python -m scripts.crsp_blend_v0_kill_amendment    # writes the amendment once; refuses to overwrite

The frozen registration (REGISTRATION_CRSP_BLEND_v0_2026-09-28_20260929T082258Z.json)
is NOT modified; its sha256 is printed on the amendment. The kill line it names
("-1.645 x its 21-draw noise sd") was never computed for this book, and the only
implementation (`shadow_bayes_rule.kill_rule_power`) builds the sd from
idiosyncratic risk alone. This script measures the gap's own volatility from the
same CRSP series the blend was chosen on and derives the line from it
(`shadow_bayes_rule.kill_rule_from_measured_gap`). $0, no LLM, no network.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import shadow_bayes_rule as SB                            # noqa: E402

OPT = REPO / "backend" / "data" / "optimus"
SB_DIR = OPT / "shadow_bayes"
REG = SB_DIR / "REGISTRATION_CRSP_BLEND_v0_2026-09-28_20260929T082258Z.json"
RULE_RECEIPT = SB_DIR / "crsp_blend_v0_2026-09-28_20260929T082258Z.json"
OUT = SB_DIR / "AMENDMENT_CRSP_BLEND_v0_KILL_RULE_2026-09-29.json"
SERIES = OPT / "crsp_rebuild" / "library_series_LIB_2026-09-29T0802Z"
RULES = ("px_vs_ma200_large", "trend_quality_trend", "co03_reversal_in_high_margin", "vol_compression")
CLAIM_MONTHLY = 0.0064          # the registration's full-sample blend estimate (+0.64%/mo)
WALK_FORWARD_MONTHLY = 0.003    # the review's walk-forward estimate (+0.14 to +0.34; ~0.3)
READS = (21, 63, 126)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def measured_series() -> tuple[pd.Series, pd.Series]:
    gap, mkt = {}, {}
    for r in RULES:
        d = pd.read_parquet(SERIES / f"{r}.parquet", columns=["rule_net", "twin21_net", "market"])
        gap[r] = d["rule_net"] - d["twin21_net"]
        mkt[r] = d["rule_net"] - d["market"]
    return (pd.concat(gap.values(), axis=1).dropna().mean(axis=1),
            pd.concat(mkt.values(), axis=1).dropna().mean(axis=1))


def horizon_sd(s: pd.Series, months: int) -> float:
    return float(s.rolling(months).sum().dropna().std()) if months > 1 else float(s.std())


def build() -> dict:
    from backend.services import lib_forward_trial as LFT                # noqa: PLC0415
    reg_sha = _sha(REG)
    reg = json.loads(REG.read_text(encoding="utf-8"))
    rule = json.loads(RULE_RECEIPT.read_text(encoding="utf-8"))
    gap, vsm = measured_series()
    sd_full = float(gap.std())
    sd_recent = float(gap["2017":"2024"].std())
    sd_m_full = float(vsm.std())
    # The line must hold a <= 5% false kill in BOTH the full sample and the most
    # recent regime, so the LARGER measured sd sets it (declared before any read).
    sd_use = max(sd_full, sd_recent)
    six_measured = horizon_sd(gap, 6)
    kill = SB.kill_rule_from_measured_gap(sd_use, sessions=126, claimed_edge_monthly=CLAIM_MONTHLY)
    kill_wf = SB.kill_rule_from_measured_gap(sd_use, sessions=126, claimed_edge_monthly=WALK_FORWARD_MONTHLY)
    readings = {}
    for n in READS:
        k = SB.kill_rule_from_measured_gap(sd_use, sessions=n, claimed_edge_monthly=CLAIM_MONTHLY)
        m = n / 21.0
        readings[str(n)] = {
            "sd_D_vs_twin": k["sd_D"],
            "band_vs_twin_1645": [round(-1.645 * k["sd_D"], 4), round(1.645 * k["sd_D"], 4)],
            "sd_D_vs_market": round(sd_m_full * np.sqrt(m), 5),
            "expected_D_if_claim_true": k["expected_D_if_claim_true"],
            "P_D_positive_if_claim_true": k["P_D_positive_if_claim_true"],
            "action": ("KILL TEST (the only one)" if n == 126 else
                       "report only: no kill, no promotion (one kill look keeps the false-kill rate at 5%)")}
    old_line = -0.047          # the idiosyncratic-only line, as the review computed it
    luck = LFT.luck_table([4, 30, 61], [0.0, 0.3], z_bar=2.0, n_sim=100_000, seed=20260928)
    held = rule.get("held", {})
    rr_hash = reg["rule_receipt"].split("hash ")[-1].rstrip(")")
    return {
        "amendment": "CRSP_BLEND_v0 kill rule",
        "dated": "2026-09-29",
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "written_before": "any read of the book (first reading at 21 sessions after the 2026-09-29 entry)",
        "amends": {"path": str(REG.relative_to(REPO)).replace("\\", "/"), "sha256": reg_sha,
                   "modified": False, "book_id": reg["book_id"], "twin_book_id": reg["twin_book_id"]},
        "what_does_not_change": (f"the book, its twin, the four rules, the rule receipt (hash {rr_hash}), the "
                                 "entry, the primary statistic (book minus matched twin21) and the licence. "
                                 "Nothing is voided."),
        "owner_decision": "keep the book; its FORWARD record is the evidence (2026-09-29)",
        "source": ("docs/reviews/REVIEW_2026-09-29_CRSP_BLEND.md section 6 and Verdict; "
                   "docs/research_notes/2026-09-29/library_on_crsp_2026-09-29.md (afternoon follow-ups)"),
        "reviewed_weaknesses": [
            {"id": "CHOSEN_AFTER_LOOKING",
             "what": ("rank 2 of 40,920 candidate blends; the '1991-2016 holdout' was used to select it; "
                      "the combination search was not deflated at its full count")},
            {"id": "SELECTION_FAILS_FORWARD",
             "what": ("the same selection procedure (filter -> clusters -> best four) run forward in time earns "
                      "about 0 on fixed splits and +0.14 to +0.34%/mo, t < 1.6, walk-forward: FAILED_VARIANT "
                      "as a procedure")},
            {"id": "WEAK_BENCHMARK",
             "what": ("the twin compounds at 5.9%/yr against the market's 10.5%; against the market the blend "
                      "is t 1.6 and about zero in 2010-2019")},
            {"id": "ERA_DEPENDENT_UNIVERSE",
             "what": ("a nominal $100M floor makes 1995-99 a 17-to-113-name mega-cap book, where the biggest "
                      "years sit")},
            {"id": "COSTS_AND_CAPACITY",
             "what": ("two sleeves turn over 77-92%/month in $3-20M/day names at a flat 2026 cost schedule; "
                      "era spreads cut the vs-market edge to +0.17%/mo (t 0.6)")},
            {"id": "DECAY", "what": "co03 -0.27 and vol_compression -0.03 %/mo in the 2020s"},
            {"id": "KILL_SD_UNDEFINED",
             "what": ("the registered '21-draw noise sd' was never computed for this book; the only "
                      "implementation is idiosyncratic-only and ignores the book-vs-twin factor mismatch "
                      "(market -0.15, SMB -0.25, BAB +0.2), giving a line near -4.7% and a ~21% false kill "
                      "under zero edge")},
        ],
        "followups_2026_09_29": {
            "receipt": "backend/data/optimus/crsp_rebuild/followups_FU_2026-09-29T0900Z.json",
            "selection_procedure_forward": "fails forward: ~0 on fixed splits, +0.14 to +0.34%/mo t < 1.6 walk-forward",
            "co03_with_frictions": (
                "skip one day + Corwin-Schultz per-name spreads + 4-month fundamentals lag: rule minus twin "
                "+0.56%/mo, t 1.91 (MDE 0.82) in 2001-2024, -0.01 in 2017-2024, and 2001 alone is +79 of +161; "
                "rule minus MARKET -0.81%/mo (t -1.52) in 2001-2024, book CAGR -5.9% vs the market's 11.2%. "
                "CANNOT_DISTINGUISH vs the twin, DEPRIORITIZED, negative vs the market"),
            "large_cap_trend_rank_floor": (
                "with a top-300/500 dollar-volume rank floor, 1991-2024 keeps t > 2 in three of four cells but "
                "1995-99 carries 38-74% of every total; after 2000 mom_12_1 is +0.11 to +0.41%/mo (t 0.4-1.5) "
                "and px_vs_ma200 top-300 +0.32 (t 1.3); only px_vs_ma200 top-500 reaches t 2.05, carried by "
                "2021: large-cap trend fades after 2000"),
        },
        "measured_gap_volatility": {
            "series": str(SERIES.relative_to(REPO)).replace("\\", "/"),
            "construction": ("mean of the four rules' (rule_net - twin21_net) monthly series, as in "
                             "crsp_blend_book.evidence()"),
            "window": [str(gap.index.min().date()), str(gap.index.max().date())], "n_months": int(len(gap)),
            "sd_monthly_full": round(sd_full, 5), "sd_monthly_2017_2024": round(sd_recent, 5),
            "sd_6m_overlapping_sum_full": round(six_measured, 5),
            "sd_6m_sqrt_time_full": round(sd_full * float(np.sqrt(6)), 5),
            "lag1_autocorr": round(float(gap.autocorr(1)), 4),
            "sd_monthly_vs_market_full": round(sd_m_full, 5),
            "sd_used": round(sd_use, 5),
            "sd_used_rule": ("max(full-sample, 2017-2024) monthly sd, scaled by sqrt(months): holds the false "
                             "kill at <= 5% in either regime"),
            "scale": (f"book scale: each of the four sleeves is {rule.get('sleeve_weight')} of the book; held "
                      f"weights sum to {round(sum(held.values()), 4)} (gated-off sleeves hold cash)"),
        },
        "kill_rule": {
            "replaces": reg["kill_rule"],
            "statistic": ("D = book minus matched twin21 (b0a33a92c56fddb1 minus b35d287bdcbf00bb), "
                          "cumulative, 126 sessions after entry"),
            "kill_line": kill["kill_line"],
            "rule": (f"D_126 < {kill['kill_line'] * 100:+.2f}% -> FAILED_VARIANT; D_126 > "
                     f"{-kill['kill_line'] * 100:+.2f}% -> evidence FOR (still CANNOT_DISTINGUISH as a claim); "
                     "otherwise CANNOT_DISTINGUISH"),
            "P_kill_if_zero_edge": kill["P_kill_if_zero_edge"],
            "old_line_as_reviewed": old_line,
            "old_line_real_false_kill_rate": round(SB.false_kill_rate(old_line, kill["sd_D"]), 4),
            "computation": kill,
        },
        "power": {
            "claimed_edge_0.64pct_mo": {k: kill[k] for k in (
                "expected_D_if_claim_true", "P_kill_if_claim_true", "P_D_above_plus_z_sd_if_claim_true",
                "P_D_positive_if_claim_true", "mde80_one_sided_5pct", "months_to_t2_if_claim_true")},
            "walk_forward_0.30pct_mo": {k: kill_wf[k] for k in (
                "expected_D_if_claim_true", "P_kill_if_claim_true", "P_D_above_plus_z_sd_if_claim_true",
                "P_D_positive_if_claim_true", "months_to_t2_if_claim_true")},
            "reading": ("at 126 sessions the book can only catch a large negative gap. Under the claimed edge it "
                        "reaches the 'evidence for' band with the probability above, and P(D > 0) is only modestly "
                        "above the 0.5 of a zero edge. Confirming the claim at t 2 takes the months stated: years."),
        },
        "reading_schedule": {
            "sessions": list(READS),
            "every_reading_reports": [
                "D vs the matched twin21 (b35d287bdcbf00bb), cumulative, with its +/-1.645 sd band from by_session",
                "D vs the MARKET (SPY total return) over the same sessions, with its sd from by_session",
                "the luck table below, printed beside the number",
                ("the realised daily sd of the forward gap beside the measured sd used here; a realised sd more "
                 "than 50% above it at 63 sessions is reported (the line is NOT moved)"),
            ],
            "by_session": readings,
        },
        "luck_table": {"what": ("P(the best of K zero-skill books reads z >= 2) and E[best z]; K = 4 shadow books "
                                "frozen 2026-09-28/29, 30 library books, 61 live parent books"),
                       "rows": luck},
        "what_counts_as_evidence": {
            "against": [
                (f"D_126 < {kill['kill_line'] * 100:+.2f}% vs the twin: FAILED_VARIANT (5% false-kill rate under "
                 "zero edge)"),
                ("D vs the market negative at 126 sessions with D vs the twin inside the band: the twin-relative "
                 "gap is not making money; stays DEPRIORITIZED, never a capital candidate"),
                "a 21- or 63-session reading is never a kill on its own",
            ],
            "for": [
                (f"D_126 > {-kill['kill_line'] * 100:+.2f}% vs the twin AND positive vs the market: evidence for; "
                 "moves P(edge) up; still CANNOT_DISTINGUISH as a claim, still PRODUCT_EXPERIMENT"),
                ("a positive D inside the band moves P(edge) only slightly: its likelihood ratio claim-vs-zero is "
                 "exp((D*mu - mu^2/2)/sd_D^2), printed on each reading"),
                ("a claim (RESEARCH_CLAIM / CAPITAL_CANDIDATE) needs forward months counted in years "
                 "(months_to_t2 above); nothing in 2026 or 2027 settles it"),
            ],
            "not_evidence": "the book being the best of the shadow books at any reading (see the luck table)",
        },
        "licence": "PRODUCT_EXPERIMENT (unchanged)", "llm_spend_usd": 0.0,
        "code": "scripts/crsp_blend_v0_kill_amendment.py; scripts/shadow_bayes_rule.kill_rule_from_measured_gap",
    }


def main() -> int:
    if OUT.exists():
        print(f"REFUSED: {OUT.name} exists; an amendment is written once. Write a new dated file instead.")
        return 2
    rec = build()
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(OUT)
    k = rec["kill_rule"]
    print(f"wrote {OUT.relative_to(REPO)}; kill line {k['kill_line']:+.4f} (false kill {k['P_kill_if_zero_edge']}); "
          f"old line real false kill {k['old_line_real_false_kill_rate']}; registration sha {rec['amends']['sha256'][:16]}")
    print(json.dumps(rec["power"], indent=1))
    print(json.dumps(rec["measured_gap_volatility"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
