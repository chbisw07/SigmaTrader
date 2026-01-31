# SigmaTrader SQLite -> PostgreSQL Migration (Goal 1: Non-breaking Cutover)

## 0) Context and Goal

SigmaTrader currently uses a local **SQLite** database (via SQLAlchemy ORM + Alembic migrations). The first goal is to **switch the backing database to PostgreSQL** to better handle **burst TradingView alerts** (high write concurrency), **without breaking or losing any existing functionality**.

This document is the reference for developers/architects to plan, execute, and validate the migration.

### Success Criteria (Goal 1)

- Existing behavior remains the same from a user/API perspective.
- No data loss: existing SQLite data can be migrated into PostgreSQL.
- Switching DBs is configuration-only (via `ST_DATABASE_URL`), not code-path forks.
- `alembic upgrade head` works against PostgreSQL (fresh DB), producing the same logical schema.
- A clear rollback plan exists (switch back to SQLite) if needed.

### Explicit Non-goals (for Goal 1)

- No schema redesign or feature work (that comes after the cutover).
- No async DB rewrite (keep current sync SQLAlchemy usage).
- No mandatory Postgres-only features (we may add optional enhancements later).

---

## 1) Current State (SQLite) - What Exists Today

### 1.1 How the DB is configured

- Settings live in `backend/app/core/config.py`.
- Default DB:
  - `ST_DATABASE_URL` default: `sqlite:///.../backend/sigma_trader.db`
  - Pytest DB: `sqlite:///.../backend/sigma_trader_test.db`

Postgres URL examples (what we will switch to after cutover):

- `postgresql+psycopg://st_user:st_pass@localhost:5432/sigmatrader`
- `postgresql+psycopg2://st_user:st_pass@localhost:5432/sigmatrader`

### 1.2 ORM / session management

- SQLAlchemy engine + session factory in `backend/app/db/session.py`:
  - `engine = create_engine(settings.database_url, future=True, ...)`
  - `SessionLocal = sessionmaker(..., expire_on_commit=False)`
  - FastAPI dependency `get_db()` yields one Session per request.
- SQLite-specific connection setting:
  - `check_same_thread=False` is set when the URL starts with `sqlite` to support multithread usage.

### 1.3 Migrations (Alembic)

- Alembic env: `backend/alembic/env.py` reads the URL from:
  - CLI/programmatic override `sqlalchemy.url`, else
  - `get_settings().database_url`.
- Base URL in `backend/alembic.ini` is SQLite, but runtime overrides exist.
- Application startup behavior in `backend/app/main.py`:
  - Best-effort auto-migrate runs by default for SQLite (or when `ST_AUTO_MIGRATE` is enabled).

Goal 1 recommendation:

- Keep `ST_AUTO_MIGRATE` disabled for production Postgres (run migrations explicitly during deploy).

### 1.4 Notable SQLite-driven implementation choices

- Time handling:
  - Custom `UTCDateTime` in `backend/app/db/types.py` stores timestamps as naive UTC and returns tz-aware UTC.
  - Some areas explicitly account for SQLite naive datetimes (examples in API/service code).
- Durability/locking design (docs):
  - `docs/strategy_deployment_2.md` specifies "SQLite-safe claim" semantics for the deployment job queue.
  - Implementation exists in `backend/app/services/deployment_jobs.py` using idempotency via unique `dedupe_key` + atomic update checks.

### 1.5 DB footprint (high level)

The ORM defines many tables (not exhaustive): `users`, `strategies`, `risk_settings`, `alerts`, `orders`, `positions`, `position_snapshots`, `indicator_rules`, plus deployments runtime tables (`strategy_deployment_jobs`, locks/actions/event logs), alert system v3 tables (`alert_definitions`, `alert_events`), market data (`candles`), etc.

Hot/likely high-write tables during alert bursts:

- `alerts` (webhook ingestion)
- `orders` (order creation / broker sync)
- `system_events` (if used heavily for debug/audit)
- deployment runtime tables (if deployments are enabled)

---

## 2) Why PostgreSQL Helps (Burst Alerts + Concurrency)

SQLite is a great local/dev DB, but it has a fundamental constraint: **single-writer** behavior on a DB file. Under bursty webhook traffic (or multiple worker processes), this often manifests as contention and "database is locked"-style issues.

PostgreSQL improves this profile because it provides:

- True concurrent writers with MVCC + row-level locking.
- Better connection pooling behavior (application-side pool + optional PgBouncer).
- Stronger operational tooling: backups, replication, observability.
- Better primitives for "job queue" patterns (`SELECT ... FOR UPDATE SKIP LOCKED`), should we adopt them later.

Trade-offs to accept:

- Operational complexity: Postgres service lifecycle, credentials, backups, upgrades.
- Requires network connectivity (even if localhost).
- Slightly different SQL semantics and stricter enforcement (constraints, types).

---

## 3) Key Technical Challenges (What Will Break If We Just Flip the URL)

### 3.1 Alembic migrations are currently SQLite-centric in places

The biggest compatibility blocker for running existing migrations against Postgres:

- Several Alembic migrations define Boolean columns with `server_default=sa.text("0")` / `sa.text("1")`.
- In PostgreSQL, a Boolean column cannot have `DEFAULT 0` or `DEFAULT 1` (type mismatch).

If we do nothing, `alembic upgrade head` on a fresh Postgres DB will fail early.

Mitigation:

- Update migrations to emit **dialect-correct defaults**:
  - Use `sa.false()` / `sa.true()` where possible (preferred), or
  - Conditional defaults: SQLite gets `"0"/"1"`, Postgres gets `"false"/"true"`.

Where this exists today (repo-specific):

- These Alembic revisions currently use `"0"/"1"` Boolean defaults and must be made Postgres-safe:
  - `backend/alembic/versions/0001_create_core_tables.py`
  - `backend/alembic/versions/0013_add_market_data_tables.py`
  - `backend/alembic/versions/0014_add_indicator_rules_and_alert_source.py`
  - `backend/alembic/versions/0016_extend_strategies_for_alert_templates.py`
  - `backend/alembic/versions/0020_add_strategy_available_for_alert.py`
  - `backend/alembic/versions/0025_add_alerts_v3_and_custom_indicators.py`
  - `backend/alembic/versions/0035_add_canonical_instruments.py`
  - `backend/alembic/versions/0037_add_synthetic_gtt_fields.py`
  - `backend/alembic/versions/0038_add_signal_strategies_v3.py`
  - `backend/alembic/versions/0040_add_rebalance_tables.py`
  - `backend/alembic/versions/0045_add_strategy_deployments.py`
  - `backend/alembic/versions/0052_add_managed_risk_positions.py`
  - `backend/alembic/versions/0055_refine_execution_policy_state_semantics.py`
  - `backend/alembic/versions/0063_add_risk_engine_tables.py`

Important note:

- Editing historical migrations is acceptable here because the "source of truth" is the repo, and the Postgres DB will be created fresh.
- We must keep migrations runnable for SQLite too (dev/test).

### 3.2 Constraint enforcement differences

- SQLite foreign keys are only enforced if `PRAGMA foreign_keys = ON` (not explicitly set in code today).
- Postgres enforces FK constraints by default.

This matters for data migration:

- Existing SQLite data may contain orphan references (rare, but possible).
- Postgres import can fail unless we clean data, import in dependency order, or temporarily disable constraints during import.

### 3.3 Timezone / datetime semantics

Current behavior intentionally standardizes on UTC using `UTCDateTime` (naive storage, tz-aware retrieval).

Risk points:

- If we later switch to `TIMESTAMPTZ` storage in Postgres, we must do it intentionally and consistently.
- During data migration, timestamps stored as text/naive values must round-trip exactly.

Goal 1 stance:

- Keep the current semantics as-is to avoid behavior changes.

### 3.4 "LIKE" / collation / case sensitivity differences

- SQLite `LIKE` behavior can be case-insensitive depending on collation.
- Postgres `LIKE` is case-sensitive (use `ILIKE` for case-insensitive).

Mitigation:

- SigmaTrader already normalizes many identifiers (e.g., uppercase symbols).
- We should still test endpoints that use `.like(...)` filters.

### 3.5 Migration of autoincrement IDs (sequences)

When importing rows with explicit IDs into Postgres:

- The underlying sequence for `SERIAL`/identity columns can remain behind.
- Next insert may fail with duplicate key unless we `setval(...)` sequences.

---

## 4) Migration Strategy (High-level, Non-breaking)

We take a conservative, low-risk approach:

1) Keep SQLAlchemy ORM models as the schema source of truth.
2) Make Alembic migrations runnable on Postgres (cross-dialect).
3) Create a new Postgres database and run `alembic upgrade head`.
4) Copy data from SQLite into Postgres (one-time migration).
5) Cut over by changing `ST_DATABASE_URL`.
6) Validate and keep rollback available.

This keeps the application code paths the same and minimizes behavior changes.

---

## 5) Implementation Plan (Developer + Architect View)

### Phase A - Preparation

- Add a Postgres driver dependency for SQLAlchemy:
  - Prefer psycopg v3 (`psycopg`) or psycopg2 (`psycopg2-binary`) based on your packaging preference.
- Add local Postgres provisioning:
  - Recommended: `docker compose` service for Postgres + a `.env` example for `ST_DATABASE_URL`.
- Confirm environments:
  - Dev: SQLite remains default unless overridden.
  - Staging/Prod: Postgres becomes default (after cutover).

### Phase B - Make migrations Postgres-compatible

- Audit Alembic migrations for SQLite-only assumptions:
  - Boolean `server_default` values (`"0"/"1"`) are the priority.
  - Any dialect-conditional FK creation is fine (SQLite limitations), but Postgres must still get the intended constraints.
- Validate: run migrations on a fresh Postgres DB locally.

Deliverable:

- `alembic upgrade head` succeeds on both SQLite and Postgres.

### Phase C - Data migration tooling + validation

Choose a data copy approach (see Section 6). Recommended path for reliability:

- Create schema in Postgres via Alembic first.
- Copy table data from SQLite -> Postgres via a controlled script.
  - Convert SQLite-stored booleans (often `0/1`) into Postgres booleans (`false/true`) if the migration tool does not do it automatically.
  - Import in dependency order (parents first) or use a constraint-friendly loading strategy.
- Fix sequences after import.
- Validate row counts + spot checks + critical invariants.

Deliverable:

- Repeatable migration runbook (commands + checklist).

### Phase D - Cutover + rollback readiness

- Freeze writes briefly (stop webhook ingestion / stop backend).
- Perform migration and validation.
- Flip `ST_DATABASE_URL` to Postgres.
- Bring backend up, run smoke tests, monitor.
- Keep the SQLite DB file as rollback source until confidence is high.

---

## 6) Data Migration Options (Choose One)

### Option 1: pgloader (fastest to try)

Pros:

- Often "just works" for SQLite -> Postgres.
- Handles type conversion and bulk loading efficiently.

Cons:

- Less control over custom conversions (e.g., booleans stored as ints, datetime formats).
- Harder to guarantee exact semantics without validation scripts.

### Option 2: SQLAlchemy-based copy script (recommended for control)

Pros:

- Can map/clean specific columns (booleans, timestamps, JSON-as-text).
- Can import in correct dependency order.
- Can add integrity checks as part of the script.

Cons:

- More implementation time.

### Option 3: `sqlite3 .dump` -> `psql` (not recommended)

Pros:

- Easy to generate.

Cons:

- SQL dialect mismatches, type mapping pain, fragile.

### Recommendation for SigmaTrader (Goal 1)

Use a controlled, repeatable approach:

1) Create a fresh Postgres database.
2) Run Alembic migrations on Postgres (`alembic upgrade head`) to create the schema.
3) Copy data from SQLite -> Postgres using either:
   - pgloader (fast trial), or
   - a purpose-built SQLAlchemy copy script (preferred long-term).
4) Fix sequences and validate.
5) Cut over by setting `ST_DATABASE_URL` to Postgres.

Runbook skeleton (intentionally high-level; exact commands come when we implement it):

- Stop the backend (so no writes happen during the copy).
- Back up `backend/sigma_trader.db`.
- Provision Postgres + credentials.
- Run migrations against Postgres.
- Run data copy (table-by-table in batches).
- Verify counts, key queries, and sequence behavior.
- Start backend against Postgres and run a webhook smoke test.

---

## 7) Validation Checklist (Nitty-gritty, Must Do)

### 7.1 Pre-migration checks (on SQLite)

- Confirm app is healthy and DB is not corrupted.
- Collect basic stats:
  - row counts for the most important tables (`alerts`, `orders`, `strategies`, `risk_settings`, etc.)
  - most recent timestamps (sanity check)
- Optional but recommended:
  - run a "FK sanity scan" (find obvious orphan references) before Postgres rejects them.
  - scan enum-like columns (stored as text with CHECK constraints) to ensure there are no unexpected values that Postgres will reject.

### 7.2 Post-migration checks (on Postgres)

- Row counts match (per table).
- Critical queries return expected results:
  - list strategies, risk settings
  - list recent alerts
  - list orders by status
  - any admin UI pages used daily
- Verify sequences are advanced:
  - Insert a new row in several tables and ensure IDs auto-increment without collision.
- Verify indexes exist (query plans not required for Goal 1, but missing indexes can hurt).

### 7.3 Application-level smoke tests

- Send a test TradingView webhook payload (or a simulated payload) and confirm:
  - alert row created
  - order creation path still works
  - no new 500s due to SQL differences

---

## 8) Rollback Plan (Mandatory)

Rollback must be simple and fast:

- Keep the original `sigma_trader.db` intact (copy it before migration).
- If issues occur after cutover:
  - stop backend
  - revert `ST_DATABASE_URL` to the SQLite URL
  - restart backend

If you need a data backfill from Postgres -> SQLite later, treat it as a separate effort (not part of Goal 1).

---

## 9) Post-cutover Improvements (Phase 2 Ideas to Make SigmaTrader More Robust)

These are optional improvements once Postgres is stable, focused on burst alert robustness and operational quality.

### 9.1 Better job-queue claiming on Postgres

Current pattern in `backend/app/services/deployment_jobs.py` is "SQLite-friendly" (select then atomic update check).

On Postgres we can tighten correctness and scale by adopting:

- `SELECT ... FOR UPDATE SKIP LOCKED` job claiming (single statement + no races).
- Advisory locks for per-deployment critical sections.

### 9.2 Alert ingestion hardening (burst-friendly)

- Add idempotency keys for webhook ingestion to dedupe repeated alerts (TradingView retries).
- Batch inserts where safe (reduce commit overhead).
- Add backpressure / queueing (Redis/Celery/RQ or a DB-backed queue) so webhooks return quickly and processing happens async.

### 9.3 Data lifecycle management

Some tables can grow quickly (`alerts`, `alert_events`, `candles`, `system_events`).

Consider:

- retention policies (e.g., keep 30-90 days of raw alerts by default)
- partitioning large time-series tables (later)
- moving large payloads to object storage if needed (rare, later)

### 9.4 Make JSON fields first-class in Postgres

Today many "JSON" values are stored as `Text`.

Postgres upgrades:

- migrate to `JSONB` for structured query + indexing (GIN indexes)
- validate JSON schema for important payloads (optional)

### 9.5 Operational maturity

- Add structured DB monitoring: slow queries, connection counts, locks.
- Add scheduled backups and restore drills.
- Consider PgBouncer for connection pooling if you scale worker counts.
- Tune SQLAlchemy engine settings for Postgres (pool sizing, `pool_pre_ping`, timeouts) once baseline is stable.

---

## 10) Work Breakdown (Sprint-friendly)

This is a suggested backlog that maps cleanly to sprint tasks:

1) Postgres local setup:
   - docker compose + `.env.example` + docs.
2) Dependency + config:
   - add psycopg driver
   - ensure `ST_DATABASE_URL` supports Postgres URL format.
3) Alembic hardening:
   - fix Boolean server defaults and any other dialect issues
   - verify migrations on fresh Postgres and fresh SQLite.
4) Data migration tool:
   - implement + document runbook
   - include sequence fixups + validation checks.
5) Cutover checklist:
   - freeze writes, migrate, validate, switch URL, smoke tests, rollback steps.
6) Post-cutover performance pass (optional):
   - indexes, pooling settings, job-queue SKIP LOCKED, retention policies.

### 10.1 Phase 2 enhancements backlog (Postgres-native, after Goal 1)

Use this section to create sprint tasks once Goal 1 is stable. These are designed to be independent, incremental improvements that reduce risk under burst traffic and make operations safer.

P0 (do soon after cutover; high ROI, low-to-medium risk):

- DB ops baseline:
  - Add backup + restore drill runbook (and schedule).
  - Add basic DB monitoring: connection counts, slow query logs, lock waits.
  - Decide how migrations run in production (recommended: explicit deploy-time migration, not startup auto-migrate).
  - Acceptance: we can restore into a fresh DB and boot SigmaTrader successfully.
- Webhook ingestion idempotency:
  - Add an idempotency key for TradingView webhook ingestion (TradingView retries can duplicate alerts).
  - Enforce with a unique index/constraint and return success for duplicates (idempotent behavior).
  - Acceptance: repeated identical webhooks do not create duplicate downstream orders.
- Postgres-optimized job claiming (deployments runtime):
  - Replace/augment the "SQLite-friendly" job claim pattern with a Postgres claim pattern that scales (e.g., SKIP LOCKED).
  - Acceptance: multiple workers can process the queue concurrently without duplicate execution, and throughput improves under load.

P1 (robustness + developer ergonomics; medium risk):

- Convert selected JSON-as-text columns to JSONB (where it pays off):
  - Candidates (examples): `orders.managed_risk_json`, alert/action payload columns, strategy/policy JSON blobs.
  - Add lightweight validation and indexes only where queries justify it.
  - Acceptance: no API contract changes; storage becomes queryable/indexable in Postgres.
- Data lifecycle / retention:
  - Define retention rules for high-growth tables: `alerts`, `alert_events`, `candles`, `system_events`.
  - Add a scheduled cleanup job (and document defaults + safe overrides).
  - Acceptance: DB size stays bounded under continuous use; cleanup is observable and reversible.
- Index review for burst paths:
  - Validate indexes for hot endpoints and background loops (alerts listing, order status polling, queue claiming).
  - Acceptance: no unexpected sequential scans for the top "daily" queries.

P2 (bigger improvements; higher design involvement):

- Time semantics hardening:
  - Decide whether to keep "naive UTC" storage everywhere or migrate to `TIMESTAMPTZ` in Postgres.
  - Do this only with explicit migration + test coverage (time bugs are subtle).
  - Acceptance: timestamps are consistent across ingestion, UI rendering, analytics, and exports.
- Constraint hardening:
  - Add stricter FKs/NOT NULL/unique constraints once data is clean and behaviors are understood.
  - Acceptance: constraints prevent bad states without blocking legitimate workflows.
- Scaling topology:
  - Decide on multi-worker Uvicorn + background worker separation.
  - Consider PgBouncer if connection counts grow.
  - Acceptance: predictable performance under burst workloads with clear capacity limits.

---

## 11) Open Questions (Decide Early)

- Migration mode:
  - Is brief downtime acceptable (simplest), or do we need near-zero downtime?
- Production deployment model:
  - single host Postgres, managed Postgres (RDS), or containerized Postgres?
- Data retention:
  - how long do we keep raw alerts/events/candles in the primary DB?
- Concurrency model:
  - do we plan to run multiple Uvicorn workers/processes after Postgres cutover?
