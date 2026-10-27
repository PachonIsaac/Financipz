from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path, so the settings load no matter which directory the process starts from.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_name: str = "financipz"
    database_url: str = ""
    supabase_url: str = ""
    allowed_origins: str = "http://localhost:5173"

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    return Settings()
