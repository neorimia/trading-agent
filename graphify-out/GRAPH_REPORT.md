# Graph Report - trading-agent  (2026-09-18)

## Corpus Check
- 29 files · ~34,321 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 320 nodes · 485 edges · 21 communities (18 shown, 3 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8210f481`
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

## God Nodes (most connected - your core abstractions)
1. `generate_proposal()` - 21 edges
2. `LLMProposal` - 20 edges
3. `Brief de proiect — Agent local de analiză și trading (multi-asset)` - 18 edges
4. `RejectedProposal` - 16 edges
5. `Research tehnic: proiecte open-source de AI agentic trading bots (GitHub/Hugging Face)` - 16 edges
6. `parse_proposal()` - 14 edges
7. `Agent local de analiză și trading: evaluare tehnică și plan de implementare` - 14 edges
8. `ProposalInput` - 13 edges
9. `Instrucțiuni pentru Claude Code — Agent local de trading, Faza 0–4` - 12 edges
10. `5. Analiza detaliată pe proiect` - 12 edges

## Surprising Connections (you probably didn't know these)
- `test_propose_rejects_out_of_universe()` --calls--> `LLMProposal`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/schema.py
- `test_propose_returns_proposal()` --calls--> `LLMProposal`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/schema.py
- `test_propose_forwards_rejected()` --calls--> `RejectedProposal`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/schema.py
- `test_validate_bind_host_accepts_loopback()` --calls--> `validate_bind_host()`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/server.py
- `test_validate_bind_host_rejects_wildcard()` --calls--> `validate_bind_host()`  [EXTRACTED]
  tests/unit/test_llm_server.py → src/llm/server.py

## Import Cycles
- None detected.

## Communities (21 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.10
Nodes (45): Any, LLMProposal, Contractul JSON al procesului LLM — modele pure, zero I/O.  Fără câmp de mărime, Ieșirea validă a stratului LLM. extra=forbid: câmpuri necunoscute → invalid., Output invalid sau în afara universului — păstrat brut, niciodată reparat., RejectedProposal, _load_dotenv_llm(), main() (+37 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (24): BaseModel, LLMProposalClient, Client, RejectedProposal, Client HTTP către procesul LLM — zero import din src.llm.  Deserializează JSON-u, ParsedProposal, ProposalContext, Tipuri de propunere pe partea engine/ — duplicat structural al llm.schema.  Defi (+16 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (32): 10. Fazele și planul 30/60/90 de zile, 11. Riscurile critice, în ordinea impactului, 12. Întrebări rămase înainte de implementare, 13. Registrul surselor verificate și decizia finală, 1. Rezumat executiv și limitele verificării, 2. Identitate, activitate, licențe și comunitate, 3. Comparația numerică, 4.10. Hugging Face: FinRobot Forecaster și FinGPT (+24 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (31): 10. Plan de implementare pe 30/60/90 de zile [OPINIE, orientativ], 11. Lista de riscuri critice, 12. Întrebări la care trebuie să răspunzi înainte de implementare, 13. Surse verificate, 14. Concluzie, 1. Rezumat executiv, 2. Tabel comparativ (scoruri 1–10), 3. Top 3 opțiuni (pentru scopul tău specific) (+23 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (29): 10. Ce nu acoperă acest document, 1. Principii de design derivate din regulile absolute, 2. Frontiere de proces, 3. Structură de directoare (extinde secțiunea 1 din instrucțiuni), 4.1 `LLMProposal` (ieșirea validă a stratului LLM), 4.2 `RejectedProposal`, 4.3 `RiskDecision` (ieșirea `risk_engine.evaluate`), 4.4 `OrderRequest` / `OrderResult` (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (18): 0. Graf de dependențe (nivel task), 1. Faza 0 — Configurare mediu local ✅ COMPLETĂ (2026-09-18, commit `cd823b3`), 2. Faza 1 — Instalare și calificare NautilusTrader (v1 stabil) ✅ COMPLETĂ (2026-09-18), 3. Faza 2 — Strat LLM local izolat (Qwen3-8B via Ollama) ✅ COMPLETĂ (2026-09-18), 4. Faza 3 — Reguli de risc deterministe, 5. Faza 4 — Backtesting realist, 6. Faza 5 — Paper trading, 7. Poartă continuă — verificare statică a izolării (CI, toate fazele ≥2) (+10 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (20): 10. Managementul riscului (obligatoriu, nu opțional), 11. Buget, 12. Roluri și responsabilități (RACI simplificat), 13. Riscuri majore și plan de mitigare, 14. Constrângeri legale și fiscale, 15. Dependențe și necunoscute deschise, 16. Glosar rapid, 17. Anexe recomandate (+12 more)

### Community 7 - "Community 7"
Cohesion: 0.23
Nodes (16): _collect_imported_modules(), _env_keys(), _forbidden_hits(), _iter_py_files(), _matches_prefix(), _module_name_for(), Path, Verificare statică a izolării engine ↔ llm (design §6).  Rulează la fiecare comm (+8 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (14): 0. Reguli absolute — citește ÎNAINTE de orice task, 10. Recapitulare — ce NU face Claude Code în această fază, 1. Structura recomandată a repository-ului, 2. Task 0 — Configurare mediu local, 3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil), 4. Task 2 — Strat LLM local izolat (Qwen3-8B via Ollama), 5. Task 3 — Reguli de risc deterministe (sursa unică de adevăr), 6. Task 4 — Backtesting realist (+6 more)

### Community 9 - "Community 9"
Cohesion: 0.24
Nodes (13): MonkeyPatch, assert_no_broker_keys(), Refuză pornirea dacă procesul vede cheile de broker din .env.engine., validate_bind_host(), _payload(), Server LLM: loopback only, POST /propose orchestrează generate + universe., test_assert_no_broker_keys_allows_llm_env(), test_assert_no_broker_keys_rejects_engine_vars() (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.29
Nodes (12): Response, _client_for(), _config(), _ollama_reachable(), _ollama_response(), Client, Teste adversariale de conținut: input injectat nu poate declanșa execuție/risc., _sample_context() (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.17
Nodes (11): 1. Versiune instalată, 2. Exemplul oficial reprodus, 3. Rezultate obținute, 4. Inspecția `RiskEngine` (cod instalat, nu documentație), 5. Fișiere create pentru această calificare, 6. Checkpoint DoD (Task 1 / instrucțiuni §3), Ce validează concret `RiskEngine` la fiecare comandă (`SubmitOrder`/`SubmitOrderList`/`ModifyOrder`), Configurație (`RiskEngineConfig`) (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.17
Nodes (12): 5.10 virattt/ai-hedge-fund, 5.11 Ce am găsit pe Hugging Face, 5.1 fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis, 5.2 FriesTrader, 5.3 Topicul GitHub `quant-trading-bot`, 5.4 Krexibd/quant-trading, 5.5 kweinmeister/agentic-trading (Google), 5.6 HKUDS/AI-Trader (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.29
Nodes (8): BacktestEngine, fetch_test_data(), Path, Descarcă datele istorice folosite de exemplul oficial NautilusTrader de backtest, Return the local path to the pinned test data, downloading it if absent/corrupt., _sha256(), Reproduce oficială — NautilusTrader "Backtest (Low-Level API)".  Sursă: docs/get, run()

## Knowledge Gaps
- **145 isolated node(s):** `trading-agent`, `0. Reguli absolute — citește ÎNAINTE de orice task`, `1. Structura recomandată a repository-ului`, `2. Task 0 — Configurare mediu local`, `3. Task 1 — Instalare și calificare NautilusTrader (v1 stabil)` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Research tehnic: proiecte open-source de AI agentic trading bots (GitHub/Hugging Face)` connect `Community 3` to `Community 12`, `Community 5`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Why does `Agent local de analiză și trading: evaluare tehnică și plan de implementare` connect `Community 2` to `Community 5`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `Design de componente — Agent local de trading, Faza 0–4` connect `Community 4` to `Community 5`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `LLMProposal` (e.g. with `ProposeRequest` and `ModelConfig`) actually correct?**
  _`LLMProposal` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `RejectedProposal` (e.g. with `ProposeRequest` and `ModelConfig`) actually correct?**
  _`RejectedProposal` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `trading-agent`, `Descarcă datele istorice folosite de exemplul oficial NautilusTrader de backtest`, `Return the local path to the pinned test data, downloading it if absent/corrupt.` to the rest of the system?**
  _177 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.10204081632653061 - nodes in this community are weakly interconnected._