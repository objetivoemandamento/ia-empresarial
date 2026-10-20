import asyncio
import json

import pytest

from app.agent_orchestrator import AgentOrchestrator, AgentRunError

OK = json.dumps({"approved": True, "notes": "ok"})


def plan(*tasks):
    return json.dumps({"tasks": [
        {"title": title, "instructions": "Faça " + title, "sensitive_action": action}
        for title, action in tasks
    ]})


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
    async def unavailable(system, user):
        raise RuntimeError("provider unavailable")

    store = make_store(tmp_path, unavailable)
    result = await store.process(store.create("Pesquisar um mercado")["id"])
    assert result["status"] == "failed"
    assert result["result"] is None
