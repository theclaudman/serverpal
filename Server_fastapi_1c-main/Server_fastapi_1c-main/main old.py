# main.py — Дашборд ServerPal

# ── Импорты (дедуплицированы) ─────────────────────────────────────────────────

import base64
import hashlib
import json
import logging
import time
import traceback
import uvicorn

from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

import httpx
import websockets

from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Query, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import PRICE_COLUMNS, SECRET_KEY, AI_SERVICE_URL, DIGEST_SERVICE_URL, settings
from database import (
    init_db, get_user, username_exists, create_user,
    verify_password, decrypt_onec_password,
    get_all_prompts, get_prompt, update_prompt,
    get_templates, create_template, delete_template,
    _fernet,
)
from services.cache import get_cached, set_cached
from services.onec_client import (
    fetch_nomenclature, fetch_prices, fetch_stocks, fetch_reserves,
    fetch_groups, fetch_contragents, fetch_cost_by_orders,
    fetch_employees, fetch_orders, fetch_revenues, fetch_payments,
    fetch_debts, fetch_events, fetch_sales, fetch_order_numbers,
    set_credentials,
)
from services.data_builder import build_price_list, build_groups_hierarchy, get_unique_groups
from services.dashboard_builder import build_managers_dashboard
from services.sales_builder import build_sales_report
from services.ai_client import chat as ai_chat
from services.digest_client import get_providers, generate_digest, ask_question


# ── Pydantic-модели запросов ──────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    content: str

class ChatMessage(BaseModel):
    prompt: str

class DigestBody(BaseModel):
    date: str = None
    provider: str = "lmstudio"

class AskBody(BaseModel):
    question: str
    provider: str = "lmstudio"

class PromptUpdate(BaseModel):
    content: str


# ── Логирование ───────────────────────────────────────────────────────────────

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            "logs/dashboard.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger("dashboard")


# ── Приложение ────────────────────────────────────────────────────────────────

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Шаблоны ───────────────────────────────────────────────────────────────────

CHAT_TEMPLATE_PATH      = Path("templates/chat.html")
DIGEST_TEMPLATE_PATH    = Path("templates/digest.html")
INDEX_TEMPLATE_PATH     = Path("templates/index.html")
LOGIN_TEMPLATE_PATH     = Path("templates/login.html")
REGISTER_TEMPLATE_PATH  = Path("templates/register.html")
TEMPLATE_PATH           = Path("templates/price_list.html")
DASHBOARD_TEMPLATE_PATH = Path("templates/managers_dashboard.html")
SALES_TEMPLATE_PATH     = Path("templates/sales_report.html")
PROMPTS_TEMPLATE_PATH   = Path("templates/prompts.html")


# ── Утилиты ───────────────────────────────────────────────────────────────────

async def check_service(url: str, timeout: float = 5) -> bool:
    """Проверяет доступность внешнего сервиса."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"check_service({url}) failed: {type(e).__name__}: {e}")
        return False


# ── Глобальные обработчики ────────────────────────────────────────────────────

# @app.exception_handler(Exception)
# async def global_exception_handler(request: Request, exc: Exception):
#     logger.error(f"Необработанная ошибка: {request.method} {request.url.path} — {exc}", exc_info=True)

#     if request.url.path.startswith("/api/"):
#         return JSONResponse(
#             {"error": "Внутренняя ошибка сервера. Попробуйте позже."},
#             status_code=500,
#         )

#     return HTMLResponse(
#         content="""
#         <html>
#         <head><title>Ошибка</title></head>
#         <body style="font-family:Arial; padding:40px; background:#1a1a2e; color:#eee;">
#             <h1>⚠️ Произошла ошибка</h1>
#             <p>Сервер столкнулся с непредвиденной ситуацией.</p>
#             <p>Попробуйте обновить страницу или вернуться на <a href="/" style="color:#4fc3f7;">главную</a>.</p>
#         </body>
#         </html>
#         """,
#         status_code=500,
#     )


# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     start = time.time()
#     response = await call_next(request)
#     duration = round(time.time() - start, 3)

#     if not request.url.path.startswith("/static"):
#         logger.info(
#             f"{request.method} {request.url.path} → {response.status_code} ({duration}s) "
#             f"IP={request.client.host}"
#         )

#     return response
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Пропускаем WebSocket — middleware("http") ломает upgrade
    if request.headers.get("upgrade", "").lower() == "websocket":
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    duration = round(time.time() - start, 3)

    if not request.url.path.startswith("/static"):
        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} ({duration}s) "
            f"IP={request.client.host}"
        )

    return response
    

# ── Инициализация БД ──────────────────────────────────────────────────────────

init_db()


# ── Сессионные cookie ─────────────────────────────────────────────────────────

def _session_fernet() -> Fernet:
    """Fernet для шифрования cookie-сессий. Ключ из SECRET_KEY (32 байта → base64)."""
    key = hashlib.sha256(SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encode_session(data: dict) -> str:
    """Шифрует данные сессии в Fernet-токен."""
    payload = json.dumps(data).encode()
    return _session_fernet().encrypt(payload).decode()


def decode_session(cookie: str) -> dict | None:
    """Расшифровывает cookie. Возвращает None если подделана или протухла."""
    try:
        data = _session_fernet().decrypt(cookie.encode(), ttl=43200)  # 12 часов
        return json.loads(data.decode())
    except (InvalidToken, Exception):
        return None


def get_session(request: Request) -> dict | None:
    return decode_session(request.cookies.get("session", ""))


def require_session(request: Request):
    """Возвращает (session, None) или (None, RedirectResponse на /login)."""
    session = get_session(request)
    if not session:
        return None, RedirectResponse(url="/login", status_code=302)
    onec_password = decrypt_onec_password(session["password"])
    set_credentials(session["onec_base_url"], session["user"], onec_password)
    return session, None


# ── Вспомогательные функции шаблонов ──────────────────────────────────────────

def _render_login(error: str = "", username: str = "") -> str:
    html = LOGIN_TEMPLATE_PATH.read_text(encoding="utf-8")
    error_block = (
        f'<div class="error-msg"><i class="bi bi-exclamation-circle"></i>{error}</div>'
        if error else ""
    )
    html = html.replace("/*@@ERROR_BLOCK@@*/", error_block)
    html = html.replace("/*@@USERNAME@@*/",    username)
    return html


def _render_register(error: str = "", username: str = "", onec_base_url: str = "") -> str:
    html = REGISTER_TEMPLATE_PATH.read_text(encoding="utf-8")
    error_block = (
        f'<div class="error-msg"><i class="bi bi-exclamation-circle"></i>{error}</div>'
        if error else ""
    )
    html = html.replace("/*@@ERROR_BLOCK@@*/",   error_block)
    html = html.replace("/*@@USERNAME@@*/",       username)
    html = html.replace("/*@@ONEC_BASE_URL@@*/",  onec_base_url)
    return html


# ── Авторизация ───────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_session(request):
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(content=_render_login())


@app.post("/login")
@limiter.limit("5/minute")
async def login_submit(
    request:  Request,
    username: str = Form(...),
    password: str = Form(default=""),
):
    username = username.strip()

    if not username:
        return HTMLResponse(
            content=_render_login(error="Введите логин"),
            status_code=400,
        )

    user = get_user(username)
    if not user:
        return HTMLResponse(
            content=_render_login(error="Пользователь не найден", username=username),
            status_code=401,
        )

    if not verify_password(password, user["password_hash"]):
        return HTMLResponse(
            content=_render_login(error="Неверный пароль", username=username),
            status_code=401,
        )

    onec_base_url = user["onec_base_url"]
    set_credentials(onec_base_url, username, password)
    try:
        await fetch_employees()
    except Exception as e:
        return HTMLResponse(
            content=_render_login(
                error=f"Не удалось подключиться к 1С: {e}",
                username=username,
            ),
            status_code=502,
        )

    encrypted_pw = _fernet().encrypt(password.encode()).decode()
    session_data = {"onec_base_url": onec_base_url, "user": username, "password": encrypted_pw}
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=encode_session(session_data),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


# ── Регистрация ───────────────────────────────────────────────────────────────

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if get_session(request):
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(content=_render_register())


@app.post("/register")
@limiter.limit("5/minute")
async def register_submit(
    request:       Request,
    onec_base_url: str = Form(...),
    username:      str = Form(...),
    password:      str = Form(default=""),
):
    onec_base_url = onec_base_url.strip().rstrip("/")
    if not onec_base_url.startswith("http://") and not onec_base_url.startswith("https://"):
        onec_base_url = "http://" + onec_base_url
    username = username.strip()

    if not onec_base_url or not username:
        return HTMLResponse(
            content=_render_register(
                error="Заполните все обязательные поля",
                username=username,
                onec_base_url=onec_base_url,
            ),
            status_code=400,
        )

    if username_exists(username):
        return HTMLResponse(
            content=_render_register(
                error="Пользователь с таким логином уже существует",
                username=username,
                onec_base_url=onec_base_url,
            ),
            status_code=400,
        )

    set_credentials(onec_base_url, username, password)
    try:
        await fetch_employees()
    except Exception as e:
        return HTMLResponse(
            content=_render_register(
                error=f"Не удалось подключиться к 1С: {e}",
                username=username,
                onec_base_url=onec_base_url,
            ),
            status_code=502,
        )

    create_user(username, password, onec_base_url)

    encrypted_pw = _fernet().encrypt(password.encode()).decode()
    session_data = {"onec_base_url": onec_base_url, "user": username, "password": encrypted_pw}
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=encode_session(session_data),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


# ── Страницы ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect
    return HTMLResponse(content=INDEX_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/price-list", response_class=HTMLResponse)
async def get_price_list(request: Request):
    session, redirect = require_session(request)
    if redirect:
        return redirect

    cache_key = session["onec_base_url"]

    cached = get_cached("price", cache_key, "price_list")
    if cached:
        price_list, groups_hierarchy, groups_list, price_columns = cached
    else:
        try:
            nomenclature = await fetch_nomenclature()
            prices = await fetch_prices(price_type_keys=list(PRICE_COLUMNS.keys()))
            stocks = await fetch_stocks()
            reserves = await fetch_reserves()
            groups = await fetch_groups()
        except Exception as e:
            logger.error(f"Ошибка подключения к 1С: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"Ошибка подключения к 1С: {e}")

        try:
            price_list       = build_price_list(nomenclature, prices, stocks, reserves, groups)
            groups_hierarchy = build_groups_hierarchy(groups)
            groups_list      = get_unique_groups(price_list)
            price_columns    = list(PRICE_COLUMNS.values())
        except Exception as e:
            logger.error(f"Ошибка обработки данных: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка обработки данных: {e}")

        set_cached("price", (price_list, groups_hierarchy, groups_list, price_columns), cache_key, "price_list")

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("/*@@PRICE_DATA@@*/[]",       json.dumps(price_list,       ensure_ascii=False))
    html = html.replace("/*@@GROUPS_LIST@@*/[]",      json.dumps(groups_list,      ensure_ascii=False))
    html = html.replace("/*@@PRICE_COLUMNS@@*/[]",    json.dumps(price_columns,    ensure_ascii=False))
    html = html.replace("/*@@GROUPS_HIERARCHY@@*/[]", json.dumps(groups_hierarchy, ensure_ascii=False))

    return HTMLResponse(content=html)


@app.get("/dashboard/managers", response_class=HTMLResponse)
async def get_managers_dashboard(
    request:    Request,
    start_date: str = Query(default=None),
    end_date:   str = Query(default=None),
):
    session, redirect = require_session(request)
    if redirect:
        return redirect

    today = date.today()
    if not start_date:
        start_date = (today - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = today.isoformat()

    cache_key = session["onec_base_url"]
    cached = get_cached("dashboard", cache_key, start_date, end_date)
    if cached:
        managers_data, totals = cached
    else:
        try:
            employees = await fetch_employees()
            orders    = await fetch_orders(start_date=start_date, end_date=end_date)
            revenues  = await fetch_revenues(start_date=start_date, end_date=end_date)
            payments  = await fetch_payments(start_date=start_date, end_date=end_date)
            debts     = await fetch_debts()
            events    = await fetch_events(start_date=start_date, end_date=end_date)
        except Exception as e:
            logger.error(f"Ошибка подключения к 1С: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"Ошибка подключения к 1С: {e}")

        try:
            contragents = await fetch_contragents()
            managers_data, totals = build_managers_dashboard(
                employees, orders, revenues, payments, debts, events, contragents
            )
        except Exception as e:
            logger.error(f"Ошибка обработки данных: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка обработки данных: {e}")

        set_cached("dashboard", (managers_data, totals), cache_key, start_date, end_date)

    def fmt(d: str) -> str:
        y, m, day = d.split("-")
        return f"{day}.{m}.{y}"

    period_str = f"{fmt(start_date)} — {fmt(end_date)}"

    html = DASHBOARD_TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("/*@@MANAGERS_DATA@@*/[]", json.dumps(managers_data, ensure_ascii=False))
    html = html.replace("/*@@TOTALS_DATA@@*/[]",   json.dumps(totals,        ensure_ascii=False))
    html = html.replace("/*@@PERIOD_TITLE@@*/",    period_str)
    html = html.replace("/*@@PERIOD_SUBTITLE@@*/", period_str)
    html = html.replace("/*@@START_DATE@@*/",      start_date)
    html = html.replace("/*@@END_DATE@@*/",        end_date)

    return HTMLResponse(content=html)


@app.get("/report/sales", response_class=HTMLResponse)
async def get_sales_report(
    request:    Request,
    start_date: str = Query(default=None),
    end_date:   str = Query(default=None),
):
    _, redirect = require_session(request)
    if redirect:
        return redirect

    today = date.today()
    if not start_date:
        start_date = today.replace(day=1).isoformat()
    if not end_date:
        end_date = today.isoformat()

    try:
        invoices    = await fetch_sales(start_date=start_date, end_date=end_date)
        nom_raw     = await fetch_nomenclature()
        contragents = await fetch_contragents()
        employees   = await fetch_employees()
        order_nums  = await fetch_order_numbers()
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Ошибка подключения к 1С: {e}")

    try:
        nom_index   = {
            n["Ref_Key"]: n.get("Description", "")
            for n in nom_raw
            if not n.get("IsFolder", False)
        }
        cont_index  = {c["Ref_Key"]: c.get("Description", "") for c in contragents}
        emp_index   = {e["Ref_Key"]: e.get("Description", "") for e in employees}
        order_index = {o["Ref_Key"]: o.get("Number", "") for o in order_nums}

        costs = await fetch_cost_by_orders(start_date=start_date, end_date=end_date)

        sales_data, daily_sales_data = build_sales_report(
            invoices, nom_index, cont_index, emp_index, costs, order_index
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обработки данных: {e}")

    def fmt(d: str) -> str:
        y, m, day = d.split("-")
        return f"{day}.{m}.{y}"

    period_str   = f"{fmt(start_date)} — {fmt(end_date)}"
    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    html = SALES_TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("/*@@SALES_DATA@@*/[]",       json.dumps(sales_data,       ensure_ascii=False))
    html = html.replace("/*@@DAILY_SALES_DATA@@*/[]", json.dumps(daily_sales_data, ensure_ascii=False))
    html = html.replace("/*@@PERIOD_DISPLAY@@*/",     period_str)
    html = html.replace("/*@@GENERATED_AT@@*/",       generated_at)
    html = html.replace("/*@@START_DATE@@*/",         start_date)
    html = html.replace("/*@@END_DATE@@*/",           end_date)

    return HTMLResponse(content=html)


# ── ИИ-ассистент ──────────────────────────────────────────────────────────────

@app.get("/chat", response_class=HTMLResponse)
async def get_chat(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect
    return HTMLResponse(content=CHAT_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.post("/api/chat")
@limiter.limit("20/minute")
async def post_chat(request: Request, body: ChatMessage):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    if not await check_service(f"{AI_SERVICE_URL}/health"):
        return JSONResponse(
            {"error": "AI-сервис недоступен. Попробуйте позже."},
            status_code=503,
        )

    # Промпт из БД (если заполнен)
    chat_prompt = get_prompt("chat")
    system_prompt = chat_prompt["content"] if chat_prompt and chat_prompt["content"].strip() else ""

    _parsed = urlparse(session["onec_base_url"])
    onec_ip = _parsed.netloc + _parsed.path.rstrip("/")
    try:
        answer = await ai_chat(
            body.prompt,
            session["user"],
            decrypt_onec_password(session["password"]),
            onec_ip,
            system_prompt=system_prompt,
        )
    except Exception as e:
        logger.error(f"Ошибка AI-чата: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=502)

    return JSONResponse({"answer": answer})


@app.websocket("/ws/chat")
async def ws_chat_proxy(websocket: WebSocket):
    """
    WebSocket прокси: браузер ↔ дашборд ↔ AI Bridge.
    Дашборд добавляет credentials и system_prompt из сессии.
    """
    # Проверяем сессию через cookie

    cookie = websocket.cookies.get("session", "")
    logger.info(f"WS /ws/chat: cookie={'есть' if cookie else 'НЕТ'}")
    session = decode_session(cookie)
    logger.info(f"WS /ws/chat: session={'есть' if session else 'НЕТ'}")

    session = decode_session(websocket.cookies.get("session", ""))
    if not session:
        await websocket.close(code=4401, reason="Не авторизован")
        return

    await websocket.accept()

    onec_password = decrypt_onec_password(session["password"])
    _parsed = urlparse(session["onec_base_url"])
    onec_ip = _parsed.netloc + _parsed.path.rstrip("/")

    # Промпт из БД
    chat_prompt = get_prompt("chat")
    system_prompt = chat_prompt["content"] if chat_prompt and chat_prompt["content"].strip() else ""

    # URL AI Bridge WebSocket
    ai_ws_url = AI_SERVICE_URL.replace("http://", "ws://").replace("https://", "wss://")
    ai_ws_url = f"{ai_ws_url}/chat/ws"

    try:
        async with websockets.connect(ai_ws_url) as ai_ws:
            while True:
                # Получаем промпт от браузера
                raw = await websocket.receive_text()
                data = json.loads(raw)

                # Дополняем credentials и system_prompt
                data["credentials"] = {
                    "login": session["user"],
                    "password": onec_password,
                    "ip": onec_ip,
                }
                data["system_prompt"] = system_prompt

                # Отправляем в AI Bridge
                await ai_ws.send(json.dumps(data, ensure_ascii=False))

                # Проксируем ответы обратно в браузер
                while True:
                    response = await ai_ws.recv()
                    await websocket.send_text(response)

                    event = json.loads(response)
                    if event.get("type") in ("done", "error"):
                        break

    except WebSocketDisconnect:
        logger.info("WS чат: клиент отключился")
    except Exception as e:
        logger.error(f"WS чат ошибка: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ── Финансовый дайджест ───────────────────────────────────────────────────────

@app.get("/digest", response_class=HTMLResponse)
async def digest_page(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect
    return HTMLResponse(content=DIGEST_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/digest/providers")
async def api_digest_providers(request: Request):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    result = await get_providers()
    return JSONResponse(result)


@app.post("/api/digest")
@limiter.limit("5/hour")
async def api_digest(request: Request, body: DigestBody):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    if not await check_service(f"{DIGEST_SERVICE_URL}/health"):
        return JSONResponse(
            {"error": "Сервис дайджеста недоступен. Попробуйте позже."},
            status_code=503,
        )

    # Промпт из БД (если заполнен)
    digest_prompt = get_prompt("digest")
    system_prompt = digest_prompt["content"] if digest_prompt and digest_prompt["content"].strip() else ""

    result = await generate_digest(
        login=session["user"],
        password=decrypt_onec_password(session["password"]),
        onec_base_url=session["onec_base_url"],
        date=body.date,
        provider=body.provider,
        system_prompt=system_prompt,
    )
    return JSONResponse(result)


@app.post("/api/digest/ask")
async def api_digest_ask(request: Request, body: AskBody):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    # Промпт «ask» из БД (если заполнен)
    ask_prompt = get_prompt("ask")
    system_prompt = ask_prompt["content"] if ask_prompt and ask_prompt["content"].strip() else ""

    result = await ask_question(
        login=session["user"],
        password=decrypt_onec_password(session["password"]),
        onec_base_url=session["onec_base_url"],
        question=body.question,
        provider=body.provider,
        system_prompt=system_prompt,
    )
    return JSONResponse(result)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    ai_ok = await check_service(f"{AI_SERVICE_URL}/health")
    digest_ok = await check_service(f"{DIGEST_SERVICE_URL}/health")

    return {
        "status": "ok",
        "services": {
            "dashboard": True,
            "ai_bridge": ai_ok,
            "digest_api": digest_ok,
        }
    }


# ── Библиотека промптов ──────────────────────────────────────────────────────

@app.get("/prompts", response_class=HTMLResponse)
async def prompts_page(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect
    return HTMLResponse(content=PROMPTS_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/prompts")
async def api_get_prompts(request: Request):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return JSONResponse(get_all_prompts())


@app.get("/api/prompts/{prompt_id}")
async def api_get_prompt(request: Request, prompt_id: str):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    prompt = get_prompt(prompt_id)
    if not prompt:
        return JSONResponse({"error": "Промпт не найден"}, status_code=404)
    return JSONResponse(prompt)


@app.post("/api/prompts/{prompt_id}")
async def api_update_prompt(request: Request, prompt_id: str, body: PromptUpdate):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    prompt = get_prompt(prompt_id)
    if not prompt:
        return JSONResponse({"error": "Промпт не найден"}, status_code=404)
    update_prompt(prompt_id, body.content)
    logger.info(f"Промпт '{prompt_id}' обновлён пользователем {session['user']}")
    return JSONResponse({"status": "ok"})


@app.get("/api/prompts/{prompt_id}/templates")
async def api_get_templates(request: Request, prompt_id: str):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    return JSONResponse(get_templates(prompt_id))


@app.post("/api/prompts/{prompt_id}/templates")
async def api_create_template(request: Request, prompt_id: str, body: TemplateCreate):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    tid = create_template(prompt_id, body.name, body.content)
    logger.info(f"Шаблон '{body.name}' создан для промпта '{prompt_id}'")
    return JSONResponse({"status": "ok", "id": tid})


@app.delete("/api/prompts/templates/{template_id}")
async def api_delete_template(request: Request, template_id: int):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    delete_template(template_id)
    return JSONResponse({"status": "ok"})


# ── Запуск ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # uvicorn.run("main:app", host="0.0.0.0", port=9001, reload=True)
    uvicorn.run("main:app", host="0.0.0.0", port=9001, reload=False)
