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
    # Comma-separated user IDs (the `sub` claim) allowed to use the API. Empty accepts any user
    # of the authentication provider, which is fine while public sign-ups are disabled.
    allowed_user_ids: str = ""

    @property
    def origins(self) -> list[str]:
        return split_csv(self.allowed_origins)

    @property
    def allowed_users(self) -> set[str]:
        return set(split_csv(self.allowed_user_ids))


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def get_settings() -> Settings:
    return Settings()
