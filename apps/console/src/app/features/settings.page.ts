import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api.service';
import { AgentStateService } from '../core/agent-state.service';
import { SecuritySettings } from '../core/models';

@Component({
  selector: 'app-settings-page',
  imports: [FormsModule],
  template: `
    <h1>Settings and security</h1>
    <p class="lede">Secrets are never shown. Live trading stays blocked until the paper gate is passed.</p>
    @if (settings(); as s) {
      <table>
        <tbody>
          <tr><th>Environment</th><td>{{ s.environment }}</td></tr>
          <tr><th>Trading mode</th><td class="mode-{{ s.trading_mode }}">{{ s.trading_mode }}</td></tr>
          <tr><th>Live flag</th><td>{{ s.live_trading_enabled }}</td></tr>
          <tr><th>Broker paper mode</th><td>{{ s.broker_paper_mode }}</td></tr>
          <tr><th>Kraken spot key</th><td>{{ s.kraken_spot_key_present ? 'present' : 'absent' }}</td></tr>
          <tr><th>Kraken spot secret</th><td>{{ s.kraken_spot_secret_present ? 'present' : 'absent' }}</td></tr>
          <tr><th>Withdraw enabled</th><td>{{ s.withdraw_enabled }}</td></tr>
          <tr><th>IP whitelist attested</th><td>{{ s.ip_whitelist_configured }}</td></tr>
          <tr><th>Dedicated subaccount</th><td>{{ s.subaccount }}</td></tr>
          <tr><th>Operator role</th><td>{{ s.operator_role }}</td></tr>
          <tr><th>Data retention</th><td>{{ s.data_retention }}</td></tr>
          <tr><th>Webhooks</th><td>{{ s.webhooks_configured ? 'configured' : 'not configured' }}</td></tr>
          <tr><th>Notifications</th><td>{{ s.notifications_configured ? 'configured' : 'not configured' }}</td></tr>
        </tbody>
      </table>
    }
    <h2>Local operator token</h2>
    <p class="muted">Optional. Stored in this browser only. Matches CONTROL_OPERATOR_TOKEN if set.</p>
    <input [(ngModel)]="token" placeholder="Bearer token" />
    <button type="button" (click)="saveToken()">Save token</button>
  `,
})
export class SettingsPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly settings = signal<SecuritySettings | null>(null);
  token = localStorage.getItem('control_operator_token') ?? '';

  ngOnInit(): void {
    this.api.security().subscribe((value) => this.settings.set(value));
  }

  saveToken(): void {
    if (this.token.trim()) {
      localStorage.setItem('control_operator_token', this.token.trim());
    } else {
      localStorage.removeItem('control_operator_token');
    }
    this.state.refresh();
  }
}
