import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { DashboardStore } from '../core/dashboard.store';
import { ALERT_LABELS, timeAgo } from '../shared/format';

@Component({
  selector: 'app-alert-banner',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule],
  template: `
    @if (store.alerts().length) {
      <section class="banner" role="alert" aria-live="polite">
        @for (alert of store.alerts(); track alert.id) {
          <div class="alert">
            <mat-icon class="icon">warning_amber</mat-icon>
            <div class="body">
              <div class="title">
                <strong>{{ labels[alert.rule] }}</strong>
                <span class="app mono">{{ alert.app_id }}</span>
                <span class="when muted">{{ timeAgo(alert.updated_at) }}</span>
              </div>
              <div class="detail">{{ alert.detail }}</div>
            </div>
            <button mat-button (click)="store.acknowledgeAlert(alert.id)">Dismiss</button>
          </div>
        }
      </section>
    }
  `,
  styles: `
    .banner {
      display: flex; flex-direction: column;
      border: 1px solid #f5c2c0; border-left: 4px solid var(--sev-high);
      border-radius: 8px; background: #fff5f5; overflow: hidden;
    }
    .alert { display: flex; align-items: center; gap: 12px; padding: 10px 12px 10px 16px; }
    .alert + .alert { border-top: 1px solid #f5c2c0; }
    .icon { color: var(--sev-high); flex: none; }
    .body { flex: 1; min-width: 0; }
    .title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; font-size: 14px; }
    .app { font-size: 12px; padding: 0 6px; background: #fde2e1; border-radius: 4px; }
    .when { font-size: 12px; }
    .detail { font-size: 13px; color: #5f2120; margin-top: 2px; }
  `,
})
export class AlertBannerComponent {
  readonly store = inject(DashboardStore);
  readonly labels = ALERT_LABELS;
  readonly timeAgo = timeAgo;
}
