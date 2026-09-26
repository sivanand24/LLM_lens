/** Typed shapes of every backend response. Keep in sync with backend/stats/views.py. */

export type Severity = 'high' | 'medium' | 'low' | 'none';
export type FlagType =
  | 'error'
  | 'empty'
  | 'refusal'
  | 'truncated'
  | 'format_invalid'
  | 'length_anomaly'
  | 'slow'
  | 'pii';
export type CallStatus = 'success' | 'provider_error' | 'timeout';
export type CheckStatus = 'pending' | 'done';
export type ExpectedFormat = 'json' | 'text' | null;
export type AlertRule = 'drift_length' | 'drift_refusal';

export interface StatsWindow {
  from: string;
  to: string;
  app_id: string | null;
}

export interface SummaryStats {
  total_calls: number;
  failures: number;
  flagged: number;
  errors: number;
  pending: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_tokens: number;
  failure_rate: number;
  flagged_rate: number;
  error_rate: number;
}

export type SummaryDeltas = { [K in keyof SummaryStats]: number | null };

export interface Summary extends SummaryStats {
  window: StatsWindow;
  previous: SummaryStats;
  deltas: SummaryDeltas;
}

export interface TimeseriesPoint {
  bucket: string;
  calls: number;
  failures: number;
  flagged: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
}

export interface Timeseries {
  window: StatsWindow;
  bucket_secs: number;
  points: TimeseriesPoint[];
}

export interface FlagCount {
  type: FlagType;
  count: number;
  by_severity: Partial<Record<Severity, number>>;
}

export interface FlagsResponse {
  window: StatsWindow;
  flags: FlagCount[];
}

export interface CallListItem {
  request_id: string;
  app_id: string;
  model: string;
  status: CallStatus;
  latency_ms: number;
  severity: Severity;
  is_failure: boolean;
  check_status: CheckStatus;
  created_at: string;
  tokens: number;
  flags: FlagType[];
  prompt_preview: string;
  response_preview: string;
}

export interface CallsPage {
  window: StatsWindow;
  items: CallListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface Flag {
  type: FlagType;
  severity: Exclude<Severity, 'none'>;
  detail: string;
}

export interface ChatMessage {
  role: string;
  content: string;
}

export interface CallDetail {
  request_id: string;
  app_id: string;
  model: string;
  provider: string;
  prompt: { messages: ChatMessage[]; system: string; char_len: number };
  response: { text: string; char_len: number; finish_reason: string | null };
  expected_format: ExpectedFormat;
  tokens: { prompt: number; completion: number; total: number };
  latency_ms: number;
  status: CallStatus;
  error: string | null;
  check_status: CheckStatus;
  flags: Flag[];
  severity: Severity;
  is_failure: boolean;
  tags: Record<string, unknown>;
  created_at: string;
}

export interface Alert {
  id: string;
  app_id: string;
  rule: AlertRule;
  value: number;
  threshold: number;
  detail: string;
  created_at: string;
  updated_at: string;
  acknowledged: boolean;
}

export interface AlertsResponse {
  alerts: Alert[];
}

export interface AppInfo {
  app_id: string;
  calls: number;
}

export interface AppsResponse {
  apps: AppInfo[];
}

// --- client-side state ---

export type RangeKey = '15m' | '1h' | '6h' | '24h' | '7d';

export const RANGE_MS: Record<RangeKey, number> = {
  '15m': 15 * 60_000,
  '1h': 60 * 60_000,
  '6h': 6 * 60 * 60_000,
  '24h': 24 * 60 * 60_000,
  '7d': 7 * 24 * 60 * 60_000,
};

export interface DashboardFilters {
  appId: string | null;
  range: RangeKey;
}

export interface CallQuery {
  flag: FlagType | null;
  severity: Severity | null;
  q: string;
  page: number; // 1-based, as the API expects
  pageSize: number;
}
