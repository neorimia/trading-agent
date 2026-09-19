# Console

Local operator UI for the trading-agent control plane. It talks only to `http://127.0.0.1:8767` via the Angular proxy. It cannot call the LLM `/propose` endpoint.

Angular 21 + PrimeNG 21 (Node 24.14 cannot run Angular CLI 22).

## Run locally

From the repository root, start the control plane first:

```bash
cp .env.control.example .env.control
uv run python -m src.control.server
```

Then, in another terminal:

```bash
cd apps/console
npm install
npm start
```

Open `http://127.0.0.1:4200/`. Emergency stop is always in the chrome. Live start and live approve stay blocked. Observer role can view but not mutate.

## Scripts

```bash
npm start   # ng serve on 127.0.0.1:4200, proxy /v1 → :8767
npm test    # vitest, once
npm run build
```
