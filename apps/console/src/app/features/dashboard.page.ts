import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../core/api.service';
import { AgentStateService } from '../core/agent-state.service';
import { PortfolioResponse, pnlClass } from '../core/models';
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
    <p><a routerLink="/orders">Open orders and pending approvals</a></p>
  `,
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly portfolio = signal<PortfolioResponse | null>(null);
  readonly pnlClass = pnlClass;

  ngOnInit(): void {
    this.api.portfolio().subscribe((value) => this.portfolio.set(value));
  }

  exposureEntries(): [string, string][] {
    const portfolio = this.portfolio();
    if (!portfolio) {
      return [];
    }
    return Object.entries(portfolio.exposure_per_instrument);
  }
}
