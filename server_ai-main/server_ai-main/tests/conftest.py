import os
import pytest
from dotenv import load_dotenv
from pathlib import Path
from app.models.schemas import BaseCredentials

# Загружаем тестовые переменные окружения до импорта settings.
TEST_ENV = Path(__file__).parent / ".env.test"
load_dotenv(TEST_ENV, override=True)

# Импортируем settings после загрузки .env.test
from app.core.config import settings  # noqa: E402


def pytest_collection_modifyitems(config, items):
    has_onec = os.environ.get("ONEC_IP") and os.environ.get("ONEC_LOGIN")
    has_llm = os.environ.get("RUN_LLM_TESTS") == "1"
    if has_onec and has_llm:
        return

    reason = "integration tests require tests/.env.test with ONEC_IP/ONEC_LOGIN and RUN_LLM_TESTS=1"
    skip_integration = pytest.mark.skip(reason=reason)
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture(scope="session")
def onec_credentials() -> BaseCredentials:
    """Учётные данные для подключения к тестовой базе 1С."""
    return BaseCredentials(
        ip=os.environ["ONEC_IP"],
        login=os.environ["ONEC_LOGIN"],
        password=os.environ.get("ONEC_PASSWORD", ""),
    )
