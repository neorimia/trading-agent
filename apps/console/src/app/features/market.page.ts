import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../core/api.service';
import { MarketInstrument, pnlClass } from '../core/models';
import { StaleBadge } from '../shared/stale-badge';
import { EmptyState } from '../shared/empty-state';

const WATCH_KEY = 'console_watchlist';

@Component({
  selector: 'app-market-page',
  imports: [FormsModule, RouterLink, StaleBadge, EmptyState],
  template: `
    <h1>Market overview</h1>
    <p class="lede">Universe allowlist only. Prices are bar closes, not a live tape.</p>
    <div class="toolbar">
      <input [(ngModel)]="query" placeholder="Filter symbol" />
    </div>
    @if (filtered().length === 0) {
      <app-empty-state title="No instruments" detail="Check universe.yaml and the control plane." />
    } @else {
      <table>
        <thead>
          <tr>
            <th></th>
            <th>Symbol</th>
            <th>Venue</th>
            <th>Price</th>
            <th>Change</th>
            <th>Volume</th>
            <th>Vol.</th>
            <th>Spread</th>
            <th>Age</th>
          </tr>
        </thead>
        <tbody>
          @for (row of filtered(); track row.symbol) {
            <tr>
              <td>
                <button type="button" class="linkish" (click)="toggle(row.symbol)">
                  {{ watched().has(row.symbol) ? '★' : '☆' }}
                </button>
              </td>
              <td><a [routerLink]="['/market', row.symbol]">{{ row.symbol }}</a></td>
              <td>{{ row.venue }}</td>
              <td class="mono">{{ row.price ?? '—' }}</td>
              <td [class]="pnlClass(row.change_pct)">{{ row.change_pct ?? '—' }}</td>
              <td class="mono">{{ row.volume ?? '—' }}</td>
              <td class="mono est">{{ row.volatility ?? '—' }} <span class="est-label">est.</span></td>
              <td>{{ row.spread ?? 'n/a' }}</td>
              <td><app-stale-badge [stale]="row.stale" /></td>
            </tr>
          }
        </tbody>
      </table>
    }
  `,
})
export class MarketPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<MarketInstrument[]>([]);
  query = '';
  readonly watched = signal<Set<string>>(new Set(JSON.parse(localStorage.getItem(WATCH_KEY) || '[]')));
  readonly pnlClass = pnlClass;

  ngOnInit(): void {
    this.api.market().subscribe((value) => this.rows.set(value));
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
