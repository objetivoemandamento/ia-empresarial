from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.llm import LLMUnavailable
from app.schemas import SkillSummary
from app.security import SkillError, UnsafeArchive


class FakeLLM:
    is_ready = True

    def __init__(self):
        self.fail = False
        self.calls = []

    async def respond(self, messages, language, tools):
        self.calls.append((messages, language, tools))
        if self.fail:
            raise LLMUnavailable("provider unavailable")
        return "resposta simulada", "fake-provider"

    async def complete(self, system, user):
        if self.fail:
            raise LLMUnavailable("provider unavailable")
        return "resultado"


class FakeSkillManager:
    def __init__(self, skill):
        self.skill = skill
        self.upload_path = None
        self.install_error = None

    def list_skills(self):
        return [self.skill]

    def preferred_language(self, skill_ids):
        return "en" if "demo-skill" in skill_ids else None

    def active_tools(self, skill_ids, language):
        if "demo-skill" not in skill_ids or language != "en":
            return []
        return [{
            "skill_id": "demo-skill", "name": "say_hello",
            "description": "Say hello", "template": "Say hello politely",
        }]

    def install_zip(self, path):
        self.upload_path = Path(path)
        assert self.upload_path.exists()
        if self.install_error:
            raise self.install_error
        return self.skill

    def approve(self, skill_id):
        if skill_id != self.skill.id:
            raise KeyError(skill_id)
        return self.skill.model_copy(update={"status": "active"})

    def reject(self, skill_id):
        if skill_id != self.skill.id:
            raise KeyError(skill_id)
        return self.skill.model_copy(update={"status": "rejected"})


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "admin_token", "test-admin-token")
    monkeypatch.setattr(main, "POLICY_FILE", tmp_path / "policies.json")
    skill = SkillSummary(
        id="demo-skill", name="Demo Skill", version="1.0.0",
        description="test", status="pending_review", languages=["en"],
        tools=["say_hello"],
    )
    llm = FakeLLM()
    manager = FakeSkillManager(skill)
    monkeypatch.setattr(main, "llm", llm)
    monkeypatch.setattr(main, "skill_manager", manager)
    return TestClient(main.app), llm, manager


def test_health_and_repository_listing(client):
    api, llm, manager = client
    health = api.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["llm_ready"] is True
    assert health.json()["agent_orchestrator_ready"] is True
    assert api.get("/api/repositories").json()["skills"][0]["id"] == "demo-skill"


def test_chat_uses_selected_skill_language_and_returns_provider(client):
    api, llm, manager = client
    response = api.post("/api/chat", json={
        "messages": [{"role": "user", "content": "Say hello"}],
        "skill_ids": ["demo-skill"],
    })
    assert response.status_code == 200
    assert response.json()["language"] == "en"
    assert response.json()["active_skills"] == ["demo-skill"]
    assert response.json()["provider"] == "fake-provider"
    assert llm.calls[0][2][0]["skill_id"] == "demo-skill"


def test_chat_maps_provider_unavailable_to_502(client):
    api, llm, manager = client
    llm.fail = True
    response = api.post("/api/chat", json={
        "messages": [{"role": "user", "content": "Say hello"}],
        "language": "pt",
    })
    assert response.status_code == 502
    assert response.json()["detail"] == "provider unavailable"


def test_repository_upload_requires_admin_and_cleans_temp_file(client):
    api, llm, manager = client
    files = {"file": ("skill.zip", b"valid zip bytes", "application/zip")}
    assert api.post("/api/repositories/upload", files=files).status_code == 401
    response = api.post("/api/repositories/upload", headers={"Authorization": "Bearer test-admin-token"}, files=files)
    assert response.status_code == 200
    assert response.json()["status"] == "pending_review"
    assert manager.upload_path is not None
    assert not manager.upload_path.exists()


def test_repository_upload_maps_unsafe_and_invalid_packages(client):
    api, llm, manager = client
    headers = {"Authorization": "Bearer test-admin-token"}
    manager.install_error = UnsafeArchive("unsafe zip")
    unsafe = api.post("/api/repositories/upload", headers=headers, files={"file": ("skill.zip", b"x", "application/zip")})
    assert unsafe.status_code == 400
    manager.install_error = SkillError("invalid skill")
    invalid = api.post("/api/repositories/upload", headers=headers, files={"file": ("skill.zip", b"x", "application/zip")})
    assert invalid.status_code == 422
    unsupported = api.post("/api/repositories/upload", headers=headers, files={"file": ("skill.txt", b"x", "text/plain")})
    assert unsupported.status_code == 415


def test_repository_approval_and_rejection_routes(client):
    api, llm, manager = client
    headers = {"Authorization": "Bearer test-admin-token"}
    assert api.post("/api/repositories/missing/approve", headers=headers).status_code == 404
    approved = api.post("/api/repositories/demo-skill/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["skill"]["status"] == "active"
    rejected = api.post("/api/repositories/demo-skill/reject", headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["skill"]["status"] == "rejected"


def test_repository_upload_rejects_too_large_files(client, monkeypatch):
    api, llm, manager = client
    monkeypatch.setattr(main.settings, "max_upload_bytes", 3)
    response = api.post(
        "/api/repositories/upload",
        headers={"Authorization": "Bearer test-admin-token"},
        files={"file": ("skill.zip", b"too large", "application/zip")},
    )
    assert response.status_code == 413
