from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


def get_env_file() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "run_all.py").exists():
            root_env = candidate / ".env"
            if root_env.exists():
                return root_env
    return current.parent / ".env"


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
