import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent_orchestrator import AgentOrchestrator, AgentRunError, SPECIALISTS, _specialty

OK = json.dumps({"approved": True, "notes": "ok"})


def plan(*tasks):
    return json.dumps({"tasks": [
        {"title": title, "instructions": "Faça " + title, "sensitive_action": action}
        for title, action in tasks
    ]})


async def unavailable_llm(system, user):
    raise RuntimeError("provider unavailable")


def make_store(tmp_path, llm, policies=None):
    return AgentOrchestrator(tmp_path / "runs.sqlite3", llm, lambda: policies or {
        "external_network_enabled": False, "prime_sandbox_enabled": False
    })


@pytest.mark.asyncio
async def test_independent_tasks_run_concurrently_and_are_reviewed(tmp_path):
    both_started = asyncio.Event()
    active = 0
    peak = 0

    async def llm(system, user):
        nonlocal active, peak
        role = system.split(".")[0].removeprefix("ROLE:")
        if role == "CEO_PLAN":
            return plan(("A", None), ("B", None))
        if role == "EXECUTOR":
            active += 1
            peak = max(peak, active)
            if active >= 2:
                both_started.set()
            try:
                await asyncio.wait_for(both_started.wait(), timeout=1)
                await asyncio.sleep(0.01)
                return "resultado independente"
            finally:
                active -= 1
        if role == "REVIEWER":
            return OK
        if role == "CEO_DELIVERY":
            return "entrega final"
        raise AssertionError(role)

    store = make_store(tmp_path, llm)
    result = await store.process(store.create("Executar tarefas independentes")["id"])
    assert result["status"] == "delivered"
    assert peak >= 2
    assert [task["status"] for task in result["tasks"]] == ["done", "done"]


@pytest.mark.asyncio
async def test_safe_task_progresses_while_publish_waits_for_approval(tmp_path):
    async def llm(system, user):
        role = system.split(".")[0].removeprefix("ROLE:")
        if role == "CEO_PLAN":
            return plan(("Publicar relatório", "publish"), ("Analisar conteúdo", None))
        if role == "EXECUTOR":
            return "análise pronta"
        if role == "REVIEWER":
            return OK
        if role == "CEO_DELIVERY":
            return "entrega final"
        raise AssertionError(role)

    store = make_store(tmp_path, llm)
    result = await store.process(store.create("Preparar relatório")["id"])
    assert result["status"] == "awaiting_approval"
    assert [task["status"] for task in result["tasks"]] == ["awaiting_approval", "done"]
    store.decide(result["approvals"][0]["id"], True)
    result = await store.process(result["id"])
    assert result["status"] == "delivered"


def test_financial_goals_are_blocked_before_model_call(tmp_path):
    async def unused_llm(system, user):
        raise AssertionError("The model must not be called for blocked financial goals")

    store = make_store(tmp_path, unused_llm)
    with pytest.raises(AgentRunError, match="financeira"):
        store.create("Transferir dinheiro para fornecedor")


@pytest.mark.asyncio
async def test_missing_model_fails_run_without_claiming_delivery(tmp_path):
    store = make_store(tmp_path, unavailable_llm)
    result = await store.process(store.create("Pesquisar um mercado")["id"])
    assert result["status"] == "failed"
    assert result["result"] is None


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "admin_token", "test-admin-token")
    monkeypatch.setattr(main, "POLICY_FILE", tmp_path / "policies.json")
    store = AgentOrchestrator(tmp_path / "api-runs.sqlite3", unavailable_llm, main.read_policies)
    monkeypatch.setattr(main, "agent_orchestrator", store)
    monkeypatch.setattr(main, "_schedule_agent_run", lambda run_id: None)
    return TestClient(main.app)


def test_agent_run_api_requires_admin_and_blocks_financial_goal(api_client):
    assert api_client.get("/api/agent-runs").status_code == 401
    headers = {"Authorization": "Bearer test-admin-token"}
    assert api_client.get("/api/agent-runs", headers=headers).status_code == 200
    blocked = api_client.post("/api/agent-runs", headers=headers, json={"goal": "Transferir dinheiro"})
    assert blocked.status_code == 422
    created = api_client.post("/api/agent-runs", headers=headers, json={"goal": "Planejar uma pesquisa de mercado"})
    assert created.status_code == 202
    run_id = created.json()["id"]
    assert api_client.get(f"/api/agent-runs/{run_id}", headers=headers).json()["status"] == "queued"


def test_permission_api_saves_optional_controls_and_protects_invariants(api_client):
    headers = {"Authorization": "Bearer test-admin-token"}
    initial = api_client.get("/api/policies").json()
    assert all(item["enabled"] is True for item in initial["protected_controls"])
    assert api_client.patch("/api/policies", json={"voice_enabled": False}).status_code == 401
    updated = api_client.patch("/api/policies", headers=headers, json={"voice_enabled": False})
    assert updated.status_code == 200
    assert updated.json()["voice_enabled"] is False
    assert all(item["enabled"] is True for item in updated.json()["protected_controls"])
    assert api_client.patch("/api/policies", headers=headers, json={"security_audit": False}).status_code == 422
    skills_policy = api_client.patch("/api/policies", headers=headers, json={"approved_skills_enabled": False})
    assert skills_policy.status_code == 200
    audio = api_client.post("/api/audio/transcribe", data={"language": "pt"}, files={"file": ("audio.webm", b"audio", "audio/webm")})
    assert audio.status_code == 403
    skills = api_client.post("/api/repositories/upload", headers=headers, files={"file": ("skills.zip", b"not-a-zip", "application/zip")})
    assert skills.status_code == 403
    chat = api_client.post("/api/chat", json={"messages": [{"role": "user", "content": "oi"}], "skill_ids": ["example"], "language": "pt"})
    assert chat.status_code == 403

def test_fifteen_specialist_routes_are_available():
    assert len(SPECIALISTS) == 15
    assert _specialty("Criar uma campanha de marketing") == "Marketing"
    assert _specialty("Corrigir bug na API Python") == "Engenharia"
    assert _specialty("Planejar integração MCP e webhook") == "Integrações"

@pytest.mark.asyncio
async def test_invalid_ceo_plan_fails_closed(tmp_path):
    async def invalid_plan(system, user):
        return "not JSON"

    store = make_store(tmp_path, invalid_plan)
    result = await store.process(store.create("Planejar algo seguro")["id"])
    assert result["status"] == "failed"
    assert result["result"] is None
    assert "Falha no planejamento" in result["error"]


@pytest.mark.asyncio
async def test_external_network_task_is_blocked_by_default(tmp_path):
    calls = []
    async def llm(system, user):
        calls.append(system)
        return plan(("Pesquisar na web", "external_network"))

    store = make_store(tmp_path, llm)
    result = await store.process(store.create("Pesquisar dados externos")["id"])
    assert result["status"] == "failed"
    assert result["tasks"][0]["status"] == "blocked"
    assert "Rede externa desativada" in result["tasks"][0]["error"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_rejected_approval_does_not_deliver_run(tmp_path):
    async def llm(system, user):
        role = system.split(".")[0].removeprefix("ROLE:")
        if role == "CEO_PLAN":
            return plan(("Publicar relatório", "publish"))
        if role == "CEO_DELIVERY":
            return "não deveria entregar"
        return OK

    store = make_store(tmp_path, llm)
    result = await store.process(store.create("Preparar relatório")["id"])
    assert result["status"] == "awaiting_approval"
    store.decide(result["approvals"][0]["id"], False)
    result = await store.process(result["id"])
    assert result["status"] == "failed"
    assert result["tasks"][0]["status"] == "rejected"
    assert result["result"] is None


@pytest.mark.asyncio
async def test_failed_planning_can_be_retried_after_provider_recovers(tmp_path):
    async def broken(system, user):
        raise RuntimeError("offline")

    store = make_store(tmp_path, broken)
    run_id = store.create("Planejar relatório seguro")["id"]
    failed = await store.process(run_id)
    assert failed["status"] == "failed"

    async def recovered(system, user):
        role = system.split(".")[0].removeprefix("ROLE:")
        if role == "CEO_PLAN":
            return plan(("Revisar relatório", None))
        if role == "EXECUTOR":
            return "revisado"
        if role == "REVIEWER":
            return OK
        if role == "CEO_DELIVERY":
            return "entrega revisada"
        raise AssertionError(role)

    store.llm_call = recovered
    queued = store.retry(run_id)
    assert queued["status"] == "queued"
    result = await store.process(run_id)
    assert result["status"] == "delivered"
    assert result["result"] == "entrega revisada"


def test_missing_run_and_approval_return_errors(tmp_path):
    async def unused(system, user):
        raise AssertionError("not called")

    store = make_store(tmp_path, unused)
    with pytest.raises(KeyError):
        store.get(999)
    with pytest.raises(KeyError):
        store.decide(999, True)

