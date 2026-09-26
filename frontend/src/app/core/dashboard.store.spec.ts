import { HttpErrorResponse } from '@angular/common/http';
import { TestBed, discardPeriodicTasks, fakeAsync, tick } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { ApiService } from './api.service';
import { DashboardStore, POLL_MS, describeError } from './dashboard.store';
import { Alert, CallDetail, CallsPage, FlagsResponse, Summary, Timeseries } from './models';

type ApiSpy = jasmine.SpyObj<ApiService>;

function makeApi(): ApiSpy {
  const api = jasmine.createSpyObj<ApiService>('ApiService', [
    'getSummary', 'getTimeseries', 'getFlags', 'getCalls', 'getCall', 'getAlerts', 'acknowledgeAlert', 'getApps',
  ]);
  api.getSummary.and.returnValue(of({ total_calls: 7 } as Summary));
  api.getTimeseries.and.returnValue(of({ bucket_secs: 60, points: [] } as unknown as Timeseries));
  api.getFlags.and.returnValue(of({ flags: [{ type: 'refusal', count: 2, by_severity: { medium: 2 } }] } as FlagsResponse));
  api.getCalls.and.returnValue(of({ items: [], total: 0, page: 1, page_size: 25 } as unknown as CallsPage));
  api.getCall.and.callFake((id: string) => of({ request_id: id } as CallDetail));
  api.getAlerts.and.returnValue(of([{ id: 'a1' } as Alert, { id: 'a2' } as Alert]));
  api.acknowledgeAlert.and.returnValue(of({ id: 'a1' } as Alert));
  api.getApps.and.returnValue(of([{ app_id: 'bot', calls: 1 }]));
  return api;
}

describe('DashboardStore', () => {
  let api: ApiSpy;
  let store: DashboardStore;

  beforeEach(() => {
    api = makeApi();
    TestBed.configureTestingModule({ providers: [{ provide: ApiService, useValue: api }] });
  });

  function create(): DashboardStore {
    store = TestBed.inject(DashboardStore);
    return store;
  }

  it('loads every panel on the first tick', fakeAsync(() => {
    create();
    tick(0);
    expect(store.summary()?.total_calls).toBe(7);
    expect(store.flags().length).toBe(1);
    expect(store.alerts().length).toBe(2);
    expect(store.apps()[0].app_id).toBe('bot');
    expect(store.calls()?.total).toBe(0);
    expect(store.lastUpdated()).not.toBeNull();
    expect(api.getCall).not.toHaveBeenCalled();
    discardPeriodicTasks();
  }));

  it('polls every 5 s while live and stops when paused', fakeAsync(() => {
    create();
    tick(0);
    expect(api.getSummary).toHaveBeenCalledTimes(1);
    tick(POLL_MS);
    expect(api.getSummary).toHaveBeenCalledTimes(2);

    store.setLive(false);
    tick(POLL_MS * 3);
    expect(api.getSummary).toHaveBeenCalledTimes(2);

    store.setLive(true);
    tick(POLL_MS);
    expect(api.getSummary).toHaveBeenCalledTimes(3);
    discardPeriodicTasks();
  }));

  it('refetches immediately with new filters and resets paging', fakeAsync(() => {
    create();
    tick(0);
    store.setCallQuery({ page: 4 });
    store.setFilters({ appId: 'bot', range: '24h' });
    expect(api.getSummary).toHaveBeenCalledTimes(2);
    expect(api.getSummary.calls.mostRecent().args[0]).toEqual({ appId: 'bot', range: '24h' });
    expect(api.getAlerts.calls.mostRecent().args[0]).toBe('bot');
    expect(store.callQuery().page).toBe(1);
    discardPeriodicTasks();
  }));

  it('reloads only the log when the call query changes', fakeAsync(() => {
    create();
    tick(0);
    store.setCallQuery({ flag: 'pii', page: 3 });
    expect(api.getCalls).toHaveBeenCalledTimes(2);
    expect(api.getCalls.calls.mostRecent().args[1]).toEqual(jasmine.objectContaining({ flag: 'pii', page: 3 }));
    expect(api.getSummary).toHaveBeenCalledTimes(1);

    store.setCallQuery({ severity: 'high' });
    expect(store.callQuery().page).toBe(1);
    discardPeriodicTasks();
  }));

  it('keeps one failing endpoint visible while others succeed', fakeAsync(() => {
    api.getSummary.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500, statusText: 'Server Error' })));
    create();
    tick(0);
    expect(store.summary()).toBeNull();
    expect(store.flags().length).toBe(1); // other panels still load
    expect(store.error()).toBe('500 Server Error');

    api.getSummary.and.returnValue(of({ total_calls: 1 } as Summary));
    tick(POLL_MS);
    expect(store.summary()?.total_calls).toBe(1);
    expect(store.error()).toBeNull();
    discardPeriodicTasks();
  }));

  it('keeps polling after a failed request', fakeAsync(() => {
    api.getFlags.and.returnValue(throwError(() => new HttpErrorResponse({ status: 503 })));
    create();
    tick(0);
    api.getFlags.and.returnValue(of({ flags: [] } as unknown as FlagsResponse));
    tick(POLL_MS);
    expect(api.getFlags).toHaveBeenCalledTimes(2);
    expect(store.flags()).toEqual([]);
    discardPeriodicTasks();
  }));

  it('opens, refreshes and closes the call drawer', fakeAsync(() => {
    create();
    tick(0);
    store.selectCall('req_1');
    expect(store.drawerOpen()).toBeTrue();
    expect(store.selectedCall()?.request_id).toBe('req_1');

    tick(POLL_MS);
    expect(api.getCall).toHaveBeenCalledTimes(2);

    store.closeCall();
    expect(store.drawerOpen()).toBeFalse();
    expect(store.selectedCall()).toBeNull();
    tick(POLL_MS);
    expect(api.getCall).toHaveBeenCalledTimes(2);
    discardPeriodicTasks();
  }));

  it('removes an acknowledged alert optimistically', fakeAsync(() => {
    create();
    tick(0);
    store.acknowledgeAlert('a1');
    expect(api.acknowledgeAlert).toHaveBeenCalledWith('a1');
    expect(store.alerts().map((a) => a.id)).toEqual(['a2']);
    discardPeriodicTasks();
  }));
});

describe('describeError', () => {
  it('explains an unreachable backend', () => {
    expect(describeError(new HttpErrorResponse({ status: 0 }))).toContain('unreachable');
  });

  it('uses the API error body when present', () => {
    const err = new HttpErrorResponse({ status: 400, error: { error: "'from' must be before 'to'" } });
    expect(describeError(err)).toBe("400: 'from' must be before 'to'");
  });
});
