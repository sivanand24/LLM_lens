import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { DashboardStore } from '../core/dashboard.store';
import { Summary } from '../core/models';
import { formatCount, formatMs, formatPct } from '../shared/format';

type Direction = 'up-is-bad' | 'neutral';

interface KpiCard {
  label: string;
  value: string;
  sub: string;
  delta: string | null;
  tone: 'bad' | 'good' | 'neutral';
}

function card(
  label: string,
  value: string,
  sub: string,
  delta: number | null,
  formatDelta: (d: number) => string,
  direction: Direction,
): KpiCard {
  if (delta === null || delta === 0) {
    return { label, value, sub, delta: delta === 0 ? 'no change' : null, tone: 'neutral' };
  }
  const arrow = delta > 0 ? '▲' : '▼';
  const tone = direction === 'neutral' ? 'neutral' : delta > 0 ? 'bad' : 'good';
  return { label, value, sub, delta: `${arrow} ${formatDelta(Math.abs(delta))}`, tone };
}

export function buildKpiCards(s: Summary): KpiCard[] {
  const pp = (d: number) => `${(d * 100).toFixed(1)} pp`;
  return [
    card('Calls', formatCount(s.total_calls), `${formatCount(s.pending)} pending checks`,
      s.deltas.total_calls, formatCount, 'neutral'),
    card('Failure rate', formatPct(s.failure_rate), `${formatCount(s.failures)} failed calls`,
      s.deltas.failure_rate, pp, 'up-is-bad'),
    card('Flagged', formatPct(s.flagged_rate), `${formatCount(s.flagged)} calls with any flag`,
      s.deltas.flagged_rate, pp, 'up-is-bad'),
    card('Errors', formatCount(s.errors), `${formatPct(s.error_rate)} of calls`,
      s.deltas.errors, formatCount, 'up-is-bad'),
    card('p95 latency', formatMs(s.p95_latency_ms), `avg ${formatMs(s.avg_latency_ms)}`,
      s.deltas.p95_latency_ms, formatMs, 'up-is-bad'),
    card('Tokens', formatCount(s.total_tokens), 'prompt + completion',
      s.deltas.total_tokens, formatCount, 'neutral'),
  ];
}

@Component({
  selector: 'app-kpi-cards',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="grid">
      @for (c of cards(); track c.label) {
        <div class="lens-panel kpi">
          <div class="label">{{ c.label }}</div>
          <div class="value">{{ c.value }}</div>
          <div class="foot">
            <span class="sub muted">{{ c.sub }}</span>
            @if (c.delta) {
              <span class="delta" [class]="'delta ' + c.tone" title="vs previous window">{{ c.delta }}</span>
            }
          </div>
        </div>
      } @empty {
        @for (i of placeholders; track i) {
          <div class="lens-panel kpi skeleton"><div class="label">&nbsp;</div><div class="value">&nbsp;</div></div>
        }
      }
    </div>
  `,
  styles: `
    .grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px; }
    @media (max-width: 1300px) { .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    @media (max-width: 640px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    .kpi { padding: 14px 16px; }
    .label { font-size: 12px; color: var(--lens-muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .value { font-size: 28px; font-weight: 400; margin: 4px 0 6px; font-variant-numeric: tabular-nums; }
    .foot { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 12px; }
    .sub { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .delta { white-space: nowrap; font-weight: 500; font-variant-numeric: tabular-nums; }
    .delta.bad { color: var(--sev-high); }
    .delta.good { color: var(--sev-none); }
    .delta.neutral { color: var(--lens-muted); }
    .skeleton .value, .skeleton .label { background: #eef0f3; border-radius: 4px; }
  `,
})
export class KpiCardsComponent {
  private readonly store = inject(DashboardStore);
  readonly placeholders = [1, 2, 3, 4, 5, 6];
  readonly cards = computed(() => {
    const summary = this.store.summary();
    return summary ? buildKpiCards(summary) : [];
  });
}
