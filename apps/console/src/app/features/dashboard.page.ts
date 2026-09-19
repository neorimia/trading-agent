import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../core/api.service';
import { AgentStateService } from '../core/agent-state.service';
import { DailyPlan, DailyPlanItem, PortfolioResponse, BrokerMonitorSnapshot, pnlClass } from '../core/models';
import { MetricCard } from '../shared/metric-card';
import { EmptyState } from '../shared/empty-state';

@Component({
  selector: 'app-dashboard-page',
  imports: [MetricCard, EmptyState, RouterLink],
  template: `
    <h1>Dashboard</h1>
    <p class="lede">Operator overview. Numbers are facts from the local engine, not forecasts.</p>
    @if (!portfolio()) {
      <app-empty-state title="Portfolio unavailable" detail="Start the control plane to load local state." />
    } @else {
      @if (portfolio()!.incomplete) {
        <p class="banner-warn">Portfolio reconstruction is incomplete. Treat P&amp;L as an estimate.</p>
      }
      <h2>Paper book (simulated)</h2>
      <section class="metric-grid">
        <app-metric-card label="Equity" [value]="portfolio()!.equity" />
        <app-metric-card label="Cash" [value]="portfolio()!.cash" />
        <app-metric-card
          label="Realized P&L"
          [value]="portfolio()!.realized_pnl"
          [valueClass]="pnlClass(portfolio()!.realized_pnl)"
        />
        <app-metric-card
          label="Unrealized P&L"
          [value]="portfolio()!.unrealized_pnl"
          [valueClass]="pnlClass(portfolio()!.unrealized_pnl)"
          hint="est. from last bar"
        />
        <app-metric-card label="Drawdown" [value]="portfolio()!.drawdown" />
        <app-metric-card label="Orders today" [value]="'' + portfolio()!.orders_today" />
      </section>
    }
    <section>
      <h2>Kraken account (monitor)</h2>
      <p class="lede">Query-only Balance/OpenOrders. This is not the paper book and cannot place orders.</p>
      @if (monitor().status === 'not_configured') {
        <app-empty-state
          title="Monitor not configured"
          detail="Paper still runs without keys. Add Query-only Kraken spot keys (Withdraw off) to observe the real account."
        />
      } @else if (monitor().status === 'error') {
        <p class="banner-warn">Monitor error: {{ monitor().error || 'poll failed' }}</p>
      } @else {
        <p class="muted">status={{ monitor().status }} · polled {{ monitor().polled_at || '—' }}</p>
        @if (krakenBalanceEntries().length === 0) {
          <app-empty-state title="No Kraken balances" detail="Spot query returned an empty book." />
        } @else {
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Quantity</th>
              </tr>
            </thead>
            <tbody>
              @for (row of krakenBalanceEntries(); track row[0]) {
                <tr>
                  <td>{{ row[0] }}</td>
                  <td class="mono">{{ row[1] }}</td>
                </tr>
              }
            </tbody>
          </table>
        }
        <p class="muted">Open client order ids: {{ monitor().open_client_order_ids.join(', ') || 'none' }}</p>
      }
    </section>
    <section>
      <h2>Exposure</h2>
      @if (exposureEntries().length === 0) {
        <app-empty-state title="No open exposure" detail="The local book is flat." />
      } @else {
        <table>
          <thead>
            <tr>
              <th>Key</th>
              <th>Notional</th>
            </tr>
          </thead>
          <tbody>
            @for (row of exposureEntries(); track row[0]) {
              <tr>
                <td>{{ row[0] }}</td>
                <td class="mono">{{ row[1] }}</td>
              </tr>
            }
          </tbody>
        </table>
      }
    </section>
    <section>
      <h2>Daily market plan (UTC session)</h2>
      <p class="lede">Deterministic checklist. Empty calendar means none listed — the model is not asked to invent events.</p>
      <p>
        <button type="button" (click)="loadPlan()">Refresh plan</button>
      </p>
      @if (!plan()) {
        <app-empty-state title="Daily plan unavailable" detail="Control plane must be up. This is not an order ticket." />
      } @else {
        @if (plan()!.blocks_trading) {
          <p class="banner-warn">Trading blocked: {{ plan()!.block_reason }}</p>
        }
        <p class="muted">
          {{ plan()!.instrument }} · session {{ plan()!.session_start_utc }} · as of {{ plan()!.as_of }} · is_order={{ plan()!.is_order }}
        </p>
        <table>
          <thead>
            <tr>
              <th>Phase</th>
              <th>Item</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            @for (row of plan()!.checklist; track row.phase + row.item) {
              <tr>
                <td>{{ row.phase }}</td>
                <td>{{ row.item }}</td>
                <td class="mono">{{ formatPlanValue(row) }}</td>
              </tr>
            }
          </tbody>
        </table>
      }
    </section>
    <p><a routerLink="/orders">Open orders and pending approvals</a></p>
  `,
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly portfolio = signal<PortfolioResponse | null>(null);
  readonly plan = signal<DailyPlan | null>(null);
  readonly pnlClass = pnlClass;

  ngOnInit(): void {
    this.api.portfolio().subscribe((value) => this.portfolio.set(value));
    this.loadPlan();
  }

  monitor(): BrokerMonitorSnapshot {
    return this.state.health().broker_monitor;
  }

  krakenBalanceEntries(): [string, string][] {
    return Object.entries(this.monitor().positions);
  }

  loadPlan(): void {
    this.api.dailyPlan().subscribe({
      next: (value) => this.plan.set(value),
      error: () => this.plan.set(null),
    });
  }

  formatPlanValue(row: DailyPlanItem): string {
    if (typeof row.value === 'string' || typeof row.value === 'number') {
      return String(row.value);
    }
    return JSON.stringify(row.value);
  }

  exposureEntries(): [string, string][] {
    const portfolio = this.portfolio();
    if (!portfolio) {
      return [];
    }
    return Object.entries(portfolio.exposure_per_instrument);
  }
}
