import { buildKpiCards } from '../dashboard/kpi-cards.component';
import { Summary, SummaryStats } from '../core/models';
import { displayResponse } from '../logs/call-drawer.component';
import { CallDetail } from '../core/models';
import { formatCount, formatMs, formatPct, isFlagType, timeAgo } from './format';

describe('format helpers', () => {
  it('formats latency', () => {
    expect(formatMs(null)).toBe('—');
    expect(formatMs(840.4)).toBe('840 ms');
    expect(formatMs(1840)).toBe('1.8 s');
    expect(formatMs(12_345)).toBe('12 s');
  });

  it('formats rates and counts', () => {
    expect(formatPct(0.1234)).toBe('12.3%');
    expect(formatCount(1234)).toBe('1,234');
    expect(formatCount(25_000)).toBe('25K');
  });

  it('guards flag types', () => {
    expect(isFlagType('pii')).toBeTrue();
    expect(isFlagType('nope')).toBeFalse();
    expect(isFlagType(3)).toBeFalse();
  });

  it('renders relative time', () => {
    const now = new Date('2026-09-26T10:00:00Z');
    expect(timeAgo('2026-09-26T09:59:30Z', now)).toBe('30s ago');
    expect(timeAgo('2026-09-26T09:15:00Z', now)).toBe('45m ago');
    expect(timeAgo('2026-09-26T07:00:00Z', now)).toBe('3h ago');
  });
});

describe('buildKpiCards', () => {
  const stats: SummaryStats = {
    total_calls: 200, failures: 20, flagged: 40, errors: 5, pending: 0,
    avg_latency_ms: 1200, p95_latency_ms: 2400, total_tokens: 50_000,
    failure_rate: 0.1, flagged_rate: 0.2, error_rate: 0.025,
  };
  const summary = (deltas: Partial<Record<keyof SummaryStats, number | null>>): Summary => ({
    ...stats,
    window: { from: '', to: '', app_id: null },
    previous: stats,
    deltas: { ...Object.fromEntries(Object.keys(stats).map((k) => [k, 0])), ...deltas } as Summary['deltas'],
  });

  it('marks a rising failure rate as bad and falling latency as good', () => {
    const cards = buildKpiCards(summary({ failure_rate: 0.05, p95_latency_ms: -300 }));
    const byLabel = Object.fromEntries(cards.map((c) => [c.label, c]));
    expect(byLabel['Failure rate'].tone).toBe('bad');
    expect(byLabel['Failure rate'].delta).toBe('▲ 5.0 pp');
    expect(byLabel['p95 latency'].tone).toBe('good');
    expect(byLabel['p95 latency'].delta).toBe('▼ 300 ms');
  });

  it('keeps traffic volume neutral', () => {
    const calls = buildKpiCards(summary({ total_calls: 50 })).find((c) => c.label === 'Calls');
    expect(calls?.tone).toBe('neutral');
    expect(calls?.value).toBe('200');
  });

  it('handles a missing previous window', () => {
    const tokens = buildKpiCards(summary({ total_tokens: null })).find((c) => c.label === 'Tokens');
    expect(tokens?.delta).toBeNull();
  });
});

describe('displayResponse', () => {
  const call = (text: string, expected_format: CallDetail['expected_format']) =>
    ({ response: { text, char_len: text.length, finish_reason: 'stop' }, expected_format }) as CallDetail;

  it('pretty-prints valid JSON', () => {
    expect(displayResponse(call('{"a":1}', 'json'))).toBe('{\n  "a": 1\n}');
  });

  it('shows invalid JSON verbatim', () => {
    expect(displayResponse(call('{"a":1,}', 'json'))).toBe('{"a":1,}');
  });

  it('leaves prose alone', () => {
    expect(displayResponse(call('Hello there.', 'text'))).toBe('Hello there.');
  });
});
