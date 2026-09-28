# Screenshots

Drop the demo images here and reference them from the root `README.md`. Keep
file names as-is so the README links keep working.

| File | What it should show |
| --- | --- |
| `dashboard.png` | `/api/dashboard` rendered: customer, open/resolved ticket counts, memory activity chart, recent agent runs |
| `retain.png` | A support run where `memory_retained: true` and the retained summary is visible |
| `recall.png` | A **new** session where `memories_recalled: 4` and the recalled memories are listed |
| `memory-flow.png` | Retain → new conversation → recall → memory-aware reply |
| `../docs/architecture.png` | Architecture diagram (the README also renders a Mermaid version inline) |

Tips for a good demo screenshot set:

* Include the response metadata panel (`memories_recalled`, `tools_used`,
  `memory_retained`) - that is what makes the memory visible.
* Show two different `session_id`s side by side in `memory-flow.png`.
* Blur or crop nothing that looks like a real customer, key or URL.
* A 30-60 second GIF of the same flow, placed near the top of the README, is the
  single highest-impact artifact for a repository like this.
