import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterOutlet } from '@angular/router';

import { DashboardStore } from './core/dashboard.store';
import { RANGE_MS, RangeKey } from './core/models';
import { CallDrawerComponent } from './logs/call-drawer.component';

@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    RouterOutlet,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
    MatSelectModule,
    MatSidenavModule,
    MatSlideToggleModule,
    MatToolbarModule,
    MatTooltipModule,
    CallDrawerComponent,
  ],
  template: `
    <mat-sidenav-container class="shell">
      <mat-sidenav-content>
        <mat-toolbar class="topbar">
          <mat-icon class="logo">center_focus_strong</mat-icon>
          <span class="brand">LLM Lens</span>
          <span class="spacer"></span>

          <mat-select
            class="app-select"
            [value]="store.filters().appId ?? ''"
            (selectionChange)="store.setFilters({ appId: $event.value || null })"
            aria-label="Application"
          >
            <mat-option value="">All apps</mat-option>
            @for (app of store.apps(); track app.app_id) {
              <mat-option [value]="app.app_id">{{ app.app_id }}</mat-option>
            }
          </mat-select>

          <mat-button-toggle-group
            class="ranges"
            hideSingleSelectionIndicator
            [value]="store.filters().range"
            (change)="store.setFilters({ range: $event.value })"
            aria-label="Time range"
          >
            @for (r of ranges; track r) {
              <mat-button-toggle [value]="r">{{ r }}</mat-button-toggle>
            }
          </mat-button-toggle-group>

          <mat-slide-toggle [checked]="store.live()" (change)="store.setLive($event.checked)">
            <span class="live" [class.on]="store.live()">
              <span class="dot"></span>{{ store.live() ? 'Live' : 'Paused' }}
            </span>
          </mat-slide-toggle>

          <span class="updated muted" [matTooltip]="'Last successful refresh'">
            {{ store.lastUpdated() ? (store.lastUpdated() | date: 'HH:mm:ss') : '—' }}
          </span>
          <button mat-icon-button (click)="store.refresh()" matTooltip="Refresh now" aria-label="Refresh">
            <mat-icon>refresh</mat-icon>
          </button>
        </mat-toolbar>

        @if (store.error(); as error) {
          <div class="error-bar" role="alert"><mat-icon>cloud_off</mat-icon>{{ error }}</div>
        }

        <main>
          <router-outlet />
        </main>
      </mat-sidenav-content>

      <mat-sidenav
        class="drawer"
        position="end"
        mode="over"
        [autoFocus]="false"
        [opened]="store.drawerOpen()"
        (closedStart)="store.closeCall()"
      >
        <app-call-drawer />
      </mat-sidenav>
    </mat-sidenav-container>
  `,
  styles: `
    .shell { height: 100vh; background: var(--lens-bg); }
    .topbar {
      position: sticky; top: 0; z-index: 10;
      display: flex; gap: 16px;
      background: #1c2333; color: #fff;
      height: 56px; font-size: 16px;
    }
    .logo { color: #8ab4ff; }
    .brand { font-weight: 500; letter-spacing: 0.02em; margin-left: -8px; }
    .spacer { flex: 1; }
    .app-select {
      width: 180px; padding: 6px 12px; border-radius: 6px;
      background: rgba(255, 255, 255, 0.08);
      --mat-select-enabled-trigger-text-color: #fff;
      --mat-select-enabled-arrow-color: #cfd8e3;
    }
    .ranges {
      --mat-standard-button-toggle-height: 32px;
      --mat-standard-button-toggle-text-color: #cfd8e3;
      --mat-standard-button-toggle-background-color: transparent;
      --mat-standard-button-toggle-selected-state-background-color: #3b4a6b;
      --mat-standard-button-toggle-selected-state-text-color: #fff;
      --mat-standard-button-toggle-divider-color: #3b4a6b;
      border-color: #3b4a6b;
      font-size: 13px;
    }
    .live { display: inline-flex; align-items: center; gap: 6px; color: #cfd8e3; font-size: 13px; }
    .live .dot { width: 8px; height: 8px; border-radius: 50%; background: #78909c; }
    .live.on .dot { background: #4caf50; box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.25); animation: pulse 2s infinite; }
    @keyframes pulse { 50% { box-shadow: 0 0 0 6px rgba(76, 175, 80, 0); } }
    .updated { color: #9aa7b8; font-size: 12px; font-variant-numeric: tabular-nums; }
    .error-bar {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 24px; background: #fdecea; color: #b71c1c; font-size: 13px;
    }
    main { padding: 20px 24px 40px; max-width: 1600px; margin: 0 auto; }
    .drawer { width: min(720px, 92vw); }
    @media (max-width: 900px) {
      .topbar { flex-wrap: wrap; height: auto; padding: 8px 16px; }
      main { padding: 16px; }
    }
  `,
})
export class AppComponent {
  readonly store = inject(DashboardStore);
  readonly ranges = Object.keys(RANGE_MS) as RangeKey[];
}
