import { ErrorHandler, Injectable, signal } from '@angular/core';

@Injectable()
export class ConsoleErrorHandler implements ErrorHandler {
  readonly critical = signal<string | null>(null);

  handleError(error: unknown): void {
    this.critical.set(formatConsoleError(error));
    console.error(error);
  }

  clear(): void {
    this.critical.set(null);
  }
}

function formatConsoleError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  if (error && typeof error === 'object') {
    const rec = error as {
      message?: unknown;
      rejection?: unknown;
      status?: unknown;
      statusText?: unknown;
    };
    if ('rejection' in rec) {
      return formatConsoleError(rec.rejection);
    }
    if (typeof rec.message === 'string' && rec.message.length) {
      return rec.message;
    }
    if (rec.status != null) {
      return `${rec.status} ${rec.statusText ?? ''}`.trim();
    }
    try {
      return JSON.stringify(error);
    } catch {
      return 'Unknown console error';
    }
  }
  return 'Unknown console error';
}
