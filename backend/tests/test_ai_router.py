import json
import os
import pytest
import httpx
from app.config import Settings
from app.llm import AIModelRouter, LLMUnavailable, _infer_task


def test_task_router_classifies_coding_and_marketing():
    assert _infer_task("Corrija este bug no Python") == "coding"
    assert _infer_task("Crie uma campanha de divulgação do produto") == "marketing"
    assert _infer_task("Olá, tudo bem?") == "general"


def test_router_rejects_invalid_json():
    router = AIModelRouter(Settings(ai_router_models_json="{"))
    with pytest.raises(LLMUnavailable, match="valid JSON"):
        router._models()


def test_router_skips_models_without_api_keys(monkeypatch):
    monkeypatch.delenv("TEST_PROVIDER_KEY", raising=False)
    settings = Settings(ai_router_models_json=json.dumps([{
        "id": "test", "provider": "test", "base_url": "https://example.invalid/v1",
        "model": "test-model", "api_key_env": "TEST_PROVIDER_KEY", "tasks": ["general"]
    }]))
    router = AIModelRouter(settings)
    assert router._models() == []


def test_router_reads_secret_from_environment(monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-not-in-config")
    settings = Settings(ai_router_models_json=json.dumps([{
        "id": "test", "provider": "test", "base_url": "https://example.invalid/v1",
        "model": "test-model", "api_key_env": "TEST_PROVIDER_KEY", "tasks": ["general"]
    }]))
    models = AIModelRouter(settings)._models()
    assert len(models) == 1
    assert models[0]["api_key"] == "secret-not-in-config"
