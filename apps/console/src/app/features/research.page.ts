import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api.service';
import { ResearchDocumentView } from '../core/models';
import { EmptyState } from '../shared/empty-state';
import { StaleBadge } from '../shared/stale-badge';

@Component({
  selector: 'app-research-page',
  imports: [EmptyState, StaleBadge, FormsModule],
  template: `
    <h1>Research and intelligence</h1>
    <p class="lede">
      External context is untrusted. Contradictions are shown, never resolved silently.
      Sentiment is an estimate. Crypto categories include protocol upgrades, unlocks, listings, and regulation.
    </p>
    <input [(ngModel)]="instrument" placeholder="Instrument filter" (keyup.enter)="load()" />
    <button type="button" (click)="load()">Load</button>
    @if (docs().length === 0) {
      <app-empty-state title="No research documents" detail="The metadata store is empty or the instrument has no mentions." />
    }
    @for (doc of docs(); track doc.doc_id) {
      <article class="card">
        <h2>{{ doc.title }}</h2>
        <p>
          <a [href]="doc.url" target="_blank" rel="noreferrer">{{ doc.source_id }}</a>
          · {{ doc.category }} · confidence {{ doc.confidence_score }}
          <app-stale-badge [stale]="doc.stale" />
        </p>
        <p class="muted">published {{ doc.published_at ?? 'unknown' }} · fetched {{ doc.fetched_at }} · event {{ doc.event_date ?? 'n/a' }}</p>
        @if (doc.sentiment_score !== null) {
          <p class="est">sentiment {{ doc.sentiment_score }} <span class="est-label">est.</span></p>
        }
        <p>impact {{ doc.impact_magnitude ?? 'n/a' }} / {{ doc.impact_direction ?? 'n/a' }}</p>
        @if (doc.contradicts.length) {
          <p class="banner-warn">Contradicting sources: {{ doc.contradicts.join(', ') }}</p>
        }
        <p>{{ doc.summary || doc.extracted_text }}</p>
        <p class="muted">assets: {{ doc.assets_mentioned.join(', ') || 'none' }}</p>
      </article>
    }
  `,
})
export class ResearchPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly docs = signal<ResearchDocumentView[]>([]);
  instrument = '';

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.research(this.instrument || undefined).subscribe((value) => this.docs.set(value));
  }
}
