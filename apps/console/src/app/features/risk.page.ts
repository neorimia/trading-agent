import { Component, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api.service';
import { AgentStateService } from '../core/agent-state.service';
import { RiskLimitsView, StressReport, pnlClass } from '../core/models';
import { ConfirmDanger } from '../shared/confirm-danger';
import { EmptyState } from '../shared/empty-state';
import { MetricCard } from '../shared/metric-card';

@Component({
  selector: 'app-risk-page',
  imports: [ConfirmDanger, EmptyState, MetricCard, FormsModule],
  template: `
    <h1>Risk management</h1>
    <p class="lede">Limits are the source of truth in YAML. Writes require typing MAX_DAILY_LOSS and a restart before they apply.</p>
    @if (state.halted()) {
      <div class="banner-error">
        HALTED{{ state.health().halt_reason ? ': ' + state.health().halt_reason : '' }}.
        Clearing the flag does not restart the agent or resume orders.
      </div>
      <p>
        <button type="button" class="danger" [disabled]="!state.canMutate()" (click)="askReset()">
          Clear halt flag
        </button>
      </p>
    }
    @if (!risk()) {
      <app-empty-state />
    } @else {
      <section class="metric-grid">
        <app-metric-card label="Daily loss remaining" [value]="risk()!.remaining_daily_loss" />
        <app-metric-card label="Drawdown remaining" [value]="risk()!.remaining_drawdown" />
        <app-metric-card label="Orders remaining" [value]="'' + risk()!.remaining_orders_today" />
        <app-metric-card label="Circuit breaker" [value]="risk()!.circuit_breaker.state" />
      </section>
      <table>
        <thead>
          <tr>
            <th>Limit</th>
            <th>Configured</th>
            <th>Consumed</th>
            <th>Remaining</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Max daily loss</td>
            <td class="mono">{{ risk()!.max_daily_loss }}</td>
            <td class="mono">{{ risk()!.consumed_daily_loss }}</td>
            <td class="mono">{{ risk()!.remaining_daily_loss }}</td>
          </tr>
          <tr>
            <td>Max drawdown</td>
            <td class="mono">{{ risk()!.max_drawdown }}</td>
            <td class="mono">{{ risk()!.consumed_drawdown }}</td>
            <td class="mono">{{ risk()!.remaining_drawdown }}</td>
          </tr>
          <tr>
            <td>Max orders / day</td>
            <td class="mono">{{ risk()!.max_orders_per_day }}</td>
            <td class="mono">{{ risk()!.consumed_orders_today }}</td>
            <td class="mono">{{ risk()!.remaining_orders_today }}</td>
          </tr>
          <tr>
            <td>Max notional / order</td>
            <td class="mono">{{ risk()!.max_notional_per_order }}</td>
            <td colspan="2">position sizing is engine-owned</td>
          </tr>
        </tbody>
      </table>
      <form class="stack" (ngSubmit)="askSave()">
        <label>max_daily_loss <input [(ngModel)]="draft.max_daily_loss" name="max_daily_loss" /></label>
        <label>max_drawdown <input [(ngModel)]="draft.max_drawdown" name="max_drawdown" /></label>
        <label>max_notional_per_order <input [(ngModel)]="draft.max_notional_per_order" name="max_notional_per_order" /></label>
        <label>max_exposure_per_instrument <input [(ngModel)]="draft.max_exposure_per_instrument" name="max_exposure_per_instrument" /></label>
        <label>max_exposure_per_asset_class <input [(ngModel)]="draft.max_exposure_per_asset_class" name="max_exposure_per_asset_class" /></label>
        <label>max_orders_per_day <input type="number" [(ngModel)]="draft.max_orders_per_day" name="max_orders_per_day" /></label>
        <button type="submit" [disabled]="!state.canMutate()">Propose limit change</button>
      </form>
    }
    <section>
      <h2>Portfolio stress (deterministic)</h2>
      <p class="lede">
        Linear spot shock table. This is not a hedge ticket and does not place orders.
        Kraken path is cash spot — options are unavailable.
      </p>
      @if (!stress()) {
        <app-empty-state title="Stress unavailable" />
      } @else {
        @if (stress()!.incomplete) {
          <p class="banner-warn">Portfolio reconstruction is incomplete. Treat shock PnL as an estimate.</p>
        }
        <section class="metric-grid">
          <app-metric-card label="Total exposure" [value]="stress()!.total_exposure" />
          <app-metric-card label="HHI" [value]="stress()!.hhi" />
          <app-metric-card label="Duplicated bets" [value]="stress()!.duplicated_bets" />
          <app-metric-card label="Hedge universe" [value]="stress()!.hedge_universe" />
        </section>
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Spot shock</th>
              <th>Est. PnL</th>
              <th>Est. equity Δ</th>
            </tr>
          </thead>
          <tbody>
            @for (row of stress()!.scenarios; track row.name) {
              <tr>
                <td>{{ row.name }}</td>
                <td class="mono">{{ row.spot_shock }}</td>
                <td class="mono" [class]="pnlClass(row.estimated_pnl)">{{ row.estimated_pnl }}</td>
                <td class="mono">{{ row.estimated_equity_change_pct }}</td>
              </tr>
            }
          </tbody>
        </table>
        <p class="muted">{{ stress()!.note }} · options_available={{ stress()!.options_available }} · is_order={{ stress()!.is_order }}</p>
      }
    </section>
    <app-confirm-danger
      #limitsDialog
      title="Write risk limits"
      body="This overwrites config/risk_limits.yaml. The running engine will not hot-patch. Type MAX_DAILY_LOSS."
      requireTyped="MAX_DAILY_LOSS"
      confirmLabel="Write YAML"
      (confirmed)="save()"
    />
    <app-confirm-danger
      #resetDialog
      title="Clear halt flag"
      body="Removes halt.flag. The agent stays stopped until you start it again. New orders stay blocked until restart and a healthy venue."
      confirmLabel="Clear halt"
      (confirmed)="resetHalt()"
    />
  `,
})
export class RiskPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly dialog = viewChild.required<ConfirmDanger>('limitsDialog');
  readonly resetDialog = viewChild.required<ConfirmDanger>('resetDialog');
  readonly risk = signal<RiskLimitsView | null>(null);
  readonly stress = signal<StressReport | null>(null);
  readonly pnlClass = pnlClass;
  draft = {
    max_notional_per_order: '',
    max_exposure_per_instrument: '',
    max_exposure_per_asset_class: '',
    max_daily_loss: '',
    max_drawdown: '',
    max_orders_per_day: 10,
  };

  ngOnInit(): void {
    this.api.riskLimits().subscribe((value) => {
      this.risk.set(value);
      this.draft = {
        max_notional_per_order: value.max_notional_per_order,
        max_exposure_per_instrument: value.max_exposure_per_instrument,
        max_exposure_per_asset_class: value.max_exposure_per_asset_class,
        max_daily_loss: value.max_daily_loss,
        max_drawdown: value.max_drawdown,
        max_orders_per_day: value.max_orders_per_day,
      };
    });
    this.api.stress().subscribe({
      next: (value) => this.stress.set(value),
      error: () => this.stress.set(null),
    });
  }

  askSave(): void {
    this.dialog().open();
  }

  askReset(): void {
    this.resetDialog().open();
  }

  resetHalt(): void {
    this.api.resetHalt().subscribe(() => this.state.refresh());
  }

  save(): void {
    const current = this.risk();
    if (!current) {
      return;
    }
    this.api
      .writeRiskLimits({
        ...this.draft,
        circuit_breaker: {
          max_consecutive_errors: current.circuit_breaker.max_consecutive_errors,
          max_consecutive_losses: current.circuit_breaker.max_consecutive_losses,
          halt_on_unknown_order_result: current.circuit_breaker.halt_on_unknown_order_result,
        },
        confirmation_token: 'MAX_DAILY_LOSS',
      })
      .subscribe(() => this.ngOnInit());
  }
}
