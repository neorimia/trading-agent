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
  broker_monitor: {
    status: 'not_configured',
    polled_at: null,
    positions: {},
    open_client_order_ids: [],
    last_price: {},
    error: null,
    mode: 'monitor',
  },
};

const MAX_BACKOFF_MS = 10_000;

/** ng serve talks to the control plane directly; Vite's /v1 WS proxy never completes the upgrade. */
export function eventsSocketUrl(): string {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const host = location.port === '4200' ? '127.0.0.1:8767' : location.host;
  const token = localStorage.getItem('control_operator_token');
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${protocol}://${host}/v1/ws/events${query}`;
}

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
  private reconnectHandle: ReturnType<typeof setTimeout> | null = null;
  private backoffMs = 1000;
  private stopped = true;

  start(): void {
    this.stopped = false;
    this.refresh();
    this.connectSocket();
    this.pollHandle = setInterval(() => this.refresh(), 2000);
  }

  stop(): void {
    this.stopped = true;
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
    if (this.reconnectHandle) {
      clearTimeout(this.reconnectHandle);
      this.reconnectHandle = null;
    }
    this.socket?.close();
    this.socket = null;
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
    if (this.stopped) {
      return;
    }
    this.socket?.close();
    this.socket = null;
    try {
      this.socket = new WebSocket(eventsSocketUrl());
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket.onmessage = (event) => {
      this.backoffMs = 1000;
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
    this.socket.onclose = () => {
      this.socket = null;
      this.scheduleReconnect();
    };
    this.socket.onerror = () => {
      this.socket?.close();
    };
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectHandle) {
      return;
    }
    this.reconnectHandle = setTimeout(() => {
      this.reconnectHandle = null;
      this.connectSocket();
    }, this.backoffMs);
    this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
  }
}
