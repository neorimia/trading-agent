# 24/7 Paper Trading — Deployment Runbook

Turns `docs/SERVER_DEPLOYMENT_AUDIT.md`'s Deployment Plan into copy-pasteable steps,
using the artifacts in this `deploy/` directory. Read the audit doc first if you
haven't — this runbook assumes its conclusions.

**Scope: paper trading only.** `LIVE_TRADING_ENABLED` stays `false` throughout. Live
is a separate, later engineering milestone (audit §"Live trading"), not a step here.

## 0. Before you start

- Pick a VPS: 8 dedicated vCPU / 32 GB RAM / 160–240 GB NVMe / Ubuntu 24.04, no GPU
  (audit's recommended tier; 4 vCPU / 16 GB is a tight trial-only minimum).
- You will need: SSH access, a Tailscale account, and this repo's git remote.

## 1. Provision & harden

```bash
# as root on the fresh VPS
adduser trading
usermod -aG sudo trading   # or skip if you'll sudo from your own account
ufw default deny incoming
ufw allow OpenSSH
ufw enable
# disable password auth, SSH keys only — edit /etc/ssh/sshd_config:
#   PasswordAuthentication no
systemctl restart ssh
```

## 2. Tailscale (remote access without publishing app ports)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

No app port (`8080`, `8765`, `8766`, `8767`, `11434`) is ever exposed publicly. The
only way in is SSH (restricted to your IP/tailnet) and the tailnet itself.

## 3. Runtimes

```bash
# Python 3.12 + uv
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt install -y git
# Node 22, only if you build the console on this box (otherwise build in CI and rsync dist/)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

## 4. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo cp deploy/systemd/ollama.service.d/override.conf /etc/systemd/system/ollama.service.d/
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
ollama pull qwen3:8b
curl http://127.0.0.1:11434/api/tags   # confirm
```

## 5. Clone & install

```bash
sudo mkdir -p /opt/trading-agent
sudo chown trading:trading /opt/trading-agent
sudo -u trading git clone <this-repo-url> /opt/trading-agent
cd /opt/trading-agent
sudo -u trading uv sync --no-dev
```

## 6. Secrets

```bash
cd /opt/trading-agent
for f in control engine llm research; do
  cp .env.$f.example .env.$f
  chmod 600 .env.$f
done
```

Edit each `.env.*` (as the `trading` user):

- `.env.control`: set `CONTROL_OPERATOR_TOKEN` to a real random value
  (`openssl rand -hex 32`) — **mandatory** before any remote UI (audit risk register:
  "Empty operator token + tunnel/proxy → anyone on the path can halt/approve"). Add
  the tailnet hostname you'll browse from to `CONTROL_CORS_ORIGINS`.
- `.env.engine`: leave `LIVE_TRADING_ENABLED=false`. Leave `KRAKEN_*` trading keys
  empty. `BROKER_PAPER_MODE=true`. **Never copy laptop live keys here.**
- `.env.llm`: confirm `OLLAMA_HOST=http://127.0.0.1:11434`.
- `.env.research`: only if you're running the research service; fill API keys.

## 7. systemd units

```bash
cd /opt/trading-agent
sudo cp deploy/systemd/trading-llm.service /etc/systemd/system/
sudo cp deploy/systemd/trading-research.service /etc/systemd/system/   # only if using research
sudo cp deploy/systemd/trading-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-llm
sudo systemctl enable --now trading-research   # if applicable
sudo systemctl enable --now trading-control
```

Do **not** enable/run `scripts/dev/start_stack.py` here — it is not the production
supervisor (it stops the whole stack on any single child exit).

## 8. Console (nginx)

```bash
cd /opt/trading-agent/apps/console
npm ci
npm run build   # → dist/console/browser/
sudo cp /opt/trading-agent/deploy/nginx/trading-console.conf /etc/nginx/sites-available/trading-console
sudo ln -s /etc/nginx/sites-available/trading-console /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Read the comments in `deploy/nginx/trading-console.conf` — bind it to the tailnet
interface, not `0.0.0.0`.

## 9. Cron, logrotate, backups

```bash
sudo -u trading crontab -e   # paste the line from deploy/cron/research-ingest.cron
sudo cp deploy/logrotate/trading-agent /etc/logrotate.d/trading-agent
sudo logrotate --debug /etc/logrotate.d/trading-agent   # dry run
```

Follow `deploy/backup/README.md` for restic setup, then run the restore drill once —
an untested backup is not a backup.

## 10. Health check

```bash
curl http://127.0.0.1:8767/v1/health -H "Authorization: Bearer $CONTROL_OPERATOR_TOKEN"
```

Confirm `llm: "up"`, `ollama: "up"`, `agent: "stopped"` (paper hasn't started yet).

Set up an external check (cron `curl` + alert, or Uptime Kuma/Netdata/Beszel over
Tailscale) against `/v1/health` and Ollama's `/api/tags`.

## 11. Start paper

Over the tailnet (SSH tunnel or the nginx UI from step 8):

```bash
curl -X POST http://127.0.0.1:8767/v1/agent/start \
  -H "Authorization: Bearer $CONTROL_OPERATOR_TOKEN" \
  -H "Idempotency-Key: boot-$(date +%s)"
```

Confirm the ApprovalGate is still required (a proposal should show up as pending, not
auto-execute).

## 12. Paper validation (days, not minutes)

Do not consider this done after step 11. Over the following days, confirm:

- [ ] A few 1h bars post through the loop; approve/reject from the remote UI works.
- [ ] `kill -9 <paper pid>` and confirm `trading-control` (or the operator, since
      control's `SubprocessAgentProcess.start` de-dupes against a live `agent_pid`)
      restarts it without duplicate simulated fills.
- [ ] `sudo systemctl stop ollama`, confirm proposals become `RejectedProposal`
      (fail-closed), not silently skipped or crashed.
- [ ] `sudo reboot`, confirm `ollama`, `trading-llm`, `trading-control` all come back
      via systemd without manual intervention.
- [ ] Leave a heartbeat stale on purpose (stop the paper process without restarting
      it) and confirm the control plane's own watchdog
      (`src/control/runtime_state.py:halt_if_heartbeat_stale`, checked every
      ≤30s independent of any dashboard client) halts instead of sitting silent.

## What NOT to do as part of this

- Buy a GPU (CPU is sufficient for `qwen3:8b` Q4_K_M at this request rate).
- Expose `11434`, `8765`, `8766`, or `8767` on a public interface.
- Set `LIVE_TRADING_ENABLED=true`. See `docs/SERVER_DEPLOYMENT_AUDIT.md` §"Live
  trading (separate milestone)" for what that actually requires — it is not a config
  flag flip.
