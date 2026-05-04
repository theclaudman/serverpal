from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    secret_key: str = "CHANGE-ME"
    encryption_key: str = ""

    ai_service_url: str = "http://localhost:8001"
    digest_service_url: str = "http://localhost:8002"

    price_type_retail: str = "55a36684-62bc-11f0-89d6-d8625b865b03"
    price_type_wholesale: str = "05baa3c2-5ea9-11f0-aa16-10ffe0a68931"

    @property
    def price_columns(self) -> dict:
        return {
            self.price_type_retail: "Розничная",
            self.price_type_wholesale: "Оптовая",
        }


settings = Settings()

# Обратная совместимость — чтобы не менять все импорты сразу
SECRET_KEY = settings.secret_key
AI_SERVICE_URL = settings.ai_service_url
DIGEST_SERVICE_URL = settings.digest_service_url
PRICE_COLUMNS = settings.price_columns