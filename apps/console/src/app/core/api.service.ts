import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AckResponse,
  AgentEventRow,
  AlertRow,
  BarsResponse,
  HealthResponse,
  MarketInstrument,
  OrderRow,
  PendingApproval,
  PortfolioResponse,
  PositionRow,
  ResearchDocumentView,
  RiskLimitsView,
  SecuritySettings,
  SignalResponse,
  StrategyRow,
} from './models';

function idempotent(key: string): { headers: HttpHeaders } {
  return { headers: new HttpHeaders({ 'Idempotency-Key': key }) };
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>('/v1/health');
  }

  portfolio(): Observable<PortfolioResponse> {
    return this.http.get<PortfolioResponse>('/v1/portfolio');
  }

  alerts(): Observable<AlertRow[]> {
    return this.http.get<AlertRow[]>('/v1/alerts');
  }

  market(symbols?: string): Observable<MarketInstrument[]> {
    const params = symbols ? { symbols } : undefined;
    return this.http.get<MarketInstrument[]>('/v1/market', { params });
  }

  bars(symbol: string, timeframe = '1d'): Observable<BarsResponse> {
    return this.http.get<BarsResponse>(`/v1/market/${symbol}/bars`, {
      params: { timeframe },
    });
  }

  signal(symbol: string): Observable<SignalResponse> {
    return this.http.get<SignalResponse>('/v1/signals', { params: { symbol } });
  }

  positions(): Observable<PositionRow[]> {
    return this.http.get<PositionRow[]>('/v1/positions');
  }

  orders(status?: string): Observable<OrderRow[]> {
    const params = status ? { status } : undefined;
    return this.http.get<OrderRow[]>('/v1/orders', { params });
  }

  pendingApprovals(): Observable<PendingApproval[]> {
    return this.http.get<PendingApproval[]>('/v1/approvals/pending');
  }

  decideApproval(
    id: string,
    approved: boolean,
    reason: string,
  ): Observable<AckResponse> {
    return this.http.post<AckResponse>(
      `/v1/approvals/${id}`,
      { approved, reason, decided_by: 'human' },
      idempotent(`approval-${id}-${approved}`),
    );
  }

  riskLimits(): Observable<RiskLimitsView> {
    return this.http.get<RiskLimitsView>('/v1/risk/limits');
  }

  writeRiskLimits(body: Record<string, unknown>): Observable<AckResponse> {
    return this.http.put<AckResponse>('/v1/risk/limits', body, idempotent(`risk-${Date.now()}`));
  }

  halt(reason: string): Observable<AckResponse> {
    return this.http.post<AckResponse>('/v1/risk/halt', { reason }, idempotent(`halt-${Date.now()}`));
  }

  resetHalt(): Observable<AckResponse> {
    return this.http.post<AckResponse>('/v1/risk/halt/reset', {}, idempotent(`halt-reset-${Date.now()}`));
  }

  agentEvents(): Observable<{ events: AgentEventRow[]; next_cursor: number | null }> {
    return this.http.get<{ events: AgentEventRow[]; next_cursor: number | null }>(
      '/v1/agent/events',
    );
  }

  startAgent(): Observable<AckResponse> {
    return this.http.post<AckResponse>('/v1/agent/start', {}, idempotent(`start-${Date.now()}`));
  }

  stopAgent(): Observable<AckResponse> {
    return this.http.post<AckResponse>('/v1/agent/stop', {}, idempotent(`stop-${Date.now()}`));
  }

  research(instrument?: string): Observable<ResearchDocumentView[]> {
    const params = instrument ? { instrument } : undefined;
    return this.http.get<ResearchDocumentView[]>('/v1/research/documents', { params });
  }

  security(): Observable<SecuritySettings> {
    return this.http.get<SecuritySettings>('/v1/settings/security');
  }

  strategies(): Observable<StrategyRow[]> {
    return this.http.get<StrategyRow[]>('/v1/strategies');
  }

  toggleStrategy(id: string, enabled: boolean, token: string): Observable<AckResponse> {
    return this.http.post<AckResponse>(
      `/v1/strategies/${id}`,
      { enabled, confirmation_token: token },
      idempotent(`strategy-${id}-${enabled}`),
    );
  }
}
