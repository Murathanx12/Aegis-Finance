const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Backend serves stale-while-revalidate, so a healthy response is fast; a
// request stuck this long means a cold recompute and should fail visibly
// (React Query retries once) instead of hanging the page for minutes.
// Known-heavy endpoints (first-ever ticker analysis, large portfolio analyze)
// pass a larger budget instead of failing at 45s.
const FETCH_TIMEOUT_MS = 45_000;
export const HEAVY_TIMEOUT_MS = 120_000;

async function fetchAPI<T>(
  path: string,
  options?: RequestInit,
  timeoutMs: number = FETCH_TIMEOUT_MS,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    signal: options?.signal ?? AbortSignal.timeout(timeoutMs),
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    // Surface the backend's `detail` (e.g. "Did you mean MRVL?") — the bare
    // status line made every failure look identical to the user.
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = ` — ${body.detail}`;
    } catch {
      // non-JSON error body; keep the status line
    }
    throw new Error(`API error: ${res.status} ${res.statusText}${detail}`);
  }

  return res.json();
}

// Market
export function getMarketStatus() {
  return fetchAPI<MarketStatus>("/api/market-status");
}

export function getMacroIndicators() {
  return fetchAPI<MacroResponse>("/api/macro");
}

export function getNetLiquidity() {
  return fetchAPI<NetLiquidityResponse>("/api/net-liquidity");
}

export function getDataQuality() {
  return fetchAPI<DataQuality>("/api/data-quality");
}

// Unified Dashboard (Bloomberg-style: everything in one call)
export function getMarketDashboard() {
  return fetchAPI<MarketDashboard>("/api/dashboard");
}

// Crash
export function getCrashPrediction(horizon = "3m", explain = false) {
  return fetchAPI<CrashPrediction>(`/api/crash/prediction?horizon=${horizon}&explain=${explain}`);
}

export function getTickerCrash(ticker: string) {
  return fetchAPI<TickerCrash>(`/api/crash/${ticker}`);
}

// Simulation
export function getSP500Projection(nSims = 10000, years = 5) {
  return fetchAPI<SP500Projection>(`/api/simulation/sp500?n_sims=${nSims}&years=${years}`);
}

export function getScenarios() {
  return fetchAPI<ScenariosResponse>("/api/simulation/scenarios");
}

// Stock
export function getStockScreener() {
  return fetchAPI<ScreenerResponse>("/api/stock/screener");
}

export function getStockAnalysis(ticker: string) {
  return fetchAPI<StockAnalysis>(`/api/stock/${ticker}`, undefined, HEAVY_TIMEOUT_MS);
}

export function getStockShap(ticker: string) {
  return fetchAPI<ShapExplanation>(`/api/stock/${ticker}/shap`);
}

// Sectors
export function getSectors() {
  return fetchAPI<SectorsResponse>("/api/sectors");
}

// Portfolio
export function analyzePortfolio(holdings: Holding[]) {
  return fetchAPI<PortfolioAnalysis>("/api/portfolio/analyze", {
    method: "POST",
    body: JSON.stringify({ holdings }),
  }, HEAVY_TIMEOUT_MS);
}

export function buildPortfolio(risk: string, amount: number, horizon: string) {
  return fetchAPI<PortfolioBuilt>("/api/portfolio/build", {
    method: "POST",
    body: JSON.stringify({
      risk_tolerance: risk,
      investment_amount: amount,
      time_horizon: horizon,
    }),
  });
}

// Ticker resolution ("marvell" → MRVL)
export interface TickerResolveResponse {
  query: string;
  resolved: boolean;
  match: { ticker: string; name: string; source: string } | null;
}
export function resolveTicker(q: string) {
  return fetchAPI<TickerResolveResponse>(`/api/stock/resolve?q=${encodeURIComponent(q)}`);
}

// Daily brief — "what happened today and how it affects your stocks"
export interface DailyBriefResponse {
  date: string;
  horizon: string;
  market: { label: string; ticker: string; change_1d_pct: number | null; change_5d_pct: number | null }[];
  geopolitical: {
    conflict_score: number | null;
    event_score: number | null;
    event_label: string | null;
    note: string | null;
  };
  regime: { regime: string | null; risk_score: number | null };
  your_tickers: {
    ticker: string;
    change_1d_pct: number | null;
    change_5d_pct: number | null;
    headlines: { title: string; publisher?: string; link?: string }[];
  }[];
  summary: {
    what_happened: string;
    impact_on_holdings: string;
    risks_to_watch: string;
    source: "llm" | "template";
    sentiment?: string;
  } | null;
  disclaimer: string;
}
export function getDailyBrief(tickers: string[]) {
  const param = tickers.length ? `?tickers=${encodeURIComponent(tickers.join(","))}` : "";
  return fetchAPI<DailyBriefResponse>(`/api/news/brief${param}`, undefined, HEAVY_TIMEOUT_MS);
}

// Analyst intelligence — Wall Street consensus (Bloomberg-ANR-shaped view)
export interface AnalystIntelligence {
  ticker: string;
  price_targets: {
    current_price: number | null;
    low: number | null;
    mean: number | null;
    median: number | null;
    high: number | null;
    upside_pct: number | null;
  } | null;
  recommendation_trend: {
    period: string;
    strongBuy: number;
    buy: number;
    hold: number;
    sell: number;
    strongSell: number;
    total: number;
  }[] | null;
  consensus_rating: {
    score: number | null;
    label: string | null;
    n_analysts: number | null;
    scale: string;
  } | null;
  recent_actions: {
    date: string;
    firm: string;
    from_grade: string | null;
    to_grade: string | null;
    action: string | null;
  }[] | null;
  attribution: string;
}
export function getStockAnalysts(ticker: string) {
  return fetchAPI<AnalystIntelligence>(`/api/stock/${ticker}/analysts`, undefined, HEAVY_TIMEOUT_MS);
}

// News
export function getMarketNews() {
  return fetchAPI<MarketNewsResponse>("/api/news/market");
}

export function getStockNews(ticker: string) {
  return fetchAPI<StockNewsResponse>(`/api/news/${ticker}`);
}

// Signals
export function getMarketSignal() {
  return fetchAPI<MarketSignal>("/api/signal");
}

export function getStockSignal(ticker: string) {
  return fetchAPI<StockSignal>(`/api/stock/${ticker}/signal`, undefined, HEAVY_TIMEOUT_MS);
}

// Options & Earnings Intelligence
export function getOptionsAnalysis(ticker: string) {
  return fetchAPI<OptionsAnalysis>(`/api/options/${ticker}`);
}

export function getVixTermStructure() {
  return fetchAPI<VixTermStructure>("/api/options/vix-term");
}

export function getEarningsAnalysis(ticker: string) {
  return fetchAPI<EarningsAnalysis>(`/api/earnings/${ticker}`);
}

// Tail Dependence / Correlation
export function getTailDependence(tickers: string[]) {
  return fetchAPI<TailDependenceResponse>(
    `/api/correlation/tail-dependence?tickers=${tickers.join(",")}`
  );
}

// Savings
export function projectSavings(params: SavingsRequest) {
  return fetchAPI<SavingsProjection>("/api/savings/project", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// Portfolio questionnaire
export function submitQuestionnaire(answers: QuestionnaireAnswers) {
  return fetchAPI<QuestionnaireResult>("/api/portfolio/questionnaire", {
    method: "POST",
    body: JSON.stringify(answers),
  });
}

// Portfolio projection
export function projectPortfolio(holdings: Holding[], years = 1, monthlyAdd = 0) {
  return fetchAPI<PortfolioProjection>("/api/portfolio/project", {
    method: "POST",
    body: JSON.stringify({ holdings, years, monthly_add: monthlyAdd }),
  });
}

// ── v9 Advanced Analytics ────────────────────────────────────

// Liquidity Risk
export function getLiquidity(ticker: string) {
  return fetchAPI<LiquidityMetrics>(`/api/analytics/liquidity/${ticker}`);
}

// Copula Tail Dependence
export function getCopulaPair(tickerA: string, tickerB: string) {
  return fetchAPI<CopulaPairResult>(`/api/analytics/copula/${tickerA}/${tickerB}`);
}

// Factor Model (FF6 = FF5 + Momentum)
export function getFactorDecomposition(ticker: string) {
  return fetchAPI<FactorDecomposition>(`/api/analytics/factors-ff6/${ticker}`);
}

export function getFactorDecompositionFF5(ticker: string) {
  return fetchAPI<FactorDecomposition>(`/api/analytics/factors/${ticker}`);
}

// Momentum Rankings
export function getMomentumRankings() {
  return fetchAPI<MomentumRankings>("/api/analytics/momentum");
}

// Economic Surprise
export function getEconomicSurprise() {
  return fetchAPI<EconomicSurprise>("/api/analytics/economic-surprise");
}

// Google Trends Sentiment
export function getTrendsSentiment() {
  return fetchAPI<TrendsSentimentFull>("/api/analytics/trends-sentiment");
}

export function getTickerAttention(ticker: string) {
  return fetchAPI<TickerAttention>(`/api/analytics/trends-sentiment/${ticker}`);
}

// Stress Testing
export function getStressScenarios() {
  return fetchAPI<StressScenarios>("/api/analytics/scenarios");
}

export function stressTestStock(ticker: string) {
  return fetchAPI<StressTestResult>(`/api/analytics/stress-test/${ticker}`);
}

export function hypotheticalStress(weights: Record<string, number>, shocks: Record<string, number>) {
  return fetchAPI<HypotheticalStressResult>("/api/analytics/stress-test/hypothetical", {
    method: "POST",
    body: JSON.stringify({ weights, shocks }),
  });
}

// Crash Timeline
export function getCrashTimeline() {
  return fetchAPI<CrashTimeline>("/api/analytics/crash-timeline");
}

// Changepoint Detection
export function getChangepoint() {
  return fetchAPI<ChangepointResult>("/api/analytics/changepoint");
}

// Covariance Diagnostics
export function getCovarianceDiagnostics() {
  return fetchAPI<CovarianceDiagnostics>("/api/analytics/covariance-diagnostics");
}

// Insider Trading
export function getInsiderTrading(ticker: string) {
  return fetchAPI<InsiderTradingResult>(`/api/stock/${ticker}/insiders`);
}

// Portfolio Attribution (Brinson-Fachler)
export function getPortfolioAttribution(holdings: Holding[], benchmark = "SPY", period = "1mo") {
  return fetchAPI<AttributionResult>("/api/portfolio/attribution", {
    method: "POST",
    body: JSON.stringify({ holdings, benchmark, period }),
  });
}

// Risk Contributions (MCTR)
export function getRiskContributions(tickers: string[], weights: number[]) {
  return fetchAPI<RiskContributions>("/api/portfolio/risk-contributions", {
    method: "POST",
    body: JSON.stringify({ tickers, weights }),
  });
}

// Advanced Portfolio Optimization
export function optimizePortfolio(tickers: string[], method = "mean_cvar") {
  return fetchAPI<OptimizationResult>("/api/portfolio/optimize", {
    method: "POST",
    body: JSON.stringify({ tickers, method }),
  });
}

export function comparePortfolioMethods(tickers: string[]) {
  return fetchAPI<ComparisonResult>("/api/portfolio/compare", {
    method: "POST",
    body: JSON.stringify({ tickers }),
  });
}

// Portfolio Factor Exposures (Fama-French 5-factor)
export function getPortfolioFactorExposures(holdings: Holding[], lookbackDays = 756) {
  return fetchAPI<FactorExposureResult>("/api/portfolio/factor-exposures", {
    method: "POST",
    body: JSON.stringify({ holdings, lookback_days: lookbackDays }),
  });
}

// Portfolio Copula Tail Risk
export function getPortfolioCopulaRisk(holdings: Holding[], lookbackDays = 504) {
  return fetchAPI<CopulaRiskResult>("/api/portfolio/copula-risk", {
    method: "POST",
    body: JSON.stringify({ holdings, lookback_days: lookbackDays }),
  });
}

// Portfolio Benchmark Analytics (tracking error, IR, active share, capture ratios)
export function getPortfolioBenchmark(holdings: Holding[], benchmark = "SPY", lookbackDays = 504) {
  return fetchAPI<BenchmarkAnalyticsResult>("/api/portfolio/benchmark", {
    method: "POST",
    body: JSON.stringify({ holdings, benchmark, lookback_days: lookbackDays }),
  });
}

// AI Portfolio Commentary
export function getPortfolioCommentary(holdings: Holding[]) {
  return fetchAPI<PortfolioCommentary>("/api/portfolio/commentary", {
    method: "POST",
    body: JSON.stringify({ holdings }),
  });
}

// Stock Sentiment
export function getStockSentiment(ticker: string) {
  return fetchAPI<StockSentiment>(`/api/stock/${ticker}/sentiment`);
}

// Stock Fundamentals (SEC EDGAR)
export function getStockFundamentals(ticker: string) {
  return fetchAPI<StockFundamentals>(`/api/stock/${ticker}/fundamentals`);
}

// Monte Carlo Retirement Simulation
export function simulateRetirement(params: RetirementMCRequest) {
  return fetchAPI<RetirementMCResult>("/api/savings/simulate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// Safe Withdrawal Rate Calculator
export function computeSafeWithdrawalRate(
  savings: number,
  retirementYears = 30,
  riskLevel = "moderate",
  targetSuccessRate = 95,
) {
  return fetchAPI<SafeWithdrawalResult>("/api/savings/safe-rate", {
    method: "POST",
    body: JSON.stringify({
      savings,
      retirement_years: retirementYears,
      risk_level: riskLevel,
      target_success_rate: targetSuccessRate,
    }),
  });
}

// Drawdown & Rolling Return Analysis
export function getDrawdownAnalysis(ticker: string, period = "10y") {
  return fetchAPI<DrawdownAnalysis>(`/api/analytics/drawdowns/${ticker}?period=${period}`);
}

// Conformal Prediction Interval
export function getConformalInterval(crashProb: number, horizon = "3m", alpha = 0.10) {
  return fetchAPI<ConformalInterval>(
    `/api/analytics/conformal-interval?crash_prob=${crashProb}&horizon=${horizon}&alpha=${alpha}`
  );
}

// ── v10 New Analytics ──────────────────────────────��───────

// Technical Analysis (RSI, MACD, Bollinger Bands, ADX, patterns)
export function getStockTechnicals(ticker: string) {
  return fetchAPI<TechnicalAnalysis>(`/api/stock/${ticker}/technicals`);
}

// Chart Pattern Recognition
export function getStockPatterns(ticker: string) {
  return fetchAPI<ChartPatternAnalysis>(`/api/stock/${ticker}/patterns`);
}

// Volatility Analytics (Bloomberg-style vol cone, GARCH forecast)
export function getStockVolatility(ticker: string) {
  return fetchAPI<VolatilityAnalytics>(`/api/stock/${ticker}/volatility`);
}

// Dividend Intelligence (Morningstar-style analytics)
export function getStockDividends(ticker: string) {
  return fetchAPI<DividendIntelligence>(`/api/stock/${ticker}/dividends`);
}

// Polygon.io Real-Time Snapshot
export function getRealtimeSnapshot(ticker: string) {
  return fetchAPI<RealtimeSnapshot>(`/api/realtime/${ticker}`);
}

// Sector Rotation Model
export function getSectorRotation() {
  return fetchAPI<SectorRotation>("/api/analytics/sector-rotation");
}

// Fixed Income Dashboard
export function getFixedIncome() {
  return fetchAPI<FixedIncomeDashboard>("/api/analytics/fixed-income");
}

// Market Valuation Metrics
export function getMarketValuation() {
  return fetchAPI<MarketValuation>("/api/analytics/valuation");
}

// Missing endpoints — wired in cycle 062
export function getPcaResiduals(tickers: string[]) {
  return fetchAPI<Record<string, unknown>>("/api/analytics/factors/pca-residuals", {
    method: "POST",
    body: JSON.stringify({ tickers }),
  });
}

export function getPortfolioFactorsFF5(weights: Record<string, number>) {
  return fetchAPI<Record<string, unknown>>("/api/analytics/factors/portfolio", {
    method: "POST",
    body: JSON.stringify(weights),
  });
}

export function stressTestPortfolio(weights: Record<string, number>) {
  return fetchAPI<Record<string, unknown>>("/api/analytics/stress-test", {
    method: "POST",
    body: JSON.stringify({ weights }),
  });
}

export function getMomentumScore(ticker: string) {
  return fetchAPI<Record<string, unknown>>(`/api/analytics/momentum/${ticker}`);
}

export function getLiquidityUniverse() {
  return fetchAPI<Record<string, unknown>>("/api/analytics/liquidity");
}

export function getCopulaPortfolio(tickers: string[], weights: number[]) {
  return fetchAPI<Record<string, unknown>>("/api/analytics/copula/portfolio", {
    method: "POST",
    body: JSON.stringify({ tickers, weights }),
  });
}

export function getVixTermStructureAnalytics() {
  return fetchAPI<Record<string, unknown>>("/api/analytics/vix-term-structure");
}

export function getCrashDiagnostics() {
  return fetchAPI<Record<string, unknown>>("/api/crash/diagnostics");
}

export function getSignalBacktest(ticker?: string, lookback?: number) {
  const params = new URLSearchParams();
  if (ticker) params.set("ticker", ticker);
  if (lookback) params.set("lookback_days", String(lookback));
  return fetchAPI<Record<string, unknown>>(`/api/backtest/signal?${params}`);
}

export function getDriftCheck() {
  return fetchAPI<Record<string, unknown>>("/api/drift/check");
}

// Relative Valuation (Koyfin-style peer comparison)
export function getStockValuation(ticker: string) {
  return fetchAPI<RelativeValuation>(`/api/stock/${ticker}/valuation`);
}

// Style Box (Morningstar 3x3)
export type StyleBox = {
  ticker: string;
  sector: string;
  name?: string;
  market_cap?: number;
  size: "Small" | "Mid" | "Large" | "Unknown";
  style: "Value" | "Blend" | "Growth";
  cell: string;
  cells: { size: string; style: string; key: string; active: boolean }[];
  net_style_score: number | null;
  value_score: number | null;
  growth_score: number | null;
  components: {
    value: Record<string, number | null>;
    growth: Record<string, number | null>;
  };
  peer_count: number;
};
export function getStyleBox(ticker: string) {
  return fetchAPI<StyleBox>(`/api/stock/${ticker}/style-box`);
}

// Factor Grades (Seeking Alpha-style A..F)
export type FactorGradeComponent = {
  grade: string | null;
  percentile: number | null;
  color: string;
  details: Record<string, { value?: number; peer_percentile?: number; grade?: string }>;
};
export type FactorGrades = {
  ticker: string;
  sector?: string;
  overall_grade: string | null;
  overall_percentile: number | null;
  overall_color: string;
  components: {
    value: FactorGradeComponent;
    growth: FactorGradeComponent;
    profitability: FactorGradeComponent;
    momentum: FactorGradeComponent;
    revisions: FactorGradeComponent;
  };
  peer_count?: number;
};
export function getFactorGrades(ticker: string) {
  return fetchAPI<FactorGrades>(`/api/stock/${ticker}/grades`);
}

// Short Interest / Squeeze Score
export type ShortInterest = {
  ticker: string;
  name?: string;
  shares_short?: number;
  short_percent_float?: number;
  days_to_cover?: number;
  float_shares?: number;
  avg_daily_volume_10d?: number;
  month_over_month_change_pct?: number;
  momentum_3m?: number;
  squeeze_score_0_100?: number;
  regime: "low" | "moderate" | "high" | "extreme" | "unknown";
  source?: string;
};
export function getShortInterest(ticker: string) {
  return fetchAPI<ShortInterest>(`/api/stock/${ticker}/short-interest`);
}

// Estimate Revisions
export type RevisionsWindow = { up: number; down: number; hold: number; total: number };
export type RevisionsTrend = {
  ticker: string;
  consensus_label: string;
  windows: Record<string, RevisionsWindow>;
  price_targets: {
    mean?: number;
    median?: number;
    high?: number;
    low?: number;
    number_of_analysts?: number;
    current_price?: number;
    implied_upside_pct?: number;
  } | null;
};
export function getRevisionsTrend(ticker: string) {
  return fetchAPI<RevisionsTrend>(`/api/stock/${ticker}/revisions`);
}

// Market Treemap (Finviz-style)
export type TreemapTicker = { ticker: string; market_cap: number; return_pct: number; size: number; value: number };
export type TreemapSector = { name: string; size: number; value: number; children: TreemapTicker[] };
export type MarketTreemap = {
  window: string;
  children: TreemapSector[];
  total_market_cap: number;
  ticker_count?: number;
  missing?: string[];
};
export function getMarketTreemap(window: "1d" | "1w" | "1m" | "ytd" = "1d") {
  return fetchAPI<MarketTreemap>(`/api/analytics/treemap?window=${window}`);
}

// Allocation Backtester (Portfolio Visualizer-style)
export type AllocationMetrics = {
  cagr: number;
  volatility_annualized: number;
  sharpe_ratio: number | null;
  max_drawdown: number;
  max_drawdown_peak_date?: string;
  max_drawdown_trough_date?: string;
  best_calendar_year?: number | null;
  worst_calendar_year?: number | null;
  final_value: number;
  n_years: number;
};
export type AllocationBacktest = {
  weights: Record<string, number>;
  start: string;
  rebalance_freq: string;
  initial_value: number;
  metrics: AllocationMetrics;
  equity_curve: { date: string; value: number }[];
  n_observations: number;
};
export function listAllocationStrategies() {
  return fetchAPI<{ strategies: { name: string; weights: Record<string, number> }[] }>(
    "/api/analytics/allocation-strategies",
  );
}
export function backtestNamedAllocation(name: string, start = "2010-01-01", rebalance = "quarterly") {
  return fetchAPI<AllocationBacktest>(
    `/api/analytics/allocation-backtest/${name}?start=${start}&rebalance=${rebalance}`,
  );
}
export function backtestCustomAllocation(weights: Record<string, number>, start = "2010-01-01", rebalance = "quarterly") {
  return fetchAPI<AllocationBacktest>("/api/analytics/allocation-backtest", {
    method: "POST",
    body: JSON.stringify({ weights, start, rebalance_freq: rebalance }),
  });
}

// AI Copilot — natural-language queries over the engine
export type CopilotMessage = { role: "user" | "assistant"; content: string };
export type CopilotResponse = {
  answer: string;
  tool_calls: { name: string; args: unknown; result_preview: string }[];
  provider: "claude" | "deepseek";
  note?: string;
};
export function copilotStatus() {
  return fetchAPI<{ available: boolean; tool_count: number }>("/api/copilot/status");
}
export function copilotTools() {
  return fetchAPI<{ tools: { name: string; description: string; parameters: unknown }[] }>(
    "/api/copilot/tools",
  );
}
export function copilotChat(messages: CopilotMessage[], prefer?: "claude" | "deepseek") {
  return fetchAPI<CopilotResponse>("/api/copilot/chat", {
    method: "POST",
    body: JSON.stringify({ messages, prefer }),
  });
}

// Pair Analysis (cointegration)
export function getPairAnalysis(tickerA: string, tickerB: string) {
  return fetchAPI<PairAnalysisResult>(`/api/analytics/pairs/${tickerA}/${tickerB}`);
}

export function scanPairs(tickers?: string[]) {
  const params = tickers ? `?tickers=${tickers.join(",")}` : "";
  return fetchAPI<PairScanResult>(`/api/analytics/pairs/scan${params}`);
}

// Tail Risk (institutional-grade: Sortino, Omega, Calmar, etc.)
export function getTailRisk(ticker: string, period = "5y") {
  return fetchAPI<TailRiskResult>(`/api/analytics/tail-risk/${ticker}?period=${period}`);
}

// Survival Model (Cox PH crash timing)
export function getSurvivalModel() {
  return fetchAPI<SurvivalModelResult>("/api/analytics/survival-model");
}

// Cross-Asset Macro Regime Monitor (Bloomberg MAC3-style)
export function getCrossAssetDashboard() {
  return fetchAPI<CrossAssetDashboard>("/api/analytics/cross-asset");
}

export function getMacroRegime() {
  return fetchAPI<MacroRegime>("/api/analytics/macro-regime");
}

// World Markets (WEI) + Economic Calendar
export interface WorldMarketRow {
  ticker: string;
  name: string;
  region: string;
  category: "index" | "fx" | "commodity" | "yield";
  price: number;
  change: number | null;
  change_pct: number | null;
  prev_close: number | null;
  source: string;
}

export interface WorldMarketsResponse {
  counts: {
    indices: number;
    fx: number;
    commodities: number;
    yields: number;
    total_attempted: number;
    total_fetched: number;
  };
  indices: WorldMarketRow[];
  fx: WorldMarketRow[];
  commodities: WorldMarketRow[];
  yields: WorldMarketRow[];
  top_gainers: WorldMarketRow[];
  top_losers: WorldMarketRow[];
}

export function getWorldMarkets() {
  return fetchAPI<WorldMarketsResponse>("/api/world-markets");
}

export interface EconomicEvent {
  date: string;
  time: string;
  country: string | null;
  event: string | null;
  actual: number | null;
  estimate: number | null;
  prior: number | null;
  impact: string | null;
  unit: string | null;
}

export interface EconomicCalendarResponse {
  days_ahead: number;
  count: number;
  events: EconomicEvent[];
  note?: string;
  error?: string;
}

export function getEconomicCalendar(days = 14) {
  return fetchAPI<EconomicCalendarResponse>(`/api/economic-calendar?days_ahead=${days}`);
}

export interface EarningsEvent {
  ticker: string;
  date: string;
  eps_estimate: number | null;
  eps_actual: number | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  time: string | null;
  source: string;
}

export interface EarningsCalendarResponse {
  days_ahead: number;
  ticker: string | null;
  count: number;
  events: EarningsEvent[];
}

export function getEarningsCalendar(opts: { ticker?: string; days?: number } = {}) {
  const p = new URLSearchParams();
  if (opts.ticker) p.set("ticker", opts.ticker);
  if (opts.days) p.set("days_ahead", String(opts.days));
  const qs = p.toString();
  return fetchAPI<EarningsCalendarResponse>(
    `/api/analytics/earnings-calendar${qs ? `?${qs}` : ""}`,
  );
}

// Institutional ownership + ETF look-through
export interface OwnershipHolder {
  holder: string | null;
  shares: number | null;
  value: number | null;
  pct_held: number | null;
  pct_change: number | null;
  date_reported: string | null;
}

export interface OwnershipResponse {
  ticker: string;
  holders: OwnershipHolder[];
  summary: Record<string, number | null>;
  crowding: {
    level: "low" | "moderate" | "high" | "very_high";
    top10_pct_held: number;
    note: string;
  };
  recent_activity: {
    buyers_top10: number;
    sellers_top10: number;
    net_signal: "accumulating" | "distributing" | "neutral";
  };
  source: string;
}

export function getStockOwnership(ticker: string) {
  return fetchAPI<OwnershipResponse>(`/api/stock/${encodeURIComponent(ticker)}/ownership`);
}

export interface EtfHolding {
  symbol: string;
  name: string | null;
  weight: number | null;
}

export interface EtfLookthroughResponse {
  ticker: string;
  top_holdings: EtfHolding[];
  sector_weights: Record<string, number | null>;
  concentration: {
    top5_pct: number;
    top10_pct: number;
    level: "low" | "moderate" | "high" | "very_high";
  };
  source: string;
}

export function getEtfLookthrough(ticker: string) {
  return fetchAPI<EtfLookthroughResponse>(
    `/api/stock/${encodeURIComponent(ticker)}/etf-lookthrough`,
  );
}

// Unified analyst consensus (multi-provider fallback)
export interface AnalystConsensusResponse {
  ticker: string;
  target_mean?: number;
  target_high?: number;
  target_low?: number;
  target_median?: number;
  num_analysts?: number;
  strong_buy?: number;
  buy?: number;
  hold?: number;
  sell?: number;
  strong_sell?: number;
  source: string;
  as_of?: string;
}

export function getAnalystConsensus(ticker: string) {
  return fetchAPI<AnalystConsensusResponse>(
    `/api/analytics/analyst-consensus/${encodeURIComponent(ticker)}`,
  );
}

// Tearsheet exports — return blobs for the browser to download / open.
export async function downloadPortfolioTearsheet(
  holdings: Holding[],
  format: "html" | "xlsx",
  title = "Portfolio Tearsheet",
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/portfolio/tearsheet.${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ holdings, title }),
  });
  if (!res.ok) {
    throw new Error(`Tearsheet export failed: ${res.status}`);
  }
  return res.blob();
}

// ── Types ──────────────────────────────────────────────────

export interface MarketDashboard {
  market: {
    sp500: number;
    sp500_1d_pct: number;
    sp500_1m_pct: number;
    sp500_3m_pct: number;
    sp500_ytd_pct: number;
    vix: number | null;
    yield_10y: number | null;
    yield_3m: number | null;
    yield_spread: number | null;
    date: string;
  } | null;
  regime: {
    regime: string;
    risk_score: number;
    vix_term_structure: string | null;
    vts_signal: string | null;
  } | null;
  crash: {
    available: boolean;
    probabilities?: Record<string, number>;
    drift_severity?: string | null;
  } | null;
  risk: Record<string, unknown> | null;
  fixed_income: {
    curve_shape: string;
    curve_interpretation: string;
    inversions: string[];
    spread_10y_2y: number | null;
    hy_spread: number | null;
    credit_stress: string | null;
    breakeven_inflation: number | null;
  } | null;
  valuation: {
    cape: number | null;
    cape_percentile: number | null;
    cape_interpretation: string | null;
    forward_pe: number | null;
    erp_pct: number | null;
    valuation_score: number | null;
    valuation_level: string | null;
  } | null;
  volatility: {
    regime: string;
    vol_30d_pct: number | null;
    vol_percentile: number | null;
  } | null;
  economic: {
    composite_score: number;
    signal: string;
    trend: string;
  } | null;
  sentiment: {
    sentiment: string;
    signal: number;
    fear_greed_ratio: number;
  } | null;
  liquidity: {
    net_liquidity_t: number | null;
    wow_change_t: number | null;
    signal: string;
  } | null;
  crypto: {
    btc_price: number;
    btc_1d_pct: number;
    btc_1m_pct: number | null;
    btc_3m_pct: number | null;
    btc_sp500_corr_30d: number | null;
    interpretation: string;
  } | null;
  breadth: {
    stocks_positive_pct: number;
    stocks_positive: number;
    stocks_total: number;
    interpretation: string;
  } | null;
}

export interface MarketStatus {
  sp500: number;
  sp500_change_1m: number;
  sp500_change_ytd: number;
  vix: number | null;
  yield_curve: number | null;
  risk_score: number;
  regime: string;
  crash_probabilities: Record<string, number>;
  data_quality: DataQuality | null;
  net_liquidity: NetLiquidityCurrent | null;
  trends_sentiment: TrendsSentiment | null;
  vix_term_structure: {
    structure: string;
    signal: string;
    vix_level: string;
    interpretation: string;
  } | null;
  economic_surprise: {
    composite_score: number;
    signal: string;
    trend: string;
    positive_surprises: number;
    negative_surprises: number;
    breadth: number;
  } | null;
  sector_rotation: {
    cycle_phase: {
      phase: string;
      confidence: number;
      description: string;
    } | null;
    breadth: string | { positive_sectors?: number; total_sectors?: number; pct_positive?: number } | null;
    leaders: string[];
    laggards: string[];
  } | null;
  changepoint: {
    detected: boolean;
    days_since: number | null;
    max_prob: number;
    interpretation: string;
  } | null;
  survival_crash_timing: {
    probabilities: Record<string, number>;
    method: string;
    top_risk_factors: { feature: string; coefficient: number }[];
    n_train: number;
    n_events: number;
  } | null;
  // Cycle_080 integrations
  vol_regime: {
    regime: string;
    current_30d_vol_pct: number | null;
    percentile: number | null;
    interpretation: string;
  } | null;
  crash_intervals: Record<string, {
    point_estimate: number;
    lower: number;
    upper: number;
    width: number;
  }> | null;
  market_drawdown: {
    current_drawdown_pct: number;
    max_drawdown_pct: number | null;
    total_drawdowns: number;
    avg_recovery_days: number | null;
    rolling_sharpe_1y: number | null;
  } | null;
  cross_asset_regime: {
    quadrant: string;
    growth_score: number;
    inflation_score: number;
    growth_interpretation: string;
    inflation_interpretation: string;
    regime_stable: boolean | null;
    description: string;
  } | null;
  last_updated: string;
}

export interface DataQuality {
  status: "healthy" | "warning" | "degraded";
  errors: number;
  warnings: number;
  info: number;
  details: { check: string; column: string; message: string; severity: string }[];
}

export interface NetLiquidityCurrent {
  walcl: number | null;
  tga: number | null;
  rrp: number | null;
  net_liquidity: number | null;
  wow_change: number | null;
  wow_change_pct: number | null;
  signal: string;
}

export interface NetLiquidityResponse {
  current: NetLiquidityCurrent;
  formula: string;
  unit: string;
  history: { date: string; walcl: number; tga: number; rrp: number; net_liquidity: number; wow_change: number }[];
  last_updated: string;
  error?: string;
}

export interface MacroResponse {
  indicators: Record<string, MacroIndicator>;
  count: number;
}

export interface MacroIndicator {
  name: string;
  value: number;
  change_1m_pct: number | null;
  last_date: string;
}

export interface CrashPrediction {
  probabilities: Record<string, number>;
  primary_horizon: string;
  primary_prob: number | null;
  last_updated: string;
  explanation?: {
    crash_prob: number;
    horizon: string;
    top_features: { feature: string; shap_value: number; feature_value: number | null }[];
  };
  external_validation?: {
    consensus_direction: string;
    engine_agreement: number;
    signals: { lei: string; sloos: string; fed: string; sentiment: string };
    divergence_alerts: string[];
  };
  regime_validation?: {
    regime: string;
    confirmed: boolean;
    confidence: string;
    checks: { price_structure: boolean; breadth: boolean; consensus: boolean };
    notes: string[];
  };
  status?: string;
  message?: string;
}

export interface TickerCrash {
  ticker: string;
  name: string;
  current_price: number;
  beta: number;
  market_crash_probs: Record<string, number>;
  ticker_crash_probs: Record<string, number>;
  risk_level: string;
}

export interface SP500Projection {
  start_price: number;
  forecast_years: number;
  n_sims: number;
  median_final: number;
  mean_final: number;
  p05_final: number;
  p95_final: number;
  median_total_return: number;
  median_annual_return: number;
  prob_loss: number;
  percentile_paths: Record<string, number[]>;
  scenario_weights: Record<string, number>;
  last_updated: string;
}

export interface ScenariosResponse {
  scenarios: ScenarioResult[];
  start_price: number;
}

export interface ScenarioResult {
  name: string;
  weight: number;
  description: string;
  median_return: number;
  p05_return: number;
  p95_return: number;
  prob_loss: number;
}

export interface StockAnalysis {
  ticker: string;
  name: string;
  sector: string;
  current_price: number;
  market_cap: number | null;
  cap_tier: string;
  beta: number;
  pe_ratio: number | null;
  analyst_target: number | null;
  hist_drift: number;
  capped_drift: number;
  volatility: number;
  expected_return: number;
  median_return: number;
  p05_price: number;
  p95_price: number;
  prob_loss_5y: number;
  avg_max_drawdown: number;
  sharpe: number;
  analyst_targets: AnalystTargets | null;
  recommendations: Recommendations | null;
  holders: HoldersData | null;
  news: NewsItem[] | null;
  earnings: EarningsData | null;
  price_history: { date: string; price: number }[] | null;
  key_stats: Record<string, number | null> | null;
  peers: string[] | null;
  // Enriched fields from backend router
  insider_signal?: {
    signal: number;
    cluster_buy: boolean;
    interpretation?: string;
    n_buys?: number;
    n_sells?: number;
    buy_value?: number;
    sell_value?: number;
  } | null;
  liquidity?: {
    score: number;
    tier: string;
    amihud: number;
    avg_dollar_volume_mm: number;
    lvar_95: number;
  } | null;
  momentum_rank?: {
    percentile: number;
    score: number;
    rank: number;
    total: number;
  } | null;
  technical_signal?: {
    sentiment: string;
    score: number;
    confidence?: number;
    reasons?: string[];
  } | null;
  rsi_14?: number | null;
  trend_direction?: string | null;
  trends_attention?: {
    attention_level: string;
    attention_zscore: number;
    interpretation: string;
  } | null;
  drawdown_analysis?: {
    total_drawdowns: number;
    max_drawdown_pct: number;
    avg_recovery_days: number;
    current_drawdown_pct: number;
    rolling_sharpe_1y: number;
    rolling_sortino_1y: number;
  } | null;
  factor_exposure?: {
    r_squared: number;
    alpha_annual: number;
    market_beta: number;
    factors: Record<string, number>;
    style: Record<string, string>;
  } | null;
  relative_valuation?: {
    verdict?: string;
    verdict_color?: string;
    composite_score?: number;
    peer_count?: number;
    sector?: string;
    historical_pe_pctile?: number | null;
    notable_metrics?: { metric: string; value: number | null; peer_avg: number | null; vs_peers: string; percentile: number | null }[];
    implied_fair_value?: {
      blended: number;
      upside_pct: number;
      estimates: Record<string, number>;
      method: string;
    } | null;
  } | null;
  crash_prob_3m?: number | null;
  crash_prob_interval?: {
    lower: number;
    upper: number;
    width: number;
  } | null;
  // Volatility analytics (Bloomberg-style vol summary)
  volatility_analytics?: {
    current_iv?: number | null;
    garch_forecast?: number;
    vol_regime?: string;
    vol_percentile?: number;
    vol_cone?: Record<string, { current: number; p25: number; p50: number; p75: number }>;
    hv_20d?: number;
    hv_60d?: number;
    iv_hv_spread?: number | null;
  } | null;
  // Dividend intelligence (Morningstar-style)
  dividend_intelligence?: {
    yield_pct?: number | null;
    annual_dividend?: number | null;
    payout_ratio?: number | null;
    growth_5y?: number | null;
    years_of_growth?: number | null;
    safety_score?: number | null;
    safety_label?: string | null;
    ex_date?: string | null;
    frequency?: string | null;
  } | null;
  // Survival model crash timing (Cox PH)
  survival_crash_timing?: Record<string, number> | null;
  // Bubble indicator (LPPL Sornette)
  bubble_indicator?: {
    confidence?: number | null;
    is_bubble?: boolean;
    status?: string;
    tc_date?: string | null;
  } | null;
  // Chart pattern recognition
  chart_patterns?: {
    patterns: { name: string; type: string; confidence: number }[];
    pattern_count: number;
    bias: string;
    strongest_pattern?: string | null;
    support_resistance?: {
      support: { price: number; touches: number; strength: number }[];
      resistance: { price: number; touches: number; strength: number }[];
      current_price?: number;
    } | null;
  } | null;
}

export interface AnalystTargets {
  current: number | null;
  low: number | null;
  mean: number | null;
  median: number | null;
  high: number | null;
}

export interface Recommendations {
  strongBuy: number;
  buy: number;
  hold: number;
  sell: number;
  strongSell: number;
}

export interface HoldersData {
  insider_pct?: string;
  institution_pct?: string;
  top_holders?: { name: string; shares: number; pct: number }[];
}

export interface NewsItem {
  title: string;
  publisher: string;
  link: string;
  date?: string;
  published?: string;
  type?: string;
}

export interface EarningsData {
  next_date: string | null;
  estimate: number | null;
  surprise_history: number[];
}

export interface MarketNewsResponse {
  gdelt: {
    avg_tone: number;
    tone_trend: number;
    volume_zscore: number;
    conflict_score: number;
    raw_data: { tone: number[]; volume: number[]; conflict: number[] };
    success: boolean;
    error?: string;
  };
  event_score: {
    event_score: number;
    components: { tone_score: number; volume_score: number; gpr_score: number };
    interpretation: string;
    regime_override: string | null;
  };
  news: NewsItem[];
  sector_impact?: Record<string, { relevance: number; headline_count: number; sample_headlines: string[] }>;
  llm_summary: { summary: string; sentiment: string } | null;
  llm_available: boolean;
}

export interface StockNewsResponse {
  ticker: string;
  news: NewsItem[];
  llm_outlook: {
    bull_case: string;
    bear_case: string;
    sentiment_score: number;
    summary: string;
  } | null;
  llm_available: boolean;
}

export interface SavingsRequest {
  monthly_contribution: number;
  current_savings: number;
  current_age: number;
  target_age: number;
  risk_level: string;
  inflation_rate: number;
  target_amount: number;
}

export interface SavingsProjection {
  projections: {
    year: number;
    age: number;
    nominal_balance: number;
    real_balance: number;
    total_contributed: number;
    growth: number;
  }[];
  summary: {
    final_nominal: number;
    final_real: number;
    total_contributed: number;
    total_growth: number;
    nominal_rate: number;
    inflation_rate: number;
    real_rate: number;
  };
  target: {
    amount: number;
    met: boolean;
    met_at_age: number | null;
    years_to_target: number | null;
    required_monthly: number | null;
  };
  milestones: { amount: number; age: number; year: number }[];
  error?: string;
}

export interface PortfolioProjection {
  current_value: number;
  horizon_years: number;
  monthly_add: number;
  expected_final: number;
  p10_final: number;
  p90_final: number;
  prob_gain: number;
  expected_return_pct: number;
  quarterly: {
    quarter: number;
    median: number;
    p10: number;
    p25: number;
    p75: number;
    p90: number;
  }[];
  error?: string;
}

export interface MarketSignal {
  action: string;
  confidence: number;
  color: string;
  composite_score: number;
  reasons: string[];
  components: Record<string, number>;
  sp500?: number;
  regime?: string;
  risk_score?: number;
  vix?: number;
  last_updated?: string;
}

export interface StockSignal {
  ticker: string;
  name?: string;
  action: string;
  confidence: number;
  color: string;
  composite_score: number;
  reasons: string[];
  beta_adj?: number;
  current_price?: number;
  market_action?: string;
  error?: string;
}

export interface ShapExplanation {
  ticker?: string;
  crash_prob: number;
  horizon: string;
  top_features: { feature: string; shap_value: number; feature_value: number | null }[];
  status?: string;
}

export interface ScreenerStock {
  ticker: string;
  name: string;
  sector: string;
  current_price: number;
  expected_return: number;
  sharpe: number;
  prob_loss: number;
  volatility: number;
  beta: number;
  pe_ratio: number | null;
  analyst_target: number | null;
  market_cap: number | null;
  signal_action?: string;
  signal_confidence?: number;
  signal_score?: number;
  crash_prob_3m?: number | null;
  prediction_confidence?: string | null;
  // Per-stock analytics (cycle_068)
  liquidity_score?: number | null;
  liquidity_tier?: string | null;
  momentum_rank?: number | null;
  momentum_percentile?: number | null;
  rsi_14?: number | null;
  trend_direction?: string | null;
  max_drawdown_pct?: number | null;
  current_drawdown_pct?: number | null;
  // Signal sub-scores + factor style (cycle_080)
  options_score?: number | null;
  earnings_score?: number | null;
  insider_score?: number | null;
  ta_score?: number | null;
  factor_style?: string | null;
  factor_alpha?: number | null;
  pattern_bias?: string | null;
  pattern_count?: number | null;
  dividend_yield?: number | null;
  dividend_safety?: string | null;
  // Full signal component breakdown
  signal_components?: Record<string, number> | null;
}

export interface ScreenerResponse {
  stocks: ScreenerStock[];
  count: number;
  market_signal?: {
    action: string;
    confidence: number;
    composite_score: number;
    reasons: string[];
  };
}

export interface SectorsResponse {
  sectors: SectorResult[];
  count: number;
}

export interface SectorResult {
  name: string;
  rank: number;
  expected_total: number;
  sim_total_return: number;
  expected_annual: number;
  beta: number;
  sigma: number;
  momentum_6m: number;
  momentum_12m: number;
  crash_prob: number;
  current_price: number;
}

export interface Holding {
  ticker: string;
  shares: number;
  current_price: number;
}

export interface PortfolioAnalysis {
  total_value: number;
  annual_return?: number;
  annual_volatility?: number;
  sharpe_ratio?: number;
  var_95_daily?: number;
  cvar_95_daily?: number;
  max_drawdown?: number;
  allocations: { ticker: string; weight: number; value: number }[];
  correlation?: { tickers: string[]; matrix: number[][] };
  risk_number?: {
    risk_number: number;
    category: string;
    portfolio_vol: number;
    portfolio_beta: number;
    max_drawdown_pct: number;
    components: Record<string, number>;
  } | null;
  factor_exposures?: {
    r_squared: number | null;
    alpha_annual: number | null;
    market_beta: number | null;
    style: Record<string, string> | null;
    stocks: Record<string, { market_beta: number; style: Record<string, string> }>;
  } | null;
  // From portfolio_engine.analyze_portfolio
  tail_risk?: {
    sortino_ratio: number;
    omega_ratio: number;
    calmar_ratio: number;
    cvar_95: number;
    tail_ratio: number;
  } | null;
  attribution?: {
    total_portfolio_return: number;
    total_benchmark_return: number;
    active_return: number;
    attribution: { allocation: number; selection: number; interaction: number };
    interpretation: string;
  } | null;
  risk_contributions?: {
    portfolio_volatility_annual: number;
    contributions: Record<string, {
      weight_pct: number;
      mctr: number;
      risk_contribution_pct: number;
      risk_weight_ratio: number;
    }>;
  } | null;
  copula_risk?: {
    copula_var_95: number;
    copula_cvar_95: number;
    tail_dependence: number;
    copula_type: string;
  } | null;
  // Inline attribution + MCTR from /analyze endpoint
  attribution_summary?: {
    period: string | null;
    total_allocation_effect: number | null;
    total_selection_effect: number | null;
    total_interaction_effect: number | null;
    total_active_return: number | null;
    portfolio_return: number | null;
    benchmark_return: number | null;
  } | null;
  mctr_summary?: {
    portfolio_vol: number | null;
    top_risk_contributors: {
      ticker: string;
      weight_pct: number;
      risk_contrib_pct: number;
      mctr: number;
    }[];
  } | null;
  benchmark_analytics?: {
    tracking_error_pct: number | null;
    information_ratio: number | null;
    active_return_annual_pct: number | null;
    active_share: number | null;
    active_share_label: string | null;
    up_capture: number | null;
    down_capture: number | null;
    beta_vs_benchmark: number | null;
    r_squared: number | null;
    management_style: string | null;
    insights: string[];
  } | null;
  // Cycle_068 integrations
  stress_test?: {
    scenarios: Record<string, {
      portfolio_drawdown_pct: number;
      sp500_drawdown_pct: number;
      relative_to_market: number | null;
    }>;
    worst_scenario: string | null;
    worst_drawdown_pct: number | null;
  } | null;
  portfolio_drawdowns?: {
    total_drawdowns: number;
    max_drawdown_pct: number | null;
    avg_recovery_days: number | null;
    current_drawdown_pct: number;
    rolling_return_1y: number | null;
  } | null;
  error?: string;
}

export interface PortfolioBuilt {
  risk_tolerance: string;
  time_horizon: string;
  investment_amount: number;
  description: string;
  holdings: {
    ticker: string;
    weight: number;
    dollar_amount: number;
    shares: number;
    price: number;
  }[];
}

export interface QuestionnaireAnswers {
  horizon: string;
  risk_tolerance: string;
  loss_reaction: string;
  experience: string;
  income_stability: string;
  goal: string;
}

export interface QuestionnaireResult {
  risk_score: number;
  allocation_style: string;
  description: string;
  factors: QuestionnaireAnswers;
  recommended_portfolio: PortfolioBuilt;
}

// Options Intelligence
export interface OptionsAnalysis {
  ticker: string;
  expiration: string;
  current_price: number;
  atm_iv_call?: number;
  atm_iv_put?: number;
  iv_skew?: number;
  iv_skew_interpretation?: string;
  put_call_volume_ratio?: number;
  put_call_oi_ratio?: number;
  total_call_volume?: number;
  total_put_volume?: number;
  max_pain?: number;
  max_pain_distance_pct?: number;
  iv_rank?: number;
  iv_percentile?: number;
  realized_vol_1y?: number;
  iv_vs_rv?: number;
  iv_term_structure?: {
    near_iv: number;
    mid_iv: number;
    slope: number;
    contango: boolean;
    interpretation: string;
  };
  mid_term?: {
    expiration: string;
    atm_iv_call?: number;
    atm_iv_put?: number;
    put_call_volume_ratio?: number;
    iv_skew?: number;
  };
  signal: {
    score: number;
    sentiment: string;
    confidence: number;
    n_signals: number;
    reasons: string[];
  };
  error?: string;
}

export interface VixTermStructure {
  values: Record<string, number>;
  vix_vix3m_ratio?: number;
  contango?: boolean;
  backwardation?: boolean;
  structure?: string;
  signal?: string;
  interpretation?: string;
  vix_level?: string;
  error?: string;
}

export interface EarningsAnalysis {
  ticker: string;
  next_earnings_date?: string;
  days_until_earnings?: number;
  earnings_imminent?: boolean;
  beat_rate?: number;
  avg_surprise_pct?: number;
  surprise_trend?: string;
  earnings_surprises?: {
    quarter: string;
    eps_actual: number;
    eps_estimate: number;
    surprise_pct: number;
    beat: boolean;
  }[];
  revenue_yoy_growth?: number;
  revenue_qoq_growth?: number;
  earnings_yoy_growth?: number;
  fundamentals?: Record<string, number>;
  analyst_targets?: Record<string, number | null>;
  recent_recommendations?: Record<string, number>;
  signal: {
    score: number;
    sentiment: string;
    confidence: number;
    n_signals: number;
    reasons: string[];
  };
  error?: string;
}

export interface TailDependenceResponse {
  pairs: {
    ticker_a: string;
    ticker_b: string;
    tail_dep: number;
    upper_tail: number;
    lower_tail: number;
  }[];
  clusters: string[][];
  portfolio_summary: {
    avg_tail_dep: number;
    max_tail_dep: number;
    diversification_quality: string;
  };
  error?: string;
}

// ── v9 Types ──────────────────────────────────────────────────

export interface LiquidityMetrics {
  ticker: string;
  metrics: {
    amihud_illiquidity: number | null;
    roll_spread_bps: number | null;
    avg_dollar_volume_mm: number;
    daily_turnover_pct: number | null;
  };
  risk: {
    var_95: number | null;
    lvar_95: number | null;
    liquidity_cost_bps: number | null;
  };
  score: { composite: number; tier: string };
  interpretation: string;
}

export interface CopulaPairResult {
  pair: string;
  correlation: { pearson: number; kendall_tau: number };
  copula: {
    best: { family: string; tail_lower: number; tail_upper: number };
    selection: string;
  };
  tail_dependence: { lower: number; upper: number };
  interpretation: string;
}

export interface FactorDecomposition {
  ticker: string;
  model: string;
  r_squared: number;
  alpha_annual: number;
  alpha_significant: boolean;
  factors: Record<string, { loading: number; t_stat: number | null; significant: boolean }>;
  style: Record<string, string>;
  residual_vol: number | null;
}

export interface TrendsSentiment {
  sentiment: "extreme_fear" | "fear" | "neutral" | "greed" | "extreme_greed";
  signal: number;
  fear_greed_ratio: number;
  interpretation: string;
}

export interface TrendsSentimentFull extends TrendsSentiment {
  avg_fear_zscore: number;
  avg_greed_zscore: number;
  fear_terms: Record<string, { current: number; mean: number; max: number; zscore: number }>;
  greed_terms: Record<string, { current: number; mean: number; max: number; zscore: number }>;
}

export interface TickerAttention {
  ticker: string;
  attention_level: "extreme" | "elevated" | "normal" | "low";
  attention_zscore: number;
  interpretation: string;
}

export interface MomentumRankings {
  rankings: {
    ticker: string;
    composite_score: number;
    rank: number;
    sector: string;
    return_1m: number;
    return_3m: number;
    return_6m: number;
    return_12m: number;
  }[];
  summary: { n_stocks: number; avg_score: number; pct_positive: number };
}

export interface EconomicSurprise {
  composite_score: number;
  signal: string;
  trend: string;
  indicators: Record<string, { surprise: number; direction: string }>;
}

export interface StressScenarios {
  scenarios: {
    id: string;
    name: string;
    start: string;
    end: string;
    sp500_drawdown: number;
    description: string;
  }[];
}

export interface StressTestResult {
  ticker: string;
  scenarios: Record<string, { name: string; projected_drawdown: number }>;
}

export interface HypotheticalStressResult {
  shocks_applied: Record<string, number>;
  portfolio_estimated_return: number;
  stock_impacts: Record<string, {
    weight_pct: number;
    estimated_return: number;
    sector: string;
  }>;
  interpretation: string;
}

export interface CrashTimeline {
  months_ahead: number;
  total_simulations: number;
  crash_threshold_pct: number;
  monthly_probabilities: { month: number; date: string; probability: number; cumulative: number }[];
  peak_risk_month: number;
  peak_risk_probability: number;
  total_crash_probability_1y: number;
  total_crash_probability_5y: number;
  contributing_factors: { factor: string; severity: string; detail: string }[];
  regime: string;
  risk_score: number;
  // Legacy compat
  months?: { month: number; date: string; crash_prob: number }[];
  methodology?: string;
}

export interface ChangepointResult {
  changepoint_detected: boolean;
  days_since_changepoint: number;
  max_changepoint_prob: number;
  interpretation: string;
}

export interface CovarianceDiagnostics {
  dimensions: { T: number; N: number; q: number };
  signal_eigenvalues: number;
  noise_eigenvalues: number;
  condition_number: { raw: number; denoised: number; improvement: number };
}

export interface InsiderTradingResult {
  ticker: string;
  signal: number;
  cluster_buy: boolean;
  interpretation: string;
  n_buys: number;
  n_sells: number;
}

export interface AttributionResult {
  attribution: {
    allocation: number;
    selection: number;
    interaction: number;
    total: number;
  };
  sector_detail: Record<string, {
    portfolio_weight: number;
    benchmark_weight: number;
    allocation_effect: number;
    selection_effect: number;
    total_effect: number;
  }>;
  interpretation: string;
}

export interface RiskContributions {
  portfolio_volatility_annual: number;
  contributions: Record<string, {
    weight_pct: number;
    mctr: number;
    risk_contribution_pct: number;
    risk_weight_ratio: number;
  }>;
  concentration: { top_5_risk_pct: number; concentrated: boolean };
}

export interface OptimizationResult {
  method: string;
  weights: Record<string, number>;
  n_assets: number;
  metrics: {
    expected_return: number | null;
    volatility: number | null;
    sharpe_ratio: number | null;
  };
}

export interface ComparisonResult {
  methods: Record<string, OptimizationResult>;
  recommendation: string;
}

export interface PortfolioCommentary {
  commentary: string;
  key_points: string[];
  risk_alerts: string[];
  provider: string;
}

export interface FactorExposureResult {
  portfolio_alpha_annual: number;
  portfolio_factors: Record<string, number>;
  portfolio_style: Record<string, string>;
  risk_attribution: Record<string, number>;
  stocks_analyzed: number;
  stocks_failed: number;
  stock_details: Record<string, { weight: number; decomposition: Record<string, unknown> }>;
}

export interface BenchmarkAnalyticsResult {
  benchmark: string;
  lookback_days: number;
  tracking_error: number;
  tracking_error_pct: number;
  information_ratio: number;
  active_return_annual_pct: number;
  active_share: {
    active_share_pct: number;
    label: string;
    description: string;
    top_active_positions: { ticker: string; portfolio_weight: number; benchmark_weight: number; active_weight: number }[];
  } | null;
  capture_ratios: {
    up_capture: number | null;
    down_capture: number | null;
    capture_ratio: number | null;
    interpretation: string | null;
  };
  rolling_tracking_error: {
    available: boolean;
    current_pct?: number;
    average_pct?: number;
    trend?: string;
    time_series?: { date: string; tracking_error_pct: number }[];
  };
  regression: {
    available: boolean;
    beta?: number;
    alpha_annual_pct?: number;
    r_squared?: number;
    residual_vol_pct?: number;
  };
  period_returns: Record<string, { portfolio_pct: number; benchmark_pct: number; active_return_pct: number; outperformed: boolean }>;
  risk_comparison: {
    portfolio: { annual_return_pct: number; volatility_pct: number; sharpe: number; sortino: number; max_drawdown_pct: number };
    benchmark: { annual_return_pct: number; volatility_pct: number; sharpe: number; sortino: number; max_drawdown_pct: number };
  };
  interpretation: {
    tracking_error_label: string;
    information_ratio_label: string;
    management_style: string | null;
    insights: string[];
  };
}

export interface CopulaRiskResult {
  gaussian_var_95: number;
  gaussian_cvar_95: number;
  copula_var_95: number;
  copula_cvar_95: number;
  tail_dependence: number;
  copula_type: string;
  n_assets: number;
}

export interface StockSentiment {
  ticker: string;
  overall: string;
  avg_score: number;
  headlines: { title: string; sentiment: string; score: number }[];
}

export interface StockFundamentals {
  ticker: string;
  piotroski_f_score: number;
  financials: Record<string, number | null>;
}

export interface DrawdownAnalysis {
  ticker: string;
  period: string;
  n_trading_days: number;
  drawdowns: {
    drawdowns: {
      peak_date: string;
      trough_date: string;
      recovery_date?: string;
      depth_pct: number;
      peak_to_trough_days: number;
      trough_to_recovery_days?: number;
      total_days?: number;
      recovered: boolean;
    }[];
    current: {
      peak_date: string;
      trough_date: string;
      depth_pct: number;
      days_since_peak: number;
      recovered: boolean;
    } | null;
    summary: {
      n_drawdowns: number;
      avg_depth_pct?: number;
      max_depth_pct?: number;
      avg_recovery_days?: number;
      max_recovery_days?: number;
    };
  };
  rolling_returns: Record<string, {
    current: number | null;
    mean: number;
    median: number;
    min: number;
    max: number;
    pct_positive: number;
    series: { date: string; return_pct: number }[];
  }>;
  rolling_risk: {
    sharpe: { current: number | null; mean: number; series: { date: string; sharpe: number }[] };
    sortino: { current: number | null; mean: number; series: { date: string; sortino: number }[] };
    max_drawdown: { current: number | null; worst: number; series: { date: string; max_dd: number }[] };
  };
}

export interface ConformalInterval {
  crash_prob_pct: number;
  interval: { lower_pct: number; upper_pct: number; width_pct: number };
  coverage: number;
  method: string;
  horizon: string;
}

export interface RetirementMCRequest {
  current_savings: number;
  monthly_contribution: number;
  monthly_withdrawal: number;
  current_age: number;
  retirement_age: number;
  end_age: number;
  risk_level: string;
  inflation_rate?: number;
  social_security_monthly?: number;
  social_security_start_age?: number;
  n_sims?: number;
}

export interface RetirementMCResult {
  parameters: RetirementMCRequest & { expected_return: number; expected_volatility: number };
  at_retirement: { age: number; median: number; p10: number; p90: number };
  at_end: { age: number; median: number; p10: number; p90: number; mean: number };
  success_rate: number;
  ruin_probability: number;
  yearly_projections: {
    age: number;
    year: number;
    phase: "accumulation" | "distribution";
    median: number;
    p10: number;
    p25: number;
    p75: number;
    p90: number;
    pct_depleted: number;
  }[];
  interpretation: string;
}

export interface SafeWithdrawalResult {
  safe_monthly_withdrawal: number;
  safe_annual_withdrawal: number;
  safe_withdrawal_rate_pct: number;
  four_pct_rule_monthly: number;
  four_pct_rule_annual: number;
  vs_four_pct: number;
  target_success_rate: number;
  retirement_years: number;
  interpretation: string;
}

// ── v10 Types ──────────────────────────────────────────────

export interface TechnicalAnalysis {
  ticker: string;
  indicators: {
    trend: {
      sma_20: number | null;
      sma_50: number | null;
      sma_200: number | null;
      ema_12: number | null;
      ema_26: number | null;
      price_vs_sma20_pct: number | null;
      price_vs_sma50_pct: number | null;
      price_vs_sma200_pct: number | null;
      macd: number | null;
      macd_signal: number | null;
      macd_histogram: number | null;
      macd_bullish: boolean;
      adx: number | null;
      adx_interpretation: string | null;
      trend_direction: string;
    };
    momentum: {
      rsi_14: number | null;
      rsi_interpretation: string;
      stochastic_k: number | null;
      stochastic_d: number | null;
      stochastic_signal: string;
      williams_r: number | null;
      roc_10: number | null;
    };
    volatility: {
      bollinger_upper: number | null;
      bollinger_lower: number | null;
      bollinger_mid: number | null;
      bollinger_width: number | null;
      bollinger_position: number | null;
      bollinger_signal: string;
      atr_14: number | null;
      atr_pct: number | null;
    };
    volume: {
      obv: number | null;
      obv_trend: string | null;
      acc_dist: number | null;
      force_index_13: number | null;
      avg_volume_20d: number | null;
      latest_volume: number | null;
      volume_ratio: number | null;
      volume_signal: string;
    };
    patterns: {
      golden_death_cross: string | null;
      support_20d: number;
      resistance_20d: number;
      high_52w: number;
      low_52w: number;
      pct_from_52w_high: number | null;
      pct_from_52w_low: number | null;
    };
  };
  signal: {
    score: number;
    sentiment: string;
    confidence: number;
    n_signals: number;
    reasons: string[];
  };
}

export interface ChartPattern {
  type: string;
  direction: "bullish" | "bearish" | "neutral";
  confidence: number;
  status: "confirmed" | "forming";
  target_price?: number;
  neckline?: number;
  pattern_height_pct?: number;
  start_index: number;
  end_index: number;
  start_date?: string;
  end_date?: string;
  breakout_date?: string;
  [key: string]: unknown;
}

export interface SupportResistanceLevel {
  price: number;
  touches: number;
  strength: number;
}

export interface ChartPatternAnalysis {
  ticker: string;
  period: string;
  bars_analyzed: number;
  patterns: ChartPattern[];
  pattern_count: number;
  bullish_patterns: number;
  bearish_patterns: number;
  bias: "bullish" | "bearish" | "neutral";
  strongest_pattern: ChartPattern | null;
  support_resistance: {
    support: SupportResistanceLevel[];
    resistance: SupportResistanceLevel[];
    current_price: number;
  };
}

export interface VolConeBand {
  window_days: number;
  current: number;
  p5: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
  percentile: number;
}

export interface VolTermEntry {
  horizon_days: number;
  realized_vol_pct: number;
}

export interface GarchCurveEntry {
  horizon_days: number;
  forecast_vol_pct: number;
}

export interface VolatilityAnalytics {
  ticker: string;
  vol_cone: Record<string, VolConeBand>;
  term_structure: VolTermEntry[];
  regime: {
    regime: "high" | "normal" | "low" | "unknown";
    percentile: number | null;
    current_30d_vol_pct: number | null;
    interpretation: string;
  };
  estimators?: {
    close_to_close_pct: number;
    parkinson_pct: number;
    garman_klass_pct: number;
    interpretation: string;
  };
  risk_premium?: {
    implied_vol_pct?: number;
    realized_vol_pct: number;
    spread_pct?: number;
    iv_rv_ratio?: number;
    iv_rank?: number;
    interpretation: string;
  };
  clustering: {
    arch_effect: boolean;
    ljung_box_pvalue?: number;
    squared_return_acf1?: number;
    interpretation: string;
  };
  vol_of_vol?: {
    vol_of_vol_pct: number;
    mean_vol_pct: number;
    coefficient_of_variation: number;
    vol_trend: "rising" | "falling" | "stable";
    interpretation: string;
  };
  garch_forecast?: {
    model: string;
    persistence?: number;
    long_run_vol_pct: number;
    current_vol_pct: number;
    curve: GarchCurveEntry[];
    interpretation?: string;
  };
  summary: {
    regime: string;
    current_30d_vol_pct: number | null;
    percentile_vs_history: number | null;
    arch_effect: boolean;
    vol_trend: string | null;
  };
}

export interface DividendIntelligence {
  ticker: string;
  pays_dividend: boolean;
  message?: string;
  current_price?: number | null;
  trailing_yield?: number | null;
  forward_yield?: number | null;
  annual_dividend?: number | null;
  frequency?: string;
  ex_dividend_date?: string | null;
  growth_rates?: {
    cagr_1y?: number;
    cagr_3y?: number;
    cagr_5y?: number;
    cagr_10y?: number;
  };
  payout?: {
    earnings_payout_pct?: number;
    eps_payout_pct?: number;
    fcf_payout_pct?: number;
  };
  consecutive_growth_years?: number;
  classification?: string;
  safety?: {
    score: number | null;
    grade: string;
    components: Record<string, number>;
  };
  ddm?: {
    intrinsic_value: number | null;
    upside_pct: number | null;
    growth_rate_used?: number;
    discount_rate?: number;
    model?: string;
  };
  income_projection?: {
    investment_amount: number;
    shares: number;
    annual_income: number;
    monthly_income: number;
    yield_on_cost: number;
  };
  history?: Array<{ date: string; amount: number }>;
  years_of_data?: number | null;
}

export interface RealtimeSnapshot {
  ticker: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  updated_ts: number | null;
  day?: {
    open: number | null;
    high: number | null;
    low: number | null;
    close: number | null;
    volume: number | null;
    vwap: number | null;
  };
  prev_day?: {
    open: number | null;
    high: number | null;
    low: number | null;
    close: number | null;
    volume: number | null;
    vwap: number | null;
  };
}

export interface SectorRotation {
  sectors: {
    sector: string;
    etf: string;
    returns: Record<string, number | null>;
    relative_strength: Record<string, number>;
    composite_score: number;
    direction: string;
    rank: number;
    volatility_20d: number | null;
  }[];
  leaders: string[];
  laggards: string[];
  breadth: {
    status: string;
    description: string;
    positive_sectors: number;
    total_sectors: number;
    pct_positive: number;
  };
  cycle_phase: {
    phase: string;
    confidence: number;
    description: string;
  };
  rotation_signal: {
    signal: string;
    description: string;
    accelerating: number;
    decelerating: number;
    stable: number;
  };
  n_sectors: number;
}

export interface RiskNumber {
  risk_number: number;
  level: string;
  description: string;
  components: Record<string, {
    value: number;
    unit: string;
    score: number;
    weight: number;
  }>;
}

export interface FixedIncomeDashboard {
  yield_curve: {
    yields: Record<string, number>;
    spreads: Record<string, number | null>;
    curvature: number | null;
    shape: string;
    inversions: string[];
    interpretation: string;
  };
  credit: {
    spreads: Record<string, {
      current: number;
      mean_1y: number | null;
      zscore?: number;
    }>;
    real_yield_10y: number | null;
    breakeven_inflation_10y: number | null;
    stress: { level: string; signals: string[] };
  };
  error?: string;
}

export interface MarketValuation {
  cape: {
    current: number;
    long_run_average: number;
    premium_pct: number;
    percentile: number | null;
    interpretation: string;
  };
  pe: {
    trailing: number | null;
    forward: number | null;
    forward_vs_trailing: number | null;
  };
  equity_risk_premium: {
    erp_pct: number | null;
    earnings_yield: number | null;
    real_yield_10y: number | null;
    interpretation: string;
  };
  dividend_yield: {
    current_pct: number | null;
    historical_avg: number;
    interpretation: string;
  };
  buffett_indicator: {
    ratio_pct: number | null;
    interpretation: string;
  };
  composite_valuation_score: {
    score: number;
    level: string;
  };
}

export interface RelativeValuationMetric {
  value: number | null;
  percentile: number | null;
  valuation_percentile: number | null;
  peer_avg: number | null;
  peer_count: number;
  vs_peers: string;
}

export interface RelativeValuationVerdict {
  label: string;
  color: string;
  description: string;
  composite_score: number;
  historical_note?: string;
}

export interface RelativeValuationPeer {
  ticker: string;
  name: string;
  is_target: boolean;
  pe_trailing: number | null;
  pe_forward: number | null;
  ev_ebitda: number | null;
  price_to_sales: number | null;
  price_to_book: number | null;
  dividend_yield: number | null;
  revenue_growth: number | null;
  profit_margin: number | null;
  market_cap: number | null;
}

export interface RelativeValuation {
  ticker: string;
  sector: string;
  peer_count: number;
  rankings: Record<string, RelativeValuationMetric>;
  composite_score: number;
  score_components: Record<string, { percentile: number; weight: number; contribution: number }>;
  verdict: RelativeValuationVerdict;
  historical: {
    pe_current: number;
    pe_5y_avg: number;
    pe_5y_min: number;
    pe_5y_max: number;
    pe_5y_median: number;
    pe_percentile_vs_history: number;
    ps_current?: number;
    ps_5y_avg?: number;
    pb_current?: number;
    pb_5y_avg?: number;
  } | null;
  peer_table: RelativeValuationPeer[];
}

// Pair Analysis
export interface PairAnalysisResult {
  ticker_a: string;
  ticker_b: string;
  cointegrated: boolean;
  p_value: number;
  half_life: number | null;
  current_zscore: number | null;
  spread_mean: number | null;
  signal: string;
  interpretation: string;
}

export interface PairScanResult {
  pairs: {
    ticker_a: string;
    ticker_b: string;
    p_value: number;
    cointegrated: boolean;
    half_life: number | null;
  }[];
  n_pairs_tested: number;
  n_cointegrated: number;
}

export interface TailRiskResult {
  ticker: string;
  period: string;
  annual_return_pct: number;
  annual_volatility_pct: number;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  omega_ratio: number | null;
  calmar_ratio: number | null;
  downside_deviation_annual: number | null;
  max_drawdown_pct: number | null;
  max_drawdown_duration_days: number | null;
  tail_concentration_pct: number | null;
  gain_pain_ratio: number | null;
  ulcer_index: number | null;
  win_rate_pct: number | null;
  avg_win_pct: number | null;
  avg_loss_pct: number | null;
  profit_factor: number | null;
  n_observations: number;
}

export interface SurvivalModelResult {
  method: string;
  probabilities: Record<string, number>;
  top_risk_factors: { feature: string; coefficient: number; direction: string }[];
  training: { n_train: number; n_events: number; features_used: number };
  interpretation: string;
  last_updated: string;
}

// Cross-Asset Macro Regime Monitor types
export interface MacroRegime {
  quadrant: string;
  description: string;
  favored_assets: string[];
  avoid_assets: string[];
  growth_score: number;
  inflation_score: number;
  regime_stable: boolean | null;
  previous_quadrant: string | null;
  growth_interpretation: string;
  inflation_interpretation: string;
}

export interface CrossAssetDashboard {
  macro_regime: MacroRegime;
  risk_on_off: {
    score: number;
    z_score: number;
    regime: string;
    interpretation: string;
    signals: Record<string, {
      value: number;
      z_score: number;
      signal: string;
    }>;
    n_signals: number;
  };
  momentum_table: {
    ticker: string;
    name: string;
    asset_class: string;
    subclass: string;
    price: number;
    return_1w: number | null;
    return_1m: number | null;
    return_3m: number | null;
    return_6m: number | null;
    return_1y: number | null;
    sma200_ratio: number | null;
    above_sma200: boolean | null;
    vol_30d_ann_pct: number | null;
  }[];
  correlations: {
    available: boolean;
    window_days: number;
    matrix: Record<string, Record<string, number>>;
    key_relationships: Record<string, { correlation: number; historical: number }>;
    divergences: {
      pair: string;
      current_corr: number;
      historical_corr: number;
      divergence: number;
      interpretation: string;
    }[];
    n_assets: number;
  };
  intermarket_divergences: {
    type: string;
    severity: string;
    message: string;
  }[];
  breadth: {
    breadth_score: number;
    uptrend_count: number;
    total_assets: number;
    interpretation: string;
    by_class: Record<string, { uptrend_pct: number; detail: { ticker: string; uptrend: boolean }[] }>;
  };
  macro_weather: {
    condition: string;
    summary: string;
    quadrant: string;
    risk_regime: string;
    roro_score: number;
    n_divergence_alerts: number;
  };
  n_assets_tracked: number;
  asset_classes: string[];
}

// ── Portfolio Intelligence ──────────────────────────────────

export interface PIMetricPack {
  total_return: number;
  annualized_return: number;
  annualized_volatility: number;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  max_drawdown: number;
  max_drawdown_duration_days: number | null;
  beta_vs_spy?: number | null;
  tracking_error_vs_spy?: number | null;
  information_ratio_vs_spy?: number | null;
  sector_exposure?: Record<string, number>;
  factor_exposure?: Record<string, number>;
}

export interface PIRiskFlag {
  flag_type: string;
  severity: "info" | "warning" | "critical";
  message: string;
  details: Record<string, unknown>;
}

export interface PIRebalanceEventLatest {
  id: number;
  portfolio_id: string;
  triggered_at: string;
  trigger_reason: string;
  pre_weights: Record<string, number>;
  post_weights: Record<string, number>;
  crash_prob_3m: number | null;
  regime: string | null;
  explanation: string;
}

export interface PISnapshotResponse {
  portfolio_id: string;
  date: string;
  weights: Record<string, number>;
  metrics: PIMetricPack | null;
  flags: PIRiskFlag[];
  latest_rebalance: PIRebalanceEventLatest | null;
}

export interface PIRebalanceEvent {
  date: string;
  reason: string;
  turnover: number;
  cost: number;
  crash_prob: number | null;
  overlay_armed: boolean;
  n_trades: number;
  portfolio_value: number;
}

export interface PIEquityCurvePoint {
  date: string;
  value: number;
}

export interface PIReplayResult {
  lane: string;
  start_date: string;
  end_date: string;
  equity_curve: PIEquityCurvePoint[];
  metrics: PIMetricPack | null;
  rebalance_log: PIRebalanceEvent[];
  crash_guard_activations: number;
  total_rebalances: number;
  total_turnover: number;
  total_cost_bps: number;
}

export interface PICompareResponse {
  lanes: Record<string, PIMetricPack | null>;
  benchmarks: Record<string, PIMetricPack | null>;
  period: string;
  start_date: string | null;
  end_date: string | null;
}

export interface PIHistoryRebalanceEntry {
  date: string;
  reason: string;
  crash_prob: number | null;
  overlay_armed: boolean;
  explanation: string;
}

export interface PIHistoryResponse {
  portfolio_id: string;
  period: string;
  equity_curve: PIEquityCurvePoint[];
  rebalance_log: PIHistoryRebalanceEntry[];
  has_rebalance_events: boolean;
}

export interface PIExplainResponse {
  portfolio_id: string;
  explanation: string;
  last_rebalance_date: string | null;
  has_rebalance_events: boolean;
}

// PI: Real portfolio analyze
export function piAnalyzePortfolio(holdings: Holding[]) {
  return fetchAPI<PISnapshotResponse>("/api/pi/real-portfolio/analyze", {
    method: "POST",
    body: JSON.stringify({ holdings }),
  });
}

// PI: Reference lane state
export function piGetReferenceState(laneId: string) {
  return fetchAPI<PISnapshotResponse>(`/api/pi/reference/${laneId}/state`);
}

// PI: Reference lane history
export function piGetReferenceHistory(laneId: string, period: string = "1Y") {
  return fetchAPI<PIHistoryResponse>(
    `/api/pi/reference/${laneId}/history?period=${encodeURIComponent(period)}`,
  );
}

// PI: Reference lane explanation
export function piGetReferenceExplain(laneId: string) {
  return fetchAPI<PIExplainResponse>(`/api/pi/reference/${laneId}/explain`);
}

// PI: Compare all lanes
export function piGetCompare(
  ids: string[] = ["conservative", "balanced", "aggressive"],
  period: string = "1Y",
) {
  const idsParam = encodeURIComponent(ids.join(","));
  return fetchAPI<PICompareResponse>(
    `/api/pi/compare?ids=${idsParam}&period=${encodeURIComponent(period)}`,
  );
}

// PI: Live forward track record (the canonical performance record)
export interface PITrackRecordPoint {
  date: string;
  value: number;
  config_version: string | null;
}

export interface PITrackRecordResponse {
  inception_date: string | null;
  age_days: number | null;
  expected_nav_date: string | null;
  all_fresh: boolean;
  intraday_date: string | null;
  lanes: Record<string, PITrackRecordPoint[]>;
  benchmarks: Record<string, PITrackRecordPoint[]>;
  benchmark_note: string;
}

export function piGetTrackRecord() {
  return fetchAPI<PITrackRecordResponse>("/api/pi/track-record");
}

// PI: Experiment registry (every trial ever recorded, adopted AND rejected)
export interface PIRegistryTrial {
  id: number;
  created_at: string;
  config_version: string | null;
  lane_id: string | null;
  param: string;
  verdict: string;
  cumulative_trials: number;
  notes: Record<string, unknown> | string | null;
}

export interface PIRegistryResponse {
  cumulative_trials: number;
  verdict_counts: Record<string, number>;
  trials: PIRegistryTrial[];
}

export function piGetRegistry() {
  return fetchAPI<PIRegistryResponse>("/api/pi/registry");
}

// Dev: full health snapshot (deploy, scheduler, NAV freshness, warnings, LLM)
export interface HealthFullResponse {
  status: string;
  deploy: {
    commit: string;
    version: string;
    started_at: string;
    uptime_seconds: number;
    cache_status: string;
  };
  scheduler: {
    running: boolean;
    n_jobs: number;
    nav?: { all_fresh: boolean; expected_nav_date?: string };
  };
  track_record: {
    inception_date: string | null;
    age_days: number | null;
    lanes: Record<string, { last_date: string | null; nav: number | null; since_inception_pct: number | null }>;
  };
  llm?: {
    provider: string;
    calls_today: number;
    daily_cap: number;
    breaker_active: boolean;
  };
  recent_warnings: { ts: string; level: string; logger: string; message: string }[];
}

export function getHealthFull() {
  return fetchAPI<HealthFullResponse>("/api/health/full");
}

// PI: Replay backtest (forces compute on cache miss — slow)
export function piGetReplay(laneId: string) {
  return fetchAPI<PIReplayResult>(`/api/pi/replay/${laneId}`);
}

// PI: Replay snapshot (fast read of SQLite cache, never recomputes)
export interface PIReplaySnapshot {
  lane_id: string;
  status: "cached" | "stale" | "missing";
  cached_at: string | null;
  fresh: boolean;
  result: PIReplayResult | null;
}

export function piGetReplaySnapshot(laneId: string) {
  return fetchAPI<PIReplaySnapshot>(`/api/pi/reference/${laneId}/snapshot`);
}

// PI: Force a fresh walk-forward replay (slow, invalidates cache)
export function piRefreshReplay(laneId: string) {
  return fetchAPI<PIReplayResult>(`/api/pi/replay/${laneId}/refresh`, {
    method: "POST",
  });
}

// PI: Manual trigger
export function piTriggerCheck(laneId?: string) {
  const params = laneId ? `?lane=${laneId}` : "";
  return fetchAPI<Record<string, unknown>>(`/api/pi/trigger-check${params}`, {
    method: "POST",
  });
}

// PI: Conviction lane — decision capture (immutable, forward-only log)
export interface ConvictionDecisionRequest {
  ticker: string;
  action: "enter" | "add" | "trim" | "exit";
  shares_delta: number;
  price: number;
  rationale: string; // >= 50 chars (honest-record discipline)
  conviction: number; // 1-5
  thesis_tags?: string[];
  target_price?: number | null;
  stop_price?: number | null;
  planned_exit_trigger?: string | null;
  catalyst_dates?: string[];
  late_entry?: boolean;
}

export interface ConvictionDecisionRow {
  id: number;
  timestamp: string;
  ticker: string;
  action: string;
  shares_delta: number;
  price: number;
  rationale: string;
  thesis_tags: string[] | null;
  conviction: number;
  target_price: number | null;
  stop_price: number | null;
  planned_exit_trigger: string | null;
  late_entry: number | boolean;
  amends_id: number | null;
}

export function piLogConvictionDecision(body: ConvictionDecisionRequest) {
  return fetchAPI<{ id: number; timestamp: string; late_entry: boolean }>(
    "/api/pi/conviction/decision",
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function piGetConvictionDecisions(limit = 100) {
  return fetchAPI<{ decisions: ConvictionDecisionRow[] }>(
    `/api/pi/conviction/decisions?limit=${limit}`,
  );
}

// PI: Risk Watch — persisted fragility + candidates + alerts in one fast read
export interface RiskWatchResponse {
  fragility: {
    status?: string;
    composite?: number | null;
    level?: string;
    n_inputs?: number;
    evaluated_at?: string;
    components?: Record<string, number | null>;
    label?: string;
  };
  candidate_readings: Record<
    string,
    { status: string; value: number | null; as_of?: string; label: string }
  >;
  alerts: {
    id: number;
    created_at: string;
    rule: string;
    subject: string;
    state: string;
    message: string;
  }[];
  disclaimer: string;
}

export function piGetRiskWatch() {
  return fetchAPI<RiskWatchResponse>("/api/pi/risk-watch");
}
