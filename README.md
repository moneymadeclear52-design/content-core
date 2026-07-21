# content-core

The platform kernel for an AI content-automation system: one versioned,
tested Python package that four content pipelines depend on, plus the service
layer, persistence, observability, and an MCP server that turn those pipelines
into a production platform.

It began as a way to eliminate ~1,500 lines of logic copy-pasted across four
repositories. It has since grown into the shared foundation for LLM access,
retrieval, agent orchestration, workflow execution, cost tracking, and a REST
API — while keeping every addition justified by a real need (see
`docs/adr/`).

```
pip install -e ".[api,db,rag,mcp]"     # install with the extras you need
```

---

## Platform architecture

```
                         ┌──────────────────────────┐
        Consumers  ─────▶ │  content-core (kernel)   │
                         └──────────────────────────┘
   CLI pipelines ─┐        LLMProvider  ── Claude / OpenAI / Gemini
   REST API ──────┼──────▶ Workflow engine + retry
   MCP clients ───┤        RAG retrieval (vector search)
   Dashboard ─────┘        Multi-agent Director
                           Telemetry (tokens · cost · latency)
                                     │
                           ┌─────────┴──────────┐
                           │ Persistence (SQLite│  → Postgres-ready
                           │  / SQLAlchemy +     │
                           │  Alembic)           │
                           └────────────────────┘
```

Four interfaces, one engine — the CLI pipelines, the REST API, the MCP server,
and the web dashboard all drive the same core. No business logic is duplicated
across them.

## Module catalog

| Module | Responsibility |
|---|---|
| `content_core.llm.LLMProvider` | Provider-agnostic text generation (Claude/OpenAI/Gemini), lazy SDK imports, retry + backoff, normalized responses, telemetry hook |
| `content_core.workflow` | Step-based workflow engine — named stages, per-stage retry, optional-stage skipping, run reports |
| `content_core.retry` | Retry decorator; retries only listed exception types (auth errors fail fast) |
| `content_core.rag` | Semantic perspective retrieval — embeddings + cosine search, fingerprint-cached index, graceful fallback |
| `content_core.agents` | Multi-agent story production — Director → Writer/Visual/Audio with a bounded single-revision critique loop |
| `content_core.telemetry` | Per-call LLM token/cost/latency recording, structured JSON logging, optional Langfuse export |
| `content_core.db` | SQLAlchemy persistence — workflow runs, step records, LLM usage, generated content |
| `content_core.api` | FastAPI service layer — background jobs, API-key auth, OpenAPI |
| `content_core.eval` | Evaluation: rule + LLM-as-judge scorers, prompt registry, benchmarking, A/B/n experiments |
| `content_core.approvals` | Human-in-the-loop approval gate (auto-approve above threshold, else queue) |
| `content_core.registry` | Minimal plugin registry for scorers/providers/publishers |
| `mcp_server.py` | MCP server exposing the platform as tools for Claude Desktop/Code, Cursor |

## Install

Extras are opt-in so a pipeline pulls only what it uses:

```bash
pip install -e .                # core: LLM, workflow, retry, injector, notion
pip install -e ".[rag]"         # + sentence-transformers, numpy
pip install -e ".[mcp]"         # + MCP server
pip install -e ".[db]"          # + SQLAlchemy, Alembic
pip install -e ".[api]"         # + FastAPI, uvicorn
pip install -e ".[dev]"         # + pytest
```

Configuration is entirely environment-based — copy `.env.example` to `.env`.
No secrets live in source.

## Using the core

```python
from content_core import LLMProvider, inject_originality
from content_core.workflow import Workflow, Step

llm = LLMProvider(provider="claude")               # or openai / gemini
hook = llm.generate("Write a hook about DB Cooper.", model="claude-sonnet-4-6")

wf = Workflow("demo", steps=[
    Step("draft",    draft_fn,    retries=2),
    Step("thumbnail", thumb_fn,   on_error="skip"),   # optional stage
    Step("upload",   upload_fn,   retries=3),
])
report = wf.run(initial_context={"topic": "..."})
print(report.summary())
```

## The REST API

```bash
pip install -e ".[api]"
uvicorn content_core.api.app:app --port 8000
# → OpenAPI docs at http://localhost:8000/docs
```

| Endpoint | Purpose |
|---|---|
| `POST /jobs/script` | Queue a script generation job (returns a job id) |
| `POST /jobs/episode` | Queue a multi-agent story episode |
| `GET /jobs/{id}` | Poll job status/result |
| `GET /runs` | Workflow run history with per-step timing |
| `GET /metrics/usage` | LLM token usage + estimated cost per provider/model |
| `GET /health` | Liveness + version |

Long-running work returns a job id immediately (FastAPI `BackgroundTasks` + an
in-process registry — see ADR-0002 for why, at this scale, not Celery/Redis).
Auth is a static API key via `X-API-Key` (`PLATFORM_API_KEY`; disabled when
unset for local dev — ADR-0004).

## The MCP server

```bash
pip install -e ".[mcp]"
python mcp_server.py          # stdio transport for Claude Desktop
```

Exposes `generate_script`, `inject_originality_tool`,
`find_perspectives` (RAG-backed), and `produce_story_episode` (multi-agent),
plus a `perspectives://{channel}` resource — callable from any MCP client.

## Persistence

SQLAlchemy models with **SQLite by default** and **Postgres-ready** via
`DATABASE_URL` (the schema is dialect-portable; switching engines is a config
change, not a migration project — ADR-0001). Alembic manages schema:

```bash
DATABASE_URL=sqlite:///content_core.db alembic upgrade head
```

## Observability

Every LLM call is recorded at the provider choke point: provider, model, input/
output tokens, latency, and estimated cost (maintainable pricing table).
Structured JSON logging via `telemetry.setup_structured_logging()`. Optional
Langfuse export behind `LANGFUSE_ENABLED=true`. Telemetry failures never break
generation.

## Evaluation, benchmarking & experiments

Quality measurement is first-class. Scorers normalize to 0–1 (comparable across
types); the LLM-as-judge uses a cheap model and degrades gracefully.

```python
from content_core.eval import evaluate, benchmark, experiment, Variant

# regression-test a prompt against golden cases (persists an eval run)
report = evaluate(template, cases, criteria=[
    {"scorer": "length_bounds", "min_words": 30, "max_words": 90},
    {"scorer": "excludes_all", "forbidden": ["as an AI"]},
    {"scorer": "llm_judge", "rubric": "Rate hook strength and factual tone."},
])

# compare models on the same prompt (cost recorded automatically)
rows = benchmark(prompt, [
    {"provider": "claude", "model": "claude-sonnet-4-6"},
    {"provider": "openai", "model": "gpt-4o"},
], criteria)

# pick the best of N prompt variants
best = experiment([Variant("a", tA), Variant("b", tB)], inputs, criteria)
```

Human-in-the-loop gate for publishing:

```python
from content_core.approvals import auto_or_queue
if auto_or_queue(workflow="rapidreelz", item_ref=job_id,
                 summary=title, score=originality, threshold=0.75) == "pending":
    return   # awaits review at GET /approvals
```

API surfaces: `GET /eval/runs`, `GET /benchmarks`, `GET /approvals`,
`POST /approvals/{id}/decide`. The dashboard's **Quality** tab visualizes all
three.

## Testing

```bash
pip install -e ".[dev]"
pytest -q          # 46 tests, no API keys, no network, < 6s
```

Tests mock vendor SDKs and use fake embedders / scripted LLMs, so the full
suite runs offline and deterministically. CI (GitHub Actions) runs the matrix
across Python 3.10–3.12 and includes a hardcoded-secret gate.

## Architecture Decision Records

`docs/adr/` documents every significant choice — including the deliberate
**declines**, each with the conditions under which it would be revisited:

| ADR | Decision |
|---|---|
| 0001 | SQLite-first persistence, Postgres-ready |
| 0002 | Background jobs without Celery/Redis |
| 0003 | Cost telemetry now; defer full OpenTelemetry/Prometheus |
| 0004 | API-key auth; not JWT/OAuth2 |
| 0005 | Keep the custom LLM abstraction; not LiteLLM |
| 0006 | Keep the Director; not LangGraph |
| 0007 | No Redis caching layer |
| 0008 | Minimal plugin registry, not a full framework |
| 0009 | LLM-as-judge with a cheap model + rule-based first |

## Deployment

The API + dashboard (+ optional Postgres) run via Docker Compose:

```bash
cd deploy && cp ../.env.example .env && docker compose up
```

See `deploy/DEPLOY.md` for managed platforms (Railway/Render/Fly.io/ECS).
Kubernetes is intentionally omitted (ADR-0003).

## Consumers

- `rapidreelz-pipeline`, `crimescope-pipeline`, `rapidreelz-stories-pipeline` (Python) and `mmc-pipeline` (Node.js Python helpers) import the core
- `platform-dashboard` (React/TypeScript) consumes the REST API

## Roadmap

- Migrate FastAPI `on_event` startup to the `lifespan` handler
- Persist the API job registry across restarts (currently in-process)
- Optional per-request distributed tracing once more than one service exists
