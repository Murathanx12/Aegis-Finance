"""TRIAL-H5 -- the event-level learner at a five-session hold: registry row.

Pre-registered 2026-09-09 (`docs/TRIALS/TRIAL-H5-event-learner-five-session.md`).
The row is the tamper-evident commitment the `pre-register-trial` skill
requires beside the canonical doc; it enters the cumulative trial count (the
conservative direction for DSR/PBO). Descriptive only: this module reads no
market data, places nothing, and arms nothing.
"""

from __future__ import annotations

TRIAL_PARAM = "h5-event-learner-five-session"


def ensure_h5_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-H5."""
    from backend.services.portfolio_intelligence.trial_registry import (
        ensure_trial_registered,
    )

    notes = {
        "hypothesis": (
            "An event-level LightGBM learner over every PIT feature of the "
            "IBES announcement frame, predicting the 5-session market-excess "
            "return from the close of session +1 and traded long-short (top vs "
            "bottom decile of its PIT-ranked prediction), earns a beta-matched "
            "excess over its placebo-trained control that is positive, "
            "era-stable, and survives borrow cost and a drawdown budget. "
            "Honest prior: found AFTER the pre-specified primary H21 failed, "
            "among 156 configurations; -78% drawdown at 46% vol; no borrow "
            "modelled; the raw reaction's survivors were below the $10m floor."
        ),
        "purpose": "experimental",
        "canonical_doc": "docs/TRIALS/TRIAL-H5-event-learner-five-session.md",
        "pre_registered": "2026-09-09",
        "decision_rule": {
            "trial": "TRIAL-H5-event-learner-five-session",
            "primary_metric": "learner_minus_control beta-matched annualised "
                              "excess on monthly date blocks at the $10m/day "
                              "floor with 100 bps/yr borrow on the short leg, "
                              "purged walk-forward 2004-2024, H5|all seeds 0-12, "
                              "seed-median",
            "adopt_threshold": "seed-median >= +20%/yr AND NW t >= 2.5 AND same "
                               "sign in 2004-07/2008-15/2016-24 AND max DD >= -45% "
                               "AND RW2 excess win over the random null >= +0.15 "
                               "in every start era -> starts a 12-month "
                               "zero-capital forward leg; earliest capital "
                               "question 2027-09-09",
            "reject_threshold": "seed-median < +4%/yr OR t < 1.5 OR the control's "
                                "seed-median > +4%/yr OR the $10m floor removes "
                                "more than half of the $3m-floor excess",
            "power": {"declared_effect_size": "20 pp/yr",
                      "event_frequency_per_year": 13000,
                      "outcome_dispersion": "monthly sd 0.145 of the differenced "
                                            "long-short series",
                      "mde_80pct": "~31%/yr on 252 blocks -- the historical read "
                                   "screens, the forward leg decides"},
            "earliest_decision": "one named historical read (N1H5_prereg_read) "
                                 "after the registering commit; forward leg "
                                 "minimum 12 months",
            "params_frozen": "hold 5; entry close of s0+1; featset all; LightGBM "
                             "400 trees; purged walk-forward by year, embargo 5; "
                             "PIT rank window 63, pool >= 200; deciles; 25 bps a "
                             "side; borrow 100 bps/yr; floors $3m report / $10m "
                             "decide",
            "crash_event_override": "SPY drawdown >= 20% defers decisions until "
                                    ">= 6 months past the trough",
            "hard_constraint": "descriptive-only; NEVER arms a book; no buy-sell "
                               "framing; no seal; no holdout re-read beyond the "
                               "one already printed",
        },
    }
    return ensure_trial_registered(TRIAL_PARAM, notes, db_path=db_path)
