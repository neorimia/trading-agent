# Graph Report - trading-agent  (2026-09-18)

## Corpus Check
- 107 files · ~62,124 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1110 nodes · 2722 edges · 65 communities (54 shown, 11 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 228 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d7d95b2e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]

## God Nodes (most connected - your core abstractions)
1. `Bar` - 70 edges
2. `KillSwitch` - 48 edges
3. `ParsedProposal` - 47 edges
4. `PaperTradingLoop` - 37 edges
5. `RiskEngine` - 37 edges
6. `ProposalContext` - 33 edges
7. `run_backtest()` - 32 edges
8. `CircuitBreaker` - 32 edges
9. `SimulatedBroker` - 31 edges
10. `PortfolioTracker` - 30 edges

## Surprising Connections (you probably didn't know these)
- `DirectOllamaClient` --uses--> `MarketDataCache`  [INFERRED]
  scripts/backtest/run_backtest.py → src/data/cache.py
- `DirectOllamaClient` --uses--> `BinanceKlinesSource`  [INFERRED]
  scripts/backtest/run_backtest.py → src/data/sources.py
- `DirectOllamaClient` --uses--> `CsvBarDataSource`  [INFERRED]
  scripts/backtest/run_backtest.py → src/data/sources.py
- `DirectOllamaClient` --uses--> `VenueCostConfig`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/cost_models.py
- `DirectOllamaClient` --uses--> `LLMProposalClient`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/llm_client.py

## Import Cycles
- None detected.

## Communities (65 total, 11 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (84): Response, DirectOllamaClient, _dt(), _file_hash(), fill_proposal_cache(), _git_commit(), json_dumps_brief(), main() (+76 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (56): RejectedProposal, LLMProposalClient, Client, RejectedProposal, Client HTTP către procesul LLM — zero import din src.llm.  Deserializează JSON-u, CachingLLMProposalClient, context_cache_key(), _load_cached() (+48 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (32): 10. Fazele și planul 30/60/90 de zile, 11. Riscurile critice, în ordinea impactului, 12. Întrebări rămase înainte de implementare, 13. Registrul surselor verificate și decizia finală, 1. Rezumat executiv și limitele verificării, 2. Identitate, activitate, licențe și comunitate, 3. Comparația numerică, 4.10. Hugging Face: FinRobot Forecaster și FinGPT (+24 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (43): 10. Plan de implementare pe 30/60/90 de zile [OPINIE, orientativ], 11. Lista de riscuri critice, 12. Întrebări la care trebuie să răspunzi înainte de implementare, 13. Surse verificate, 14. Concluzie, 1. Rezumat executiv, 2. Tabel comparativ (scoruri 1–10), 3. Top 3 opțiuni (pentru scopul tău specific) (+35 more)

### Community 4 - "Community 4"
Cohesion: 0.25
Nodes (8): 10. Ce nu acoperă acest document, 1. Principii de design derivate din regulile absolute, 2. Frontiere de proces, 3. Structură de directoare (extinde secțiunea 1 din instrucțiuni), 6. Verificare statică a izolării (acceptance criteriu Task 2), 7. Decizie de design — cuplarea `engine/` ↔ `llm/`: Opțiunea B, izolare totală, 9. Trasabilitate — componente afectate per task, Design de componente — Agent local de trading, Faza 0–4

### Community 5 - "Community 5"
Cohesion: 0.14
Nodes (14): 0. Reguli absolute — citește ÎNAINTE de orice task, 10. Recapitulare — ce NU face Claude Code în această fază, 1. Structura recomandată a repository-ului, 2. Task 0 — Configurare mediu local, 3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil), 4. Task 2 — Strat LLM local izolat (Qwen3-8B via Ollama), 5. Task 3 — Reguli de risc deterministe (sursa unică de adevăr), 6. Task 4 — Backtesting realist (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (20): 10. Managementul riscului (obligatoriu, nu opțional), 11. Buget, 12. Roluri și responsabilități (RACI simplificat), 13. Riscuri majore și plan de mitigare, 14. Constrângeri legale și fiscale, 15. Dependențe și necunoscute deschise, 16. Glosar rapid, 17. Anexe recomandate (+12 more)

### Community 7 - "Community 7"
Cohesion: 0.23
Nodes (16): _collect_imported_modules(), _env_keys(), _forbidden_hits(), _iter_py_files(), _matches_prefix(), _module_name_for(), Path, Verificare statică a izolării engine ↔ llm (design §6).  Rulează la fiecare comm (+8 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (32): CircuitBreakerOutcome, CircuitBreakerState, datetime, Path, Watchdog flag-only — design §2: fără client de broker propriu., CircuitBreaker, Circuit breaker — stare RUNNING/HALTED, reluare doar prin kill switch manual., Contoare consecutive în memorie; tranziția spre HALTED scrie flag-ul de control. (+24 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (42): Protocol, ApprovalOperator, ApprovalResult, FileApprovalOperator, Path, UUID, ApprovalGate — același flux în paper și live. Nu auto-aprobă intern., Scrie fișierul de decizie. Operatorul uman e un script/CLI, nu gateway-ul. (+34 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (19): _bar_from_json(), _bar_to_json(), _cache_key(), canonical_dataset_hash(), _format_report(), MarketDataCache, datetime, Path (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.17
Nodes (11): 1. Versiune instalată, 2. Exemplul oficial reprodus, 3. Rezultate obținute, 4. Inspecția `RiskEngine` (cod instalat, nu documentație), 5. Fișiere create pentru această calificare, 6. Checkpoint DoD (Task 1 / instrucțiuni §3), Ce validează concret `RiskEngine` la fiecare comandă (`SubmitOrder`/`SubmitOrderList`/`ModifyOrder`), Configurație (`RiskEngineConfig`) (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (24): _engine(), _proposal(), Path, RiskEngine.evaluate — fiecare limită din risk_limits.yaml, inclusiv cazuri la pr, _state(), test_avoid_is_no_action(), test_daily_loss_at_threshold_rejected(), test_daily_loss_over_threshold_rejected() (+16 more)

### Community 13 - "Community 13"
Cohesion: 0.05
Nodes (53): BarType, CurrencyPair, DataFrame, DatetimeIndex, FillModel, Instrument, MakerTakerFeeModel, Order (+45 more)

### Community 21 - "Community 21"
Cohesion: 0.09
Nodes (43): _decimal_from_yaml(), load_risk_limits(), Any, Decimal, Path, Schema RiskLimits — validare hard la pornire, fără fallback silențios., YAML încarcă numere ca float; trecem prin str ca să nu pierdem precizie., Încarcă și validează config/risk_limits.yaml. Lipsă/invalid → ValueError, fără d (+35 more)

### Community 23 - "Community 23"
Cohesion: 0.13
Nodes (21): BinanceKlinesSource, CsvBarDataSource, Client, Path, Sursă locală, zero rețea — pentru teste și fixtures pinned., Client REST public, fără credențiale. Interzis în procesul llm/ (trăiește în dat, _binance_reachable(), datetime (+13 more)

### Community 24 - "Community 24"
Cohesion: 0.15
Nodes (16): KrakenPublicOHLCSource, Client, datetime, OHLC public Kraken — fără autentificare, doar date de piață., Client REST public. Zero chei. Interzis în procesul llm/., bars_to_iterable(), _close_time_utc(), _decimal() (+8 more)

### Community 25 - "Community 25"
Cohesion: 0.20
Nodes (9): 1. Sursă de date (deviere față de `universe.yaml`), 2. Costuri (nu preț mid), 3. Split cronologic + walk-forward, 4. Holdout — baseline vs LLM, costuri 1× / 2× / 3×, 5. Look-ahead bias, 6. Reproductibilitate, 7. Cum se re-rulează, 8. Fișiere (+1 more)

### Community 28 - "Community 28"
Cohesion: 0.11
Nodes (36): Modele de graniță pentru research (design-research-financiar.md §6.1).  Toate au, Intrare de registry. `tos_reviewed_at` e obligatoriu — vezi Regula absolută 1., Ieșirea unui Connector, înainte de extracție/normalizare., Rândul normalizat, persistat în metadata.db — vezi design §5 pentru DDL echivale, RawDocument, ResearchDocument, SourceConfig, load_source_registry() (+28 more)

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (13): 0. Cum se leagă de codul existent, 10. Comparație tehnologii, 11. Surse posibile, 12. Livrabile (rezumat conform cerinței), 2. Variante de implementare, 3. Arhitectură modulară propusă, 4. Schema documentului (Metadata DB), 5. Scoring de relevanță (+5 more)

### Community 30 - "Community 30"
Cohesion: 0.11
Nodes (18): BaselineProposalClient, build_loop(), _dt(), main(), _parse_args(), datetime, Namespace, Path (+10 more)

### Community 31 - "Community 31"
Cohesion: 0.28
Nodes (10): PaperRunResult, Paper trading loop — Faza 5. Nu modifică calea de backtest.  Flux: bar → llm_cli, SessionRecord, BrokerClient, BrokerClient protocol + SimulatedBroker (dry_run local, zero chei de exchange)., OrderGateway, OrderGateway — submit idempotent + cancel_all. Nu importă src.llm., OrderRequest (+2 more)

### Community 32 - "Community 32"
Cohesion: 0.18
Nodes (11): 0. Graf de dependențe (nivel task), 1. Faza 0 — Configurare mediu local ✅ COMPLETĂ (2026-09-18, commit `cd823b3`), 2. Faza 1 — Instalare și calificare NautilusTrader (v1 stabil) ✅ COMPLETĂ (2026-09-18), 3. Faza 2 — Strat LLM local izolat (Qwen3-8B via Ollama) ✅ COMPLETĂ (2026-09-18), 4. Faza 3 — Reguli de risc deterministe ✅ COMPLETĂ (2026-09-18), 5. Faza 4 — Backtesting realist ✅ COMPLETĂ (2026-09-18), 6. Faza 5 — Paper trading ✅ COD + 30 SESIUNI (2026-09-18); revizuire PO/Risk owner deschisă, 7. Poartă continuă — verificare statică a izolării (CI, toate fazele ≥2) (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.42
Nodes (9): ApprovalGate, _bars(), build_loop(), FixedProposalClient, Path, End-to-end paper flow: proposal → risc → aprobare → ordin → audit. Zero rețea., test_avoid_never_reaches_gateway(), test_human_reject_does_not_submit() (+1 more)

### Community 34 - "Community 34"
Cohesion: 0.29
Nodes (8): BacktestEngine, fetch_test_data(), Path, Descarcă datele istorice folosite de exemplul oficial NautilusTrader de backtest, Return the local path to the pinned test data, downloading it if absent/corrupt., _sha256(), Reproduce oficială — NautilusTrader "Backtest (Low-Level API)".  Sursă: docs/get, run()

### Community 35 - "Community 35"
Cohesion: 0.44
Nodes (9): DataValidator, _bar(), DataValidator: gap-uri, duplicate, timestamp-viitor — fără reparare silențioasă., test_duplicate_timestamp_fails(), test_empty_series_fails(), test_future_timestamp_fails(), test_gap_fails(), test_out_of_order_fails() (+1 more)

### Community 37 - "Community 37"
Cohesion: 0.29
Nodes (7): Agent local de analiză și trading (multi-asset), Decizii tehnice cheie, Documente, Fazele proiectului, Instalare (mediu local), Reguli absolute (Fazele 0–4), Structura de repository

### Community 38 - "Community 38"
Cohesion: 0.18
Nodes (11): SimulatedOutcome, Decimal, Execuție locală dry_run. Fill-uri simulate la last_price; fără rețea., SimulatedBroker, Path, Cazuri explicite Faza 5: reconnect, stale, reject/partial, timeout, duplicate., test_duplicate_client_order_id_does_not_resubmit(), test_post_submit_timeout_halts() (+3 more)

### Community 39 - "Community 39"
Cohesion: 0.16
Nodes (14): Exception, _connect(), DuplicateClientOrderId, IdempotencyStore, Connection, Path, UUID, Rezervare client_order_id ÎNAINTE de submit — design §5 execution/. (+6 more)

### Community 40 - "Community 40"
Cohesion: 0.16
Nodes (22): BaseModel, BrokerState, Reconstituire după restart — doar stare, fără resubmit., Snapshot de poziții + ordine deschise, pentru reconciliere., LocalPortfolioSnapshot, Path, Reconciliere local vs broker — la pornire și periodic. Design §8.4., Reconciliation (+14 more)

### Community 41 - "Community 41"
Cohesion: 0.16
Nodes (15): AuditLog, _connect(), Connection, Path, SQLite append-only. Fără UPDATE/DELETE expuse public., Jurnal de audit. `record` e singurul verb public de scriere., Citire pentru rapoarte/watchdog — nu e mutație., AuditEvent (+7 more)

### Community 42 - "Community 42"
Cohesion: 0.12
Nodes (24): KrakenDataClientConfig, SandboxExecutionClientConfig, assert_no_kraken_trading_keys(), build_kraken_data_client_config(), build_sandbox_exec_client_config(), Decimal, Client de date Spot, fără credențiale — feed public., Execuție simulată locală. Niciun ordin nu ajunge la Kraken. (+16 more)

### Community 43 - "Community 43"
Cohesion: 0.23
Nodes (16): Bar, Bară OHLCV. `timestamp` e close-time UTC (lookahead-safe: bara e cunoscută la în, iter_prefixes(), Fiecare prefix bars[:i+1] — helper pentru look-ahead și cache fill., chronological_split(), ChronologicalSplit, Separare cronologică train/validation/holdout + ferestre walk-forward expanding., Expanding window: fold i antrenează pe prefixul 0..i, evaluează pe chunk-ul i+1. (+8 more)

### Community 44 - "Community 44"
Cohesion: 0.20
Nodes (10): 1. Poziționare în sistem și izolare de proces, 2. Flux de date — secvență completă (on_bar → context → propunere), 3. Domeniu de module (fișiere propuse), 4. Specificație API — `research/server.py`, 5. Schemă bază de date — `metadata.db` (SQLite pentru MVP/intermediar, portabil la Postgres), 7. Scoring de relevanță — interfață, 8. Checklist de validare a designului (înainte de `/sc:implement`), 9. Mapare pe versiuni (referință: `research-crawling-financiar.md` §9) (+2 more)

### Community 45 - "Community 45"
Cohesion: 0.30
Nodes (6): AuditEventType, Any, PaperTradingLoop, _payload(), Any, UUID

### Community 46 - "Community 46"
Cohesion: 0.22
Nodes (9): 1. Poziționare față de fazele existente ale proiectului, 2. Graf de dependențe între faze, 4. Ordine de execuție recomandată, 5. Mapare pe structura de teste existentă, 6. Riscuri per fază, 7. Criterii de succes (Gate R), 8. Ce nu intră în acest workflow, 9. Pasul următor (+1 more)

### Community 47 - "Community 47"
Cohesion: 0.22
Nodes (9): 3. Faze — task-uri, dependențe, teste, R0 — Registry & guardrails (fundație, blocantă pentru tot restul), R1a — RSS connector (paralel cu R1b), R1b — API connectors: FRED + SEC EDGAR (paralel cu R1a), R2 — Normalizare & Metadata Store, R3 — Context builder determinist, R4 — Integrare engine, R5 — Teste adversariale & izolare de proces (gate final înainte de backtest cu context real) (+1 more)

### Community 48 - "Community 48"
Cohesion: 0.57
Nodes (7): _gateway(), _order(), Path, OrderGateway — idempotent pe client_order_id, cancel_all., test_cancel_all_clears_open_orders(), test_duplicate_does_not_double_fill(), test_submit_fills_and_is_idempotent()

### Community 49 - "Community 49"
Cohesion: 0.26
Nodes (7): Heartbeat, datetime, Path, Heartbeat pe fișier. Watchdog-ul îl citește fără să importe engine/., Path, test_missing_file_is_stale(), test_write_and_fresh()

### Community 50 - "Community 50"
Cohesion: 0.40
Nodes (5): 6.1 `src/research/models.py`, 6.2 `src/research/connectors.py`, 6.3 `src/research/store.py`, 6.4 `src/research/context_builder.py`, 6. Modele de interfață (Python, spec-level)

### Community 51 - "Community 51"
Cohesion: 0.29
Nodes (6): 1. Mediu și izolare, 2. Rularea de 30 de sesiuni, 3. Criteriile din DoD, 4. Cum se reproduce, 5. Ce rămâne la PO / Risk owner, Raport de paper trading — Faza 5 (Task 5)

### Community 52 - "Community 52"
Cohesion: 0.50
Nodes (4): 9. Trei versiuni, Avansat / producție, Intermediar (1-2 luni), MVP (1-2 săptămâni)

### Community 54 - "Community 54"
Cohesion: 0.67
Nodes (3): 1.1 Juridice / ToS, 1.2 Tehnice, 1. Probleme de analizat înainte de implementare

### Community 58 - "Community 58"
Cohesion: 0.20
Nodes (19): baseline_proposal(), ema(), ema_cross_direction(), market_summary_from_bars(), proposal_context_at(), Decimal, Funcții pure de semnal — folosite de strategii și de testul de look-ahead.  Nu i, Întoarce long/exit după crossover, sau None dacă indicatorii nu sunt gata. (+11 more)

### Community 59 - "Community 59"
Cohesion: 0.25
Nodes (8): 4.1 `LLMProposal` (ieșirea validă a stratului LLM), 4.2 `RejectedProposal`, 4.3 `RiskDecision` (ieșirea `risk_engine.evaluate`), 4.4 `OrderRequest` / `OrderResult`, 4.5 `AuditEvent`, 4.6 `config/risk_limits.yaml` — schema minimă (Task 3, pas 1), 4.7 `config/universe.yaml` — schema minimă, 4. Contracte de date

### Community 60 - "Community 60"
Cohesion: 0.25
Nodes (8): 5. Interfețe pe modul, `audit/`, `data/`, `engine/`, `execution/`, `llm/`, `monitor/`, `risk/`

### Community 62 - "Community 62"
Cohesion: 0.40
Nodes (5): 8.1 Flux normal — propunere → aprobare → execuție, 8.2 Propunere respinsă (schema invalidă sau adversarial), 8.3 Kill switch, 8.4 Reconciliere după restart, 8. Fluxuri principale (sequence diagrams)

## Knowledge Gaps
- **204 isolated node(s):** `trading-agent`, `0. Reguli absolute — citește ÎNAINTE de orice task`, `1. Structura recomandată a repository-ului`, `2. Task 0 — Configurare mediu local`, `3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil)` (+199 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Bar` connect `Community 43` to `Community 1`, `Community 33`, `Community 35`, `Community 10`, `Community 13`, `Community 45`, `Community 24`, `Community 58`, `Community 30`, `Community 31`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `ParsedProposal` connect `Community 1` to `Community 0`, `Community 33`, `Community 40`, `Community 9`, `Community 12`, `Community 13`, `Community 45`, `Community 21`, `Community 58`, `Community 30`, `Community 31`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `SourceConfig` connect `Community 28` to `Community 40`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `Bar` (e.g. with `BaselineProposalClient` and `MarketDataCache`) actually correct?**
  _`Bar` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `KillSwitch` (e.g. with `BaselineProposalClient` and `BacktestMetrics`) actually correct?**
  _`KillSwitch` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `ParsedProposal` (e.g. with `DirectOllamaClient` and `BaselineProposalClient`) actually correct?**
  _`ParsedProposal` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `PaperTradingLoop` (e.g. with `BaselineProposalClient` and `AuditLog`) actually correct?**
  _`PaperTradingLoop` has 23 INFERRED edges - model-reasoned connections that need verification._