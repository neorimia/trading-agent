import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  input,
  viewChild,
} from '@angular/core';
import { createChart, LineSeries, IChartApi, ISeriesApi, LineData, Time } from 'lightweight-charts';

export interface LineChartPoint {
  time: string | number;
  value: number;
}

export interface LineChartSeries {
  name: string;
  color: string;
  points: LineChartPoint[];
}

/** Grafic generic multi-serie (linie) — folosit pentru equity curve, drawdown curve etc.
 * Nu e specific unui instrument (spre deosebire de `CandleChart`). */
@Component({
  selector: 'app-line-chart',
  template: `<div class="line-chart-host" [style.height.px]="height()" #host></div>`,
})
export class LineChart implements AfterViewInit, OnDestroy {
  readonly series = input<LineChartSeries[]>([]);
  readonly height = input(220);
  readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private chart: IChartApi | null = null;
  private lines: ISeriesApi<'Line'>[] = [];

  constructor() {
    effect(() => {
      this.series();
      this.render();
    });
  }

  ngAfterViewInit(): void {
    const el = this.host().nativeElement;
    this.chart = createChart(el, {
      height: this.height(),
      layout: {
        background: { color: '#0e1014' },
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
    this.render();
  }

  ngOnDestroy(): void {
    this.chart?.remove();
  }

  private render(): void {
    if (!this.chart) {
      return;
    }
    for (const line of this.lines) {
      this.chart.removeSeries(line);
    }
    this.lines = [];
    for (const series of this.series()) {
      const line = this.chart.addSeries(LineSeries, {
        color: series.color,
        lineWidth: 2,
        title: series.name,
      });
      const data: LineData<Time>[] = series.points.map((point) => ({
        time: (typeof point.time === 'string'
          ? Math.floor(new Date(point.time).getTime() / 1000)
          : point.time) as Time,
        value: point.value,
      }));
      line.setData(data);
      this.lines.push(line);
    }
    this.chart.timeScale().fitContent();
  }
}
