# Raport de calificare — NautilusTrader v1.231.0

**Task:** Task 1 (instrucțiuni §3) / Faza 1 (workflow §2) — Instalare și calificare NautilusTrader (v1 stabil).

**Data calificării:** 2026-09-18.

**Mediu:** macOS (Darwin 25.6.0), Apple M2 Max, ARM64, Python 3.12.13, venv local al proiectului (`.venv/`).

---

## 1. Versiune instalată

| Câmp | Valoare |
|---|---|
| Pachet | `nautilus_trader` |
| Versiune | `1.231.0` (pinned exact în `pyproject.toml` — `nautilus_trader==1.231.0`, **nu** `develop`, **nu** v2 RC — regulă absolută #8) |
| Wheel instalat | `nautilus_trader-1.231.0-cp312-cp312-macosx_26_0_arm64.whl` |
| SHA256 wheel | `ed9304cbedeccd03e157c89b1e9acc3c9c35785f3bc2a114e4ea2e262a051890` (din `uv.lock`, verificat de `uv` la instalare) |
| Tag ARM64 | `cp312-cp312-macosx_26_0_arm64` — nativ, zero fallback Rosetta (consistent cu verificarea `lipo -info` din Faza 0) |
| Commit sursă corespondent | `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317` (tag `v1.231.0`, repo `nautechsystems/nautilus_trader`, rezolvat via GitHub API din tag-ul semnat) |
| Locație instalare | `.venv/lib/python3.12/site-packages/nautilus_trader/` |

**Verificare import + versiune** (`python -c "import nautilus_trader; print(nautilus_trader.__version__)"`):

```
1.231.0
```

---

## 2. Exemplul oficial reprodus

**Sursă:** [`docs/getting_started/backtest_low_level.py`](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/docs/getting_started/backtest_low_level.py) din repo-ul oficial, la commit-ul `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317` (tag `v1.231.0`) — tutorialul „Backtest (Low-Level API)": strategie EMA cross cu execuție TWAP pe un exchange Binance Spot **simulat**, folosind date istorice de trade ticks (ETHUSDT), 2020-08-14, ~5 ore.

**Date istorice:** `tests/test_data/binance/ethusdt-trades.csv` din același commit — fișier static, 69.807 trade ticks, licențiat sub același repo. Descărcat o singură dată de `scripts/nautilus_qualification/fetch_test_data.py` într-un cache local (`.cache/`, exclus din git), cu verificare `sha256` (`a90fd7b0a83d32190258651eca7ecb0ecdcaf3deb54f73a17ce028bfe49fdd74`) la fiecare rulare ulterioară — zero re-descărcare dacă hash-ul se potrivește.

**Reproducere:** `src/` → `scripts/nautilus_qualification/run_backtest.py`.

**Singura modificare față de exemplul oficial:** încărcarea datelor. Exemplul oficial folosește `TestDataProvider().read_csv_ticks("binance/ethusdt-trades.csv")`, care — fără un checkout local complet al repo-ului sursă NautilusTrader — descarcă aceleași date de pe branch-ul `develop` la fiecare rulare (`fsspec` + `GithubFileSystem`, vezi `nautilus_trader/test_kit/providers.py:_determine_filesystem`). `develop` e un target mobil, nepotrivit pentru un raport de calificare reproductibil (§3, criteriul „rulare repetată → același output"). Am înlocuit apelul cu `CSVTickDataLoader.load(file_path=<fixture local pinned>)` — exact funcția pe care `TestDataProvider.read_csv_ticks` o apelează intern, doar că pe un fișier pinned prin hash de commit în loc de un branch mobil. **Logica de backtest propriu-zisă (engine, venue, strategie, algoritm de execuție) e identică, neschimbată.**

**Zero conexiune de rețea către un broker real:** venue-ul `BINANCE` e un `SimulatedVenue` intern al `BacktestEngine`, fără niciun client de execuție extern. Singura conexiune de rețea din tot procesul e descărcarea inițială (unică, cache-uită) a fișierului CSV static de pe `raw.githubusercontent.com` — nu un feed sau broker.

---

## 3. Rezultate obținute

Rulare de referință (`python -m scripts.nautilus_qualification.run_backtest`), log complet salvat în `backtests/reports/nautilus_qualification/run_1.log` și `run_2.log`.

| Metrică | Valoare |
|---|---|
| Interval backtest | 2020-08-14 10:00:00.223 UTC → 2020-08-14 14:59:58.693 UTC (4h 59m 58s) |
| Iterații (ticks procesate) | 69.806 |
| Total evenimente | 152 |
| Total ordine | 75 |
| Total poziții | 15 |
| Sold inițial | 1.000.000,00000000 USDT + 10,00000000 ETH |
| Sold final | 999.998,88570475 USDT + 10,00000000 ETH |
| PnL total (USDT) | −1,11429525 USDT (−0,0111 %) |
| PnL total (ETH) | 0,0 (poziție ETH revine la 10,0 la final) |
| Long Ratio | 0,53 |
| Câștig maxim per poziție | 0,24298735 USDT |
| Timp de execuție (wall-clock, engine) | ~0,29 s pentru ~4h59m de date simulate |

**Interpretare (ordine de mărime, nu comparație cifră-cu-cifră — conform §3 pas 4):** rezultatul e consistent cu ce descrie tutorialul oficial — o strategie EMA cross simplă, fără optimizare de parametri, pe o fereastră scurtă (5h) de date istorice, produce un rezultat aproape neutru, ușor negativ, dominat de comisioane (75 de ordine × ~0,00425 USDT/ordin ≈ 0,32 USDT comisioane cumulate, plus impactul spread-ului simulat pe execuții MARKET). Nu există nicio discrepanță calitativă față de comportamentul documentat — tutorialul nu promite profitabilitate, ci doar demonstrează pipeline-ul complet (date → strategie → execuție TWAP → raportare). **Nu am ajustat perioada sau parametrii pentru a „repara" rezultatul.**

### Reproductibilitate (verificată prin rulare repetată)

Am rulat scriptul de două ori consecutiv și am comparat log-urile complete (`run_1.log` vs. `run_2.log`), normalizând doar câmpurile despre care NautilusTrader documentează explicit că sunt generate per-rulare (nu fac parte din rezultatul simulării):

- `instance_id`, `Run ID`, `event_id` — UUID-uri random per proces/eveniment de runtime.
- `Run started` / `Run finished`, `Elapsed time`, `Initialized in Xms/µs`, `Integrity check passed in Xµs` — timestamp-uri de wall-clock reale ale mașinii care rulează scriptul.
- `RAM-*`, `Swap-*`, `PID` — telemetrie de sistem la momentul rulării.

După normalizare, **toate câmpurile relevante pentru simulare sunt identice bit-cu-bit între cele două rulări**: fiecare preț, cantitate, comision, notional, sold de cont, timestamp de eveniment simulat (`ts_event`/`ts_init` în nanosecunde unix, domeniul `2020-08-14`), ID de poziție/ordin derivat determinist din `client_order_id`, și toate cele trei rapoarte finale (account, order fills, positions) — identice. Diferența unică rămasă după normalizare a fost o linie de log de disconnect suprapusă cu wall-clock-ul real al procesului, fără nicio legătură cu conținutul simulării.

**Concluzie: același input → același output, confirmat.**

---

## 4. Inspecția `RiskEngine` (cod instalat, nu documentație)

Sursă inspectată direct: `.venv/lib/python3.12/site-packages/nautilus_trader/risk/engine.pyx` (1212 linii, Cython — sursa e livrată alături de extensia compilată `.so`) și `nautilus_trader/risk/config.py`.

### Configurație (`RiskEngineConfig`)

- `bypass: bool = False` — dacă `True`, sare peste **toate** verificările de risc și rate-limit-urile (dar tot verifică ID-uri duplicate). **Notă pentru Faza 3:** acest flag nu trebuie niciodată setat `True` în cod productiv — e echivalentul intern al unui kill switch invers.
- `max_order_submit_rate: str = "100/00:00:01"` — rate limit pe comenzi de submit ordine (throttler, format `N/interval`).
- `max_order_modify_rate: str = "100/00:00:01"` — rate limit pe modificări de ordine.
- `max_notional_per_order: dict[str, int]` — notional maxim per `InstrumentId`, configurabil per instrument, poate fi actualizat la runtime prin `set_max_notional_per_order()`.
- `debug: bool = False` — logging suplimentar pe calea de verificare a riscului.

### Ce validează concret `RiskEngine` la fiecare comandă (`SubmitOrder`/`SubmitOrderList`/`ModifyOrder`)

1. **Preț** (`_check_price`): precizie ≤ precizia instrumentului; preț pozitiv (cu excepția instrumentelor care permit explicit preț negativ, ex. anumite futures pe energie).
2. **Cantitate** (`_check_quantity`): precizie ≤ precizia instrumentului; `quantity` între `instrument.min_quantity` și `instrument.max_quantity` (verificare de bază la nivel de ordin, sărită pentru `is_quote_quantity` — acelea sunt verificate mai jos pe cantitatea efectivă convertită).
3. **Cantitate efectivă per cont** (`_check_orders_risk_for_account`), pentru fiecare ordin grupat pe `account_id`:
   - Conversie quote→base pentru ordine cotate în monedă de cotare (`is_quote_quantity`), folosind cel mai bun preț disponibil (worst-case pentru LIMIT/STOP_LIMIT).
   - Re-verificare `min_quantity`/`max_quantity` pe cantitatea efectivă (post-conversie), cu motiv explicit în evenimentul de refuz (`QUANTITY_EXCEEDS_MAXIMUM` / `QUANTITY_BELOW_MINIMUM`).
   - **Notional per ordin** vs. `max_notional_per_order` (config, per instrument) → `NOTIONAL_EXCEEDS_MAX_PER_ORDER`.
   - **Notional** vs. `instrument.min_notional`/`instrument.max_notional` (limite native ale instrumentului, nu ale config-ului de risc) → `NOTIONAL_LESS_THAN_MIN_FOR_INSTRUMENT` / `NOTIONAL_GREATER_THAN_MAX_FOR_INSTRUMENT`.
   - **Sold disponibil**: impactul asupra soldului (`account.balance_impact`) nu poate face `free balance` negativ, decât dacă contul permite explicit `allow_borrowing` (margin) → `NOTIONAL_EXCEEDS_FREE_BALANCE`.
   - **Notional cumulat de cumpărare** în același batch de ordine, per cont, nu poate depăși soldul liber → `CUM_NOTIONAL_EXCEEDS_FREE_BALANCE`.
   - Pentru vânzări: distincție explicită între „reducere de poziție" (nu consumă sold, sare verificarea) și vânzare care deschide/mărește short (verificată separat).
4. **Stare de tranzacționare** (`_execution_gateway`): dacă `trading_state == HALTED`, orice `SubmitOrder`/`SubmitOrderList` e refuzat necondiționat, indiferent de conținut. Dacă `REDUCING`, ordinele care ar mări o poziție netă existentă sunt refuzate (doar reducerea e permisă).
5. **Rate limiting**: throttler separat pentru submit și modify, configurabil (`max_order_submit_rate`/`max_order_modify_rate`), cu refuz automat (`_deny_new_order`/`_deny_modify_order`) la depășire.
6. **Expirare GTD**: ordinele cu `expire_time` deja trecut sunt refuzate la intrare, nu doar la timeout ulterior.

### Relevanță pentru Faza 3 (reguli de risc deterministe)

`RiskEngine`-ul NautilusTrader validează corect forma și limitele **la nivel de ordin/venue** (preț, cantitate, notional, sold, stare halt), dar:
- **Nu are noțiune de pierdere zilnică maximă sau drawdown** — acestea trebuie implementate separat, la nivelul `src/risk/` din acest proiect (design §4.6, `risk_limits.yaml`), nu în config-ul NautilusTrader.
- **Nu are kill switch cu semantică de business** — `trading_state=HALTED` e mecanismul de bază pe care `src/risk/kill_switch.py` (Faza 3) trebuie să îl orchestreze, nu să îl înlocuiască.
- `max_notional_per_order` e per-instrument, nu per-clasă de active — validarea „expunere max per clasă" din `risk_limits.yaml` rămâne responsabilitatea `RiskEngine`-ului propriu (`src/risk/risk_engine.py`), aplicată **înainte** ca o comandă să ajungă la NautilusTrader.

Concluzie: NautilusTrader e sursa de adevăr pentru validări de format/limite native ale venue-ului; limitele de business (risc determinist, sursă unică de adevăr conform regulii absolute #3) rămân exclusiv în `src/risk/`, aplicate pe `ParsedProposal` înainte de orice `SubmitOrder`.

---

## 5. Fișiere create pentru această calificare

- `scripts/nautilus_qualification/fetch_test_data.py` — descarcă + verifică sha256 fixture-ul oficial (o singură dată, cache local).
- `scripts/nautilus_qualification/run_backtest.py` — reproduce exemplul oficial, cu singura modificare documentată la §2.
- `backtests/reports/nautilus_qualification/run_1.log`, `run_2.log` — log-urile complete ale celor două rulări folosite pentru verificarea reproductibilității.
- `src/engine/adapters/__init__.py` — scaffold inițial, fără logică de business (deliverabil Task 1).

---

## 6. Checkpoint DoD (Task 1 / instrucțiuni §3)

- [x] Exemplul oficial de backtest rulează integral, fără modificări majore de cod (unica modificare — sursa datelor, pinned local — documentată la §2).
- [x] Raportul de calificare există, cu rezultate reproductibile (verificat prin rulare repetată, §3 — identice bit-cu-bit după normalizarea câmpurilor de runtime nedeterministe prin design).
- [x] Zero conexiune de rețea către un broker real (venue simulat intern; singura rețea folosită e descărcarea unică a unui fișier istoric static, cache-uit).
