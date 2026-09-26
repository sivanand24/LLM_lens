import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';

import { DashboardStore } from '../core/dashboard.store';
import { CallListItem } from '../core/models';
import { ALL_FLAGS, FLAG_LABELS, SEVERITIES, formatMs, isFlagType } from '../shared/format';
import { SeverityChipComponent } from '../shared/severity-chip.component';

@Component({
  selector: 'app-log-table',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatSelectModule,
    MatTableModule,
    MatTooltipModule,
    SeverityChipComponent,
  ],
  template: `
    <section class="lens-panel">
      <div class="head">
        <h2 class="lens-panel-title">Calls</h2>
        <div class="filters">
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="search">
            <mat-icon matPrefix>search</mat-icon>
            <input
              #searchBox
              matInput
              placeholder="Search prompt, response, request id"
              [value]="store.callQuery().q"
              (input)="search$.next(searchBox.value)"
            />
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-select
              placeholder="Any flag"
              [value]="store.callQuery().flag"
              (selectionChange)="store.setCallQuery({ flag: $event.value })"
            >
              <mat-option [value]="null">Any flag</mat-option>
              @for (f of flags; track f) {
                <mat-option [value]="f">{{ flagLabels[f] }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-select
              placeholder="Any severity"
              [value]="store.callQuery().severity"
              (selectionChange)="store.setCallQuery({ severity: $event.value })"
            >
              <mat-option [value]="null">Any severity</mat-option>
              @for (s of severities; track s) {
                <mat-option [value]="s">{{ s }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (hasFilters()) {
            <button mat-button (click)="clearFilters()"><mat-icon>filter_alt_off</mat-icon>Clear</button>
          }
        </div>
      </div>

      <div class="table-wrap">
        <table mat-table [dataSource]="rows()" [trackBy]="trackById">
          <ng-container matColumnDef="time">
            <th mat-header-cell *matHeaderCellDef>Time</th>
            <td mat-cell *matCellDef="let c" class="nowrap mono small">{{ c.created_at | date: 'MMM d, HH:mm:ss' }}</td>
          </ng-container>
          <ng-container matColumnDef="app">
            <th mat-header-cell *matHeaderCellDef>App / model</th>
            <td mat-cell *matCellDef="let c" class="nowrap">
              <div>{{ c.app_id }}</div>
              <div class="muted small">{{ c.model }}</div>
            </td>
          </ng-container>
          <ng-container matColumnDef="severity">
            <th mat-header-cell *matHeaderCellDef>Severity</th>
            <td mat-cell *matCellDef="let c">
              @if (c.check_status === 'pending') {
                <span class="muted small">checking…</span>
              } @else {
                <app-severity-chip [severity]="c.severity" />
              }
            </td>
          </ng-container>
          <ng-container matColumnDef="flags">
            <th mat-header-cell *matHeaderCellDef>Flags</th>
            <td mat-cell *matCellDef="let c">
              <div class="flags">
                @for (f of c.flags; track f) {
                  <span class="flag">{{ flagLabel(f) }}</span>
                }
              </div>
            </td>
          </ng-container>
          <ng-container matColumnDef="latency">
            <th mat-header-cell *matHeaderCellDef class="num">Latency</th>
            <td mat-cell *matCellDef="let c" class="num mono small">{{ formatMs(c.latency_ms) }}</td>
          </ng-container>
          <ng-container matColumnDef="preview">
            <th mat-header-cell *matHeaderCellDef>Prompt → response</th>
            <td mat-cell *matCellDef="let c" class="preview">
              <div class="p">{{ c.prompt_preview }}</div>
              <div class="r muted">{{ c.status === 'success' ? c.response_preview : '(' + c.status + ')' }}</div>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="columns; sticky: true"></tr>
          <tr
            mat-row
            *matRowDef="let row; columns: columns"
            class="row"
            [class.selected]="row.request_id === store.selectedCallId()"
            [class.failure]="row.is_failure"
            (click)="store.selectCall(row.request_id)"
            tabindex="0"
            (keydown.enter)="store.selectCall(row.request_id)"
          ></tr>
          <tr class="mat-row" *matNoDataRow>
            <td class="empty muted" [attr.colspan]="columns.length">
              {{ store.calls() ? 'No calls match these filters' : 'Loading…' }}
            </td>
          </tr>
        </table>
      </div>

      <mat-paginator
        [length]="store.calls()?.total ?? 0"
        [pageIndex]="store.callQuery().page - 1"
        [pageSize]="store.callQuery().pageSize"
        [pageSizeOptions]="[25, 50, 100]"
        (page)="onPage($event)"
      />
    </section>
  `,
  styles: `
    .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }
    .head .lens-panel-title { margin: 0; }
    .filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .filters mat-form-field { width: 160px; --mat-form-field-container-height: 40px; --mat-form-field-container-vertical-padding: 8px; font-size: 13px; }
    .filters .search { width: 300px; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; }
    .row { cursor: pointer; }
    .row:hover { background: #f6f8fb; }
    .row.selected { background: #e8f0fe; }
    .row.failure td:first-child { box-shadow: inset 3px 0 0 var(--sev-high); }
    .nowrap { white-space: nowrap; }
    .small { font-size: 12px; }
    .num { text-align: right; }
    .flags { display: flex; flex-wrap: wrap; gap: 4px; }
    .flag { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: #eef1f5; white-space: nowrap; }
    .preview { max-width: 520px; }
    .preview .p, .preview .r { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
    .preview .r { font-size: 12px; }
    .empty { padding: 32px; text-align: center; }
  `,
})
export class LogTableComponent {
  readonly store = inject(DashboardStore);
  readonly columns = ['time', 'app', 'severity', 'flags', 'latency', 'preview'];
  readonly flags = ALL_FLAGS;
  readonly flagLabels = FLAG_LABELS;
  readonly severities = SEVERITIES;
  readonly formatMs = formatMs;

  readonly search$ = new Subject<string>();
  readonly rows = computed<CallListItem[]>(() => this.store.calls()?.items ?? []);
  readonly hasFilters = computed(() => {
    const q = this.store.callQuery();
    return q.flag !== null || q.severity !== null || q.q !== '';
  });

  constructor() {
    this.search$
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe((q) => this.store.setCallQuery({ q }));
  }

  trackById = (_: number, row: CallListItem) => row.request_id;

  // mat-table row context is untyped; narrow before indexing.
  flagLabel(flag: unknown): string {
    return isFlagType(flag) ? FLAG_LABELS[flag] : String(flag);
  }

  onPage(e: PageEvent): void {
    this.store.setCallQuery({ page: e.pageIndex + 1, pageSize: e.pageSize });
  }

  clearFilters(): void {
    this.store.setCallQuery({ flag: null, severity: null, q: '' });
  }
}
