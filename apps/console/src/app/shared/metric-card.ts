import { Component, computed, input } from '@angular/core';

import { formatQuote } from '../core/models';

const NUMERIC_RE = /^-?\d+(\.\d+)?$/;

@Component({
  selector: 'app-metric-card',
  template: `
    <article class="metric" [class.readout]="size() === 'hero'" [class.readout-hero]="size() === 'hero'">
      <p class="metric-label">{{ label() }}</p>
      <p class="metric-value" [class]="valueClass()">{{ displayValue() }}</p>
      @if (hint()) {
        <p class="metric-hint">{{ hint() }}</p>
      }
    </article>
  `,
})
export class MetricCard {
  readonly label = input.required<string>();
  readonly value = input.required<string | number>();
  /** Fixed decimal places for numeric values (e.g. 0 for counts, 2 for money). Omit to scale with magnitude. */
  readonly decimals = input<number | null>(null);
  readonly hint = input<string | null>(null);
  readonly valueClass = input('');
  readonly size = input<'default' | 'hero'>('default');

  readonly displayValue = computed(() => {
    const raw = this.value();
    if (typeof raw === 'number') {
      return formatQuote(raw, { decimals: this.decimals() ?? undefined });
    }
    // Status strings (e.g. "RUNNING", "spot_only_kraken") pass through untouched;
    // only values that look like plain numbers get formatted.
    if (!NUMERIC_RE.test(raw.trim())) {
      return raw;
    }
    return formatQuote(raw, { decimals: this.decimals() ?? undefined });
  });
}
