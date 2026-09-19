import { Component, input } from '@angular/core';

@Component({
  selector: 'app-page-header',
  template: `
    <header class="page-header">
      <div class="page-header-copy">
        <h1>{{ title() }}</h1>
        @if (lede()) {
          <p class="lede">{{ lede() }}</p>
        }
      </div>
      <div class="page-header-actions">
        <ng-content />
      </div>
    </header>
  `,
})
export class PageHeader {
  readonly title = input.required<string>();
  readonly lede = input('');
}
