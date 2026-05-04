import os
import pytest
from dotenv import load_dotenv
from pathlib import Path
from app.models.schemas import BaseCredentials

# Загружаем тестовые переменные окружения до импорта settings
load_dotenv(Path(__file__).parent / ".env.test", override=True)

# Импортируем settings после загрузки .env.test
from app.core.config import settings  # noqa: E402


@pytest.fixture(scope="session")
def onec_credentials() -> BaseCredentials:
    """Учётные данные для подключения к тестовой базе 1С."""
    return BaseCredentials(
        ip=os.environ["ONEC_IP"],
        login=os.environ["ONEC_LOGIN"],
        password=os.environ.get("ONEC_PASSWORD", ""),
    )
