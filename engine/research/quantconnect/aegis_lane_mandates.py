# Aegis Finance — lane-mandate historical replay for QuantConnect (LEAN).
# =======================================================================
#
# DIRECTION-CHECK, NOT THE TRACK RECORD. This replays the *mandates* of the
# Aegis reference lanes (backend/data/paper_portfolios.yaml, config v2) on
# QuantConnect's survivorship-free data, 2015 -> today, so the result is a
# third-party-hosted number anyone can audit. It is never written into the
# forward paper_nav and never reported as "we beat the market".
#
# Honesty constraints baked in:
# - ETF SLEEVES ONLY. The live lanes' individual-stock universe was chosen
#   in 2026 with knowledge of which names won; replaying it to 2015 would be
#   hindsight bias. The mandate's testable content is the sleeve allocation
#   + rebalancing discipline, so that is exactly what runs here.
# - EQUAL WEIGHT inside each sleeve. The live lanes use HRP on the equity
#   sleeve; whether HRP beats EW is an OPEN pre-registered forward question
#   (TRIAL-001) — assuming the answer in a backtest would beg it.
# - No crash overlay. The overlay depends on the crash model, which is
#   currently model_not_deployed in prod; replaying a model that does not
#   run live would flatter the mandate.
# - Names enter when they list (XLRE 2015, XLC 2018): QC only trades listed
#   securities and the sleeve redistributes over what exists — the same
#   thing a real 2015 investor would have held.
#
# HOW TO RUN (QuantConnect free tier):
#   1. quantconnect.com -> sign up (free) -> Create New Algorithm (Python).
#   2. Replace main.py with this file. Set LANE below.
#   3. Backtest. Repeat for each lane. Click "Share" on each result for a
#      public URL; paste the URLs into docs/research/HONEST_REPLAY notes.

from AlgorithmImports import *

LANE = "balanced"  # <- edit per run: conservative | balanced | aggressive

MANDATES = {
    #                 equity  bonds  alts   rebalance
    "conservative": (0.40,   0.50,  0.10,  "monthly"),
    "balanced":     (0.70,   0.25,  0.05,  "monthly"),
    "aggressive":   (0.95,   0.05,  0.00,  "weekly"),
}

EQUITY_SLEEVE = ["SPY", "QQQ", "IWM", "VTI", "VEA", "VWO"]
BOND_SLEEVE = ["AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP"]
ALT_SLEEVE = ["GLD", "IAU", "USO", "VNQ"]


class AegisLaneMandateReplay(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2015, 1, 1)
        # no SetEndDate -> runs to the latest available day
        self.SetCash(100_000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage,
                               AccountType.Cash)

        eq, bd, alt, cadence = MANDATES[LANE]
        self.sleeves = [(EQUITY_SLEEVE, eq), (BOND_SLEEVE, bd),
                        (ALT_SLEEVE, alt)]

        for sleeve, _ in self.sleeves:
            for tkr in sleeve:
                self.AddEquity(tkr, Resolution.Daily)

        self.SetBenchmark("SPY")

        date_rule = (self.DateRules.WeekStart("SPY")
                     if cadence == "weekly"
                     else self.DateRules.MonthStart("SPY"))
        self.Schedule.On(date_rule,
                         self.TimeRules.AfterMarketOpen("SPY", 30),
                         self.Rebalance)

    def Rebalance(self):
        targets = []
        for sleeve, sleeve_weight in self.sleeves:
            # equal weight across the sleeve members that are actually
            # tradable *today* — a 2015 investor holds what exists in 2015
            live = [t for t in sleeve
                    if self.Securities[t].Price > 0
                    and self.Securities[t].IsTradable]
            if not live or sleeve_weight <= 0:
                continue
            w = sleeve_weight / len(live)
            targets.extend(PortfolioTarget(t, w) for t in live)
        if targets:
            self.SetHoldings(targets, liquidateExistingHoldings=True)
