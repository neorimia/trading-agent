import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiService } from './api.service';
import {
  AlertRow,
  HealthResponse,
  PendingApproval,
  SecuritySettings,
  WsEnvelope,
} from './models';

const EMPTY_HEALTH: HealthResponse = {
  agent: 'stopped',
  venue: 'down',
  llm: 'down',
  research: 'down',
  trading_mode: 'paper',
  heartbeat_age_s: null,
  last_bar_at: null,
  last_bar_instrument: null,
  reconciliation: 'unknown',
  halt_reason: null,
  live_actions_blocked: true,
};

@Injectable({ providedIn: 'root' })
export class AgentStateService {
  private readonly api = inject(ApiService);
  readonly health = signal<HealthResponse>(EMPTY_HEALTH);
  readonly alerts = signal<AlertRow[]>([]);
  readonly pending = signal<PendingApproval[]>([]);
  readonly security = signal<SecuritySettings | null>(null);
  readonly connectionError = signal<string | null>(null);
  readonly paper = computed(() => this.health().trading_mode === 'paper');
  readonly halted = computed(() => this.health().agent === 'halted');
  readonly canMutate = computed(() => this.security()?.operator_role !== 'observer');

  private socket: WebSocket | null = null;
  private pollHandle: ReturnType<typeof setInterval> | null = null;

  start(): void {
    this.refresh();
    this.connectSocket();
    this.pollHandle = setInterval(() => this.refresh(), 2000);
  }

  stop(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
    }
    this.socket?.close();
  }

  refresh(): void {
    this.api.health().subscribe({
      next: (value) => {
        this.health.set(value);
        this.connectionError.set(null);
      },
      error: () => this.connectionError.set('Control plane unreachable on loopback.'),
    });
    this.api.alerts().subscribe({ next: (value) => this.alerts.set(value) });
    this.api.pendingApprovals().subscribe({ next: (value) => this.pending.set(value) });
    this.api.security().subscribe({ next: (value) => this.security.set(value) });
  }

  private connectSocket(): void {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const token = localStorage.getItem('control_operator_token');
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    const url = `${protocol}://${location.host}/v1/ws/events${query}`;
    try {
      this.socket = new WebSocket(url);
    } catch {
      return;
    }
    this.socket.onmessage = (event) => {
      const envelope = JSON.parse(event.data) as WsEnvelope;
      if (envelope.channel === 'health') {
        this.health.set(envelope.payload as unknown as HealthResponse);
        this.connectionError.set(null);
      }
      if (envelope.channel === 'alerts' && Array.isArray(envelope.payload['items'])) {
        this.alerts.set(envelope.payload['items'] as AlertRow[]);
      }
      if (envelope.channel === 'approvals' && Array.isArray(envelope.payload['items'])) {
        this.pending.set(envelope.payload['items'] as PendingApproval[]);
      }
    };
  }
}
