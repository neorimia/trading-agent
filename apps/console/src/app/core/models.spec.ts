import { formatQuote, pnlClass } from './models';

describe('formatQuote', () => {
  it('renders an em dash for missing values', () => {
    expect(formatQuote(null)).toBe('—');
    expect(formatQuote(undefined)).toBe('—');
    expect(formatQuote('')).toBe('—');
  });

  it('renders an em dash instead of crashing on non-numeric input', () => {
    expect(formatQuote('NaN')).toBe('—');
    expect(formatQuote('not-a-number')).toBe('—');
    expect(formatQuote(Number.NaN)).toBe('—');
  });

  it('never renders unrounded float noise', () => {
    // This is the exact class of bug reported in docs/ux-ui/dashboard.md P0.
    expect(formatQuote('5.357063999999999999999999906')).toBe('5.36');
  });

  it('scales decimal places with magnitude by default', () => {
    expect(formatQuote(1234.5)).toBe('1,234.50');
    expect(formatQuote(0.5)).toBe('0.5000');
    expect(formatQuote(0.0123)).toBe('0.0123');
    expect(formatQuote(0.000123)).toBe('0.000123');
  });

  it('honors an explicit decimals override', () => {
    expect(formatQuote('5', { decimals: 0 })).toBe('5');
    expect(formatQuote('5', { decimals: 2 })).toBe('5.00');
  });

  it('appends an optional currency/unit suffix', () => {
    expect(formatQuote('100', { decimals: 2, currency: 'USD' })).toBe('100.00 USD');
  });

  it('handles very large and very small magnitudes without throwing', () => {
    expect(formatQuote(1e21)).toBe('1,000,000,000,000,000,000,000.00');
    expect(formatQuote(1e-10)).toBe('0.000000');
  });

  it('accepts numbers directly, not just strings', () => {
    expect(formatQuote(42)).toBe('42.00');
  });
});

describe('pnlClass', () => {
  it('classifies positive, negative and zero/invalid values', () => {
    expect(pnlClass('1.5')).toBe('pnl-pos');
    expect(pnlClass('-1.5')).toBe('pnl-neg');
    expect(pnlClass('0')).toBe('pnl-zero');
    expect(pnlClass(null)).toBe('pnl-zero');
    expect(pnlClass(undefined)).toBe('pnl-zero');
  });
});
