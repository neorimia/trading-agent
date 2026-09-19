import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  input,
  viewChild,
} from '@angular/core';
import { createChart, CandlestickSeries, LineSeries, IChartApi, ISeriesApi, CandlestickData, LineData, Time } from 'lightweight-charts';

import { BarPoint } from '../core/models';

@Component({
  selector: 'app-candle-chart',
  template: `<div class="chart-host" #host></div>`,
})
export class CandleChart implements AfterViewInit, OnDestroy {
  readonly bars = input<BarPoint[]>([]);
  readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private chart: IChartApi | null = null;
  private candles: ISeriesApi<'Candlestick'> | null = null;
  private emaFast: ISeriesApi<'Line'> | null = null;
  private emaSlow: ISeriesApi<'Line'> | null = null;

  constructor() {
    effect(() => {
      this.bars();
      this.render();
    });
  }

  ngAfterViewInit(): void {
    const el = this.host().nativeElement;
    this.chart = createChart(el, {
      height: 360,
      layout: {
        background: { color: '#16181d' },
        textColor: '#c8cdd6',
        fontFamily: 'IBM Plex Sans, sans-serif',
      },
      grid: {
        vertLines: { color: '#23262e' },
        horzLines: { color: '#23262e' },
      },
      timeScale: { borderColor: '#2c3038' },
      rightPriceScale: { borderColor: '#2c3038' },
    });
    this.candles = this.chart.addSeries(CandlestickSeries, {
      upColor: '#3d9a6a',
      downColor: '#c45b5b',
      borderVisible: false,
      wickUpColor: '#3d9a6a',
      wickDownColor: '#c45b5b',
    });
    this.emaFast = this.chart.addSeries(LineSeries, { color: '#7aa2d6', lineWidth: 1, title: 'EMA fast' });
    this.emaSlow = this.chart.addSeries(LineSeries, { color: '#c9a227', lineWidth: 1, title: 'EMA slow' });
    this.render();
  }

  ngOnDestroy(): void {
    this.chart?.remove();
  }

  private render(): void {
    if (!this.chart || !this.candles) {
      return;
    }
    const candleData: CandlestickData<Time>[] = [];
    const fast: LineData<Time>[] = [];
    const slow: LineData<Time>[] = [];
    for (const bar of this.bars()) {
      const time = Math.floor(new Date(bar.timestamp).getTime() / 1000) as Time;
      candleData.push({
        time,
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
      });
      if (bar.ema_fast) {
        fast.push({ time, value: Number(bar.ema_fast) });
      }
      if (bar.ema_slow) {
        slow.push({ time, value: Number(bar.ema_slow) });
      }
    }
    this.candles.setData(candleData);
    this.emaFast?.setData(fast);
    this.emaSlow?.setData(slow);
    this.chart.timeScale().fitContent();
  }
}
