# PostgreSQL Development Environment Setup (Kubuntu 24.04 LTS)

This document describes how to install and prepare a **PostgreSQL development environment** on **Kubuntu 24.04 LTS**, suitable for migrating an existing SQLite-based application (e.g., SigmaTrader) to PostgreSQL.

The goal is to:
- Install PostgreSQL server
- Create a clean application database and user
- Install client and GUI tools
- Prepare the system so application-level migration work can begin safely

---

## 1. Install PostgreSQL Server

Update package lists and install PostgreSQL:

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
```

Verify that PostgreSQL is running:

```bash
systemctl status postgresql --no-pager
```

You should see the service in an `active (running)` state.

---

## 2. Access PostgreSQL Shell (Admin)

PostgreSQL creates a default Linux user and DB role called `postgres`.

Switch to the postgres user and open the psql shell:

```bash
sudo -u postgres psql
```

Exit the shell:

```sql
\q
```

---

## 3. Create Application User and Database

It is best practice to use a **dedicated DB user** for the application.

Example (adjust names as needed):

```bash
sudo -u postgres psql -c "CREATE USER sigmatrader WITH PASSWORD 'CHANGE_ME_STRONG';"
```

Create the database and assign ownership:

```bash
sudo -u postgres psql -c "CREATE DATABASE sigmatrader_db OWNER sigmatrader;"
```

Grant privileges on the default schema:

```bash
sudo -u postgres psql -d sigmatrader_db -c "GRANT ALL ON SCHEMA public TO sigmatrader;"
```

---

## 4. Test Database Connectivity

Test login using TCP (recommended for app usage):

```bash
psql "postgresql://sigmatrader:CHANGE_ME_STRONG@localhost:5432/sigmatrader_db"
```

Run a quick check:

```sql
SELECT version();
```

Exit with `\q`.

---

## 5. Authentication Model (Notes)

On Ubuntu/Kubuntu:
- **Local socket connections** use `peer` authentication by default
- **TCP localhost connections** use password-based authentication (`scram-sha-256`)

For application development, always prefer:

```
postgresql://user:password@localhost:5432/dbname
```

This avoids peer-auth confusion and matches production patterns.

---

## 6. Optional but Useful PostgreSQL Extensions

Enable commonly used extensions (only if required by your schema):

```bash
sudo -u postgres psql -d sigmatrader_db -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
sudo -u postgres psql -d sigmatrader_db -c "CREATE EXTENSION IF NOT EXISTS citext;"
```

Notes:
- `pgcrypto` → UUIDs, hashing
- `citext` → case-insensitive text columns

---

## 7. Install PostgreSQL Client Tools

### Command-line client

```bash
sudo apt install -y postgresql-client
```

### Enhanced CLI (optional but recommended)

```bash
sudo apt install -y pgcli
```

Usage:

```bash
pgcli postgresql://sigmatrader@localhost:5432/sigmatrader_db
```

Provides:
- Autocomplete
- Syntax highlighting
- Command history

---

## 8. Install GUI Database Browser (DBeaver Community Edition)

DBeaver is used as a **SQLite Browser–like GUI** for PostgreSQL and SQLite side-by-side.

Install via Snap:

```bash
sudo snap install dbeaver-ce
```

Launch:

```bash
dbeaver-ce
```

Typical usage:
- Open existing SQLite database
- Open PostgreSQL database
- Compare schemas, row counts, and data visually

---

## 9. Environment Variable for Applications

Set the database URL used by your application (example for SQLAlchemy):

```bash
export DATABASE_URL="postgresql+psycopg://sigmatrader:CHANGE_ME_STRONG@localhost:5432/sigmatrader_db"
```

Or add to `.env`:

```
DATABASE_URL=postgresql+psycopg://sigmatrader:CHANGE_ME_STRONG@localhost:5432/sigmatrader_db
```

---

## 10. Python Driver (If Applicable)

Recommended PostgreSQL driver for Python:

```bash
pip install "psycopg[binary]"
```

(Use non-binary build with `libpq-dev` if you prefer system-linked libraries.)

---

## 11. Readiness Checklist

Before starting migration work:

- [ ] PostgreSQL service running
- [ ] Application DB and user created
- [ ] Able to connect via connection string
- [ ] DBeaver opens PostgreSQL DB successfully
- [ ] Environment variable configured

At this point, the system is **ready for schema and data migration**.

---

## 12. Next Phase (Out of Scope Here)

- Schema creation via ORM / migrations
- Data copy from SQLite → PostgreSQL
- Constraint, index, and type verification
- Application-level testing

These steps are intentionally left to automated migration tooling or Codex-driven changes.

---

**Document status:** Stable reference for local PostgreSQL dev setup on Kubuntu 24.04 LTS
