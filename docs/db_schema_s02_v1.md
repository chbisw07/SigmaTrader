## SigmaTrader – Core DB Schema (Sprint S02 / G01)

This document defines the **initial SQLite schema** for the core trading entities used in SigmaTrader. It is designed to be implemented via SQLAlchemy models and Alembic migrations in Sprint S02 / G02.

Conventions:

- Primary keys use `INTEGER PRIMARY KEY`.
- Timestamps are stored as `TIMESTAMP` with `CURRENT_TIMESTAMP` defaults.
- Booleans are represented as `INTEGER` (`0` = false, `1` = true).
- Enumerated values are stored as `TEXT` with `CHECK` constraints.
- Foreign keys assume `PRAGMA foreign_keys = ON` at connection time.

---

### 1. `strategies`

Represents a trading strategy, including its execution mode.

Key points:

- One row per strategy.
- `execution_mode` controls AUTO vs MANUAL behavior.
- Risk settings are linked via the `risk_settings` table (per-strategy rows).

```sql
CREATE TABLE strategies (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT,
    execution_mode  TEXT NOT NULL DEFAULT 'MANUAL'
                    CHECK (execution_mode IN ('AUTO', 'MANUAL')),
    enabled         INTEGER NOT NULL DEFAULT 1, -- 0 = disabled, 1 = enabled
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_strategies_execution_mode
    ON strategies (execution_mode);
```

---

### 2. `risk_settings`

Stores global and per-strategy risk limits.

Key points:

- `scope = 'GLOBAL'` → applies as default when no per-strategy row exists.
- `scope = 'STRATEGY'` → row is tied to a specific `strategy_id`.
- Symbol lists are stored as JSON-encoded `TEXT` for flexibility.

```sql
CREATE TABLE risk_settings (
    id                       INTEGER PRIMARY KEY,
    scope                    TEXT NOT NULL DEFAULT 'STRATEGY'
                             CHECK (scope IN ('GLOBAL', 'STRATEGY')),
    strategy_id              INTEGER
                             REFERENCES strategies(id)
                             ON DELETE CASCADE,

    max_order_value          REAL,   -- ₹ limit per order (nullable → no limit)
    max_quantity_per_order   REAL,   -- max size per order
    max_daily_loss           REAL,   -- daily P&L floor before blocking
    allow_short_selling      INTEGER NOT NULL DEFAULT 1, -- 0/1
    max_open_positions       INTEGER,
    clamp_mode               TEXT NOT NULL DEFAULT 'CLAMP'
                             CHECK (clamp_mode IN ('CLAMP', 'REJECT')),

    symbol_whitelist         TEXT,   -- JSON array of symbols
    symbol_blacklist         TEXT,   -- JSON array of symbols

    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        (scope = 'GLOBAL' AND strategy_id IS NULL)
        OR (scope = 'STRATEGY' AND strategy_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX ux_risk_settings_scope_strategy
    ON risk_settings (scope, strategy_id);
```

---

### 3. `alerts`

Normalized representation of incoming TradingView alerts.

Key points:

- Stores both normalized fields and the full raw payload.
- Linked to `strategies` where possible; can be strategy-less if not recognized.

```sql
CREATE TABLE alerts (
    id              INTEGER PRIMARY KEY,
    strategy_id     INTEGER
                    REFERENCES strategies(id)
                    ON DELETE SET NULL,

    symbol          TEXT NOT NULL,
    exchange        TEXT,
    interval        TEXT,
    action          TEXT NOT NULL
                    CHECK (action IN ('BUY', 'SELL')),
    qty             REAL,            -- requested size/contracts
    price           REAL,            -- price from alert (if present)

    platform        TEXT NOT NULL DEFAULT 'TRADINGVIEW',
    raw_payload     TEXT NOT NULL,   -- original JSON as text

    received_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    bar_time        TIMESTAMP        -- bar open/close time if provided
);

CREATE INDEX ix_alerts_strategy_time
    ON alerts (strategy_id, received_at);

CREATE INDEX ix_alerts_symbol_time
    ON alerts (symbol, received_at);
```

---

### 4. `orders`

Represents orders derived from alerts, including manual queue, execution mode, and broker linkage.

Key points:

- Every order optionally links back to an `alert` and `strategy`.
- `status` models the lifecycle described in the PRD.
- `mode` distinguishes AUTO vs MANUAL orders at creation time.
- `simulated` distinguishes paper-trading orders from live ones.

```sql
CREATE TABLE orders (
    id                INTEGER PRIMARY KEY,
    alert_id          INTEGER
                      REFERENCES alerts(id)
                      ON DELETE SET NULL,
    strategy_id       INTEGER
                      REFERENCES strategies(id)
                      ON DELETE SET NULL,

    symbol            TEXT NOT NULL,
    exchange          TEXT,

    side              TEXT NOT NULL
                      CHECK (side IN ('BUY', 'SELL')),
    qty               REAL NOT NULL,
    price             REAL,  -- limit price or last known
    order_type        TEXT NOT NULL DEFAULT 'MARKET'
                      CHECK (order_type IN ('MARKET', 'LIMIT')),
    product           TEXT NOT NULL DEFAULT 'MIS'
                      CHECK (product IN ('MIS', 'CNC')),
    gtt               INTEGER NOT NULL DEFAULT 0, -- 0/1

    status            TEXT NOT NULL DEFAULT 'WAITING'
                      CHECK (
                          status IN (
                              'WAITING',
                              'VALIDATED',
                              'SENDING',
                              'SENT',
                              'FAILED',
                              'EXECUTED',
                              'PARTIALLY_EXECUTED',
                              'CANCELLED',
                              'REJECTED'
                          )
                      ),

    mode              TEXT NOT NULL DEFAULT 'MANUAL'
                      CHECK (mode IN ('AUTO', 'MANUAL')),

    zerodha_order_id  TEXT,          -- broker order identifier
    error_message     TEXT,          -- last error, if any
    simulated         INTEGER NOT NULL DEFAULT 0, -- 0/1

    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_orders_strategy_status
    ON orders (strategy_id, status);

CREATE INDEX ix_orders_symbol_time
    ON orders (symbol, created_at);

CREATE INDEX ix_orders_zerodha_order_id
    ON orders (zerodha_order_id);
```

---

### 5. `positions`

Tracks current positions, aggregating open orders and broker state.

Key points:

- One row per `(symbol, product)` combination.
- `pnl` is a cached value for convenience; true P&L can be recomputed if needed.

```sql
CREATE TABLE positions (
    id            INTEGER PRIMARY KEY,
    symbol        TEXT NOT NULL,
    product       TEXT NOT NULL
                  CHECK (product IN ('MIS', 'CNC')),
    qty           REAL NOT NULL,       -- net quantity
    avg_price     REAL NOT NULL,       -- average entry price
    pnl           REAL NOT NULL DEFAULT 0.0,
    last_updated  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX ux_positions_symbol_product
    ON positions (symbol, product);
```

---

### 6. `analytics_trades`

Stores closed trades, linking entry and exit orders for analytics.

Key points:

- Each row represents one closed trade.
- Links to entry and exit `orders` plus the corresponding `strategy`.
- Holds derived metrics like P&L and R-multiple.

```sql
CREATE TABLE analytics_trades (
    id              INTEGER PRIMARY KEY,
    entry_order_id  INTEGER NOT NULL
                    REFERENCES orders(id)
                    ON DELETE CASCADE,
    exit_order_id   INTEGER NOT NULL
                    REFERENCES orders(id)
                    ON DELETE CASCADE,
    strategy_id     INTEGER
                    REFERENCES strategies(id)
                    ON DELETE SET NULL,

    pnl             REAL NOT NULL,   -- realized P&L for the trade
    r_multiple      REAL,            -- R multiple (risk-adjusted return)

    opened_at       TIMESTAMP NOT NULL,
    closed_at       TIMESTAMP NOT NULL
);

CREATE INDEX ix_analytics_trades_strategy_closed_at
    ON analytics_trades (strategy_id, closed_at);
```

---

### 7. Extensibility & PRD Alignment Notes

- **Manual queue**  
  - Orders created in manual mode start with `status = 'WAITING'` and `mode = 'MANUAL'`.  
  - Queue views can filter `orders` by `status = 'WAITING'` and `simulated` as needed.

- **AUTO vs MANUAL execution**  
  - `strategies.execution_mode` defines default behavior per strategy.  
  - `orders.mode` captures the mode in effect at order creation, so mode changes do not retroactively alter old orders.

- **Risk management**  
  - `risk_settings` supports both global and per-strategy rows via `scope` and `strategy_id`.  
  - Core limits from the PRD are represented explicitly:
    - `max_order_value`, `max_quantity_per_order`, `max_daily_loss`, `allow_short_selling`, `max_open_positions`, `symbol_whitelist`, `symbol_blacklist`, and `clamp_mode`.

- **Simulation / paper trading**  
  - `orders.simulated` allows paper trades to flow through the same pipeline as live trades.

- **Analytics**  
  - `analytics_trades` is keyed by `entry_order_id` and `exit_order_id`, enabling reconstruction of trades, P&L curves, and R-multiple analytics.
  - Indexes on `(strategy_id, closed_at)` support per-strategy analytics queries by date range.

- **Future additions (not part of S02 / G01 tasks)**  
  - `users` table for multi-user authentication.  
  - `settings` table for global key/value config (e.g., Zerodha credentials, global app toggles).  
  - Additional indexes once real workloads are observed (for example, on `orders.status, created_at` for dashboard summaries).

