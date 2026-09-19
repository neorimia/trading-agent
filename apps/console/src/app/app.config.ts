import { ApplicationConfig, ErrorHandler, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { providePrimeNG } from 'primeng/config';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth.interceptor';
import { ConsolePreset } from './core/console.preset';
import { ConsoleErrorHandler } from './core/error-handler';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    providePrimeNG({
      theme: {
        preset: ConsolePreset,
        options: { darkModeSelector: '.theme-dark' },
      },
      ripple: false,
    }),
    ConsoleErrorHandler,
    { provide: ErrorHandler, useExisting: ConsoleErrorHandler },
  ],
};
