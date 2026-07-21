# Deployment Guide

The platform is two services — the FastAPI backend (`content-core[api]`) and
the React dashboard — plus an optional Postgres. Docker Compose runs all three.

## Local / self-hosted (Docker Compose)

```bash
cd content-core/deploy
cp ../.env.example .env          # fill in ANTHROPIC_API_KEY, PLATFORM_API_KEY, etc.
docker compose up                # API :8000, dashboard :5173, SQLite
```

With Postgres instead of SQLite:
```bash
DATABASE_URL=postgresql+psycopg://platform:platform@postgres:5432/platform \
  docker compose --profile postgres up
```

Health: `GET http://localhost:8000/health`. The API runs Alembic migrations on
startup, so the schema is created/updated automatically.

## Managed platforms

Both services are standard containers; any of these work:

| Platform | API | Dashboard | Notes |
|---|---|---|---|
| **Railway** | deploy `api.Dockerfile` | deploy dashboard Dockerfile | add a Postgres plugin; set `DATABASE_URL` |
| **Render** | Web Service (Docker) | Static Site (`npm run build`, publish `dist/`) | free Postgres tier available |
| **Fly.io** | `fly launch` on api.Dockerfile | `fly launch` on dashboard | volumes for SQLite, or Fly Postgres |
| **AWS ECS/Fargate** | task from api image | task or S3+CloudFront for static | RDS Postgres |

Set these env vars in production:
- `ANTHROPIC_API_KEY` (and any providers you use)
- `PLATFORM_API_KEY` — enables API auth (unset = open; never leave unset in prod)
- `DATABASE_URL` — Postgres in prod; SQLite is fine for single-node
- `LANGFUSE_ENABLED=true` + Langfuse keys, if using observability export

## Dashboard → API wiring
The dashboard talks to `/api` (proxied in dev via Vite). In production, serve
the dashboard behind the same domain and reverse-proxy `/api` to the backend,
or set the API base at build time. Set `VITE_API_KEY` to match `PLATFORM_API_KEY`.

## Kubernetes
Intentionally not provided — see ADR-0003. Compose covers single-node
deployment; a K8s manifest would be scaffolding for scale this platform
doesn't have. The images are standard, so a future Helm chart is
straightforward if the need arises.
