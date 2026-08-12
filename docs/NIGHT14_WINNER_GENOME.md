# WINNER-GENOME-1 — how the Bloomberg leaderboard was actually produced

**Pre-registered** `Aegis module/TRIALS/PREREG_WINNER_GENOME_1.md` @ `4aa03aa`,
committed **before** the simulator produced a number. Receipts
`Aegis module/data/factory/winner_genome_1_results.json` (untracked — `/data/`
is gitignored), runner `scripts/run_winner_genome_1.py`.

**RESULTS PENDING — this file is filled in after the run.**

---

## 0. The question, and the thing we do not have

Murat entered the Bloomberg Global Trading Challenge, watched teams post
enormous 5-week returns, and said: *"it doesnt seem real even looks luck but i
dont think so."*

The honest version of that question is not "why did the winner win." It is:

> **Which observable portfolio-construction behaviours occur disproportionately
> among winning portfolios, survive controls for volatility and
> winner-selection, and continue to work in periods not used to discover them?**

**Stated first, because everything downstream depends on it: we do not have the
winning teams' holdings.** The Bloomberg tables in the screenshots are
**aggregate across all ~2,600 competitors**. NVIDIA's aggregate P&L is the sum
over every team that held it; it is not evidence that the winning team held
NVIDIA. No portfolio can be reconstructed from those tables, and this trial does
not pretend otherwise.

What *is* reconstructible is the **strategy family** each winning captain
described publicly. Those descriptions — and only those — are the input.

