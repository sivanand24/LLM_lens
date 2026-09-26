import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  Alert,
  AlertsResponse,
  AppInfo,
  AppsResponse,
  CallDetail,
  CallQuery,
  CallsPage,
  DashboardFilters,
  FlagsResponse,
  RANGE_MS,
  Summary,
  Timeseries,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  /** The window slides: `to` is "now" at request time, so live polling always shows the latest range. */
  windowParams(filters: DashboardFilters, now: Date = new Date()): HttpParams {
    const from = new Date(now.getTime() - RANGE_MS[filters.range]);
    let params = new HttpParams().set('from', from.toISOString()).set('to', now.toISOString());
    if (filters.appId) {
      params = params.set('app_id', filters.appId);
    }
    return params;
  }

  getSummary(filters: DashboardFilters): Observable<Summary> {
    return this.http.get<Summary>(`${this.base}/stats/summary`, { params: this.windowParams(filters) });
  }

  getTimeseries(filters: DashboardFilters): Observable<Timeseries> {
    return this.http.get<Timeseries>(`${this.base}/stats/timeseries`, { params: this.windowParams(filters) });
  }

  getFlags(filters: DashboardFilters): Observable<FlagsResponse> {
    return this.http.get<FlagsResponse>(`${this.base}/stats/flags`, { params: this.windowParams(filters) });
  }

  getCalls(filters: DashboardFilters, query: CallQuery): Observable<CallsPage> {
    let params = this.windowParams(filters)
      .set('page', query.page)
      .set('page_size', query.pageSize);
    if (query.flag) params = params.set('flag', query.flag);
    if (query.severity) params = params.set('severity', query.severity);
    if (query.q.trim()) params = params.set('q', query.q.trim());
    return this.http.get<CallsPage>(`${this.base}/calls`, { params });
  }

  getCall(requestId: string): Observable<CallDetail> {
    return this.http.get<CallDetail>(`${this.base}/calls/${encodeURIComponent(requestId)}`);
  }

  getAlerts(appId: string | null): Observable<Alert[]> {
    const params = appId ? new HttpParams().set('app_id', appId) : undefined;
    return this.http.get<AlertsResponse>(`${this.base}/alerts`, { params }).pipe(map((r) => r.alerts));
  }

  acknowledgeAlert(id: string): Observable<Alert> {
    return this.http.post<Alert>(`${this.base}/alerts/${encodeURIComponent(id)}/ack`, {});
  }

  getApps(): Observable<AppInfo[]> {
    return this.http.get<AppsResponse>(`${this.base}/apps`).pipe(map((r) => r.apps));
  }
}
