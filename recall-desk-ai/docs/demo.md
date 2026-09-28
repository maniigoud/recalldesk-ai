# Demo

A five-minute walkthrough of the memory workflow. Every command below is a real
API call against the running backend.

Setup: `cd backend && uvicorn app.main:app --reload`, base URL
`http://localhost:8000`. Demo account (development only):

```
demo@recalldesk.local / DemoPassword123!
```

---

## 0. Check the services are really there

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok",
  "services": { "database": "connected",
                "hindsight": "configured (bank: recall-desk-ai)",
                "groq": "configured (model: openai/gpt-oss-120b)",
                "knowledge_base": "loaded" } }
```

`unconfigured` means the credential is missing; `unavailable` means it was
configured and the call failed. The endpoint never pretends.

---

## 1. Log in

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@recalldesk.local","password":"DemoPassword123!"}'
```

Save the token:

```bash
export TOKEN="<access_token>"
```

---

## 2. Pick the customer

```bash
curl "http://localhost:8000/api/customers?search=Arjun" -H "Authorization: Bearer $TOKEN"
```

Arjun Technologies is the account that already has history: AWS RDS, PostgreSQL 16,
a connection limit of 100, and a previous timeout caused by connection-pool
exhaustion.

---

## 3. Session 1 - establish context

```bash
curl -X POST http://localhost:8000/api/support/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"customer_id": 1,
       "message": "We are deploying our API to AWS RDS using PostgreSQL 16. Our connection limit is 100. We prefer detailed technical explanations in writing."}'
```

```json
{ "conversation_id": 41,
  "message": "Noted: PostgreSQL 16 on RDS with a 100 connection limit...",
  "memories_recalled": 0,
  "memory_retained": true,
  "memory_provider": "hindsight",
  "retained_summary": "Arjun Technologies runs its API on AWS RDS with PostgreSQL 16.; ...",
  "tools_used": [] }
```

Nothing was recalled (this is the first conversation), and durable facts were
written to Hindsight.

---

## 4. Session 2 - new conversation, memory survives

Omit `conversation_id` to force a brand new session.

```bash
curl -X POST http://localhost:8000/api/support/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "message": "Our API is timing out again."}'
```

```json
{ "conversation_id": 42,
  "message": "This looks similar to the timeout your team hit before. With a 100 connection limit on RDS, pool exhaustion is the first thing to check...",
  "memories_recalled": 4,
  "memory_retained": true,
  "tools_used": ["get_customer_tickets", "search_knowledge_base"] }
```

The agent answered with context it was never told in this session.

Two sessions, two `session_id`s, two empty-of-the-other transcripts:

```bash
curl "http://localhost:8000/api/customers/1/conversations" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/conversations/42/messages" -H "Authorization: Bearer $TOKEN"
```

---

## 5. Show the memory itself (Memory Explorer)

```bash
curl "http://localhost:8000/api/customers/1/memories?limit=20" -H "Authorization: Bearer $TOKEN"
```

```json
{ "items": [ { "id": "…", "content": "Arjun Technologies runs its API on AWS RDS with PostgreSQL 16.",
               "type": "world", "customer_id": 1, "source": "hindsight",
               "context": "customer support interaction", "tags": ["customer:1", "org:1", "recall-desk"] } ],
  "total": 7, "provider": "hindsight" }
```

Direct recall and reflection:

```bash
curl -X POST http://localhost:8000/api/memory/recall \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "query": "previous timeouts and what fixed them", "limit": 5}'

curl -X POST http://localhost:8000/api/memory/reflect \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "query": "What recurring technical issues has this customer experienced?"}'
```

---

## 6. Show the contrast (optional)

Same second-session message with memory disabled. The agent has no access to
Hindsight, so it re-asks:

```json
{ "message": "I can help with that. Could you tell me which database engine you
               are using and what your connection limits are?",
  "memories_recalled": 0 }
```

---

## 7. Observe the workflow

```bash
curl http://localhost:8000/api/dashboard -H "Authorization: Bearer $TOKEN"
curl http://localhost:8000/api/analytics -H "Authorization: Bearer $TOKEN"
```

Every AI response already carries `memories_recalled`, `tools_used`,
`memory_retained`, `model`, `latency_ms` and `demo_mode` - enough to render the
retain/recall cycle live in the frontend.

---

## 8. Reseed

```bash
cd backend
python -m app.seed.seed_data --force          # wipe + reseed the demo workspace
python -m app.seed.seed_data --skip-memory    # database only, no Hindsight writes
```

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `memories_recalled: 0` in session 2 | Hindsight consolidation/recall lag, or the customer id differs. Check `/api/customers/{id}/memories`. |
| `demo_mode: true` | `GROQ_API_KEY` and/or `HINDSIGHT_API_KEY` missing. The response says which one. |
| `503 HINDSIGHT_ERROR` | Hindsight unreachable. `GET /health/detailed` probes it live. |
| `503 DATABASE_ERROR` | `DATABASE_URL` wrong or `alembic upgrade head` not run. |
