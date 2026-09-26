import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import type { EChartsOption } from 'echarts';
import { NgxEchartsDirective } from 'ngx-echarts';

import { DashboardStore } from '../core/dashboard.store';
import { Timeseries } from '../core/models';
import { formatMs, severityColor } from '../shared/format';

const CALLS_COLOR = '#5470c6';
const LATENCY_COLOR = '#8d6e63';

/** Static chart setup; data arrives through [merge] so polling doesn't reset the chart. */
export const TREND_BASE_OPTIONS: EChartsOption = {
  animationDuration: 300,
  grid: { left: 48, right: 64, top: 32, bottom: 28 },
  legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 12 } },
  tooltip: { trigger: 'axis', axisPointer: { type: 'line' } },
  xAxis: { type: 'time', axisLabel: { hideOverlap: true, fontSize: 11 } },
  yAxis: [
    { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#eef0f3' } } },
    {
      type: 'value',
      splitLine: { show: false },
      axisLabel: { formatter: (v: number) => formatMs(v) },
    },
  ],
};

export function buildTrendSeries(ts: Timeseries): EChartsOption {
  const points = ts.points;
  return {
    series: [
      {
        name: 'Calls',
        type: 'line',
        showSymbol: false,
        smooth: 0.2,
        lineStyle: { width: 2, color: CALLS_COLOR },
        itemStyle: { color: CALLS_COLOR },
        areaStyle: { color: CALLS_COLOR, opacity: 0.08 },
        data: points.map((p) => [p.bucket, p.calls]),
      },
      {
        name: 'Failures',
        type: 'line',
        showSymbol: false,
        smooth: 0.2,
        lineStyle: { width: 2, color: severityColor('high') },
        itemStyle: { color: severityColor('high') },
        areaStyle: { color: severityColor('high'), opacity: 0.12 },
        data: points.map((p) => [p.bucket, p.failures]),
      },
      {
        name: 'p95 latency',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.5, type: 'dashed', color: LATENCY_COLOR },
        itemStyle: { color: LATENCY_COLOR },
        tooltip: { valueFormatter: (v) => formatMs(typeof v === 'number' ? v : null) },
        data: points.map((p) => [p.bucket, p.p95_latency_ms]),
      },
    ],
  };
}

@Component({
  selector: 'app-trend-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgxEchartsDirective],
  template: `
    <h2 class="lens-panel-title">
      Traffic &amp; failures
      @if (bucketLabel(); as b) { <span class="bucket">per {{ b }}</span> }
    </h2>
    <div class="chart" echarts [options]="baseOptions" [merge]="mergeOptions()"></div>
  `,
  styles: `
    :host { display: block; }
    .chart { height: 300px; }
    .bucket { text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 6px; }
  `,
})
export class TrendChartComponent {
  private readonly store = inject(DashboardStore);
  readonly baseOptions = TREND_BASE_OPTIONS;

  readonly mergeOptions = computed<EChartsOption>(() => {
    const ts = this.store.timeseries();
    return ts ? buildTrendSeries(ts) : {};
  });

  readonly bucketLabel = computed(() => {
    const secs = this.store.timeseries()?.bucket_secs;
    if (!secs) return null;
    if (secs < 3600) return `${secs / 60} min`;
    if (secs < 86_400) return `${secs / 3600} h`;
    return 'day';
  });
}
