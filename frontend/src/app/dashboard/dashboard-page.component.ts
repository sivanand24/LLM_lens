import { ChangeDetectionStrategy, Component } from '@angular/core';

import { LogTableComponent } from '../logs/log-table.component';
import { AlertBannerComponent } from './alert-banner.component';
import { FlagBreakdownComponent } from './flag-breakdown.component';
import { KpiCardsComponent } from './kpi-cards.component';
import { TrendChartComponent } from './trend-chart.component';

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AlertBannerComponent, KpiCardsComponent, TrendChartComponent, FlagBreakdownComponent, LogTableComponent],
  template: `
    <app-alert-banner />
    <app-kpi-cards />
    <div class="charts">
      <app-trend-chart class="lens-panel" />
      <app-flag-breakdown class="lens-panel" />
    </div>
    <app-log-table />
  `,
  styles: `
    :host { display: flex; flex-direction: column; gap: 16px; }
    .charts { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 16px; }
    @media (max-width: 1100px) { .charts { grid-template-columns: 1fr; } }
  `,
})
export class DashboardPageComponent {}
