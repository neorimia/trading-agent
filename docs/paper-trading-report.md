# Raport de paper trading — Faza 5 (Task 5)

**Task:** Task 5 (instrucțiuni §7) / Faza 5 (workflow §6) — Paper trading, Cale B.

**Data rulării:** 2026-09-18.

**Run ID:** `20260918T143445Z` (arhiva locală în `runtime/paper-faza5/`, gitignored).

**Decizii umane blocate înainte de implementare:**
- **Cale B** — crypto via Kraken, `dry_run: true`.
- **monitor/ flag-only** — watchdog-ul scrie `runtime/control/halt.flag` (KillSwitch existent); fără client de broker separat.

---

## 1. Mediu și izolare

| Câmp | Valoare |
|---|---|
| Path | B |
| `dry_run` | `true` (validat hard la încărcare; `false` refuză pornirea) |
| Venue execuție | `KRAKEN` |
| Instrument | `ETHUSD` |
| Date de piață | Kraken public OHLC (`GET /0/public/OHLC`, **fără autentificare**) |
| Execuție | `SimulatedBroker` (echivalent Nautilus `SandboxExecutionClient`) — **zero ordine pe exchange** |
| Wiring Nautilus | `KrakenDataClientConfig(api_key=None, api_secret=None)` + `SandboxExecutionClientConfig(venue=KRAKEN, CASH)` |
| Chei Kraken în mediu | absente (asserție `assert_no_kraken_trading_keys`) |
| Chei live | zero |
| Aprobare umană | `ApprovalGate` pe fișiere; operatorul de rulare a scris aceleași `decision.json` ca un om (`ScriptedApprovalOperator`) |

Spike public Kraken (2026-09-18): HTTP 200, `error: []`, 721 lumânări zilnice `XETHZUSD`, fără API key.

---

## 2. Rularea de 30 de sesiuni

| Câmp | Valoare |
|---|---|
| Interval date | 2025-08-01 → 2026-09-18 UTC |
| Bare încărcate | 414 |
| Lookback | 20 |
| Sesiuni | **30** |
| Client de propuneri | baseline EMA-cross (determinist, `--skip-llm`) |
| Incident critic | niciunul; `halted=false` |
| Restart simulat | **reconciliere completă** (`restart_reconciled=true`) — snapshot broker restaurat pe o instanță nouă |
| Latență buclă | 0.0763 s total, **2.5 ms / sesiune** (fără fetch-ul OHLC) |

Distribuție decizii:

| Direcție propusă | Sesiuni | Risk aprobat | Human aprobat | Fill |
|---|---|---|---|---|
| `long` | 18 | 7 | 7 | 7 |
| `exit` | 12 | 0 | — | 0 |

Respingeri de risc (așteptate, nu incidente):
- `below_min_notional_or_no_capacity`: 12 (cap de expunere după fill-urile deja deschise)
- `no_open_position`: 11 (`exit` fără poziție deschisă)

Jurnal audit (append-only SQLite): `reconciliation_ok` 1, `proposal` 30, `risk_decision` 30, `human_approval` 7, `order_submitted` 7, `fill` 7. Zero ordine fără `human_approval=true`. 30 `correlation_id` unice.

---

## 3. Criteriile din DoD

| Criteriu | Rezultat |
|---|---|
| Zero ordine neautorizate | 0 |
| Zero duplicate `client_order_id` | 0 (unicitate + test `test_duplicate_client_order_id_does_not_resubmit`) |
| Zero ordine peste limită | 0 executate; 12 respinse de risc sub cap |
| Reconciliere după restart | da, pe instanță broker restaurată |
| Rată JSON invalid | 0 (propuneri structurate, nu LLM live) |
| Rată citări nesusținute | 0 (baseline, fără rationale LLM) |
| Reconectare / stale / reject / partial / timeout / duplicate | acoperite în `tests/integration/test_paper_resilience.py` |

---

## 4. Cum se reproduce

```bash
PYTHONPATH=. uv run python scripts/paper_trading/run_paper_session.py \
  --skip-llm --operator scripted --simulate-restart --max-sessions 30 \
  --runtime-dir runtime/paper-faza5 \
  --start 2025-08-01T00:00:00+00:00 --end 2026-09-18T23:59:59+00:00
```

Aprobare umană reală (fără operator scriptat): `--operator file`, apoi `scripts/paper_trading/approve.py <correlation_id> --approve`.

LLM live: omite `--skip-llm` și pornește `src/llm/server.py` pe loopback.

---

## 5. Revizuire PO / Risk owner

**Revizuit:** 2026-09-19 — PO/Risk owner (Gabriel Cruceanu).  
**Verdict:** acceptat ca evidență Faza 5 Path B.

Acceptat:
- 30 sesiuni ETHUSD pe OHLC public Kraken, `halted=false`, restart reconciliat
- 7 fill-uri, toate cu `human_approval=true`; zero ordine neautorizate / duplicate / peste limită
- Calea B: `dry_run: true`, `SimulatedBroker`, zero chei de trading

Nu autorizează:
- `LIVE_TRADING_ENABLED=true`
- `dry_run: false`
- capital pe Kraken Spot

Următorul ciclu (cod 2026-09-19, nu live): paper `--mode stream` pe OHLC public + sidecar `KrakenLiveBroker` `monitor` (Balance/OpenOrders). Paper recon **nu** compară cu soldul Kraken. Timeframe operațional: `1h` (`stale_data_threshold_s: 10800`); batch-ul de 30 sesiuni din acest raport rămâne pe intervalul 1d de atunci. `LIVE_TRADING_ENABLED` rămâne oprit. 30 sesiuni aici = 30 cicluri bar→decizie, nu 30 zile calendaristice.
