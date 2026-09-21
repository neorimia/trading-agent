import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Button } from 'primeng/button';
import { IconField } from 'primeng/iconfield';
import { InputIcon } from 'primeng/inputicon';
import { InputText } from 'primeng/inputtext';
import { TableModule } from 'primeng/table';

import { ApiService } from '../core/api.service';
import { MarketInstrument, formatQuote, pnlClass } from '../core/models';
import { EmptyState } from '../shared/empty-state';
import { PageHeader } from '../shared/page-header';
import { PageSkeleton } from '../shared/page-skeleton';
import { StaleBadge } from '../shared/stale-badge';

const WATCH_KEY = 'console_watchlist';

@Component({
  selector: 'app-market-page',
  imports: [FormsModule, RouterLink, StaleBadge, EmptyState, Button, IconField, InputIcon, InputText, TableModule, PageHeader, PageSkeleton],
  template: `
    <div class="reveal">
      <app-page-header title="Market overview" lede="Universe allowlist only. Prices are bar closes, not a live tape." />
      <div class="toolbar">
        <p-iconfield iconPosition="left">
          <p-inputicon class="pi pi-search" />
          <input pInputText [(ngModel)]="query" placeholder="Filter symbol" aria-label="Filter symbol" />
        </p-iconfield>
      </div>
      @if (!ready()) {
        <app-page-skeleton />
      } @else if (filtered().length === 0) {
        <app-empty-state title="No instruments" detail="Check universe.yaml and the control plane." icon="pi-search" />
      } @else {
        <div class="table-scroll">
        <p-table [value]="filtered()" sortField="symbol" [sortOrder]="1">
          <ng-template #header>
            <tr>
              <th></th>
              <th pSortableColumn="symbol">Symbol <p-sortIcon field="symbol" /></th>
              <th pSortableColumn="venue">Venue <p-sortIcon field="venue" /></th>
              <th>Price</th>
              <th>Change</th>
              <th>Volume</th>
              <th>Vol.</th>
              <th>Spread</th>
              <th>Status</th>
            </tr>
          </ng-template>
          <ng-template #body let-row>
            <tr>
              <td>
                <p-button
                  [icon]="watched().has(row.symbol) ? 'pi pi-star-fill' : 'pi pi-star'"
                  [text]="true"
                  [rounded]="true"
                  [ariaLabel]="(watched().has(row.symbol) ? 'Unwatch ' : 'Watch ') + row.symbol"
                  (onClick)="toggle(row.symbol)"
                />
              </td>
              <td><a [routerLink]="['/market', row.symbol]">{{ row.symbol }}</a></td>
              <td>{{ row.venue }}</td>
              <td class="mono">{{ fmt(row.price) }}</td>
              <td [class]="pnlClass(row.change_pct)">{{ fmt(row.change_pct) }}</td>
              <td class="mono">{{ fmt(row.volume) }}</td>
              <td class="mono est">{{ fmt(row.volatility) }} <span class="est-label">est.</span></td>
              <td>{{ fmt(row.spread) }}</td>
              <td><app-stale-badge [stale]="row.stale" [reason]="row.status" /></td>
            </tr>
          </ng-template>
        </p-table>
        </div>
      }
    </div>
  `,
})
export class MarketPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<MarketInstrument[]>([]);
  readonly ready = signal(false);
  query = '';
  readonly watched = signal<Set<string>>(new Set(JSON.parse(localStorage.getItem(WATCH_KEY) || '[]')));
  readonly fmt = formatQuote;
  readonly pnlClass = pnlClass;

  ngOnInit(): void {
    this.api.market().subscribe({
      next: (value) => {
        this.rows.set(value);
        this.ready.set(true);
      },
      error: () => this.ready.set(true),
    });
  }

  filtered(): MarketInstrument[] {
    const q = this.query.trim().toUpperCase();
    const list = this.rows();
    const watched = this.watched();
    const watchedFirst = [...list].sort((a, b) => Number(watched.has(b.symbol)) - Number(watched.has(a.symbol)));
    if (!q) {
      return watchedFirst;
    }
    return watchedFirst.filter((row) => row.symbol.includes(q) || row.venue.includes(q));
  }

  toggle(symbol: string): void {
    const next = new Set(this.watched());
    if (next.has(symbol)) {
      next.delete(symbol);
    } else {
      next.add(symbol);
    }
    this.watched.set(next);
    localStorage.setItem(WATCH_KEY, JSON.stringify([...next]));
  }
}
