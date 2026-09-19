import { Component, OnDestroy, OnInit, inject, viewChild } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Badge } from 'primeng/badge';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';
import { Tag } from 'primeng/tag';

import { AgentStateService } from './core/agent-state.service';
import { ApiService } from './core/api.service';
import { ConsoleErrorHandler } from './core/error-handler';
import { ConfirmDanger } from './shared/confirm-danger';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Badge, Button, Message, Tag, ConfirmDanger],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit, OnDestroy {
  readonly state = inject(AgentStateService);
  readonly errors = inject(ConsoleErrorHandler);
  private readonly api = inject(ApiService);
  readonly haltDialog = viewChild.required<ConfirmDanger>('haltDialog');
  readonly startDialog = viewChild.required<ConfirmDanger>('startDialog');

  heartbeatLabel(): string {
    const age = this.state.health().heartbeat_age_s;
    if (age == null) {
      return 'n/a';
    }
    return `${age}s`;
  }

  ngOnInit(): void {
    this.state.start();
  }

  ngOnDestroy(): void {
    this.state.stop();
  }

  askHalt(): void {
    this.haltDialog().open();
  }

  onHalt(payload: { reason: string }): void {
    this.api.halt(payload.reason).subscribe(() => this.state.refresh());
  }

  askStart(): void {
    this.startDialog().open();
  }

  onStart(): void {
    this.api.startAgent().subscribe(() => this.state.refresh());
  }

  onStop(): void {
    this.api.stopAgent().subscribe(() => this.state.refresh());
  }
}
