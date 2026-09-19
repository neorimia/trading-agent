import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

import { ApiService } from '../core/api.service';
import {
  BarPoint,
  OrderRow,
  PositionRow,
  ResearchDocumentView,
  SignalResponse,
} from '../core/models';
import { CandleChart } from '../shared/candle-chart';
import { EmptyState } from '../shared/empty-state';
import { StaleBadge } from '../shared/stale-badge';

@Component({
  selector: 'app-asset-page',
  imports: [CandleChart, EmptyState, StaleBadge],
  template: `
    <h1>{{ symbol }}</h1>
    <p class="lede">Candles use bar close time (lookahead-safe). The agent signal is a proposal, not an order.</p>
    @if (bars().length === 0) {
      <app-empty-state title="No bars" detail="The venue feed returned no completed candles." />
    } @else {
      <app-candle-chart [bars]="bars()" />
    }
    <section class="split">
      <article class="card secondary">
        <h2>Agent signal (proposal)</h2>
        @if (!signal()) {
          <app-empty-state title="No signal" />
        } @else {
          <p>Source: {{ signal()!.source }} · confidence {{ signal()!.confidence ?? 'n/a' }}</p>
          <p>Direction: {{ signal()!.direction ?? 'none' }}</p>
          <p>{{ signal()!.rationale }}</p>
          <p class="muted">{{ signal()!.sources.join(', ') }}</p>
        }
      </article>
      <article class="card">
        <h2>Position / orders</h2>
        @for (pos of positions(); track pos.instrument) {
          <p>Qty {{ pos.quantity }} · last {{ pos.last_price }} · stop {{ pos.stop_loss }} ({{ pos.stop_source }})</p>
        }
        @for (order of orders(); track order.correlation_id) {
          <p class="mono">{{ order.status }} {{ order.side }} {{ order.quantity }} @ {{ order.fill_price ?? '—' }}</p>
        }
      </article>
    </section>
    <section>
      <h2>Research</h2>
      @for (doc of docs(); track doc.doc_id) {
        <article class="card">
          <h3>{{ doc.title }}</h3>
          <app-stale-badge [stale]="doc.stale" />
          <p>confidence {{ doc.confidence_score }} · {{ doc.source_id }}</p>
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
  symbol = '';
  readonly bars = signal<BarPoint[]>([]);
  readonly signal = signal<SignalResponse | null>(null);
  readonly positions = signal<PositionRow[]>([]);
  readonly orders = signal<OrderRow[]>([]);
  readonly docs = signal<ResearchDocumentView[]>([]);

  ngOnInit(): void {
    this.symbol = this.route.snapshot.paramMap.get('symbol') ?? '';
    this.api.bars(this.symbol).subscribe((value) => this.bars.set(value.bars));
    this.api.signal(this.symbol).subscribe((value) => this.signal.set(value));
    this.api.positions().subscribe((value) =>
      this.positions.set(value.filter((row) => row.instrument === this.symbol)),
    );
    this.api.orders().subscribe((value) =>
      this.orders.set(value.filter((row) => row.instrument === this.symbol)),
    );
    this.api.research(this.symbol).subscribe((value) => this.docs.set(value));
  }
}
