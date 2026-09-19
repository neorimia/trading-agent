import { DailyPlanItem } from '../core/models';

export type PlanStatus = 'loading' | 'ready' | 'error';

export type SessionPhaseId = 'session_open_utc' | 'intraday' | 'session_close_utc';

export type SessionItemKind =
  | 'list'
  | 'levels'
  | 'volume'
  | 'watchlist'
  | 'scenarios'
  | 'remaining'
  | 'review'
  | 'text';

export interface SessionPhase {
  id: string;
  label: string;
  items: DailyPlanItem[];
}

export interface LabeledValue {
  label: string;
  value: string;
}

export const PHASE_ORDER: readonly SessionPhaseId[] = [
  'session_open_utc',
  'intraday',
  'session_close_utc',
];

export const EMPTY_LIST_COPY = 'None listed';

const PHASE_LABELS: Record<SessionPhaseId, string> = {
  session_open_utc: 'Open',
  intraday: 'Intraday',
  session_close_utc: 'Close',
};

const ITEM_LABELS: Record<string, string> = {
  'pre-session news and catalysts': 'News',
  'economic / protocol calendar': 'Calendar',
  'major price levels': 'Levels',
  'unusual volume': 'Volume',
  watchlist: 'Watchlist',
  'session scenarios': 'Scenarios',
  'risk limits remaining': 'Remaining',
  'end-of-day review': 'Review',
};

const LEVEL_KEYS: { key: string; label: string }[] = [
  { key: 'close', label: 'close' },
  { key: 'swing_high', label: 'swing high' },
  { key: 'swing_low', label: 'swing low' },
  { key: 'ema_fast', label: 'EMA fast' },
  { key: 'ema_slow', label: 'EMA slow' },
];

const RISK_KEYS: { key: string; label: string }[] = [
  { key: 'remaining_daily_loss', label: 'Daily loss' },
  { key: 'remaining_drawdown', label: 'Drawdown' },
  { key: 'remaining_orders_today', label: 'Orders' },
];

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase as SessionPhaseId] ?? phase.replaceAll('_', ' ');
}

export function itemLabel(item: string): string {
  return ITEM_LABELS[item] ?? item;
}

export function itemKind(item: string): SessionItemKind {
  switch (item) {
    case 'pre-session news and catalysts':
    case 'economic / protocol calendar':
      return 'list';
    case 'major price levels':
      return 'levels';
    case 'unusual volume':
      return 'volume';
    case 'watchlist':
      return 'watchlist';
    case 'session scenarios':
      return 'scenarios';
    case 'risk limits remaining':
      return 'remaining';
    case 'end-of-day review':
      return 'review';
    default:
      return 'text';
  }
}

export function blockReasonCopy(reason: string | null | undefined): string {
  if (reason === 'venue_stale') {
    return 'Market data is stale. Trading stays paused until the venue reconnects.';
  }
  return reason || 'Trading is paused.';
}

export function listEntries(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : value == null ? [] : [value];
  return raw.map((entry) => String(entry)).filter((entry) => entry && entry !== 'none listed');
}

export function levelRows(value: unknown): LabeledValue[] {
  if (!isRecord(value)) {
    return [];
  }
  return LEVEL_KEYS.flatMap(({ key, label }) => {
    const raw = value[key];
    if (raw == null || raw === '') {
      return [];
    }
    return [{ label, value: formatNumberish(raw) }];
  });
}

export function remainingRisk(value: unknown): LabeledValue[] {
  if (!isRecord(value)) {
    return [];
  }
  return RISK_KEYS.flatMap(({ key, label }) => {
    const raw = value[key];
    if (raw == null || raw === '') {
      return [];
    }
    return [{ label, value: String(raw) }];
  });
}

export function volumeCopy(value: unknown): string {
  if (value == null || value === '' || value === 'unknown') {
    return 'z unknown';
  }
  return `z ${formatNumberish(value)}`;
}

export function reviewCopy(value: unknown): string {
  if (value === 'journal fills vs thesis') {
    return 'Journal fills against the thesis';
  }
  return scalarText(value);
}

export function scalarText(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return '';
}

export function groupChecklist(items: DailyPlanItem[]): SessionPhase[] {
  const byPhase = new Map<string, DailyPlanItem[]>();
  for (const item of items) {
    const rows = byPhase.get(item.phase) ?? [];
    rows.push(item);
    byPhase.set(item.phase, rows);
  }
  const known = PHASE_ORDER.filter((phase) => byPhase.has(phase));
  const extras = [...byPhase.keys()].filter(
    (phase) => !PHASE_ORDER.includes(phase as SessionPhaseId),
  );
  return [...known, ...extras].map((id) => ({
    id,
    label: phaseLabel(id),
    items: byPhase.get(id) ?? [],
  }));
}

/** UTC hour 00-07 open, 08-19 intraday, 20-23 close. */
export function currentPhase(asOfIso: string): SessionPhaseId {
  const moment = new Date(asOfIso);
  if (Number.isNaN(moment.getTime())) {
    return 'intraday';
  }
  const hour = moment.getUTCHours();
  if (hour < 8) {
    return 'session_open_utc';
  }
  if (hour >= 20) {
    return 'session_close_utc';
  }
  return 'intraday';
}

export function formatUtcDate(iso: string): string {
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(moment);
}

export function formatNumberish(value: unknown): string {
  const raw = String(value);
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    return raw;
  }
  if (Number.isInteger(n)) {
    return String(n);
  }
  if (Math.abs(n) >= 1) {
    return n.toFixed(2);
  }
  return String(Number(n.toPrecision(4)));
}

export function formatUtcTime(iso: string): string {
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(moment);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
