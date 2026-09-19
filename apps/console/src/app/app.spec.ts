import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { providePrimeNG } from 'primeng/config';

import { App } from './app';
import { ConsolePreset } from './core/console.preset';
import { ConsoleErrorHandler } from './core/error-handler';
import { routes } from './app.routes';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideRouter(routes),
        providePrimeNG({
          theme: {
            preset: ConsolePreset,
            options: { darkModeSelector: '.theme-dark' },
          },
          ripple: false,
        }),
        ConsoleErrorHandler,
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render skip link and chrome telemetry', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.skip-link')?.textContent).toContain('Skip to content');
    expect(el.querySelector('.telemetry')).toBeTruthy();
    expect(el.querySelector('nav[aria-label="Console"]')).toBeTruthy();
    expect(el.querySelector('#content')).toBeTruthy();
  });
});
