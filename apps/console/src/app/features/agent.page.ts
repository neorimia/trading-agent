import { Component, OnInit, inject, signal } from '@angular/core';
import { Accordion, AccordionContent, AccordionHeader, AccordionPanel } from 'primeng/accordion';
import { Timeline } from 'primeng/timeline';

import { ApiService } from '../core/api.service';
import { AgentEventRow } from '../core/models';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';

@Component({
  selector: 'app-agent-page',
  imports: [EmptyState, Accordion, AccordionContent, AccordionHeader, AccordionPanel, Timeline, PageHeader, PageSkeleton],
  template: `
    <div class="reveal">
      <app-page-header
        title="Agent activity"
        lede="Append-only audit trail. Proposals and analyses are not orders. Human decisions and errors stay visible."
      />
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (events().length === 0) {
        <app-empty-state title="No audit events" detail="Run a paper session to populate the log." icon="pi-clock" />
      } @else {
        <p-timeline [value]="events()">
          <ng-template #opposite let-event>
            <span class="mono">{{ event.timestamp }}</span>
          </ng-template>
          <ng-template #content let-event>
            <p class="mono">{{ event.event_type }} · {{ event.correlation_id }}</p>
            <p-accordion>
              <p-accordion-panel [value]="event.id">
                <p-accordion-header>Payload</p-accordion-header>
                <p-accordion-content>
                  <pre>{{ payload(event) }}</pre>
                </p-accordion-content>
              </p-accordion-panel>
            </p-accordion>
          </ng-template>
        </p-timeline>
      }
    </div>
  `,
})
export class AgentPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly events = signal<AgentEventRow[]>([]);
  readonly ready = signal(false);

  ngOnInit(): void {
    this.api.agentEvents().subscribe({
      next: (value) => {
        this.events.set(value.events.slice().reverse());
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
  }

  payload(event: AgentEventRow): string {
    return JSON.stringify(event.payload, null, 2);
  }
}
