# Agent local de analiză și trading (multi-asset)

Agent local de analiză și trading care combină un **motor determinist** de execuție/risc/portofoliu (NautilusTrader) cu un **strat de raționament LLM** (Qwen3-8B, local, via Ollama) ținut strict în afara autorității de execuție. LLM-ul propune, codul determinist decide.

**Status actual:** Fazele 0–2 complete. Mediul local, calificarea NautilusTrader v1.231.0 și stratul LLM izolat (Qwen3-8B via Ollama, HTTP loopback) sunt în place. LLM-ul produce doar propuneri JSON; nu are import sau acces către `risk/`/`execution/`/`engine/`. Nicio conexiune la broker/exchange live, niciun secret sau credențial real.

## Documente

| Document | Conținut |
|---|---|
| [`brief-proiect-agent-trading-local.md`](brief-proiect-agent-trading-local.md) | Brief de proiect (v1.0): obiectiv, scope, arhitectură propusă, stack tehnic, fazele și gate criteria, buget, riscuri, constrângeri legale. Punct de plecare recomandat. |
| [`CLAUDE-instructiuni-faza-0-4.md`](CLAUDE-instructiuni-faza-0-4.md) | Instrucțiuni de execuție pentru Claude Code: reguli absolute de siguranță, structura de repository recomandată, task-uri detaliate (0–5) cu criterii de acceptare pentru Fazele 0–4. |
| [`design-componente-faza-0-4.md`](design-componente-faza-0-4.md) | Design tehnic la nivel de componentă: frontiere de proces (izolare LLM), interfețe pe modul, contracte de date (JSON), diagrame de secvență pentru fluxurile principale. Punct de plecare pentru `/sc:implement`. |
| [`Raport-agentic-trading-2026-09-18.md`](Raport-agentic-trading-2026-09-18.md) | Evaluare tehnică comparativă a proiectelor open-source de agentic trading (licențe, activitate, fișe tehnice), arhitectura propusă, controale tehnice obligatorii, plan 30/60/90 zile. |
| [`research_agentic_trading_bots.md`](research_agentic_trading_bots.md) | Research tehnic independent asupra acelorași proiecte open-source, cu analiză de compatibilitate Robinhood și plan etapizat Faza 0–6. Folosit ca verificare încrucișată pentru raportul de mai sus. |

## Instalare (mediu local)

Verificat pe o clonă curată, macOS Apple Silicon (arm64), Python 3.12.

**Cerințe:**
- Python 3.12 (`brew install python@3.12`)
- [`uv`](https://docs.astral.sh/uv/) (`brew install uv` sau `pipx install uv`) — gestionează venv-ul și dependențele fixate din `pyproject.toml`/`uv.lock`
- [`gitleaks`](https://github.com/gitleaks/gitleaks) (`brew install gitleaks`) — scanner de secrete, rulat ca pre-commit hook
- [`Ollama`](https://ollama.com) cu modelul `qwen3:8b` (cuantizare Q4_K_M) — necesar doar pentru procesul LLM și pentru testele marcate `llm_live`

**Pași:**

```bash
git clone <url-repo> trading-agent
cd trading-agent

# Instalează dependențele fixate (creează .venv/ automat)
uv sync --group dev

# Activează pre-commit hook-ul de scanare a secretelor
uv run pre-commit install

# Copiază șabloanele de mediu (fișierele reale NU intră niciodată în git)
cp .env.engine.example .env.engine
cp .env.llm.example .env.llm
cp .env.control.example .env.control
# apoi completează manual valorile relevante în fiecare fișier

# Verifică instalarea
uv run python -c "import nautilus_trader; print(nautilus_trader.__version__)"
uv run pytest --collect-only
```

**Note de compatibilitate ARM64 (verificat 2026-09-18, macOS 26 / Darwin 25.6.0, Python 3.12.13):**
- Toate pachetele critice (`nautilus_trader==1.231.0`, `pydantic`/`pydantic-core`, `numpy`, `pandas`, `pyarrow`, `msgspec`) instalează wheel-uri **native arm64** — verificat cu `lipo -info` pe fiecare `.so` compilat. Zero emulare Rosetta.
- `uvloop` instalează un wheel **universal2** (conține și slice arm64, și x86_64) — pe Apple Silicon rulează nativ pe slice-ul arm64, nu e o rulare prin Rosetta.
- Dacă un pachet nou adăugat ulterior nu are wheel arm64 și se instalează doar prin build din sursă/emulare, documentează explicit acest fapt aici înainte de a-l fixa în `pyproject.toml`.

**Strat LLM izolat (Faza 2):** proces separat, bind obligatoriu pe loopback (`127.0.0.1`). Nu încarcă `.env.engine`.

```bash
# Ollama trebuie să ruleze deja (ollama serve) cu qwen3:8b disponibil
uv run python -m src.llm.server
```

Testele de izolare AST și contractul de schemă rulează în suita standard. Testul live contra modelului real se skip-uiește singur dacă Ollama nu răspunde:

```bash
uv run pytest
uv run pytest -m llm_live    # doar apelul real către Qwen3-8B
```

## Consolă de operator (control plane + Angular)

Al patrulea proces pe loopback (`127.0.0.1:8767`). Citește runtime/audit/config și scrie doar acțiuni de operator (halt, aprobări paper, start/stop paper). Nu apelează LLM `/propose` și nu expune secrete.

Pornește tot stack-ul local (LLM `:8765`, research `:8766`, control `:8767`, consolă `:4200`, apoi paper stream prin `POST /v1/agent/start`):

```bash
uv run python scripts/dev/start_stack.py
```

`--no-paper` lasă Start agent pe butonul din UI. `--no-console` sare `ng serve`. Ctrl-C oprește paper/monitor, apoi procesele HTTP. Nu setează `LIVE_TRADING_ENABLED`. Loguri: `runtime/logs/`.

Servicii individuale, dacă nu vrei launcher-ul:

```bash
uv run python -m src.llm.server          # :8765
uv run python -m src.research.server     # :8766
uv run python -m src.control.server      # :8767
cd apps/console && npm start             # :4200 — proxy /v1 către :8767
```

Emergency stop e permanent în chrome. Start live și approve live rămân blocate. Detalii: [`apps/console/README.md`](apps/console/README.md).

**Scanner de secrete:** `gitleaks` rulează automat la fiecare `git commit` (hook local din `.pre-commit-config.yaml`, scanează doar diff-ul staged). Poate fi rulat manual oricând cu:

```bash
gitleaks protect --staged --verbose --redact   # doar modificările staged
gitleaks detect --source . -v                  # întreg istoricul git
```

## Decizii tehnice cheie

- **Nucleu execuție/risc/portofoliu:** NautilusTrader v1.231.0 (stabil) — nu v2 RC.
- **Alternativă crypto rapidă:** Freqtrade.
- **LLM local:** Qwen3-8B (4-bit) via Ollama — doar propuneri, fără drept de execuție.
- **Broker acțiuni (faza 1):** XTB, execuție manuală (API-ul XTB e dezactivat din martie 2025).
- **Exchange crypto:** Kraken Spot.
- **Robinhood:** nu se folosește în faza 1 (eligibilitate neconfirmată pentru cont din România).

Detalii complete și justificare: [`brief-proiect-agent-trading-local.md`](brief-proiect-agent-trading-local.md#5-decizia-tehnică-și-justificarea-ei).

## Reguli absolute (Fazele 0–4)

1. Nicio cheie/credențială de broker sau exchange **live** — doar date istorice, sandbox/replay, conturi paper/demo, `dry_run: true`.
2. Stratul LLM **nu are** acces direct sau indirect la plasarea de ordine.
3. Limitele de risc sunt definite în cod/config, validate la pornire — niciun output LLM nu le poate modifica.
4. Nimic nu trece din `dry_run`/paper în live automat.
5. Niciun secret în git.

Lista completă: [`CLAUDE-instructiuni-faza-0-4.md`](CLAUDE-instructiuni-faza-0-4.md#0-reguli-absolute--citește-înainte-de-orice-task).

## Structura de repository

Scaffolding-ul de mai jos există deja în repo (Faza 0); fișierele `.py`/`.yaml` din interior se adaugă pe măsură ce avansează Fazele 1–5.

```
trading-agent/
├── .env.example / .env.engine.example / .env.llm.example / .env.control.example
├── .gitignore / .pre-commit-config.yaml
├── pyproject.toml / uv.lock / requirements*.txt
├── apps/console/              # consolă Angular (operator), proxy către :8767
├── config/
│   ├── risk_limits.yaml       # limite deterministe, validate la pornire (Faza 3)
│   ├── universe.yaml          # allowlist de instrumente (Faza 2)
│   └── strategies.yaml        # enable/disable strategii (restart required)
├── src/
│   ├── data/                  # ingestie și validare date
│   ├── engine/                # integrare NautilusTrader
│   ├── risk/                  # risk_engine.py — sursa unică de adevăr pentru limite
│   ├── llm/                   # serviciu LLM izolat, doar propuneri
│   ├── research/              # context extern, metadata store
│   ├── execution/             # order gateway, idempotency, reconciliere
│   ├── monitor/               # monitor independent, kill switch
│   ├── audit/                 # bază de date append-only (SQLite/JSONL)
│   └── control/               # control plane FastAPI loopback (:8767)
├── backtests/reports/
├── tests/{unit,integration,adversarial}/
└── docs/qualification-report.md
```

Vezi [`CLAUDE-instructiuni-faza-0-4.md`](CLAUDE-instructiuni-faza-0-4.md#1-structura-recomandată-a-repository-ului) pentru task-urile (0–5) care populează această structură.

## Fazele proiectului

| Faza | Obiectiv | Gate |
|---|---|---|
| 0 — Cercetare/selectare | Decizie de arhitectură, licențe, buget | Document de decizie semnat de PO |
| 1 — Instalare/audit | Mediu izolat, dependențe fixate | Zero credențiale live |
| 2 — Reproducere | Reproducerea unui exemplu oficial de backtest | Rezultate reproductibile |
| 3 — Backtest realist | Costuri, slippage, walk-forward | Fără look-ahead bias nedetectat |
| 4 — Paper trading | Date live, cont simulat, ≥30 sesiuni | Zero incidente critice |
| 5 — Live minim | ≤50 EUR expuși | Doar după Gate Faza 4 complet |
| 6 — Automatizare graduală | Reducerea aprobării manuale | Pe bază de dovezi, nu de calendar |

Detalii complete: [`brief-proiect-agent-trading-local.md`](brief-proiect-agent-trading-local.md#8-faze-și-porți-de-decizie-gate-criteria).
