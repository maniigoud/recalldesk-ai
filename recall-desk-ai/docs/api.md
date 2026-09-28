# API contract

Base URL: `http://localhost:8000`
Swagger: `http://localhost:8000/docs` · ReDoc: `http://localhost:8000/redoc`
OpenAPI JSON: `http://localhost:8000/openapi.json`

Authenticated endpoints need `Authorization: Bearer <access_token>`.

## Error format

Every error (validation, auth, not found, upstream failure) uses one shape:

```json
{ "error": { "code": "CUSTOMER_NOT_FOUND", "message": "Customer 1 was not found." } }
```

| Code | HTTP |
| --- | --- |
| `VALIDATION_ERROR` | 422 |
| `AUTHENTICATION_FAILED` | 401 |
| `FORBIDDEN` | 403 |
| `CUSTOMER_NOT_FOUND` / `TICKET_NOT_FOUND` / `CONVERSATION_NOT_FOUND` | 404 |
| `CONFLICT` (e.g. `EMAIL_ALREADY_EXISTS`) | 409 |
| `HINDSIGHT_ERROR`, `LLM_ERROR` | 503 |
| `HINDSIGHT_NOT_CONFIGURED`, `LLM_NOT_CONFIGURED` | 503 |
| `DATABASE_ERROR`, `INTERNAL_ERROR` | 500 |

---

## Authentication

### `POST /api/auth/register`

```json
{ "name": "Priya Raman", "email": "demo@recalldesk.local", "password": "DemoPassword123!",
  "organization_name": "RecallDesk Demo Workspace", "role": "agent" }
```

`201`:

```json
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600,
  "user": { "id": 1, "name": "Priya Raman", "email": "demo@recalldesk.local",
            "role": "admin", "organization_id": 1, "created_at": "2026-09-28T09:00:00" } }
```

### `POST /api/auth/login`

```json
{ "email": "demo@recalldesk.local", "password": "DemoPassword123!" }
```

Returns the same `TokenResponse`. Wrong credentials -> `401 AUTHENTICATION_FAILED`.

### `GET /api/auth/me`

Returns the `UserRead` object for the current token.

---

## Customers

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/customers` | `search`, `status`, `limit`, `offset`, `sort_by`, `sort_dir` |
| POST | `/api/customers` | `{ name, email, company?, status? }` |
| GET | `/api/customers/{id}` | detail + summary |
| PUT | `/api/customers/{id}` | partial update |
| DELETE | `/api/customers/{id}` | `204` |

`GET /api/customers` response:

```json
{ "items": [ { "id": 1, "name": "Arjun Mehta", "email": "arjun.mehta@arjuntech.example",
               "company": "Arjun Technologies", "status": "active",
               "organization_id": 1 } ],
  "total": 12, "limit": 25, "offset": 0 }
```

`GET /api/customers/{id}` detail:

```json
{ "id": 1, "name": "Arjun Mehta", "company": "Arjun Technologies", "status": "active",
  "ticket_count": 4, "open_ticket_count": 2, "resolved_ticket_count": 2,
  "conversation_count": 3, "message_count": 12,
  "memory_count": 7, "memory_count_capped": false, "memory_provider": "hindsight",
  "recent_tickets": [ { "id": 3, "title": "API latency spikes", "status": "resolved",
                        "priority": "critical", "created_at": "...", "resolved_at": "..." } ],
  "recent_memories": [ { "id": "abc", "content": "...", "type": "world",
                         "relevance": 0.87, "source": "hindsight" } ] }
```

`memory_count` comes from Hindsight (tag filtered) - never a placeholder.
`memory_count_capped: true` means "at least 200".

---

## Tickets

| Method | Path |
| --- | --- |
| GET | `/api/tickets?status=&priority=&customer_id=&assigned_to=&search=` |
| POST | `/api/tickets` |
| GET | `/api/tickets/{id}` |
| PUT | `/api/tickets/{id}` |
| DELETE | `/api/tickets/{id}` |

Create:

```json
{ "customer_id": 1, "title": "API latency spikes", "description": "...",
  "priority": "high", "status": "open", "assigned_to": 2 }
```

Update (optionally records/updates the resolution in the same call):

```json
{ "ticket": { "status": "resolved" },
  "resolution": { "summary": "Pool exhaustion was the root cause",
                  "solution": "Raised max_connections to 400 and added pgbouncer.",
                  "successful": true } }
```

Detail adds `customer_name`, `customer_email`, `assignee_name`, `conversation_count`
and the `resolutions` array.

Statuses: `open`, `investigating`, `waiting`, `resolved`, `escalated`.
Priorities: `low`, `medium`, `high`, `critical`.

---

## Conversations

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/customers/{id}/conversations` | paged, includes `message_count` |
| POST | `/api/customers/{id}/conversations` | creates a new `session_id` |
| GET | `/api/conversations/{id}` | detail with messages |
| GET | `/api/conversations/{id}/messages` | message list |
| POST | `/api/conversations/{id}/messages` | append a message |

```json
{ "id": 10, "customer_id": 1, "ticket_id": 3, "session_id": "3f1c…",
  "created_at": "...", "updated_at": "...", "message_count": 2 }
```

A new session never deletes persistent memory.

---

## AI support

### `POST /api/support/chat`

```json
{ "customer_id": 1, "conversation_id": 10, "message": "Our API is timing out again." }
```

`conversation_id` is optional - omit it to start a new session.
`persist: false` runs a read-only preview against an existing conversation.

```json
{
  "conversation_id": 11,
  "session_id": "9ab2…",
  "message": "This looks similar to the timeout your team hit in June...",
  "memories_recalled": 4,
  "memory_retained": true,
  "memory_provider": "hindsight",
  "llm_provider": "groq",
  "model": "openai/gpt-oss-120b",
  "tools_used": ["recall_customer_memory", "get_customer_tickets"],
  "tool_details": [ { "name": "get_customer_tickets", "arguments_summary": "customer_id=1, limit=5" } ],
  "recalled_memories": [ { "id": "…", "content": "…", "type": "world", "relevance": 0.91 } ],
  "retained_summary": "Arjun Technologies still runs the RDS instance with a 100 connection limit.",
  "demo_mode": false,
  "warnings": [],
  "agent_run_id": 42,
  "latency_ms": 2310,
  "tokens": 1480
}
```

`memories_recalled`, `tools_used`, `memory_retained` and `model` are what the
frontend needs to show the memory workflow live.

---

## Memory

### `GET /api/customers/{id}/memories`

Query: `search`, `memory_type` (`world` | `experience` | `observation`), `limit`, `offset`.

```json
{ "items": [ { "id": "b21", "content": "Customer uses PostgreSQL 16 on AWS RDS.",
               "type": "world", "customer_id": 1, "source": "hindsight",
               "relevance": null, "created_at": "2026-09-20T10:30:00Z",
               "context": "customer support interaction",
               "document_id": "rd-c1-9f2a", "tags": ["customer:1", "org:1", "recall-desk"],
               "metadata": { "customer_id": "1" }, "scores": { "final": 0.91 } } ],
  "total": 7, "limit": 20, "offset": 0, "provider": "hindsight" }
```

### `POST /api/memory/recall`

```json
{ "customer_id": 1, "query": "previous API timeouts", "limit": 8,
  "types": ["world", "observation"], "budget": "mid" }
```

Returns `RecallResponse` (memories + count + provider + duration).

### `POST /api/memory/retain`

```json
{ "customer_id": 1, "content": "Arjun Technologies raised the RDS limit to 300.",
  "context": "customer support interaction", "conversation_id": 11 }
```

`201` -> `{ "customer_id": 1, "retained": true, "provider": "hindsight", "document_id": "rd-c1-…", "duration_ms": 840 }`

### `POST /api/memory/reflect`

```json
{ "customer_id": 1, "query": "What recurring technical issues has this customer experienced?",
  "budget": "mid" }
```

```json
{ "customer_id": 1, "query": "…",
  "answer": "Two timeout incidents, both connection-pool exhaustion…",
  "memories_used": [ { "id": "…", "content": "…", "type": "experience" } ],
  "provider": "hindsight", "demo_mode": false, "duration_ms": 3120 }
```

---

## Dashboard & analytics

### `GET /api/dashboard?days=14`

Real counts: `customer_count`, `open_ticket_count`, `resolved_ticket_count`,
`escalated_ticket_count`, `conversation_count`, `agent_run_count`,
`memory_event_count`, `memory_recall_count`, `memory_retain_count`,
`memory_reflect_count`, `memory_provider`, `llm_configured`,
`memory_activity[{date, retains, recalls, reflects}]`, `recent_tickets`,
`recent_support_activity`.

### `GET /api/analytics`

`total_tickets`, `open_tickets`, `resolved_tickets`, `escalated_tickets`,
`resolution_rate`, `average_resolution_hours`, `agent_runs`,
`successful_agent_runs`, `average_agent_latency_ms`, `total_tokens`,
`memory_recalls`, `memory_retains`, `memory_reflects`, `customers`,
`conversations`, `tickets_by_status`, `tickets_by_priority`,
`recurring_issue_categories[{category, count}]`.

---

## System

### `GET /health`

```json
{ "status": "degraded", "app": "RecallDesk AI", "environment": "development",
  "services": { "database": "connected", "hindsight": "configured (bank: recall-desk-ai)",
                "groq": "unconfigured", "knowledge_base": "loaded" } }
```

`status` is `ok` only when the database is reachable and both external services
are configured. Values are truthful - `unconfigured` means the credential is
missing, `unavailable` means it was configured but the call failed.

### `GET /health/detailed`

Adds the live Hindsight probe result and the active providers.

---

## Agent tools

The model can call these; each is validated and role-checked by the registry.

| Tool | Purpose | Roles |
| --- | --- | --- |
| `search_customer` | Find customers by name/email/company | admin, agent, viewer |
| `get_customer_tickets` | Recent tickets for a customer | admin, agent, viewer |
| `get_ticket_history` | One ticket with its resolutions | admin, agent, viewer |
| `search_knowledge_base` | RecallDesk product documentation | admin, agent, viewer |
| `recall_customer_memory` | On demand Hindsight recall | admin, agent, viewer |
| `create_ticket` | Open a new ticket | admin, agent |
| `update_ticket` | Change status/priority/assignee | admin, agent |
| `suggest_resolution` | Record what fixed a ticket | admin, agent |
