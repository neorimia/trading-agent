import { Component, OnDestroy, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { Select } from 'primeng/select';
import { TableModule, TableRowSelectEvent } from 'primeng/table';
import { Tag } from 'primeng/tag';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import {
  BacktestJobRow,
  BacktestJobStatus,
  StrategyRow,
  StrategyStatusLabel,
  StrategyVersionRow,
} from '../core/models';
import { ConfirmDanger } from '../shared/confirm-danger';
import { EmptyState } from '../shared/empty-state';
import { LineChart, LineChartSeries } from '../shared/line-chart';
import { MetricCard } from '../shared/metric-card';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';

const STATUS_OPTIONS: StrategyStatusLabel[] = [
  'experimental',
  'testing',
  'paper_candidate',
  'disabled',
];
const COST_MULTIPLIERS: (1 | 2 | 3)[] = [1, 2, 3];
const REGIME_DIMENSION_LABELS: Record<string, string> = {
  trend: 'Trend (bull/bear/sideways)',
  direction: 'Direction',
  volatility: 'Volatility',
  volume: 'Volume',
};
const POLL_MS = 3000;

type PendingEditKind = 'params' | 'status';
type Severity = 'success' | 'info' | 'warn' | 'secondary' | 'danger';

@Component({
  selector: 'app-strategies-page',
  imports: [
    ConfirmDanger,
    EmptyState,
    LineChart,
    MetricCard,
    FormsModule,
    Button,
    InputText,
    Message,
    Select,
    TableModule,
    Tag,
    PageHeader,
    PageSkeleton,
  ],
  template: `
    <div class="reveal">
      <app-page-header
        title="Strategy center"
        lede="Strategies only produce buy/sell/hold signals. RiskEngine still sizes every order and no button here ever reaches a live Kraken order."
      />
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (rows().length === 0) {
        <app-empty-state icon="pi-sitemap" />
      } @else {
        <div class="strategies-layout">
          <p-table
            [value]="rows()"
            dataKey="id"
            selectionMode="single"
            [selection]="selected()"
            (onRowSelect)="onRowSelect($event)"
            styleClass="strategy-list-table"
          >
            <ng-template #header>
              <tr>
                <th>Strategy</th>
                <th>Status</th>
                <th>v</th>
              </tr>
            </ng-template>
            <ng-template #body let-row>
              <tr [pSelectableRow]="row" [class.selected-row]="row.id === selectedId()">
                <td>
                  <div class="strategy-name">{{ row.name }}</div>
                  <div class="muted mono">{{ row.kind }}</div>
                  <p-tag
                    [value]="row.enabled ? 'enabled' : 'disabled'"
                    [severity]="row.enabled ? 'success' : 'secondary'"
                  />
                </td>
                <td><p-tag [value]="row.status" [severity]="statusSeverity(row.status)" /></td>
                <td class="mono">{{ row.version }}</td>
              </tr>
            </ng-template>
          </p-table>

          @if (!selected()) {
            <app-empty-state title="Select a strategy" detail="Pick a row on the left to see its hypothesis, parameters, versions and backtests." icon="pi-sliders-h" />
          } @else {
            <article class="strategy-detail">
              <header class="strategy-detail-head">
                <div>
                  <h2>{{ selected()!.name }}</h2>
                  <div class="score-grid">
                    <p-tag [value]="selected()!.kind" severity="secondary" />
                    <p-tag [value]="selected()!.status" [severity]="statusSeverity(selected()!.status)" />
                    <p-tag [value]="'v' + selected()!.version" severity="secondary" />
                    <p-tag [value]="selected()!.enabled ? 'enabled' : 'disabled'" [severity]="selected()!.enabled ? 'success' : 'secondary'" />
                    <p-tag value="Backtest" severity="info" />
                    <p-tag
                      [value]="'Paper: ' + (selected()!.last_paper_sessions ?? 0) + ' sessions' + (selected()!.last_paper_halted ? ' (halted)' : '')"
                      severity="secondary"
                    />
                    <p-tag value="Live (locked)" severity="danger" icon="pi pi-lock" />
                  </div>
                </div>
                <p-button
                  [label]="selected()!.enabled ? 'Disable' : 'Enable'"
                  [severity]="selected()!.enabled ? 'danger' : 'success'"
                  size="small"
                  [disabled]="!state.canMutate()"
                  (onClick)="askToggle(selected()!)"
                />
              </header>

              @if (feedback(); as msg) {
                <p-message [severity]="msg.severity" [text]="msg.text" />
              }
              <p class="lede">{{ selected()!.hypothesis || 'No hypothesis recorded — treat as untested.' }}</p>
              <p class="muted">
                Assets: {{ selected()!.supported_assets.join(', ') || 'none' }} · Timeframes:
                {{ selected()!.supported_timeframes.join(', ') || 'none' }} · Last backtest ref:
                {{ selected()!.last_backtest_ref ?? '-' }}
              </p>

              <section class="split">
                <article class="panel secondary">
                  <h3>Parameters (editing writes a new immutable version)</h3>
                  @if (paramKeys().length === 0) {
                    <p class="muted">This kind has no local parameters (e.g. LLM-assisted).</p>
                  } @else {
                    @for (group of paramGroups(); track group.label) {
                      <h4 class="param-group-label">{{ group.label }}</h4>
                      <div class="stack">
                        @for (key of group.keys; track key) {
                          <label
                            >{{ key }}
                            <input
                              pInputText
                              [(ngModel)]="paramDraft[key]"
                              [name]="key"
                              [disabled]="!state.canMutate()"
                            />
                          </label>
                        }
                      </div>
                    }
                    <p-button
                      label="Propose new version"
                      size="small"
                      [disabled]="!state.canMutate()"
                      (onClick)="askEditParams()"
                    />
                  }
                </article>
                <article class="panel secondary">
                  <h3>Lifecycle actions</h3>
                  <label class="field-label" for="status-select">Mark status (new version, same params)</label>
                  <div class="toolbar">
                    <p-select id="status-select" [options]="statusOptions" [(ngModel)]="pendingStatus" appendTo="body" size="small" />
                    <p-button label="Apply status" size="small" severity="secondary" [disabled]="!state.canMutate()" (onClick)="askMarkStatus(pendingStatus)" />
                  </div>
                  <label class="field-label" for="clone-id">Clone as (disabled, experimental, v1)</label>
                  <div class="toolbar">
                    <input pInputText id="clone-id" [(ngModel)]="cloneNewId" name="cloneNewId" />
                    <p-button label="Clone" size="small" severity="secondary" [disabled]="!state.canMutate() || !cloneNewId.trim()" (onClick)="askClone()" />
                  </div>
                </article>
              </section>

              <section class="panel">
                <h3>Version history (read-only, immutable snapshots)</h3>
                @if (versions().length === 0) {
                  <app-empty-state title="No versions yet" icon="pi-history" />
                } @else {
                  <p-table [value]="versions()">
                    <ng-template #header>
                      <tr>
                        <th>v</th>
                        <th>Status</th>
                        <th>Enabled</th>
                        <th>Updated</th>
                        <th>Change note</th>
                      </tr>
                    </ng-template>
                    <ng-template #body let-row>
                      <tr>
                        <td class="mono">{{ row.version }}</td>
                        <td><p-tag [value]="row.status" [severity]="statusSeverity(row.status)" /></td>
                        <td>{{ row.enabled ? 'yes' : 'no' }}</td>
                        <td class="mono">{{ shortDate(row.updated_at) }}</td>
                        <td>{{ row.change_note }}</td>
                      </tr>
                    </ng-template>
                  </p-table>
                }
              </section>

              <section class="panel">
                <h3>Backtest (out-of-sample check, not an order)</h3>
                <p class="muted">
                  Runs the shared backtest engine asynchronously with realistic Kraken-tier costs. A single run is not proof —
                  compare against baselines and check the warnings below before trusting a number.
                </p>
                <div class="toolbar">
                  <label
                    >Asset
                    <p-select [options]="selected()!.supported_assets" [(ngModel)]="btSymbol" appendTo="body" size="small" />
                  </label>
                  <label
                    >Timeframe
                    <p-select [options]="selected()!.supported_timeframes" [(ngModel)]="btTimeframe" appendTo="body" size="small" />
                  </label>
                  <label
                    >Cost ×
                    <p-select [options]="costMultipliers" [(ngModel)]="btCostMultiplier" appendTo="body" size="small" />
                  </label>
                  <label>Start <input pInputText type="date" [(ngModel)]="btStart" name="btStart" /></label>
                  <label>End <input pInputText type="date" [(ngModel)]="btEnd" name="btEnd" /></label>
                  <p-button label="Run backtest" size="small" [disabled]="!state.canMutate()" (onClick)="askBacktest()" />
                </div>

                @if (jobs().length === 0) {
                  <app-empty-state title="No backtest runs yet" icon="pi-play" />
                } @else {
                  <p-table [value]="jobs()" selectionMode="single" [selection]="selectedJob()" (onRowSelect)="onJobSelect($event)">
                    <ng-template #header>
                      <tr>
                        <th>Run</th>
                        <th>Status</th>
                        <th>Asset / TF</th>
                        <th>Cost ×</th>
                        <th>Created</th>
                      </tr>
                    </ng-template>
                    <ng-template #body let-row>
                      <tr [pSelectableRow]="row" [class.selected-row]="selectedJob()?.run_id === row.run_id">
                        <td class="mono">{{ row.run_id.slice(0, 8) }}</td>
                        <td><p-tag [value]="row.status" [severity]="jobStatusSeverity(row.status)" /></td>
                        <td class="mono">{{ row.request.universe_symbol }} / {{ row.request.timeframe }}</td>
                        <td class="mono">{{ row.request.cost_multiplier }}</td>
                        <td class="mono">{{ shortDate(row.created_at) }}</td>
                      </tr>
                    </ng-template>
                  </p-table>
                }

                @if (selectedJob(); as job) {
                  @if (job.status === 'error') {
                    <p-message severity="warn" [text]="'Run failed: ' + (job.error ?? 'unknown error')" />
                  } @else if (job.status !== 'done') {
                    <p-message severity="info" [text]="'Run is ' + job.status + '…'" />
                  } @else if (job.metrics; as metrics) {
                    @for (warning of warnings(); track warning) {
                      <p-message severity="warn" [text]="warning" />
                    }
                    <section class="metric-grid">
                      @for (card of performanceCards(); track card.label) {
                        <app-metric-card [label]="card.label" [value]="card.value" />
                      }
                    </section>

                    <h4>Baseline comparison (total return)</h4>
                    <dl class="facts">
                      @for (row of baselineRows(); track row.label) {
                        <div>
                          <dt>{{ row.label }}</dt>
                          <dd class="mono">{{ row.value }}</dd>
                        </div>
                      }
                    </dl>

                    <h4>Equity vs buy &amp; hold</h4>
                    <app-line-chart [series]="equitySeries()" />

                    <h4>Drawdown</h4>
                    <app-line-chart [series]="drawdownSeries()" [height]="160" />

                    <h4>Trade distribution ({{ metrics.extra.trade_pnls.length }} closed trades)</h4>
                    @if (tradeHistogram().length === 0) {
                      <p class="muted">No closed trades in this run.</p>
                    } @else {
                      <div class="hist">
                        @for (bucket of tradeHistogram(); track bucket.rangeLabel) {
                          <div class="hist-row">
                            <span class="hist-label mono">{{ bucket.rangeLabel }}</span>
                            <div class="hist-bar-track">
                              <div
                                class="hist-bar"
                                [class.pnl-pos]="bucket.positive"
                                [class.pnl-neg]="!bucket.positive"
                                [style.width.%]="(bucket.count / tradeHistogramMax()) * 100"
                              ></div>
                            </div>
                            <span class="mono">{{ bucket.count }}</span>
                          </div>
                        }
                      </div>
                    }

                    <h4>Regime performance (per-bar returns, not a "trade only in regime X" simulation)</h4>
                    @for (dim of regimeBreakdown(); track dim.dimension) {
                      <h5 class="muted">{{ regimeLabel(dim.dimension) }}</h5>
                      <p-table [value]="dim.buckets">
                        <ng-template #header>
                          <tr>
                            <th>Regime</th>
                            <th>Bars</th>
                            <th>Bar win rate</th>
                            <th>Cumulative return</th>
                          </tr>
                        </ng-template>
                        <ng-template #body let-row>
                          <tr>
                            <td>{{ row.bucket }}</td>
                            <td class="mono">{{ row.n_bars }}</td>
                            <td class="mono">{{ row.bar_win_rate ?? 'n/a' }}</td>
                            <td class="mono">{{ row.cumulative_return_pct }}%</td>
                          </tr>
                        </ng-template>
                      </p-table>
                    }
                    <p class="muted">
                      dataset_hash {{ metrics.comparable.dataset_hash.slice(0, 12) }} · n_bars
                      {{ metrics.comparable.n_bars }} · n_fills {{ metrics.comparable.n_fills }}
                    </p>
                  }
                }
              </section>
            </article>
          }
        </div>
      }

      <app-confirm-danger
        #toggleDialog
        [title]="pendingToggle?.enabled ? 'Disable strategy' : 'Enable strategy'"
        body="This writes config/strategies.yaml. The engine picks it up on the next start. RiskEngine still sizes every order."
        [requireTyped]="pendingToggle?.enabled ? 'DISABLE_STRATEGY' : 'ENABLE_STRATEGY'"
        confirmLabel="Write config"
        (confirmed)="applyToggle($event.reason)"
      />
      <app-confirm-danger
        #editDialog
        [title]="pendingEditKind === 'status' ? 'Mark strategy status' : 'Propose new parameter version'"
        [body]="editDialogBody()"
        requireTyped="EDIT_STRATEGY"
        confirmLabel="Write new version"
        (confirmed)="applyEdit($event.reason)"
      />
      <app-confirm-danger
        #cloneDialog
        title="Clone strategy"
        body="Creates a new, disabled, experimental (v1) strategy entry with the same parameters. It never inherits the source's enabled state or status."
        requireTyped="CLONE_STRATEGY"
        confirmLabel="Clone"
        (confirmed)="applyClone($event.reason)"
      />
      <app-confirm-danger
        #backtestDialog
        title="Run backtest"
        body="Runs the async backtest job on public historical bars only — no live order path. Results are estimates, not guarantees; compare against the baselines below."
        requireTyped="RUN_BACKTEST"
        confirmLabel="Queue backtest"
        (confirmed)="applyBacktest($event.reason)"
      />
    </div>
  `,
})
export class StrategiesPage implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly toggleDialog = viewChild.required<ConfirmDanger>('toggleDialog');
  readonly editDialog = viewChild.required<ConfirmDanger>('editDialog');
  readonly cloneDialog = viewChild.required<ConfirmDanger>('cloneDialog');
  readonly backtestDialog = viewChild.required<ConfirmDanger>('backtestDialog');

  readonly rows = signal<StrategyRow[]>([]);
  readonly ready = signal(false);
  readonly selectedId = signal<string | null>(null);
  readonly versions = signal<StrategyVersionRow[]>([]);
  readonly jobs = signal<BacktestJobRow[]>([]);
  readonly selectedJob = signal<BacktestJobRow | null>(null);
  readonly feedback = signal<{ severity: 'success' | 'error'; text: string } | null>(null);

  readonly statusOptions = STATUS_OPTIONS;
  readonly costMultipliers = COST_MULTIPLIERS;

  paramDraft: Record<string, string> = {};
  pendingStatus: StrategyStatusLabel = 'experimental';
  pendingToggle: StrategyRow | null = null;
  pendingEditKind: PendingEditKind = 'params';
  cloneNewId = '';
  btSymbol = '';
  btTimeframe = '1d';
  btCostMultiplier: 1 | 2 | 3 = 1;
  btStart = '';
  btEnd = '';

  private pollHandle: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.reload();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  selected(): StrategyRow | null {
    const id = this.selectedId();
    return id ? this.rows().find((row) => row.id === id) ?? null : null;
  }

  paramKeys(): string[] {
    return Object.keys(this.paramDraft);
  }

  /** Heuristic grouping so the parameter form isn't one flat list — matches on key naming
   *  convention rather than a per-strategy-kind map, so it keeps working as kinds gain params. */
  paramGroups(): { label: string; keys: string[] }[] {
    const keys = this.paramKeys();
    const riskKeys = keys.filter((key) => /atr|stop|target|risk/i.test(key));
    const trendKeys = keys.filter((key) => !riskKeys.includes(key));
    const groups = [
      { label: 'Trend detection', keys: trendKeys },
      { label: 'Risk & exit', keys: riskKeys },
    ];
    return groups.filter((group) => group.keys.length > 0);
  }

  onRowSelect(event: TableRowSelectEvent<StrategyRow>): void {
    if (event.data && !Array.isArray(event.data)) {
      this.selectStrategy(event.data);
    }
  }

  onJobSelect(event: TableRowSelectEvent<BacktestJobRow>): void {
    if (event.data && !Array.isArray(event.data)) {
      this.selectJob(event.data);
    }
  }

  selectStrategy(row: StrategyRow): void {
    this.stopPolling();
    this.feedback.set(null);
    this.selectedId.set(row.id);
    this.paramDraft = { ...row.params };
    this.pendingStatus = row.status;
    this.cloneNewId = `${row.id}_copy`;
    this.selectedJob.set(null);
    this.versions.set([]);
    this.jobs.set([]);
    this.initBacktestForm(row);
    this.loadVersions(row.id);
    this.loadJobs(row.id);
  }

  selectJob(job: BacktestJobRow): void {
    this.selectedJob.set(job);
    if (job.status === 'queued' || job.status === 'running') {
      this.startPolling();
    }
  }

  statusSeverity(status: StrategyStatusLabel): Severity {
    switch (status) {
      case 'paper_candidate':
        return 'success';
      case 'testing':
        return 'info';
      case 'experimental':
        return 'warn';
      case 'disabled':
        return 'danger';
      default:
        return 'secondary';
    }
  }

  jobStatusSeverity(status: BacktestJobStatus): Severity {
    switch (status) {
      case 'done':
        return 'success';
      case 'running':
        return 'info';
      case 'error':
        return 'danger';
      default:
        return 'secondary';
    }
  }

  shortDate(iso: string): string {
    return iso.slice(0, 16).replace('T', ' ');
  }

  askToggle(row: StrategyRow): void {
    this.pendingToggle = row;
    this.toggleDialog().open();
  }

  applyToggle(_reason: string): void {
    const row = this.pendingToggle;
    if (!row) {
      return;
    }
    const enabled = !row.enabled;
    const token = enabled ? 'ENABLE_STRATEGY' : 'DISABLE_STRATEGY';
    this.api.toggleStrategy(row.id, enabled, token).subscribe({
      next: () => {
        this.feedback.set({ severity: 'success', text: `${row.name} ${enabled ? 'enabled' : 'disabled'}.` });
        this.reload();
      },
      error: () => this.feedback.set({ severity: 'error', text: `Could not ${enabled ? 'enable' : 'disable'} ${row.name}.` }),
    });
  }

  askEditParams(): void {
    if (!this.selected()) {
      return;
    }
    this.pendingEditKind = 'params';
    this.editDialog().open();
  }

  askMarkStatus(status: StrategyStatusLabel): void {
    if (!this.selected()) {
      return;
    }
    this.pendingEditKind = 'status';
    this.pendingStatus = status;
    this.editDialog().open();
  }

  editDialogBody(): string {
    if (this.pendingEditKind === 'status') {
      return `Writes a new immutable version of ${this.selected()?.id ?? 'this strategy'} with status = ${this.pendingStatus}. Parameters are unchanged.`;
    }
    return 'Writes a new immutable version with the edited parameters. Invalid parameters are rejected before anything is written.';
  }

  applyEdit(reason: string): void {
    const row = this.selected();
    if (!row) {
      return;
    }
    const body =
      this.pendingEditKind === 'status'
        ? { params: row.params, status: this.pendingStatus, change_note: reason }
        : { params: this.paramDraft, change_note: reason };
    this.api.writeStrategyVersion(row.id, body).subscribe({
      next: () => {
        this.feedback.set({ severity: 'success', text: `New version written for ${row.name}.` });
        this.reload();
        this.loadVersions(row.id);
      },
      error: () => this.feedback.set({ severity: 'error', text: `Could not write a new version for ${row.name}.` }),
    });
  }

  askClone(): void {
    if (!this.selected() || !this.cloneNewId.trim()) {
      return;
    }
    this.cloneDialog().open();
  }

  applyClone(_reason: string): void {
    const row = this.selected();
    const newId = this.cloneNewId.trim();
    if (!row || !newId) {
      return;
    }
    this.api.cloneStrategy(row.id, newId).subscribe({
      next: () => {
        this.feedback.set({ severity: 'success', text: `Cloned ${row.name} as ${newId}.` });
        this.cloneNewId = `${row.id}_copy`;
        this.reload();
      },
      error: () => this.feedback.set({ severity: 'error', text: `Could not clone ${row.name} as ${newId}.` }),
    });
  }

  askBacktest(): void {
    if (!this.selected()) {
      return;
    }
    this.backtestDialog().open();
  }

  applyBacktest(_reason: string): void {
    const row = this.selected();
    if (!row) {
      return;
    }
    this.api
      .startBacktest(row.id, {
        universe_symbol: this.btSymbol,
        timeframe: this.btTimeframe,
        start: `${this.btStart}T00:00:00Z`,
        end: `${this.btEnd}T00:00:00Z`,
        cost_multiplier: this.btCostMultiplier,
      })
      .subscribe(() => {
        this.loadJobs(row.id);
        this.startPolling();
      });
  }

  performanceCards(): { label: string; value: string }[] {
    const perf = this.selectedJob()?.metrics?.extra.performance;
    if (!perf) {
      return [];
    }
    return [
      { label: 'Total return', value: `${perf.total_return_pct}%` },
      { label: 'Annualized', value: perf.annualized_return_pct ? `${perf.annualized_return_pct}%` : 'n/a' },
      { label: 'Sharpe', value: perf.sharpe_ratio ?? 'n/a' },
      { label: 'Sortino', value: perf.sortino_ratio ?? 'n/a' },
      { label: 'Calmar', value: perf.calmar_ratio ?? 'n/a' },
      { label: 'Max drawdown', value: `${perf.max_drawdown_pct}%` },
      { label: 'Win rate', value: perf.win_rate ?? 'n/a' },
      { label: 'Profit factor', value: perf.profit_factor ?? 'n/a' },
      { label: 'Expectancy', value: perf.expectancy ?? 'n/a' },
      { label: 'Trades', value: String(perf.n_trades) },
      { label: 'Turnover', value: perf.turnover },
      { label: 'Total fees', value: perf.total_fees },
      { label: 'Est. slippage', value: perf.estimated_slippage },
      { label: 'Longest losing streak', value: String(perf.longest_losing_streak) },
      { label: 'Avg exposure', value: perf.avg_exposure_pct ? `${perf.avg_exposure_pct}%` : 'n/a' },
    ];
  }

  baselineRows(): { label: string; value: string }[] {
    const extra = this.selectedJob()?.metrics?.extra;
    if (!extra) {
      return [];
    }
    const b = extra.baselines;
    return [
      { label: 'Strategy total return', value: `${extra.performance.total_return_pct}%` },
      { label: 'Buy & hold', value: b.buy_and_hold_pct ? `${b.buy_and_hold_pct}%` : 'n/a' },
      { label: 'Cash (0% by definition)', value: `${b.cash_pct}%` },
      { label: 'Random control (same trade rate)', value: b.random_control_pct ? `${b.random_control_pct}%` : 'n/a' },
    ];
  }

  warnings(): string[] {
    return this.selectedJob()?.metrics?.extra.performance.warnings ?? [];
  }

  equitySeries(): LineChartSeries[] {
    const extra = this.selectedJob()?.metrics?.extra;
    if (!extra) {
      return [];
    }
    return [
      {
        name: 'Strategy equity',
        color: '#3d9a6a',
        points: extra.equity_curve.map((p) => ({ time: p.t, value: Number(p.equity) })),
      },
      {
        name: 'Buy & hold',
        color: '#7aa2d6',
        points: extra.buy_and_hold_curve.map((p) => ({ time: p.t, value: Number(p.equity) })),
      },
    ];
  }

  drawdownSeries(): LineChartSeries[] {
    const extra = this.selectedJob()?.metrics?.extra;
    if (!extra) {
      return [];
    }
    return [
      {
        name: 'Drawdown %',
        color: '#c45b5b',
        points: extra.drawdown_curve.map((p) => ({ time: p.t, value: Number(p.drawdown_pct) })),
      },
    ];
  }

  tradeHistogram(): { rangeLabel: string; count: number; positive: boolean }[] {
    const pnls = (this.selectedJob()?.metrics?.extra.trade_pnls ?? []).map(Number);
    if (pnls.length === 0) {
      return [];
    }
    const min = Math.min(...pnls);
    const max = Math.max(...pnls);
    if (min === max) {
      return [{ rangeLabel: min.toFixed(2), count: pnls.length, positive: min >= 0 }];
    }
    const bucketCount = 6;
    const width = (max - min) / bucketCount;
    const buckets = Array.from({ length: bucketCount }, (_, i) => ({
      lo: min + i * width,
      hi: min + (i + 1) * width,
      count: 0,
    }));
    for (const pnl of pnls) {
      const idx = Math.min(bucketCount - 1, Math.floor((pnl - min) / width));
      buckets[idx].count += 1;
    }
    return buckets.map((b) => ({
      rangeLabel: `${b.lo.toFixed(1)} to ${b.hi.toFixed(1)}`,
      count: b.count,
      positive: b.hi > 0,
    }));
  }

  tradeHistogramMax(): number {
    return Math.max(1, ...this.tradeHistogram().map((b) => b.count));
  }

  regimeLabel(dimension: string): string {
    return REGIME_DIMENSION_LABELS[dimension] ?? dimension;
  }

  regimeBreakdown(): {
    dimension: string;
    buckets: { bucket: string; n_bars: number; bar_win_rate: string | null; cumulative_return_pct: string }[];
  }[] {
    const regime = this.selectedJob()?.metrics?.extra.regime;
    if (!regime) {
      return [];
    }
    return Object.entries(regime).map(([dimension, buckets]) => ({
      dimension,
      buckets: Object.entries(buckets).map(([bucket, metrics]) => ({ bucket, ...metrics })),
    }));
  }

  private initBacktestForm(row: StrategyRow): void {
    this.btSymbol = row.supported_assets[0] ?? 'ETHUSD';
    this.btTimeframe = row.supported_timeframes.includes('1d')
      ? '1d'
      : row.supported_timeframes[0] ?? '1d';
    this.btCostMultiplier = 1;
    const end = new Date();
    const start = new Date(end.getTime() - 90 * 24 * 60 * 60 * 1000);
    this.btEnd = end.toISOString().slice(0, 10);
    this.btStart = start.toISOString().slice(0, 10);
  }

  private loadVersions(id: string): void {
    this.api.listStrategyVersions(id).subscribe({
      next: (value) => this.versions.set(value.slice().reverse()),
      error: () => this.versions.set([]),
    });
  }

  private loadJobs(id: string): void {
    this.api.listBacktests(id).subscribe({
      next: (value) => {
        this.jobs.set(value);
        if (value.some((job) => job.status === 'queued' || job.status === 'running')) {
          this.startPolling();
        }
      },
      error: () => this.jobs.set([]),
    });
  }

  private startPolling(): void {
    if (this.pollHandle) {
      return;
    }
    this.pollHandle = setInterval(() => {
      const row = this.selected();
      if (!row) {
        this.stopPolling();
        return;
      }
      this.api.listBacktests(row.id).subscribe((list) => {
        this.jobs.set(list);
        const current = this.selectedJob();
        if (current) {
          const fresh = list.find((job) => job.run_id === current.run_id);
          if (fresh) {
            this.selectedJob.set(fresh);
          }
        }
        if (!list.some((job) => job.status === 'queued' || job.status === 'running')) {
          this.stopPolling();
        }
      });
    }, POLL_MS);
  }

  private stopPolling(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }

  private reload(): void {
    this.api.strategies().subscribe({
      next: (value) => {
        this.rows.set(value);
        this.ready.set(true);
        const current = this.selectedId();
        const stillThere = current ? value.find((row) => row.id === current) : undefined;
        if (!stillThere && value.length > 0) {
          this.selectStrategy(value[0]);
        }
      },
      error: () => this.ready.set(true),
    });
  }
}
