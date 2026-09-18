# Graph Report - trading-agent  (2026-09-18)

## Corpus Check
- 67 files · ~46,221 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 738 nodes · 1695 edges · 28 communities (22 shown, 6 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 96 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `75c3119d`
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

## God Nodes (most connected - your core abstractions)
1. `Bar` - 54 edges
2. `ParsedProposal` - 37 edges
3. `run_backtest()` - 32 edges
4. `KillSwitch` - 29 edges
5. `ProposalContext` - 27 edges
6. `RiskEngine` - 26 edges
7. `_engine()` - 25 edges
8. `CsvBarDataSource` - 23 edges
9. `generate_proposal()` - 23 edges
10. `LLMProposal` - 22 edges

## Surprising Connections (you probably didn't know these)
- `DirectOllamaClient` --uses--> `MarketDataCache`  [INFERRED]
  scripts/backtest/run_backtest.py → src/data/cache.py
- `DirectOllamaClient` --uses--> `BinanceKlinesSource`  [INFERRED]
  scripts/backtest/run_backtest.py → src/data/sources.py
- `DirectOllamaClient` --uses--> `CsvBarDataSource`  [INFERRED]
  scripts/backtest/run_backtest.py → src/data/sources.py
- `DirectOllamaClient` --uses--> `VenueCostConfig`  [INFERRED]
  scripts/backtest/run_backtest.py → src/engine/cost_models.py
- `DirectOllamaClient` --uses--> `LLMProposal`  [INFERRED]
  scripts/backtest/run_backtest.py → src/llm/schema.py

## Import Cycles
- None detected.

## Communities (28 total, 6 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (75): MonkeyPatch, Response, RejectedProposal, LLMProposal, Contractul JSON al procesului LLM — modele pure, zero I/O.  Fără câmp de mărime, Ieșirea validă a stratului LLM. extra=forbid: câmpuri necunoscute → invalid., Output invalid sau în afara universului — păstrat brut, niciodată reparat., RejectedProposal (+67 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (57): DirectOllamaClient, Umple cache-ul din script (nu din engine/). Același generate_proposal ca llm/ser, BacktestMetrics, Any, Câmpuri stabile între rulări (fără UUID/wall-clock)., LLMProposalClient, Client, RejectedProposal (+49 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (32): 10. Fazele și planul 30/60/90 de zile, 11. Riscurile critice, în ordinea impactului, 12. Întrebări rămase înainte de implementare, 13. Registrul surselor verificate și decizia finală, 1. Rezumat executiv și limitele verificării, 2. Identitate, activitate, licențe și comunitate, 3. Comparația numerică, 4.10. Hugging Face: FinRobot Forecaster și FinGPT (+24 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (43): 10. Plan de implementare pe 30/60/90 de zile [OPINIE, orientativ], 11. Lista de riscuri critice, 12. Întrebări la care trebuie să răspunzi înainte de implementare, 13. Surse verificate, 14. Concluzie, 1. Rezumat executiv, 2. Tabel comparativ (scoruri 1–10), 3. Top 3 opțiuni (pentru scopul tău specific) (+35 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (29): 10. Ce nu acoperă acest document, 1. Principii de design derivate din regulile absolute, 2. Frontiere de proces, 3. Structură de directoare (extinde secțiunea 1 din instrucțiuni), 4.1 `LLMProposal` (ieșirea validă a stratului LLM), 4.2 `RejectedProposal`, 4.3 `RiskDecision` (ieșirea `risk_engine.evaluate`), 4.4 `OrderRequest` / `OrderResult` (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (32): 0. Reguli absolute — citește ÎNAINTE de orice task, 10. Recapitulare — ce NU face Claude Code în această fază, 1. Structura recomandată a repository-ului, 2. Task 0 — Configurare mediu local, 3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil), 4. Task 2 — Strat LLM local izolat (Qwen3-8B via Ollama), 5. Task 3 — Reguli de risc deterministe (sursa unică de adevăr), 6. Task 4 — Backtesting realist (+24 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (20): 10. Managementul riscului (obligatoriu, nu opțional), 11. Buget, 12. Roluri și responsabilități (RACI simplificat), 13. Riscuri majore și plan de mitigare, 14. Constrângeri legale și fiscale, 15. Dependențe și necunoscute deschise, 16. Glosar rapid, 17. Anexe recomandate (+12 more)

### Community 7 - "Community 7"
Cohesion: 0.23
Nodes (16): _collect_imported_modules(), _env_keys(), _forbidden_hits(), _iter_py_files(), _matches_prefix(), _module_name_for(), Path, Verificare statică a izolării engine ↔ llm (design §6).  Rulează la fiecare comm (+8 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (29): CircuitBreakerOutcome, CircuitBreakerState, CircuitBreaker, Circuit breaker — stare RUNNING/HALTED, reluare doar prin kill switch manual., Contoare consecutive în memorie; tranziția spre HALTED scrie flag-ul de control., CircuitBreakerLimits, KillSwitch, KillSwitchResult (+21 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (54): BaseModel, _decimal_from_yaml(), Any, Decimal, Schema RiskLimits — validare hard la pornire, fără fallback silențios., YAML încarcă numere ca float; trecem prin str ca să nu pierdem precizie., Limite imutabile pe durata rulării. Extra fields interzise., RiskLimits (+46 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (52): Protocol, _bar_from_json(), _bar_to_json(), _cache_key(), canonical_dataset_hash(), _format_report(), MarketDataCache, datetime (+44 more)

### Community 11 - "Community 11"
Cohesion: 0.17
Nodes (11): 1. Versiune instalată, 2. Exemplul oficial reprodus, 3. Rezultate obținute, 4. Inspecția `RiskEngine` (cod instalat, nu documentație), 5. Fișiere create pentru această calificare, 6. Checkpoint DoD (Task 1 / instrucțiuni §3), Ce validează concret `RiskEngine` la fiecare comandă (`SubmitOrder`/`SubmitOrderList`/`ModifyOrder`), Configurație (`RiskEngineConfig`) (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (24): _engine(), _proposal(), Path, RiskEngine.evaluate — fiecare limită din risk_limits.yaml, inclusiv cazuri la pr, _state(), test_avoid_is_no_action(), test_daily_loss_at_threshold_rejected(), test_daily_loss_over_threshold_rejected() (+16 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (41): BacktestEngine, BarType, CurrencyPair, DataFrame, DatetimeIndex, FillModel, Instrument, MakerTakerFeeModel (+33 more)

### Community 21 - "Community 21"
Cohesion: 0.33
Nodes (15): load_risk_limits(), Path, Încarcă și validează config/risk_limits.yaml. Lipsă/invalid → ValueError, fără d, Path, Validare hard a config/risk_limits.yaml — fără fallback la valori implicite., test_empty_file_raises(), test_extra_field_is_rejected(), test_halt_on_unknown_false_raises() (+7 more)

### Community 23 - "Community 23"
Cohesion: 0.07
Nodes (54): Namespace, _dt(), _file_hash(), fill_proposal_cache(), _git_commit(), json_dumps_brief(), main(), _parse_args() (+46 more)

### Community 24 - "Community 24"
Cohesion: 0.12
Nodes (14): PortfolioTracker, datetime, Decimal, Tracker de portofoliu determinist — input pentru RiskEngine în timpul backtestul, BaselineEMACross, BaselineEMACrossConfig, _from_nautilus(), _from_ns() (+6 more)

### Community 25 - "Community 25"
Cohesion: 0.20
Nodes (9): 1. Sursă de date (deviere față de `universe.yaml`), 2. Costuri (nu preț mid), 3. Split cronologic + walk-forward, 4. Holdout — baseline vs LLM, costuri 1× / 2× / 3×, 5. Look-ahead bias, 6. Reproductibilitate, 7. Cum se re-rulează, 8. Fișiere (+1 more)

## Knowledge Gaps
- **153 isolated node(s):** `trading-agent`, `0. Reguli absolute — citește ÎNAINTE de orice task`, `1. Structura recomandată a repository-ului`, `2. Task 0 — Configurare mediu local`, `3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil)` (+148 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ParsedProposal` connect `Community 1` to `Community 0`, `Community 9`, `Community 12`, `Community 23`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `Bar` connect `Community 10` to `Community 24`, `Community 1`, `Community 13`, `Community 23`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `run_backtest()` connect `Community 13` to `Community 24`, `Community 1`, `Community 10`, `Community 23`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Bar` (e.g. with `MarketDataCache` and `DataValidator`) actually correct?**
  _`Bar` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `ParsedProposal` (e.g. with `DirectOllamaClient` and `LLMProposalClient`) actually correct?**
  _`ParsedProposal` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `KillSwitch` (e.g. with `BacktestMetrics` and `CircuitBreaker`) actually correct?**
  _`KillSwitch` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `ProposalContext` (e.g. with `DirectOllamaClient` and `LLMProposalClient`) actually correct?**
  _`ProposalContext` has 6 INFERRED edges - model-reasoned connections that need verification._