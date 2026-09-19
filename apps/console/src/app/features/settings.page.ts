import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Tag } from 'primeng/tag';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import { SecuritySettings } from '../core/models';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';

@Component({
  selector: 'app-settings-page',
  imports: [FormsModule, Button, InputText, Tag, PageHeader, PageSkeleton],
  template: `
    <div class="reveal">
      <app-page-header
        title="Settings and security"
        lede="Secrets are never shown. Live trading stays blocked until the paper gate is passed."
      />
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (settings(); as s) {
        <dl class="facts">
          <div><dt>Environment</dt><dd>{{ s.environment }}</dd></div>
          <div>
            <dt>Trading mode</dt>
            <dd><p-tag [value]="s.trading_mode" [severity]="s.trading_mode === 'live' ? 'warn' : 'info'" /></dd>
          </div>
          <div><dt>Live flag</dt><dd>{{ s.live_trading_enabled }}</dd></div>
          <div><dt>Broker paper mode</dt><dd>{{ s.broker_paper_mode }}</dd></div>
          <div><dt>Kraken spot key</dt><dd>{{ s.kraken_spot_key_present ? 'present' : 'absent' }}</dd></div>
          <div><dt>Kraken spot secret</dt><dd>{{ s.kraken_spot_secret_present ? 'present' : 'absent' }}</dd></div>
          <div><dt>Withdraw enabled</dt><dd>{{ s.withdraw_enabled }}</dd></div>
          <div><dt>IP whitelist attested</dt><dd>{{ s.ip_whitelist_configured }}</dd></div>
          <div><dt>Dedicated subaccount</dt><dd>{{ s.subaccount }}</dd></div>
          <div><dt>Operator role</dt><dd>{{ s.operator_role }}</dd></div>
          <div><dt>Data retention</dt><dd>{{ s.data_retention }}</dd></div>
          <div><dt>Webhooks</dt><dd>{{ s.webhooks_configured ? 'configured' : 'not configured' }}</dd></div>
          <div><dt>Notifications</dt><dd>{{ s.notifications_configured ? 'configured' : 'not configured' }}</dd></div>
        </dl>
      }
      <h2>Local operator token</h2>
      <p class="muted">Optional. Stored in this browser only. Matches CONTROL_OPERATOR_TOKEN if set.</p>
      <div class="toolbar">
        <input pInputText [(ngModel)]="token" placeholder="Bearer token" aria-label="Operator token" />
        <p-button label="Save token" (onClick)="saveToken()" />
      </div>
    </div>
  `,
})
export class SettingsPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly settings = signal<SecuritySettings | null>(null);
  readonly ready = signal(false);
  token = localStorage.getItem('control_operator_token') ?? '';

  ngOnInit(): void {
    this.api.security().subscribe({
      next: (value) => {
        this.settings.set(value);
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
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
