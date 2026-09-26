import { ClipboardModule } from '@angular/cdk/clipboard';
import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DashboardStore } from '../core/dashboard.store';
import { CallDetail } from '../core/models';
import { FLAG_LABELS, formatMs } from '../shared/format';
import { SeverityChipComponent } from '../shared/severity-chip.component';

/** Pretty-print JSON responses; fall back to the raw text when it isn't valid JSON. */
export function displayResponse(call: CallDetail): string {
  const text = call.response.text;
  if (call.expected_format === 'json' || /^\s*[[{]/.test(text)) {
    try {
      const parsed: unknown = JSON.parse(text);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return text;
    }
  }
  return text;
}

@Component({
  selector: 'app-call-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ClipboardModule,
    DatePipe,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    MatTooltipModule,
    SeverityChipComponent,
  ],
  template: `
    <header class="head">
      <div class="title">
        <span class="mono id">{{ store.selectedCallId() }}</span>
        @if (store.selectedCallId(); as id) {
          <button mat-icon-button [cdkCopyToClipboard]="id" matTooltip="Copy request id" aria-label="Copy request id">
            <mat-icon>content_copy</mat-icon>
          </button>
        }
      </div>
      <button mat-icon-button (click)="store.closeCall()" aria-label="Close"><mat-icon>close</mat-icon></button>
    </header>

    @if (store.selectedCall(); as call) {
      <div class="content">
        <div class="status-line">
          @if (call.check_status === 'pending') {
            <span class="muted">Checks pending…</span>
          } @else {
            <app-severity-chip [severity]="call.severity" />
          }
          <span class="muted">{{ call.created_at | date: 'MMM d, y, HH:mm:ss' }}</span>
        </div>

        <dl class="meta">
          <div><dt>App</dt><dd>{{ call.app_id }}</dd></div>
          <div><dt>Model</dt><dd>{{ call.model }} <span class="muted">({{ call.provider }})</span></dd></div>
          <div><dt>Status</dt><dd [class.bad]="call.status !== 'success'">{{ call.status }}</dd></div>
          <div><dt>Latency</dt><dd>{{ formatMs(call.latency_ms) }}</dd></div>
          <div><dt>Tokens</dt><dd>{{ call.tokens.prompt }} → {{ call.tokens.completion }}</dd></div>
          <div><dt>Finish reason</dt><dd>{{ call.response.finish_reason ?? '—' }}</dd></div>
          <div><dt>Expected format</dt><dd>{{ call.expected_format ?? '—' }}</dd></div>
          <div><dt>Response length</dt><dd>{{ call.response.char_len }} chars</dd></div>
        </dl>

        @if (call.flags.length) {
          <h3>Flags</h3>
          <ul class="flag-list">
            @for (f of call.flags; track f.type) {
              <li [class]="'sev-' + f.severity">
                <div class="flag-head"><strong>{{ flagLabels[f.type] }}</strong><app-severity-chip [severity]="f.severity" /></div>
                <div class="flag-detail mono">{{ f.detail }}</div>
              </li>
            }
          </ul>
        }

        @if (call.error) {
          <h3>Error</h3>
          <pre class="block error">{{ call.error }}</pre>
        }

        <h3>Prompt <span class="muted count">{{ call.prompt.char_len }} chars</span></h3>
        @for (m of call.prompt.messages; track $index) {
          <div class="message">
            <div class="role">{{ m.role }}</div>
            <pre class="block">{{ m.content }}</pre>
          </div>
        }

        <h3>Response</h3>
        @if (call.status === 'success') {
          <pre class="block response">{{ responseText() || '(empty)' }}</pre>
        } @else {
          <div class="muted">No response — the provider call failed.</div>
        }

        @if (hasTags()) {
          <h3>Tags</h3>
          <pre class="block small">{{ tagsText() }}</pre>
        }
      </div>
    } @else if (store.selectedCallId()) {
      <mat-progress-bar mode="indeterminate" />
    }
  `,
  styles: `
    :host { display: block; }
    .head {
      position: sticky; top: 0; z-index: 1;
      display: flex; justify-content: space-between; align-items: center;
      padding: 8px 8px 8px 20px; background: #fff; border-bottom: 1px solid var(--lens-border);
    }
    .title { display: flex; align-items: center; gap: 4px; min-width: 0; }
    .id { font-size: 14px; overflow: hidden; text-overflow: ellipsis; }
    .content { padding: 16px 20px 40px; }
    .status-line { display: flex; align-items: center; gap: 12px; font-size: 13px; }
    .meta {
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 24px;
      margin: 16px 0 8px; padding: 12px 16px; background: #f7f8fa; border-radius: 8px;
    }
    .meta dt { font-size: 11px; color: var(--lens-muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .meta dd { margin: 2px 0 0; font-size: 14px; overflow-wrap: anywhere; }
    .meta dd.bad { color: var(--sev-high); font-weight: 500; }
    h3 { font-size: 13px; font-weight: 500; margin: 20px 0 8px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--lens-muted); }
    .count { text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 4px; }
    .flag-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
    .flag-list li { padding: 8px 12px; border-radius: 6px; background: #f7f8fa; border-left: 3px solid var(--sev-low); }
    .flag-list li.sev-high { border-left-color: var(--sev-high); }
    .flag-list li.sev-medium { border-left-color: var(--sev-medium); }
    .flag-head { display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
    .flag-detail { font-size: 12px; color: var(--lens-muted); margin-top: 4px; overflow-wrap: anywhere; }
    .message + .message { margin-top: 8px; }
    .role { font-size: 11px; font-weight: 500; text-transform: uppercase; color: var(--lens-muted); margin-bottom: 2px; }
    .block {
      margin: 0; padding: 10px 12px; border-radius: 6px; background: #f7f8fa; border: 1px solid var(--lens-border);
      font-family: var(--lens-mono); font-size: 12.5px; line-height: 1.5;
      white-space: pre-wrap; overflow-wrap: anywhere; max-height: 420px; overflow: auto;
    }
    .block.error { background: #fdecea; border-color: #f5c2c0; color: #b71c1c; }
    .block.small { font-size: 12px; }
  `,
})
export class CallDrawerComponent {
  readonly store = inject(DashboardStore);
  readonly flagLabels = FLAG_LABELS;
  readonly formatMs = formatMs;

  readonly responseText = computed(() => {
    const call = this.store.selectedCall();
    return call ? displayResponse(call) : '';
  });
  readonly hasTags = computed(() => Object.keys(this.store.selectedCall()?.tags ?? {}).length > 0);
  readonly tagsText = computed(() => JSON.stringify(this.store.selectedCall()?.tags ?? {}, null, 2));
}
