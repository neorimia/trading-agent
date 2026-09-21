import { Component, computed, input } from '@angular/core';
import { Tag } from 'primeng/tag';
import { Tooltip } from 'primeng/tooltip';

const REASON_LABELS: Record<string, string> = {
  research_only: 'research-only — no execution venue',
  no_adapter: 'no data adapter for venue',
  data_unavailable: 'data unavailable',
  stale: 'stale / unverified',
};

const REASON_TOOLTIPS: Record<string, string> = {
  research_only: 'This symbol is tracked for research only — no venue adapter can execute orders on it.',
  no_adapter: 'No data adapter is configured for this venue, so live pricing cannot be verified.',
  data_unavailable: 'The venue did not return fresh data for this symbol on the last poll.',
  stale: 'This price has not been refreshed recently and may not reflect the current market.',
};

@Component({
  selector: 'app-stale-badge',
  imports: [Tag, Tooltip],
  template: `
    @if (stale()) {
      <p-tag [value]="label()" severity="warn" [pTooltip]="tooltip()" tooltipPosition="top" />
    } @else {
      <p-tag value="confirmed" severity="success" pTooltip="Price data was verified against the venue feed on the last poll." tooltipPosition="top" />
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
  readonly tooltip = computed(() => {
    const reason = this.reason();
    return (reason && REASON_TOOLTIPS[reason]) || REASON_TOOLTIPS['stale'];
  });
}
