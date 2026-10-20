from functools import lru_cache
from pathlib import Path
import re
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    data_dir: Path = Path("./data")
    max_upload_bytes: int = 25_000_000
    max_zip_files: int = 2_000
    max_uncompressed_bytes: int = 100_000_000
    max_compression_ratio: int = 100
    allowed_origins: str = "http://localhost:5173"
    admin_token: str = "change-me-in-development"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # JSON array of OpenAI-compatible model endpoints. Secrets are referenced by
    # environment-variable name, never stored in the JSON configuration.
    ai_router_models_json: str = ""
    openai_api_key: str = ""
    transcription_model: str = "whisper-1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self):
        if self.app_env.lower() in {"prod", "production"}:
            if self.admin_token == "change-me-in-development" or len(self.admin_token) < 32:
                raise ValueError("Production requires a unique ADMIN_TOKEN with at least 32 characters")
            legacy_ready = bool(self.llm_base_url.strip() and self.llm_api_key.strip() and self.llm_model.strip())
            if legacy_ready:
                from urllib.parse import urlparse
                parsed_legacy = urlparse(self.llm_base_url)
                if parsed_legacy.scheme not in {"https", "http"} or not parsed_legacy.netloc or parsed_legacy.username or parsed_legacy.password:
                    raise ValueError("Production LLM_BASE_URL must be a valid HTTP(S) URL without embedded credentials")
                if parsed_legacy.scheme != "https" and parsed_legacy.hostname not in {"localhost", "127.0.0.1", "::1"}:
                    raise ValueError("Production remote LLM_BASE_URL must use HTTPS")
            router_ready = bool(self.ai_router_models_json.strip())
            if not (legacy_ready or router_ready):
                raise ValueError("Production requires LLM_BASE_URL/API_KEY/MODEL or AI_ROUTER_MODELS_JSON")
            if router_ready:
                import json
                import os
                from urllib.parse import urlparse
                try:
                    models = json.loads(self.ai_router_models_json)
                except json.JSONDecodeError as exc:
                    raise ValueError("AI_ROUTER_MODELS_JSON must be valid JSON") from exc
                if not isinstance(models, list) or not models:
                    raise ValueError("AI_ROUTER_MODELS_JSON must be a non-empty JSON array")
                configured_provider = False
                for item in models:
                    if not isinstance(item, dict) or item.get("enabled", True) is False:
                        continue
                    required = (item.get("id"), item.get("base_url"), item.get("model"), item.get("api_key_env"))
                    if not all(isinstance(value, str) and value.strip() for value in required):
                        continue
                    if not re.fullmatch(r"[A-Z][A-Z0-9_]*(?:_API_KEY|_API_TOKEN)", item["api_key_env"].strip()):
                        continue
                    parsed_url = urlparse(item["base_url"])
                    if parsed_url.scheme not in {"https", "http"} or not parsed_url.netloc or parsed_url.username or parsed_url.password:
                        continue
                    if parsed_url.scheme != "https" and parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                        continue
                    if os.getenv(item["api_key_env"].strip()):
                        configured_provider = True
                        break
                if not configured_provider:
                    raise ValueError("Production requires at least one enabled AI router model with its API key environment variable configured")
            if not self.origins:
                raise ValueError("Production requires at least one ALLOWED_ORIGINS entry")
        return self

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
