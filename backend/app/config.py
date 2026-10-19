from functools import lru_cache
from pathlib import Path
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
    openai_api_key: str = ""
    transcription_model: str = "whisper-1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self):
        if self.app_env.lower() in {"prod", "production"}:
            if self.admin_token == "change-me-in-development" or len(self.admin_token) < 32:
                raise ValueError("Production requires a unique ADMIN_TOKEN with at least 32 characters")
            if not (self.llm_base_url.strip() and self.llm_api_key.strip() and self.llm_model.strip()):
                raise ValueError("Production requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL")
            if not self.origins:
                raise ValueError("Production requires at least one ALLOWED_ORIGINS entry")
        return self

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
