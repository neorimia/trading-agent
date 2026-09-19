import { Component, OnInit, inject, signal } from '@angular/core';

import { ApiService } from '../core/api.service';
import { AgentEventRow } from '../core/models';
import { EmptyState } from '../shared/empty-state';

@Component({
  selector: 'app-agent-page',
  imports: [EmptyState],
  template: `
    <h1>Agent activity</h1>
    <p class="lede">Append-only audit trail. Proposals are not orders. Human decisions and errors stay visible.</p>
    @if (events().length === 0) {
      <app-empty-state title="No audit events" detail="Run a paper session to populate the log." />
    }
    <ol class="timeline">
      @for (event of events(); track event.id) {
        <li>
          <p class="mono">{{ event.timestamp }} · {{ event.event_type }} · {{ event.correlation_id }}</p>
          <pre>{{ payload(event) }}</pre>
        </li>
      }
    </ol>
  `,
})
export class AgentPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly events = signal<AgentEventRow[]>([]);

  ngOnInit(): void {
    this.api.agentEvents().subscribe((value) => this.events.set(value.events.slice().reverse()));
  }

  payload(event: AgentEventRow): string {
    return JSON.stringify(event.payload, null, 2);
  }
}
