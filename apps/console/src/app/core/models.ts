export type AgentStatus = 'running' | 'stopped' | 'halted';
export type VenueStatus = 'connected' | 'stale' | 'down';
export type TradingMode = 'paper' | 'live';

export interface BrokerMonitorSnapshot {
  status: 'not_configured' | 'polling' | 'error';
  polled_at: string | null;
  positions: Record<string, string>;
  open_client_order_ids: string[];
  last_price: Record<string, string>;
  error: string | null;
  mode: 'monitor';
}

export interface HealthResponse {
  agent: AgentStatus;
  venue: VenueStatus;
  llm: 'up' | 'down';
  research: 'up' | 'down';
  ollama: 'up' | 'down';
  trading_mode: TradingMode;
  heartbeat_age_s: number | null;
  last_bar_at: string | null;
  last_bar_instrument: string | null;
  reconciliation: 'ok' | 'mismatch' | 'unknown';
  halt_reason: string | null;
  live_actions_blocked: boolean;
  broker_monitor: BrokerMonitorSnapshot;
}

export interface PortfolioResponse {
  equity: string;
  cash: string;
  realized_pnl: string;
  unrealized_pnl: string;
  drawdown: string;
  peak_equity: string;
  exposure_per_instrument: Record<string, string>;
  exposure_per_asset_class: Record<string, string>;
  orders_today: number;
  starting_cash: string;
  incomplete: boolean;
  as_of: string | null;
}

export type MarketDataStatus = 'ok' | 'stale' | 'research_only' | 'no_adapter' | 'data_unavailable';

export interface MarketInstrument {
  symbol: string;
  venue: string;
  asset_class: string;
  price: string | null;
  change_pct: string | null;
  volume: string | null;
  volatility: string | null;
  spread: string | null;
  as_of: string | null;
  stale: boolean;
  in_universe: boolean;
  status: MarketDataStatus;
}

export interface BarPoint {
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  ema_fast: string | null;
  ema_slow: string | null;
}

export interface BarsResponse {
  symbol: string;
  timeframe: string;
  bars: BarPoint[];
  stale: boolean;
}

export interface SignalResponse {
  symbol: string;
  source: 'ema_cross' | 'llm' | 'none';
  direction: string | null;
  confidence: number | null;
  rationale: string | null;
  as_of: string | null;
  sources: string[];
  is_proposal: boolean;
}

export interface PositionRow {
  instrument: string;
  quantity: string;
  entry_price: string | null;
  last_price: string | null;
  unrealized_pnl: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  stop_source: string;
}

export interface OrderRow {
  correlation_id: string;
  client_order_id: string | null;
  instrument: string;
  side: string | null;
  quantity: string | null;
  status: string;
  fill_price: string | null;
  filled_quantity: string | null;
  fee: string | null;
  slippage: string | null;
  timestamp: string;
  reason: string | null;
  trading_mode: TradingMode;
}

export interface PendingApproval {
  correlation_id: string;
  requested_at: string;
  expires_at: string;
  remaining_s: number;
  instrument: string;
  side: string;
  quantity: string;
  reject_reason: string | null;
  requires_human_approval: boolean;
  estimated_notional: string | null;
  last_price: string | null;
  rationale: string | null;
  stale: boolean;
  trading_mode: TradingMode;
  approve_blocked_reason: string | null;
}

export interface CircuitBreakerView {
  max_consecutive_errors: number;
  max_consecutive_losses: number;
  halt_on_unknown_order_result: boolean;
  state: 'RUNNING' | 'HALTED';
}

export interface RiskLimitsView {
  max_notional_per_order: string;
  max_exposure_per_instrument: string;
  max_exposure_per_asset_class: string;
  max_daily_loss: string;
  max_drawdown: string;
  max_orders_per_day: number;
  circuit_breaker: CircuitBreakerView;
  consumed_daily_loss: string;
  remaining_daily_loss: string;
  consumed_drawdown: string;
  remaining_drawdown: string;
  consumed_orders_today: number;
  remaining_orders_today: number;
  restart_required_on_write: boolean;
}

export interface AgentEventRow {
  id: number;
  timestamp: string;
  correlation_id: string;
  event_type: string;
  payload: Record<string, unknown>;
}

export interface ResearchDocumentView {
  doc_id: string;
  url: string;
  title: string;
  source_id: string;
  published_at: string | null;
  fetched_at: string;
  event_date: string | null;
  assets_mentioned: string[];
  category: string;
  summary: string | null;
  sentiment_score: number | null;
  impact_magnitude: string | null;
  impact_direction: string | null;
  confidence_score: number;
  stale: boolean;
  contradicts: string[];
  extracted_text: string;
}

export interface DiscoveryCandidateFactors {
  notional_volume_24h_usd: string;
  spread_bps: number;
  liquidity_score: number;
  spread_score: number;
  volatility: number | null;
  data_quality_score: number;
  operational_risk_score: number;
  correlation_btc: number | null;
  correlation_eth: number | null;
  min_order_notional_usd: string | null;
  listing_age_days: number;
  exchange_status: string;
}

export interface DiscoveryCandidateSource {
  source_id: string;
  url: string;
  fetched_at: string;
}

export interface DiscoveryCandidate {
  id: string;
  asset: string;
  asset_class: string;
  exchange: string;
  timestamp: string;
  research_horizon: string;
  candidate_status: string;
  opportunity_score: number;
  risk_score: number;
  confidence_score: number;
  data_quality_score: number;
  factors: DiscoveryCandidateFactors;
  bullish_case: string[];
  bearish_case: string[];
  neutral_case: string[];
  invalidation_conditions: string[];
  missing_data: string[];
  sources: DiscoveryCandidateSource[];
  expires_at: string;
  requires_human_review: boolean;
  composite_rank: number;
}

export interface SecuritySettings {
  environment: string;
  trading_mode: TradingMode;
  live_trading_enabled: boolean;
  broker_paper_mode: boolean;
  kraken_spot_key_present: boolean;
  kraken_spot_secret_present: boolean;
  withdraw_enabled: boolean;
  ip_whitelist_configured: boolean;
  subaccount: boolean;
  operator_role: 'operator' | 'observer';
  data_retention: string;
  webhooks_configured: boolean;
  notifications_configured: boolean;
}

export type StrategyKind = 'ema_cross' | 'donchian_breakout' | 'rsi_mean_reversion' | 'llm';
export type StrategyStatusLabel = 'experimental' | 'testing' | 'paper_candidate' | 'disabled';

export interface StrategyRow {
  id: string;
  name: string;
  kind: StrategyKind;
  enabled: boolean;
  params: Record<string, string>;
  status: StrategyStatusLabel;
  version: number;
  hypothesis: string;
  supported_assets: string[];
  supported_timeframes: string[];
  last_paper_sessions: number | null;
  last_paper_halted: boolean | null;
  last_backtest_ref: string | null;
}

export interface PerformanceMetrics {
  n_bars: number;
  n_trades: number;
  starting_equity: string;
  ending_equity: string;
  total_return_pct: string;
  annualized_return_pct: string | null;
  volatility_pct: string | null;
  sharpe_ratio: string | null;
  sortino_ratio: string | null;
  calmar_ratio: string | null;
  max_drawdown_pct: string;
  recovery_factor: string | null;
  win_rate: string | null;
  avg_win: string | null;
  avg_loss: string | null;
  expectancy: string | null;
  profit_factor: string | null;
  longest_losing_streak: number;
  turnover: string;
  turnover_ratio: string | null;
  total_fees: string;
  estimated_slippage: string;
  avg_exposure_pct: string | null;
  warnings: string[];
}

export interface BaselineComparison {
  buy_and_hold_pct: string | null;
  cash_pct: string;
  random_control_pct: string | null;
}

export interface RegimeBucketMetrics {
  n_bars: number;
  bar_win_rate: string | null;
  cumulative_return_pct: string;
}

export type RegimeBreakdown = Record<string, Record<string, RegimeBucketMetrics>>;

export interface EquityCurvePoint {
  t: string;
  equity: string;
  exposure: string;
}

export interface DrawdownCurvePoint {
  t: string;
  drawdown_pct: string;
}

export interface BuyHoldCurvePoint {
  t: string;
  equity: string;
}

export interface BacktestComparableMetrics {
  strategy: string;
  cost_multiplier: number;
  dataset_hash: string;
  n_bars: number;
  n_fills: number;
  n_decisions: number;
  ending_usdt: string;
  commissions_usdt: string;
  decisions: string[];
}

export interface BacktestExtraMetrics {
  performance: PerformanceMetrics;
  baselines: BaselineComparison;
  regime: RegimeBreakdown;
  equity_curve: EquityCurvePoint[];
  drawdown_curve: DrawdownCurvePoint[];
  buy_and_hold_curve: BuyHoldCurvePoint[];
  trade_pnls: string[];
}

export type BacktestJobStatus = 'queued' | 'running' | 'done' | 'error';

export interface BacktestJobRow {
  run_id: string;
  strategy_id: string;
  status: BacktestJobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  request: {
    strategy_kind: string;
    strategy_params: Record<string, unknown>;
    universe_symbol: string;
    timeframe: string;
    start: string;
    end: string;
    cost_multiplier: number;
  };
  metrics: { comparable: BacktestComparableMetrics; extra: BacktestExtraMetrics } | null;
}

export interface BacktestRunRequestBody {
  universe_symbol: string;
  timeframe: string;
  start: string;
  end: string;
  cost_multiplier: 1 | 2 | 3;
  confirmation_token: string;
}

export interface StrategyVersionRow {
  id: string;
  name: string;
  kind: string;
  enabled: boolean;
  status: StrategyStatusLabel;
  version: number;
  hypothesis: string;
  supported_assets: string[];
  supported_timeframes: string[];
  params: Record<string, unknown>;
  updated_at: string;
  change_note: string;
}

export interface AlertRow {
  id: string;
  severity: 'warning' | 'error';
  title: string;
  detail: string;
  persistent: boolean;
}

export type AnalysisType = 'priced_in' | 'technical' | 'news_impact' | 'daily_plan';

export interface IndicatorSnapshot {
  timeframe: string;
  bar_count: number;
  instrument?: string;
  as_of: string;
  open?: string;
  high?: string;
  low?: string;
  close: string;
  volume?: string;
  ema_fast: string;
  ema_slow: string;
  rsi_14: string;
  atr_14: string;
  volume_z_20: string;
  swing_high: string;
  swing_low: string;
  funding: string;
  open_interest: string;
}

export interface IndicatorsResponse {
  symbol: string;
  timeframe: string;
  snapshot: IndicatorSnapshot;
  is_order: false;
}

export interface StressScenario {
  name: string;
  spot_shock: string;
  estimated_pnl: string;
  estimated_equity_change_pct: string;
}

export interface StressConcentration {
  instrument: string;
  notional: string;
  weight: string;
}

export interface StressReport {
  total_exposure: string;
  hhi: string;
  duplicated_bets: string;
  concentration: StressConcentration[];
  scenarios: StressScenario[];
  hedge_universe: string;
  options_available: boolean;
  note: string;
  as_of: string | null;
  incomplete: boolean;
  is_order: false;
}

export interface DailyPlanItem {
  phase: string;
  item: string;
  value: unknown;
}

export interface DailyPlan {
  instrument: string;
  session_start_utc: string;
  as_of: string;
  checklist: DailyPlanItem[];
  blocks_trading: boolean;
  block_reason: string | null;
  is_order: false;
}

export interface AnalysisDataSource {
  url: string;
  as_of?: string | null;
  content_hash?: string | null;
}

export interface ParsedAnalysis {
  asset: string;
  timestamp: string;
  timeframe: string;
  analysis_type: string;
  factual_summary: string;
  data_sources: AnalysisDataSource[];
  bullish_case: string;
  bearish_case: string;
  neutral_case: string;
  key_assumptions: string[];
  catalysts: string[];
  risks: string[];
  invalidation_conditions: string[];
  confidence_score: number;
  data_quality_score: number;
  uncertainty: string;
  recommended_action: string;
  action_type: string;
  position_size_suggestion: null;
  required_human_approval: boolean;
  expiry_time: string;
  audit_metadata: {
    model_name: string;
    prompt_hash: string;
    facts_bundle_hash: string;
    temperature: number;
    schema_version: string;
  };
}

export interface AnalysisRunResponse {
  is_order: false;
  facts_bundle: Record<string, unknown>;
  analysis: ParsedAnalysis | null;
  rejected: { reason: string; raw_output: string } | null;
}

export interface StoredAnalysis {
  timestamp: string;
  correlation_id: string;
  instrument: string;
  analysis_type: string;
  is_order: boolean;
  result: Record<string, unknown>;
}

export interface AckResponse {
  ok: boolean;
  detail: string;
  restart_required: boolean;
}

export interface WsEnvelope {
  channel: 'health' | 'approvals' | 'alerts' | 'events';
  payload: Record<string, unknown>;
  sent_at: string;
}

export function pnlClass(value: string | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) {
    return 'pnl-zero';
  }
  return n > 0 ? 'pnl-pos' : 'pnl-neg';
}

export interface FormatQuoteOptions {
  /** Fixed decimal places. Omit to scale with magnitude (2 for >=1, more for small crypto prices). */
  decimals?: number;
  /** Optional unit/currency suffix appended after the number, e.g. 'USD'. */
  currency?: string | null;
}

/**
 * Formats a raw numeric string/number from the local engine into a short,
 * locale-aware display value. Never renders unrounded floats
 * (e.g. `5.357063999999999999999999906`) or blows up on `NaN`/`null`.
 */
export function formatQuote(value: string | number | null | undefined, options: FormatQuoteOptions = {}): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) {
    return '—';
  }
  const decimals = options.decimals ?? quoteDecimals(n);
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(n);
  return options.currency ? `${formatted} ${options.currency}` : formatted;
}

function quoteDecimals(n: number): number {
  const abs = Math.abs(n);
  if (abs === 0 || abs >= 1) {
    return 2;
  }
  if (abs >= 0.01) {
    return 4;
  }
  return 6;
}

export function isNarrowViewport(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < 768;
}
