"""RESEARCH-GYM-1 — where Aegis is allowed to overfit on purpose.

Registered ONCE as a campaign (R2). Its internal variants are ledgered, never
individually pre-registered, and never citable.

    from backend.services.research_gym import (DecisionEpisode, replay,
                                               attribute_in_place)

    ep = DecisionEpisode(decision_ts="2020-04-01", security="SPY",
                         action="SELL", exposure_before=1.0, exposure_after=0.0,
                         stated_reason="extreme stress + bearish regime",
                         beliefs=Beliefs(p_up=0.35, horizon_days=63))
    surface = replay(ep, forward_daily_returns)   # the WHOLE menu
    attribute_in_place(ep, surface)               # forecast? or action-mapping?

THE SHAPE OF THE ANSWER
=======================
`regret.regret_triple()` says how much the decision cost, in THREE declared
denominators — against the ex-post best (an upper bound with a large positive
null), against a fixed default, and as an excess over the state-and-action
matched null. `surface.regret_pct()` gives only the first and is kept for
continuity; reading it alone is the G1 defect. `ep.failure_mode` says WHERE it
went wrong — and the
distinction between `forecast_failure` and `action_mapping_failure` is the one
worth the whole exercise: the first means the world surprised us, the second
means we saw it correctly and did the wrong thing about it.

The timing backtest is dataset zero. Its sell signals had a 28.6% hit rate
against buys at 67.4% — and the stated cause was that sells fired at VIX > 25,
historically the best time to buy. If that is right, those episodes are
action-mapping failures rather than forecast failures, and the fix belongs in
the policy layer, not the model. `scripts/gym_dissect_timing.py` asks the
machinery instead of assuming the answer.
"""

from backend.services.research_gym.charter import (CAMPAIGN, ExportRefused,
                                                   GymOutputIsNotEvidence,
                                                   GymResult, LineageRow,
                                                   TransferTest,
                                                   read_lineage,
                                                   record_lineage,
                                                   request_export,
                                                   unledgered_search_warning)
from backend.services.research_gym.counterfactual import (MATERIAL_COST_GAP_PCT,
                                                          MATERIAL_EDGE_PCT,
                                                          Attribution,
                                                          ResponseSurface,
                                                          attribute,
                                                          attribute_in_place,
                                                          replay,
                                                          taken_policy_name)
from backend.services.research_gym.base_rate import (ESTABLISHED, SUGGESTIVE,
                                                     TOO_THIN, Assessment,
                                                     BaseRate, assess,
                                                     build_base_rates,
                                                     conditional_base_rate,
                                                     disagrees_with_base_rate,
                                                     vix_bucket)
from backend.services.research_gym.autopsy import (Autopsy, AutopsyRefused,
                                                   PrecursorRefused,
                                                   SliceResult, adjudicate,
                                                   compile_precursor,
                                                   evaluate_slice,
                                                   run_transfer)
from backend.services.research_gym.tensor import (RegretTensor, TensorCell,
                                                  build_regret_tensor)
from backend.services.research_gym.power import (Power, count_episodes,
                                                 effective_n, mde_mean,
                                                 mde_proportion, power_for)
from backend.services.research_gym.regret import (DEFAULT_FAILURE_PERCENTILE,
                                                  MatchedNull, NullCell,
                                                  NullMismatch, RegretTriple,
                                                  build_matched_null,
                                                  failure_threshold_pct,
                                                  regret_triple)
from backend.services.research_gym.episode import (ACTION_MAPPING_FAILURE,
                                                   CERTIFICATION,
                                                   CONCENTRATION_FAILURE,
                                                   COST_FAILURE,
                                                   FAILURE_DESCRIPTIONS,
                                                   FAILURE_MODES,
                                                   FORECAST_FAILURE, GYM,
                                                   NO_FAILURE,
                                                   REGIME_TRANSITION_FAILURE,
                                                   SIZING_FAILURE,
                                                   STATE_TO_FORECAST_FAILURE,
                                                   TIMING_FAILURE,
                                                   UNCLASSIFIED, Beliefs,
                                                   DecisionEpisode, Outcome)
from backend.services.research_gym.policies import (DEFAULT_COST_BPS_ONE_WAY,
                                                    POLICY_MENU, PolicyResult,
                                                    run_policy)

__all__ = [
    "CAMPAIGN", "GYM", "CERTIFICATION",
    "DecisionEpisode", "Beliefs", "Outcome",
    "POLICY_MENU", "PolicyResult", "run_policy", "DEFAULT_COST_BPS_ONE_WAY",
    "ResponseSurface", "replay", "attribute", "attribute_in_place",
    "taken_policy_name", "MATERIAL_EDGE_PCT", "MATERIAL_COST_GAP_PCT",
    "Attribution",
    # G1 — three denominators, and the calibrated gate that replaced 1.0pp.
    "RegretTriple", "regret_triple", "MatchedNull", "NullCell", "NullMismatch",
    "build_matched_null", "failure_threshold_pct", "DEFAULT_FAILURE_PERCENTILE",
    # G2 — n_effective and MDE on every row.
    "Power", "power_for", "effective_n", "count_episodes", "mde_mean",
    "mde_proportion",
    "Assessment", "assess", "ESTABLISHED", "SUGGESTIVE", "TOO_THIN",
    # AUTOPSY-TO-RULE-1 — a mechanism that only explains its parent dies.
    "Autopsy", "AutopsyRefused", "PrecursorRefused", "compile_precursor",
    "SliceResult", "evaluate_slice", "run_transfer", "adjudicate",
    # REGRET_TENSOR — state x action x horizon, with a per-cell MDE.
    "RegretTensor", "TensorCell", "build_regret_tensor",
    "FAILURE_MODES", "FAILURE_DESCRIPTIONS", "FORECAST_FAILURE",
    "ACTION_MAPPING_FAILURE", "TIMING_FAILURE", "SIZING_FAILURE",
    "STATE_TO_FORECAST_FAILURE",
    "REGIME_TRANSITION_FAILURE", "CONCENTRATION_FAILURE", "COST_FAILURE",
    "BaseRate", "build_base_rates", "conditional_base_rate",
    "disagrees_with_base_rate", "vix_bucket",
    "NO_FAILURE", "UNCLASSIFIED",
    "GymResult", "GymOutputIsNotEvidence", "ExportRefused",
    "LineageRow", "record_lineage", "read_lineage",
    "unledgered_search_warning", "TransferTest", "request_export",
]
