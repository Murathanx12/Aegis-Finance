"""The research daemon's FIRST REAL QUEUE (Order 20 §2.1 / §2.5).

    python -m scripts.research_daemon_first_queue            # print queue
    python -m scripts.research_daemon_first_queue --receipt  # + write receipt

WHAT THIS IS
============
Every number on every job below is a DECLARED PRIOR, written before any data
is read, sourced from the order documents and adjudication that specified the
hypothesis — never from a peek at the outcome. The daemon freezes priority at
submission (HYPOTHESIS-BANDIT-1), so this script is the persistence: re-running
it re-derives the identical queue from the identical declarations, which makes
"the priority was fixed beforehand" checkable by diffing two runs.

The daemon derives its reserved windows from the confirmation-budget ledger
(`derive_reserved_windows`, 2026-08-18) — nothing here may touch the M4 or IV
confirmation calendars, and the guard now actually knows where they are.

WHAT THIS IS NOT
================
Not an executor. Jobs run when a session (or a future runner) picks them off
`queue()` in priority order, does the work, and calls `record_result` with a
p-value — at which point they count toward m. Ops chores (universe hygiene,
telemetry backlog) are DELIBERATELY absent: they produce no p-value, so
queueing them would leave permanent NEED_MORE_DATA residue in a ledger whose
whole job is honest m-counting. Ops work is tracked in the orders, not here.

Declared-prior discipline: `se_per_block` and `expected_effect` are honest
guesses recorded so the power screen can rank jobs — a job whose declared
effect proves optimistic dies at its own MDE later, which is the system
working. What a declaration may NOT do is move after submission.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import research_daemon as RD          # noqa: E402

J = RD.HypothesisJob


#: The queue, in declaration order (the DAEMON ranks; this order is not a
#: statement of priority). Sources for each declaration are cited inline.
FIRST_QUEUE: tuple[RD.HypothesisJob, ...] = (
    # ── P0-adjacent: the cost model's next honest step (Order 20 §2.1) ─────
    J(hypothesis_id="HJ-EFFECTIVE-SPREAD-1",
      question=("Effective spreads on the TAQ calibration overlap are "
                "materially inside quoted (documented 0.5-0.9x quoted; "
                "adjudication B7 adds a regime-drift cadence to the join)"),
      universe="taq_calibration_2026_184", outcome="effective_to_quoted_ratio",
      start="2026-07-15", end="2026-08-14",
      n_date_blocks=23, se_per_block=0.04, expected_effect=0.25,
      effect_units="ratio_departure_from_1",
      cost_usd=2.0, cost_minutes=300.0, p_resolves=0.90, decision_value=0.70,
      pit_cutoff="2026-08-14", horizon_days=0),

    # ── P1: the management question (Order 20 §2.2 builds its episodes) ────
    J(hypothesis_id="CONVEXITY-PRESERVATION-1",
      question=("Trim/stop rules destroy right-tail terminal wealth vs hold "
                "on +20/+40/+75/+100 crossers, and continuation covariates "
                "(revisions, profitability, financing, expectations) separate "
                "the episodes where they do"),
      universe="us_top1500_winner_crossings", outcome="episode_wealth_delta_h60",
      start="2002-01-01", end="2024-12-31",
      n_date_blocks=23, se_per_block=0.020, expected_effect=0.030,
      effect_units="terminal_wealth_fraction",
      cost_usd=0.0, cost_minutes=600.0, p_resolves=0.85, decision_value=0.80,
      parent_corpse_ids=("CANON-S15-TRAILING-STOP",),
      distinct_claim=("The stop is an ARM evaluated on episodes anchored at "
                      "threshold crossings with matched losers, not a filter "
                      "conditioned on the path being evaluated - S15's trap "
                      "is the control design, not the candidate."),
      pit_cutoff="episode threshold-crossing date", horizon_days=60),

    J(hypothesis_id="EVENT-RESOLUTION-CURVE-1",
      question=("For earnings/FDA/M&A/guidance, the tradable fraction of the "
                "announcement move (arrival-axis, S62) is measurable and "
                "materially above zero after the 87-95% overnight share"),
      universe="us_top1500_events", outcome="tradable_fraction_by_arrival",
      start="2015-01-01", end="2024-12-31",
      n_date_blocks=40, se_per_block=0.030, expected_effect=0.100,
      effect_units="fraction_of_event_move",
      cost_usd=0.0, cost_minutes=480.0, p_resolves=0.80, decision_value=0.70,
      parent_corpse_ids=("G4-EARNINGS-OVERNIGHT",),
      distinct_claim=("G4 measured the earnings effect arriving while the "
                      "market is shut; this asks what fraction REMAINS "
                      "reachable per arrival bucket, an execution-boundary "
                      "question G4 did not price."),
      pit_cutoff="event announcement timestamp", horizon_days=20),

    # ── P1 imports from review round 2 (adjudication A10-A12, §61 cap) ─────
    J(hypothesis_id="PURE-NEWS-RESIDUAL-1",
      question=("The UNEXPECTED component of news (observed minus a strictly "
                "PIT expected-news model) predicts residual return/drift "
                "where raw sentiment does not (hypothesis_source: NBER "
                "w35093; capped at adaptive-historical-validation)"),
      universe="us_top1500_newsflow", outcome="residual_return_h5_h20",
      start="2019-01-01", end="2024-12-31",
      n_date_blocks=60, se_per_block=0.0040, expected_effect=0.0060,
      effect_units="monthly_residual_return",
      cost_usd=40.0, cost_minutes=1200.0, p_resolves=0.40, decision_value=0.60,
      parent_corpse_ids=("G5-CONDITIONAL-SHAPE",),
      distinct_claim=("Residualizing news against a PIT expectation model is "
                      "an information-set claim about the unexpected "
                      "component, not another learned conditional shape on "
                      "signals G5 already priced."),
      pit_cutoff="expected-news model trains strictly pre-article", horizon_days=20),

    J(hypothesis_id="IMPLIED-REVISION-1",
      question=("Analyst reiteration language shifts BEFORE formal "
                "recommendation/target changes and the market reacts "
                "(hypothesis_source: SSRN 5166926). DATA GATE: PIT report "
                "text entitlement unverified - expected SHELF"),
      universe="us_analyst_covered", outcome="pre_revision_drift_h20",
      start="2018-01-01", end="2024-12-31",
      n_date_blocks=48, se_per_block=0.0050, expected_effect=0.0060,
      effect_units="monthly_residual_return",
      cost_usd=100.0, cost_minutes=1500.0, p_resolves=0.15, decision_value=0.55,
      parent_corpse_ids=("ANALYST-TARGET-LEVELS",),
      distinct_claim=("Asks whether reiteration LANGUAGE moves before formal "
                      "revisions - an arrival-timing claim about text, not "
                      "the level or implied upside of the dead target-price "
                      "signal."),
      pit_cutoff="report publication timestamp", horizon_days=20),

    J(hypothesis_id="INFORMATION-PROCESSING-GAP-1",
      question=("Identical fundamental surprise resolves differently by the "
                "attention/processing load at event time (macro density, "
                "sector event density, news volume, disagreement)"),
      universe="us_top1500_events", outcome="drift_by_processing_load_h20",
      start="2016-01-01", end="2024-12-31",
      n_date_blocks=40, se_per_block=0.0050, expected_effect=0.0080,
      effect_units="conditional_drift_difference",
      cost_usd=0.0, cost_minutes=600.0, p_resolves=0.70, decision_value=0.50,
      parent_corpse_ids=("G5-CONDITIONAL-SHAPE",),
      distinct_claim=("The conditioning variable is the information "
                      "ENVIRONMENT at arrival (a state G5's signals never "
                      "contained), not a reshaping of an existing predictor."),
      pit_cutoff="event announcement timestamp", horizon_days=20),

    J(hypothesis_id="OPTIONS-EQUITY-DISLOCATION-1",
      question=("Event-conditioned disagreement between option-implied "
                "expectations and equity reaction predicts resolution "
                "direction; strictly synchronized timestamps only"),
      universe="us_optionable_events", outcome="post_event_resolution_h10",
      start="2016-01-01", end="2024-12-31",
      n_date_blocks=36, se_per_block=0.0060, expected_effect=0.0080,
      effect_units="conditional_drift_difference",
      cost_usd=0.0, cost_minutes=720.0, p_resolves=0.60, decision_value=0.50,
      parent_corpse_ids=("OPTIONS-GENERIC-ALPHA",),
      distinct_claim=("The claim is event-specific expectation disagreement "
                      "with strict synchronization, not the post-2008-decayed "
                      "generic option-implied stock-return predictor family."),
      pit_cutoff="option close same-day as equity close", horizon_days=10),

    J(hypothesis_id="REACTION-GAP-1",
      question=("After a large shock to A, economically-exposed B reprices "
                "with measurable delay relative to expected sensitivity "
                "(propagation direction of MARKET-GRAPH-1's surviving "
                "relation information)"),
      universe="us_top1500_semantic_graph", outcome="exposed_name_catchup_h5",
      start="2019-01-01", end="2024-12-31",
      n_date_blocks=60, se_per_block=0.0040, expected_effect=0.0050,
      effect_units="event_window_residual_return",
      cost_usd=0.0, cost_minutes=600.0, p_resolves=0.60, decision_value=0.55,
      parent_corpse_ids=("MG1-MINVAR",),
      distinct_claim=("Uses the relation information in the propagation "
                      "direction; the minimum-variance covariance route MG1 "
                      "closed stays closed and is not reopened here."),
      pit_cutoff="shock arrival timestamp", horizon_days=5),

    J(hypothesis_id="INFORMATION-HALF-LIFE-1",
      question=("Edge from delayed disclosures (PTR, 13D/G, Form 4, "
                "revisions) decays measurably with information age after "
                "realistic ingestion latency; the decay curve prices which "
                "data systems are worth building"),
      universe="us_disclosure_events", outcome="edge_by_information_age",
      start="2016-01-01", end="2024-12-31",
      n_date_blocks=36, se_per_block=0.0050, expected_effect=0.0070,
      effect_units="conditional_drift_difference",
      cost_usd=0.0, cost_minutes=480.0, p_resolves=0.70, decision_value=0.60,
      pit_cutoff="public availability timestamp, not filing date",
      horizon_days=20),

    # ── P2 shelf: declared now so the bandit can rank them honestly ────────
    J(hypothesis_id="NEWS-X-FLOW-1",
      question=("Post-surprise drift intensity conditions on WHO absorbs the "
                "news (retail-contrarian proxy; hypothesis_source NBER "
                "w34086). DATA GATE: no credible PIT retail proxy verified"),
      universe="us_top1500_events", outcome="drift_by_flow_proxy_h20",
      start="2018-01-01", end="2024-12-31",
      n_date_blocks=40, se_per_block=0.0050, expected_effect=0.0060,
      effect_units="conditional_drift_difference",
      cost_usd=50.0, cost_minutes=900.0, p_resolves=0.30, decision_value=0.45,
      pit_cutoff="proxy availability timestamp", horizon_days=20),

    J(hypothesis_id="SEQUENCE-OF-EVIDENCE-1",
      question=("The ARRIVAL ORDER of evidence (insider -> revision -> skew "
                "-> event vs permuted orders) carries information beyond the "
                "terminal feature vector; simple sequence baselines before "
                "any attention model"),
      universe="us_top1500_events", outcome="order_vs_terminal_state_h20",
      start="2018-01-01", end="2024-12-31",
      n_date_blocks=40, se_per_block=0.0050, expected_effect=0.0055,
      effect_units="conditional_drift_difference",
      cost_usd=0.0, cost_minutes=900.0, p_resolves=0.50, decision_value=0.45,
      parent_corpse_ids=("G5-CONDITIONAL-SHAPE",),
      distinct_claim=("The claim is information arrival SEQUENCE using data "
                      "classes G5 never contained, not another nonlinear "
                      "conditional shape on the same signals."),
      pit_cutoff="each evidence item's own arrival timestamp",
      horizon_days=20),

    J(hypothesis_id="CROSS-ENTITY-LAG-1",
      question=("Supplier/customer/competitor shocks propagate with "
                "measurable lag on a FROZEN PIT graph; 1-hop and 2-hop vs "
                "industry controls, before any GNN is earned"),
      universe="us_top1500_semantic_graph", outcome="hop_lag_repricing_h5",
      start="2019-01-01", end="2024-12-31",
      n_date_blocks=60, se_per_block=0.0040, expected_effect=0.0045,
      effect_units="event_window_residual_return",
      cost_usd=0.0, cost_minutes=720.0, p_resolves=0.55, decision_value=0.45,
      parent_corpse_ids=("MG1-MINVAR",),
      distinct_claim=("Simple lagged propagation on a frozen graph, tested "
                      "against industry controls - not covariance estimation "
                      "and not a graph neural network."),
      pit_cutoff="graph frozen before evaluation window", horizon_days=5),

    J(hypothesis_id="MODEL-DISAGREEMENT-1",
      question=("Disagreement TOPOLOGY across model families (numeric vs "
                "options vs event/LLM) predicts subsequent magnitude/"
                "drawdown, before any averaging"),
      universe="us_top1500", outcome="magnitude_by_disagreement_h20",
      start="2019-01-01", end="2024-12-31",
      n_date_blocks=60, se_per_block=0.0045, expected_effect=0.0050,
      effect_units="conditional_magnitude_difference",
      cost_usd=0.0, cost_minutes=600.0, p_resolves=0.55, decision_value=0.40,
      parent_corpse_ids=("G5-CONDITIONAL-SHAPE",),
      distinct_claim=("The regressor is cross-model disagreement structure, "
                      "a quantity that does not exist inside any single "
                      "model G5 tested; the target is magnitude, not sign."),
      pit_cutoff="all member models strictly PIT", horizon_days=20),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="research_daemon_first_queue")
    ap.add_argument("--receipt", action="store_true",
                    help="write the nightly receipt to the daemon dir")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    d = RD.ResearchDaemon()          # reserved windows DERIVED from ledger
    print("=" * 78)
    print("AEGIS-RESEARCH-DAEMON-1 — first real queue")
    print("=" * 78)
    print(f"reserved windows in force ({len(d.reserved)}):")
    for w in d.reserved:
        print(f"  {w.name}")
    print()

    for job in FIRST_QUEUE:
        sub = d.submit(job)
        tag = "POWERED" if sub.powered else "SHELF  "
        print(f"  [{tag}] {job.hypothesis_id:<32} mde={sub.mde:.5f} "
              f"declared={job.expected_effect:g} "
              f"priority={sub.priority:.4f}")

    print()
    print("queue, as the bandit ranks it (priority frozen at submission):")
    for i, sub in enumerate(d.queue(), 1):
        print(f"  {i:2}. {sub.job.hypothesis_id:<32} {sub.priority:.4f}"
              f"{'' if sub.powered else '   (shelved: under its own MDE)'}")

    rec = d.nightly_receipt()
    print()
    print(f"submitted={rec['submitted']}  m={rec['multiplicity_m']}  "
          f"shelved={rec['shelved_underpowered']}  "
          f"queue_depth={rec['queue_depth']}")

    if a.receipt:
        p = d.write_receipt()
        print(f"\nreceipt written: {p}")
    else:
        print("\n--receipt not given: nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
