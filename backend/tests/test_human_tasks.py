import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import main
from app.human_tasks import HumanTaskStore
from app.task_schema import downgrade, upgrade


@pytest.fixture()
def task_client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "admin_token", "test-admin-token")
    monkeypatch.setattr(main, "task_store", HumanTaskStore(tmp_path / "tasks.sqlite3"))
    return TestClient(main.app)


HEADERS = {"Authorization": "Bearer test-admin-token"}


def create_task(client, **overrides):
    payload = {"title": "Revisar relatório", "description": "Conferir os indicadores"}
    payload.update(overrides)
    response = client.post("/api/human-tasks", headers=HEADERS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["task"]


def test_tasks_require_admin_authentication(task_client):
    assert task_client.get("/api/human-tasks").status_code == 401
    assert task_client.post("/api/human-tasks", json={"title": "Tarefa"}).status_code == 401


def test_create_list_and_audit_history(task_client):
    task = create_task(task_client, priority="high", owner="Matheus")
    assert task["status"] == "open"
    assert task["priority"] == "high"
    assert task["owner"] == "Matheus"

    listed = task_client.get("/api/human-tasks", headers=HEADERS).json()["tasks"]
    assert any(item["id"] == task["id"] for item in listed)

    events = task_client.get(f"/api/human-tasks/{task['id']}/history", headers=HEADERS).json()["events"]
    assert events[0]["action"] == "created"
    assert events[0]["actor"] == "admin"


def test_idempotency_prevents_duplicate_tasks(task_client):
    first = create_task(task_client, idempotency_key="task-once")
    second = create_task(task_client, title="Texto diferente", idempotency_key="task-once")
    assert first["id"] == second["id"]
    assert len(task_client.get("/api/human-tasks", headers=HEADERS).json()["tasks"]) == 1


def test_approval_is_exact_scope_and_does_not_execute_action(task_client):
    task = create_task(task_client, title="Revisão humana", requires_approval=True)
    assert task["status"] == "awaiting_approval"

    response = task_client.post(
        f"/api/human-tasks/{task['id']}/decision",
        headers=HEADERS,
        json={"decision": "approve", "scope": "Revisar o documento versão 1", "note": "Apenas revisão"},
    )
    assert response.status_code == 200
    approved = response.json()["task"]
    assert approved["status"] == "open"
    assert approved["approved_scope"] == "Revisar o documento versão 1"

    event = task_client.get(f"/api/human-tasks/{task['id']}/history", headers=HEADERS).json()["events"][-1]
    assert event["detail"]["effect"] == "approval records this exact scope only; no external action executed"


@pytest.mark.parametrize("title", [
    "Enviar Pix para fornecedor",
    "Realizar transferência bancária",
    "Fazer saque",
    "Withdraw money",
    "Send funds to vendor",
    "Pay a supplier",
    "Transfer funds to another account",
])
def test_outgoing_financial_actions_are_rejected(task_client, title):
    response = task_client.post("/api/human-tasks", headers=HEADERS, json={"title": title})
    assert response.status_code == 403


def test_outgoing_financial_scope_is_rejected_even_when_approval_is_requested(task_client):
    task = create_task(task_client, title="Revisão de procedimento", requires_approval=True)
    response = task_client.post(
        f"/api/human-tasks/{task['id']}/decision",
        headers=HEADERS,
        json={"decision": "approve", "scope": "Executar um Pix para terceiro"},
    )
    assert response.status_code == 403
    assert task_client.get(f"/api/human-tasks/{task['id']}", headers=HEADERS).json()["task"]["status"] == "awaiting_approval"


def test_dependencies_must_be_completed_before_dependent_task(task_client):
    first = create_task(task_client, title="Preparar relatório")
    second = create_task(task_client, title="Revisar relatório", dependencies=[first["id"]])

    blocked = task_client.post(
        f"/api/human-tasks/{second['id']}/complete", headers=HEADERS,
        json={"note": "Concluído"},
    )
    assert blocked.status_code == 409

    completed = task_client.post(
        f"/api/human-tasks/{first['id']}/complete", headers=HEADERS,
        json={"note": "Relatório preparado", "evidence": ["relatorio-v1.pdf"]},
    )
    assert completed.status_code == 200
    assert completed.json()["task"]["status"] == "done"

    dependent = task_client.post(
        f"/api/human-tasks/{second['id']}/complete", headers=HEADERS,
        json={"note": "Revisão final"},
    )
    assert dependent.status_code == 200
    assert dependent.json()["task"]["status"] == "done"


def test_invalid_status_transitions_are_rejected(task_client):
    task = create_task(task_client)
    response = task_client.post(
        f"/api/human-tasks/{task['id']}/status", headers=HEADERS,
        json={"status": "done", "note": "Tentar pular a conclusão"},
    )
    assert response.status_code == 422

    cancelled = task_client.post(
        f"/api/human-tasks/{task['id']}/status", headers=HEADERS,
        json={"status": "cancelled", "note": "Cancelada pelo responsável"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["task"]["status"] == "cancelled"


def test_task_store_persists_after_reopen(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    store = HumanTaskStore(path)
    from app.human_tasks import TaskCreate
    created = store.create(TaskCreate(title="Persistir tarefa"), "tester")
    restored = HumanTaskStore(path)
    assert restored.get(created["id"])["title"] == "Persistir tarefa"
    assert len(restored.history(created["id"])) == 1


def test_migration_upgrade_downgrade_and_reupgrade(tmp_path):
    connection = sqlite3.connect(tmp_path / "migration.sqlite3")
    upgrade(connection)
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='human_tasks'"
    ).fetchone()
    downgrade(connection)
    assert not connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='human_tasks'"
    ).fetchone()
    upgrade(connection)
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='human_tasks'"
    ).fetchone()
    connection.close()
