import { Component, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { ProgressBar } from 'primeng/progressbar';
import { TableModule } from 'primeng/table';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import { RiskLimitsView, StressReport, pnlClass } from '../core/models';
import { ConfirmDanger } from '../shared/confirm-danger';
import { EmptyState } from '../shared/empty-state';
import { MetricCard } from '../shared/metric-card';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';

@Component({
  selector: 'app-risk-page',
  imports: [
    ConfirmDanger,
    EmptyState,
    MetricCard,
    FormsModule,
    Button,
    InputText,
    Message,
    ProgressBar,
    TableModule,
    PageHeader,
    PageSkeleton,
  ],
  template: `
    <div class="reveal">
      <app-page-header
        title="Risk management"
        lede="Limits are the source of truth in YAML. Writes require typing MAX_DAILY_LOSS and a restart before they apply."
      />
      @if (state.halted()) {
        <p-message
          severity="error"
          [text]="
            'HALTED' +
            (state.health().halt_reason ? ': ' + state.health().halt_reason : '') +
            '. Clearing the flag does not restart the agent or resume orders.'
          "
        />
        <div class="toolbar">
          <p-button label="Clear halt flag" severity="danger" [disabled]="!state.canMutate()" (onClick)="askReset()" />
        </div>
      }
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (!risk()) {
        <app-empty-state icon="pi-shield" />
      } @else {
        <section class="metric-grid">
          <app-metric-card label="Daily loss remaining" [value]="risk()!.remaining_daily_loss" />
          <app-metric-card label="Drawdown remaining" [value]="risk()!.remaining_drawdown" />
          <app-metric-card label="Orders remaining" [value]="'' + risk()!.remaining_orders_today" />
          <app-metric-card label="Circuit breaker" [value]="risk()!.circuit_breaker.state" />
        </section>
        <div class="remain-row">
          <span>Daily loss remaining</span>
          <p-progressbar [value]="remainingPct(risk()!.remaining_daily_loss, risk()!.max_daily_loss)" [showValue]="false" />
        </div>
        <div class="remain-row">
          <span>Drawdown remaining</span>
          <p-progressbar [value]="remainingPct(risk()!.remaining_drawdown, risk()!.max_drawdown)" [showValue]="false" />
        </div>
        <div class="remain-row">
          <span>Orders remaining</span>
          <p-progressbar [value]="orderPct(risk()!.remaining_orders_today, risk()!.max_orders_per_day)" [showValue]="false" />
        </div>
        <p-table [value]="limitRows()">
          <ng-template #header>
            <tr>
              <th>Limit</th>
              <th>Configured</th>
              <th>Consumed</th>
              <th>Remaining</th>
            </tr>
          </ng-template>
          <ng-template #body let-row>
            <tr>
              <td>{{ row.label }}</td>
              <td class="mono">{{ row.configured }}</td>
              <td class="mono">{{ row.consumed }}</td>
              <td class="mono">{{ row.remaining }}</td>
            </tr>
          </ng-template>
        </p-table>
        <form class="stack" (ngSubmit)="askSave()">
          <label>max_daily_loss <input pInputText [(ngModel)]="draft.max_daily_loss" name="max_daily_loss" /></label>
          <label>max_drawdown <input pInputText [(ngModel)]="draft.max_drawdown" name="max_drawdown" /></label>
          <label>max_notional_per_order <input pInputText [(ngModel)]="draft.max_notional_per_order" name="max_notional_per_order" /></label>
          <label>max_exposure_per_instrument <input pInputText [(ngModel)]="draft.max_exposure_per_instrument" name="max_exposure_per_instrument" /></label>
          <label>max_exposure_per_asset_class <input pInputText [(ngModel)]="draft.max_exposure_per_asset_class" name="max_exposure_per_asset_class" /></label>
          <label>max_orders_per_day <input pInputText type="number" [(ngModel)]="draft.max_orders_per_day" name="max_orders_per_day" /></label>
          <p-button type="submit" label="Propose limit change" [disabled]="!state.canMutate()" />
        </form>
      }
      <section>
        <h2>Portfolio stress (deterministic)</h2>
        <p class="lede">
          Linear spot shock table. This is not a hedge ticket and does not place orders. Kraken path is cash spot - options are unavailable.
        </p>
        @if (!stress()) {
          <app-empty-state title="Stress unavailable" icon="pi-chart-bar" />
        } @else {
          @if (stress()!.incomplete) {
            <p-message severity="warn" text="Portfolio reconstruction is incomplete. Treat shock PnL as an estimate." />
          }
          <section class="metric-grid">
            <app-metric-card label="Total exposure" [value]="stress()!.total_exposure" />
            <app-metric-card label="HHI" [value]="stress()!.hhi" />
            <app-metric-card label="Duplicated bets" [value]="stress()!.duplicated_bets" />
            <app-metric-card label="Hedge universe" [value]="stress()!.hedge_universe" />
          </section>
          <p-table [value]="stress()!.scenarios">
            <ng-template #header>
              <tr>
                <th>Scenario</th>
                <th>Spot shock</th>
                <th>Est. PnL</th>
                <th>Est. equity Δ</th>
              </tr>
            </ng-template>
            <ng-template #body let-row>
              <tr>
                <td>{{ row.name }}</td>
                <td class="mono">{{ row.spot_shock }}</td>
                <td class="mono" [class]="pnlClass(row.estimated_pnl)">{{ row.estimated_pnl }}</td>
                <td class="mono">{{ row.estimated_equity_change_pct }}</td>
              </tr>
            </ng-template>
          </p-table>
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
    </div>
  `,
})
export class RiskPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly dialog = viewChild.required<ConfirmDanger>('limitsDialog');
  readonly resetDialog = viewChild.required<ConfirmDanger>('resetDialog');
  readonly risk = signal<RiskLimitsView | null>(null);
  readonly stress = signal<StressReport | null>(null);
  readonly ready = signal(false);
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
    this.api.riskLimits().subscribe({
      next: (value) => {
        this.risk.set(value);
        this.draft = {
          max_notional_per_order: value.max_notional_per_order,
          max_exposure_per_instrument: value.max_exposure_per_instrument,
          max_exposure_per_asset_class: value.max_exposure_per_asset_class,
          max_daily_loss: value.max_daily_loss,
          max_drawdown: value.max_drawdown,
          max_orders_per_day: value.max_orders_per_day,
        };
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
    this.api.stress().subscribe({
      next: (value) => this.stress.set(value),
      error: () => this.stress.set(null),
    });
  }

  remainingPct(remaining: string, max: string): number {
    const r = Number(remaining);
    const m = Number(max);
    if (!Number.isFinite(r) || !Number.isFinite(m) || m === 0) {
      return 0;
    }
    return Math.max(0, Math.min(100, (r / m) * 100));
  }

  orderPct(remaining: number, max: number): number {
    if (!max) {
      return 0;
    }
    return Math.max(0, Math.min(100, (remaining / max) * 100));
  }

  limitRows(): { label: string; configured: string; consumed: string; remaining: string }[] {
    const risk = this.risk();
    if (!risk) {
      return [];
    }
    return [
      {
        label: 'Max daily loss',
        configured: risk.max_daily_loss,
        consumed: risk.consumed_daily_loss,
        remaining: risk.remaining_daily_loss,
      },
      {
        label: 'Max drawdown',
        configured: risk.max_drawdown,
        consumed: risk.consumed_drawdown,
        remaining: risk.remaining_drawdown,
      },
      {
        label: 'Max orders / day',
        configured: String(risk.max_orders_per_day),
        consumed: String(risk.consumed_orders_today),
        remaining: String(risk.remaining_orders_today),
      },
      {
        label: 'Max notional / order',
        configured: risk.max_notional_per_order,
        consumed: '-',
        remaining: 'position sizing is engine-owned',
      },
    ];
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
