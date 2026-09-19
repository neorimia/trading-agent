import { Component, EventEmitter, Output, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Dialog } from 'primeng/dialog';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Textarea } from 'primeng/textarea';

@Component({
  selector: 'app-confirm-danger',
  imports: [Dialog, Button, InputText, Textarea, FormsModule],
  template: `
    <p-dialog
      [header]="title()"
      [visible]="visible()"
      [modal]="true"
      [closable]="true"
      (visibleChange)="visible.set($event)"
    >
      <p>{{ body() }}</p>
      @if (requireTyped()) {
        <label class="field-label" [attr.for]="'confirm-token'">Type {{ requireTyped() }} to confirm</label>
        <input pInputText id="confirm-token" [(ngModel)]="typed" />
      }
      <label class="field-label" [attr.for]="'confirm-reason'">Reason</label>
      <textarea pTextarea id="confirm-reason" [(ngModel)]="reason" rows="3"></textarea>
      <div class="dialog-actions">
        <p-button label="Cancel" severity="secondary" (onClick)="visible.set(false)" />
        <p-button
          [label]="confirmLabel()"
          severity="danger"
          [disabled]="!canConfirm()"
          (onClick)="confirm()"
        />
      </div>
    </p-dialog>
  `,
})
export class ConfirmDanger {
  readonly title = input('Confirm');
  readonly body = input('');
  readonly confirmLabel = input('Confirm');
  readonly requireTyped = input<string | null>(null);
  readonly visible = signal(false);
  typed = '';
  reason = '';
  @Output() readonly confirmed = new EventEmitter<{ reason: string }>();

  open(): void {
    this.typed = '';
    this.reason = '';
    this.visible.set(true);
  }

  canConfirm(): boolean {
    const token = this.requireTyped();
    if (token && this.typed !== token) {
      return false;
    }
    return this.reason.trim().length > 0;
  }

  confirm(): void {
    if (!this.canConfirm()) {
      return;
    }
    this.confirmed.emit({ reason: this.reason.trim() });
    this.visible.set(false);
  }
}
