# Memory design

## What Hindsight is for

Hindsight is the persistent memory engine. RecallDesk never reimplements it and
never mirrors its contents into MySQL. The whole application talks to it
through `app/services/hindsight_service.py` and nothing else.

## One bank, scoped by tags

A single memory bank is used:

```
HINDSIGHT_BANK_ID=recall-desk-ai
```

Every retained memory carries:

| Field | Value | Why |
| --- | --- | --- |
| `tags` | `customer:<customer_id>`, `org:<organization_id>`, `recall-desk` | Visibility scoping for recall and reflect |
| `metadata.customer_id` | `<customer_id>` | Lets the API normalize results for the frontend |
| `metadata.organization_id` | `<organization_id>` | Same, for tenancy |
| `metadata.conversation_id` | conversation id | Traceability back to MySQL |
| `context` | `customer support interaction` | Shapes how Hindsight extracts facts |
| `document_id` | `rd-c<customer>-<uuid>` | Idempotency key per retain operation |
| `entities` | customer name, company | Entity graph edges between customers and systems |

Recall and reflect are always issued with a **single** customer tag:

```python
tags=[f"customer:{customer_id}"]
tags_match="any_strict"
```

Two rules matter here, and both were verified against the live Hindsight API:

1. A multi-tag filter is an **OR**. Passing `["customer:1", "org:1"]` returns
   every memory in the organization, including other customers' memories. Only
   the customer tag is passed.
2. `any_strict` excludes untagged/global memories, so nothing leaks in from a
   global scope.

As defence in depth the service also drops any result whose owning customer
(metadata `customer_id`, or the `customer:<id>` tag for consolidated
`observation` memories) does not match the customer being asked about, and logs
`hindsight.cross_customer_result_dropped` when it does.

## What gets retained

Retention is selective. Every turn, a second LLM pass classifies the
conversation and returns JSON:

```json
{"memories": [
  {"type": "fact",       "content": "Arjun Technologies runs its API on AWS RDS with PostgreSQL 16."},
  {"type": "preference", "content": "Arjun Technologies prefers detailed technical explanations in writing."},
  {"type": "experience", "content": "A previous API timeout at Arjun Technologies was caused by connection-pool exhaustion."},
  {"type": "resolution", "content": "Increasing the connection pool size resolved the previous timeout incident at Arjun Technologies."}
]}
```

Durable memory types:

* **fact** - technology stack, infrastructure, versions, configuration values, account context
* **preference** - communication style, technical depth, channel, escalation expectations
* **experience** - incidents: symptoms, timing, root cause
* **resolution** - what fixed it, and whether the fix worked

Never retained: greetings, thanks, acknowledgements, restated questions,
generic advice, and anything the customer only just asked for.

If no LLM is configured, a keyword/number heuristic (`app/services/agent_service.py::is_durable`)
decides what is durable so the pipeline still behaves sensibly in demo mode.

## What gets recalled

The customer's latest message is the recall query. Only the top few results are
passed to the LLM:

```
HINDSIGHT_RECALL_BUDGET=mid
HINDSIGHT_RECALL_MAX_TOKENS=1200
```

The full memory bank is never dumped into a prompt. Hindsight does the
retrieval (semantic + keyword + graph + temporal, fused and reranked) and the
agent receives the small relevant slice.

## Reflection

`POST /api/memory/reflect` asks Hindsight to reason over accumulated memory
instead of returning facts. It is used for questions like "what patterns have
we seen with this customer?" and returns the synthesized answer plus the
memories it cited (`based_on`).

## Memory counts in the API

`GET /api/customers/{id}` returns `memory_count`. It is **not** invented:

* the app calls Hindsight's memory listing, filters by the customer tag and
  counts what came back;
* if the scan window (200 memories) is exhausted, `memory_count_capped: true`
  is returned so the UI can show "200+".

`memory_events` in MySQL is only an audit trail of retain/recall/reflect calls.
It is never used as a substitute for Hindsight.

## Session vs memory

```
conversation (MySQL)  = the transcript of one sitting
customer memory       = everything learned across every sitting
```

Starting a new conversation creates a new `session_id` and an empty transcript.
It does not touch, reset or delete any Hindsight memory. This is the difference
that the demo in the README shows.

## Failures

* Hindsight errors never break CRUD: the customer detail endpoint degrades to
  `memory_count: 0` and logs a warning.
* During a support run, a recall failure is reported in the response `warnings`
  array and the agent answers from live data only.
* When `HINDSIGHT_API_KEY` is missing, the demo provider is used and every
  response says `memory_provider: "demo"` and `demo_mode: true`. Production
  (`APP_ENV=production`) refuses to start without credentials.
