import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { IconField } from 'primeng/iconfield';
import { InputIcon } from 'primeng/inputicon';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { Tag } from 'primeng/tag';

import { ApiService } from '../core/api.service';
import { ResearchDocumentView } from '../core/models';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';
import { StaleBadge } from '../shared/stale-badge';

@Component({
  selector: 'app-research-page',
  imports: [EmptyState, StaleBadge, FormsModule, Button, IconField, InputIcon, InputText, Message, Tag, PageHeader, PageSkeleton],
  template: `
    <div class="reveal">
      <app-page-header
        title="Research and intelligence"
        lede="External context is untrusted. Contradictions are shown, never resolved silently. Sentiment is an estimate. Crypto categories include protocol upgrades, unlocks, listings, and regulation."
      />
      <div class="toolbar">
        <p-iconfield iconPosition="left">
          <p-inputicon class="pi pi-search" />
          <input
            pInputText
            [(ngModel)]="instrument"
            placeholder="Instrument filter"
            (keyup.enter)="load()"
            aria-label="Instrument filter"
          />
        </p-iconfield>
        <p-button label="Load" (onClick)="load()" />
      </div>
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (docs().length === 0) {
        <app-empty-state title="No research documents" detail="The metadata store is empty or the instrument has no mentions." icon="pi-book" />
      } @else {
        @for (doc of docs(); track doc.doc_id) {
          <article class="panel">
            <h2>{{ doc.title }}</h2>
            <div class="doc-meta">
              <a [href]="doc.url" target="_blank" rel="noreferrer">{{ doc.source_id }}</a>
              <p-tag [value]="doc.category" severity="secondary" />
              <span>confidence {{ doc.confidence_score }}</span>
              <app-stale-badge [stale]="doc.stale" />
            </div>
            <p class="muted">published {{ doc.published_at ?? 'unknown' }} · fetched {{ doc.fetched_at }} · event {{ doc.event_date ?? 'n/a' }}</p>
            @if (doc.sentiment_score !== null) {
              <p class="est">sentiment {{ doc.sentiment_score }} <span class="est-label">est.</span></p>
            }
            <p>impact {{ doc.impact_magnitude ?? 'n/a' }} / {{ doc.impact_direction ?? 'n/a' }}</p>
            @if (doc.contradicts.length) {
              <p-message severity="warn" [text]="'Contradicting sources: ' + doc.contradicts.join(', ')" />
            }
            <p>{{ doc.summary || doc.extracted_text }}</p>
            <p class="muted">assets: {{ doc.assets_mentioned.join(', ') || 'none' }}</p>
          </article>
        }
      }
    </div>
  `,
})
export class ResearchPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly docs = signal<ResearchDocumentView[]>([]);
  readonly ready = signal(false);
  instrument = '';

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.ready.set(false);
    this.api.research(this.instrument || undefined).subscribe({
      next: (value) => {
        this.docs.set(value);
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
  }
}
