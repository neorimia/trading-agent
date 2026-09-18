# Raport de backtest — Faza 4 (Task 4)

**Task:** Task 4 (instrucțiuni §6) / Faza 4 (workflow §5) — Backtesting realist.

**Data rulării:** 2026-09-18.

**Run ID:** `faza4-ethusd-1d-202411-202412` (arhiva locală în `backtests/reports/`, gitignored).

**Mediu:** macOS ARM64, Python 3.12, NautilusTrader `1.231.0` (calificat în Faza 1), Qwen3-8B local (`qwen3:8b` Q4_K_M via Ollama).

---

## 1. Sursă de date (deviere față de `universe.yaml`)

`config/universe.yaml` marchează `ETHUSD` / `BTCUSD` cu `venue: KRAKEN` — asta e **ruta de execuție** pentru Faza 5, nu vendor-ul de istoric.

Istoricul de backtest e luat de pe **Binance public klines** (`GET /api/v3/klines`, fără autentificare, paginat pe `startTime`/`endTime`). Kraken-ul public OHLC întoarce ~720 lumânări și nu e practic de paginat pe luni. Același pattern ca Faza 1 (date Binance statice, venue simulat intern, zero conexiune de broker).

| Câmp | Valoare |
|---|---|
| Instrument univers | `ETHUSD` |
| Simbol istoric | `ETHUSDT` (Binance spot) |
| Timeframe | `1d` (timestamp = close-time UTC — bara e cunoscută la închidere) |
| Interval | 2024-11-01 → 2024-12-31 |
| Bare | 61 (fără gap-uri) |
| Dataset hash (sha256 canonic) | `c9ddad6021ec43d59e37a79db4a5b341b01d7e8f9fa290b3e378c157b68ba7c7` |
| Cache local | `.cache/market_data/` (gitignored, ca Faza 1) |

Validare: `DataValidator` respinge gap-uri, duplicate și timestamp-uri în viitor — nu repară silențios.

---

## 2. Costuri (nu preț mid)

Venue-ul Nautilus e `SimulatedVenue BINANCE`, cont CASH multi-currency, `MakerTakerFeeModel` pe fee-urile instrumentului.

| Multiplicator | Taker/maker fee | Spread bid/ask | Slippage (tick-uri) | Top-of-book (fill parțial) |
|---|---|---|---|---|
| 1× | 10 bps | 10 bps | 1 | 40% din cantitate la best, restul alunecat |
| 2× | 20 bps | 20 bps | 2 | idem |
| 3× | 30 bps | 30 bps | 3 | idem |

`PartialSlippageFillModel` e determinist (`random_seed=42`, probabilități 0 sau 1). Quote tick-uri sintetizate din close ± half-spread, deci matching-ul nu vede doar mid.

Aprobarea umană (Faza 5) e implicită în backtest: `RiskDecision.approved` e suficient pentru submit pe venue-ul simulat. Sizing-ul rămâne exclusiv în `src/risk/`.

---

## 3. Split cronologic + walk-forward

61 bare, 60% / 20% / 20%:

| Segment | Bare | Rol |
|---|---|---|
| Train | 36 | warmup + expanding window |
| Validation | 12 | OOS în walk-forward |
| Holdout | 13 (2024-12-19 … 2024-12-31) | neatins până la evaluarea finală |

Walk-forward pe train+validation, 3 fold-uri expanding, **doar baseline** (EMA 10/20, fără grid-search — parametrii sunt specificația, nu un fit pe holdout):

| Fold | Train | OOS | Fills | Comisioane 1× |
|---|---|---|---|---|
| 0 | 12 | 12 | 1 | 0.99989118 USDT |
| 1 | 24 | 12 | 1 | 0.99976443 USDT |
| 2 | 36 | 12 | 1 | 0.99985575 USDT |

EMA 10/20 nu e re-optimizat pe ferestre. Holdout-ul nu apare în nicio fereastră WF.

---

## 4. Holdout — baseline vs LLM, costuri 1× / 2× / 3×

Capital inițial: 10.000 USDT. `ending_usdt` = sold cash USDT (pozițiile holdout s-au închis).

| Cost | Baseline ending | Baseline fills | Baseline commissions | LLM ending | LLM fills | LLM commissions |
|---|---|---|---|---|---|---|
| 1× | 9975.17056968 | 2 | 1.97678512 | 10000.00000000 | 0 | 0 |
| 2× | 9973.19027337 | 2 | 3.95357023 | 10000.00000000 | 0 | 0 |
| 3× | 9971.20997704 | 2 | 5.93035536 | 10000.00000000 | 0 | 0 |

Baseline: long pe 2024-12-19, exit pe 2024-12-21 (2 fill-uri taker). Comisioanele scalează liniar cu multiplicatorul (1.98 → 3.95 → 5.93). PnL-ul baseline se înrăutățește la 2× și 3× — nu există un „avantaj” de trading care să dispară, ci o pierdere care crește cu costurile.

LLM (Qwen3-8B, temperature 0, cache pe sha256(`ProposalContext`)): **avoid** pe toate cele 13 zile de holdout. RiskEngine mapează `avoid` la `no_action_proposed`. Capitalul rămâne 10.000 la toate multiplicatoarele.

Comparație: pe acest holdout, LLM a evitat round-trip-ul pierzător al EMA-cross. Diferența se **lărgește** la 2×/3× (baseline plătește mai mult), nu se inversează. Nu e un semnal de alpha — e un eșantion scurt în care modelul a ales să nu tranzacționeze.

Propunerile au fost generate o dată prin `src.llm.service.generate_proposal` (același schema/prompt ca procesul izolat) și reluate din cache. Engine-ul nu importă `src.llm`.

---

## 5. Look-ahead bias

`tests/adversarial/test_lookahead_bias.py`: pentru cutoff-uri T, semnalul EMA și `ProposalContext` calculate pe `bars[:T+1]` sunt identice cu aceleași calcule pe o serie în care barele **după** T sunt corupte la 99999. Dacă strategia ar citi close-ul viitor, testul eșuează. Metodologie inspirată de Freqtrade lookahead analysis, fără dependență de cod Freqtrade.

---

## 6. Reproductibilitate

- `tests/integration/test_backtest_reproducibility.py`: două rulări Nautilus pe fixture-ul CSV, baseline și LLM cu cache read-only → `comparable()` identic.
- Rularea documentată a fost repetată (același `dataset_hash`, același cache de propuneri) → aceleași `ending_usdt` / `commissions_usdt` / decizii pe holdout.

Câmpuri excluse din comparație (ca în Faza 1): UUID-uri de runtime, wall-clock, telemetrie.

---

## 7. Cum se re-rulează

```bash
python -m scripts.backtest.run_backtest \
  --instrument ETHUSD --timeframe 1d \
  --start 2024-11-01T00:00:00+00:00 \
  --end 2024-12-31T23:59:59+00:00 \
  --direct-ollama \
  --run-id faza4-ethusd-1d-202411-202412
```

`--direct-ollama` umple cache-ul din script (nu din `engine/`) cu același `generate_proposal`. Re-rularea cu cache-ul deja populat nu re-apelează modelul. `--csv tests/fixtures/bars_ethusd_1d.csv` evită rețeaua.

---

## 8. Fișiere

| Path | Rol |
|---|---|
| `src/data/{sources,validation,cache}.py` | fetch, validare, hash |
| `src/engine/{signals,splits,cost_models,instruments,portfolio_tracker}.py` | semnal pur, split, costuri, tracker |
| `src/engine/{strategy_baseline,strategy_llm_assisted,proposal_cache,backtest_runner}.py` | strategii + harness |
| `scripts/backtest/run_backtest.py` | CLI |
| `tests/adversarial/test_lookahead_bias.py` | look-ahead |
| `tests/integration/test_backtest_reproducibility.py` | reproductibilitate |
| `backtests/reports/faza4-ethusd-1d-202411-202412/` | manifest + metrici (local, gitignored) |
