import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { providePrimeNG } from 'primeng/config';

import { ConsolePreset } from '../core/console.preset';
import { StrategyRow } from '../core/models';
import { StrategiesPage } from './strategies.page';

const BASELINE: StrategyRow = {
  id: 'baseline_ema_cross',
  name: 'EMA trend filter',
  kind: 'ema_cross',
  enabled: true,
  params: { fast_ema_period: '10', slow_ema_period: '20' },
  status: 'experimental',
  version: 1,
  hypothesis: 'Trend persists long enough to beat Kraken costs.',
  supported_assets: ['ETHUSD', 'BTCUSD'],
  supported_timeframes: ['1h', '1d'],
  last_paper_sessions: 0,
  last_paper_halted: false,
  last_backtest_ref: null,
};

const DONCHIAN: StrategyRow = {
  ...BASELINE,
  id: 'donchian_breakout',
  name: 'Donchian breakout + volume',
  kind: 'donchian_breakout',
  enabled: false,
  params: {},
};

describe('StrategiesPage', () => {
  let fixture: ComponentFixture<StrategiesPage>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [StrategiesPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        providePrimeNG({
          theme: { preset: ConsolePreset, options: { darkModeSelector: '.theme-dark' } },
          ripple: false,
        }),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(StrategiesPage);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    // Destroy first so ngOnDestroy clears any pending setInterval poll started by a
    // backtest test — otherwise it could fire against a torn-down TestBed later.
    fixture.destroy();
    http.verify();
  });

  function flushList(): void {
    fixture.detectChanges();
    http.expectOne('/v1/strategies').flush([BASELINE, DONCHIAN]);
    http.expectOne('/v1/strategies/baseline_ema_cross/versions').flush([]);
    http.expectOne('/v1/strategies/baseline_ema_cross/backtests').flush([]);
    fixture.detectChanges();
  }

  it('renders both strategies and auto-selects the first row', () => {
    flushList();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('EMA trend filter');
    expect(el.textContent).toContain('Donchian breakout + volume');
    expect(fixture.componentInstance.selected()?.id).toBe('baseline_ema_cross');
    expect(el.textContent).toContain('Trend persists long enough to beat Kraken costs.');
  });

  it('does not mutate anything just by rendering (no strategy toggle/version/clone/backtest calls)', () => {
    flushList();
    // afterEach's http.verify() is the real assertion here — flushList() only expects the
    // three read-only GETs, so any stray mutating request would fail the test immediately.
    expect(fixture.componentInstance.rows().length).toBe(2);
  });

  it('selecting a different strategy loads its versions and backtests', () => {
    flushList();
    fixture.componentInstance.selectStrategy(DONCHIAN);
    fixture.detectChanges();
    http.expectOne('/v1/strategies/donchian_breakout/versions').flush([
      {
        id: 'donchian_breakout',
        name: 'Donchian breakout + volume',
        kind: 'donchian_breakout',
        enabled: false,
        status: 'experimental',
        version: 1,
        hypothesis: '',
        supported_assets: ['ETHUSD'],
        supported_timeframes: ['1d'],
        params: {},
        updated_at: '2026-01-01T00:00:00Z',
        change_note: 'seed',
      },
    ]);
    http.expectOne('/v1/strategies/donchian_breakout/backtests').flush([]);
    fixture.detectChanges();
    expect(fixture.componentInstance.selected()?.id).toBe('donchian_breakout');
    expect(fixture.componentInstance.versions().length).toBe(1);
  });

  it('toggle dialog requires the exact confirmation token before writing', () => {
    flushList();
    const component = fixture.componentInstance;
    component.askToggle(BASELINE);
    fixture.detectChanges();
    // Typing the wrong token must not allow confirm — canConfirm() gates the dialog button.
    const dialog = component.toggleDialog();
    dialog.typed = 'not-the-token';
    dialog.reason = 'testing';
    expect(dialog.canConfirm()).toBe(false);
    dialog.typed = 'DISABLE_STRATEGY';
    expect(dialog.canConfirm()).toBe(true);
  });

  it('running a backtest posts to the backtests endpoint with the confirmation token', () => {
    flushList();
    const component = fixture.componentInstance;
    component.btSymbol = 'ETHUSD';
    component.btTimeframe = '1d';
    component.btStart = '2024-01-01';
    component.btEnd = '2024-02-01';
    component.btCostMultiplier = 1;
    component.applyBacktest('operator requested run');

    const req = http.expectOne('/v1/strategies/baseline_ema_cross/backtests');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.confirmation_token).toBe('RUN_BACKTEST');
    expect(req.request.body.universe_symbol).toBe('ETHUSD');
    req.flush({ run_id: 'run-1', status: 'queued' });

    http.expectOne('/v1/strategies/baseline_ema_cross/backtests').flush([
      {
        run_id: 'run-1',
        strategy_id: 'baseline_ema_cross',
        status: 'queued',
        created_at: '2026-01-01T00:00:00Z',
        started_at: null,
        finished_at: null,
        error: null,
        request: {
          strategy_kind: 'ema_cross',
          strategy_params: {},
          universe_symbol: 'ETHUSD',
          timeframe: '1d',
          start: '2024-01-01T00:00:00Z',
          end: '2024-02-01T00:00:00Z',
          cost_multiplier: 1,
        },
        metrics: null,
      },
    ]);
    // Polling is on a real setInterval (POLL_MS) — it does not fire synchronously within
    // this test, so no further request is expected here.
  });

  it('cloning writes to the clone endpoint with the CLONE_STRATEGY token', () => {
    flushList();
    const component = fixture.componentInstance;
    component.cloneNewId = 'baseline_ema_cross_copy';
    component.applyClone('cloning for a parameter experiment');

    const req = http.expectOne('/v1/strategies/baseline_ema_cross/clone');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      new_id: 'baseline_ema_cross_copy',
      confirmation_token: 'CLONE_STRATEGY',
    });
    req.flush({ ok: true, detail: 'cloned', restart_required: true });

    http.expectOne('/v1/strategies').flush([BASELINE, DONCHIAN]);
  });
});
