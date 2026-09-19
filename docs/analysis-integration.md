# Analysis integration (Level 1 → 2 → 3)

Research reports from the seven crypto-adapted prompts stay **outside the order path**.
`POST /analyze` never becomes a Kraken order. `POST /propose` remains the only LLM gate
that can later become a `ParsedProposal`, and even that still goes through `RiskEngine`,
`ApprovalGate`, YAML limits, and the kill switch.

## What ships at Level 1 (current MVP)

- Isolated LLM process: `POST /analyze` returns `LLMAnalysis | RejectedAnalysis`.
- Control plane: `POST /v1/research/analyze` for operator-triggered reports only.
  Control still does **not** call `/propose`.
- Deterministic facts: indicators (`src/engine/indicators.py`), stress
  (`src/engine/stress.py`), daily plan template (`src/engine/daily_plan.py`).
- Console: Asset page Run analysis, Dashboard daily plan, Risk stress table.
- `normalize_analysis()` **always returns `None`**. Zero `ParsedProposal` from analyses.
- `position_size_suggestion` must stay `null`; a numeric value rejects the report.
- Missing derivatives/on-chain fields are `unknown`, never estimated.
- Time-travel: bars with close-time `<= as_of`; research docs with
  `fetched_at <= as_of` and `published_at <= as_of` (or unpublished).

Not in Level 1: RSS until a human signs ToS, funding/OI/on-chain adapters,
trade journal P6, LLM commentary inside the backtest fill loop, scheduler-driven
signals.

## Promotion to Level 2 (decision-support)

All of the following must be true before the normalizer may emit a `ParsedProposal`:

1. A measured set of Level 1 analyses with source coverage (every factual claim
   cites `data_sources[]` or is marked `unknown`).
2. Zero recorded cases of the model filling `position_size_suggestion`.
3. At least one crypto RSS (or equivalent) source with `tos_reviewed_at` set by a human.
4. Existing paper sessions without a critical halt attributed to analysis misuse.
5. Operator review of false-positive news (contradictions left visible, not resolved).

Level 2 behavior, when enabled:

- Scheduler may run P2 on bar close, P3 on new high-credibility docs, P7 daily UTC,
  P4 on fill.
- `normalize_analysis()` becomes deterministic: expiry, confidence floor,
  data-quality floor, unresolved contradictions → `None`, optional EMA confluence.
- Any resulting `ParsedProposal` still requires **human approval**. UI must keep
  labelling it “proposal, not order”.
- `llm_assisted` stays disabled until that strategy row is explicitly enabled
  (restart required, same as today).

## Promotion to Level 3 (limited automation)

All of the following must be true:

1. 30 paper sessions without a critical halt (existing Phase 4/5 gate).
2. Process win-rate on a journal (not PnL) after P6 exists.
3. Measured false-long rate of the normalizer.
4. Kill switch tested while paper is running.

Level 3 still does **not** let the LLM auto-execute. Auto-exec is only for an
already approved deterministic strategy (`baseline_ema_cross` or similar) inside
YAML limits. LLM may at most **veto** (block) an EMA trade when P3 is unverified
high-impact or P2 invalidation is hit. Every veto is an audit event plus an alert.

## Invariants that never change

- LLM process: no `src.risk` / `src.execution` / `src.engine` imports, no broker keys.
- Control process: no `src.llm` imports, no `/propose` proxy.
- `RiskEngine` is the only producer of `quantity`.
- Live start and live approve stay blocked.
- Universe allowlist is the only tradable set (`BTCUSD` / `ETHUSD` on Kraken paper).
