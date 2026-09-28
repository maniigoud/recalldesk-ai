# Backend

FastAPI service for RecallDesk AI. See the [root README](../README.md) for the
project overview and [`../docs/api.md`](../docs/api.md) for the API contract.

```
app/
├── main.py            application, CORS, error handlers, /health
├── api/
│   ├── deps.py        JWT -> current user -> organization scope, service wiring
│   └── routes/        auth, customers, tickets, conversations, support,
│                      memory, dashboard, analytics
├── core/              config, security (bcrypt + JWT), logging, error types
├── db/                async engine/session, declarative base
├── models/            9 MySQL tables + enums
├── schemas/           Pydantic request/response contracts
├── services/
│   ├── hindsight_service.py    the ONLY place that talks to Hindsight
│   ├── agent_service.py         recall -> context -> Groq -> retain pipeline
│   ├── llm_service.py           GroqProvider / DemoLLMProvider
│   ├── auth_service.py · customer_service.py · ticket_service.py
│   ├── conversation_service.py · analytics_service.py
│   └── knowledge_base_service.py
├── tools/             tool registry + 8 agent tools
└── seed/seed_data.py  synthetic demo data
```

## Run

```bash
pip install -r requirements.txt
cp ../.env.example .env     # or .env.example here; edit DATABASE_URL and keys
alembic upgrade head
python -m app.seed.seed_data
uvicorn app.main:app --reload
```

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

No API keys required. `db`-marked tests need `TEST_DATABASE_URL`.
