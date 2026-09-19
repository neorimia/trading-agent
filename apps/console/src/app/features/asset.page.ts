import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import {
  AnalysisRunResponse,
  AnalysisType,
  BarPoint,
  IndicatorSnapshot,
  OrderRow,
  ParsedAnalysis,
  PositionRow,
  ResearchDocumentView,
  SignalResponse,
  StoredAnalysis,
} from '../core/models';
import { CandleChart } from '../shared/candle-chart';
import { EmptyState } from '../shared/empty-state';
import { StaleBadge } from '../shared/stale-badge';

const ANALYSIS_TYPES: AnalysisType[] = ['priced_in', 'technical', 'news_impact', 'daily_plan'];
const TIMEFRAMES = ['1h', '4h', '1d'];

@Component({
  selector: 'app-asset-page',
  imports: [CandleChart, EmptyState, StaleBadge, FormsModule],
  template: `
    <h1>{{ symbol }}</h1>
    <p class="lede">
      Candles use bar close time (lookahead-safe). Analyses are research reports, not orders.
      Position size stays engine-owned.
    </p>
    <div class="toolbar">
      <label>
        Timeframe
        <select [(ngModel)]="timeframe" (ngModelChange)="loadMarket()">
          @for (tf of timeframes; track tf) {
            <option [ngValue]="tf">{{ tf }}</option>
          }
        </select>
      </label>
    </div>
    @if (bars().length === 0) {
      <app-empty-state title="No bars" detail="The venue feed returned no completed candles." />
    } @else {
      <app-candle-chart [bars]="bars()" />
    }
    <section class="split">
      <article class="card secondary">
        <h2>Technical snapshot</h2>
        <p class="muted">Deterministic indicators. Funding and open interest are unknown until a derivatives adapter exists.</p>
        @if (!snapshot()) {
          <app-empty-state title="Indicators not ready" />
        } @else {
          <table>
            <tbody>
              @for (row of snapshotRows(); track row[0]) {
                <tr>
                  <td>{{ row[0] }}</td>
                  <td class="mono">{{ row[1] }}</td>
                </tr>
              }
            </tbody>
          </table>
        }
      </article>
      <article class="card">
        <h2>Agent signal (proposal)</h2>
        @if (!signal()) {
          <app-empty-state title="No signal" />
        } @else {
          <p>Source: {{ signal()!.source }} · confidence {{ signal()!.confidence ?? 'n/a' }}</p>
          <p>Direction: {{ signal()!.direction ?? 'none' }}</p>
          <p>{{ signal()!.rationale }}</p>
          <p class="muted">{{ signal()!.sources.join(', ') }}</p>
        }
        <h2>Position / orders</h2>
        @for (pos of positions(); track pos.instrument) {
          <p>Qty {{ pos.quantity }} · last {{ pos.last_price }} · stop {{ pos.stop_loss }} ({{ pos.stop_source }})</p>
        }
        @for (order of orders(); track order.correlation_id) {
          <p class="mono">{{ order.status }} {{ order.side }} {{ order.quantity }} @ {{ order.fill_price ?? '—' }}</p>
        }
      </article>
    </section>
    <section class="card">
      <h2>Run research analysis</h2>
      <p class="muted">Level 1 copilot. Never places an order. recommended_action is not executable.</p>
      <div class="toolbar">
        <label>
          Type
          <select [(ngModel)]="analysisType">
            @for (kind of analysisTypes; track kind) {
              <option [ngValue]="kind">{{ kind }}</option>
            }
          </select>
        </label>
        <button type="button" [disabled]="!state.canMutate() || running()" (click)="runAnalysis()">
          {{ running() ? 'Running…' : 'Run analysis' }}
        </button>
      </div>
      @if (runError()) {
        <p class="banner-warn">{{ runError() }}</p>
      }
      @if (rejected()) {
        <p class="banner-warn">Rejected: {{ rejected() }}</p>
      }
      @if (analysis(); as report) {
        <article>
          <p class="badge-fact">research report · not an order · expiry {{ report.expiry_time }}</p>
          <p>data quality {{ report.data_quality_score }} · confidence {{ report.confidence_score }} · {{ report.action_type }}</p>
          <p><strong>Facts:</strong> {{ report.factual_summary }}</p>
          <p><strong>Bull:</strong> {{ report.bullish_case }}</p>
          <p><strong>Bear:</strong> {{ report.bearish_case }}</p>
          <p><strong>Neutral:</strong> {{ report.neutral_case }}</p>
          <p><strong>Recommended (not an order):</strong> {{ report.recommended_action }}</p>
          <p class="muted">Size suggestion: not applicable (engine-owned). Human approval required: {{ report.required_human_approval }}</p>
          <p class="muted">Sources: {{ sourceList(report) }}</p>
          <p class="muted">prompt {{ report.audit_metadata.prompt_hash }} · facts {{ report.audit_metadata.facts_bundle_hash }}</p>
          <p class="est">{{ report.uncertainty }}</p>
        </article>
      }
    </section>
    <section>
      <h2>Stored analyses</h2>
      @if (stored().length === 0) {
        <app-empty-state title="No analyses yet" detail="Run analysis to persist a research report in the audit log." />
      }
      @for (row of stored(); track row.correlation_id) {
        <article class="card secondary">
          <p class="mono">{{ row.timestamp }} · {{ row.analysis_type }} · is_order={{ row.is_order }}</p>
        </article>
      }
    </section>
    <section>
      <h2>Research documents</h2>
      @for (doc of docs(); track doc.doc_id) {
        <article class="card">
          <h3>{{ doc.title }}</h3>
          <app-stale-badge [stale]="doc.stale" />
          <p>confidence {{ doc.confidence_score }} · {{ doc.source_id }} · {{ doc.category }}</p>
          @if (doc.contradicts.length) {
            <p class="banner-warn">Contradicting documents: {{ doc.contradicts.join(', ') }}</p>
          }
        </article>
      }
    </section>
  `,
})
export class AssetPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly state = inject(AgentStateService);
  symbol = '';
  timeframe = '1d';
  analysisType: AnalysisType = 'technical';
  readonly timeframes = TIMEFRAMES;
  readonly analysisTypes = ANALYSIS_TYPES;
  readonly bars = signal<BarPoint[]>([]);
  readonly signal = signal<SignalResponse | null>(null);
  readonly positions = signal<PositionRow[]>([]);
  readonly orders = signal<OrderRow[]>([]);
  readonly docs = signal<ResearchDocumentView[]>([]);
  readonly snapshot = signal<IndicatorSnapshot | null>(null);
  readonly analysis = signal<ParsedAnalysis | null>(null);
  readonly rejected = signal<string | null>(null);
  readonly runError = signal<string | null>(null);
  readonly running = signal(false);
  readonly stored = signal<StoredAnalysis[]>([]);

  ngOnInit(): void {
    this.symbol = this.route.snapshot.paramMap.get('symbol') ?? '';
    this.loadMarket();
    this.api.signal(this.symbol).subscribe((value) => this.signal.set(value));
    this.api.positions().subscribe((value) =>
      this.positions.set(value.filter((row) => row.instrument === this.symbol)),
    );
    this.api.orders().subscribe((value) =>
      this.orders.set(value.filter((row) => row.instrument === this.symbol)),
    );
    this.api.research(this.symbol).subscribe((value) => this.docs.set(value));
    this.refreshStored();
  }

  loadMarket(): void {
    this.api.bars(this.symbol, this.timeframe).subscribe((value) => this.bars.set(value.bars));
    this.api.indicators(this.symbol, this.timeframe).subscribe({
      next: (value) => this.snapshot.set(value.snapshot),
      error: () => this.snapshot.set(null),
    });
  }

  snapshotRows(): [string, string][] {
    const snap = this.snapshot();
    if (!snap) {
      return [];
    }
    return [
      ['close', snap.close],
      ['EMA fast', snap.ema_fast],
      ['EMA slow', snap.ema_slow],
      ['RSI 14', snap.rsi_14],
      ['ATR 14', snap.atr_14],
      ['volume z', snap.volume_z_20],
      ['swing high', snap.swing_high],
      ['swing low', snap.swing_low],
      ['funding', snap.funding],
      ['open interest', snap.open_interest],
    ];
  }

  sourceList(report: ParsedAnalysis): string {
    if (!report.data_sources.length) {
      return 'unknown';
    }
    return report.data_sources.map((item) => item.url).join(', ');
  }

  runAnalysis(): void {
    this.running.set(true);
    this.runError.set(null);
    this.rejected.set(null);
    this.api.analyze(this.symbol, this.analysisType, this.timeframe).subscribe({
      next: (value: AnalysisRunResponse) => {
        this.running.set(false);
        this.analysis.set(value.analysis);
        this.rejected.set(value.rejected ? `${value.rejected.reason}` : null);
        this.refreshStored();
      },
      error: (err: { error?: { detail?: string }; message?: string }) => {
        this.running.set(false);
        this.runError.set(err.error?.detail ?? err.message ?? 'analyze failed');
      },
    });
  }

  private refreshStored(): void {
    this.api.analyses(this.symbol).subscribe((value) => this.stored.set(value.slice().reverse()));
  }
}
