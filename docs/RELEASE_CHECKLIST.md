# Release and production acceptance checklist

## Configuration before deploying

- [ ] Set a unique `ADMIN_TOKEN` (at least 32 characters) in the backend environment; never commit it.
- [ ] Set `ALLOWED_ORIGINS` to the exact public frontend origin.
- [ ] Configure either all of `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` or `AI_ROUTER_MODELS_JSON` plus at least one provider secret referenced by `api_key_env`.
- [ ] Use HTTPS for remote model endpoints; the production validator rejects remote HTTP endpoints and missing router secrets.
- [ ] Confirm `DATA_DIR=/var/data` and the persistent disk in `render.yaml` are active for the deployed service.
- [ ] Do not deploy the PR branch to the existing Render service until credentials are configured; production startup is intentionally blocked without a usable provider.

## Acceptance tests

- [ ] GitHub Actions: backend tests, frontend build, desktop and mobile Playwright smoke tests all pass.
- [ ] `GET /api/health` reports `llm_ready=true` and `agent_orchestrator_ready=true`.
- [ ] Admin can create a harmless agent run; status progresses from queued to delivered.
- [ ] Independent tasks overlap in time (bounded to four workers); reviewer output is recorded.
- [ ] Sensitive tasks wait for approval; approval decisions are persisted and auditable.
- [ ] Financial transfer/payment/withdrawal goals are rejected before model calls.
- [ ] Permission changes require the admin token; protected controls cannot be disabled.
- [ ] Refreshing the UI preserves the ability to inspect persisted runs and task history.
- [ ] A real provider failure triggers fallback or a clear failed state without claiming success.
- [ ] Frontend and API deployed commits are verified after Render finishes deployment.

## Explicitly not accepted as complete yet

- Browser, shell, code execution, publishing, sending messages, and REA/MCP are not connected as production tools by this PR. Approval does not execute them. Each needs a separate real adapter, sandboxing, allowlists, timeouts and end-to-end tests.
- Real-model end-to-end validation cannot be claimed until a provider key is configured privately and a run succeeds against that provider.
