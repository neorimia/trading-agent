import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Accordion, AccordionContent, AccordionHeader, AccordionPanel } from 'primeng/accordion';
import { Button } from 'primeng/button';
import { DatePicker } from 'primeng/datepicker';
import { Select } from 'primeng/select';
import { Timeline } from 'primeng/timeline';

import { ApiService } from '../core/api.service';
import { AgentEventRow } from '../core/models';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';

@Component({
  selector: 'app-agent-page',
  imports: [
    EmptyState,
    DatePipe,
    FormsModule,
    Accordion,
    AccordionContent,
    AccordionHeader,
    AccordionPanel,
    Button,
    DatePicker,
    Select,
    Timeline,
    PageHeader,
    PageSkeleton,
  ],
  template: `
    <div class="reveal">
      <app-page-header
        title="Agent activity"
        lede="Append-only audit trail. Proposals and analyses are not orders. Human decisions and errors stay visible."
      />
      <div class="toolbar">
        <label>
          Event type
          <p-select [(ngModel)]="typeFilter" [options]="typeOptions()" optionLabel="label" optionValue="value" placeholder="All types" [showClear]="true" />
        </label>
        <label>
          From
          <p-date-picker [(ngModel)]="fromDate" dateFormat="yy-mm-dd" [showIcon]="true" [showButtonBar]="true" />
        </label>
        <label>
          To
          <p-date-picker [(ngModel)]="toDate" dateFormat="yy-mm-dd" [showIcon]="true" [showButtonBar]="true" />
        </label>
        @if (typeFilter || fromDate || toDate) {
          <p-button label="Clear filters" severity="secondary" [text]="true" (onClick)="clearFilters()" />
        }
      </div>
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (events().length === 0) {
        <app-empty-state title="No audit events" detail="Run a paper session to populate the log." icon="pi-clock" />
      } @else if (filteredEvents().length === 0) {
        <app-empty-state title="No events match these filters" icon="pi-filter-slash" />
      } @else {
        <p-timeline [value]="filteredEvents()">
          <ng-template #opposite let-event>
            <span class="mono">{{ event.timestamp | date: 'yyyy-MM-dd HH:mm:ss' }}</span>
          </ng-template>
          <ng-template #content let-event>
            <p>{{ summarize(event) }}</p>
            <p class="muted mono">{{ event.event_type }} · {{ event.correlation_id }}</p>
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
  typeFilter: string | null = null;
  fromDate: Date | null = null;
  toDate: Date | null = null;

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

  typeOptions(): { label: string; value: string }[] {
    const types = new Set(this.events().map((event) => event.event_type));
    return Array.from(types)
      .sort()
      .map((type) => ({ label: type, value: type }));
  }

  filteredEvents(): AgentEventRow[] {
    const from = this.fromDate ? startOfDay(this.fromDate).getTime() : null;
    const to = this.toDate ? endOfDay(this.toDate).getTime() : null;
    return this.events().filter((event) => {
      if (this.typeFilter && event.event_type !== this.typeFilter) {
        return false;
      }
      const ts = new Date(event.timestamp).getTime();
      if (from !== null && ts < from) {
        return false;
      }
      if (to !== null && ts > to) {
        return false;
      }
      return true;
    });
  }

  clearFilters(): void {
    this.typeFilter = null;
    this.fromDate = null;
    this.toDate = null;
  }

  /** Human-readable one-liner per event type; falls back to the raw type for anything unmapped. */
  summarize(event: AgentEventRow): string {
    const p = event.payload;
    const instrument = str(p['instrument']);
    switch (event.event_type) {
      case 'order_submitted':
        return `Order submitted: ${str(p['side'])} ${str(p['quantity'])} ${instrument}`.trim();
      case 'fill':
        return `Fill: ${instrument} @ ${str(p['fill_price'])}`.trim();
      case 'risk_decision':
        return p['approved'] === false
          ? `Risk decision: blocked${instrument ? ` — ${instrument}` : ''}${p['reason'] ? ` (${str(p['reason'])})` : ''}`
          : `Risk decision: approved${instrument ? ` — ${instrument}` : ''}`;
      case 'human_approval':
        return `Human approval: ${p['approved'] ? 'approved' : 'rejected'}${instrument ? ` — ${instrument}` : ''}`;
      case 'proposal':
        return `Proposal: ${str(p['action']) || 'action'} ${instrument}`.trim();
      case 'rejected_proposal':
        return `Proposal rejected${instrument ? `: ${instrument}` : ''}${p['reason'] ? ` (${str(p['reason'])})` : ''}`;
      case 'analysis':
        return `Analysis run: ${str(p['analysis_type']) || 'analysis'} ${instrument}`.trim();
      case 'discovery_summary':
        return `Discovery summary: ${str(p['candidate_count']) || str(p['count']) || '?'} candidates`;
      case 'halt':
        return `Trading halted${p['reason'] ? `: ${str(p['reason'])}` : ''}`;
      case 'operator_action':
        return `Operator action: ${str(p['action']) || 'unspecified'}`;
      case 'reconciliation_mismatch':
        return `Reconciliation mismatch${instrument ? `: ${instrument}` : ''}`;
      case 'run_bar_error':
        return `Bar processing error${p['message'] ? `: ${str(p['message'])}` : ''}`;
      default:
        return event.event_type;
    }
  }
}

function str(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

function startOfDay(date: Date): Date {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

function endOfDay(date: Date): Date {
  const d = new Date(date);
  d.setHours(23, 59, 59, 999);
  return d;
}
