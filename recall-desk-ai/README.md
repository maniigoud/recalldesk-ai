# RecallDesk AI

> A customer-support AI agent that remembers what matters across conversations.

**Support that remembers.**

RecallDesk AI is a support workspace (React/TypeScript frontend + FastAPI backend)
whose AI agent keeps persistent per-customer memory using
[Hindsight](https://github.com/vectorize-io/hindsight). The agent recalls what
it learned in earlier sessions, answers with that context, and writes back only
the information worth keeping.

MySQL stores the structured work (customers, tickets, conversations, resolutions).
**Hindsight stores the memory.** Groq does the reasoning. Never the reverse.

---

## Why I built this

Most AI agents are good at using the current conversation.

The problem starts when the conversation ends.

A customer explains their stack, their limits, the incident they had last month.
The transcript is gone. Next session the agent starts from zero and asks the same
questions again. Support teams end up being the memory, and every new agent has
to be re-taught everything.

RecallDesk AI makes memory an actual layer of the agent architecture. The
interesting part is not "store the chat log" - it is deciding **what** to
retain, **which** memory is relevant right now, and **how** to scope memory to
one customer so it can never bleed into another account.

---

## Demo

<!-- Replace with your demo GIF or YouTube link -->

```
Conversation 1  ->  RETAIN  ->  new session  ->  RECALL  ->  memory-aware reply
```

A 30–60 second screen recording showing `memories_recalled: 0` in the first
session and `memories_recalled: 4` in the second is the single most convincing
artifact for this project.

---

## Architecture

```
User
  |
  v
React + TypeScript frontend  (:5173 Vite / :3000 Next.js)
  |
  v
FastAPI backend  (:8000)
  |
  +--> MySQL 8 ........... customers, tickets, conversations, messages,
  |                        resolutions, agent_runs, memory_events (audit only)
  |
  +--> Hindsight .......... RETAIN / RECALL / REFLECT   <- the core feature
  |
  +--> Groq ............... reasoning + tool calling (stateless)
  |
  +--> Knowledge base ..... RecallDesk's own product docs
  |
  v
Response + memory observability metadata
```

```mermaid
flowchart LR
  U[Customer message] --> F[FastAPI route]
  F --> S[Agent service]
  S --> DB[(MySQL 8)]
  S -->|RECALL| H[Hindsight]
  H -->|memories| S
  S -->|context| G[Groq]
  G -->|tool calls| T[Tool registry]
  T --> S
  G --> A[Answer]
  S --> DB
  S -->|RETAIN durable facts| H
  S --> A
  A --> UI[Frontend]
```

Detailed write-up: [`docs/architecture.md`](docs/architecture.md).

---

## How Memory Works

### 1. RETAIN

After every useful exchange, a second LLM pass classifies the turn and returns
only durable information. Nothing else is stored.

```json
{"memories": [
  {"type": "fact",       "content": "Arjun Technologies runs its API on AWS RDS with PostgreSQL 16."},
  {"type": "fact",       "content": "Arjun Technologies has an RDS connection limit of 100 connections."},
  {"type": "preference", "content": "Arjun Technologies prefers detailed technical explanations in writing."},
  {"type": "experience", "content": "A previous API timeout at Arjun Technologies was caused by connection-pool exhaustion."},
  {"type": "resolution", "content": "Increasing the connection pool size resolved the previous timeout incident."}
]}
```

`"thanks"`, `"ok"` and restated questions are discarded. The extracted facts go
to Hindsight in one retained document tagged with the customer, and the
retain/recall calls are recorded in the `memory_events` audit table.

### 2. RECALL

A new conversation starts. The new message is sent to Hindsight, which runs
semantic + keyword + graph + temporal retrieval and returns the few relevant
memories. Only those (a token budget, not the whole bank) are added to the agent
context before Groq is called.

```
"Our API is timing out again."
        |
        v
   Hindsight RECALL  ->  "PostgreSQL 16 on RDS", "connection limit 100",
                          "previous timeout caused by pool exhaustion"
        |
        v
   agent context = live customer record + these memories + knowledge base
        |
        v
   Groq -> "This looks similar to the timeout your team hit before..."
```

The agent never says *my memory system told me*. It just uses what it knows.

### 3. REFLECT

`POST /api/memory/reflect` asks Hindsight to reason over everything accumulated
for a customer instead of returning facts - useful for questions like *"what
patterns have we seen with this account?"*. The response includes the memories
the answer was based on.

### 4. Scoping

One memory bank for the product (`recall-desk-ai`), one tag per customer.

> A multi-tag Hindsight filter is an **OR**: `["customer:1", "org:1"]` returns
> every memory in the organization. RecallDesk passes only
> `tags=["customer:<id>"]` with `tags_match="any_strict"`, and additionally drops
> any result whose owning customer does not match. This was found by testing
> against the live API, not assumed.

---

## Before vs After

### Without persistent memory

```
Conversation 1
  Customer: "We deploy our API to AWS RDS using PostgreSQL 16. Connection limit is 100."
  Agent:    "Noted."

Conversation 2 (new session)
  Customer: "Our API is timing out again."
  Agent:    "Which database are you using? What is your connection limit?"
```

### With RecallDesk AI

```
Conversation 1
  Customer: "We deploy our API to AWS RDS using PostgreSQL 16. Connection limit is 100."
                 |
                 v
            Hindsight RETAIN
                 |
Conversation 2 (new session, empty transcript)
  Customer: "Our API is timing out again."
                 |
                 v
            Hindsight RECALL  -> PostgreSQL 16, RDS, limit 100, prior pool incident
                 |
                 v
  Agent: "This looks similar to the timeout your team hit before. With a 100
          connection limit on RDS, connection-pool exhaustion is the first thing
          to check..."
```

The new session transcript is empty - memory lives in Hindsight, not in the chat log.

---

## Tech Stack

- React, TypeScript, Tailwind (frontend in [`frontend/`](frontend/))
- FastAPI, Python 3.11, Pydantic v2
- MySQL 8 (async via SQLAlchemy 2.x + aiomysql), Alembic migrations
- JWT authentication, bcrypt password hashing, role-based access (`admin` / `agent` / `viewer`)
- Groq (`openai/gpt-oss-120b` by default) for chat completions and tool calling
- Hindsight for persistent agent memory (`retain` / `recall` / `reflect`)
- pytest, ruff

---

## Hindsight Integration

Hindsight is **the** central technical feature of this project, not a
decorative dependency. The production path is:

```
RecallDesk  ->  Hindsight  ->  RETAIN / RECALL / REFLECT  ->  customer memory
```

| File | Role |
| --- | --- |
| [`backend/app/services/hindsight_service.py`](backend/app/services/hindsight_service.py) | The **only** place that talks to Hindsight. Official `hindsight-client`, `retain` / `recall` / `reflect` / `list_memories`, bank creation, per-customer tagging, cross-customer filtering, health probe. |
| [`backend/app/services/agent_service.py`](backend/app/services/agent_service.py) | The agent pipeline: recall before answering, extract durable memory, retain after answering. |

The application uses Hindsight for:

- persistent customer memory
- customer-scoped recall (tags + `any_strict` + post-filter)
- selective durable-memory retention (not every message)
- memory reflection over accumulated experience

### Honest note on the fallback provider

When `HINDSIGHT_API_KEY` is not set, the backend runs an in-process
`DemoMemoryProvider` so the CRUD and dashboard still work locally. It is **not**
a mock of the integration path: the real provider is used automatically as soon
as credentials exist, every response reports `memory_provider` and `demo_mode`,
`/health` reports `unconfigured`, and `APP_ENV=production` refuses to start
without credentials. The same applies to the LLM (`GroqProvider` /
`DemoLLMProvider`).

---

## API

Base URL `http://localhost:8000` · Swagger `/docs` · ReDoc `/redoc`

### System

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Truthful status of database, Hindsight, Groq |
| `GET` | `/health/detailed` | Live Hindsight probe and active providers |

### Memory

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/memory/recall` | Hindsight recall for a customer |
| `POST` | `/api/memory/retain` | Retain information into customer memory |
| `POST` | `/api/memory/reflect` | Reflect over accumulated memory |
| `GET` | `/api/customers/{id}/memories` | Memory Explorer (paged, filtered) |

### AI support

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/support/chat` | The agent run: recall → context → Groq → retain |

Example request:

```json
{ "customer_id": 1, "conversation_id": 10, "message": "Our API is timing out again." }
```

Example response (trimmed):

```json
{
  "conversation_id": 11,
  "message": "This looks similar to the timeout your team hit before...",
  "memories_recalled": 4,
  "memory_retained": true,
  "memory_provider": "hindsight",
  "tools_used": ["get_customer_tickets", "search_knowledge_base"],
  "model": "openai/gpt-oss-120b",
  "demo_mode": false,
  "latency_ms": 2310
}
```

`memories_recalled`, `tools_used` and `memory_retained` are what makes the
memory workflow visible in the UI during a demo.

### Application

| Method | Path |
| --- | --- |
| `POST` | `/api/auth/register`, `/api/auth/login`, `GET /api/auth/me` |
| `GET/POST/PUT/DELETE` | `/api/customers`, `/api/customers/{id}` |
| `GET/POST/PUT/DELETE` | `/api/tickets`, `/api/tickets/{id}` |
| `GET/POST` | `/api/customers/{id}/conversations` |
| `GET/POST` | `/api/conversations/{id}/messages` |
| `GET` | `/api/dashboard`, `/api/analytics` |

Full request/response examples: [`docs/api.md`](docs/api.md).

---

## Environment Variables

Copy `.env.example` to `backend/.env` and fill it in. **Never commit your real
API keys.**

```
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b

HINDSIGHT_API_URL=https://api.hindsight.vectorize.io
HINDSIGHT_API_KEY=
HINDSIGHT_BANK_ID=recall-desk-ai

DATABASE_URL=mysql+aiomysql://root:password@localhost:3306/recall_desk
JWT_SECRET_KEY=change-me
CORS_ORIGINS=http://localhost:5173
```

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | yes | MySQL only. SQLite is not supported. |
| `JWT_SECRET_KEY` | yes | Long random value in production. |
| `HINDSIGHT_API_URL` | for memory | Cloud or self hosted. |
| `HINDSIGHT_API_KEY` | for memory | `hsk_...` |
| `HINDSIGHT_BANK_ID` | no | Default `recall-desk-ai`; created on startup. |
| `GROQ_API_KEY` | for real answers | Without it the LLM is a labelled demo provider. |
| `CORS_ORIGINS` | no | Comma separated list of allowed origins. |

`.env` is gitignored. Only `.env.example` is committed, and it has no secrets.

---

## Running Locally

### Backend

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
cp .env.example .env          # then edit DATABASE_URL, JWT_SECRET_KEY, API keys
alembic upgrade head
python -m app.seed.seed_data
uvicorn app.main:app --reload
```

Windows activation: `.venv\Scripts\activate` · macOS/Linux: `source .venv/bin/activate`

- API <http://localhost:8000> · Swagger <http://localhost:8000/docs> · ReDoc <http://localhost:8000/redoc>

Demo credentials (development only, fictional):

```
demo@recalldesk.local / DemoPassword123!
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server origin must be present in `CORS_ORIGINS` (`http://localhost:5173`
for Vite, `http://localhost:3000` for the Next.js build in this repo).

### Docker

```bash
docker compose up --build     # MySQL + backend (migrations + seed run automatically)
```

Hindsight stays external: pass `HINDSIGHT_API_URL` / `HINDSIGHT_API_KEY` through
the environment.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite runs with **no API keys**. Tests marked `db` need a MySQL test
database and skip themselves when one is not reachable:

```bash
export TEST_DATABASE_URL="mysql+aiomysql://root:<password>@localhost:3306/recall_desk_test"
pytest
```

---

## Demo Flow

The full walkthrough - including the exact two messages that demonstrate
retain → new session → recall - is in [`docs/demo.md`](docs/demo.md).

```
1. log in                              POST /api/auth/login
2. pick Arjun Technologies             GET  /api/customers?search=Arjun
3. session 1: "AWS RDS, PostgreSQL 16, connection limit 100"
                                           -> memories_recalled: 0, memory_retained: true
4. session 2 (no conversation_id): "Our API is timing out again."
                                           -> memories_recalled: > 0, contextual answer
5. GET /api/customers/1/conversations   -> two distinct session_ids
6. POST /api/memory/reflect             -> patterns across both sessions
```

---

## Screenshots

<!-- Add your screenshots to ./screenshots and reference them here -->

| File | What it shows |
| --- | --- |
| `screenshots/dashboard.png` | Dashboard with real ticket/memory counts |
| `screenshots/retain.png` | A support run that retained memory |
| `screenshots/recall.png` | A new session recalling previous context |
| `screenshots/memory-flow.png` | Retain → new session → recall diagram |
| `docs/architecture.png` | Architecture diagram |

---

## What I learned

Persistent memory is not just storing chat history.

The important questions are:

- **What should be retained?** Most of a conversation is disposable. "Thanks,
  got it" is not memory; "PostgreSQL 16 on RDS with a 100 connection limit" is.
- **Which memory is relevant now?** Hindsight does multi-strategy retrieval, and
  the agent gets a token-budgeted slice, never the whole bank.
- **How should memory be scoped?** Tags are not a one-liner: an OR of two tags
  silently leaks one customer's facts into another's context. That bug was found
  by testing against the live API, not by reading docs.
- **How do you observe memory?** Every retain/recall/reflect is recorded, and
  every AI response reports what was recalled, which tools ran and whether
  memory was written - otherwise memory behaviour is invisible and undebuggable.
- **Where does state end and memory begin?** A conversation session is
  disposable state; Hindsight is durable knowledge. MySQL is not a memory engine
  and is not allowed to become one.

RecallDesk AI treats memory as a separate layer of the agent architecture, not
as a longer prompt.

---

## Learn More

- Hindsight: <https://github.com/vectorize-io/hindsight>
- Hindsight documentation: <https://hindsight.vectorize.io/>
- What is agent memory: <https://vectorize.io/what-is-agent-memory>

---

## License

[MIT](LICENSE) · Demo data is synthetic; all companies and people are fictional.
