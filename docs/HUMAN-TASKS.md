# Human tasks and human approval

## API

All endpoints require the administrator bearer token configured as `ADMIN_TOKEN`.

- `GET /api/human-tasks` — list tasks; optional `status` and `owner` filters.
- `POST /api/human-tasks` — create a task. Supports priority, owner, due date, dependencies, evidence, an idempotency key, and an optional human-approval gate.
- `GET /api/human-tasks/{id}` — read one task.
- `PATCH /api/human-tasks/{id}` — update task metadata.
- `POST /api/human-tasks/{id}/status` — move an open task to in-progress, blocked, or cancelled; invalid transitions are rejected.
- `POST /api/human-tasks/{id}/decision` — approve or reject a task waiting for approval.
- `POST /api/human-tasks/{id}/complete` — complete a task after dependencies are complete.
- `GET /api/human-tasks/{id}/history` — read the append-only audit events.

## Safety guarantees

- Approval records the exact submitted scope; it does not grant broader permissions and does not execute external actions.
- Pix, withdrawals, outgoing transfers and other detected outgoing-payment instructions are rejected at task creation, update, approval and completion.
- Dependencies must exist; self-dependencies and dependency cycles are rejected.
- A task with unfinished dependencies cannot be completed.
- Idempotency keys prevent duplicate creation on retries.
- Every creation, update, status change, decision and completion is recorded in the audit table.

## Storage and deployment

The task ledger uses SQLite under `DATA_DIR/human_tasks.sqlite3`; the versioned migration is `backend/migrations/versions/0008_human_tasks.py`. The runtime applies it idempotently on startup.

SQLite persistence depends on a durable filesystem. Do not deploy this service to an ephemeral filesystem and assume task records survive restarts. The current Render configuration declares a persistent disk; confirm its cost before using it. The existing suspended Render PostgreSQL and inactive Supabase project are not reactivated automatically.

## Validation

Run the backend suite with `python -m pytest -q backend` and build the frontend with `npm --prefix frontend run build`. Tests cover authentication, task persistence, idempotency, exact-scope approvals, blocked financial actions, dependencies, status transitions and migration upgrade/downgrade/re-upgrade.
