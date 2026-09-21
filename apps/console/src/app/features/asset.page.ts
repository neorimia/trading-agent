import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';
import { Select } from 'primeng/select';
import { Tag } from 'primeng/tag';

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
  formatQuote,
} from '../core/models';
import { CandleChart } from '../shared/candle-chart';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';
import { StaleBadge } from '../shared/stale-badge';

const ANALYSIS_TYPES: AnalysisType[] = ['priced_in', 'technical', 'news_impact', 'daily_plan'];
const TIMEFRAMES = ['1h', '4h', '1d'];

@Component({
  selector: 'app-asset-page',
  imports: [CandleChart, EmptyState, StaleBadge, FormsModule, Button, Message, Select, Tag, PageHeader, PageSkeleton],
  template: `
    <div class="reveal">
      <app-page-header
        [title]="symbol"
        lede="Candles use bar close time (lookahead-safe). Analyses are research reports, not orders. Position size stays engine-owned."
      >
        <label>
          Timeframe
          <p-select
            [options]="timeframes"
            [(ngModel)]="timeframe"
            (ngModelChange)="loadMarket()"
            appendTo="body"
            size="small"
          />
        </label>
      </app-page-header>
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (bars().length === 0) {
        <app-empty-state title="No bars" detail="The venue feed returned no completed candles." icon="pi-chart-line" />
      } @else {
        <app-candle-chart [bars]="bars()" />
      }
      <section class="split">
        <article class="panel secondary">
          <h2>Technical snapshot</h2>
          <p class="muted">Deterministic indicators. Funding and open interest are unknown until a derivatives adapter exists.</p>
          @if (!snapshot()) {
            <app-empty-state title="Indicators not ready" icon="pi-sliders-h" />
          } @else {
            <dl class="facts">
              @for (row of snapshotRows(); track row[0]) {
                <div>
                  <dt>{{ row[0] }}</dt>
                  <dd class="mono">{{ row[1] }}</dd>
                </div>
              }
            </dl>
          }
        </article>
        <article class="panel">
          <h2>Agent signal (proposal)</h2>
          @if (!signal()) {
            <app-empty-state title="No signal" icon="pi-bolt" />
          } @else {
            <p>Source: {{ signal()!.source }} · confidence {{ signal()!.confidence ?? 'n/a' }}</p>
            <p>Direction: {{ signal()!.direction ?? 'none' }}</p>
            <p>{{ signal()!.rationale }}</p>
            <p class="muted">{{ signal()!.sources.join(', ') }}</p>
          }
          <h2>Position / orders</h2>
          @if (positions().length === 0 && orders().length === 0) {
            <app-empty-state [title]="'No open position on ' + symbol" detail="No orders recorded for this instrument either." icon="pi-wallet" />
          }
          @for (pos of positions(); track pos.instrument) {
            <p>Qty {{ fmt(pos.quantity) }} · last {{ fmt(pos.last_price) }} · stop {{ fmt(pos.stop_loss) }} ({{ pos.stop_source }})</p>
          }
          @for (order of orders(); track order.correlation_id) {
            <p class="mono">{{ order.status }} {{ order.side }} {{ fmt(order.quantity) }} @ {{ fmt(order.fill_price) }}</p>
          }
        </article>
      </section>
      <section class="panel">
        <h2>Run research analysis</h2>
        <p class="muted">Level 1 copilot. Never places an order. recommended_action is not executable.</p>
        <div class="toolbar">
          <label>
            Type
            <p-select [options]="analysisTypes" [(ngModel)]="analysisType" appendTo="body" size="small" />
          </label>
          <p-button
            [label]="running() ? 'Running…' : 'Run analysis'"
            [disabled]="!state.canMutate() || running()"
            [loading]="running()"
            (onClick)="runAnalysis()"
          />
        </div>
        @if (runError()) {
          <p-message severity="warn" [text]="runError()!" />
        }
        @if (rejected()) {
          <p-message severity="warn" [text]="'Rejected: ' + rejected()" />
        }
        @if (analysis(); as report) {
          <article class="report-grid">
            <p-tag value="research report · not an order" severity="info" />
            <p class="muted">expiry {{ report.expiry_time }} · data quality {{ report.data_quality_score }} · confidence {{ report.confidence_score }} · {{ report.action_type }}</p>
            <div class="report-block">
              <h3>Facts</h3>
              <p>{{ report.factual_summary }}</p>
            </div>
            <div class="report-block">
              <h3>Bull</h3>
              <p>{{ report.bullish_case }}</p>
            </div>
            <div class="report-block">
              <h3>Bear</h3>
              <p>{{ report.bearish_case }}</p>
            </div>
            <div class="report-block">
              <h3>Neutral</h3>
              <p>{{ report.neutral_case }}</p>
            </div>
            <div class="report-block">
              <h3>Recommended (not an order)</h3>
              <p>{{ report.recommended_action }}</p>
            </div>
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
          <app-empty-state title="No analyses yet" detail="Run analysis to persist a research report in the audit log." icon="pi-file" />
        }
        @for (row of stored(); track row.correlation_id) {
          <article class="panel secondary">
            <p class="mono">{{ row.timestamp }} · {{ row.analysis_type }} · is_order={{ row.is_order }}</p>
          </article>
        }
      </section>
      <section>
        <h2>Research documents</h2>
        @for (doc of docs(); track doc.doc_id) {
          <article class="panel">
            <h3>{{ doc.title }}</h3>
            <div class="doc-meta">
              <app-stale-badge [stale]="doc.stale" />
              <span>confidence {{ doc.confidence_score }} · {{ doc.source_id }} · {{ doc.category }}</span>
            </div>
            @if (doc.contradicts.length) {
              <p-message severity="warn" [text]="'Contradicting documents: ' + doc.contradicts.join(', ')" />
            }
          </article>
        }
      </section>
    </div>
  `,
})
export class AssetPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly state = inject(AgentStateService);
  symbol = '';
  timeframe = '1h';
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
  readonly ready = signal(false);
  readonly fmt = formatQuote;

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
    this.api.bars(this.symbol, this.timeframe).subscribe({
      next: (value) => {
        this.bars.set(value.bars);
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
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
      ['close', formatQuote(snap.close)],
      ['EMA fast', formatQuote(snap.ema_fast)],
      ['EMA slow', formatQuote(snap.ema_slow)],
      ['RSI 14', formatQuote(snap.rsi_14)],
      ['ATR 14', formatQuote(snap.atr_14)],
      ['volume z', formatQuote(snap.volume_z_20)],
      ['swing high', formatQuote(snap.swing_high)],
      ['swing low', formatQuote(snap.swing_low)],
      // funding/open_interest are the literal string "unknown" until a derivatives adapter
      // exists — leave untouched rather than formatting to a numeric placeholder.
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
