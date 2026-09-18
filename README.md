# Agent local de analiză și trading (multi-asset)

Agent local de analiză și trading care combină un **motor determinist** de execuție/risc/portofoliu (NautilusTrader) cu un **strat de raționament LLM** (Qwen3-8B, local, via Ollama) ținut strict în afara autorității de execuție. LLM-ul propune, codul determinist decide.

**Status actual:** Faza 0 (Cercetare/selectare) — proiect în stadiu de documentare/planificare. Nu există încă cod sursă. Nicio conexiune la broker/exchange live, niciun secret sau credențial real.

## Documente

| Document | Conținut |
|---|---|
| [`brief-proiect-agent-trading-local.md`](brief-proiect-agent-trading-local.md) | Brief de proiect (v1.0): obiectiv, scope, arhitectură propusă, stack tehnic, fazele și gate criteria, buget, riscuri, constrângeri legale. Punct de plecare recomandat. |
| [`CLAUDE-instructiuni-faza-0-4.md`](CLAUDE-instructiuni-faza-0-4.md) | Instrucțiuni de execuție pentru Claude Code: reguli absolute de siguranță, structura de repository recomandată, task-uri detaliate (0–5) cu criterii de acceptare pentru Fazele 0–4. |
| [`design-componente-faza-0-4.md`](design-componente-faza-0-4.md) | Design tehnic la nivel de componentă: frontiere de proces (izolare LLM), interfețe pe modul, contracte de date (JSON), diagrame de secvență pentru fluxurile principale. Punct de plecare pentru `/sc:implement`. |
| [`Raport-agentic-trading-2026-09-18.md`](Raport-agentic-trading-2026-09-18.md) | Evaluare tehnică comparativă a proiectelor open-source de agentic trading (licențe, activitate, fișe tehnice), arhitectura propusă, controale tehnice obligatorii, plan 30/60/90 zile. |
| [`research_agentic_trading_bots.md`](research_agentic_trading_bots.md) | Research tehnic independent asupra acelorași proiecte open-source, cu analiză de compatibilitate Robinhood și plan etapizat Faza 0–6. Folosit ca verificare încrucișată pentru raportul de mai sus. |

## Decizii tehnice cheie

- **Nucleu execuție/risc/portofoliu:** NautilusTrader v1.231.0 (stabil) — nu v2 RC.
- **Alternativă crypto rapidă:** Freqtrade.
- **LLM local:** Qwen3-8B (4-bit) via Ollama — doar propuneri, fără drept de execuție.
- **Broker acțiuni (faza 1):** XTB, execuție manuală (API-ul XTB e dezactivat din martie 2025).
- **Exchange crypto:** Kraken Spot.
- **Robinhood:** nu se folosește în faza 1 (eligibilitate neconfirmată pentru cont din România).

Detalii complete și justificare: [`brief-proiect-agent-trading-local.md`](brief-proiect-agent-trading-local.md#5-decizia-tehnică-și-justificarea-ei).

## Reguli absolute (Fazele 0–4)

1. Nicio cheie/credențială de broker sau exchange **live** — doar date istorice, sandbox/replay, conturi paper/demo, `dry_run: true`.
2. Stratul LLM **nu are** acces direct sau indirect la plasarea de ordine.
3. Limitele de risc sunt definite în cod/config, validate la pornire — niciun output LLM nu le poate modifica.
4. Nimic nu trece din `dry_run`/paper în live automat.
5. Niciun secret în git.

Lista completă: [`CLAUDE-instructiuni-faza-0-4.md`](CLAUDE-instructiuni-faza-0-4.md#0-reguli-absolute--citește-înainte-de-orice-task).

## Structura de repository (planificată)

```
trading-agent/
├── config/
│   ├── risk_limits.yaml           # limite deterministe, validate la pornire
│   └── universe.yaml              # allowlist de instrumente
├── src/
│   ├── data/                      # ingestie și validare date
│   ├── engine/                    # integrare NautilusTrader
│   ├── risk/                      # risk_engine.py — sursa unică de adevăr pentru limite
│   ├── llm/                       # serviciu LLM izolat, doar propuneri
│   ├── execution/                 # order gateway, idempotency, reconciliere
│   ├── monitor/                   # monitor independent, kill switch
│   └── audit/                     # bază de date append-only (SQLite/JSONL)
├── backtests/reports/
├── tests/{unit,integration,adversarial}/
└── docs/qualification-report.md
```

Vezi [`CLAUDE-instructiuni-faza-0-4.md`](CLAUDE-instructiuni-faza-0-4.md#1-structura-recomandată-a-repository-ului) pentru task-urile (0–5) care populează această structură.

## Fazele proiectului

| Faza | Obiectiv | Gate |
|---|---|---|
| 0 — Cercetare/selectare | Decizie de arhitectură, licențe, buget | Document de decizie semnat de PO |
| 1 — Instalare/audit | Mediu izolat, dependențe fixate | Zero credențiale live |
| 2 — Reproducere | Reproducerea unui exemplu oficial de backtest | Rezultate reproductibile |
| 3 — Backtest realist | Costuri, slippage, walk-forward | Fără look-ahead bias nedetectat |
| 4 — Paper trading | Date live, cont simulat, ≥30 sesiuni | Zero incidente critice |
| 5 — Live minim | ≤50 EUR expuși | Doar după Gate Faza 4 complet |
| 6 — Automatizare graduală | Reducerea aprobării manuale | Pe bază de dovezi, nu de calendar |

Detalii complete: [`brief-proiect-agent-trading-local.md`](brief-proiect-agent-trading-local.md#8-faze-și-porți-de-decizie-gate-criteria).
