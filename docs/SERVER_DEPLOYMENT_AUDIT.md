# Server Deployment Audit

**Date:** 2026-09-20  
**Scope:** repository inspection only. No deployment, no live trades, no credential rotation, no code changes.  
**Sources:** implementation under `src/`, `scripts/`, `config/`, `.env*.example`, `apps/console/`, CI, and graphify graph (`graphify-out/`, built from commit `fe1a53a6`). Uncommitted discovery work (`src/discovery/`) exists on disk and is noted where relevant; it is not required for 24/7 paper.

---

# Executive Summary

This application **can run 24/7 on a remote Linux server together with Ollama on the same CPU-only machine**, but the repository is a **local loopback paper-trading stack**, not a packaged production service.

**Verdict: READY WITH INFRASTRUCTURE CHANGES.**

What already works for unattended paper:

- Multi-process design: isolated LLM HTTP process, control plane, paper stream, optional research and Kraken read-only monitor.
- Fail-closed LLM path: malformed, timed-out, or missing Ollama output becomes `RejectedProposal` and does not size or submit an order.
- Deterministic risk, file-based kill switch, SQLite audit log, idempotent `client_order_id` reservation, startup reconciliation.
- Secrets are gitignored; CI runs gitleaks; no wallets or blockchain keys.

What blocks calling this “production-ready”:

- No Docker, systemd, Procfile, or restart policy. The only launcher (`scripts/dev/start_stack.py`) **stops the entire stack if any child exits**.
- All HTTP servers **refuse non-loopback binds**. Remote access is not implemented; it must be Tailscale or SSH tunnel.
- Operator auth is **optional**. Empty `CONTROL_OPERATOR_TOKEN` means no Bearer check.
- The console is `ng serve` (Node). WebSocket URL hard-codes `127.0.0.1:8767` when the UI port is `4200`.
- Human approval **blocks the paper loop for up to 3600 seconds**. Unattended proposals time out; they are not auto-executed.
- Live Kraken placement exists as a library (`KrakenLiveBroker`) and is **not** the 24/7 agent path. `LIVE_TRADING_ENABLED=true` blocks paper start.

**GPU is not required.** The configured model is `qwen3:8b` Q4_K_M. Inference is about **one chat request per closed 1h bar**. CPU latency of 10–40s fits the 60s timeout and does not change trading outcomes vs GPU.

**Recommended hardware:** 8 dedicated vCPU, 32 GB RAM, 160–240 GB NVMe, no GPU, Ubuntu 24.04. Estimated **€25–70/month** for paper + local Ollama on an EU dedicated-CPU / high-memory VPS class.

---

# Current Architecture

## Languages, runtimes, package managers

| Layer | Actual |
|---|---|
| Python | **3.12 only** (`requires-python = "==3.12.*"` in `pyproject.toml`) |
| Python packages | **uv** (`uv.lock`; `[tool.uv] package = false` — no console_scripts) |
| Pinned deps | FastAPI 0.141.1, uvicorn 0.53.0, pydantic 2.13.5, httpx 0.28.1, nautilus_trader 1.231.0, feedparser, trafilatura, python-dotenv, pyyaml, websockets |
| Frontend | Angular 21 + PrimeNG 21, TypeScript ~5.9, **npm@11.9.0** |
| External runtime | **Ollama** (not in-repo) serving `qwen3:8b` |
| Not present | Dockerfile, compose, `.devcontainer`, Makefile, justfile, Procfile, systemd units, Redis, PostgreSQL, Celery, APScheduler |

NautilusTrader is a hard dependency and is used for **backtest / qualification**. The 24/7 paper path uses `SimulatedBroker`, not a Nautilus live node.

## Process map (what actually runs)

```
                    Operator (browser / SSH)
                              │
                              ▼
                    ┌─────────────────────┐
                    │ Angular ng serve    │  127.0.0.1:4200
                    │ proxy /v1 → :8767   │
                    └──────────┬──────────┘
                               │ REST + WebSocket
                               ▼
                    ┌─────────────────────┐
                    │ Control FastAPI     │  127.0.0.1:8767
                    │ src.control.server  │
                    └───┬─────────────┬───┘
                        │ spawn       │ health/analyze
          ┌─────────────┴──┐          │
          ▼                ▼          ▼
   Paper stream      Broker monitor   LLM FastAPI     Research FastAPI
   run_paper_        (optional,       127.0.0.1:8765  127.0.0.1:8766
   session.py        read-only)       src.llm.server  src.research.server
   --mode stream                      │
   --operator file                    ▼
          │                     Ollama 127.0.0.1:11434
          │                     qwen3:8b Q4_K_M
          ▼
   Kraken public OHLC REST
   SimulatedBroker + SQLite/JSON under runtime/
```

| Process | Entry | Bind | Role |
|---|---|---|---|
| LLM | `python -m src.llm.server` | `127.0.0.1:8765` | `POST /propose`, `POST /analyze`. Refuses broker env vars at boot. |
| Research | `python -m src.research.server` | `127.0.0.1:8766` | `GET /context`. Optional; skipped without `.env.research`. |
| Control | `python -m src.control.server` | `127.0.0.1:8767` | Operator API, `/v1/ws/events`, agent start/stop, approvals, halt. |
| Console | `npm start` → `ng serve --host 127.0.0.1 --port 4200` | `127.0.0.1:4200` | Dev UI. Node required on this path. |
| Paper | `scripts/paper_trading/run_paper_session.py --operator file --mode stream` | none | Poll Kraken public OHLC every 30s; one session per **closed 1h bar**. |
| Monitor | `scripts/monitor/run_broker_monitor.py` | none | Optional. Balance/OpenOrders if spot keys exist and withdraw is disabled. |
| Ollama | external binary | `127.0.0.1:11434` | Local LLM. |

Launcher: `scripts/dev/start_stack.py`. It starts LLM, optional research, control, console, then `POST /v1/agent/start`. If any HTTP child exits, it raises `SystemExit` and tears the stack down (`start_stack.py` around L326–336). **This is a development supervisor, not a 24/7 unit.**

## Entry points (no installable package)

There is no `[project.scripts]`. Runtime is `python -m …` or `scripts/`.

Long-running:

- `src.llm.server`, `src.research.server`, `src.control.server` (uvicorn)
- `scripts/paper_trading/run_paper_session.py --mode stream`
- `scripts/monitor/run_broker_monitor.py`

One-shot (need external cron if freshness matters):

- `scripts/research/ingest_once.py`
- `scripts/discovery/run_daily_discovery.py` (uncommitted at audit time)
- `scripts/backtest/run_backtest.py`
- `scripts/paper_trading/approve.py`

## Data / APIs

| Direction | What |
|---|---|
| Market data (paper) | Kraken **public** OHLC REST (`src/data/kraken.py`). No market WebSocket. |
| Historical / backtest | Binance public klines (`BinanceKlinesSource`). Not live execution. |
| Execution (paper 24/7) | `SimulatedBroker` only. `dry_run: true` is mandatory (`config/paper_trading.yaml`). |
| Execution (library, unused by agent start) | `KrakenLiveBroker` REST AddOrder/CancelAll (`src/execution/kraken_live.py`). |
| Research | FRED / ALFRED / SEC EDGAR / BLS / BEA + RSS (`config/research_sources.yaml`). httpx + feedparser. **No Playwright/Selenium.** |
| LLM | Engine → `:8765` → Ollama `/api/chat`. Backtest may use `--direct-ollama`. |

## Bind and isolation (design, not accidental)

```18:21:src/control/settings.py
def validate_bind_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"control server must bind to loopback, not {host!r}")
    return host
```

The same loopback check exists in `src/llm/server.py` and `src/research/server.py`. Putting `0.0.0.0` in env **refuses to start**. Docker multi-container networking therefore needs host network, a single shared-localhost container, or a later code change.

The LLM process strips/rejects broker keys (`assert_no_broker_keys`). Paper children are spawned with `paper_child_env()` which removes Kraken trading secrets (`src/execution/key_policy.py`).

---

# Server Deployment Feasibility

## Primary question

**Can this application run 24/7 on a remote server without the developer laptop remaining online?**

**Yes, for paper trading, after infrastructure packaging.**  
**No, for live trading, as currently wired.**

## Verdict

**READY WITH INFRASTRUCTURE CHANGES**

Not READY: missing supervisor, remote-access path, production console serving, restart/health completeness.  
Not NOT READY: the paper loop, persistence, fail-closed LLM, and kill switch are real and tested.  
Not “minor changes”: Docker/systemd, Tailscale, static UI, and child auto-restart are operations work plus a few code gaps.

## Evidence

| Claim | Evidence |
|---|---|
| Designed as local loopback | `validate_bind_host` in control/LLM/research; `.env.*.example` hosts are `127.0.0.1`; `docs/utilizare.md` documents local-only ports |
| Long-running paper loop exists | `PaperTradingLoop.run_stream` infinite poll until SIGTERM/halt (`src/engine/strategy_paper.py`) |
| State survives process restart (paper) | `restore_persisted_state()` + `reconcile_startup()`; tests in `tests/integration/test_paper_resilience.py` |
| No production supervisor | No systemd/Docker; `start_stack.py` exits if a child dies; `SubprocessAgentProcess` has **no auto-restart** if paper later dies |
| Live path blocked | `LIVE_TRADING_ENABLED` → `start_stack.assert_paper_start_allowed`; control `POST /v1/agent/start` returns 403 “live start is blocked” |
| Human-in-the-loop | Agent start uses `--operator file`; `ApprovalGate` waits up to `approval_timeout_s: 3600` |
| Python 3.12 + uv + Node (if UI) | `pyproject.toml`, `apps/console/package.json` |
| Ollama is assumed local | `OLLAMA_HOST=http://127.0.0.1:11434`; `start_stack.py` pings that URL |

## What “24/7” means for this repo

The engine can poll Kraken public OHLC, request an LLM proposal on each closed 1h candle, run `RiskEngine`, and **wait for a human** (dashboard or `scripts/paper_trading/approve.py`). If nobody approves within one hour, the order is rejected with `approval_timeout`. That is intentional safety, not a missing feature.

The laptop does **not** need to stay online once the server is up. The **operator** still needs a way to reach the dashboard (Tailscale/SSH) to approve, halt, or restart.

---

# Ollama Analysis

## How Ollama is used

```
Paper / backtest          Isolated LLM process              Ollama
LLMProposalClient  -->    POST /propose  -->  generate_proposal()
                          httpx POST {OLLAMA_HOST}/api/chat
                          stream=false, think=false,
                          format=<LLMProposal JSON schema>,
                          temperature=0
```

Operator research uses `LLMAnalysisClient` → `POST /analyze` → same Ollama model. Analyses are **not** order signals (`normalize_analysis` returns `None` at Level 1).

## Model

| Item | Value | Source |
|---|---|---|
| Name | `qwen3:8b` | `.env.llm.example` `LLM_MODEL_NAME`; `src/llm/service.py` `load_llm_settings()` |
| Quantization | Official Ollama tag is **Q4_K_M** (comment in `.env.llm.example`; confirmed in `docs/backtest-report.md`) | env comment, not an API field |
| Size on disk | ~5.2 GB | Ollama library for `qwen3:8b` |
| Alternate models | None in YAML. Single env var. | — |
| Embeddings | Not used | no embedding deps or calls |
| Tool / function calling | Forbidden in prompts; not sent to Ollama | `src/llm/service.py`, `src/llm/analysis_prompts.py` |
| Streaming | Disabled (`stream: False`) | `generate_proposal` / `generate_analysis` |
| Context window | **Not set** (`num_ctx` absent). Ollama model default applies (Qwen3-8B native 32K). | `src/llm/service.py` payload |

## Endpoint

| Hop | Default | Configurable |
|---|---|---|
| LLM → Ollama | `http://127.0.0.1:11434/api/chat` | `OLLAMA_HOST` |
| Engine → LLM server | `http://127.0.0.1:8765/propose` | paper CLI `--llm-url`; control health uses `LLM_SERVICE_URL` |
| LLM bind | `127.0.0.1:8765` | `LLM_SERVER_HOST` / `LLM_SERVER_PORT`, loopback only |
| Stack launcher Ollama check | hardcoded `http://127.0.0.1:11434` | `scripts/dev/start_stack.py` |

`agent_process.py` does **not** pass `--llm-url`. Paper therefore always defaults to `http://127.0.0.1:8765` unless started by hand. `LLM_SERVICE_TIMEOUT_SECONDS` in `.env.engine.example` is **unused**.

## Frequency and concurrency

- Paper timeframe: `1h` (`config/paper_trading.yaml`).
- Poll: 30s. LLM is **not** called every poll — only when a **new closed bar** advances the session (`strategy_paper.py`).
- Lookback: 20 bars before the first proposal.
- If `llm_assisted.enabled: true` (current `config/strategies.yaml`), agent start **does not** pass `--skip-llm`.
- Operator analyze: one `/analyze` per UI/API request.
- Concurrency: single uvicorn process, no workers; sequential `request_proposal`. One model loaded. Expected concurrent Ollama load: **1**, rarely 2 if an operator analyze overlaps a bar.

## Timeouts and retries

| Layer | Timeout | On failure | Retries |
|---|---|---|---|
| Ollama in `service.py` | `LLM_TIMEOUT_SECONDS` default **60** | `RejectedProposal(reason="timeout"\|"model_error")` | **None** |
| `LLMProposalClient` default | 30s | same reject | none |
| Paper/backtest client | **120s** hardcoded | same | none |
| `LLMAnalysisClient` | 60s | `RejectedAnalysis` | none |
| Control health ping | 1.5s GET to `LLM_SERVICE_URL` | `llm="down"` alert | none |

Invalid JSON / extra fields (`extra="forbid"`) / universe mismatch → reject. Think-block stripping does **not** repair JSON.

## Can Ollama run on the same server without architectural changes?

**Yes**, if both bind to localhost on that host — which is exactly what the code assumes. No GPU library, CUDA flag, or remote inference client exists.

A **Docker Compose split** of `trading-agent` vs `ollama` **does** need an architectural accommodation because LLM/control bind `127.0.0.1` (sibling containers cannot connect) and `OLLAMA_HOST` defaults to loopback. Host network, a single container, or a later bind-host change would be required. Native systemd on one Linux host does **not**.

---

# Model Hardware Requirements

Estimates for **the actual model this repo uses**: Ollama `qwen3:8b` Q4_K_M. Application code does not pin `num_ctx`; budget the Ollama default (up to 32K). Proposals are short JSON, so practical KV cache is far below 32K if Ollama’s loaded context is reduced later.

| Resource | Estimate | Why |
|---|---|---|
| Disk (weights) | ~5.2 GB | Ollama `qwen3:8b` blob |
| RAM (CPU inference, model loaded) | **8–12 GB** | ~5 GB weights + KV + llama.cpp overhead. 32K context can approach ~11 GB |
| VRAM (GPU, 4k–8k ctx) | **6–8 GB** | ~6.5 GB typical Q4_K_M + short context |
| App processes (control+llm+research+paper) | **0.5–1.5 GB** | FastAPI + httpx + SQLite; Nautilus not in the paper hot path |
| `ng serve` (if used) | **0.5–1.5 GB** | should not be used in production |
| OS + headroom | **2–4 GB** | — |
| CPU during inference | **4–8 cores** useful | one burst per hour |
| CPU idle (poll loop) | **<1 core** | 30s sleep |

Startup/load: first `ollama pull` is minutes on a typical VPS NIC; later process start loads weights from NVMe in tens of seconds. Keep the Ollama daemon up so the model stays resident.

Tokens/sec (order of magnitude, 8B Q4):

- Modern 8-core dedicated CPU (AVX2/AVX-512): **~15–30 tok/s**
- Consumer GPU (8–12 GB, e.g. RTX 3060 class): **~50–80+ tok/s**

A constrained JSON proposal is typically a few hundred tokens. **CPU: ~10–40 s. GPU: ~1–5 s.** Timeout is 60 s at Ollama, 120 s at the paper client. CPU fits.

---

# CPU vs GPU

## Can this trading agent realistically operate using Ollama on CPU only?

**Yes.**

The trading loop’s LLM cadence is **hourly**, not tick-by-tick. Human approval can wait **up to one hour**. GPU would shorten inference from tens of seconds to a few seconds. That does **not** change:

- when a 1h bar closes,
- when `RiskEngine` sizes,
- when an operator approves,
- whether a malformed model output can trade (it cannot).

GPU would matter if you later: switch to sub-minute bars, keep a much larger model loaded, raise `num_ctx` to 32K+ with heavy prompts, or serve multiple concurrent operators with overlapping `/analyze` and `/propose`. **None of that is the current workload.**

Paying for a GPU server for this repository’s 1h paper loop is **waste**. Use the money for RAM, dedicated CPU, disk, and backups.

---

# Server Sizing

No PostgreSQL, Redis, or message broker is justified by the code. Persistence is SQLite + JSON files.

OS: **Ubuntu 24.04 LTS** (matches CI Python 3.12 / Linux; Ollama’s Linux install path). Docker is optional (see Docker section).

## MINIMUM

| Item | Spec |
|---|---|
| Type | High-memory VPS (shared vCPU acceptable for a trial) |
| vCPU | 4 |
| RAM | **16 GB** (tight: 8–12 GB model + OS + Python) |
| SSD | 80 GB NVMe |
| GPU | **None** |
| Network | 1 Gbps; a few MB/h to Kraken public OHLC + optional research APIs |
| Notes | Do not run `ng serve`. Disable LLM strategy or expect swap risk while the model loads. Suitable for **development / short paper tests**, not comfortable 24/7. |

## RECOMMENDED

| Item | Spec |
|---|---|
| Type | **Dedicated-CPU VPS / high-memory cloud** (search: 8 vCPU dedicated, 32 GB RAM) |
| vCPU | **8 dedicated** |
| RAM | **32 GB** |
| SSD | **160–240 GB NVMe** |
| GPU | **None** |
| Network | Public egress to Kraken (and research APIs if enabled). No inbound except SSH/Tailscale |
| Docker | Optional; systemd on the host is the smaller change |
| Notes | Model stays resident; paper + control + LLM + Ollama coexist. This is the default buy. |

Comparable search class (use the spec, not the brand): Hetzner **CCX33**-class (8 dedicated / 32 GB / ~240 GB) or cheaper shared **CX53**-class (16 shared / 32 GB / 320 GB) if noisy-neighbor CPU is acceptable.

## PRODUCTION / PERFORMANCE

| Item | Spec |
|---|---|
| Type | Dedicated-CPU VPS or small dedicated server |
| vCPU | 8–16 dedicated |
| RAM | 32–64 GB |
| SSD | 240 GB+ NVMe (logs, audit SQLite, research payloads) |
| GPU | Still **not required** for `qwen3:8b` hourly. Add **≥8 GB VRAM** only if the model or cadence changes |
| Network | Same as recommended; IP whitelist on Kraken keys if live is ever enabled |
| Notes | Extra RAM is for headroom and snapshot backups, not inference quality. Extra CPU helps the hourly burst and keeps p99 under the 60s timeout. |

---

# Same Server vs Separate Ollama Server

## OPTION A — Trading Agent + Ollama on one server (recommended)

| Axis | Assessment |
|---|---|
| Monthly cost | **Lowest** for this workload (~€25–70) |
| Latency | Loopback; 10–40s is model time, not network |
| Security | Ollama stays on `127.0.0.1:11434`; never published |
| Privacy | Prompts and market summaries never leave the box |
| Reliability | One machine is a single point of failure; acceptable for paper. Mitigate with backups + restart policies |
| Scalability | Irrelevant at 1 req/h |
| Maintenance | One OS, one Ollama, one Python stack |
| Network dependency | Only market/research egress |

This matches the code’s assumption (`127.0.0.1` everywhere).

## OPTION B — App server + Ollama server

| Axis | Assessment |
|---|---|
| Monthly cost | Roughly **2×** plus private networking |
| Latency | Fine on a VPC; still dominated by generation time |
| Security | Must **not** expose 11434 to the internet. Private VLAN / Tailscale only. LLM bind lock still assumes localhost unless code changes |
| Reliability | Ollama outage is isolated, but the agent already fail-closes; extra host is extra ops |
| Scalability | Only useful if you later run large models or many concurrent chats |

**Not justified** for `qwen3:8b` hourly.

## OPTION C — VPS + cloud inference API

| Axis | Assessment |
|---|---|
| Monthly cost | App VPS cheap; inference billed per token. At 1 call/h this is small money and large architecture change |
| Latency | Often faster than CPU Ollama |
| Security / privacy | Market context and prompts leave the host. Conflicts with LLM process isolation (`.env.llm` has no broker keys **because** inference is local) |
| Reliability | Depends on vendor uptime and your API key |
| Code | Would replace `src/llm/service.py` Ollama `/api/chat` with another client |

Use only as a **fallback** if local Ollama ops become the bottleneck — not as the default.

## Recommendation for THIS project

**OPTION A.** Same Linux server, CPU Ollama, loopback only, Tailscale for the operator.

---

# Docker Readiness

## Current state

| Artifact | Status |
|---|---|
| `Dockerfile` | **Absent** |
| `docker-compose.yml` / `compose.yml` | **Absent** |
| `.devcontainer` | **Absent** |
| Production image, healthchecks, restart policies | **Absent** |

Docker is **not** production-ready because it does not exist.

## Proposed architecture (do not implement in this phase)

Do **not** introduce PostgreSQL or Redis. They are unused.

Preferred **first** production packaging: **systemd units on the host** (smallest delta vs loopback binds).

If Docker is desired later, two viable shapes:

### Shape 1 — host network (least code change)

Linux `network_mode: host` so `127.0.0.1:8765/8766/8767/11434` keep working. Publish **no** ports on the public interface; firewall + Tailscale still apply.

### Shape 2 — private compose network (needs a bind-host change)

Conceptual compose (services that actually exist):

```yaml
# CONCEPT ONLY — not in the repo
services:
  ollama:
    image: ollama/ollama
    volumes:
      - ollama_models:/root/.ollama
    # do NOT publish 11434 to 0.0.0.0
    restart: unless-stopped

  llm:
    build: .
    command: python -m src.llm.server
    env_file: .env.llm
    environment:
      OLLAMA_HOST: http://ollama:11434
      # LLM_SERVER_HOST cannot be 0.0.0.0 today — code rejects it
    depends_on: [ollama]
    restart: unless-stopped

  research:
    build: .
    command: python -m src.research.server
    env_file: .env.research
    restart: unless-stopped
    profiles: ["research"]

  control:
    build: .
    command: python -m src.control.server
    env_file: [.env.control, .env.engine]
    volumes:
      - runtime_data:/app/runtime
      - research_data:/app/data/research
    restart: unless-stopped
    # paper child is spawned by control (agent_process.py)

  # optional static UI — not ng serve
  console:
    image: nginx:alpine
    volumes:
      - ./apps/console/dist:/usr/share/nginx/html:ro
    # listen on Tailscale IP only, or not at all (SSH tunnel)

volumes:
  ollama_models:
  runtime_data:
  research_data:
```

**Blocker for Shape 2:** `validate_bind_host` rejects anything except loopback. `OLLAMA_HOST=http://127.0.0.1:11434` will not reach a sibling container. Isolation rule still applies: the `llm` container must never receive `.env.engine` broker keys.

Paper remains a **child of control** (`SubprocessAgentProcess`). In Compose, that child must share the control container’s filesystem (`runtime/`) and localhost LLM URL, or paper becomes its own service (code change).

---

# Persistence

## What must survive restarts

| Data | Default path | Mechanism |
|---|---|---|
| Audit trail | `runtime/.../audit/audit.sqlite` | SQLite WAL, append-only `INSERT` (`src/audit/audit_log.py`) |
| Order idempotency | `runtime/.../execution/idempotency.sqlite` | `reserve` then `UPDATE result_json` |
| Halt / kill switch | `runtime/.../control/halt.flag` | atomic JSON write |
| Heartbeat | `runtime/.../heartbeat/paper-engine.json` | rewritten every poll |
| Last bar | `runtime/.../control/last_bar.json` | JSON |
| Local positions | `runtime/.../control/local_positions.json` | JSON |
| Simulated broker | `runtime/.../control/simulated_broker.json` | paper snapshot |
| Portfolio tracker | `runtime/.../control/paper_tracker.json` | JSON |
| Reconciliation | `runtime/.../control/reconciliation.json` | JSON |
| Approvals | `runtime/.../control/approvals/*.json` | request + decision files |
| PIDs | `agent.pid`, `broker_monitor.pid` | stale if unclean death; health uses `pid_is_alive` |
| Child logs | `runtime/logs/paper.log`, `monitor.log` | stdout capture |
| Research metadata | `data/research/metadata.db` | SQLite upsert |
| Research blobs | `data/research/` | files |
| Discovery (if used) | `data/discovery/YYYY-MM-DD.jsonl` | append-only JSONL |
| Market cache | `.cache/` | gitignored; rebuildable |
| Config | `config/*.yaml` | git |
| Secrets | `.env.llm`, `.env.engine`, `.env.control`, `.env.research` | gitignored |
| Ollama weights | `/usr/share/ollama/.ollama` or `~/.ollama` (or Docker volume) | must be a persistent volume |

`runtime/` and `data/research/` are gitignored. A server without a mounted volume **loses trading state on recreate**.

## Crash / reboot matrix

| Event | Kept | Lost / reset |
|---|---|---|
| Paper process crash | SQLite, JSON snapshots, halt flag, approvals | In-memory bar history (`_history`); circuit-breaker consecutive counters; in-flight HTTP; LLM call in progress |
| Docker/container restart (if volumes mounted) | Same as disk | Same ephemeral state; Ollama model **stays** if volume persists |
| Host reboot | Disk as above | All processes dead until systemd/Docker restart them (**not configured today**) |
| Power loss | WAL SQLite may need recovery; last un-fsynced JSON write could be truncated (writes use temp+`os.replace` in `src/runtime_io.py`) | Same as reboot |

On stream restart, `restore_persisted_state()` reloads tracker / SimulatedBroker / in-flight IDs, then `reconcile_startup()`. Bar history is **re-seeded from the next poll**, not from disk.

## Ollama model persistence

The server **must not** download `qwen3:8b` on every restart.

Correct strategy:

1. Store Ollama data on a **named volume or host bind** (`/root/.ollama` in the official image; `/usr/share/ollama/.ollama` for systemd `ollama.service`).
2. `ollama pull qwen3:8b` **once** (or a oneshot unit that pulls if missing).
3. `Restart=always` on the Ollama daemon so weights stay mapped.
4. Do not bake the 5 GB blob into a CI image unless you want huge images; pulling once onto the volume is enough.
5. Remote backup of weights is optional — they are reproducible from the Ollama library.

---

# 24/7 Reliability

## Designed for continuous paper?

**Partially.** `run_stream` is an infinite loop with halt/SIGTERM. Control can start/stop it. There is **no** supervisor to bring HTTP processes or a dead paper child back.

## Issue register

| Issue | Severity | Evidence | Effect |
|---|---|---|---|
| No systemd/Docker restart; `start_stack` kills stack on child exit | **CRITICAL** | `start_stack.py` L326–330; no unit files | Host reboot or crash = downtime until a human SSH’s in |
| `SubprocessAgentProcess` does not restart paper if it dies later | **CRITICAL** | `src/control/agent_process.py` start/stop only | Silent stop of trading loop; control may still be “up” until PID check |
| `run_bar` has no try/except; any exception kills the process | **HIGH** | `run_stream` only wraps `poll_bars` | One audit I/O or approval parse error ends the session |
| Optional operator token (empty = no auth) | **CRITICAL** if any port is reachable beyond loopback | `server.py` `require_auth` L154–159 | Halt, approve, start/stop without credentials |
| Approval wait blocks the entire stream up to 3600s | **HIGH** | `ApprovalGate.request`; poll 0.05s | Next 1h bar delayed; heartbeat can look stale while waiting |
| Heartbeat threshold loaded but not auto-HALT | **MEDIUM** | `heartbeat_threshold_s: 30` in YAML; `Watchdog` does not use `Heartbeat.is_stale` | Health shows age; process can be wedged without halt |
| No REST retry/backoff on Kraken or Ollama | **MEDIUM** | `kraken_live.py` 15s timeout; LLM no retries | Transient blips become rejects/timeouts (fail-closed — safe, noisy) |
| Crash between `reserve` and `store_result` | **HIGH** for live; **LOW** for paper SimulatedBroker | `order_gateway.py` L15–28 | `duplicate_in_flight` without querying the exchange |
| Circuit-breaker counters are process-local | **MEDIUM** | `src/risk/circuit_breaker.py` | Restart resets consecutive error/loss counts; halt **file** survives |
| Research ingest / discovery are one-shot | **LOW** (paper) | `ingest_once.py`, `run_daily_discovery.py` | Stale research context until cron exists |
| No market WebSocket; REST poll only | **LOW** | `src/data/kraken.py` | Fine for 1h bars; no reconnect logic needed |
| Console WS reconnects with backoff | **LOW** | `agent-state.service.ts` 1s→10s | UI only |
| Control WS has no server-side client reconnect | N/A | server push every 2s | Client handles it |
| Duplicate `client_order_id` replay | Mitigated | UUID per order + IdempotencyStore | Same ID will not double-submit |
| New bar after restart can emit a **new** order UUID for the same thesis | **MEDIUM** (product) | new `uuid4()` per approved decision | Not a replay of the old ID; strategy can re-signal |
| `LIVE_TRADING_ENABLED` blocks the only 24/7 start path | **CRITICAL** for live | control 403; start_stack SystemExit | Live 24/7 is not an operations toggle; it is unbuilt |

## Duplicate trades / lost signals / bad position state

**Paper (current 24/7 path):** SimulatedBroker snapshot + idempotency + startup recon make duplicate simulated fills unlikely. Lost signals: if the process is down across a bar close, that bar may be skipped or processed late depending on `poll_bars` / `last_ts`. Incorrect paper position: recon mismatch triggers halt-and-flatten (`PeriodicReconciler`).

**Live (library only):** timeout stores an open ID and can halt (`halt_on_unknown_order_result: true`). Crash after Kraken Accept before `store_result` does **not** confirm via QueryOrders. **Do not enable live until that window is closed.**

---

# Failure Scenarios

## Ollama crashes or is unreachable

The trading agent does **not** crash. `generate_proposal` catches `httpx.TimeoutException` / `HTTPError` and returns `RejectedProposal`. Paper audits `rejected_proposal` and **does not** call `RiskEngine` / submit (`strategy_paper.py` L341–360). There is **no** automatic fallback to EMA unless the agent was started with `--skip-llm` or `llm_assisted` is disabled **and the agent is restarted**.

There is **no retry**. Fail-closed is the correct trading bias.

| Outage | Likely behavior |
|---|---|
| Ollama down 30s | If a bar closes during the outage: one `timeout` or `model_error` reject. Next hour retries. Stream keeps polling. |
| Ollama down 10 min | Same; up to one missed LLM proposal. No unsafe order. |
| Model loading slowly (>60s) | Ollama call times out → reject. Paper client allows 120s so the LLM server may wait the full 60s then return reject. |
| Inference timeout | `reason="timeout"`, no order. |
| Malformed LLM JSON / extra fields | `schema_invalid` / validation error → reject. `extra="forbid"` on pydantic models. |
| Hallucinated instrument | `instrument_not_in_universe` after schema validation against `config/universe.yaml`. |
| Hallucinated size/price | **Not in the proposal schema.** LLM may only return instrument, direction, confidence, rationale. `RiskEngine` alone computes quantity. `confidence` is not used for sizing. |
| LLM process down, Ollama up | Engine `LLMProposalClient` HTTP error → reject. Control health marks `llm=down` (ping treats HTTP <500 as up; FastAPI `/` 404 still counts as up — **weak health**). |

A trading system must never execute because the model “said so.” This repo already routes authority through schema → universe → risk → human approval → gateway. **That part is sound.** The gap is operational: prolonged Ollama downtime is silent missed signals, not a page, unless you add monitoring.

## Other failures

| Scenario | Behavior |
|---|---|
| Control process dies | Paper child may keep running (`start_new_session=True`) until something SIGTERMs it. UI gone. No auto-restart. |
| Paper dies, control lives | PID check → agent not running. No respawn. |
| Kraken public OHLC error | `poll_bars` exception swallowed; sleep 30s; continue. |
| Halt flag set | Loop stops new orders; reset is **manual** (`POST /v1/risk/halt/reset` or Risk page). |
| Disk full | SQLite/JSON writes fail → `run_bar` can kill the process (**HIGH**). |

---

# Security Audit

Deployment-focused. **No secret values are reproduced.**

## Secrets handling

| Item | Location | Risk |
|---|---|---|
| Real `.env.control`, `.env.engine`, `.env.llm`, `.env.research` | Working tree, **gitignored** (`.gitignore` L1–8) | Fine locally; on a server they must be `0600`, not in images, not in logs |
| Templates | `.env.example`, `.env.*.example` | Key **names** only |
| `config/*.yaml` | repo | No API key fields found |
| CI | `.github/workflows/ci.yml` job `secrets-scan` (gitleaks, full history) | Good |
| Pre-commit | `.pre-commit-config.yaml` `gitleaks protect --staged` | Good |
| Wallets / mnemonics | **None** in `src/` | N/A |
| Exchange keys | Env names `KRAKEN_SPOT_API_*`, `BROKER_API_*` | Paper start **strips** them from the paper child. Monitor may keep spot keys if withdraw disabled |
| Operator token | `CONTROL_OPERATOR_TOKEN` | Empty in the example → **auth off** |
| Research keys | `FRED_API_KEY`, `BLS_API_KEY`, `BEA_API_KEY` | Optional; not in YAML |
| Docker socket | Not used | If you later mount `/var/run/docker.sock` into a container, that is root-equivalent — do not |

## Logging of secrets

`redact_secrets()` is used for control security settings payload, broker monitor errors, and Kraken HTTP error reasons (`src/execution/key_policy.py`). Child `paper.log` is raw stdout — keep log level from dumping env. Do not enable debug httpx tracing in production.

## Auth / CORS / debug

- CORS default: `http://127.0.0.1:4200,http://localhost:4200`.
- Mutations need `Idempotency-Key` + role `operator`.
- FastAPI LLM app sets `docs_url=None`, `redoc_url=None`.
- Control still exposes a full operator API on loopback, including halt and approve.
- WebSocket `/v1/ws/events` accepts optional `?token=`.

## Open ports in development (must not be copied to production)

8765, 8766, 8767, 4200, 11434 — all intended as **localhost only**. Publishing them on a public VPS IP without Tailscale + token is a **CRITICAL** misconfiguration.

---

# Network Architecture

## Ollama must not be public

Port **11434 does not need to be reachable from the Internet.** The only client is the LLM process on the same host (or the same Docker network).

Preferred:

```
Internet ──(none)──► 11434

Operator ──Tailscale/SSH──► Linux host
                              │
                              ├── control :8767  (localhost or Tailscale ACL)
                              ├── llm     :8765  (localhost)
                              ├── research:8766  (localhost)
                              └── ollama  :11434 (localhost)
                                    ▲
                                    └── llm process only
```

Reject:

```
Internet ──► :11434 ──► Ollama
```

Ollama has no application auth in the default install. Public 11434 is unauthenticated GPU/CPU theft and prompt injection into a trading-adjacent model.

## Remote administration (recommended)

| Method | Use |
|---|---|
| **Tailscale** (or Headscale) | Primary. Operator laptop/phone on the tailnet reaches the dashboard without public HTTP. |
| **SSH** (key-only, optionally via Tailscale) | Admin, logs, `systemctl`, approvals CLI. Disable password auth. |
| Cloudflare Tunnel | Possible for HTTPS dashboard **after** token + TLS + WS host fix. Extra attack surface; not needed if Tailscale works. |
| Public reverse proxy to `:8767` / `:4200` | **Do not**, until: non-empty `CONTROL_OPERATOR_TOKEN`, TLS, CORS locked, WS URL not hardcoded to `127.0.0.1:8767`. |
| VPN (WireGuard) | Equivalent to Tailscale if you already operate one. |

### Dashboard access

Today the UI is `ng serve` on `127.0.0.1:4200`. For a server:

1. SSH tunnel: `ssh -L 4200:127.0.0.1:4200 -L 8767:127.0.0.1:8767 user@host` then use the laptop browser (works with current WS hardcode on port 4200).
2. Tailscale + later: nginx serving `apps/console/dist` on the tailnet IP, API+WS same origin (requires the WS host fix in `agent-state.service.ts`).

## Firewall (minimum policy)

Assume nftables/ufw on the VPS. Default deny incoming.

| Port | Exposure |
|---|---|
| UDP/41641 (Tailscale) or whatever the overlay needs | PRIVATE (tailnet) |
| TCP 22 | PRIVATE: admin IP / Tailscale only. **Not** `0.0.0.0/0` if Tailscale SSH is available |
| TCP 80/443 | **Closed** unless you later add a locked tunnel |
| TCP 8765 LLM | **LOCALHOST ONLY** |
| TCP 8766 research | **LOCALHOST ONLY** |
| TCP 8767 control | LOCALHOST or Tailscale interface only |
| TCP 4200 console | LOCALHOST or Tailscale; better: replace with nginx on Tailscale |
| TCP 11434 Ollama | **LOCALHOST ONLY** |
| Egress 443 | PUBLIC to Kraken, Ollama registry (first pull), research APIs, Ubuntu updates |

**PUBLIC inbound: none required** for paper 24/7. Market data is egress.

---

# Monitoring

## Health that exists today

| Check | Where | Gap |
|---|---|---|
| `GET /v1/health` | Control (`build_health`) | Agent PID, halt, venue age, LLM/research ping, recon, broker monitor |
| LLM `/health` | **Missing** | Control pings service **root**; HTTP <500 counts as up (a 404 is “up”) |
| Research `/health` | **Missing** | Same |
| Ollama | `start_stack` warning only | Not in `/v1/health` |
| Heartbeat age | Reported | Not an auto-halt |
| Last successful bar | `last_bar.json` | Stale check in Watchdog for data age (`stale_data_threshold_s: 10800`) |

## Proposed lightweight checks (single server)

Avoid Prometheus+Grafana+Loki unless you already run them. For one box:

1. **systemd** `Restart=on-failure` + `systemctl is-active` for `ollama`, `trading-llm`, `trading-control`, `trading-research`.
2. Cron or a 1-minute script:
   - `curl -fsS -H "Authorization: Bearer …" http://127.0.0.1:8767/v1/health`
   - `curl -fsS http://127.0.0.1:11434/api/tags` and assert `qwen3:8b` is present
   - `curl -fsS http://127.0.0.1:8765/propose` is **not** a health check (it would call the model). Add a real `/health` later.
3. Disk: alert if `runtime/` filesystem > 80%.
4. Optional: `node_exporter` + a cheap Grafana Cloud / Netdata / Beszel / Uptime Kuma on Tailscale — CPU, RAM, disk, container/process alive. GPU exporter only if a GPU exists.
5. Alerting: email/Telegram when health `agent != running`, `llm == down`, halt active unexpectedly, or disk full.

Useful fields already in `HealthResponse` (console `models.ts` / control models): agent status, venue, heartbeat age, halt reason, llm/research flags.

---

# Logging

## What exists

Per `correlation_id`, paper records (`src/audit/events.py`):

`proposal` → `risk_decision` → `human_approval` → `order_submitted` → `fill`  
plus `rejected_proposal`, `halt`, `reconciliation_*`, `operator_action`, `analysis`.

That is enough to reconstruct **most** of: why a trade was considered, what the LLM returned (payload), what risk decided, whether a human approved, and the simulated fill.

## Gaps for production reconstruction

| Gap | Severity |
|---|---|
| Child `paper.log` is unstructured stdout, not tied to `correlation_id` | MEDIUM |
| Research context that influenced a proposal is **not** attached to the same audit event | MEDIUM |
| LLM raw Ollama HTTP body is only stored when parsing fails (`raw_output` on rejects) | LOW |
| No log rotation/config in-repo | MEDIUM |
| `LOG_LEVEL` in env examples; no centralized JSON logging | LOW |

Do not log: private keys, `CONTROL_OPERATOR_TOKEN`, Kraken secrets, Authorization headers. `redact_secrets` is a start; keep httpx debug off.

---

# Backup Strategy

## What to back up

| Asset | Backup? | Frequency / retention |
|---|---|---|
| `runtime/` (audit DB, idempotency, halt, positions, approvals, logs) | **Yes — primary** | Daily encrypted; 14–30 days. Before any live experiment: extra snapshot |
| `config/` | Yes (also in git) | On change; keep last 10 |
| `.env.*` (not examples) | **Yes, encrypted, off-box** | On change. Treat as secrets backup |
| `data/research/` | Yes if you rely on ingest history | Weekly + 30 days |
| `data/discovery/` | Optional | Weekly |
| Ollama models | **No remote backup required** | Re-`pull` `qwen3:8b` |
| `.cache/` | No | Rebuildable |
| `apps/console/node_modules` | No | `npm ci` |

## How

- `restic` or `age`/`gpg` encrypted tarball to object storage (Hetzner Storage Box, S3-compatible, Backblaze) over Tailscale or SSH.
- SQLite: `sqlite3 audit.sqlite ".backup /tmp/audit.sqlite"` then restic (safe with WAL).
- Permissions: backup key on the server with read to `runtime/` + env files; restore key offline.
- Restore drill: empty VM → restore `runtime/` + env + config → start processes → confirm `/v1/health` and last audit `correlation_id`.

Encryption: restic password or age identity. Do not push plaintext `.env.engine` to a bucket.

---

# Estimated Infrastructure Cost

Prices are **order-of-magnitude 2026 EU VPS class** so you can compare Hetzner / OVHcloud / Contabo / Scaleway / Vultr / DigitalOcean / AWS / RunPod. Verify the live catalog; do not treat a brand as a recommendation.

## By operating mode

| Mode | Hardware class | Why | Monthly (infra only) |
|---|---|---|---|
| DEVELOPMENT / TESTING | 4 vCPU, 8–16 GB, 80 GB, no GPU. Stop Ollama when idle | App tests; `pytest` does not need the model except `llm_live` | **€5–20** |
| PAPER TRADING 24/7 | **8 dedicated vCPU, 32 GB, 160–240 GB, CPU Ollama** | Model resident; hourly inference | **€25–70** |
| LOW-VOLUME LIVE | Same as paper, plus Kraken IP whitelist and stricter backups. **Code not ready** | Hardware does not unblock live safety | **€25–70** (+0 GPU) |
| HIGHER-VOLUME PRODUCTION | 8–16 dedicated CPU, 32–64 GB. GPU **only if** bars become frequent or model grows | Extra CPU: timeout margin. Extra RAM: snapshots | **€50–120** CPU-only; **€100–400+** if you add a GPU |

## Where more money helps vs wastes

**Helps:** RAM so `qwen3:8b` never swaps; dedicated CPU so a noisy neighbor does not blow the 60s timeout; NVMe so SQLite WAL and model load are fast; encrypted off-box backups.

**Wastes:** GPU for 1h bars; a second Ollama server; managed Postgres/Redis; 128 GB RAM; RunPod/AWS GPU instances for this repo’s current `LLM_MODEL_NAME`.

Option C cloud tokens at ~1 proposal/hour are cheap **in dollars** and expensive **in architecture/privacy**. Not the cost-optimal default.

---

# Recommended Architecture

```
                         INTERNET
                             │
              egress only: Kraken public OHLC
              optional: FRED/SEC/BLS/BEA, Ollama pull
                             │
                             ▼
              ┌──────────────────────────────────────┐
              │  Linux VPS (Ubuntu 24.04)            │
              │  8 dedicated vCPU / 32 GB / NVMe     │
              │  NO public inbound (or SSH via TS)   │
              │                                      │
              │   systemd:                           │
              │     ollama          (localhost:11434)│
              │     trading-llm     (localhost:8765) │
              │     trading-research(localhost:8766) │
              │     trading-control (localhost:8767) │
              │         └── paper stream (child)     │
              │         └── monitor (optional)       │
              │                                      │
              │     qwen3:8b on persistent volume    │
              │     runtime/ + data/ on persistent   │
              │     disk                             │
              └──────────────┬───────────────────────┘
                             │
                    Tailscale / SSH
                             │
                             ▼
                    Operator laptop/phone
                    dashboard + approve/halt
                             │
                    cron: health, ingest, restic
```

This is the current in-repo architecture moved off the laptop, with a real supervisor and overlay admin network. Ollama stays private. The operator is no longer a process dependency — only an approver.

---

# Required Code Changes

Infrastructure-first. Do **not** treat these as this audit’s implementation.

## Must have before unattended paper 24/7

1. **Process supervision** — systemd (or Docker host-network) with `Restart=on-failure` for Ollama, LLM, research, control. Paper: respawn if PID dies (control watchdog **or** its own unit).
2. **Remote access without publishing app ports** — Tailscale or SSH tunnels. Set a non-empty `CONTROL_OPERATOR_TOKEN`.
3. **Do not use `start_stack.py` as PID 1** — it tears down everything on one child exit.
4. **Persistent volumes** for `runtime/`, `data/`, Ollama models, and env files.

## Should have soon after

5. Wrap `PaperTradingLoop.run_bar` so one exception audits + continues or HALTs, instead of killing the process.
6. Auto-HALT (or at least alert) on stale heartbeat using the existing `heartbeat_threshold_s`.
7. Real `GET /health` on LLM and research (liveness without calling Ollama). Include Ollama `/api/tags` in control health.
8. Serve Angular `dist/` (nginx) instead of `ng serve`. Fix `eventsSocketUrl()` so production is not hardcoded to `127.0.0.1:8767` when the UI is not on port 4200 (`apps/console/src/app/core/agent-state.service.ts`).
9. Cron: `scripts/research/ingest_once.py`; backups of `runtime/`.
10. Log rotation (`journald` + `logrotate` on `runtime/logs`).

## Only if you insist on multi-container Docker

11. Allow LLM/control bind on a private interface **or** document `network_mode: host`. Keep “not on the public Internet” as an invariant, not `0.0.0.0` plus a hope.

## Live trading (separate milestone — not required to host paper)

12. Do not flip `LIVE_TRADING_ENABLED` until: exchange confirmation of in-flight `client_order_id`, QueryOrders on the `duplicate_in_flight` window, IP-whitelisted keys, withdraw disabled, and a start path that is not “blocked on purpose.”
13. Non-blocking or async approval so a 3600s wait cannot stall market polling (or accept missed bars as policy).

**Not required:** GPU support, Postgres, Redis, exposing 11434, cloud LLM, browser automation.

---

# Deployment Plan

Feasible for **paper**. Do not deploy live.

1. **Provision** a Linux VPS: 8 dedicated vCPU, 32 GB RAM, 160 GB+ NVMe, Ubuntu 24.04, EU or a region close to you (operator latency to the UI; Kraken is public HTTPS).
2. **Harden:** unattended upgrades for security patches, SSH keys only, disable password auth, create a deploy user, `ufw default deny incoming`.
3. **Firewall:** no public app ports. Install **Tailscale**. Restrict SSH to tailnet or your IP.
4. **Install runtimes:** Python 3.12, [uv](https://github.com/astral-sh/uv), git. Node 22 only if you build the console on-box (or build CI artifacts elsewhere).
5. **Install Ollama** (vendor install or Docker with **127.0.0.1:11434**). Enable the systemd service. `ollama pull qwen3:8b` once. Confirm `curl http://127.0.0.1:11434/api/tags`.
6. **Clone** this repository to a fixed path (e.g. `/opt/trading-agent`). `uv sync --group dev` or `--no-dev` once you drop pytest from the server.
7. **Secrets:** copy `.env.*.example` to `.env.*` on the server. `chmod 600`. Fill `CONTROL_OPERATOR_TOKEN`. Leave `LIVE_TRADING_ENABLED=false`. Leave Kraken trading keys empty for paper. Never copy laptop live keys.
8. **Directories:** `runtime/` and `data/research/` on the data disk; confirm gitignore so they are not committed from the server.
9. **systemd units** (new, not in repo yet): `ollama`, `trading-llm` (`python -m src.llm.server` with `.env.llm` only), optional `trading-research`, `trading-control` (`.env.control` + `.env.engine`). `Restart=on-failure`, `After=network-online.target ollama.service`.
10. **Do not** run `scripts/dev/start_stack.py` as the production supervisor.
11. **Start paper** via `POST /v1/agent/start` (or the UI over an SSH tunnel) after control is healthy. Confirm ApprovalGate still required.
12. **Health:** cron `curl` `/v1/health` + Ollama tags; alert on failure.
13. **Monitoring:** Netdata/Beszel/Uptime Kuma on Tailscale, or node_exporter if you already have a scrape target.
14. **Backups:** restic of `runtime/`, `config/`, encrypted `.env.*`, daily.
15. **Paper validation (days, not minutes):** watch a few 1h bars, reject and approve from the remote UI, kill -9 the paper PID and confirm you can restart without duplicate simulated fills, stop Ollama and confirm rejects not orders, reboot the VPS and confirm units come back.
16. **Controlled production:** still paper. Live is a later engineering project, not a deploy flag.

---

# Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Treating `start_stack.py` as production | High if rushed | Entire stack dies on one crash | systemd |
| Publishing 11434 or 8767 | High on a default VPS | Unauthenticated LLM / operator API | ufw + Tailscale; loopback binds |
| Empty operator token + tunnel/proxy | High | Anyone on the path can halt/approve | Set token before any remote UI |
| Assuming GPU is required | Medium | Wasted €100–400/mo | CPU 32 GB VPS |
| Enabling live to “just try” | Medium | Real money, incomplete crash recovery | Keep `LIVE_TRADING_ENABLED=false` |
| Disk full on `runtime/` | Medium over months | Process crash in `run_bar` | disk alerts + logrotate |
| Operator asleep during approval window | Certain | Timed-out orders; blocked loop for up to 1h | Accept as design, or later async approvals |
| Ollama default 32K context RAM spike | Low–medium | Swap / OOM on 16 GB box | 32 GB RAM; later set `num_ctx` |
| Docs vs YAML (`llm_assisted` enabled) | Low | Unexpected LLM calls | Current YAML is source of truth |
| Uncommitted discovery pipeline | Low | Extra disk/API if enabled without cron | Keep out of 24/7 until scheduled |

---

# Final Verdict

The agent is a **carefully isolated paper system** that already fail-closes on LLM failure and keeps a reconstructable audit log. It is **not** a deployable 24/7 product until someone owns process restart, remote access, and persistence on a real disk.

It **can** leave your personal computer. It **cannot** safely control live funds on the current start path.

---

TRADING AGENT ON SERVER: **YES WITH CHANGES**

OLLAMA ON SAME SERVER: **YES**

GPU REQUIRED: **NO**

MINIMUM SERVER: **4 vCPU, 16 GB RAM, 80 GB NVMe, no GPU, Ubuntu 24.04 (tight; trial only)**

RECOMMENDED SERVER: **8 dedicated vCPU, 32 GB RAM, 160–240 GB NVMe, no GPU, Ubuntu 24.04, Tailscale, systemd**

ESTIMATED MONTHLY INFRASTRUCTURE: **€25–70** paper + CPU Ollama (EU dedicated-CPU / high-memory VPS class). GPU **€100–400+** would not improve this workload.

PRODUCTION READINESS: **40% paper 24/7** · **15% live**

TOP 5 BLOCKERS BEFORE DEPLOYMENT:

1. No process supervisor — `start_stack.py` is not 24/7; paper child is not auto-restarted.
2. Loopback-only servers plus optional auth — remote access must be Tailscale/SSH, never a naked public reverse proxy.
3. Console is `ng serve` with WebSocket hardcoded to `127.0.0.1:8767` on port 4200 — no production UI serving path.
4. `run_bar` exceptions and missing heartbeat auto-halt can stop or wedge the loop without recovery.
5. Live trading is explicitly blocked and lacks exchange-side confirmation of the in-flight idempotency window — do not enable it as part of this move.

NEXT ACTION: **Provision the recommended CPU VPS and add systemd + Tailscale for paper-only operation. Do not buy a GPU. Do not set `LIVE_TRADING_ENABLED=true`.**
