import { AlertRule, FlagType, Severity } from '../core/models';

export const FLAG_LABELS: Record<FlagType, string> = {
  error: 'Error',
  empty: 'Empty',
  refusal: 'Refusal',
  truncated: 'Truncated',
  format_invalid: 'Invalid format',
  length_anomaly: 'Length anomaly',
  slow: 'Slow',
  pii: 'PII',
};

export const ALL_FLAGS = Object.keys(FLAG_LABELS) as FlagType[];

export const SEVERITIES: Severity[] = ['high', 'medium', 'low', 'none'];

export const ALERT_LABELS: Record<AlertRule, string> = {
  drift_length: 'Response length drift',
  drift_refusal: 'Refusal rate drift',
};

export function isFlagType(value: unknown): value is FlagType {
  return typeof value === 'string' && value in FLAG_LABELS;
}

// Mirrors the CSS tokens in styles.scss; used where CSS variables can't reach (canvas charts).
const SEVERITY_FALLBACK: Record<Severity, string> = {
  high: '#e53935',
  medium: '#ffb300',
  low: '#78909c',
  none: '#43a047',
};

export function severityColor(severity: Severity): string {
  if (typeof document !== 'undefined') {
    const value = getComputedStyle(document.documentElement).getPropertyValue(`--sev-${severity}`).trim();
    if (value && !value.startsWith('var(')) return value;
  }
  return SEVERITY_FALLBACK[severity];
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  return ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s` : `${Math.round(ms)} ms`;
}

export function formatPct(rate: number | null | undefined, digits = 1): string {
  if (rate === null || rate === undefined) return '—';
  return `${(rate * 100).toFixed(digits)}%`;
}

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return n < 10_000 ? n.toLocaleString('en') : compact.format(n);
}

export function timeAgo(iso: string, now: Date = new Date()): string {
  const secs = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86_400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86_400)}d ago`;
}
