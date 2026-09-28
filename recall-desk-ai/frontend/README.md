# Frontend

The RecallDesk AI frontend: **React + TypeScript + Tailwind**, built with
Next.js 16 (App Router). The backend is the FastAPI service in
[`../backend`](../backend).

> If you port this app to Vite, keep the same origin rule: the dev server origin
> must be listed in the backend's `CORS_ORIGINS` (`http://localhost:5173` for
> Vite, `http://localhost:3000` for this build).

## Run

```bash
npm install
npm run dev          # http://localhost:3000
```

```bash
npm run build        # production build
npm run start        # serve the production build
```

## Connect to the backend

| Setting | Value |
| --- | --- |
| API base URL | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| Auth | `POST /api/auth/login` -> `Authorization: Bearer <token>` |

1. Add `http://localhost:3000` to `CORS_ORIGINS` in `backend/.env`.
2. Never put `GROQ_API_KEY` or `HINDSIGHT_API_KEY` in frontend code. They are
   server-side only; the browser talks exclusively to the backend.

## The endpoints the UI needs

| Screen | Endpoint |
| --- | --- |
| Login | `POST /api/auth/login` |
| Dashboard | `GET /api/dashboard` |
| Analytics | `GET /api/analytics` |
| Customer list / search | `GET /api/customers?search=&status=&limit=&offset=` |
| Customer detail | `GET /api/customers/{id}` (includes `memory_count`, `recent_tickets`, `recent_memories`) |
| Tickets | `GET /api/tickets?status=&priority=&customer_id=` |
| Chat | `POST /api/support/chat` |
| Conversation history | `GET /api/conversations/{id}/messages` |
| Memory Explorer | `GET /api/customers/{id}/memories` |
| Memory operations | `POST /api/memory/recall` · `/retain` · `/reflect` |

Request and response shapes for all of them: [`../docs/api.md`](../docs/api.md).

## What to render from an AI run

`POST /api/support/chat` returns everything needed to make the memory workflow
visible:

```json
{ "memories_recalled": 4,
  "memory_retained": true,
  "memory_provider": "hindsight",
  "tools_used": ["get_customer_tickets", "search_knowledge_base"],
  "recalled_memories": [ { "content": "...", "type": "world", "relevance": 0.91 } ],
  "retained_summary": "...",
  "model": "openai/gpt-oss-120b",
  "demo_mode": false,
  "latency_ms": 2310 }
```

Suggested UI affordances:

* a "Hindsight recall - N memories" chip on each assistant message
* a collapsible list of the recalled memories
* a "tools used" chip row
* a "memory retained" indicator when `memory_retained` is true
* a persistent "demo mode" banner when `demo_mode` is true, so a fallback run is
  never mistaken for real Hindsight/Groq processing
