import { Component, input } from '@angular/core';

@Component({
  selector: 'app-stale-badge',
  template: `
    @if (stale()) {
      <span class="badge-stale">stale / unverified</span>
    } @else {
      <span class="badge-fact">confirmed</span>
    }
  `,
})
export class StaleBadge {
  readonly stale = input(false);
}
