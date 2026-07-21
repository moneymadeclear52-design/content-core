# ADR-0002: In-process background jobs instead of Celery + Redis

**Status:** Accepted · July 2026

## Context
Script/episode generation over HTTP should not block the request. Celery +
Redis is the conventional answer.

## Decision
Use FastAPI `BackgroundTasks` with an in-process job registry
(POST returns a job id; GET /jobs/{id} polls status/result).

## Why not Celery + Redis
Celery requires a broker (Redis), worker processes, and deployment
orchestration — three moving parts serving a platform with **one user and no
queue contention**. The failure modes added (broker down, worker drift,
serialization issues) exceed the problem being solved. This is precisely
"forcing queueing where it is not needed."

## Adopt-Celery triggers
- Multi-user or multi-tenant API traffic
- Jobs that must survive process restarts mid-execution
- Horizontal scaling of workers (esp. GPU/video-render farms)
When triggered: the job-registry interface (id/status/result) is already the
contract Celery would fulfill — migration swaps the executor, not the API.
