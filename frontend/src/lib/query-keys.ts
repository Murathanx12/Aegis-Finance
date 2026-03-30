/**
 * Centralized React Query key factory.
 * Keeps cache keys consistent across the app.
 */
export const queryKeys = {
  market: {
    status: ["market", "status"] as const,
    macro: ["market", "macro"] as const,
    netLiquidity: ["market", "net-liquidity"] as const,
    dataQuality: ["market", "data-quality"] as const,
    signal: ["market", "signal"] as const,
  },
  signal: {
    stock: (ticker: string) => ["signal", "stock", ticker] as const,
  },
  crash: {
    prediction: (horizon: string, explain: boolean) =>
      ["crash", "prediction", horizon, explain] as const,
    ticker: (ticker: string) => ["crash", "ticker", ticker] as const,
  },
  simulation: {
    sp500: (nSims: number, years: number) =>
      ["simulation", "sp500", nSims, years] as const,
    scenarios: ["simulation", "scenarios"] as const,
  },
  stock: {
    screener: ["stock", "screener"] as const,
    analysis: (ticker: string) => ["stock", "analysis", ticker] as const,
    shap: (ticker: string) => ["stock", "shap", ticker] as const,
    signal: (ticker: string) => ["stock", "signal", ticker] as const,
  },
  sectors: ["sectors"] as const,
  portfolio: {
    analyze: ["portfolio", "analyze"] as const,
    build: ["portfolio", "build"] as const,
    project: ["portfolio", "project"] as const,
  },
  savings: {
    project: ["savings", "project"] as const,
  },
  news: {
    market: ["news", "market"] as const,
    ticker: (ticker: string) => ["news", "ticker", ticker] as const,
  },
} as const;

/** Stale times by endpoint category (ms) */
export const staleTimes = {
  market: 5 * 60 * 1000,      // 5 min
  stock: 15 * 60 * 1000,      // 15 min
  sectors: 60 * 60 * 1000,    // 1 hr
  crash: 30 * 60 * 1000,      // 30 min
  simulation: 60 * 60 * 1000, // 1 hr
  news: 15 * 60 * 1000,       // 15 min
} as const;
