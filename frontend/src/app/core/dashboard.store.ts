import { HttpErrorResponse } from '@angular/common/http';
import { DestroyRef, Injectable, WritableSignal, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Observable, Subject, catchError, filter, merge, share, switchMap, tap, timer } from 'rxjs';

import { ApiService } from './api.service';
import {
  Alert,
  AppInfo,
  CallDetail,
  CallQuery,
  CallsPage,
  DashboardFilters,
  FlagCount,
  Summary,
  Timeseries,
} from './models';

export const POLL_MS = 5000;

export const DEFAULT_FILTERS: DashboardFilters = { appId: null, range: '1h' };
export const DEFAULT_CALL_QUERY: CallQuery = { flag: null, severity: null, q: '', page: 1, pageSize: 25 };

export function describeError(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) return 'Backend unreachable — is the Django server running on :8000?';
    const body: unknown = err.error;
    if (typeof body === 'object' && body !== null && 'error' in body && typeof body.error === 'string') {
      return `${err.status}: ${body.error}`;
    }
    return `${err.status} ${err.statusText}`;
  }
  return err instanceof Error ? err.message : 'Unexpected error';
}

/**
 * Single source of truth for the dashboard.
 *
 * Every endpoint reloads on the same trigger: a 5 s poll while `live` is on, plus
 * explicit refreshes when filters change. switchMap drops stale in-flight requests.
 */
@Injectable({ providedIn: 'root' })
export class DashboardStore {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  // --- inputs ---
  readonly live = signal(true);
  readonly filters = signal<DashboardFilters>(DEFAULT_FILTERS);
  readonly callQuery = signal<CallQuery>(DEFAULT_CALL_QUERY);
  readonly selectedCallId = signal<string | null>(null);

  // --- server state ---
  readonly summary = signal<Summary | null>(null);
  readonly timeseries = signal<Timeseries | null>(null);
  readonly flags = signal<FlagCount[]>([]);
  readonly alerts = signal<Alert[]>([]);
  readonly apps = signal<AppInfo[]>([]);
  readonly calls = signal<CallsPage | null>(null);
  readonly selectedCall = signal<CallDetail | null>(null);

  // --- status ---
  readonly lastUpdated = signal<Date | null>(null);
  /** Errors are tracked per source so one healthy endpoint can't mask another failing one. */
  private readonly errors = signal<Record<string, string>>({});
  readonly error = computed(() => Object.values(this.errors())[0] ?? null);
  readonly drawerOpen = computed(() => this.selectedCallId() !== null);

  private readonly refresh$ = new Subject<void>();
  private readonly callsRefresh$ = new Subject<void>();
  private readonly select$ = new Subject<void>();

  constructor() {
    const tick$ = merge(
      timer(0, POLL_MS).pipe(filter(() => this.live())),
      this.refresh$,
    ).pipe(share());

    this.load('summary', tick$, () => this.api.getSummary(this.filters()), this.summary);
    this.load('timeseries', tick$, () => this.api.getTimeseries(this.filters()), this.timeseries);
    this.load('flags', tick$, () => this.api.getFlags(this.filters()), this.flags, (r) => r.flags);
    this.load('alerts', tick$, () => this.api.getAlerts(this.filters().appId), this.alerts);
    this.load('apps', tick$, () => this.api.getApps(), this.apps);
    this.load(
      'calls',
      merge(tick$, this.callsRefresh$),
      () => this.api.getCalls(this.filters(), this.callQuery()),
      this.calls,
    );
    // The open call is re-fetched on each tick so pending checks resolve in place.
    this.load(
      'call',
      merge(this.select$, tick$.pipe(filter(() => this.selectedCallId() !== null))),
      () => this.api.getCall(this.selectedCallId() ?? ''),
      this.selectedCall,
    );
  }

  private load<R, T = R>(
    source: string,
    trigger$: Observable<unknown>,
    request: () => Observable<R>,
    target: WritableSignal<T>,
    project: (response: R) => T = (r) => r as unknown as T,
  ): void {
    trigger$
      .pipe(
        switchMap(() =>
          request().pipe(
            tap(() => {
              this.setError(source, null);
              this.lastUpdated.set(new Date());
            }),
            catchError((err: unknown) => {
              this.setError(source, describeError(err));
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((response) => target.set(project(response)));
  }

  private setError(source: string, message: string | null): void {
    this.errors.update((errors) => {
      if (message === null) {
        if (!(source in errors)) return errors;
        const { [source]: _, ...rest } = errors;
        return rest;
      }
      return errors[source] === message ? errors : { ...errors, [source]: message };
    });
  }

  // --- actions ---

  setLive(live: boolean): void {
    this.live.set(live);
  }

  refresh(): void {
    this.refresh$.next();
  }

  setFilters(patch: Partial<DashboardFilters>): void {
    this.filters.update((f) => ({ ...f, ...patch }));
    this.callQuery.update((q) => ({ ...q, page: 1 }));
    this.refresh$.next();
  }

  /** Any change other than paging sends the log table back to page 1. */
  setCallQuery(patch: Partial<CallQuery>): void {
    this.callQuery.update((q) => ({ ...q, page: 1, ...patch }));
    this.callsRefresh$.next();
  }

  selectCall(requestId: string): void {
    if (this.selectedCall()?.request_id !== requestId) {
      this.selectedCall.set(null);
    }
    this.selectedCallId.set(requestId);
    this.select$.next();
  }

  closeCall(): void {
    this.selectedCallId.set(null);
    this.selectedCall.set(null);
    this.setError('call', null);
  }

  acknowledgeAlert(id: string): void {
    this.alerts.update((alerts) => alerts.filter((a) => a.id !== id));
    this.api
      .acknowledgeAlert(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.setError('ack', null),
        error: (err: unknown) => {
          this.setError('ack', describeError(err));
          this.refresh$.next();
        },
      });
  }
}
