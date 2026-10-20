import asyncio
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
    monkeypatch.delenv("TEST_PROVIDER_API_KEY", raising=False)
    settings = Settings(ai_router_models_json=json.dumps([{
        "id": "test", "provider": "test", "base_url": "https://example.invalid/v1",
        "model": "test-model", "api_key_env": "TEST_PROVIDER_API_KEY", "tasks": ["general"]
    }]))
    router = AIModelRouter(settings)
    assert router._models() == []


def test_router_reads_secret_from_environment(monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_API_KEY", "secret-not-in-config")
    settings = Settings(ai_router_models_json=json.dumps([{
        "id": "test", "provider": "test", "base_url": "https://example.invalid/v1",
        "model": "test-model", "api_key_env": "TEST_PROVIDER_API_KEY", "tasks": ["general"]
    }]))
    models = AIModelRouter(settings)._models()
    assert len(models) == 1
    assert models[0]["api_key"] == "secret-not-in-config"

class FakeResponse:
    def __init__(self, content="ok", status=200):
        self.content = content
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("failed", request=None, response=None)

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


class FakeAsyncClient:
    responses = []
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json, headers):
        self.requests.append({"url": url, "payload": json, "headers": headers})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_router_falls_back_after_provider_failure(monkeypatch):
    monkeypatch.setenv("PRIMARY_TEST_API_KEY", "primary-secret")
    monkeypatch.setenv("FALLBACK_TEST_API_KEY", "fallback-secret")
    config = json.dumps([
        {"id": "primary", "base_url": "https://primary.example/v1", "model": "primary-model",
         "api_key_env": "PRIMARY_TEST_API_KEY", "tasks": ["general"], "priority": 1},
        {"id": "fallback", "base_url": "https://fallback.example/v1", "model": "fallback-model",
         "api_key_env": "FALLBACK_TEST_API_KEY", "tasks": ["general"], "priority": 2},
    ])
    FakeAsyncClient.responses = [httpx.ConnectError("offline"), FakeResponse("fallback answer")]
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.llm.httpx.AsyncClient", FakeAsyncClient)
    router = AIModelRouter(Settings(ai_router_models_json=config))
    answer, provider = asyncio.run(router.respond([{"role": "user", "content": "Olá"}], "pt", []))
    assert answer == "fallback answer"
    assert provider == "router:fallback"
    assert len(FakeAsyncClient.requests) == 2


def test_router_ignores_invalid_priority_and_rejects_remote_http(monkeypatch):
    monkeypatch.setenv("TEST_ROUTER_API_KEY", "test-secret")
    config = json.dumps([
        {"id": "bad-priority", "base_url": "https://safe.example/v1", "model": "safe-model",
         "api_key_env": "TEST_ROUTER_API_KEY", "tasks": ["general"], "priority": "invalid"},
        {"id": "insecure", "base_url": "http://remote.example/v1", "model": "remote-model",
         "api_key_env": "TEST_ROUTER_API_KEY", "tasks": ["general"], "priority": 1},
    ])
    models = AIModelRouter(Settings(ai_router_models_json=config))._models()
    assert [item["id"] for item in models] == ["bad-priority"]
    assert models[0]["priority"] == 100

def test_router_refuses_non_secret_environment_variable_names(monkeypatch):
    monkeypatch.setenv("PATH", "/not-a-provider-secret")
    settings = Settings(ai_router_models_json=json.dumps([{
        "id": "unsafe", "base_url": "https://provider.example/v1", "model": "model-id",
        "api_key_env": "PATH", "tasks": ["general"]
    }]))
    assert AIModelRouter(settings)._models() == []

@pytest.mark.asyncio
async def test_ceo_review_role_routes_to_analysis_model(monkeypatch):
    monkeypatch.setenv("MARKETING_TEST_API_KEY", "marketing-secret")
    monkeypatch.setenv("REVIEW_TEST_API_KEY", "review-secret")
    config = json.dumps([
        {"id": "marketing", "base_url": "https://marketing.example/v1", "model": "marketing-model",
         "api_key_env": "MARKETING_TEST_API_KEY", "tasks": ["marketing"], "priority": 1},
        {"id": "review", "base_url": "https://review.example/v1", "model": "review-model",
         "api_key_env": "REVIEW_TEST_API_KEY", "tasks": ["analysis"], "priority": 2},
    ])
    FakeAsyncClient.responses = [FakeResponse("reviewed")]
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.llm.httpx.AsyncClient", FakeAsyncClient)
    router = AIModelRouter(Settings(ai_router_models_json=config))
    answer, provider = await router.respond([
        {"role": "system", "content": "ROLE:REVIEWER. Revise o resultado"},
        {"role": "user", "content": "Criar uma campanha de marketing"},
    ], "pt", [])
    assert answer == "reviewed"
    assert provider == "router:review"
    assert "review.example" in FakeAsyncClient.requests[0]["url"]

