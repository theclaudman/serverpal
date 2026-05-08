from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


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

    # LLM (OpenAI-совместимый API — LM Studio, OpenAI, и др.)
    openai_api_key: str = "lm-studio"
    openai_base_url: str = "http://127.0.0.1:1234/v1"
    openai_model: str = "dolphin-2.9.4-llama3.1-8b"

    # Сервис
    service_api_key: str = "change_me"

    # Агентный цикл
    max_tool_iterations: int = 5

    # Пути
    data_dir: Path = Path("data/connected_bases")
    logs_dir: Path = Path("logs")
    knowledge_base_file: Path = Path("knowledge_base.txt")


settings = Settings()

if settings.service_api_key.strip() in {"", "change-me", "change_me"}:
    raise RuntimeError("SERVICE_API_KEY должен быть задан в корневом .env")
