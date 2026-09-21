import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Message } from 'primeng/message';
import { TableModule } from 'primeng/table';
import { Tag } from 'primeng/tag';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import { DailyPlan, PortfolioResponse, BrokerMonitorSnapshot, formatQuote, pnlClass } from '../core/models';
import { EmptyState } from '../shared/empty-state';
import { MetricCard } from '../shared/metric-card';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';
import { SessionPlan } from '../shared/session-plan';
import { PlanStatus } from '../shared/session-plan.util';

@Component({
  selector: 'app-dashboard-page',
  imports: [MetricCard, EmptyState, RouterLink, Message, TableModule, Tag, PageHeader, PageSkeleton, SessionPlan],
  template: `
    <div class="reveal">
      <app-page-header title="Dashboard" lede="Operator overview. Numbers are facts from the local engine, not forecasts.">
        <a routerLink="/orders">Open orders</a>
      </app-page-header>
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (!portfolio()) {
        <app-empty-state title="Portfolio unavailable" detail="Start the control plane to load local state." icon="pi-wallet" />
      } @else {
        @if (portfolio()!.incomplete) {
          <p-message severity="warn" text="Portfolio reconstruction is incomplete. Treat P&L as an estimate." />
        }
        <h2>Paper book (simulated)</h2>
        <section class="pnl-strip">
          <app-metric-card label="Equity" [value]="portfolio()!.equity" [decimals]="2" hint="USD" size="hero" />
          <section class="metric-grid">
            <app-metric-card label="Cash" [value]="portfolio()!.cash" [decimals]="2" hint="USD" />
            <app-metric-card
              label="Realized P&L"
              [value]="portfolio()!.realized_pnl"
              [decimals]="2"
              hint="USD"
              [valueClass]="pnlClass(portfolio()!.realized_pnl)"
            />
            <app-metric-card
              label="Unrealized P&L"
              [value]="portfolio()!.unrealized_pnl"
              [decimals]="2"
              hint="USD · est. from last bar"
              [valueClass]="pnlClass(portfolio()!.unrealized_pnl)"
            />
            <app-metric-card label="Drawdown" [value]="portfolio()!.drawdown" [decimals]="2" hint="USD" />
            <app-metric-card label="Orders today" [value]="portfolio()!.orders_today" [decimals]="0" />
          </section>
        </section>
      }
      <section class="split">
        <article class="panel secondary">
          <h2>Exposure</h2>
          @if (!ready()) {
            <p class="muted">Loading book…</p>
          } @else if (exposureEntries().length === 0) {
            <app-empty-state title="No open exposure" detail="The local book is flat." icon="pi-minus-circle" />
          } @else {
            <p-table [value]="exposureEntries()" [tableStyle]="{ 'min-width': '16rem' }">
              <ng-template #header>
                <tr>
                  <th>Key</th>
                  <th>Notional</th>
                </tr>
              </ng-template>
              <ng-template #body let-row>
                <tr>
                  <td>{{ row[0] }}</td>
                  <td class="mono">{{ row[1] }}</td>
                </tr>
              </ng-template>
            </p-table>
          }
        </article>
        <app-session-plan
          [plan]="plan()"
          [status]="planStatus()"
          [loading]="planLoading()"
          (refresh)="loadPlan()"
        />
      </section>
      <section class="panel">
        <h2>Kraken account (monitor)</h2>
        <p class="lede">Query-only Balance/OpenOrders. This is not the paper book and cannot place orders.</p>
        @if (monitor().status === 'not_configured') {
          <app-empty-state
            title="Monitor not configured"
            detail="Paper still runs without keys. Add Query-only Kraken spot keys (Withdraw off) to observe the real account."
            icon="pi-key"
          />
        } @else if (monitor().status === 'error') {
          <p-message severity="warn" [text]="'Monitor error: ' + (monitor().error || 'poll failed')" />
        } @else {
          <p class="doc-meta">
            <p-tag [value]="monitor().status" severity="success" />
            <span class="muted">polled {{ monitor().polled_at || 'n/a' }}</span>
          </p>
          @if (krakenBalanceEntries().length === 0) {
            <app-empty-state title="No Kraken balances" detail="Spot query returned an empty book." icon="pi-wallet" />
          } @else {
            <p-table [value]="krakenBalanceEntries()">
              <ng-template #header>
                <tr>
                  <th>Asset</th>
                  <th>Quantity</th>
                </tr>
              </ng-template>
              <ng-template #body let-row>
                <tr>
                  <td>{{ row[0] }}</td>
                  <td class="mono">{{ row[1] }}</td>
                </tr>
              </ng-template>
            </p-table>
          }
          <p class="muted">Open client order ids: {{ monitor().open_client_order_ids.join(', ') || 'none' }}</p>
        }
      </section>
    </div>
  `,
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly portfolio = signal<PortfolioResponse | null>(null);
  readonly plan = signal<DailyPlan | null>(null);
  readonly planStatus = signal<PlanStatus>('loading');
  readonly planLoading = signal(false);
  readonly ready = signal(false);
  readonly pnlClass = pnlClass;

  ngOnInit(): void {
    this.api.portfolio().subscribe({
      next: (value) => {
        this.portfolio.set(value);
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
    this.loadPlan();
  }

  monitor(): BrokerMonitorSnapshot {
    return this.state.health().broker_monitor;
  }

  krakenBalanceEntries(): [string, string][] {
    return Object.entries(this.monitor().positions).map(
      ([asset, quantity]) => [asset, formatQuote(quantity)] as [string, string],
    );
  }

  loadPlan(): void {
    this.planLoading.set(true);
    if (!this.plan()) {
      this.planStatus.set('loading');
    }
    this.api.dailyPlan().subscribe({
      next: (value) => {
        this.plan.set(value);
        this.planStatus.set('ready');
        this.planLoading.set(false);
      },
      error: () => {
        this.plan.set(null);
        this.planStatus.set('error');
        this.planLoading.set(false);
      },
    });
  }

  exposureEntries(): [string, string][] {
    const portfolio = this.portfolio();
    if (!portfolio) {
      return [];
    }
    return Object.entries(portfolio.exposure_per_instrument).map(
      ([key, notional]) => [key, formatQuote(notional, { decimals: 2 })] as [string, string],
    );
  }
}
