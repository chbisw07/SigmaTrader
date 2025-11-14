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

