# Database Migrations (Alembic)

Stage 2 replaced the original `create_all` migration shim with genuine,
versioned Alembic migrations.

## Migration chain
| Revision | Contents |
|---|---|
| `001_baseline` | Full current schema: 14 tables + their indexes (generated with Alembic autogenerate from the SQLAlchemy models; verified drift-free with `alembic check`). |
| `002_txn_indexes` | Additive composite indexes on `transactions`: `(user_id, type, date)`, `(user_id, currency, type)`, `(user_id, category_name, date)`. |
| `003_health_snapshots` | Stage 3: `health_score_snapshots` table (one health-score reading per user/day). |
| `004_subs_calendar` | Stage 4: `subscription_overrides` (confirm/dismiss/edit per normalised merchant) + `payment_reminders`. |
| `005_statement_imports` | Stage 5: `statement_imports` audit table (counts and filename only, never statement contents). |
| `006_memory_notifications` | Stage 7: `user_memories` (user-owned financial memory) + `notifications` (proactive briefings, deduplicated). |

## Fresh database
```bash
cd backend
DATABASE_URL=<your-url> alembic upgrade head
```

## Existing database (created before migrations, e.g. by the seed script)
Such databases have the tables but **no** `alembic_version` row. Do NOT run
`upgrade head` blindly and never drop/recreate the database. Instead:

```bash
cd backend
# 1. Back up first (SQLite example):
cp finsight.db finsight.db.backup
# 2. Stamp the database at the baseline (records the revision, changes no data):
DATABASE_URL=sqlite:///./finsight.db alembic stamp 001_baseline
# 3. Apply the remaining migrations:
DATABASE_URL=sqlite:///./finsight.db alembic upgrade head
```

This procedure was tested on a copy of the live development database
(3 users, 396 transactions): row counts identical before/after, only the
new indexes and the version row were added.

Databases that were stamped with the retired shim revision `001_initial`
should be re-stamped: `alembic stamp 001_baseline --purge`, then
`alembic upgrade head`.

## Rollback limitations
- `002_txn_indexes` downgrade is safe and lossless (drops only indexes).
- `003`–`006` downgrades drop their own stage's tables; those tables hold user-entered data (overrides, reminders, memories), so in production restore from backup instead of downgrading.
- Verification status: chain 001→006 verified on clean SQLite (upgrade, drift check, downgrade-to-003 + re-upgrade round-trip). Migrations 001–003 were additionally verified on a real PostgreSQL 16 server during Stages 2–3; 004–006 are additive `create_table` migrations in the same style and were verified on SQLite (PostgreSQL was not re-run for 004–006 because the verification VM's package mirror was unavailable to reinstall it).
- `001_baseline` downgrade **drops all tables** — it exists for disposable
  dev/test databases only. Never run `alembic downgrade base` against a
  database containing real data; restore from backup instead.
- Downgrading across a future data-migration revision will follow that
  revision's own documented policy.

## Verification performed (2026-11-01)
- Clean SQLite: `upgrade head` → 15 tables, `alembic check` = no drift.
- Clean **PostgreSQL 16** (real server): `upgrade head`, `alembic check`,
  `downgrade -1` → `upgrade head` round-trip, plus a full application
  smoke test (register → CSV import → analytics → forecast → intelligence
  overview) with results identical to SQLite.
- Existing-database stamp procedure: see above.
- `scripts/verify.sh` runs the migration stage on every verification.
