from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file() -> Path:
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
    raise RuntimeError("Не удалось найти корень проекта ServerPal")

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
    price_type_retail: str = "55a36684-62bc-11f0-89d6-d8625b865b03"
    price_type_wholesale: str = "05baa3c2-5ea9-11f0-aa16-10ffe0a68931"
    allowed_origins: str = "http://127.0.0.1:9001"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    registration_enabled: bool = False
    registration_token: str = ""
    
    @property
    def price_columns(self) -> dict:
        return {
            self.price_type_retail: "Розничная",
            self.price_type_wholesale: "Оптовая",
        }

settings = Settings()

if settings.service_api_key.strip() in {"", "change-me", "change_me"}:
    raise RuntimeError("SERVICE_API_KEY должен быть задан в корневом .env")

SECRET_KEY = settings.secret_key
AI_SERVICE_URL = settings.ai_service_url
DIGEST_SERVICE_URL = settings.digest_service_url
SERVICE_API_KEY = settings.service_api_key
PRICE_COLUMNS = settings.price_columns
