## SigmaTrader (ST)

SigmaTrader is a trading companion app that turns **TradingView alerts** into **Zerodha (Kite)** orders with:

- **Auto & Manual execution modes**
- **Waiting queue** for reviewing and editing orders before sending
- **Risk management layer** (position limits, capital limits, daily loss, short-sell protection)
- **Order tracking & status sync** with Zerodha
- **Trade analytics** for strategy-level performance insights

Architecture:

- **Backend:** Python, FastAPI, SQLAlchemy, Zerodha Kite Connect
- **Frontend:** React, TypeScript, Material UI
- **Database:** SQLite

Goal: a safe, transparent, and extensible way to bridge TradingView strategies with live execution and analytics.

### Getting started

#### Backend (FastAPI)

Prerequisites:

- Python 3.10+ (Python 3.12 recommended)

Setup and run:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Run backend tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

Database migrations (Alembic):

- To create or upgrade the local SQLite schema using the ORM models:

  ```bash
  cd backend
  source .venv/bin/activate
  alembic upgrade head
  ```

- To generate a new migration after changing models:

  ```bash
  cd backend
  source .venv/bin/activate
  alembic revision --autogenerate -m "describe your change"
  alembic upgrade head
  ```

Code quality (backend):

- Format and sort imports with Black/isort:

  ```bash
  cd backend
  source .venv/bin/activate
  black app tests
  isort app tests
  ```

- Lint with Ruff:

  ```bash
  cd backend
  source .venv/bin/activate
  ruff check app tests
  ```

- Optional: install and run `pre-commit` hooks from the repo root:

  ```bash
  cd backend
  source .venv/bin/activate
  pre-commit install
  # then on each commit, hooks will run automatically
  # or run manually:
  pre-commit run --all-files
  ```

#### Frontend (React + TypeScript)

Frontend code lives under `frontend/` and is built with Vite, React, TypeScript, Material UI, React Router, and Vitest.

Setup and run:

```bash
cd frontend
npm install
npm run dev
```

Then open the URL printed by Vite (by default `http://localhost:5173`). The app expects the backend to be available at `http://localhost:8000`; in development, Vite will proxy `/health` calls directly to the backend URL configured in `vite.config.ts` (to be wired in a later sprint if needed).

Run frontend tests:

```bash
cd frontend
npm test
```

Admin UI (strategies & risk settings):

- The **Settings** page includes a read-only view of:
  - Strategies loaded from `GET /api/strategies/`.
  - Risk settings loaded from `GET /api/risk-settings/`.
- In development, Vite proxies `/api` calls to the FastAPI backend on `http://localhost:8000`.

Code quality (frontend):

- Lint with ESLint:

  ```bash
  cd frontend
  npm run lint
  ```

- Format with Prettier:

  ```bash
  cd frontend
  npm run format
  ```

#### Marketing website (local)

A standalone, local-first marketing website lives under `website/` (separate from the main app UI in `frontend/`).

Setup and run (from repo root):

```bash
npm -C website install
npm -C website run roadmap:generate
npm -C website run dev
```

Then open `http://localhost:5174/`.

If you are currently inside `frontend/`, use `../website` instead:

```bash
npm -C ../website install && npm -C ../website run dev
```

### Docs

- TradingView webhook setup and templates: `docs/tradingview_alerts.md`
