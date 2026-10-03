# RECLAIM OS

> **Don't chase every failed payment. Recover the right revenue.**

An AI revenue-recovery operating system. It finds revenue at risk across failed payments, abandoned checkouts, failed subscriptions and overdue invoices, decides **what to do, whether it is allowed, and whether to do nothing**, executes through a deterministic simulator, and measures recovery against a control group, with a full audit trail.

> **Everything in this repository is DEMO / SIMULATED.** Customers, payments and "recovered revenue" are synthetic, the payment/recovery simulator is local and deterministic, and no payment gateway, LLM API or external service is used. "Incremental recovery" is an *estimate* from a simulated experiment, not proof of causal lift.

## The problem
Recovery teams retry or message every failed payment. That wastes money and customer goodwill, ignores retry/contact limits, treats one customer's four problems as four unrelated tickets, and nobody can say how much revenue the effort *actually caused*.

## The solution (and why it is different)
RECLAIM OS does not just list failed payments. For every case it answers:

1. **What** revenue is at risk (customer-level exposure across all sources).
2. **Why** (root-cause diagnosis with evidence and an explainable recoverability score).
3. **Which** action has the highest expected value (not the highest probability).
4. **Whether** it is permitted (deterministic policy gate: ALLOW / BLOCK / ESCALATE).
5. **Whether to act, escalate or deliberately do nothing** (`NO_ACTION` is a real decision).
6. **How much** was recovered, and how much was **incremental vs a control group**.
7. **Why**, for every decision (audit ledger).

## Architecture
```
Data ingestion → Revenue events → Risk engine (explainable score) → Customer revenue graph
  → Diagnosis → Candidate actions → Expected-value optimizer → POLICY GATE
        ├─ ACT ───────► Simulator ─► Outcome ─► Recovery measurement ─┐
        ├─ ESCALATE ──► Human queue (approve / reject / more info)    ├─► Control-group analysis ─► Audit ledger
        └─ NO_ACTION ─► Stop (with reason)                            ┘
```
| Module | File |
|---|---|
| Scoring, diagnosis, candidates, optimizer, budget | `backend/app/engine.py` |
| Policy gate (pure, deterministic) | `backend/app/policy.py` |
| Deterministic simulator + group assignment | `backend/app/simulator.py` |
| Workflow: analyze → execute → review → audit, dashboard, graph, lab, experiments | `backend/app/service.py` |
| REST API (FastAPI) | `backend/app/main.py` |
| Seed (1,006 customers, 196 cases, 6 scenarios) | `backend/app/seed.py` |
| React UI | `frontend/src/` |

## Features
- **Command Center**: revenue at risk / recoverable / recovered / incremental, funnel, trend, risk by source, recovery by action, failure reasons, segments, budget utilisation, AI vs Control.
- **AI Decision Room**: case → root cause, evidence, score breakdown, candidate-action table (probability, expected recovery, cost, friction, EV, policy status), selected action, why, stopping rule, **Execute**, live audit timeline.
- **Revenue Risk Graph**: one customer's checkout / payment / subscription / invoice exposure as a graph.
- **Recovery Lab**: budget / segment / strategy / retry-delay / contact-frequency simulator (always labelled SIMULATION) plus per-case counterfactuals (always labelled ESTIMATED).
- **Human Review**: pending, high-value, policy exceptions, escalated, decided; Approve / Reject / Request info / Inspect.
- **Audit Ledger**: filter by case, customer, action/event, actor, policy, outcome, date.
- **Six deterministic showcase scenarios** on the Command Center (see `docs/DEMO_SCRIPT.md`).

## Tech stack
Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic 2, NumPy (seeded data generation), SQLite (default). React 18, TypeScript, Vite, Tailwind CSS 3, Recharts, Lucide. pytest, Vitest. Docker / Docker Compose.
*Not used:* pandas and scikit-learn. The scoring model is an explicit, additive, explainable rule set rather than a trained model.

## Data model
`Customer, Payment, Checkout, Subscription, Invoice, RecoveryCase, RecoveryAction, RecoveryOutcome, RecoveryPolicy, AgentDecision, Experiment, AuditEvent, HumanReview` (`backend/app/models.py`). A `RecoveryCase` links a customer to one source item and carries score, root cause, decision, group (AI / CONTROL / DEMO), expected and actual recovery. Customers carry a few cached history counters (successful payments, previous recoveries, engagement) used by scoring.

## AI decision engine
Runs in `AI_MODE=demo` (default): fully deterministic and offline.
- **Recoverability score (1–99)** = 15 + additive factors: payment history, failure type, customer value, recency, previous recoveries, overdue age, engagement, retry count, failed attempts, contact permission, segment, payment method, checkout value. Every factor is returned with points and text, e.g. `+18  7 previous successful payments`.
- **Diagnosis** maps the failure to a root cause with evidence lines.
- **Probability** per action = base rate for the failure class × (0.55 + 0.9 × score/100).
- The explanation generator (`engine.explain`) is the seam where an LLM could be plugged in later; none is required or called.

## Recovery optimizer
```
expected_recovery = revenue_at_risk × probability
expected_value    = expected_recovery − intervention_cost − friction_penalty
friction_penalty  = revenue_at_risk × friction_rate(low .4% / medium 1.2% / high 8%) × (1.5 if LTV ≥ ₹2L)
```
It picks the highest-EV **permitted** action. If even the best permitted action beats `NO_ACTION` by less than ₹100, it does nothing. If the unconstrained best action was blocked, that is recorded (`ACTION_BLOCKED`) and shown. **Budget:** `allocate_budget` ranks opportunities by expected value per rupee of intervention cost and fills the daily budget greedily (an approximation of the 0/1 knapsack, not an exact optimum).

## Policy engine (`backend/app/policy.py`)
`MAX_PAYMENT_RETRIES=2`, `MAX_CUSTOMER_MESSAGES=3`, `MIN_MESSAGE_INTERVAL_HOURS=24`, `HIGH_VALUE_THRESHOLD=100000`, `HUMAN_APPROVAL_THRESHOLD=100000`, `MAX_OVERDUE_AUTOMATION_DAYS=30`, plus `MAX_FAILED_RECOVERY_ATTEMPTS=2` (stopping rule), `MIN_HUMAN_REVIEW_VALUE=25000`, `MIN_NET_GAIN=100`, `DAILY_RECOVERY_BUDGET=10000`. Also: no contact without permission, no retries on non-retryable failures (expired card, hard decline, auth, fraud), fraud flags escalate, already-resolved items block everything but NO_ACTION. The gate runs at analysis **and again at execution time**.

## Control-group evaluation
Eligible cases (those the agent would act on) are split into **AI** and **CONTROL** by a seeded hash (default 70/30, seed 42). The AI arm gets the simulated action; the control arm gets nothing but may recover organically (simulated). The UI and API keep two numbers apart:
- **Observed recovery**: what the AI arm recovered in the simulator.
- **Estimated incremental recovery** = (AI value-weighted recovery rate − control rate) × AI-arm revenue at risk, with a 95% CI on the case-rate lift. `POST /api/experiments/run` re-runs it with any split/seed. Small samples, simulated outcomes: treat it as illustrative.

## Installation & running locally
Requirements: Python 3.11+ (tested on 3.12), Node 18+ for building the UI (optional if you use the bundled `frontend/dist`).

**Fastest (UI + API on one port):**
```bash
./scripts/run_local.sh            # macOS/Linux      (Windows: .\scripts\run_local.ps1)
# open http://127.0.0.1:8000   (API docs: /docs)
```
**Manual:**
```bash
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..       # skip if frontend/dist already exists
cd backend && python -m uvicorn app.main:app --port 8000
```
**Frontend dev server with hot reload:** run the API as above, then `cd frontend && npm run dev` → http://localhost:5173 (proxies `/api` to :8000).

The database is created and seeded automatically on first start (≈5 s). Use **Reset demo** in the UI, `POST /api/simulator/reset`, or `python scripts/seed_db.py` to restore the initial state.

## Docker
```bash
docker compose up --build        # → http://localhost:8000
```
> **Docker was NOT verified in the build environment** (no Docker daemon was available). The `Dockerfile` (multi-stage: Node build → Python runtime) and `docker-compose.yml` were written carefully and the YAML was parsed, but never executed. The non-Docker path above is the verified one.

## Demo walkthrough
See **`docs/DEMO_SCRIPT.md`** for the 3-minute story and the six scenarios (retry success, ₹85,000 payment link, ₹4,80,000 human escalation, already paid → NO ACTION, retry limit → BLOCKED, checkout recovery). Scenario cases are deterministic and unexecuted after every reset.

## API (Swagger at `/docs`)
`GET /api/dashboard` · `GET /api/customers[/{id}]` · `GET /api/recovery-cases[/{id}]` · `POST /api/recovery-cases/{id}/analyze|execute|approve|reject|request-info` · `GET /api/recovery-actions` · `GET /api/reviews` · `GET /api/audit` · `GET /api/experiments` · `POST /api/experiments/run` · `GET /api/recovery-lab/{case_id}` · `POST /api/recovery-lab/simulate` · `GET /api/policies` · `GET /api/scenarios` · `POST /api/simulator/reset` · `GET /api/health`.
Errors are structured: `{"error": {"code": "CASE_CLOSED", "message": "…"}}`; stack traces are never returned.

## Testing
```bash
python -m pytest -q                         # 63 backend tests (run from project root)
cd frontend && npm test && npm run build    # 5 UI unit/smoke tests, type-check + production build
python scripts/acceptance.py                # end-to-end API flow against a RUNNING server (32 checks, run twice with a reset)
```
Backend tests cover scoring, candidates, EV maths, optimizer, budget allocation, every policy rule, no-action logic, retry limits, human escalation/approval/rejection, simulator determinism, experiment maths, audit events and the API.

## Project structure
```
backend/app/   engine.py policy.py simulator.py service.py seed.py models.py db.py main.py
frontend/src/  App.tsx pages/ components/ api.ts format.ts
tests/         pytest suite        scripts/  run_local.* seed_db.py acceptance.py
docs/          DEMO_SCRIPT.md      data/     SQLite DB is created here
Dockerfile  docker-compose.yml  .env.example  README.md
```

## Limitations
- All data and outcomes are synthetic; outcomes are drawn from the model's own probabilities, so the demo is *self-consistent*, not evidence that the model would work on real traffic.
- Incremental recovery is a simulated, small-sample estimate with no causal guarantee.
- The scoring/probability tables are hand-set heuristics, not learned from data.
- Budget allocation is greedy, not an exact optimiser.
- SQLite by default; the schema is portable SQLAlchemy but PostgreSQL has **not** been tested. There is no authentication, multi-tenancy or real gateway/messaging integration.
- Docker files are unverified (see above). The UI was verified by type-check, production build, render smoke tests and API-level acceptance, **not** by clicking through it in a browser.
- Timestamps are generated relative to the first start; "Reset demo" regenerates them.

## Future improvements
Learned recoverability model on real history; exact knapsack/LP budget optimiser; real gateway + messaging adapters behind the simulator interface; optional LLM explanation layer behind `AI_MODE`; PostgreSQL CI; auth and roles for reviewers; proper randomised holdout from live traffic.
