"""Write the night's PROPOSED (never activated) PRODUCT_EXPERIMENT contracts with a policy hash."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from scripts.night.family_board import OUT

COMMON = {"licence": "PRODUCT_EXPERIMENT",
          "activation": "NONE -- proposed, not seeded; seeding is attended (seed-a-lane skill, owner flips the flag)",
          "proposed_by": "S65 night-backtests builder", "claim": "none (CLAIMS PROMOTED: none)"}

CONTRACTS = [
    {**COMMON, "name": "rev_net_raises_refresh_k20_liquid500_v1",
     "selector": "rank by net analyst price-target raises over the trailing 90 days (raises minus cuts, per broker; "
                 "an event is usable from max(anndats, actdats) + 1 trading day); names with zero events are not eligible",
     "universe": "top 500 US common stocks by median 63-session dollar volume, price >= the xs_ranker floor, "
                 ">= 1 target event in the last 365 days",
     "construction": "top 20, equal weight, gross 1.0, long only, no leverage, no stops",
     "rebalance": "monthly, first session after month-end; the member list is REFRESHED every month "
                  "(the frozen revision_flow_v0 list keeps running as its own book)",
     "fill_convention": "decide on month-end close data; trade at the next session's open",
     "costs": "10 bps one-way on traded weight (20 bps sensitivity printed beside)",
     "control": "turnover-matched random twin (same k, same eligible set, same number of replacements, same costs); SPY beside",
     "objective": "terminal wealth, balanced personality; scored as net minus twin, by year, leave-one-year-out",
     "inputs": ["live analyst target events (yfinance upgrades/downgrades panel; IBES when available)",
                "daily bars prices_2025_26"],
     "worst_case_dollars": "20 names x 5% notional, no stops: a -30% gap on one name = -1.5% of equity; gross 100%",
     "evidence": "family_board_20261110T163318Z.json liquid500/rev_net_raises k=20: +0.57%/mo vs twin, t 2.94, "
                 "MDE 0.54, 18/26 years, LOO worst +0.50, breadth worst +0.27 (k=100); "
                 "decay_factors_20261110T164325Z.json: edge halves after one month, gone by month 3; "
                 "FF5+UMD alpha +0.50 t 1.60 MDE 0.87 = cannot distinguish from momentum + size",
     "why": "the most robust family on survivor-free CRSP 2000-2024 and the one the five leader books already trade; "
            "the decay test says a frozen list keeps about half the edge after a month, so the testable change is "
            "the monthly refresh"},
    {**COMMON, "name": "pruned_selector_population_v1 (virtual population, no broker)",
     "selector": "30 single-signal roots (scripts/night/branching_sim.py SELECTORS), top 20 each, eligible universe",
     "construction": "each branch equal weight; population book = equal weight over surviving branches",
     "rebalance": "monthly; epoch every 12 months",
     "branching_rule": "kill the bottom 25% (age >= 24 months) by mean net-minus-twin since birth; the top 6 each "
                       "spawn one mutant (k in {10,20,50} or the other universe); the 3 lowest-error-correlation top "
                       "pairs spawn a rank-average join; children score only after birth; cap 80",
     "fill_convention": "month-end decision, next-session entry",
     "costs": "10 bps one-way",
     "control": "every branch has a turnover-matched random twin; population score = population net minus the same "
                "weights on the twins; and all 30 roots never pruned",
     "objective": "terminal wealth; score = excess over twins, never over SPY",
     "evidence": "branching_sim_20261110T1640*/T1641* (7 variants): pruning gain over never-pruned roots "
                 "+0.32..+0.56 %/mo net of twins, t 2.3-3.7, MDE 0.33-0.43, 18-23/31 years, LOO worst > 0 in 7/7; "
                 "the Thompson allocator adds nothing reliable",
     "why": "the CH-16 design tested on history: branches differ in alpha source, each has a twin, kills are "
            "forward-only. Pruning works on this history; the allocator is optional"},
]

NOT_PROMOTED = {
    "mom_12_1_liquid500": "+0.91%/mo vs twin t 2.04, MDE 1.20, FF5+UMD alpha below its MDE; it is the arena's existing "
                          "single signal, not a new alpha source",
    "pead_ear": "+0.45..+0.49 at L0 but -0.53 (t -1.8) at L2: a one-month signal that reverses",
    "low_vol, value_bm, reversal_1m, quality_gp_at": "cannot distinguish or negative vs twin at every k",
    "dip_add on SPY/QQQ/market": "best of 12 cells at the 92nd percentile of random dates: cannot distinguish",
    "dip_add on single stocks": "small positive timing (31/36 block cells): an EXECUTION rule for planned adds, not a book",
}


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for c in CONTRACTS:
        c["policy_hash_sha256"] = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
        c["proposed_at"] = now
    p = OUT / "proposed_contracts_20261111.json"
    p.write_text(json.dumps({"schema": "proposed_product_experiment_contracts/1", "contracts": CONTRACTS,
                             "not_promoted": NOT_PROMOTED}, indent=1), encoding="utf-8")
    for c in CONTRACTS:
        print(c["name"], c["policy_hash_sha256"])
    print("written", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
