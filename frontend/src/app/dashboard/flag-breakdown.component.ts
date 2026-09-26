import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import type { ECElementEvent, EChartsOption } from 'echarts';
import { NgxEchartsDirective } from 'ngx-echarts';

import { DashboardStore } from '../core/dashboard.store';
import { FlagCount, Severity } from '../core/models';
import { FLAG_LABELS, isFlagType, severityColor } from '../shared/format';

const STACK_SEVERITIES: Exclude<Severity, 'none'>[] = ['high', 'medium', 'low'];
const DONUT_PALETTE = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4'];

export function buildBarOptions(flags: FlagCount[]): EChartsOption {
  // Largest at the top: ECharts draws category axes bottom-up.
  const ordered = [...flags].reverse();
  return {
    animationDuration: 300,
    grid: { left: 24, right: 24, top: 28, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 12 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#eef0f3' } } },
    yAxis: {
      type: 'category',
      data: ordered.map((f) => f.type),
      axisLabel: { formatter: (t: string) => (isFlagType(t) ? FLAG_LABELS[t] : t), fontSize: 12 },
      axisTick: { show: false },
    },
    series: STACK_SEVERITIES.map((sev) => ({
      name: sev,
      type: 'bar',
      stack: 'severity',
      barMaxWidth: 18,
      cursor: 'pointer',
      itemStyle: { color: severityColor(sev), borderRadius: 2 },
      data: ordered.map((f) => f.by_severity[sev] ?? 0),
    })),
  };
}

export function buildDonutOptions(flags: FlagCount[]): EChartsOption {
  return {
    animationDuration: 300,
    color: DONUT_PALETTE,
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [
      {
        type: 'pie',
        radius: ['52%', '78%'],
        center: ['50%', '50%'],
        cursor: 'pointer',
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: flags.map((f) => ({ name: FLAG_LABELS[f.type], value: f.count, id: f.type })),
      },
    ],
  };
}

@Component({
  selector: 'app-flag-breakdown',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgxEchartsDirective],
  template: `
    <h2 class="lens-panel-title">
      Flags <span class="hint">click to filter the log</span>
    </h2>
    @if (store.flags().length) {
      <div class="body">
        <div class="bar" echarts [options]="barOptions()" (chartClick)="onBarClick($event)"></div>
        <div class="donut-wrap">
          <div class="donut" echarts [options]="donutOptions()" (chartClick)="onDonutClick($event)"></div>
          <div class="total"><strong>{{ total() }}</strong><span class="muted">flags</span></div>
        </div>
      </div>
    } @else {
      <div class="empty muted">No flags in this window</div>
    }
  `,
  styles: `
    :host { display: block; }
    .hint { text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 6px; font-size: 12px; }
    .body { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); align-items: center; height: 300px; }
    .bar { height: 300px; }
    .donut-wrap { position: relative; height: 220px; }
    .donut { height: 100%; }
    .total {
      position: absolute; inset: 0; pointer-events: none;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
    }
    .total strong { font-size: 22px; font-weight: 500; }
    .total span { font-size: 12px; }
    .empty { height: 300px; display: grid; place-items: center; }
  `,
})
export class FlagBreakdownComponent {
  readonly store = inject(DashboardStore);

  readonly barOptions = computed(() => buildBarOptions(this.store.flags()));
  readonly donutOptions = computed(() => buildDonutOptions(this.store.flags()));
  readonly total = computed(() => this.store.flags().reduce((sum, f) => sum + f.count, 0));

  onBarClick(event: ECElementEvent): void {
    if (isFlagType(event.name)) this.store.setCallQuery({ flag: event.name });
  }

  onDonutClick(event: ECElementEvent): void {
    const data: unknown = event.data;
    if (typeof data === 'object' && data !== null && 'id' in data && isFlagType(data.id)) {
      this.store.setCallQuery({ flag: data.id });
    }
  }
}
