import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApiService } from './api.service';
import { Alert, CallQuery, DashboardFilters } from './models';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;
  const allApps: DashboardFilters = { appId: null, range: '1h' };
  const query: CallQuery = { flag: null, severity: null, q: '', page: 1, pageSize: 25 };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('builds a sliding window ending now', () => {
    const now = new Date('2026-09-26T10:00:00Z');
    const params = api.windowParams({ appId: 'bot', range: '6h' }, now);
    expect(params.get('to')).toBe('2026-09-26T10:00:00.000Z');
    expect(params.get('from')).toBe('2026-09-26T04:00:00.000Z');
    expect(params.get('app_id')).toBe('bot');
  });

  it('omits app_id when all apps are selected', () => {
    expect(api.windowParams(allApps).has('app_id')).toBeFalse();
  });

  it('requests the summary with window params', () => {
    api.getSummary(allApps).subscribe();
    const req = http.expectOne((r) => r.url === '/api/stats/summary');
    expect(req.request.method).toBe('GET');
    expect(req.request.params.has('from')).toBeTrue();
    expect(req.request.params.has('to')).toBeTrue();
    req.flush({});
  });

  it('hits timeseries and flags endpoints', () => {
    api.getTimeseries(allApps).subscribe();
    api.getFlags({ appId: 'bot', range: '15m' }).subscribe();
    expect(http.expectOne((r) => r.url === '/api/stats/timeseries').request.params.has('app_id')).toBeFalse();
    expect(http.expectOne((r) => r.url === '/api/stats/flags').request.params.get('app_id')).toBe('bot');
  });

  it('sends only the call filters that are set', () => {
    api.getCalls(allApps, { ...query, flag: 'refusal', q: '  timeout  ', page: 3, pageSize: 50 }).subscribe();
    const req = http.expectOne((r) => r.url === '/api/calls');
    const p = req.request.params;
    expect(p.get('flag')).toBe('refusal');
    expect(p.get('q')).toBe('timeout');
    expect(p.get('page')).toBe('3');
    expect(p.get('page_size')).toBe('50');
    expect(p.has('severity')).toBeFalse();
    req.flush({ items: [], total: 0, page: 3, page_size: 50 });
  });

  it('encodes the request id for call detail', () => {
    api.getCall('req_a/b').subscribe();
    expect(http.expectOne('/api/calls/req_a%2Fb').request.method).toBe('GET');
  });

  it('unwraps alerts and filters by app', () => {
    const alert = { id: 'a1', rule: 'drift_refusal' } as Alert;
    let result: Alert[] = [];
    api.getAlerts('bot').subscribe((a) => (result = a));
    const req = http.expectOne((r) => r.url === '/api/alerts');
    expect(req.request.params.get('app_id')).toBe('bot');
    req.flush({ alerts: [alert] });
    expect(result).toEqual([alert]);
  });

  it('acknowledges an alert with POST', () => {
    api.acknowledgeAlert('a1').subscribe();
    const req = http.expectOne('/api/alerts/a1/ack');
    expect(req.request.method).toBe('POST');
    req.flush({});
  });

  it('unwraps the app list', () => {
    let apps: string[] = [];
    api.getApps().subscribe((a) => (apps = a.map((x) => x.app_id)));
    http.expectOne('/api/apps').flush({ apps: [{ app_id: 'bot', calls: 3 }] });
    expect(apps).toEqual(['bot']);
  });
});
