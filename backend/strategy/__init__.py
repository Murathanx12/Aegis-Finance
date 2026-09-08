"""THE STRATEGY INTERFACE -- one contract, one call, one receipt.

    from backend.strategy import Strategy, Window, run_one
    receipt = run_one(strategy, window=Window("2004-01", "2015-12"))

Roadmap `docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` block S. The external
review's one-line conclusion (`EXTERNAL_2026-09-07_FIVE_REPOS.md` section 7):
every one of five external repos has a single named executable contract for
what a strategy is and one command that runs it end to end; Aegis had the most
research depth of any of them and no such object, which is why a new mechanism
costs a session instead of a file.

Importing this package registers the engines, so `run_one` can dispatch to any
of them without the caller importing the adapter first.
"""

from backend.strategy.contract import (DEFAULT_EXIT_PRIORITY, Benchmark,
                                       Construction, CostModel, HoldRule,
                                       Licence, LossBudget, Objective, Signal,
                                       Sizing, Strategy, StrategyError,
                                       Universe, Window,
                                       loss_budget_worst_case)
from backend.strategy.run import (EngineNotRegistered, RECEIPT_SCHEMA,
                                  SealedWindowRefused, engines, register_engine,
                                  run_one)
from backend.strategy import adapters as _adapters   # noqa: F401  registers engines
from backend.strategy.adapters import (arena_book_strategy, compare_to_sealed,
                                       growth_champion_strategy)
from backend.strategy.chain import information_chain
from backend.strategy.execution import (CapacityPath, ExecutionRefused,
                                        adv_capped_path, breakeven_row,
                                        execution_row, trades_from_turnover)
from backend.strategy.ladder import (ExitLadder, LadderRefused,
                                     meta_label_exits, stop_vs_volatility)
from backend.strategy.leak import (LeakAnalysisRefused, lookahead_analysis,
                                   recursive_analysis)
from backend.strategy.manifold import (DO_PREDICT_TRUSTWORTHY, ManifoldGate,
                                       ManifoldRefusal, expired_flags,
                                       fit_manifold)
from backend.strategy.numerai import (EraScoringRefused, era_boost_weights,
                                      mmc, neutralize, per_era_scores)
from backend.strategy.protections import (BookState, PROFILES, ProtectionError,
                                          ProtectionStack, default_protections,
                                          profile_bounds)

__all__ = [
    "BookState", "CapacityPath", "DO_PREDICT_TRUSTWORTHY", "EraScoringRefused",
    "ExecutionRefused", "ExitLadder", "LadderRefused", "LeakAnalysisRefused",
    "ManifoldGate", "ManifoldRefusal", "PROFILES", "ProtectionError",
    "ProtectionStack", "adv_capped_path", "breakeven_row", "default_protections",
    "era_boost_weights", "execution_row", "expired_flags", "fit_manifold",
    "lookahead_analysis", "meta_label_exits", "mmc", "neutralize",
    "per_era_scores", "profile_bounds", "recursive_analysis",
    "stop_vs_volatility", "trades_from_turnover",
    "Benchmark", "Construction", "CostModel", "DEFAULT_EXIT_PRIORITY",
    "EngineNotRegistered", "HoldRule", "Licence", "LossBudget", "Objective",
    "RECEIPT_SCHEMA", "SealedWindowRefused", "Signal", "Sizing", "Strategy",
    "StrategyError", "Universe", "Window",
    "arena_book_strategy", "compare_to_sealed", "engines", "growth_champion_strategy",
    "information_chain", "loss_budget_worst_case", "register_engine", "run_one",
]
