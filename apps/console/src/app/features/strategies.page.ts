import { Component, OnInit, inject, signal, viewChild } from '@angular/core';

import { ApiService } from '../core/api.service';
import { AgentStateService } from '../core/agent-state.service';
import { StrategyRow } from '../core/models';
import { ConfirmDanger } from '../shared/confirm-danger';
import { EmptyState } from '../shared/empty-state';

@Component({
  selector: 'app-strategies-page',
  imports: [ConfirmDanger, EmptyState],
  template: `
    <h1>Strategy center</h1>
    <p class="lede">Enabling a strategy does not skip RiskEngine or human approval. Restart required after a change.</p>
    @if (rows().length === 0) {
      <app-empty-state />
    }
    <table>
      <thead>
        <tr>
          <th>Strategy</th>
          <th>Kind</th>
          <th>Enabled</th>
          <th>Params</th>
          <th>Paper sessions</th>
          <th>Backtest</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        @for (row of rows(); track row.id) {
          <tr>
            <td>{{ row.name }}</td>
            <td>{{ row.kind }}</td>
            <td>{{ row.enabled ? 'active' : 'inactive' }}</td>
            <td class="mono">{{ paramText(row) }}</td>
            <td>{{ row.last_paper_sessions ?? '—' }} @if (row.last_paper_halted) { (halted) }</td>
            <td>{{ row.last_backtest_ref ?? '—' }}</td>
            <td>
              <button type="button" [disabled]="!state.canMutate()" (click)="askToggle(row)">
                {{ row.enabled ? 'Disable' : 'Enable' }}
              </button>
            </td>
          </tr>
        }
      </tbody>
    </table>
    <app-confirm-danger
      [title]="pending?.enabled ? 'Disable strategy' : 'Enable strategy'"
      body="This writes config/strategies.yaml. The engine picks it up on the next start. RiskEngine still sizes every order."
      [requireTyped]="pending?.enabled ? 'DISABLE_STRATEGY' : 'ENABLE_STRATEGY'"
      confirmLabel="Write config"
      (confirmed)="apply($event.reason)"
    />
  `,
})
export class StrategiesPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly dialog = viewChild.required(ConfirmDanger);
  readonly rows = signal<StrategyRow[]>([]);
  pending: StrategyRow | null = null;

  ngOnInit(): void {
    this.reload();
  }

  paramText(row: StrategyRow): string {
    return Object.entries(row.params)
      .map(([key, value]) => `${key}=${value}`)
      .join(' ');
  }

  askToggle(row: StrategyRow): void {
    this.pending = row;
    this.dialog().open();
  }

  apply(_reason: string): void {
    const row = this.pending;
    if (!row) {
      return;
    }
    const enabled = !row.enabled;
    const token = enabled ? 'ENABLE_STRATEGY' : 'DISABLE_STRATEGY';
    this.api.toggleStrategy(row.id, enabled, token).subscribe(() => this.reload());
  }

  private reload(): void {
    this.api.strategies().subscribe((value) => this.rows.set(value));
  }
}
