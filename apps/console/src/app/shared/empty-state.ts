import { Component, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  template: `
    <div class="empty reveal">
      <i [class]="'pi empty-icon ' + icon()" aria-hidden="true"></i>
      <div>
        <p>{{ title() }}</p>
        <p class="muted">{{ detail() }}</p>
        <ng-content />
      </div>
    </div>
  `,
})
export class EmptyState {
  readonly title = input('Nothing to show');
  readonly detail = input('No data from the control plane yet.');
  readonly icon = input('pi-inbox');
}
