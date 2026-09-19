import { DailyPlanItem } from '../core/models';
import {
  EMPTY_LIST_COPY,
  blockReasonCopy,
  currentPhase,
  formatUtcDate,
  formatUtcTime,
  groupChecklist,
  itemKind,
  itemLabel,
  levelRows,
  listEntries,
  phaseLabel,
  remainingRisk,
  reviewCopy,
  volumeCopy,
} from './session-plan.util';

describe('session-plan helpers', () => {
  it('maps snake_case phases to operator labels', () => {
    expect(phaseLabel('session_open_utc')).toBe('Open');
    expect(phaseLabel('intraday')).toBe('Intraday');
    expect(phaseLabel('session_close_utc')).toBe('Close');
  });

  it('maps checklist items to short labels and kinds', () => {
    expect(itemLabel('economic / protocol calendar')).toBe('Calendar');
    expect(itemKind('major price levels')).toBe('levels');
    expect(itemKind('risk limits remaining')).toBe('remaining');
  });

  it('rewrites venue_stale into operator copy', () => {
    expect(blockReasonCopy('venue_stale')).toContain('Market data is stale');
    expect(blockReasonCopy('halted')).toBe('halted');
    expect(blockReasonCopy(null)).toBe('Trading is paused.');
  });

  it('treats none listed arrays as empty', () => {
    expect(listEntries(['none listed'])).toEqual([]);
    expect(listEntries(['FOMC', 'none listed'])).toEqual(['FOMC']);
    expect(listEntries([])).toEqual([]);
  });

  it('picks only level fields from an indicator snapshot', () => {
    const rows = levelRows({
      close: '2410',
      swing_high: '2480',
      swing_low: '2360',
      ema_fast: '2401.5214929133109',
      ema_slow: '2388',
      rsi_14: '61',
      volume_z_20: '1.2',
    });
    expect(rows.map((row) => row.label)).toEqual([
      'close',
      'swing high',
      'swing low',
      'EMA fast',
      'EMA slow',
    ]);
    expect(rows.find((row) => row.label === 'EMA fast')?.value).toBe('2401.52');
    expect(rows.some((row) => row.label === 'rsi_14')).toBe(false);
  });

  it('rounds long volume z-scores', () => {
    expect(volumeCopy('1.9221978840914961')).toBe('z 1.92');
  });

  it('formats remaining risk as labeled metrics', () => {
    expect(
      remainingRisk({
        remaining_daily_loss: '1000',
        remaining_drawdown: '2000',
        remaining_orders_today: 8,
      }),
    ).toEqual([
      { label: 'Daily loss', value: '1000' },
      { label: 'Drawdown', value: '2000' },
      { label: 'Orders', value: '8' },
    ]);
  });

  it('formats volume and review copy', () => {
    expect(volumeCopy('unknown')).toBe('z unknown');
    expect(volumeCopy('1.4')).toBe('z 1.40');
    expect(reviewCopy('journal fills vs thesis')).toBe('Journal fills against the thesis');
  });

  it('groups checklist rows in session order', () => {
    const items: DailyPlanItem[] = [
      { phase: 'intraday', item: 'watchlist', value: ['ETHUSD'] },
      { phase: 'session_close_utc', item: 'end-of-day review', value: 'journal fills vs thesis' },
      { phase: 'session_open_utc', item: 'unusual volume', value: 'unknown' },
    ];
    expect(groupChecklist(items).map((phase) => phase.label)).toEqual(['Open', 'Intraday', 'Close']);
  });

  it('highlights the UTC phase from as_of', () => {
    expect(currentPhase('2026-09-19T03:00:00+00:00')).toBe('session_open_utc');
    expect(currentPhase('2026-09-19T12:00:00+00:00')).toBe('intraday');
    expect(currentPhase('2026-09-19T21:15:00+00:00')).toBe('session_close_utc');
  });

  it('formats UTC dates without leaking ISO strings', () => {
    const date = formatUtcDate('2026-09-19T00:00:00+00:00');
    const time = formatUtcTime('2026-09-19T14:32:00+00:00');
    expect(date).not.toContain('T');
    expect(date).toContain('2026');
    expect(time).toMatch(/14:32/);
    expect(EMPTY_LIST_COPY).toBe('None listed');
  });
});
