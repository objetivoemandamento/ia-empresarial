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

def test_update_task_fields_and_filter_by_owner_and_status(task_client):
    first = create_task(task_client, title="Tarefa A", owner="Alice")
    create_task(task_client, title="Tarefa B", owner="Bob")
    updated = task_client.patch(
        f"/api/human-tasks/{first['id']}", headers=HEADERS,
        json={"title": "Tarefa A revisada", "priority": "urgent", "owner": "Alice"},
    )
    assert updated.status_code == 200
    assert updated.json()["task"]["title"] == "Tarefa A revisada"
    assert updated.json()["task"]["priority"] == "urgent"
    alice = task_client.get("/api/human-tasks?owner=Alice", headers=HEADERS).json()["tasks"]
    assert len(alice) == 1 and alice[0]["id"] == first["id"]
    open_tasks = task_client.get("/api/human-tasks?status=open", headers=HEADERS).json()["tasks"]
    assert len(open_tasks) == 2


def test_dependency_cycle_is_rejected_on_update(task_client):
    first = create_task(task_client, title="Tarefa primeira")
    second = create_task(task_client, title="Tarefa segunda", dependencies=[first["id"]])
    response = task_client.patch(
        f"/api/human-tasks/{first['id']}", headers=HEADERS,
        json={"dependencies": [second["id"]]},
    )
    assert response.status_code == 409
    assert "circular" in response.json()["detail"].lower()


def test_completed_task_cannot_be_updated(task_client):
    task = create_task(task_client, title="Tarefa concluível")
    completed = task_client.post(
        f"/api/human-tasks/{task['id']}/complete", headers=HEADERS,
        json={"note": "Feito"},
    )
    assert completed.status_code == 200
    update = task_client.patch(
        f"/api/human-tasks/{task['id']}", headers=HEADERS,
        json={"title": "Tentar alterar após conclusão"},
    )
    assert update.status_code == 409


@pytest.mark.parametrize("payload", [
    {"title": "Revisar documento", "description": "Fazer um Pix para terceiro"},
    {"title": "Revisar documento", "evidence": ["Enviar dinheiro ao fornecedor"]},
])
def test_financial_actions_are_rejected_in_description_and_evidence(task_client, payload):
    response = task_client.post("/api/human-tasks", headers=HEADERS, json=payload)
    assert response.status_code == 403


def test_missing_task_and_history_return_404(task_client):
    assert task_client.get("/api/human-tasks/missing-id", headers=HEADERS).status_code == 404
    assert task_client.get("/api/human-tasks/missing-id/history", headers=HEADERS).status_code == 404

def test_task_validation_rejects_blank_title_duplicate_missing_and_self_dependencies(task_client):
    blank = task_client.post("/api/human-tasks", headers=HEADERS, json={"title": " "})
    assert blank.status_code == 422
    base = create_task(task_client, title="Base")
    duplicate = task_client.post("/api/human-tasks", headers=HEADERS, json={
        "title": "Duplicate dependency", "dependencies": [base["id"], base["id"]],
    })
    assert duplicate.status_code == 422
    missing = task_client.post("/api/human-tasks", headers=HEADERS, json={
        "title": "Missing dependency", "dependencies": ["not-real"],
    })
    assert missing.status_code == 422
    self_dep = task_client.patch(
        f"/api/human-tasks/{base['id']}", headers=HEADERS,
        json={"dependencies": [base["id"]]},
    )
    assert self_dep.status_code == 422


def test_task_update_handles_empty_payload_nulls_and_blank_titles(task_client):
    task = create_task(task_client, title="Task update", description="original", priority="high")
    unchanged = task_client.patch(f"/api/human-tasks/{task['id']}", headers=HEADERS, json={})
    assert unchanged.status_code == 200
    cleared = task_client.patch(
        f"/api/human-tasks/{task['id']}", headers=HEADERS,
        json={"description": None, "priority": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["task"]["description"] == ""
    assert cleared.json()["task"]["priority"] == "high"
    assert task_client.patch(
        f"/api/human-tasks/{task['id']}", headers=HEADERS, json={"title": None}
    ).status_code == 422
    assert task_client.patch(
        f"/api/human-tasks/{task['id']}", headers=HEADERS, json={"title": " "}
    ).status_code == 422


def test_task_status_transitions_and_approval_errors(task_client):
    task = create_task(task_client, title="Status flow")
    missing = task_client.post("/api/human-tasks/missing-id/status", headers=HEADERS,
                               json={"status": "blocked"})
    assert missing.status_code == 404
    started = task_client.post(f"/api/human-tasks/{task['id']}/status", headers=HEADERS,
                               json={"status": "in_progress", "note": "Iniciado"})
    assert started.status_code == 200
    assert task_client.post(f"/api/human-tasks/{task['id']}/status", headers=HEADERS,
                            json={"status": "in_progress"}).status_code == 409

    no_approval = task_client.post(f"/api/human-tasks/{task['id']}/decision", headers=HEADERS,
                                   json={"decision": "approve", "scope": "Executar apenas revisão"})
    assert no_approval.status_code == 409
    missing_decision = task_client.post("/api/human-tasks/missing-id/decision", headers=HEADERS,
                                        json={"decision": "approve", "scope": "Revisar documento"})
    assert missing_decision.status_code == 404
    blank_scope = task_client.post(f"/api/human-tasks/{task['id']}/decision", headers=HEADERS,
                                   json={"decision": "approve", "scope": " "})
    assert blank_scope.status_code == 422


def test_reject_decision_and_dependency_completion_order(task_client):
    approval_task = create_task(task_client, title="Aguardar decisão", requires_approval=True)
    rejected = task_client.post(
        f"/api/human-tasks/{approval_task['id']}/decision", headers=HEADERS,
        json={"decision": "reject", "scope": "Revisão do documento", "note": "Não autorizado"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["task"]["status"] == "rejected"
    assert task_client.post(
        f"/api/human-tasks/{approval_task['id']}/complete", headers=HEADERS,
        json={"note": "Tentar concluir"},
    ).status_code == 409

    parent = create_task(task_client, title="Tarefa pai")
    child = create_task(task_client, title="Tarefa filha", dependencies=[parent["id"]])
    assert task_client.post(
        f"/api/human-tasks/{child['id']}/complete", headers=HEADERS,
        json={"note": "Antes da dependência"},
    ).status_code == 409
    assert task_client.post(
        f"/api/human-tasks/{parent['id']}/complete", headers=HEADERS,
        json={"note": "Pai concluído"},
    ).status_code == 200
    assert task_client.post(
        f"/api/human-tasks/{child['id']}/complete", headers=HEADERS,
        json={"note": "Agora concluída"},
    ).status_code == 200

