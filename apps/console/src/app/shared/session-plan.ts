import { Component, EventEmitter, Output, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';
import { Skeleton } from 'primeng/skeleton';
import { Tag } from 'primeng/tag';

import { DailyPlan } from '../core/models';
import { EmptyState } from './empty-state';
import { MetricCard } from './metric-card';
import {
  EMPTY_LIST_COPY,
  PlanStatus,
  blockReasonCopy,
  currentPhase,
  formatUtcDate,
  formatUtcTime,
  groupChecklist,
  itemKind,
  itemLabel,
  listEntries,
  levelRows,
  remainingRisk,
  reviewCopy,
  volumeCopy,
} from './session-plan.util';

@Component({
  selector: 'app-session-plan',
  host: { class: 'panel secondary session-plan' },
  imports: [RouterLink, Button, Message, Skeleton, Tag, EmptyState, MetricCard],
  template: `
    <header class="session-plan-head">
      <div class="session-plan-copy">
        <h2>Today's session</h2>
        @if (status() === 'ready' && plan(); as readyPlan) {
          <p class="session-plan-meta">
            <span translate="no">{{ readyPlan.instrument }}</span>
            <span class="mono">{{ sessionDate(readyPlan.session_start_utc) }}</span>
          </p>
          <p class="muted">Updated {{ sessionTime(readyPlan.as_of) }} UTC</p>
        }
      </div>
      <div class="session-plan-actions">
        @if (status() === 'ready' && plan(); as readyPlan) {
          <p-tag
            [value]="readyPlan.blocks_trading ? 'Trading paused' : 'Open to trade'"
            [severity]="readyPlan.blocks_trading ? 'warn' : 'success'"
          />
        }
        <p-button
          icon="pi pi-refresh"
          severity="secondary"
          size="small"
          [loading]="loading()"
          [disabled]="loading()"
          ariaLabel="Refresh session plan"
          (onClick)="refresh.emit()"
        />
      </div>
    </header>
      @if (status() === 'loading') {
        <div class="session-plan-skeleton" aria-busy="true" aria-live="polite">
          <p class="visually-hidden">Loading session plan…</p>
          <p-skeleton height="4.5rem" borderRadius="0" />
          <p-skeleton height="4.5rem" borderRadius="0" />
          <p-skeleton height="4.5rem" borderRadius="0" />
        </div>
      } @else if (status() === 'error' || !plan()) {
        <app-empty-state
          title="Session plan unavailable"
          detail="Start the control plane, then refresh."
          icon="pi-calendar"
        />
      } @else {
        @if (plan()!.blocks_trading) {
          <p-message severity="warn" [text]="blockedCopy(plan()!.block_reason)" />
        }
        <ol class="session-plan-phases">
          @for (phase of phases(); track phase.id) {
            <li class="session-plan-phase" [class.current]="phase.id === activePhase()">
              <h3>
                {{ phase.label }}
                @if (phase.id === activePhase()) {
                  <span class="session-plan-now">current</span>
                }
              </h3>
              <dl class="session-plan-items">
                @for (row of phase.items; track row.item) {
                  <dt>{{ rowLabel(row.item) }}</dt>
                  <dd>
                    @switch (rowKind(row.item)) {
                      @case ('list') {
                        @if (entries(row.value).length === 0) {
                          <span class="muted">{{ emptyCopy }}</span>
                        } @else {
                          <span>{{ entries(row.value).join(', ') }}</span>
                        }
                      }
                      @case ('levels') {
                        @if (levels(row.value).length === 0) {
                          <span class="muted">{{ emptyCopy }}</span>
                        } @else {
                          <div class="session-plan-levels">
                            @for (level of levels(row.value); track level.label) {
                              <div class="session-plan-level">
                                <span>{{ level.label }}</span>
                                <span class="mono">{{ level.value }}</span>
                              </div>
                            }
                          </div>
                        }
                      }
                      @case ('volume') {
                        <span class="mono">{{ volume(row.value) }}</span>
                      }
                      @case ('watchlist') {
                        @if (entries(row.value).length === 0) {
                          <span class="muted">{{ emptyCopy }}</span>
                        } @else {
                          <span class="session-plan-watchlist">
                            @for (symbol of entries(row.value); track symbol) {
                              <a [routerLink]="['/market', symbol]" translate="no">{{ symbol }}</a>
                            }
                          </span>
                        }
                      }
                      @case ('scenarios') {
                        <a [routerLink]="['/market', plan()!.instrument]">Run analysis on the asset page</a>
                      }
                      @case ('remaining') {
                        <div class="session-plan-metrics">
                          @for (metric of risk(row.value); track metric.label) {
                            <app-metric-card [label]="metric.label" [value]="metric.value" />
                          }
                        </div>
                      }
                      @case ('review') {
                        <span>{{ review(row.value) }}</span>
                      }
                      @default {
                        <span>{{ fallback(row.value) }}</span>
                      }
                    }
                  </dd>
                }
              </dl>
            </li>
          }
        </ol>
      }
  `,
})
export class SessionPlan {
  readonly plan = input<DailyPlan | null>(null);
  readonly status = input<PlanStatus>('loading');
  readonly loading = input(false);
  @Output() readonly refresh = new EventEmitter<void>();

  readonly emptyCopy = EMPTY_LIST_COPY;
  readonly blockedCopy = blockReasonCopy;
  readonly rowLabel = itemLabel;
  readonly rowKind = itemKind;
  readonly entries = listEntries;
  readonly levels = levelRows;
  readonly volume = volumeCopy;
  readonly risk = remainingRisk;
  readonly review = reviewCopy;

  readonly phases = computed(() => groupChecklist(this.plan()?.checklist ?? []));
  readonly activePhase = computed(() => {
    const asOf = this.plan()?.as_of;
    return asOf ? currentPhase(asOf) : null;
  });

  sessionDate(iso: string): string {
    return formatUtcDate(iso);
  }

  sessionTime(iso: string): string {
    return formatUtcTime(iso);
  }

  fallback(value: unknown): string {
    const text = typeof value === 'string' || typeof value === 'number' ? String(value) : '';
    return text || EMPTY_LIST_COPY;
  }
}
