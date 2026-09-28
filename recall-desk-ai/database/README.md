# Database

The RecallDesk AI backend uses **MySQL 8** only. SQLite is intentionally not supported.

## Create the database

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS recall_desk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS recall_desk_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

`recall_desk_test` is only used by the pytest suite (see `TEST_DATABASE_URL`).

## Schema

All tables are created by **Alembic migrations**, never by hand.

| Table | Purpose |
| --- | --- |
| `organizations` | Tenant boundary; every row in the product belongs to one |
| `users` | Support agents, admins and viewers (bcrypt password hash) |
| `customers` | Customer accounts (unique email per organization) |
| `tickets` | Support tickets with status, priority and assignment |
| `conversations` | A session (`session_id`) between a customer and the agent |
| `messages` | Messages inside one session |
| `resolutions` | What fixed a ticket and whether it worked |
| `memory_events` | Audit log of Hindsight retain/recall/reflect calls |
| `agent_runs` | One row per AI agent execution (model, latency, tokens, status) |

### What is NOT in MySQL

Customer memory itself is not duplicated here. Hindsight owns the facts,
preferences, incidents and resolutions that the agent remembers; MySQL keeps
structured application state and an audit trail of memory operations.

## Migrations

```bash
cd backend
alembic upgrade head                 # apply
alembic downgrade -1                 # roll back one revision
alembic revision --autogenerate -m "describe change"
alembic current                      # show applied revisions
alembic history                      # show the revision graph
```

`alembic.ini` intentionally contains no credentials: `migrations/env.py` reads
`DATABASE_URL` from the environment.
