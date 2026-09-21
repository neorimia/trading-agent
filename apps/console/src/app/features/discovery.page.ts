import { DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { InputNumber } from 'primeng/inputnumber';
import { Select } from 'primeng/select';
import { Tag } from 'primeng/tag';

import { AgentStateService } from '../core/agent-state.service';
import { ApiService } from '../core/api.service';
import { DiscoveryCandidate } from '../core/models';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';
import { StaleBadge } from '../shared/stale-badge';

const WATCH_KEY = 'console_watchlist';

const STATUS_OPTIONS = [
  { label: 'All statuses', value: null },
  { label: 'Research', value: 'research' },
  { label: 'Watchlist', value: 'watchlist' },
  { label: 'Trade setup', value: 'trade_setup' },
];

@Component({
  selector: 'app-discovery-page',
  imports: [FormsModule, DecimalPipe, Button, InputNumber, Select, Tag, EmptyState, PageHeader, PageSkeleton, StaleBadge],
  template: `
    <div class="reveal">
      <app-page-header
        title="Asset discovery"
        lede="Research candidates only — never an order. Every component score is shown individually; nothing is collapsed into a single number."
      />
      <div class="toolbar">
        <p-select [(ngModel)]="status" [options]="statusOptions" optionLabel="label" optionValue="value" placeholder="Status" (onChange)="load()" />
        <p-inputnumber [(ngModel)]="minScore" placeholder="Min. opportunity score" [min]="0" [max]="1" [step]="0.05" (onInput)="load()" />
        <p-button label="Load" (onClick)="load()" />
      </div>
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (candidates().length === 0) {
        <app-empty-state title="No discovery candidates" detail="The discovery store is empty, or no run has produced candidates matching these filters yet." icon="pi-compass" />
      } @else {
        @for (candidate of candidates(); track candidate.id) {
          <article class="panel">
            <h2>{{ candidate.asset }} <span class="muted">· {{ candidate.exchange }}</span></h2>
            <div class="doc-meta">
              <p-tag [value]="candidate.candidate_status" severity="secondary" />
              <span>composite rank {{ candidate.composite_rank | number: '1.2-2' }}</span>
              <app-stale-badge [stale]="expired(candidate)" reason="stale" />
            </div>
            <p class="muted">horizon {{ candidate.research_horizon }} · expires {{ candidate.expires_at }}</p>

            <div class="score-grid">
              <span>opportunity {{ candidate.opportunity_score }}</span>
              <span>risk {{ candidate.risk_score }}</span>
              <span>confidence {{ candidate.confidence_score }}</span>
              <span>data quality {{ candidate.data_quality_score }}</span>
              <span>liquidity {{ candidate.factors.liquidity_score }}</span>
              <span>spread {{ candidate.factors.spread_score }}</span>
              <span class="est">volatility {{ candidate.factors.volatility ?? 'n/a' }} <span class="est-label">est.</span></span>
              <span>operational risk {{ candidate.factors.operational_risk_score }}</span>
            </div>

            @if (candidate.bullish_case.length || candidate.bearish_case.length || candidate.neutral_case.length) {
              @for (line of candidate.bullish_case; track line) {
                <p>bullish: {{ line }}</p>
              }
              @for (line of candidate.bearish_case; track line) {
                <p>bearish: {{ line }}</p>
              }
              @for (line of candidate.neutral_case; track line) {
                <p>neutral: {{ line }}</p>
              }
            } @else {
              <p class="muted">no LLM summary yet</p>
            }

            @if (candidate.invalidation_conditions.length) {
              <p class="muted">invalidation:
                @for (cond of candidate.invalidation_conditions; track cond) {
                  <p-tag [value]="cond" severity="secondary" />
                }
              </p>
            }
            @if (candidate.missing_data.length) {
              <p class="muted">missing / rejected:
                @for (item of candidate.missing_data; track item) {
                  <p-tag [value]="item" severity="warn" />
                }
              </p>
            }
            @if (candidate.sources.length) {
              <p class="muted">sources:
                @for (source of candidate.sources; track source.source_id) {
                  <a [href]="source.url" target="_blank" rel="noreferrer">{{ source.source_id }}</a>
                  <span class="est-label">({{ source.fetched_at }})</span>
                }
              </p>
            }

            <div class="toolbar">
              <p-button
                [label]="watched().has(candidate.asset) ? 'Remove from watchlist' : 'Add to watchlist'"
                [outlined]="watched().has(candidate.asset)"
                (onClick)="toggleWatch(candidate.asset)"
              />
              @if (state.canMutate()) {
                <p-button
                  label="Generate LLM summary"
                  severity="secondary"
                  [loading]="summarizing().has(candidate.asset)"
                  (onClick)="summarize(candidate)"
                />
              }
            </div>
          </article>
        }
      }
    </div>
  `,
})
export class DiscoveryPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly state = inject(AgentStateService);
  readonly candidates = signal<DiscoveryCandidate[]>([]);
  readonly ready = signal(false);
  readonly watched = signal<Set<string>>(new Set(JSON.parse(localStorage.getItem(WATCH_KEY) || '[]')));
  readonly summarizing = signal<Set<string>>(new Set());
  readonly statusOptions = STATUS_OPTIONS;
  status: string | null = null;
  minScore: number | null = null;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.ready.set(false);
    this.api
      .discoveryCandidates({
        status: this.status ?? undefined,
        min_score: this.minScore ?? undefined,
      })
      .subscribe({
        next: (value) => {
          this.candidates.set(value);
          this.ready.set(true);
        },
        error: () => this.ready.set(true),
      });
  }

  expired(candidate: DiscoveryCandidate): boolean {
    return new Date(candidate.expires_at).getTime() <= Date.now();
  }

  toggleWatch(asset: string): void {
    const next = new Set(this.watched());
    if (next.has(asset)) {
      next.delete(asset);
    } else {
      next.add(asset);
    }
    this.watched.set(next);
    localStorage.setItem(WATCH_KEY, JSON.stringify([...next]));
  }

  summarize(candidate: DiscoveryCandidate): void {
    const pending = new Set(this.summarizing());
    pending.add(candidate.asset);
    this.summarizing.set(pending);
    this.api.summarizeDiscoveryCandidate(candidate.asset).subscribe({
      next: (updated) => {
        this.candidates.set(this.candidates().map((c) => (c.id === updated.id ? updated : c)));
        this.doneSummarizing(candidate.asset);
      },
      error: () => this.doneSummarizing(candidate.asset),
    });
  }

  private doneSummarizing(asset: string): void {
    const pending = new Set(this.summarizing());
    pending.delete(asset);
    this.summarizing.set(pending);
  }
}
