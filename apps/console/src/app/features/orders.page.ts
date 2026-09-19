import { DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api.service';
import { AgentStateService } from '../core/agent-state.service';
import { liveApproveBlocked } from '../core/permission.guard';
import { OrderRow, PendingApproval, PositionRow } from '../core/models';
import { ConfirmDanger } from '../shared/confirm-danger';
import { EmptyState } from '../shared/empty-state';

@Component({
  selector: 'app-orders-page',
  imports: [ConfirmDanger, EmptyState, FormsModule, DecimalPipe],
  template: `
    <h1>Orders and positions</h1>
    <p class="lede">
      {{ state.paper() ? 'PAPER TRADING' : 'LIVE TRADING' }} —
      every live order would show notional, price, fee and estimated risk. Live approve is blocked in this build.
    </p>
    <h2>Pending human approval</h2>
    @if (state.pending().length === 0) {
      <app-empty-state title="No pending approvals" detail="The agent is not waiting on an operator decision." />
    }
    @for (item of state.pending(); track item.correlation_id) {
      <article class="card order-card" [class.live-mode]="item.trading_mode === 'live'">
        <p class="mode-pill">{{ item.trading_mode }}</p>
        <p>{{ item.side }} {{ item.quantity }} {{ item.instrument }}</p>
        <p>Last {{ item.last_price ?? '—' }} · notional est. {{ item.estimated_notional ?? '—' }} · remaining {{ item.remaining_s | number: '1.0-0' }}s</p>
        <p class="muted">{{ item.rationale || 'No rationale attached' }}</p>
        @if (item.approve_blocked_reason) {
          <p class="banner-warn">Approve blocked: {{ item.approve_blocked_reason }}</p>
        }
        <div class="dialog-actions">
          <button type="button" [disabled]="!canApprove(item)" (click)="choose(item, true)">Approve</button>
          <button type="button" class="danger" [disabled]="!state.canMutate()" (click)="choose(item, false)">Reject</button>
        </div>
      </article>
    }
    <h2>Positions</h2>
    @if (positions().length === 0) {
      <app-empty-state title="No positions" />
    } @else {
      <table>
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Qty</th>
            <th>Entry</th>
            <th>Last</th>
            <th>Stop</th>
            <th>Take profit</th>
            <th>uP&amp;L</th>
          </tr>
        </thead>
        <tbody>
          @for (row of positions(); track row.instrument) {
            <tr>
              <td>{{ row.instrument }}</td>
              <td class="mono">{{ row.quantity }}</td>
              <td class="mono">{{ row.entry_price ?? '—' }}</td>
              <td class="mono">{{ row.last_price ?? '—' }}</td>
              <td class="mono">{{ row.stop_loss ?? '—' }}</td>
              <td>{{ row.take_profit ?? '—' }}</td>
              <td class="mono">{{ row.unrealized_pnl ?? '—' }}</td>
            </tr>
          }
        </tbody>
      </table>
    }
    <h2>Order history</h2>
    <label>Status <input [(ngModel)]="statusFilter" (ngModelChange)="loadOrders()" /></label>
    @if (orders().length === 0) {
      <app-empty-state title="No orders in the audit log" />
    } @else {
      <table>
        <thead>
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
            <th>Correlation</th>
          </tr>
        </thead>
        <tbody>
          @for (row of orders(); track row.correlation_id + row.status + row.timestamp) {
            <tr>
              <td class="mono">{{ row.timestamp }}</td>
              <td>{{ row.trading_mode }}</td>
              <td>{{ row.instrument }}</td>
              <td>{{ row.side }}</td>
              <td class="mono">{{ row.quantity }}</td>
              <td>{{ row.status }}</td>
              <td class="mono">{{ row.fill_price ?? '—' }}</td>
              <td class="mono">{{ row.fee ?? '—' }}</td>
              <td class="mono">{{ row.slippage ?? '—' }}</td>
              <td class="mono">{{ row.correlation_id }}</td>
            </tr>
          }
        </tbody>
      </table>
    }
    <app-confirm-danger
      [title]="approveNext ? 'Approve order' : 'Reject order'"
      [body]="confirmBody()"
      confirmLabel="Record decision"
      (confirmed)="submit($event.reason)"
    />
  `,
})
export class OrdersPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly dialog = viewChild.required(ConfirmDanger);
  readonly positions = signal<PositionRow[]>([]);
  readonly orders = signal<OrderRow[]>([]);
  statusFilter = '';
  selected: PendingApproval | null = null;
  approveNext = false;

  ngOnInit(): void {
    this.api.positions().subscribe((value) => this.positions.set(value));
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
    return `${item.trading_mode.toUpperCase()} ${item.side} ${item.quantity} ${item.instrument} at last ${item.last_price ?? 'n/a'}, notional est. ${item.estimated_notional ?? 'n/a'}. Expiry defaults to reject.`;
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
