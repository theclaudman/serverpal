import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import reports, chat, query
from app.core.scheduler import start_scheduler
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.logs_dir / "app.log", encoding="utf-8"),
    ],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём нужные директории при старте
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    start_scheduler()
    yield


app = FastAPI(
    title="1C AI Bridge",
    description="Сервис-связка между базами 1С УНФ 3.0 и GigaChat AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(reports.router)
app.include_router(chat.router)
app.include_router(query.router)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)