# Utilizare — agent local de paper trading

Ghid de operator pentru stack-ul local. Execuția e **paper** (`dry_run: true`, `SimulatedBroker`). Nu plasează ordine pe Kraken. LLM-ul (dacă e activ) doar propune; riscul și tu decideți.

Documente înrudite: [README.md](../README.md) (instalare), [paper-trading-report.md](paper-trading-report.md) (raport Faza 5), [apps/console/README.md](../apps/console/README.md) (consolă).

---

## 1. Ce face aplicația

| Proces | Port | Rol |
|---|---|---|
| LLM | `127.0.0.1:8765` | Propuneri JSON (Qwen via Ollama). Fără execuție. |
| Research | `127.0.0.1:8766` | Context extern (opțional; pornește doar dacă există `.env.research`). |
| Control | `127.0.0.1:8767` | API operator: health, halt, aprobări, start/stop paper. |
| Consolă | `127.0.0.1:4200` | UI Angular; proxy `/v1` → control. |
| Paper stream | copil al controlului | Poll OHLC public Kraken → sesiune pe fiecare lumânare **închisă**. |
| Broker monitor | copil separat | Dacă există `KRAKEN_SPOT_API_KEY` + secret: Balance/OpenOrders, **doar citire**. Nu e calea de execuție. |

**Nu este:** trading live, start live, approve live, sau trece automat din paper în live.

---

## 2. Prima dată (instalare)

Cerințe: Python 3.12, [`uv`](https://github.com/astral-sh/uv), Node (pentru consolă), opțional [Ollama](https://ollama.com) cu `qwen3:8b`.

```bash
cd trading-agent
uv sync --group dev
uv run pre-commit install

cp .env.engine.example .env.engine
cp .env.llm.example .env.llm
cp .env.control.example .env.control
# opțional, pentru pagina Research:
cp .env.research.example .env.research
```

Completează valorile locale. **Nu** pune chei de trading live. Lasă `LIVE_TRADING_ENABLED=false`. Fișierele `.env.*` nu intră în git.

Verificare:

```bash
uv run python -c "import nautilus_trader; print(nautilus_trader.__version__)"
uv run pytest --collect-only
```

---

## 3. Pornire

Din rădăcina repo-ului:

```bash
uv run python scripts/dev/start_stack.py
```

Aștepți `stack ready`, apoi deschizi [http://127.0.0.1:4200/](http://127.0.0.1:4200/).

Launcher-ul pornește LLM, research (dacă `.env.research` există), control, consolă, apoi `POST /v1/agent/start` (paper stream + monitor dacă sunt chei spot). **Ctrl-C** oprește paper/monitor, apoi procesele HTTP.

Opțiuni:

| Flag | Efect |
|---|---|
| `--no-paper` | Nu pornește stream-ul; folosești **Start agent** din chrome-ul consolei. |
| `--no-console` | Fără `ng serve`; rămâne API-ul pe `:8767`. |

Porturile trebuie libere (`8765`, `8766`, `8767`, `4200`). Dacă Ollama nu răspunde pe `:11434`, vezi un warning; baseline-ul EMA tot funcționează.

Servicii individuale (dacă nu vrei launcher-ul):

```bash
uv run python -m src.llm.server          # :8765
uv run python -m src.research.server     # :8766
uv run python -m src.control.server      # :8767
cd apps/console && npm start             # :4200
```

Apoi, în consolă: **Start agent** (doar paper).

---

## 4. Consola — pagini

Chrome (sus, pe toate paginile):

- mod `paper` / `live` (live rămâne blocat în acest build)
- status agent (`running` / oprit) și venue (`connected` / `stale` / `down`)
- **Start agent** / **Stop** — pornește sau oprește bucla paper
- **Emergency stop** — scrie halt flag; ordinele noi sunt refuzate. Reluarea e manuală pe pagina Risk (**Clear halt flag**), apoi Start din nou.

| Rută | Ce vezi / ce faci |
|---|---|
| Dashboard `/` | Equity, cash, P&L paper (simulat), broker monitor, plan zilnic. |
| Market `/market` | Universe allowlist; prețuri = close de bar, nu bandă live. Click pe simbol → grafic. |
| Strategies `/strategies` | Enable/disable. După schimbare e nevoie de **restart** (Stop + Start). Nu ocolește riscul și nici aprobarea umană. |
| Orders `/orders` | **Pending human approval**, poziții paper, istoric ordine. Aici aprobi sau respingi. |
| Risk `/risk` | Limite din YAML, circuit breaker, halt reset. Scrierea limitelor cere confirmare tastată `MAX_DAILY_LOSS` și restart. |
| Research `/research` | Documente externe (neîncredere implicită). Necesită procesul research. |
| Activity `/agent` | Audit append-only (propuneri, risc, aprobări, fill-uri). |
| Settings `/settings` | Flag-uri de securitate (secretele nu se afișează). Token opțional dacă `CONTROL_OPERATOR_TOKEN` e setat. |

Rol `observer` (`CONTROL_OPERATOR_ROLE`): doar vizualizare, fără mutații.

---

## 5. Cum știi că stream-ul e viu

Health în UI sau:

```bash
curl -sS http://127.0.0.1:8767/v1/health
```

Semne bune:

- `agent`: `running`
- `venue`: `connected`
- `last_bar_at` setat (ex. ETHUSD)
- `heartbeat_age_s` sub ~30s (pragul din `config/paper_trading.yaml`)
- `reconciliation`: `ok`
- `trading_mode`: `paper`

PID-uri: `runtime/paper/control/agent.pid` și `broker_monitor.pid`. Procesul paper trebuie să aibă STAT diferit de `Z` (zombie).

Loguri:

| Fișier | Sursă |
|---|---|
| `runtime/logs/{llm,research,control,console}.log` | procesele HTTP / Angular |
| `runtime/paper/logs/paper.log` | stdout/stderr copil paper |
| `runtime/paper/logs/monitor.log` | sidecar monitor |

Dacă copilul iese imediat la start, controlul raportează eșec și mesajul e în `paper.log`.

---

## 6. Testul end-to-end pe stream (paper)

Config operațional: [`config/paper_trading.yaml`](../config/paper_trading.yaml) — `ETHUSD`, timeframe **1h**, cash simulat `10000`.

1. Lasă stack-ul pornit (`start_stack.py` sau Start agent).
2. Stream-ul **nu** tranzacționează continuu. La pornire **seed**-uiește istoricul; o **sesiune nouă** apare doar pe o lumânare **închisă**, mai nouă decât `last_bar`.
3. Implicit strategia e **baseline EMA 10/20** (`--skip-llm`), nu Qwen. Nu fiecare oră produce semnal.
4. Dacă riscul aprobă, apare un card pe **Orders** (timeout 1h, `approval_timeout_s`).
5. Apasă **Approve** sau **Reject**. Fără Approve nu există fill.
6. Poziția și P&L sunt pe **Paper book (simulated)**. Panoul Kraken monitor poate rămâne gol — e alt proces, doar observare.

Aprobare din CLI (același ApprovalGate pe fișiere):

```bash
PYTHONPATH=. uv run python scripts/paper_trading/approve.py <correlation_id> --approve
```

Pending via API: `GET /v1/approvals/pending`.

---

## 7. Strategie LLM (opțional)

Implicit `llm_assisted` e **oprit** în [`config/strategies.yaml`](../config/strategies.yaml).

1. Ollama trebuie să ruleze (`ollama serve`) cu `qwen3:8b`.
2. Strategies → activează **LLM-assisted (proposal only)**.
3. **Stop** apoi **Start agent** (restart obligatoriu).
4. Copilul paper apelează LLM-ul; tot trece prin RiskEngine + ApprovalGate.

Fără restart, rămâne EMA.

---

## 8. Replay rapid (fără să aștepți ora)

Alt director runtime, nu înlocuiește stream-ul din consolă. Operator **scripted** = auto-approve (doar pentru acest CLI):

```bash
PYTHONPATH=. uv run python scripts/paper_trading/run_paper_session.py \
  --skip-llm --operator scripted --simulate-restart --max-sessions 30 \
  --runtime-dir runtime/paper-faza5 \
  --start 2025-08-01T00:00:00+00:00 --end 2026-09-18T23:59:59+00:00
```

Aprobare umană pe batch: `--operator file`, apoi `approve.py`. LLM live: omite `--skip-llm`.

Detalii și rezultate de referință: [paper-trading-report.md](paper-trading-report.md).

---

## 9. Oprire și halt

| Acțiune | Efect |
|---|---|
| **Stop** (chrome) sau Ctrl-C pe `start_stack.py` | Oprește paper + monitor (SIGTERM). Stack-ul launcher se închide. |
| **Emergency stop** | Halt: flag pe disc, fără ordine noi. Agentul poate rămâne pornit până îl oprești. |
| Risk → **Clear halt flag** | Șterge flag-ul. **Nu** repornește agentul singur. |

Nu lăsa un PID zombie: dacă health zice `running` dar `last_bar` nu se mișcă, verifică `ps` și `runtime/paper/logs/paper.log`, apoi Stop/Start sau Ctrl-C + `start_stack.py` din nou.

---

## 10. Probleme frecvente

| Simptom | Ce verifici |
|---|---|
| Port already in use | Alt `start_stack` sau proces pe 8765–8767 / 4200. Ctrl-C pe instanța veche. |
| `agent: running` fără `last_bar` | Copil mort/zombie; vezi `paper.log`. Restart. |
| Venue `stale` | Nicio lumânare închisă în `stale_data_threshold_s` (3h la 1h). Rețea Kraken public OHLC. |
| Pending gol ore în șir | Normal dacă EMA nu taie. Aștepți barul următor sau rulezi replay-ul din §8. |
| Research down | Lipsește `.env.research`; e warning, restul merge. |
| LLM fail | Ollama oprit; cu `llm_assisted` inactiv, paper-ul tot rulează pe EMA. |
| Observer: viewing only | `CONTROL_OPERATOR_ROLE=observer` sau token lipsă. Settings → token dacă e configurat. |
| `agent/start HTTP 403: live start is blocked` | `LIVE_TRADING_ENABLED=true` în `.env.engine` (sau în shell). Pune `false`. Start live nu e disponibil. |

---

## 11. Ce nu faci

- Nu seta `LIVE_TRADING_ENABLED=true`.
- Nu pune `dry_run: false` în `paper_trading.yaml` (pornirea e refuzată).
- Nu copia chei de broker în `.env.llm`.
- Nu trata soldul Kraken din monitor ca P&L paper.
- Nu aștepta ordine pe exchange: fill-ul e local, simulat.
