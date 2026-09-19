import { Component, computed, input } from '@angular/core';
import { Tag } from 'primeng/tag';

const REASON_LABELS: Record<string, string> = {
  research_only: 'research-only — no execution venue',
  no_adapter: 'no data adapter for venue',
  data_unavailable: 'data unavailable',
  stale: 'stale / unverified',
};

@Component({
  selector: 'app-stale-badge',
  imports: [Tag],
  template: `
    @if (stale()) {
      <p-tag [value]="label()" severity="warn" />
    } @else {
      <p-tag value="confirmed" severity="success" />
    }
  `,
})
export class StaleBadge {
  readonly stale = input(false);
  readonly reason = input<string | null>(null);
  readonly label = computed(() => {
    const reason = this.reason();
    return (reason && REASON_LABELS[reason]) || 'stale / unverified';
  });
}
