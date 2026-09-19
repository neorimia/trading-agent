import { Component, input } from '@angular/core';

@Component({
  selector: 'app-metric-card',
  template: `
    <article class="metric" [class.readout]="size() === 'hero'" [class.readout-hero]="size() === 'hero'">
      <p class="metric-label">{{ label() }}</p>
      <p class="metric-value" [class]="valueClass()">{{ value() }}</p>
      @if (hint()) {
        <p class="metric-hint">{{ hint() }}</p>
      }
    </article>
  `,
})
export class MetricCard {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly hint = input<string | null>(null);
  readonly valueClass = input('');
  readonly size = input<'default' | 'hero'>('default');
}
