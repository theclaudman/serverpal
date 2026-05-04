"""
server.py — FastAPI-приложение Digest API

Точка входа:
  python server.py → uvicorn на порту 8002

Эндпоинты:
  GET  /health         — проверка что сервис жив
  POST /api/digest     — сгенерировать дайджест
  POST /api/ask        — вопрос по данным последнего дайджеста
  GET  /api/providers  — список доступных LLM-провайдеров
"""

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api_models import (
    DigestRequest, AskRequest,
    DigestResponse, AskResponse, ErrorResponse,
    ProviderInfo, ProvidersResponse, HealthResponse,
)
import context_builder


# ---------------------------------------------------------------------------
# Приложение
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Digest API",
    description="Финансовый дайджест из 1С УНФ",
    version="0.1.0",
)

# CORS — дашборд на другом порту
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # MVP: всё разрешено. SaaS: ограничить.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR    = Path(__file__).parent
PROMPTS_DIR = BASE_DIR / "prompts"


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    """Загружает промпт из файла prompts/."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Промпт не найден: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _parse_date(date_str: str | None) -> datetime:
    """Парсит дату YYYY-MM-DD или возвращает вчера."""
    if not date_str:
        return datetime.now() - timedelta(days=1)
    return datetime.strptime(date_str, "%Y-%m-%d")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


# ---------------------------------------------------------------------------
# GET /api/providers
# ---------------------------------------------------------------------------

@app.get("/api/providers", response_model=ProvidersResponse)
async def get_providers():
    from lm_client import check_lmstudio, _get_openai_key

    # LM Studio
    lmstudio_available = False
    try:
        lmstudio_available = check_lmstudio()
    except Exception:
        pass

    # OpenAI
    openai_available = False
    try:
        _get_openai_key()
        openai_available = True
    except (ValueError, Exception):
        pass

    providers = [
        ProviderInfo(
            id="lmstudio",
            name="LM Studio (локальный)",
            available=lmstudio_available,
            anonymize=False,
        ),
        ProviderInfo(
            id="openai",
            name="OpenAI GPT-4o",
            available=openai_available,
            anonymize=True,
        ),
    ]

    return ProvidersResponse(providers=providers)


# ---------------------------------------------------------------------------
# POST /api/digest
# ---------------------------------------------------------------------------

@app.post("/api/digest")
async def generate_digest(req: DigestRequest):
    # Парсим дату
    try:
        target_date = _parse_date(req.date)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="invalid_date",
                message=f"Неверный формат даты: {req.date}. Используй YYYY-MM-DD.",
            ).model_dump(),
        )

    date_str = target_date.strftime("%Y-%m-%d")

    # Генерируем дайджест
    from digest import run_digest_api
    result = run_digest_api(
        base_url=req.credentials.base_url,
        login=req.credentials.login,
        password=req.credentials.password,
        date=target_date,
        provider=req.provider,
    )

    # Ошибка — пробрасываем
    if result["status"] == "error":
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error=result["error"],
                message=result["message"],
            ).model_dump(),
        )

    # Сохраняем в кэш
    ctx = context_builder.set_context(
        base_url=req.credentials.base_url,
        date_str=date_str,
        aggregated_text=result["aggregated_text"],
        real_names=result["real_names"],
        anonymized=result["anonymized"],
    )
    context_builder.set_digest_text(
        base_url=req.credentials.base_url,
        date_str=date_str,
        digest_text=result["digest"],
    )

    return DigestResponse(
        digest=result["digest"],
        date=result["date"],
        generated_at=result["generated_at"],
        provider=result["provider"],
        anonymized=result["anonymized"],
    )


# ---------------------------------------------------------------------------
# POST /api/ask
# ---------------------------------------------------------------------------

@app.post("/api/ask")
async def ask_question(req: AskRequest):
    base_url = req.credentials.base_url
    anonymize = req.provider.lower().strip() != "lmstudio"

    # Ищем свежий контекст — берём последний доступный по base_url
    # Для MVP: пробуем вчера и сегодня
    ctx = None
    date_str = None
    for days_ago in range(0, 3):
        d = datetime.now() - timedelta(days=days_ago)
        ds = d.strftime("%Y-%m-%d")
        ctx = context_builder.get_context(base_url, ds)
        if ctx:
            date_str = ds
            break

    if ctx is None:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="no_context",
                message="Сначала сгенерируйте дайджест.",
            ).model_dump(),
        )

    # Загружаем промпт
    prompt_file = "ask_anonymous.txt" if anonymize else "ask.txt"
    try:
        system_prompt = _load_prompt(prompt_file)
    except FileNotFoundError as e:
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="prompt_missing",
                message=str(e),
            ).model_dump(),
        )

    # Отправляем в LLM
    from lm_client import send_with_question
    try:
        answer = send_with_question(
            aggregated_text=ctx.aggregated_text,
            question=req.question,
            system_prompt=system_prompt,
            provider=req.provider,
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error="llm_unavailable",
                message=f"LLM недоступен ({req.provider}): {e}",
            ).model_dump(),
        )

    # Демаскировка если нужно
    if anonymize and ctx.real_names:
        from digest import _demask_with_names, CLIENT_ID
        answer = _demask_with_names(answer, CLIENT_ID, ctx.real_names)

    age = context_builder.get_context_age_minutes(base_url, date_str)

    return AskResponse(
        answer=answer,
        question=req.question,
        context_date=date_str,
        context_age_minutes=age,
        provider=req.provider,
    )


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
