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

// Savings
export function projectSavings(params: SavingsRequest) {
  return fetchAPI<SavingsProjection>("/api/savings/project", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// Portfolio projection
export function projectPortfolio(holdings: Holding[], years = 1, monthlyAdd = 0) {
  return fetchAPI<PortfolioProjection>("/api/portfolio/project", {
    method: "POST",
    body: JSON.stringify({ holdings, years, monthly_add: monthlyAdd }),
  });
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

export interface ShapExplanation {
  ticker?: string;
  crash_prob: number;
  horizon: string;
  top_features: { feature: string; shap_value: number; feature_value: number | null }[];
  status?: string;
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
