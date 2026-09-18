# Graph Report - trading-agent  (2026-09-18)

## Corpus Check
- 43 files · ~38,008 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 472 nodes · 904 edges · 23 communities (19 shown, 4 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 22 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `067bf644`
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

## God Nodes (most connected - your core abstractions)
1. `KillSwitch` - 26 edges
2. `_engine()` - 25 edges
3. `generate_proposal()` - 21 edges
4. `_proposal()` - 21 edges
5. `_state()` - 21 edges
6. `LLMProposal` - 20 edges
7. `Brief de proiect — Agent local de analiză și trading (multi-asset)` - 18 edges
8. `load_risk_limits()` - 17 edges
9. `size_position()` - 17 edges
10. `ParsedProposal` - 16 edges

## Surprising Connections (you probably didn't know these)
- `_proposal()` --references--> `ParsedProposal`  [EXTRACTED]
  tests/adversarial/test_risk_bypass.py → src/engine/proposal_types.py
- `_proposal()` --references--> `ParsedProposal`  [EXTRACTED]
  tests/unit/test_risk_engine.py → src/engine/proposal_types.py
- `test_validate_bind_host_accepts_loopback()` --calls--> `validate_bind_host()`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/server.py
- `test_validate_bind_host_rejects_wildcard()` --calls--> `validate_bind_host()`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/server.py
- `test_assert_no_broker_keys_allows_llm_env()` --calls--> `assert_no_broker_keys()`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/server.py

## Import Cycles
- None detected.

## Communities (23 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (70): MonkeyPatch, Response, LLMProposal, Contractul JSON al procesului LLM — modele pure, zero I/O.  Fără câmp de mărime, Ieșirea validă a stratului LLM. extra=forbid: câmpuri necunoscute → invalid., Output invalid sau în afara universului — păstrat brut, niciodată reparat., RejectedProposal, assert_no_broker_keys() (+62 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (23): LLMProposalClient, Client, RejectedProposal, Client HTTP către procesul LLM — zero import din src.llm.  Deserializează JSON-u, ParsedProposal, ProposalContext, Tipuri de propunere pe partea engine/ — duplicat structural al llm.schema.  Defi, Deserializare locală a JSON-ului HTTP — identic structural cu LLMProposal. (+15 more)

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
Cohesion: 0.14
Nodes (26): BaseModel, Limite imutabile pe durata rulării. Extra fields interzise., RiskLimits, InstrumentRules, PortfolioState, Reguli de lot/notional pentru rotunjirea cantității. extra=forbid., Expunere și metrici de risc deja realizate — niciun câmp nu vine din LLM., _floor_to_lot() (+18 more)

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (28): _decimal_from_yaml(), Any, Decimal, Schema RiskLimits — validare hard la pornire, fără fallback silențios., YAML încarcă numere ca float; trecem prin str ca să nu pierdem precizie., load_instrument_rules(), _optional_positive_decimal(), Any (+20 more)

### Community 11 - "Community 11"
Cohesion: 0.17
Nodes (11): 1. Versiune instalată, 2. Exemplul oficial reprodus, 3. Rezultate obținute, 4. Inspecția `RiskEngine` (cod instalat, nu documentație), 5. Fișiere create pentru această calificare, 6. Checkpoint DoD (Task 1 / instrucțiuni §3), Ce validează concret `RiskEngine` la fiecare comandă (`SubmitOrder`/`SubmitOrderList`/`ModifyOrder`), Configurație (`RiskEngineConfig`) (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (24): _engine(), _proposal(), Path, RiskEngine.evaluate — fiecare limită din risk_limits.yaml, inclusiv cazuri la pr, _state(), test_avoid_is_no_action(), test_daily_loss_at_threshold_rejected(), test_daily_loss_over_threshold_rejected() (+16 more)

### Community 13 - "Community 13"
Cohesion: 0.29
Nodes (8): BacktestEngine, fetch_test_data(), Path, Descarcă datele istorice folosite de exemplul oficial NautilusTrader de backtest, Return the local path to the pinned test data, downloading it if absent/corrupt., _sha256(), Reproduce oficială — NautilusTrader "Backtest (Low-Level API)".  Sursă: docs/get, run()

### Community 21 - "Community 21"
Cohesion: 0.33
Nodes (15): load_risk_limits(), Path, Încarcă și validează config/risk_limits.yaml. Lipsă/invalid → ValueError, fără d, Path, Validare hard a config/risk_limits.yaml — fără fallback la valori implicite., test_empty_file_raises(), test_extra_field_is_rejected(), test_halt_on_unknown_false_raises() (+7 more)

## Knowledge Gaps
- **145 isolated node(s):** `trading-agent`, `0. Reguli absolute — citește ÎNAINTE de orice task`, `1. Structura recomandată a repository-ului`, `2. Task 0 — Configurare mediu local`, `3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil)` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LLMProposal` connect `Community 0` to `Community 9`, `Community 1`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `Research tehnic: proiecte open-source de AI agentic trading bots (GitHub/Hugging Face)` connect `Community 3` to `Community 5`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `RejectedProposal` connect `Community 0` to `Community 9`, `Community 1`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `KillSwitch` (e.g. with `CircuitBreaker` and `RiskDecision`) actually correct?**
  _`KillSwitch` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `trading-agent`, `Descarcă datele istorice folosite de exemplul oficial NautilusTrader de backtest`, `Return the local path to the pinned test data, downloading it if absent/corrupt.` to the rest of the system?**
  _203 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06736842105263158 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.125 - nodes in this community are weakly interconnected._