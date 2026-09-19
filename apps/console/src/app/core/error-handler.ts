import { ErrorHandler, Injectable, signal } from '@angular/core';

@Injectable()
export class ConsoleErrorHandler implements ErrorHandler {
  readonly critical = signal<string | null>(null);

  handleError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.critical.set(message);
    console.error(error);
  }

  clear(): void {
    this.critical.set(null);
  }
}
