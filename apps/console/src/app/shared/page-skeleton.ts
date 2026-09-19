import { Component } from '@angular/core';
import { Skeleton } from 'primeng/skeleton';

@Component({
  selector: 'app-page-skeleton',
  imports: [Skeleton],
  template: `
    <div class="page-skeleton reveal" aria-busy="true" aria-live="polite">
      <p-skeleton width="14rem" height="1.7rem" borderRadius="0" />
      <p-skeleton width="32rem" height="0.85rem" borderRadius="0" />
      <div class="metric-grid">
        <p-skeleton height="4.4rem" borderRadius="0" />
        <p-skeleton height="4.4rem" borderRadius="0" />
        <p-skeleton height="4.4rem" borderRadius="0" />
        <p-skeleton height="4.4rem" borderRadius="0" />
      </div>
      <p-skeleton height="10rem" borderRadius="0" />
    </div>
  `,
})
export class PageSkeleton {}
