import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { TableModule } from 'primeng/table';
import { Tag } from 'primeng/tag';
import { Tooltip } from 'primeng/tooltip';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import { liveApproveBlocked } from '../core/permission.guard';
import { OrderRow, PendingApproval, PositionRow, formatQuote, pnlClass } from '../core/models';
import { ConfirmDanger } from '../shared/confirm-danger';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';

@Component({
  selector: 'app-orders-page',
  imports: [
    ConfirmDanger,
    EmptyState,
    FormsModule,
    DatePipe,
    DecimalPipe,
    Button,
    InputText,
    Message,
    TableModule,
    Tag,
    Tooltip,
    PageHeader,
    PageSkeleton,
  ],
  template: `
    <div class="reveal">
      <app-page-header
        title="Orders and positions"
        [lede]="
          (state.paper() ? 'PAPER TRADING' : 'LIVE TRADING') +
          ' - every live order would show notional, price, fee and estimated risk. Live approve is blocked in this build.'
        "
      />
      <h2>Pending human approval</h2>
      @if (state.pending().length === 0) {
        <app-empty-state title="No pending approvals" detail="The agent is not waiting on an operator decision." icon="pi-check-circle" />
      }
      @for (item of state.pending(); track item.correlation_id) {
        <article class="ticket" [class.live-mode]="item.trading_mode === 'live'">
          <p-tag [value]="item.trading_mode" [severity]="item.trading_mode === 'live' ? 'warn' : 'info'" />
          <p>{{ item.side }} {{ fmt(item.quantity) }} {{ item.instrument }}</p>
          <p>
            Last {{ fmt(item.last_price) }} · notional est. {{ fmt(item.estimated_notional) }} · remaining
            {{ item.remaining_s | number: '1.0-0' }}s
          </p>
          <p class="muted">{{ item.rationale || 'No rationale attached' }}</p>
          @if (item.approve_blocked_reason) {
            <p-message severity="warn" [text]="'Approve blocked: ' + item.approve_blocked_reason" />
          }
          <div class="dialog-actions">
            <p-button label="Approve" [disabled]="!canApprove(item)" (onClick)="choose(item, true)" />
            <p-button label="Reject" severity="danger" [disabled]="!state.canMutate()" (onClick)="choose(item, false)" />
          </div>
        </article>
      }
      <h2>Positions</h2>
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (positions().length === 0) {
        <app-empty-state title="No positions" icon="pi-minus-circle" />
      } @else {
        <div class="table-scroll">
        <p-table [value]="positions()">
          <ng-template #header>
            <tr>
              <th>Instrument</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>Last</th>
              <th>Stop</th>
              <th>Take profit</th>
              <th>uP&amp;L</th>
            </tr>
          </ng-template>
          <ng-template #body let-row>
            <tr>
              <td>{{ row.instrument }}</td>
              <td class="mono">{{ fmt(row.quantity) }}</td>
              <td class="mono">{{ fmt(row.entry_price) }}</td>
              <td class="mono">{{ fmt(row.last_price) }}</td>
              <td class="mono">{{ fmt(row.stop_loss) }}</td>
              <td>{{ fmt(row.take_profit) }}</td>
              <td class="mono" [class]="pnlClass(row.unrealized_pnl)">{{ fmt(row.unrealized_pnl) }}</td>
            </tr>
          </ng-template>
        </p-table>
        </div>
      }
      <h2>Order history</h2>
      <div class="toolbar">
        <label>
          Status
          <input pInputText [(ngModel)]="statusFilter" (ngModelChange)="loadOrders()" placeholder="Filter status" />
        </label>
        <label>
          Instrument
          <input pInputText [(ngModel)]="instrumentFilter" placeholder="Filter instrument" />
        </label>
      </div>
      @if (orders().length === 0) {
        <app-empty-state title="No orders in the audit log" icon="pi-book" />
      } @else if (filteredOrders().length === 0) {
        <app-empty-state title="No orders match this instrument filter" icon="pi-filter-slash" />
      } @else {
        <div class="table-scroll">
        <p-table [value]="filteredOrders()" [paginator]="true" [rows]="20" [rowsPerPageOptions]="[20, 50, 100]">
          <ng-template #header>
            <tr>
              <th>Time</th>
              <th>Mode</th>
              <th>Instrument</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Status</th>
              <th>Fill</th>
              <th>Fee</th>
              <th>Slippage</th>
              <th>Reason</th>
              <th>Correlation</th>
            </tr>
          </ng-template>
          <ng-template #body let-row>
            <tr>
              <td class="mono">{{ row.timestamp | date: 'yyyy-MM-dd HH:mm:ss' }}</td>
              <td>{{ row.trading_mode }}</td>
              <td>{{ row.instrument || '-' }}</td>
              <td>{{ row.side }}</td>
              <td class="mono">{{ fmt(row.quantity) }}</td>
              <td>{{ row.status }}</td>
              <td class="mono">{{ fmt(row.fill_price) }}</td>
              <td class="mono">{{ fmt(row.fee) }}</td>
              <td class="mono">{{ fmt(row.slippage) }}</td>
              <td>{{ row.reason || '-' }}</td>
              <td class="mono" [pTooltip]="row.correlation_id" tooltipPosition="top">{{ shortId(row.correlation_id) }}</td>
            </tr>
          </ng-template>
        </p-table>
        </div>
      }
      <app-confirm-danger
        [title]="approveNext ? 'Approve order' : 'Reject order'"
        [body]="confirmBody()"
        confirmLabel="Record decision"
        (confirmed)="submit($event.reason)"
      />
    </div>
  `,
})
export class OrdersPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly dialog = viewChild.required(ConfirmDanger);
  readonly positions = signal<PositionRow[]>([]);
  readonly orders = signal<OrderRow[]>([]);
  readonly ready = signal(false);
  readonly fmt = formatQuote;
  readonly pnlClass = pnlClass;
  statusFilter = '';
  instrumentFilter = '';
  selected: PendingApproval | null = null;
  approveNext = false;

  // Plain method, not computed(): instrumentFilter is a template-bound field, not a signal,
  // so a computed() here would cache on the `orders` signal only and miss filter keystrokes.
  filteredOrders(): OrderRow[] {
    const filter = this.instrumentFilter.trim().toLowerCase();
    const rows = this.orders();
    if (!filter) {
      return rows;
    }
    return rows.filter((row) => row.instrument.toLowerCase().includes(filter));
  }

  shortId(id: string): string {
    return id.length > 8 ? `${id.slice(0, 8)}…` : id;
  }

  ngOnInit(): void {
    this.api.positions().subscribe({
      next: (value) => {
        this.positions.set(value);
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
    this.loadOrders();
  }

  loadOrders(): void {
    this.api.orders(this.statusFilter || undefined).subscribe((value) => this.orders.set(value));
  }

  canApprove(item: PendingApproval): boolean {
    if (!this.state.canMutate() || item.approve_blocked_reason) {
      return false;
    }
    if (item.trading_mode === 'live' || liveApproveBlocked()) {
      return false;
    }
    return true;
  }

  confirmBody(): string {
    const item = this.selected;
    if (!item) {
      return '';
    }
    return `${item.trading_mode.toUpperCase()} ${item.side} ${formatQuote(item.quantity)} ${item.instrument} at last ${formatQuote(item.last_price)}, notional est. ${formatQuote(item.estimated_notional)}. Expiry defaults to reject.`;
  }

  choose(item: PendingApproval, approved: boolean): void {
    this.selected = item;
    this.approveNext = approved;
    this.dialog().open();
  }

  submit(reason: string): void {
    const item = this.selected;
    if (!item) {
      return;
    }
    this.api.decideApproval(item.correlation_id, this.approveNext, reason).subscribe(() => {
      this.state.refresh();
      this.loadOrders();
    });
  }
}
