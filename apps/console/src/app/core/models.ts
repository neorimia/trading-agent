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

export interface StrategyRow {
  id: string;
  name: string;
  kind: 'ema_cross' | 'llm';
  enabled: boolean;
  params: Record<string, string>;
  last_paper_sessions: number | null;
  last_paper_halted: boolean | null;
  last_backtest_ref: string | null;
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

export function isNarrowViewport(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < 768;
}
