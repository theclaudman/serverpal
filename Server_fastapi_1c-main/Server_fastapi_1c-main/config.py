from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file() -> Path | None:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "run_all.py").exists():
            root_env = candidate / ".env"
            if root_env.exists():
                return root_env
            raise RuntimeError(
                f"Корневой .env не найден: {root_env}. "
                "Создайте его из .env.example в корне проекта."
            )
    return None

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    secret_key: str = "CHANGE-ME"
    encryption_key: str = ""
    ai_service_url: str = "http://127.0.0.1:8001"
    digest_service_url: str = "http://127.0.0.1:8002"
    service_api_key: str = ""
    dashboard_db_path: str = "users.db"
    price_type_retail: str = ""
    price_type_wholesale: str = ""
    allowed_origins: str = "http://127.0.0.1:9001"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    registration_enabled: bool = False
    registration_token: str = ""
    
settings = Settings()

if settings.service_api_key.strip() in {"", "change-me", "change_me"}:
    raise RuntimeError("SERVICE_API_KEY должен быть задан в корневом .env")

SECRET_KEY = settings.secret_key
AI_SERVICE_URL = settings.ai_service_url
DIGEST_SERVICE_URL = settings.digest_service_url
SERVICE_API_KEY = settings.service_api_key
