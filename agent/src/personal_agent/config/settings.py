from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    log_level: str = "INFO"
    openai_api_key: SecretStr | None = None
    agent_data_dir: Path = Path.home() / "Library/Application Support/PersonalAgent"
    model_dir: Path = Path("/Volumes/sh_disk/model")
    model_config = SettingsConfigDict(
        env_file=AGENT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
