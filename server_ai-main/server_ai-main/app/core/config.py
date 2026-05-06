from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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
