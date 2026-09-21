# Analiza strategiilor — `/strategies`

**Data auditului:** 2026-09-21. **Autor:** agent Cursor, sesiune „Strategies page overhaul”.
**Domeniu:** [config/strategies.yaml](../config/strategies.yaml), [src/engine/](../src/engine/), [src/risk/](../src/risk/), [apps/console/src/app/features/strategies.page.ts](../apps/console/src/app/features/strategies.page.ts).

Acest document separă strategiile **reale** (cod care rulează prin `RiskEngine` în backtest/paper) de orice ar putea părea placeholder. Nu există placeholder-e ascunse în UI-ul curent — pagina `/strategies` afișează exact cele două strategii din `config/strategies.yaml`, dar interfața nu arăta suficient despre ele. Acest document + implementarea din acest commit rezolvă asta.

---

## 0. Snapshot al stării dinaintea modificărilor

Capturat live la `http://127.0.0.1:4200/strategies`, mod `PAPER`, agent rulând, `Exchange data is down. New orders are blocked.`

| Strategie (UI) | Kind | Enabled | Params | Paper sessions | Backtest ref |
|---|---|---|---|---|---|
| Baseline EMA cross | `ema_cross` | active | `fast_ema_period=10 slow_ema_period=20` | 0 | `-` |
| LLM-assisted (proposal only) | `llm` | active | `{}` | 0 | `-` |

Pagina avea doar: tabel, tag enabled/disabled, buton Enable/Disable cu `ConfirmDanger`. Fără detalii, fără grafice, fără comparație, fără versiuni, fără buton de backtest.

Rezultate de backtest existente înainte de acest commit: [docs/backtest-report.md](backtest-report.md) (holdout de 13 zile, `ETHUSD` `1d`, 2024-12-19→31). Acestea rămân valabile ca istoric; rulările noi (secțiunea 7) sunt separate și explicit datate.

---

## 1. Auditul strategiilor existente

### 1.1 Baseline EMA cross — **reală**, cod în [src/engine/strategy_baseline.py](../src/engine/strategy_baseline.py) + [src/engine/signals.py](../src/engine/signals.py)

| Câmp | Valoare |
|---|---|
| Scop | Trend following long-only pe un singur activ |
| Ipoteză de piață | Pe crypto major (ETH/BTC), un trend susținut de EMA persistă suficient cât un long-only cu costurile Kraken curente să nu fie doar zgomot |
| Active suportate | `ETHUSD`, `BTCUSD` (univers Kraken); paper rulează pe `ETHUSD` `1h` ([config/paper_trading.yaml](../config/paper_trading.yaml)); backtestul documentat e pe `1d` |
| Indicatori | EMA(10), EMA(20) — `src/engine/signals.py::ema` |
| Intrare | Stare continuă: `fast_ema ≥ slow_ema` → `long` (nu semnal pe eveniment de cross, ci pe fiecare bară cât timp condiția e adevărată) |
| Ieșire | `fast_ema < slow_ema` → `exit` |
| Stop-loss | 2% hardcodat **în `RiskEngine`** (`_DEFAULT_STOP_FRACTION`), nu e proprietatea strategiei — orice strategie „long” primește același stop intern |
| Take-profit | Absent |
| Trailing stop | Absent |
| Position sizing | Exclusiv `RiskEngine.size_position` — strategia nu calculează cantitate |
| Max exposure | Limitele globale din `risk_limits.yaml` (nicio limită locală) |
| Cooldown | Absent — poate re-intra imediat după un exit dacă EMA revine peste |
| Max poziții simultane | Structural ≤ 1 (un singur instrument per proces de engine) |
| Filtre volatilitate/lichiditate | Absente |
| Comisioane | Da — `MakerTakerFeeModel` Nautilus, taxe reale Kraken (16bps maker / 26bps taker) |
| Slippage | Da — `PartialSlippageFillModel`, determinist, seed 42 |
| Confidence | Hardcodat `1.0` — nu reflectă tăria semnalului |
| Motivul semnalului | String generic `"ema_cross fast=10 slow=20"` |
| Condiții de invalidare | Absente ca și concept explicit |
| Versiune | Absentă (nu exista concept de versiune înainte de acest commit) |

**Metrici istorice** (din [docs/backtest-report.md](backtest-report.md), holdout 13 zile, capital inițial 10.000 USDT):

| Cost | Ending USDT | Fills | Comisioane |
|---|---|---|---|
| 1× | 9975.17 | 2 | 1.98 |
| 2× | 9973.19 | 2 | 3.95 |
| 3× | 9971.21 | 2 | 5.93 |

**Nu existau, înainte de acest commit:** win rate, profit factor, expectancy, Sharpe/Sortino/Calmar, max drawdown, recovery factor, turnover, performanță pe regim de piață, comparație cu buy-and-hold. Eșantionul (13 zile, 2 fill-uri) e mult prea mic pentru orice concluzie statistică.

**Risc de overfitting:** parametrii 10/20 sunt specificația inițială a proiectului (Faza 0-4), nu rezultatul unui grid-search — verificat direct în [claudedocs/CLAUDE-instructiuni-faza-0-4.md](../claudedocs/CLAUDE-instructiuni-faza-0-4.md). Nu sunt „optimizați", dar nici nu au fost testați pe intervale/active multiple înainte de acest commit. Eșantion unic (o fereastră de 2 luni, un singur activ) → risc ridicat ca rezultatul holdout-ului (o pierdere mică pe 2 tranzacții) să nu fie reprezentativ.

**Lipsuri de implementare identificate:**
1. Semnal de stare, nu de eveniment (re-emite `long` pe fiecare bară cât timp condiția ține).
2. Fără cooldown, fără invalidare explicită, fără versiune.
3. Stop-loss e un detaliu intern al `RiskEngine`, nu al strategiei — nu poate fi ajustat per-strategie fără a schimba comportamentul global.
4. Fără filtru de trend/regim — tranzacționează la fel în trend puternic sau piață laterală, deși ipoteza presupune trend.

### 1.2 LLM-assisted (proposal only) — **reală, dar experimentală**, cod în [src/engine/strategy_llm_assisted.py](../src/engine/strategy_llm_assisted.py)

| Câmp | Valoare |
|---|---|
| Scop | Propunere `long`/`avoid`/`exit` generată de un LLM local (Qwen3-8B via Ollama), pe baza unui rezumat tehnic determinist |
| Active/TF | Aceleași ca EMA (univers comun) |
| Intrare/ieșire | Determinate de textul generat de model, validat strict prin schema `ParsedProposal` (`extra=forbid`) |
| Stop-loss/TP | Aceleași reguli interne ca EMA (RiskEngine) |
| Position sizing | Exclusiv `RiskEngine` |
| Confidence | Vine din modelul LLM (`ParsedProposal.confidence`), dar temperature=0 + cache → determinist per input, nu o probabilitate calibrată |
| Rezultat holdout (13 zile) | `avoid` pe toate cele 13 zile → 0 fill-uri, capital neschimbat la toate multiplicatoarele de cost |

**Nu e alpha demonstrat.** Evitarea round-trip-ului pierzător al EMA-cross pe acest eșantion scurt poate fi coincidență (un LLM care nu tranzacționează nu poate „pierde”, dar nici nu a demonstrat că poate câștiga). Marcat `experimental` — rămâne așa până nu bate baseline-ul pe un eșantion out-of-sample mai lung, cu costuri 1×/2×/3×.

**Risc specific:** nedeterminism de model (parțial atenuat prin temperature 0 + cache pe `sha256(ProposalContext)`), dependență de disponibilitatea Ollama, imposibilitatea de a face sensitivity analysis clasică pe „parametri” (promptul nu e un parametru numeric).

---

## 2. Probleme identificate în arhitectură (înainte de acest commit)

1. **Nicio interfață comună de strategie** — `backtest_runner.py` avea `if strategy_kind == "baseline": ... else: ...`, ceea ce ar fi dus la o ramură nouă per strategie viitoare.
2. **Strategia Nautilus semnalizează ȘI trimite ordinul.** `BaselineEMACross.on_bar` calculează semnalul, cheamă `RiskEngine.evaluate`, și dacă e aprobat, trimite direct `self.submit_order(...)`. Semnalul (ce ar trebui expus în UI ca „propunere”) nu era separat de execuție.
3. **Metricile de backtest erau minimale**: `n_fills`, `n_decisions`, `ending_usdt`, `commissions_usdt`. Lipseau toate metricile cerute (win rate, Sharpe, drawdown etc.) și orice comparație cu baseline.
4. **Fără regimuri de piață** — nicio strategie nu știa dacă rulează în trend sau range.
5. **RiskEngine nu avea**: risc maxim per tranzacție explicit, expunere corelată, verificare lichiditate/spread, R:R minim. (Avea deja: notional per ordin, expunere per instrument/clasă, pierdere zilnică, drawdown, ordine/zi, kill switch, circuit breaker — acestea rămân neschimbate ca bază.)
6. **Toggle-ul de enable/disable scria YAML fără versiune** — o schimbare de parametri nu era distinsă de starea anterioară.
7. **UI-ul nu distingea** backtest / paper / live / experimental, nu arăta ipoteza, riscurile sau condițiile de invalidare.
8. **`paper sessions` și `backtest_ref` erau globale**, nu per-strategie (proveneau din `paper_run_summary.json` unic și din cel mai recent fișier din `backtests/reports/`).

Aceste probleme sunt adresate în [docs/backtesting-methodology.md](backtesting-methodology.md) (arhitectură + metrici) și [docs/risk-management.md](risk-management.md) (limite noi).

---

## 3. Strategii noi — decizie și motivare

### 3.1 Implementate în acest val

| Strategie | Categorie | Status inițial | Motivare |
|---|---|---|---|
| **EMA trend filter** (rescrisă) | Trend following | `paper_candidate` după validare OOS | Există deja, cost mic de rescriere pe interfața comună; adăugăm filtru ADX + cooldown pentru a reduce re-entry-urile pe zgomot |
| **Donchian breakout + volum** | Trend following / breakout | `experimental` | Ipoteză diferită de EMA (urmărește extreme de preț confirmate de volum, nu media mobilă) — testabilă separat, comportament diferit în range (nu ar trebui să tranzacționeze) |
| **RSI mean reversion (doar sideways)** | Mean reversion | `experimental` | Singura strategie din primul val care pariază pe reversie, nu pe continuare — utilă ca „control” pentru a vedea dacă piața testată e mai degrabă trending sau range-bound |
| **LLM-assisted** | — | `experimental` (neschimbată) | Rămâne cum era; nu e „mai bună” fără dovadă OOS |

### 3.2 Amânate explicit — și de ce

| Strategie | Motiv amânare |
|---|---|
| MACD confirmation | Puternic corelat cu EMA cross (ambele sunt derivate din EMA) — ar adăuga o strategie aproape redundantă cu #1, nu o ipoteză nouă |
| VWAP reversion | Necesită preț tipic intraday/tick-level; sursele actuale (Binance/Kraken OHLC public) nu oferă suficientă granularitate pentru un VWAP corect fără look-ahead |
| Relative strength ranking între active | Universul e format din 2 active crypto (ETHUSD, BTCUSD) — un ranking pe 2 elemente nu produce informație utilă |
| Risk parity simplificat / volatility targeting portfolio-level | Necesită un portofoliu multi-instrument gestionat simultan; arhitectura curentă rulează un instrument per proces de engine (o singură `PortfolioTracker` per strategie) |
| Rate of change, Bollinger Bands standalone | Suprapunere semnificativă cu RSI mean reversion / Donchian breakout; nu adaugă o ipoteză distinctă testabilă separat în acest val |
| Maximum correlation filter (ca strategie separată) | Implementată parțial ca limită de risc (`max_correlated_exposure` în `risk_limits.yaml`), nu ca strategie de trading |

ADX și ATR sunt folosite ca **filtre în interiorul** strategiilor de mai sus (regim de piață, distanță de stop), nu ca strategii de sine stătătoare — un semnal „ADX confirmation” fără o direcție de intrare/ieșire proprie nu produce un `BUY`/`SELL`/`HOLD` testabil independent.

---

## 4. Ce nu poate fi marcat „producție” și de ce

Conform criteriilor din [docs/backtesting-methodology.md](backtesting-methodology.md) §8:

- **Toate strategiile din acest repo rămân cel mult `paper_candidate`**, niciodată `production`/live — nu există cale de execuție live calificată (`src/execution/kraken_live.py` există dar nu e activată; `dry_run: true` peste tot).
- Istoricul disponibil local (fixture `tests/fixtures/bars_ethusd_1d.csv`, ~2 luni) e prea scurt pentru concluzii robuste pe orice strategie. Rulările documentate în secțiunea 7 folosesc acest fixture plus, unde e posibil, ferestre mai lungi din cache-ul local — numărul exact de bare e raportat explicit la fiecare rulare.
- LLM-assisted rămâne `experimental` până nu există un eșantion OOS pe care să bată baseline-ul EMA după costuri.
- Donchian breakout și RSI mean reversion pornesc `experimental`: sunt strategii noi, fără istoric de rulare — devin `paper_candidate` doar după ce backtestul din secțiunea 7 arată minimum de tranzacții (>1) și un `comparable()` reproductibil.

---

## 5. Referințe încrucișate

- Metodologie de backtest, split-uri, costuri, look-ahead: [docs/backtesting-methodology.md](backtesting-methodology.md)
- Limite de risc, cine le poate schimba, ce nu poate fi suprascris: [docs/risk-management.md](risk-management.md)
- Rezultatele rulării locale (numere reale, comparație cu baseline, regim de piață): secțiunea 7 din [docs/backtesting-methodology.md](backtesting-methodology.md) și concluzia finală din acest fișier, secțiunea 6.

---

## 6. Concluzie

Rulare locală reală: ETHUSD + BTCUSD, `1d`, 2024-01-01→12-31 (366 bare/activ, date publice Binance klines), split cronologic 60/20/20, walk-forward pe train+validation (3 folduri), holdout izolat (74 bare, ~2.5 luni, neatins înainte de această rulare), costuri 1×/2×/3×. Numerele complete, per activ și strategie, sunt în [docs/backtesting-methodology.md](backtesting-methodology.md) §7.

**Rezumat al rezultatelor (nu inventat, extras direct din rulare):**

- `ema_cross`: 2 tranzacții pe holdout la fiecare activ, randament mic dar pozitiv la 1×/2×/3× (+0.60%/+0.55%/+0.50% ETHUSD; +0.42%/+0.37%/+0.31% BTCUSD) — semnul nu se inversează la 3× costuri, dar eșantionul (2 tranzacții) e mult sub pragul de 10 pentru orice concluzie statistică. Pe walk-forward (3 folduri, tot 2024), a pierdut bani în 4 din 6 folduri — whipsaw vizibil.
- `donchian_breakout`: 0-2 tranzacții pe **un an întreg**, pe 2 active. Filtrul combinat ADX+volum aproape că nu se activează pe date reale ETH/BTC 2024.
- `rsi_mean_reversion`: 0-3 tranzacții pe un an întreg. 2024 a fost dominant `bull`/`trend`, nu `range` — ipoteza de mean-reversion nu a avut prea multe ocazii reale de testat.
- `llm_assisted`: fără rulare OOS nouă documentată în acest ciclu (rămâne pe rezultatul holdout de 13 zile din [docs/backtest-report.md](backtest-report.md): `avoid` pe toate zilele, 0 fill-uri) — nu există dovadă că bate baseline-ul.
- **Toate cele 3 strategii long-only rămân mult sub buy-and-hold** (+26.04% ETHUSD, +36.85% BTCUSD pe același holdout) — 2024 a fost un an puternic direcțional pentru crypto majors, iar `RiskEngine` (notional per ordin capat la 1000 din 10.000 capital, reconfirmare la fiecare bară) e conservator prin construcție, nu optimizat să capteze un trend mare cu puține poziții mici. E trade-off-ul documentat în [docs/risk-management.md](risk-management.md), nu un bug.

„Strategiile recomandate pentru paper trading sunt **niciuna, în acest moment** — deoarece toate cele trei strategii pe reguli (`ema_cross`, `donchian_breakout`, `rsi_mean_reversion`) au produs între 0 și 2 tranzacții pe holdout-ul de 74 de bare (sub pragul minim de 10 tranzacții pentru orice concluzie statistică), iar pe tot anul 2024 (walk-forward) numărul de tranzacții rămâne la fel de mic pentru Donchian și RSI. `ema_cross` e cea mai apropiată de a deveni `paper_candidate` (randament pozitiv, semn stabil la 1×/2×/3×), dar are nevoie de mai multe cicluri de tranzacționare observate înainte să treacă dincolo de `experimental`. Strategiile care trebuie evitate momentan pentru orice decizie de capital sunt **toate patru** (`ema_cross`, `donchian_breakout`, `rsi_mean_reversion`, `llm_assisted`) din cauza **eșantionului de tranzacții insuficient statistic (0-3 tranzacții/an) și a randamentului mult sub buy-and-hold pe o piață puternic direcțională** — nicio strategie nu a demonstrat că generează alpha peste ce ai obține ținând pur și simplu activul. Înainte de orice tranzacționare live trebuie să verificăm **(1) performanță pe un istoric mai lung și pe cel puțin un regim `bear`/`sideways` real, nu doar `bull` 2024; (2) un eșantion de minimum 10-20 de tranzacții per strategie pentru ca win rate/profit factor/expectancy să fie interpretabile; (3) sensitivity analysis pe parametrii impliciți (±1 treaptă), nedusă până acum; (4) rezultate consistente pe paper trading live (nu doar backtest) pentru cel puțin câteva săptămâni; (5) calea de execuție live (`src/execution/kraken_live.py`) rămâne complet neactivată — `dry_run: true` și `LIVE_TRADING_ENABLED=false` trebuie păstrate până toate punctele de mai sus sunt bifate.**”
