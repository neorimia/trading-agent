# Graph Report - trading-agent  (2026-09-18)

## Corpus Check
- 135 files · ~72,485 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1478 nodes · 3724 edges · 88 communities (77 shown, 11 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 273 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d85ae6b4`
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
- [[_COMMUNITY_Community 36|Community 36]]
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
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]

## God Nodes (most connected - your core abstractions)
1. `Bar` - 70 edges
2. `ParsedProposal` - 52 edges
3. `KillSwitch` - 51 edges
4. `PaperTradingLoop` - 40 edges
5. `ProposalContext` - 38 edges
6. `RiskEngine` - 37 edges
7. `run_backtest()` - 35 edges
8. `CsvBarDataSource` - 33 edges
9. `SimulatedBroker` - 33 edges
10. `CircuitBreaker` - 32 edges

## Surprising Connections (you probably didn't know these)
- `DirectOllamaClient` --uses--> `VenueCostConfig`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/cost_models.py
- `DirectOllamaClient` --uses--> `LLMProposalClient`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/llm_client.py
- `DirectOllamaClient` --uses--> `CachingLLMProposalClient`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/proposal_cache.py
- `DirectOllamaClient` --uses--> `ParsedProposal`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/proposal_types.py
- `DirectOllamaClient` --uses--> `ProposalContext`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/proposal_types.py

## Import Cycles
- None detected.

## Communities (88 total, 11 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.21
Nodes (16): LLMProposal, Ieșirea validă a stratului LLM. extra=forbid: câmpuri necunoscute → invalid., assert_no_broker_keys(), Refuză pornirea dacă procesul vede cheile de broker din .env.engine., validate_bind_host(), _payload(), MonkeyPatch, Server LLM: loopback only, POST /propose orchestrează generate + universe. (+8 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (65): BaselineProposalClient, RejectedProposal, Client determinist: EMA-cross, fără LLM. Folosit când --skip-llm., LLMProposalClient, Client, RejectedProposal, Client HTTP către procesul LLM — zero import din src.llm.  Deserializează JSON-u, CachingLLMProposalClient (+57 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (32): 10. Fazele și planul 30/60/90 de zile, 11. Riscurile critice, în ordinea impactului, 12. Întrebări rămase înainte de implementare, 13. Registrul surselor verificate și decizia finală, 1. Rezumat executiv și limitele verificării, 2. Identitate, activitate, licențe și comunitate, 3. Comparația numerică, 4.10. Hugging Face: FinRobot Forecaster și FinGPT (+24 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (43): 10. Plan de implementare pe 30/60/90 de zile [OPINIE, orientativ], 11. Lista de riscuri critice, 12. Întrebări la care trebuie să răspunzi înainte de implementare, 13. Surse verificate, 14. Concluzie, 1. Rezumat executiv, 2. Tabel comparativ (scoruri 1–10), 3. Top 3 opțiuni (pentru scopul tău specific) (+35 more)

### Community 4 - "Community 4"
Cohesion: 0.15
Nodes (13): 10. Ce nu acoperă acest document, 1. Principii de design derivate din regulile absolute, 2. Frontiere de proces, 3. Structură de directoare (extinde secțiunea 1 din instrucțiuni), 6. Verificare statică a izolării (acceptance criteriu Task 2), 7. Decizie de design — cuplarea `engine/` ↔ `llm/`: Opțiunea B, izolare totală, 8.1 Flux normal — propunere → aprobare → execuție, 8.2 Propunere respinsă (schema invalidă sau adversarial) (+5 more)

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
Cohesion: 0.12
Nodes (21): Path, KillSwitch, KillSwitchResult, Path, Semnal HALT partajat prin `runtime/control/halt.flag` (sau alt path injectat)., Scrie flag-ul. Idempotent: un al doilea apel lasă sistemul tot în HALT., Șterge flag-ul. Doar acțiune manuală — reluare după HALT nu e automată., Path (+13 more)

### Community 9 - "Community 9"
Cohesion: 0.16
Nodes (19): ApprovalGate, ApprovalOperator, ApprovalResult, FileApprovalOperator, Path, UUID, ApprovalGate — același flux în paper și live. Nu auto-aprobă intern., Scrie fișierul de decizie. Operatorul uman e un script/CLI, nu gateway-ul. (+11 more)

### Community 10 - "Community 10"
Cohesion: 0.11
Nodes (28): Protocol, _bar_from_json(), _bar_to_json(), _cache_key(), canonical_dataset_hash(), _format_report(), MarketDataCache, datetime (+20 more)

### Community 11 - "Community 11"
Cohesion: 0.17
Nodes (11): 1. Versiune instalată, 2. Exemplul oficial reprodus, 3. Rezultate obținute, 4. Inspecția `RiskEngine` (cod instalat, nu documentație), 5. Fișiere create pentru această calificare, 6. Checkpoint DoD (Task 1 / instrucțiuni §3), Ce validează concret `RiskEngine` la fiecare comandă (`SubmitOrder`/`SubmitOrderList`/`ModifyOrder`), Configurație (`RiskEngineConfig`) (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (24): _engine(), _proposal(), Path, RiskEngine.evaluate — fiecare limită din risk_limits.yaml, inclusiv cazuri la pr, _state(), test_avoid_is_no_action(), test_daily_loss_at_threshold_rejected(), test_daily_loss_over_threshold_rejected() (+16 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (29): BarType, CurrencyPair, DataFrame, DatetimeIndex, FillModel, MakerTakerFeeModel, _bar_type(), _bars_frame() (+21 more)

### Community 21 - "Community 21"
Cohesion: 0.33
Nodes (15): load_risk_limits(), Path, Încarcă și validează config/risk_limits.yaml. Lipsă/invalid → ValueError, fără d, Path, Validare hard a config/risk_limits.yaml — fără fallback la valori implicite., test_empty_file_raises(), test_extra_field_is_rejected(), test_halt_on_unknown_false_raises() (+7 more)

### Community 23 - "Community 23"
Cohesion: 0.13
Nodes (21): BinanceKlinesSource, CsvBarDataSource, Client, Path, Sursă locală, zero rețea — pentru teste și fixtures pinned., Client REST public, fără credențiale. Interzis în procesul llm/ (trăiește în dat, _binance_reachable(), datetime (+13 more)

### Community 24 - "Community 24"
Cohesion: 0.42
Nodes (7): bars_to_iterable(), _close_time_utc(), _decimal(), _ms(), datetime, Surse de bare: Binance public klines (backfill opțional) și CSV local.  Execuția, require_utc()

### Community 25 - "Community 25"
Cohesion: 0.20
Nodes (9): 1. Sursă de date (deviere față de `universe.yaml`), 2. Costuri (nu preț mid), 3. Split cronologic + walk-forward, 4. Holdout — baseline vs LLM, costuri 1× / 2× / 3×, 5. Look-ahead bias, 6. Reproductibilitate, 7. Cum se re-rulează, 8. Fișiere (+1 more)

### Community 28 - "Community 28"
Cohesion: 0.14
Nodes (29): load_source_registry(), Path, Registry de surse — nicio sursă nu e utilizabilă fără tos_reviewed_at valid (Reg, Încarcă și validează config/research_sources.yaml. Lipsă/invalid → ValueError, f, Path, R0 — modele de graniță + registry de surse. Fără rețea, fără fallback silențios., Fișierul real din config/ nu are surse revizuite manual încă — trebuie să fie go, test_missing_registry_file_raises() (+21 more)

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (13): 0. Cum se leagă de codul existent, 10. Comparație tehnologii, 11. Surse posibile, 12. Livrabile (rezumat conform cerinței), 2. Variante de implementare, 3. Arhitectură modulară propusă, 4. Schema documentului (Metadata DB), 5. Scoring de relevanță (+5 more)

### Community 30 - "Community 30"
Cohesion: 0.08
Nodes (52): ApiConnector, Connector, Client, datetime, Connectors — Protocol comun (mirror DataSource din src/data/sources.py) + RSS/AP, Adapter per API oficial (FRED, SEC EDGAR) — dispatch intern după host-ul din bas, Impune rate_limit_per_min al sursei (config, nu hardcodat) — un sleep măsurabil, Cheie stabilă sha256(url|fetched_at) — pointer pe care RawDocumentStore (R2) îl (+44 more)

### Community 31 - "Community 31"
Cohesion: 0.16
Nodes (19): MetadataStore, Path, Fișiere imutabile, cheie = raw_payload_ref — mirror MarketDataCache (src/data/ca, Wrapper SQLite peste schema design-research-financiar.md §5., (related_doc_id, relation_type) pentru un doc_id — folosit de teste de dedup/adv, RawDocumentStore, datetime, Path (+11 more)

### Community 32 - "Community 32"
Cohesion: 0.18
Nodes (11): 0. Graf de dependențe (nivel task), 1. Faza 0 — Configurare mediu local ✅ COMPLETĂ (2026-09-18, commit `cd823b3`), 2. Faza 1 — Instalare și calificare NautilusTrader (v1 stabil) ✅ COMPLETĂ (2026-09-18), 3. Faza 2 — Strat LLM local izolat (Qwen3-8B via Ollama) ✅ COMPLETĂ (2026-09-18), 4. Faza 3 — Reguli de risc deterministe ✅ COMPLETĂ (2026-09-18), 5. Faza 4 — Backtesting realist ✅ COMPLETĂ (2026-09-18), 6. Faza 5 — Paper trading ✅ COD + 30 SESIUNI (2026-09-18); revizuire PO/Risk owner deschisă, 7. Poartă continuă — verificare statică a izolării (CI, toate fazele ≥2) (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.18
Nodes (12): BacktestMetrics, Any, Câmpuri stabile între rulări (fără UUID/wall-clock)., ProposalClient, _from_nautilus(), _from_ns(), LLMAssistedStrategy, LLMAssistedStrategyConfig (+4 more)

### Community 34 - "Community 34"
Cohesion: 0.29
Nodes (8): BacktestEngine, fetch_test_data(), Path, Descarcă datele istorice folosite de exemplul oficial NautilusTrader de backtest, Return the local path to the pinned test data, downloading it if absent/corrupt., _sha256(), Reproduce oficială — NautilusTrader "Backtest (Low-Level API)".  Sursă: docs/get, run()

### Community 35 - "Community 35"
Cohesion: 0.23
Nodes (14): timedelta, timeframe_delta(), DataValidator, datetime, Validare hard a seriilor OHLCV: gap-uri, duplicate, timestamp-uri în viitor.  Nu, ValidationIssue, _bar(), DataValidator: gap-uri, duplicate, timestamp-viitor — fără reparare silențioasă. (+6 more)

### Community 36 - "Community 36"
Cohesion: 0.21
Nodes (15): DocumentCategory, extract_text(), find_mentioned_assets(), normalize_document(), Keyword match simplu, whole-word case-insensitive (MVP din research-crawling-fin, Extracție + normalizare → ResearchDocument. `category` e furnizat de caller (nu, Boilerplate removal (trafilatura) — HTML tratat strict ca date brute, niciodată, R2 — extracție (boilerplate removal) + normalizare → ResearchDocument. Fără rețe (+7 more)

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (7): Agent local de analiză și trading (multi-asset), Decizii tehnice cheie, Documente, Fazele proiectului, Instalare (mediu local), Reguli absolute (Fazele 0–4), Structura de repository

### Community 38 - "Community 38"
Cohesion: 0.16
Nodes (15): AuditLog, _connect(), Connection, Path, SQLite append-only. Fără UPDATE/DELETE expuse public., Jurnal de audit. `record` e singurul verb public de scriere., Citire pentru rapoarte/watchdog — nu e mutație., AuditEvent (+7 more)

### Community 39 - "Community 39"
Cohesion: 0.11
Nodes (28): Exception, BrokerClient, BrokerClient protocol + SimulatedBroker (dry_run local, zero chei de exchange)., _connect(), DuplicateClientOrderId, IdempotencyStore, Connection, Path (+20 more)

### Community 40 - "Community 40"
Cohesion: 0.11
Nodes (32): BaseModel, PaperTradingConfig, PaperRunResult, Path, Paper trading loop — Faza 5. Nu modifică calea de backtest.  Flux: bar → llm_cli, SessionRecord, BrokerState, Snapshot de poziții + ordine deschise, pentru reconciliere. (+24 more)

### Community 41 - "Community 41"
Cohesion: 0.19
Nodes (15): _load_dotenv_llm(), main(), propose(), ProposeRequest, RejectedProposal, HTTP loopback — singurul punct de intrare extern al procesului LLM.  Host-ul e f, Corpul POST /propose — independent de engine.ProposalContext., load_llm_settings() (+7 more)

### Community 42 - "Community 42"
Cohesion: 0.07
Nodes (48): KrakenDataClientConfig, SandboxExecutionClientConfig, build_kraken_data_client_config(), build_paper_node_config(), build_sandbox_exec_client_config(), Decimal, Cale B: date publice Kraken + execuție sandbox Nautilus. Zero chei de trading., Client de date Spot, fără credențiale — feed public. (+40 more)

### Community 43 - "Community 43"
Cohesion: 0.27
Nodes (12): chronological_split(), ChronologicalSplit, Separare cronologică train/validation/holdout + ferestre walk-forward expanding., Expanding window: fold i antrenează pe prefixul 0..i, evaluează pe chunk-ul i+1., walk_forward_folds(), WalkForwardFold, _bars(), Walk-forward și split cronologic — holdout neatins de ferestre. (+4 more)

### Community 44 - "Community 44"
Cohesion: 0.20
Nodes (10): 1. Poziționare în sistem și izolare de proces, 2. Flux de date — secvență completă (on_bar → context → propunere), 3. Domeniu de module (fișiere propuse), 4. Specificație API — `research/server.py`, 5. Schemă bază de date — `metadata.db` (SQLite pentru MVP/intermediar, portabil la Postgres), 7. Scoring de relevanță — interfață, 8. Checklist de validare a designului (înainte de `/sc:implement`), 9. Mapare pe versiuni (referință: `research-crawling-financiar.md` §9) (+2 more)

### Community 45 - "Community 45"
Cohesion: 0.27
Nodes (17): build_external_context(), timedelta, Randare determinist — aceleași `documents` + `as_of` (+ contradicting_pairs) → a, _document(), datetime, R3 — build_external_context: funcție pură, determinist, fără rețea/LLM.  Cazuri, test_contradicting_documents_both_appear_with_explicit_label(), test_contradicting_pair_referencing_document_outside_list_is_ignored() (+9 more)

### Community 46 - "Community 46"
Cohesion: 0.22
Nodes (9): 1. Poziționare față de fazele existente ale proiectului, 2. Graf de dependențe între faze, 4. Ordine de execuție recomandată, 5. Mapare pe structura de teste existentă, 6. Riscuri per fază, 7. Criterii de succes (Gate R), 8. Ce nu intră în acest workflow, 9. Pasul următor (+1 more)

### Community 47 - "Community 47"
Cohesion: 0.22
Nodes (9): 3. Faze — task-uri, dependențe, teste, R0 — Registry & guardrails (fundație, blocantă pentru tot restul), R1a — RSS connector (paralel cu R1b), R1b — API connectors: FRED + SEC EDGAR (paralel cu R1a), R2 — Normalizare & Metadata Store, R3 — Context builder determinist, R4 — Integrare engine, R5 — Teste adversariale & izolare de proces (gate final înainte de backtest cu context real) (+1 more)

### Community 48 - "Community 48"
Cohesion: 0.21
Nodes (17): InstrumentRules, Reguli de lot/notional pentru rotunjirea cantității. extra=forbid., _floor_to_lot(), Decimal, Dimensionare de poziție — funcție pură, fără I/O, fără input LLM., qty = min(cap_notional / price, risk_budget / (stop + cost + slippage)), rotunji, size_position(), size_position e o funcție pură: fără I/O, fără input din LLM. (+9 more)

### Community 49 - "Community 49"
Cohesion: 0.19
Nodes (9): _dt(), _parse_args(), datetime, Namespace, CLI paper trading — Cale B, dry_run obligatoriu., PortfolioTracker, datetime, Decimal (+1 more)

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
Cohesion: 0.18
Nodes (21): Bar, Bară OHLCV. `timestamp` e close-time UTC (lookahead-safe: bara e cunoscută la în, baseline_proposal(), ema(), ema_cross_direction(), market_summary_from_bars(), proposal_context_at(), Decimal (+13 more)

### Community 59 - "Community 59"
Cohesion: 0.36
Nodes (9): _fmt_dt(), _interpretation(), datetime, R3 — context builder determinist (design-research-financiar.md §6.4, research-cr, Strat de analiză/semnal (§7: rezumat/analiză), separat explicit de Facts:., _render_document(), _require_utc(), Rândul normalizat, persistat în metadata.db — vezi design §5 pentru DDL echivale (+1 more)

### Community 60 - "Community 60"
Cohesion: 0.33
Nodes (6): Limite imutabile pe durata rulării. Extra fields interzise., RiskLimits, PortfolioState, Expunere și metrici de risc deja realizate — niciun câmp nu vine din LLM., RiskEngine — singura cale de la ParsedProposal la o decizie de mărime.  Primește, RiskEngine

### Community 61 - "Community 61"
Cohesion: 0.07
Nodes (53): BrokerMode, constraints_for(), execution_pair(), get_instrument(), historical_symbol(), InstrumentConstraints, nautilus_symbol(), HistoricalSource (+45 more)

### Community 62 - "Community 62"
Cohesion: 0.15
Nodes (19): _decimal_from_yaml(), Any, Decimal, Schema RiskLimits — validare hard la pornire, fără fallback silențios., YAML încarcă numere ca float; trecem prin str ca să nu pierdem precizie., load_instrument_rules(), _optional_positive_decimal(), Any (+11 more)

### Community 66 - "Community 66"
Cohesion: 0.47
Nodes (9): _engine(), _proposal(), Path, Bypass de risc prin conținut LLM — respins indiferent de rationale/confidence., _state(), test_exit_at_exposure_limit_does_not_increase_exposure(), test_halt_rejects_urgent_high_confidence_proposal(), test_rationale_cannot_override_drawdown_limit() (+1 more)

### Community 67 - "Community 67"
Cohesion: 0.16
Nodes (16): CircuitBreakerOutcome, CircuitBreakerState, CircuitBreaker, Circuit breaker — stare RUNNING/HALTED, reluare doar prin kill switch manual., Contoare consecutive în memorie; tranziția spre HALTED scrie flag-ul de control., CircuitBreakerLimits, Kill switch independent — stare externă pe fișier, nu variabilă de proces.  Apel, _breaker() (+8 more)

### Community 68 - "Community 68"
Cohesion: 0.22
Nodes (14): parse_proposal(), RejectedProposal, Elimină blocurile <think>…</think> din output-ul Qwen3. Nu repară JSON-ul., Validează JSON-ul brut pe schema LLMProposal. Invalid → respins, nu reparat., strip_think_blocks(), validate_against_universe(), test_injected_extra_fields_are_rejected_not_executed(), Validare schemă: output invalid e respins, nu reparat. (+6 more)

### Community 69 - "Community 69"
Cohesion: 0.20
Nodes (9): BaselineEMACross, BaselineEMACrossConfig, _from_nautilus(), _from_ns(), datetime, NautilusBar, Strategie baseline EMA-cross, long-only, fără LLM — trece prin RiskEngine., EMA-cross determinist. Mărimea poziției vine exclusiv din RiskEngine. (+1 more)

### Community 70 - "Community 70"
Cohesion: 0.29
Nodes (10): compute_content_hash(), Hash pe text normalizat (whitespace colapsat, lowercase), nu pe titlu — Risc R2, _document(), Path, R2 — deduplicare pe content_hash (checkpoint R2, workflow_research-financiar.md, Testul explicit de coliziune cerut de workflow §3 — insert SQL brut cu content_h, test_compute_content_hash_differs_for_different_text(), test_compute_content_hash_ignores_whitespace_and_case_differences() (+2 more)

### Community 71 - "Community 71"
Cohesion: 0.29
Nodes (6): AuditEventType, Any, PaperTradingLoop, _payload(), Any, UUID

### Community 72 - "Community 72"
Cohesion: 0.21
Nodes (16): DirectOllamaClient, _dt(), _file_hash(), fill_proposal_cache(), _git_commit(), json_dumps_brief(), main(), _parse_args() (+8 more)

### Community 73 - "Community 73"
Cohesion: 0.26
Nodes (12): RejectedProposal, _build_user_message(), _extract_message_content(), generate_proposal(), ModelConfig, ProposalInput, Any, Client (+4 more)

### Community 74 - "Community 74"
Cohesion: 0.14
Nodes (15): build_loop(), main(), Path, SimulatedOutcome, Decimal, Reconstituire după restart — doar stare, fără resubmit., Execuție locală dry_run. Fill-uri simulate la last_price; fără rețea., SimulatedBroker (+7 more)

### Community 75 - "Community 75"
Cohesion: 0.25
Nodes (8): 4.1 `LLMProposal` (ieșirea validă a stratului LLM), 4.2 `RejectedProposal`, 4.3 `RiskDecision` (ieșirea `risk_engine.evaluate`), 4.4 `OrderRequest` / `OrderResult`, 4.5 `AuditEvent`, 4.6 `config/risk_limits.yaml` — schema minimă (Task 3, pas 1), 4.7 `config/universe.yaml` — schema minimă, 4. Contracte de date

### Community 76 - "Community 76"
Cohesion: 0.20
Nodes (13): ContextRequest, ContextResponse, _contradicting_pairs(), get_context(), _load_dotenv_research(), main(), _metadata_store(), Request (+5 more)

### Community 77 - "Community 77"
Cohesion: 0.25
Nodes (8): 5. Interfețe pe modul, `audit/`, `data/`, `engine/`, `execution/`, `llm/`, `monitor/`, `risk/`

### Community 78 - "Community 78"
Cohesion: 0.24
Nodes (12): _collect_imported_modules(), _forbidden_hits(), _iter_py_files(), _matches_prefix(), _module_name_for(), Path, Verificare statică a izolării research <-> engine/risk/execution (design §1, §6, Adversarial: un `.env.research` atacat/corupt cu RESEARCH_SERVER_HOST=0.0.0.0 nu (+4 more)

### Community 79 - "Community 79"
Cohesion: 0.37
Nodes (12): _as_of(), _client(), datetime, ResearchClient: fail-open spre None la orice eroare — niciodată excepție necontr, test_get_context_never_raises_on_any_error(), test_get_context_parses_external_context(), test_get_context_returns_none_on_204(), test_get_context_returns_none_on_5xx() (+4 more)

### Community 80 - "Community 80"
Cohesion: 0.23
Nodes (13): _client_for(), _config(), _malicious_document(), _ollama_response(), Client, Response, Teste adversariale de conținut research: text injectat dintr-o sursă externă nu, Chiar dacă modelul 'cade' în injecție și emite câmpuri de execuție, schema stric (+5 more)

### Community 81 - "Community 81"
Cohesion: 0.18
Nodes (15): Heartbeat, datetime, Path, Heartbeat pe fișier. Watchdog-ul îl citește fără să importe engine/., _bars(), build_loop(), FixedProposalClient, Path (+7 more)

### Community 82 - "Community 82"
Cohesion: 0.32
Nodes (11): validate_bind_host(), _document(), MonkeyPatch, Path, Server research: loopback only, GET /context orchestrează MetadataStore + contex, test_context_marks_contradicting_sources(), test_context_rejects_extra_query_param(), test_context_returns_200_with_documents() (+3 more)

### Community 83 - "Community 83"
Cohesion: 0.23
Nodes (8): Row, compute_doc_id(), _dt_to_iso(), _iso_to_dt(), datetime, R2 — RawDocumentStore, MetadataStore, extracție+normalizare (design-research-fin, True dacă rândul a fost scris în `documents`. False dacă doc.content_hash exista, sha256(url|fetched_at) — identic cu _raw_payload_ref din connectors.py (design §

### Community 84 - "Community 84"
Cohesion: 0.22
Nodes (7): KrakenPublicOHLCSource, Client, datetime, OHLC public Kraken — DataSource fără autentificare, doar date de piață., Client REST public. Zero chei. Interzis în procesul llm/., Kraken public OHLC — fără auth, mapare ETHUSD., test_kraken_source_parses_public_ohlc()

### Community 85 - "Community 85"
Cohesion: 0.40
Nodes (4): Instrument, Order, OrderBook, Price

### Community 86 - "Community 86"
Cohesion: 0.29
Nodes (12): _client_for(), _config(), _ollama_reachable(), _ollama_response(), Client, Response, Teste adversariale de conținut: input injectat nu poate declanșa execuție/risc., _sample_context() (+4 more)

### Community 87 - "Community 87"
Cohesion: 0.27
Nodes (7): Contractul JSON al procesului LLM — modele pure, zero I/O.  Fără câmp de mărime, Output invalid sau în afara universului — păstrat brut, niciodată reparat., RejectedProposal, _outcome(), Sincronizare llm.schema ↔ engine.proposal_types (design §7)., test_proposal_schemas_agree(), test_rejected_schemas_agree()

## Knowledge Gaps
- **204 isolated node(s):** `trading-agent`, `0. Reguli absolute — citește ÎNAINTE de orice task`, `1. Structura recomandată a repository-ului`, `2. Task 0 — Configurare mediu local`, `3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil)` (+199 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ResearchDocument` connect `Community 59` to `Community 36`, `Community 70`, `Community 40`, `Community 45`, `Community 80`, `Community 82`, `Community 83`, `Community 28`, `Community 30`, `Community 31`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `RawDocument` connect `Community 30` to `Community 36`, `Community 40`, `Community 83`, `Community 28`, `Community 31`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Why does `ParsedProposal` connect `Community 1` to `Community 33`, `Community 66`, `Community 71`, `Community 72`, `Community 73`, `Community 40`, `Community 9`, `Community 12`, `Community 49`, `Community 81`, `Community 87`, `Community 58`, `Community 60`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `Bar` (e.g. with `BaselineProposalClient` and `MarketDataCache`) actually correct?**
  _`Bar` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ParsedProposal` (e.g. with `DirectOllamaClient` and `BaselineProposalClient`) actually correct?**
  _`ParsedProposal` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `KillSwitch` (e.g. with `BaselineProposalClient` and `BacktestMetrics`) actually correct?**
  _`KillSwitch` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `PaperTradingLoop` (e.g. with `BaselineProposalClient` and `AuditLog`) actually correct?**
  _`PaperTradingLoop` has 25 INFERRED edges - model-reasoned connections that need verification._