# Per-Symbol Settings Master CSV (Current Code Reality)

File: `docs/per_symbol_settings_master.csv`

Goal: provide a **single CSV** that lists the **union of all columns** for per-symbol settings that are **already implemented in code today**. This makes it easy to:
- review what per-symbol knobs exist
- prepare data in Excel / Google Sheets
- later implement "import from CSV/XLSX" without inventing new schemas

## How To Use

- Column `record_type` decides which columns are relevant for the row.
- Unused columns for a given `record_type` should be left blank.
- Recommended key columns for most record types:
  - `user_id` (optional for some tables; when blank it means "global/default" where supported)
  - `broker_name`
  - `exchange`
  - `symbol`

## Supported record_type values (implemented)

### 1) SYMBOL_RISK_CATEGORY
Maps to DB table: `symbol_risk_categories` (`backend/app/models/risk_engine.py`)

Used by Risk Engine v2.

Required columns:
- `record_type=SYMBOL_RISK_CATEGORY`
- `broker_name` (typically `zerodha` or `angelone`; `*` is used as a global wildcard in UI logic)
- `exchange` (typically `NSE` or `BSE`; `*` allowed for wildcard)
- `symbol` (e.g. `INFY`; `*` allowed for wildcard/default)
- `risk_category` in `{LC, MC, SC, ETF}`

Optional columns:
- `user_id` (blank means global default row; the UI commonly uses `symbol='*'` + `broker_name='*'` + `exchange='*'` for the default category)

### 2) HOLDING_GOAL
Maps to DB table: `holding_goals` (`backend/app/models/holdings.py`)

Required columns:
- `record_type=HOLDING_GOAL`
- `user_id`
- `broker_name`
- `exchange`
- `symbol`
- `goal_label` in `{CORE, TRADE, THEME, HEDGE, INCOME, PARKING}`
- `goal_review_date` in `YYYY-MM-DD`

Optional columns:
- `goal_target_type` in `{PCT_FROM_AVG_BUY, PCT_FROM_LTP, ABSOLUTE_PRICE}`
- `goal_target_value` (number)
- `goal_note` (string)

### 3) HOLDING_EXIT_SUBSCRIPTION (MVP)
Maps to DB table: `holding_exit_subscriptions` (`backend/app/models/holdings_exit.py`)

Required columns:
- `record_type=HOLDING_EXIT_SUBSCRIPTION`
- `user_id` (blank means "global"; for MVP we expect per-user usage)
- `broker_name` (MVP supports `zerodha` effectively)
- `exchange`
- `symbol`
- `hex_product` (MVP requires `CNC`)
- `hex_trigger_kind` (MVP supports `TARGET_ABS_PRICE` or `TARGET_PCT_FROM_AVG_BUY`)
- `hex_trigger_value` (number)
- `hex_price_source` (MVP requires `LTP`)
- `hex_size_mode` (`ABS_QTY` or `PCT_OF_POSITION`)
- `hex_size_value` (number; for `ABS_QTY` must be an integer)
- `hex_min_qty` (int)
- `hex_order_type` (MVP requires `MARKET`)
- `hex_dispatch_mode` (MVP requires `MANUAL`)
- `hex_execution_target` (`LIVE` or `PAPER`)
- `hex_cooldown_seconds` (int)

Notes:
- This CSV only covers the *create-time* fields. Lifecycle fields like `status`, `pending_order_id`, `next_eval_at` are runtime-managed.

### 4) GROUP_MEMBER
Maps to DB table: `group_members` (`backend/app/models/groups.py`)

Used for baskets/portfolios (group membership is per symbol).

Required columns:
- `record_type=GROUP_MEMBER`
- `group_id` (or `group_name` if you build an import step that resolves names -> ids)
- `exchange`
- `symbol`

Optional columns:
- `group_target_weight` (0.0..1.0)
- `group_notes`
- `group_reference_qty`, `group_reference_price`
- `group_frozen_price`
- `group_weight_locked` (`true`/`false`)
- `group_allocation_amount`, `group_allocation_qty`

## What This CSV Does NOT Include

These are either not per-symbol, or not intended to be user-imported:
- runtime state tables (e.g. `execution_policy_state`, `positions`, `managed_risk_positions`)
- event/log tables (`*_events`, decision logs)
- broker instrument master tables (`securities`, `broker_instruments`, etc.)

