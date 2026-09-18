# Workflow de implementare — Agent local de trading, Faza 0–4

**Sursă:** [`CLAUDE-instructiuni-faza-0-4.md`](../CLAUDE-instructiuni-faza-0-4.md) (task-uri + reguli absolute) și [`design-componente-faza-0-4.md`](../design-componente-faza-0-4.md) (module, interfețe, contracte de date).

**Statutul acestui document:** plan de implementare. **Nu conține și nu execută cod.** Pasul următor, per task, este `/sc:implement`.

**Notă critică de ordine:** deși design-ul numerotează secțiunile 1–10, task-urile din instrucțiuni au propria lor dependență (secțiunea 8 a instrucțiunilor). Acest workflow urmează graful de dependențe al task-urilor, nu ordinea secțiunilor din design.

---

## 0. Graf de dependențe (nivel task)

```
Faza 0 (mediu)
   └──> Faza 1 (NautilusTrader) ──┬──> Faza 3 (risc determinist)
                                    │         │
        Faza 2 (LLM izolat) ──────┘         ▼
                                     Faza 4 (backtesting realist)
                                              │
                                              ▼
                                     Faza 5 (paper trading)
```

- Faza 2 poate începe **în paralel** cu Faza 1 (ambele depind doar de Faza 0), dar rezultatul ei **nu se integrează** cu Faza 3/4 până când testele adversariale din Faza 3 nu trec.
- Faza 5 are un **punct de decizie umană obligatoriu** înainte de start (Cale A vs. Cale B, secțiunea 5 mai jos).
- Testul de izolare statică (`tests/adversarial/test_process_isolation.py`, design §6) e livrabil în Faza 2, dar rulează în CI la *fiecare* commit ulterior, inclusiv în Fazele 3–5 — e o poartă continuă, nu un checkpoint unic.

---

## 1. Faza 0 — Configurare mediu local ✅ COMPLETĂ (2026-09-18, commit `cd823b3`)

**Corespunde:** Task 0 (instrucțiuni §2).

**Dependențe:** niciuna — punct de start.

**Livrabile:**
- `.env.example`, `.env.engine.example`, `.env.llm.example` (design §3 — separate explicit, `.env.llm.example` fără nicio cheie de broker)
- `.gitignore` (exclude `.env*` reale, `venv/`, `runtime/` complet)
- `pyproject.toml`/`requirements.txt` cu versiuni fixate (`==`)
- Pre-commit hook cu scanner de secrete (gitleaks sau echivalent)
- `README.md` cu instrucțiuni de instalare verificate pe o clonă curată
- Structura de directoare completă din design §3 (foldere goale unde e cazul: `config/`, `src/{data,engine,risk,llm,execution,monitor,audit}/`, `runtime/`, `backtests/reports/`, `tests/{unit,integration,fixtures,adversarial}/`, `docs/`)

**Pași de execuție:**
1. Creează venv/conda dedicat, Python 3.12+.
2. Creează structura de directoare din design §3.
3. Scrie cele trei fișiere `.env*.example` — verifică manual că `.env.llm.example` nu conține niciun string ce matchează `BROKER`/`API_KEY`/`SECRET`.
4. Configurează `.gitignore` (include explicit `runtime/` — design §3 subliniază că starea locală nu ajunge niciodată în git).
5. Instalează și configurează scanner de secrete ca pre-commit hook.
6. Fixează dependențele cu versiuni exacte; verifică suport ARM64 nativ pentru fiecare pachet critic (NautilusTrader în special) — documentează explicit orice fallback prin Rosetta.
7. Scrie `README.md`, apoi validează pe o clonă curată a repo-ului.

**Checkpoint de validare (DoD Task 0):**
- [x] Instalare de la zero pe clonă curată reușește doar din `README.md`. Verificat de două ori prin simulare de clonă curată (`uv sync --group dev` → `pre-commit install` → copiere `.env*.example` → `import nautilus_trader` → `pytest --collect-only`), toate pașii au reușit.
- [x] `git log` curat (verificat cu scanner-ul). `gitleaks detect --source . -v` pe tot istoricul → `no leaks found`. Hook-ul de pre-commit a fost testat live: un fals `AWS_SECRET_ACCESS_KEY` a fost blocat (exit code 1); un commit curat trece.
- [x] Toate dependențele fixate. `pyproject.toml`/`uv.lock`/`requirements.txt`/`requirements-dev.txt`, toate cu `==` (inclusiv `nautilus_trader==1.231.0`).
- [x] Zero pachete rulate prin emulare x86 fără notă explicită. Verificat cu `lipo -info` pe fiecare `.so` compilat din `nautilus_trader`, `pydantic-core`, `numpy`, `pandas`, `pyarrow`, `msgspec` → 100% `arm64` nativ. Singura excepție e `uvloop`, care livrează un wheel universal2 (conține și slice arm64) — documentată explicit în README ca „nu e fallback Rosetta”.

**Livrabile efective:** `.env.example`, `.env.engine.example` (verificat manual — zero string `BROKER`/`API_KEY`/`SECRET`), `.gitignore` actualizat, `pyproject.toml` + `uv.lock` + `requirements*.txt`, `.pre-commit-config.yaml` (hook local `gitleaks protect --staged`, instalat și testat), `README.md` cu secțiune de instalare verificată, structura completă de directoare din design §3 (foldere goale marcate cu `.gitkeep`). Commit: `cd823b3` — "Faza 0: configurare mediu local (venv, structura repo, secrete, deps fixate)".

---

## 2. Faza 1 — Instalare și calificare NautilusTrader (v1 stabil) ✅ COMPLETĂ (2026-09-18)

**Corespunde:** Task 1 (instrucțiuni §3).

**Dependențe:** Faza 0 completă.

**Livrabile:**
- NautilusTrader v1.231.0 instalat (pinned, **nu** v2 RC — regulă absolută #8)
- `docs/qualification-report.md`
- `src/engine/adapters/` — scaffold inițial (fără logică de business încă)

**Pași de execuție:**
1. Instalează NautilusTrader v1.231.0 exact (nu `develop`).
2. Verifică import + versiune printr-un script minimal.
3. Rulează un exemplu **oficial** de backtest (din docs/repo NautilusTrader), pe date istorice locale, zero conexiune broker.
4. Compară output cu documentația oficială (ordin de mărime, nu cifre exacte); dacă diverge, documentează — nu ajusta perioada ca să „repari" rezultatul.
5. Inspectează efectiv codul `RiskEngine` din pachetul instalat (nu presupune din README) — notează ce validează concret.
6. Scrie `docs/qualification-report.md`: versiune exactă, hash commit/wheel, exemplul reprodus, rezultate, discrepanțe.

**Checkpoint de validare (DoD Task 1):**
- [x] Exemplul oficial rulează integral, fără modificări majore. Reprodus `docs/getting_started/backtest_low_level.py` (commit `27a8e54e`, tag `v1.231.0`) — EMA cross + execuție TWAP pe Binance Spot simulat, 69.807 trade ticks ETHUSDT. Unica modificare: sursa datelor (`CSVTickDataLoader` pe fixture local pinned prin hash, în loc de `TestDataProvider` care ar fi tras din branch-ul mobil `develop`) — documentată explicit în raport, logica de backtest neschimbată.
- [x] Raport de calificare există, cu rezultate reproductibile (rulare repetată → același output). `docs/qualification-report.md`. Rulat de două ori consecutiv; după normalizarea câmpurilor nedeterministe prin design (UUID-uri de runtime, timestamp-uri wall-clock, telemetrie de sistem), toate valorile de simulare (prețuri, cantități, comisioane, solduri, timestamp-uri de eveniment simulat, cele 3 rapoarte finale) sunt identice bit-cu-bit între rulări.
- [x] Zero conexiune de rețea către broker real. Venue `BINANCE` e `SimulatedVenue` intern al `BacktestEngine`; singura rețea folosită e descărcarea unică (cache-uită, verificată sha256) a fișierului CSV istoric static.

**Livrabile efective:** NautilusTrader `1.231.0` instalat (wheel `cp312-cp312-macosx_26_0_arm64`, nativ ARM64, hash verificat de `uv.lock`), `docs/qualification-report.md` (include inspecția codului sursă `RiskEngine` — `nautilus_trader/risk/engine.pyx` — ce validează concret: preț, cantitate, notional per ordin/instrument, sold disponibil, stare HALTED/REDUCING, rate limiting; și ce NU acoperă, relevant pentru Faza 3: pierdere zilnică/drawdown, kill switch de business), `src/engine/adapters/__init__.py` (scaffold, fără logică de business), `scripts/nautilus_qualification/` (fetch + reproducere, reutilizabile pentru re-calificare la upgrade de versiune), `backtests/reports/nautilus_qualification/run_1.log` + `run_2.log` (log-urile complete ale celor două rulări de reproductibilitate, locale — gitignored ca orice raport de backtest generat).

---

## 3. Faza 2 — Strat LLM local izolat (Qwen3-8B via Ollama) ✅ COMPLETĂ (2026-09-18)

**Corespunde:** Task 2 (instrucțiuni §4) + design §7 (izolare totală engine↔llm).

**Dependențe:** Faza 0 completă. **Poate rula în paralel cu Faza 1** (nu depinde de NautilusTrader).

**Livrabile:**
- `src/llm/schema.py` — `LLMProposal`, `RejectedProposal` (pure data, zero I/O)
- `src/llm/service.py` — generare + validare schema + allowlist univers
- `src/llm/server.py` — HTTP loopback `127.0.0.1`, singurul punct de intrare extern al procesului
- `src/engine/llm_client.py` — client HTTP, **zero import din `llm/`**
- `src/engine/proposal_types.py` — `ParsedProposal`, duplicat structural, definit independent
- `config/universe.yaml`
- `tests/adversarial/test_process_isolation.py` (design §6 — verificare AST statică)
- `tests/integration/test_proposal_contract.py` + `tests/fixtures/llm_proposals.json` (design §7 — sincronizare schema `llm.schema` ↔ `engine.proposal_types`)

**Pași de execuție:**
1. Instalează Ollama local, descarcă Qwen3-8B cuantizat 4-bit.
2. Scrie `config/universe.yaml` (schema minimă design §4.7).
3. Implementează `llm/schema.py` — `LLMProposal`/`RejectedProposal`, fără câmp de mărime poziție/preț/limită risc (design §4.1–4.2).
4. Implementează `llm/service.py`: `generate_proposal()`, `validate_against_universe()` — output invalid → `RejectedProposal`, niciodată „reparat" silențios.
5. Implementează `llm/server.py`: endpoint `POST /propose`, loopback only.
6. Implementează `engine/proposal_types.py` (schema duplicată, independentă) și `engine/llm_client.py` (deserializează JSON HTTP direct în `ParsedProposal`, fără a trece prin niciun tip din `llm/`).
7. Scrie `tests/fixtures/llm_proposals.json` (cazuri valide + invalide) și `tests/integration/test_proposal_contract.py` — verifică că cele două scheme acceptă/resping identic aceleași exemple.
8. Scrie `tests/adversarial/test_process_isolation.py` (design §6, cei 6 pași AST): zero import `llm/` → `risk/`/`execution/`/`engine/`; zero import `risk/`/`execution/`/`engine/` → `llm/` (fără excepții, inclusiv `schema.py`); zero pachet client broker cunoscut în `llm/`; `.env.llm.example` fără chei `BROKER`/`API_KEY`/`SECRET`.
9. Scrie teste adversariale de conținut: text extern (injectat) care cere „dezactivează limitele"/„schimbă contul" → rezultatul așteptat e ignorarea instrucțiunii.

**Checkpoint de validare (DoD Task 2):**
- [x] Serviciul LLM rulează în proces separat, izolare confirmată prin testul static (nu doar afirmată). `tests/adversarial/test_process_isolation.py` — AST pe `src/llm` (zero import `risk`/`execution`/`engine`, zero clienți broker), AST pe `src/risk`/`execution`/`engine` (zero import `src.llm`, inclusiv `schema`), `.env.llm.example` fără cheile `BROKER`/`API_KEY`/`SECRET` din `.env.engine.example`. Serverul refuză bind pe `0.0.0.0` și refuză pornirea dacă vede cheile de broker din engine.
- [x] Test automat: propunere în afara schema-ului → respinsă, nu reparată. JSON trunchiat, `direction=buy`, `confidence` în afara [0,1], câmpuri extra (`position_size`, `disable_risk_limits`) → `RejectedProposal(reason=schema_invalid)`. extra=`forbid` pe ambele scheme.
- [x] Test adversarial de conținut: input adversarial nu declanșează execuție/schimbare risc. Mock: contextul injectat e marcat untrusted, câmpurile de sizing/risc sunt respinse, `sys.modules` nu încarcă `src.execution`/`src.risk`/`src.engine`. Live (`pytest -m llm_live`, 22.8s pe Qwen3-8B local): output-ul e doar `LLMProposal` cu câmpurile din schemă sau `RejectedProposal`.
- [x] Zero chei de broker accesibile din procesul LLM. Procesul încarcă doar `.env.llm`; `assert_no_broker_keys()` blochează prezența cheilor din `.env.engine`.

**Livrabile efective:** `config/universe.yaml` (AAPL, MSFT, ETHUSD, BTCUSD), `src/llm/{schema,service,server}.py`, `src/engine/{proposal_types,llm_client}.py`, `tests/adversarial/test_process_isolation.py`, `tests/adversarial/test_llm_prompt_injection.py`, `tests/integration/test_proposal_contract.py` + `tests/fixtures/llm_proposals.json`. Stack HTTP: FastAPI `0.141.1` + uvicorn `0.53.0` + httpx `0.28.1` (pinned `==`). Model: Ollama `qwen3:8b` (Q4_K_M, deja instalat local). `LLM_MODEL_NAME` din `.env.llm.example` corectat la tag-ul real `qwen3:8b`.

**Poartă de integrare (nu e parte din DoD Task 2, dar blochează Faza 3/4):** rezultatele Fazei 2 nu se conectează la `risk/`/`engine/`-ul „productiv" până când testele adversariale din **Faza 3** nu trec.

---

## 4. Faza 3 — Reguli de risc deterministe ✅ COMPLETĂ (2026-09-18)

**Corespunde:** Task 3 (instrucțiuni §5).

**Dependențe:** Faza 1 completă (integrare NautilusTrader) **și** Faza 2 completă (pentru testele adversariale care simulează propuneri LLM) — punctul de sincronizare al graniței de izolare.

**Livrabile:**
- `config/risk_limits.yaml` (schema design §4.6)
- `src/risk/config_schema.py` — `RiskLimits` (pydantic), validare hard la pornire
- `src/risk/position_sizing.py` — funcție pură de dimensionare
- `src/risk/risk_engine.py` — `evaluate(proposal: ParsedProposal, portfolio_state) -> RiskDecision`
- `src/risk/kill_switch.py`, `src/risk/circuit_breaker.py`
- `tests/unit/` (acoperire per limită) + `tests/adversarial/` (bypass prin output LLM)

**Pași de execuție:**
1. Scrie `config/risk_limits.yaml` cu toate câmpurile minime (design §4.6): notional max/ordin, expunere max per instrument/clasă, pierdere zilnică max, drawdown max, ordine/zi max, config circuit breaker (`halt_on_unknown_order_result: true` obligatoriu).
2. Implementează `load_risk_limits()` — validare schema + valori sane la pornire; aplicația refuză pornirea dacă lipsă/invalid (fără fallback silențios).
3. Implementează `size_position()` ca funcție pură (formula exactă din instrucțiuni §5.3), testabilă izolat.
4. Implementează `RiskEngine.evaluate()` — primește **`ParsedProposal`** (tipul din `engine/`, niciodată din `llm/` — design §7), verifică flag-ul HALT (`runtime/control/halt.flag`) la fiecare apel.
5. Implementează `KillSwitch.trigger()` — funcție/serviciu independent, apelabil manual, testabil separat de restul aplicației.
6. Implementează `CircuitBreaker` — stare `RUNNING`/`HALTED`, tranziție la N erori/pierderi consecutive sau rezultat necunoscut.
7. Scrie suite `tests/unit/` — acoperă fiecare limită din `risk_limits.yaml`, inclusiv cazuri limită (exact la prag, peste, sub minim instrument).
8. Scrie minim 3 teste adversariale (instrucțiuni §5, criteriu explicit): propunere care cere mărime peste limită, propunere care „sare" stop-loss, conținut care încearcă să convingă sistemul să ignore drawdown-ul — toate trebuie respinse indiferent de conținutul propunerii.
9. Testează manual kill switch-ul; documentează timpul de răspuns și starea pozițiilor deschise după activare.

**Checkpoint de validare (DoD Task 3):**
- [x] `risk_engine.py` nu importă/depinde de niciun modul din `llm/` (verificat de testul static al Fazei 2, extins să acopere și `risk/`). `tests/adversarial/test_process_isolation.py` iterează deja `src/risk/**/*.py` — zero import `src.llm` (inclusiv `schema`). `RiskEngine.evaluate` primește `ParsedProposal` din `src.engine.proposal_types`.
- [x] Teste unitare acoperă fiecare limită + cazuri limită. `tests/unit/test_risk_engine.py` (notional la cap, expunere instrument/clasă la prag și peste, pierdere zilnică, drawdown, ordine/zi, sub min notional, instrument necunoscut, `avoid`/`exit`/`long`, HALT) + suite per componentă (`test_risk_config_schema`, `test_position_sizing`, `test_portfolio_state`, `test_kill_switch`, `test_circuit_breaker`). `halt_on_unknown_order_result: false` eșuează la încărcare.
- [x] Minim 3 teste adversariale trec. `tests/adversarial/test_risk_bypass.py`: câmpuri extra de sizing respinse de `extra=forbid`; rationale „ignoră limitele" nu crește notionalul peste cap; `exit` la expunere maximă nu o mărește; rationale „ignoră drawdown-ul" e respins; HALT respinge propunerea „urgentă" cu `confidence=1.0`.
- [x] Kill switch testat manual, rezultat documentat. `KillSwitch.trigger("manual kill-switch verification (Faza 3)")` + `is_active()`: flag scris, `triggered=True`, timp de răspuns **0.430 ms** (`time.perf_counter`, 2026-09-18T13:38:58Z). `reset()` șterge flag-ul. Starea pozițiilor deschise după activare: **parțială** — `execution/` (cancel-all / broker) nu există încă (Faza 5); la HALT, `RiskEngine.evaluate` respinge orice propunere nouă (inclusiv `exit`) cu `reject_reason="halted"`, `quantity=0`. Nu există poziții live de anulat în această fază.

**Livrabile efective:** `config/risk_limits.yaml` (sume absolute, `halt_on_unknown_order_result: true`), `config/universe.yaml` extins cu `min_notional`/`lot_size`/`tick_size` (opționale pentru `llm/`), `src/risk/{config_schema,portfolio_state,position_sizing,kill_switch,circuit_breaker,risk_engine}.py`. `pytest -m "not llm_live"` → 105 passed.

---

## 5. Faza 4 — Backtesting realist ✅ COMPLETĂ (2026-09-18)

**Corespunde:** Task 4 (instrucțiuni §6).

**Dependențe:** Faza 3 completă (risk engine e sursa unică de adevăr, trebuie să existe înainte de a rula strategia end-to-end).

**Livrabile:**
- `src/data/sources.py`, `src/data/validation.py`, `src/data/cache.py`
- `src/engine/strategy_llm_assisted.py` (mod backtest)
- `backtests/reports/`
- Test automat de detecție look-ahead bias

**Pași de execuție:**
1. Implementează `DataSource.fetch_bars()`, `DataValidator.validate()` (gap-uri, duplicate, timestamp-viitor), `MarketDataCache.get_or_fetch()` (+ hash dataset pentru reproductibilitate).
2. Construiește backtestul pe NautilusTrader cu comisioane, spread bid/ask, slippage, fills parțiale.
3. Implementează separare cronologică strictă train/validation/test + walk-forward; păstrează holdout final neatins.
4. Scrie test automat de look-ahead bias (referință metodologică: Freqtrade lookahead analysis, fără dependență de cod).
5. Rulează fiecare backtest la costuri normale, 2× și 3× — documentează dacă avantajul dispare.
6. Construiește baseline determinist fără LLM; compară strategia cu LLM față de baseline, pe aceleași date/costuri.
7. Arhivează per rulare: inputuri exacte, seed-uri, hash date, output complet.

**Checkpoint de validare (DoD Task 4):**
- [x] Backtestul include comisioane + slippage (nu doar preț mid). `MakerTakerFeeModel` (10 bps taker, scalat 1×/2×/3×) + quote bid/ask (10 bps spread) + `PartialSlippageFillModel` (1–3 tick-uri + 40% top-of-book). Holdout baseline: 2 fill-uri, comisioane 1.97678512 / 3.95357023 / 5.93035536 USDT.
- [x] Test automat de look-ahead bias există și ar eșua dacă bias-ul ar fi introdus. `tests/adversarial/test_lookahead_bias.py` — EMA și `ProposalContext` la T identice pe seria trunchiată vs. seria cu barele viitoare corupte.
- [x] Raport arată explicit rezultate la 1×/2×/3× costuri. `docs/backtest-report.md` + `backtests/reports/faza4-ethusd-1d-202411-202412/holdout_comparison.json`.
- [x] Comparație documentată LLM vs. baseline determinist. Holdout 2024-12-19…31: baseline EMA-cross round-trip pierzător; Qwen3-8B a propus `avoid` pe toate cele 13 zile (capital 10.000 neschimbat la toate multiplicatoarele).
- [x] Rulare repetată → rezultate identice. `tests/integration/test_backtest_reproducibility.py`; re-rulare documentată cu același `dataset_hash` `c9ddad6021ec43d59e37a79db4a5b341b01d7e8f9fa290b3e378c157b68ba7c7` și cache de propuneri → aceleași metrici.

**Livrabile efective:** `src/data/{sources,validation,cache}.py` (Binance public klines + CSV fixture; `venue: KRAKEN` rămâne ruta de execuție, nu vendor-ul de istoric), `src/engine/{signals,splits,cost_models,instruments,portfolio_tracker,proposal_cache,strategy_baseline,strategy_llm_assisted,backtest_runner}.py`, `scripts/backtest/run_backtest.py`, `tests/adversarial/test_lookahead_bias.py`, `tests/integration/test_backtest_reproducibility.py`, `docs/backtest-report.md`. Run: `faza4-ethusd-1d-202411-202412` (61 bare ETHUSDT 1d, 2024-11-01…12-31). `pytest -m "not llm_live and not network_live"` → 138 passed.

---

## 6. Faza 5 — Paper trading ✅ COD + 30 SESIUNI (2026-09-18); revizuire PO/Risk owner deschisă

**Corespunde:** Task 5 (instrucțiuni §7).

**Dependențe:** Faza 4 completă.

**Decizii umane (2026-09-18):** Cale B (crypto / Kraken, `dry_run: true`). `monitor/` flag-only — fără client de broker separat; HALT prin `runtime/control/halt.flag`.

**Livrabile efective:** `src/audit/{events,audit_log}.py`, `src/execution/{types,broker,idempotency_store,order_gateway,human_approval,reconciliation}.py`, `src/monitor/{heartbeat,watchdog}.py`, `src/engine/{paper_config,strategy_paper}.py`, `src/engine/adapters/kraken_paper.py`, `src/data/kraken.py`, `config/paper_trading.yaml`, `scripts/paper_trading/run_paper_session.py`, `docs/paper-trading-report.md`. Spike Kraken public OHLC: HTTP 200, zero chei.

**Checkpoint de validare (DoD Task 5):**
- [x] Minim 30 sesiuni paper, fără incident critic nereportat. Run `20260918T143445Z`, 30 sesiuni ETHUSD pe OHLC public Kraken, `halted=false`.
- [x] Zero chei live folosite. `assert_no_kraken_trading_keys`; `KrakenDataClientConfig(api_key=None)`; execuție `SimulatedBroker` / sandbox.
- [x] Reconciliere completă demonstrată după minim un restart simulat. Broker snapshot restaurat pe instanță nouă; `restart_reconciled=true`.
- [ ] Raport final revizuit de PO/Risk owner **înainte** de orice discuție despre Faza 5+ (live). `docs/paper-trading-report.md` scris, așteaptă revizuire.

---

## 7. Poartă continuă — verificare statică a izolării (CI, toate fazele ≥2)

Nu e o fază separată, ci o regulă care rulează la fiecare commit din Faza 2 înainte:

```
tests/adversarial/test_process_isolation.py (design §6):
  1. AST-scan src/llm/**/*.py — zero import din src.risk/src.execution/src.engine, zero pachet client broker cunoscut
  2. AST-scan src/risk/**/*.py, src/execution/**/*.py, src/engine/**/*.py — ZERO import din src.llm (inclusiv src.llm.schema, fără excepții)
  3. .env.llm.example — zero chei BROKER/API_KEY/SECRET prezente în .env.engine.example
```

Sincronizarea `llm.schema` ↔ `engine.proposal_types` se verifică separat prin `tests/integration/test_proposal_contract.py` (Faza 2), nu prin acest test.

---

## 8. Checklist global — Definition of Done Faza 0–4 (per instrucțiuni §9)

- [ ] Toate DoD-urile individuale (Faza 0–5) bifate.
- [ ] Zero chei/credențiale live în cod, config sau istoric git.
- [x] Toate limitele de risc în config validat, niciodată în prompt/cod LLM. `config/risk_limits.yaml` + `load_risk_limits()` (Faza 3); `ParsedProposal` nu are câmpuri de sizing/risc.
- [ ] Suite unit + adversarial rulează în CI la fiecare commit relevant.
- [ ] Rapoartele de calificare NautilusTrader, backtest și paper trading există, revizuite de PO/Risk owner.
- [x] Kill switch testat manual, rezultat documentat. Vezi DoD Task 3 (0.430 ms, HALT respinge propuneri noi; cancel-all așteaptă Faza 5).
- [ ] Zero cod care presupune/pregătește silențios trecerea la live.

---

## 9. Ce nu acoperă acest workflow

- Alegerea mecanismului concret de transport HTTP pentru `llm/server.py` — decizie de implementare (Faza 2).
- Schema exactă SQLite pentru `audit/`/`idempotency_store` — DDL la implementare (Faza 5), pe baza contractelor design §4.
- Cod. Pasul următor este `/sc:implement` pe Faza 5 (paper trading), după punctul de decizie umană Cale A vs. Cale B.
