import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Severity } from '../core/models';

@Component({
  selector: 'app-severity-chip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span [class]="'chip sev-' + severity()">{{ label() || severity() }}</span>`,
  styles: `
    .chip {
      display: inline-block;
      padding: 1px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 500;
      line-height: 18px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      white-space: nowrap;
      color: #fff;
    }
    .sev-high { background: var(--sev-high); }
    .sev-medium { background: var(--sev-medium); color: #3e2c00; }
    .sev-low { background: var(--sev-low); }
    .sev-none { background: var(--sev-none); }
  `,
})
export class SeverityChipComponent {
  readonly severity = input.required<Severity>();
  readonly label = input<string>('');
}
