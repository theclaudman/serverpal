from app.core.config import settings
from app.models.schemas import BaseCredentials, ChatRequest
from app.services.onec_service import _build_url


def test_settings_load_defaults_or_env():
    assert settings.openai_base_url
    assert settings.openai_model


def test_build_url_adds_http_and_path():
    assert _build_url("127.0.0.1/unf", "/hs/ai/query") == "http://127.0.0.1/unf/hs/ai/query"


def test_chat_request_defaults_system_prompt():
    request = ChatRequest(
        credentials=BaseCredentials(login="user", password="pass", ip="127.0.0.1/unf"),
        prompt="hello",
    )

    assert request.system_prompt == ""
