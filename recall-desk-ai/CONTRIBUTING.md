# Contributing

Thanks for looking at RecallDesk AI.

## Rules that keep the project honest

1. **No secrets, ever.** `GROQ_API_KEY`, `HINDSIGHT_API_KEY` and `JWT_SECRET_KEY`
   come from the environment. Only `.env.example` is committed, and it is empty.
2. **Hindsight is the memory layer.** All Hindsight calls live in
   `backend/app/services/hindsight_service.py`. Do not scatter them through the
   app, and do not mirror memories into MySQL.
3. **MySQL is application state, not a memory engine.** `memory_events` is an
   audit log for observability only.
4. **Routes stay thin.** No database queries, no Groq calls and no Hindsight
   calls in route handlers - routes call services, services own the logic.
5. **The LLM never touches the database.** It emits tool calls; the tool registry
   validates them, checks the caller's role and calls the service layer.
6. **Never fake a result.** Dashboard numbers come from real counts, memory
   counts come from Hindsight, and demo providers are labelled (`demo_mode: true`)
   in every response. `APP_ENV=production` refuses to start without credentials.
7. **No SQLite.** MySQL 8 only, migrations via Alembic - never hand-edited tables.

## Local development

```bash
cd backend
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
python -m app.seed.seed_data
uvicorn app.main:app --reload
```

## Before you open a pull request

```bash
ruff check app tests migrations --select E9,F,B --ignore B008
pytest
```

`pytest` passes without any API keys. Tests marked `@pytest.mark.db` need
`TEST_DATABASE_URL` pointing at a MySQL test database and skip themselves
otherwise.

## Adding an agent tool

1. Add a `ToolDefinition` in `backend/app/tools/` with a JSON schema, a handler
   and an explicit `roles` tuple.
2. Register it in `AgentService._build_registry`.
3. Make sure the handler calls a service, validates its arguments and returns a
   JSON-serialisable result.
4. Cover it in `tests/test_knowledge_and_tools.py` (permissions, invalid input,
   handler error).
