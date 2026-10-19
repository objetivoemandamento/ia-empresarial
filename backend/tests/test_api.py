from fastapi.testclient import TestClient
import json
import zipfile
import pytest

from app import main
from app.config import Settings
from app.repository_manager import SkillManager


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "admin_token", "test-admin-token")
    isolated_settings = Settings(
        data_dir=tmp_path,
        max_upload_bytes=1_000_000,
        max_zip_files=100,
        max_uncompressed_bytes=1_000_000,
        max_compression_ratio=100,
    )
    monkeypatch.setattr(main, "skill_manager", SkillManager(isolated_settings))
    return TestClient(main.app)


def make_skill_zip(tmp_path):
    manifest = {
        "schema_version": "1.0", "id": "api-skill", "name": "API Skill",
        "version": "1.0.0", "description": "test skill", "languages": ["pt", "en"],
        "tools": [{"name": "summarize", "description": "Summarize text",
                   "kind": "prompt_template", "template": "Summarize {{input}}"}],
    }
    path = tmp_path / "skill.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("README.txt", "Declarative skill package")
    return path.read_bytes()


def test_health_lists_supported_languages(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["language_default"] == "pt"
    assert set(payload["supported_languages"]) == {"pt", "en", "zh", "es", "hi"}
    assert payload["llm_mode"] in {"demo", "configured"}
    assert payload["llm_ready"] is (payload["llm_mode"] == "configured")
    assert isinstance(payload["transcription_ready"], bool)


def test_upload_requires_admin_authentication(client):
    response = client.post("/api/repositories/upload", files={"file": ("skill.zip", b"bad zip")})
    assert response.status_code == 401


def test_upload_rejects_non_zip_file(client):
    response = client.post(
        "/api/repositories/upload",
        headers={"Authorization": "Bearer test-admin-token"},
        files={"file": ("skill.txt", b"not a zip")},
    )
    assert response.status_code == 415


def test_chat_defaults_to_portuguese_and_reports_demo_provider(client, monkeypatch):
    class FakeLLM:
        async def respond(self, messages, language, tools):
            return f"resposta em {language}", "test-provider"

    monkeypatch.setattr(main, "llm", FakeLLM())
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Olá"}]})
    assert response.status_code == 200
    assert response.json() == {
        "answer": "resposta em pt",
        "language": "pt",
        "active_skills": [],
        "provider": "test-provider",
    }


def test_chat_rejects_unsupported_language(client):
    response = client.post(
        "/api/chat",
        json={"language": "fr", "messages": [{"role": "user", "content": "Bonjour"}]},
    )
    assert response.status_code == 422


def test_moderation_requires_admin_authentication(client):
    response = client.post("/api/repositories/unknown/approve")
    assert response.status_code == 401


def test_upload_valid_skill_then_approve(client, tmp_path):
    response = client.post(
        "/api/repositories/upload",
        headers={"Authorization": "Bearer test-admin-token"},
        files={"file": ("skill.zip", make_skill_zip(tmp_path), "application/zip")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending_review"
    skill_id = payload["skill"]["id"]
    assert payload["skill"]["status"] == "pending_review"

    approval = client.post(
        f"/api/repositories/{skill_id}/approve",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert approval.status_code == 200
    assert approval.json()["skill"]["status"] == "active"

    chat = client.post("/api/chat", json={
        "language": "pt", "skill_ids": [skill_id],
        "messages": [{"role": "user", "content": "Resuma isto"}],
    })
    assert chat.status_code == 200
    assert chat.json()["active_skills"] == [skill_id]


def test_upload_invalid_zip_is_rejected(client):
    response = client.post(
        "/api/repositories/upload",
        headers={"Authorization": "Bearer test-admin-token"},
        files={"file": ("skill.zip", b"not a zip", "application/zip")},
    )
    assert response.status_code == 400


def test_production_settings_reject_weak_admin_token():
    with pytest.raises(ValueError, match="ADMIN_TOKEN"):
        Settings(app_env="production", admin_token="change-me-in-development")


def test_audio_rejects_unsupported_language(client):
    response = client.post(
        "/api/audio/transcribe",
        data={"language": "fr"},
        files={"file": ("recording.webm", b"fake audio", "audio/webm")},
    )
    assert response.status_code == 422


def test_skill_catalog_survives_manager_restart(tmp_path):
    settings = Settings(data_dir=tmp_path, max_upload_bytes=1_000_000,
                       max_zip_files=100, max_uncompressed_bytes=1_000_000,
                       max_compression_ratio=100)
    manager = SkillManager(settings)
    archive = tmp_path / "persist.zip"
    manifest = {
        "schema_version": "1.0", "id": "persist-skill", "name": "Persist Skill",
        "version": "1.0.0", "description": "persistence test", "languages": ["pt"],
        "tools": [{"name": "summarize", "description": "Summarize text",
                   "kind": "prompt_template", "template": "Summarize {{input}}"}],
    }
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
    manager.install_zip(archive)
    manager.approve("persist-skill")

    restored = SkillManager(settings)
    skills = restored.list_skills()
    assert len(skills) == 1
    assert skills[0].id == "persist-skill"
    assert skills[0].status == "active"


def test_moderation_rejects_invalid_state_transitions(client, tmp_path):
    headers = {"Authorization": "Bearer test-admin-token"}
    upload = client.post(
        "/api/repositories/upload", headers=headers,
        files={"file": ("skill.zip", make_skill_zip(tmp_path), "application/zip")},
    )
    assert upload.status_code == 200
    skill_id = upload.json()["skill"]["id"]
    assert client.post(f"/api/repositories/{skill_id}/approve", headers=headers).status_code == 200
    # An active skill cannot be re-approved or rejected through the pending-review workflow.
    assert client.post(f"/api/repositories/{skill_id}/approve", headers=headers).status_code == 409
    assert client.post(f"/api/repositories/{skill_id}/reject", headers=headers).status_code == 409


def test_rejected_skill_id_can_be_submitted_again_for_review(client, tmp_path):
    headers = {"Authorization": "Bearer test-admin-token"}
    archive = make_skill_zip(tmp_path)
    upload = client.post(
        "/api/repositories/upload", headers=headers,
        files={"file": ("skill.zip", archive, "application/zip")},
    )
    assert upload.status_code == 200
    skill_id = upload.json()["skill"]["id"]
    rejected = client.post(f"/api/repositories/{skill_id}/reject", headers=headers)
    assert rejected.status_code == 200
    retry = client.post(
        "/api/repositories/upload", headers=headers,
        files={"file": ("skill.zip", archive, "application/zip")},
    )
    assert retry.status_code == 200
    assert retry.json()["skill"]["status"] == "pending_review"


def test_production_settings_require_llm_configuration():
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        Settings(
            app_env="production", admin_token="a" * 40,
            llm_base_url="", llm_api_key="", llm_model="",
        )
