# Architecture

## The problem

A support agent that forgets is a chatbot. Every new session starts from zero:
the agent re-asks for the database engine, re-explains rate limits, and
re-diagnoses an incident the team fixed eight weeks ago.

## The solution

RecallDesk AI keeps three kinds of knowledge apart and uses the right store for each:

| Store | Holds | Never holds |
| --- | --- | --- |
| **MySQL 8** | Users, organizations, customers, tickets, conversations, messages, resolutions, agent runs, memory audit events | Learned customer memory |
| **Hindsight** | Durable customer memory: facts, preferences, incidents, successful resolutions | Application state, credentials, other customers' data |
| **Knowledge base** | RecallDesk's own product documentation | Anything customer specific |
| **Groq** | Reasoning over the context above | Memory (it is stateless) |

## Request flow

```
Customer message
      |
      v
FastAPI route  ->  service layer  (routes never touch the DB or an external API)
      |
      v
1. authenticate (JWT) and resolve organization
2. validate customer + conversation
3. store the user message in MySQL
      |
      +--> 4. Hindsight RECALL  (tags: customer:<id>, tags_match=any_strict)
      |
      +--> 5. MySQL context: customer record, recent tickets, recent messages
      |
      +--> 6. knowledge base snippets for the question
      |
      v
7. build one prompt: system prompt + live record + recalled memories + KB + message
8. Groq chat completion with 8 tool schemas
9. tool calls are executed by the ToolRegistry (validation, role checks, services)
      -> back to Groq, up to AGENT_MAX_TOOL_ITERATIONS
10. final answer
      |
      +--> 11. store the assistant message in MySQL
      |
      +--> 12. memory extraction: which parts of this turn are durable?
      |
      +--> 13. Hindsight RETAIN (only the extracted durable facts)
      |
      +--> 14. memory_events row (retain + recall)
      +--> 15. agent_runs row (model, latency, tokens, status)
      v
16. response + observability metadata
```

## Layers

```
app/
├── api/          HTTP layer: routing, auth dependencies, status codes
│   ├── deps.py       JWT -> current user -> organization scope; service wiring
│   └── routes/       auth, customers, tickets, conversations, support, memory,
│                     dashboard, analytics
├── services/     Business logic. The only layer that talks to MySQL,
│                 Hindsight, Groq or the knowledge base.
├── tools/        Agent tool definitions (schema, roles, handler)
├── models/       SQLAlchemy ORM models
├── schemas/      Pydantic request/response contracts
├── core/         config, security (bcrypt + JWT), logging, error types
├── db/           engine/session and declarative base
└── seed/         synthetic demo data
```

Rules enforced in code review:

* No database queries in route handlers.
* No Hindsight or Groq calls in route handlers.
* The LLM never receives a database connection; it can only request a tool call.
* Secrets come from the environment only.

## Security

* Passwords hashed with bcrypt (direct `bcrypt` library, no deprecated passlib wrapper).
* JWT access tokens carry `sub`, `role`, `organization_id`, `exp`, `type`, `iss`.
* Every query is organization scoped; a user in organization A cannot read
  organization B's customers, tickets, conversations or memories.
* Structured JSON logging with redaction of `password`, `token`, `*_api_key`,
  `secret` keys. Stack traces are logged server side and never returned.
* CORS origins are configurable; the Vite dev server is allowed by default.
* API keys (Groq, Hindsight) live only in the backend environment.
