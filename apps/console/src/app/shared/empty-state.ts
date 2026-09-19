import { Component, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  template: `
    <div class="empty">
      <p>{{ title() }}</p>
      <p class="muted">{{ detail() }}</p>
    </div>
  `,
})
export class EmptyState {
  readonly title = input('Nothing to show');
  readonly detail = input('No data from the control plane yet.');
}
