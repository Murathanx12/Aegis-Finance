const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
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
  return fetchAPI<StockAnalysis>(`/api/stock/${ticker}`);
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
  });
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
  return fetchAPI<StockSignal>(`/api/stock/${ticker}/signal`);
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

// ── Types ──────────────────────────────────────────────────

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
  months: { month: number; date: string; crash_prob: number }[];
  methodology: string;
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
