import { Component, OnInit, inject, signal, viewChild } from '@angular/core';
import { Button } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { Tag } from 'primeng/tag';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import { StrategyRow } from '../core/models';
import { ConfirmDanger } from '../shared/confirm-danger';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';

@Component({
  selector: 'app-strategies-page',
  imports: [ConfirmDanger, EmptyState, Button, TableModule, Tag, PageHeader, PageSkeleton],
  template: `
    <div class="reveal">
      <app-page-header
        title="Strategy center"
        lede="Enabling a strategy does not skip RiskEngine or human approval. Restart required after a change."
      />
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (rows().length === 0) {
        <app-empty-state icon="pi-sitemap" />
      } @else {
        <p-table [value]="rows()">
          <ng-template #header>
            <tr>
              <th>Strategy</th>
              <th>Kind</th>
              <th>Enabled</th>
              <th>Params</th>
              <th>Paper sessions</th>
              <th>Backtest</th>
              <th></th>
            </tr>
          </ng-template>
          <ng-template #body let-row>
            <tr>
              <td>{{ row.name }}</td>
              <td>{{ row.kind }}</td>
              <td>
                <p-tag [value]="row.enabled ? 'active' : 'inactive'" [severity]="row.enabled ? 'success' : 'secondary'" />
              </td>
              <td class="mono">{{ paramText(row) }}</td>
              <td>{{ row.last_paper_sessions ?? '-' }} @if (row.last_paper_halted) { (halted) }</td>
              <td>{{ row.last_backtest_ref ?? '-' }}</td>
              <td>
                <p-button
                  [label]="row.enabled ? 'Disable' : 'Enable'"
                  severity="secondary"
                  size="small"
                  [disabled]="!state.canMutate()"
                  (onClick)="askToggle(row)"
                />
              </td>
            </tr>
          </ng-template>
        </p-table>
      }
      <app-confirm-danger
        [title]="pending?.enabled ? 'Disable strategy' : 'Enable strategy'"
        body="This writes config/strategies.yaml. The engine picks it up on the next start. RiskEngine still sizes every order."
        [requireTyped]="pending?.enabled ? 'DISABLE_STRATEGY' : 'ENABLE_STRATEGY'"
        confirmLabel="Write config"
        (confirmed)="apply($event.reason)"
      />
    </div>
  `,
})
export class StrategiesPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly dialog = viewChild.required(ConfirmDanger);
  readonly rows = signal<StrategyRow[]>([]);
  readonly ready = signal(false);
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
    this.api.strategies().subscribe({
      next: (value) => {
        this.rows.set(value);
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
  }
}
