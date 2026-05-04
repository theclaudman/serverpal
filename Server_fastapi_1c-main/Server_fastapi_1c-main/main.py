# main.py

from database import init_db, get_user, username_exists, create_user, verify_password, decrypt_onec_password
import base64
import hashlib
#import hmac
import json
import traceback
from datetime import date, datetime, timedelta
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from config import PRICE_COLUMNS, SECRET_KEY
from database import init_db, get_user, username_exists, create_user
from services.onec_client import (
    fetch_nomenclature,
    fetch_prices,
    fetch_stocks,
    fetch_reserves,
    fetch_groups,
    fetch_contragents,
    fetch_cost_by_orders,
    fetch_employees,
    fetch_orders,
    fetch_revenues,
    fetch_payments,
    fetch_debts,
    fetch_events,
    fetch_sales,
    fetch_order_numbers,
    set_credentials,
)
from services.data_builder import (
    build_price_list,
    build_groups_hierarchy,
    get_unique_groups,
)
from services.dashboard_builder import build_managers_dashboard
from services.sales_builder import build_sales_report
from services.ai_client import chat as ai_chat
from services.digest_client import get_providers, generate_digest, ask_question

app = FastAPI()

init_db()

CHAT_TEMPLATE_PATH      = Path("templates/chat.html")
DIGEST_TEMPLATE_PATH    = Path("templates/digest.html")
INDEX_TEMPLATE_PATH     = Path("templates/index.html")
LOGIN_TEMPLATE_PATH     = Path("templates/login.html")
REGISTER_TEMPLATE_PATH  = Path("templates/register.html")
TEMPLATE_PATH           = Path("templates/price_list.html")
DASHBOARD_TEMPLATE_PATH = Path("templates/managers_dashboard.html")
SALES_TEMPLATE_PATH     = Path("templates/sales_report.html")


# ── Сессионные cookie ────────────────────────────────────────────────────────

from cryptography.fernet import Fernet, InvalidToken

def _session_fernet() -> Fernet:
    """Fernet для шифрования cookie-сессий. Ключ из SECRET_KEY (32 байта → base64)."""
    import hashlib
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


# ── Вспомогательные функции шаблонов ─────────────────────────────────────────

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


# ── Авторизация ──────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_session(request):
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(content=_render_login())


@app.post("/login")
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

    # Ищем пользователя в БД
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

    # Проверяем подключение к 1С
    onec_base_url = user["onec_base_url"]
    set_credentials(onec_base_url, username, password)
    try:
        fetch_employees()
    except Exception as e:
        return HTMLResponse(
            content=_render_login(
                error=f"Не удалось подключиться к 1С: {e}",
                username=username,
            ),
            status_code=502,
        )

    from database import _fernet
    encrypted_pw = _fernet().encrypt(password.encode()).decode()
    session_data = {"onec_base_url": onec_base_url, "user": username, "password": encrypted_pw}
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=encode_session(session_data),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,  # 12 часов
    )
    return response


# ── Регистрация ───────────────────────────────────────────────────────────────

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if get_session(request):
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(content=_render_register())


@app.post("/register")
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

    # Проверяем подключение к 1С перед сохранением
    set_credentials(onec_base_url, username, password)
    try:
        fetch_employees()
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

    # Автоматически входим после регистрации
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
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


# ── Страницы ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def get_index(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect
    return HTMLResponse(content=INDEX_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/price-list", response_class=HTMLResponse)
def get_price_list(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect

    try:
        nomenclature = fetch_nomenclature()
        prices = fetch_prices(price_type_keys=list(PRICE_COLUMNS.keys()))
        stocks = fetch_stocks()
        reserves = fetch_reserves()
        groups = fetch_groups()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка подключения к 1С: {e}")

    try:
        price_list       = build_price_list(nomenclature, prices, stocks, reserves, groups)
        groups_hierarchy = build_groups_hierarchy(groups)
        groups_list      = get_unique_groups(price_list)
        price_columns    = list(PRICE_COLUMNS.values())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки данных: {e}")

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("/*@@PRICE_DATA@@*/[]",       json.dumps(price_list,       ensure_ascii=False))
    html = html.replace("/*@@GROUPS_LIST@@*/[]",      json.dumps(groups_list,      ensure_ascii=False))
    html = html.replace("/*@@PRICE_COLUMNS@@*/[]",    json.dumps(price_columns,    ensure_ascii=False))
    html = html.replace("/*@@GROUPS_HIERARCHY@@*/[]", json.dumps(groups_hierarchy, ensure_ascii=False))

    return HTMLResponse(content=html)


@app.get("/dashboard/managers", response_class=HTMLResponse)
def get_managers_dashboard(
    request:    Request,
    start_date: str = Query(default=None),
    end_date:   str = Query(default=None),
):
    _, redirect = require_session(request)
    if redirect:
        return redirect

    today = date.today()
    if not start_date:
        start_date = (today - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = today.isoformat()

    try:
        employees = fetch_employees()
        orders    = fetch_orders(start_date=start_date, end_date=end_date)
        revenues  = fetch_revenues(start_date=start_date, end_date=end_date)
        payments  = fetch_payments(start_date=start_date, end_date=end_date)
        debts     = fetch_debts()
        events    = fetch_events(start_date=start_date, end_date=end_date)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка подключения к 1С: {e}")

    try:
        contragents = fetch_contragents()
        managers_data, totals = build_managers_dashboard(
            employees, orders, revenues, payments, debts, events, contragents
        )
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Ошибка обработки данных: {e}")

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
def get_sales_report(
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
        invoices    = fetch_sales(start_date=start_date, end_date=end_date)
        nom_raw     = fetch_nomenclature()
        contragents = fetch_contragents()
        employees   = fetch_employees()
        order_nums  = fetch_order_numbers()
    except Exception as e:
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

        costs = fetch_cost_by_orders(start_date=start_date, end_date=end_date)

        sales_data, daily_sales_data = build_sales_report(
            invoices, nom_index, cont_index, emp_index, costs, order_index
        )
    except Exception as e:
        print(traceback.format_exc())
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


# ── ИИ-ассистент ─────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    prompt: str


@app.get("/chat", response_class=HTMLResponse)
def get_chat(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect
    return HTMLResponse(content=CHAT_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.post("/api/chat")
async def post_chat(request: Request, body: ChatMessage):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    _parsed = urlparse(session["onec_base_url"])
    onec_ip = _parsed.netloc + _parsed.path.rstrip("/")
    try:
        answer = ai_chat(body.prompt, session["user"], session["password"], onec_ip)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    return JSONResponse({"answer": answer})


# ── Финансовый дайджест ──────────────────────────────────────────────────────

class DigestBody(BaseModel):
    date: str = None
    provider: str = "lmstudio"


class AskBody(BaseModel):
    question: str
    provider: str = "lmstudio"


@app.get("/digest", response_class=HTMLResponse)
def digest_page(request: Request):
    _, redirect = require_session(request)
    if redirect:
        return redirect
    return HTMLResponse(content=DIGEST_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/digest/providers")
async def api_digest_providers(request: Request):
    session, redirect = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    result = get_providers()
    return JSONResponse(result)


@app.post("/api/digest")
async def api_digest(request: Request, body: DigestBody):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    result = generate_digest(
        login=session["user"],
        password=session["password"],
        onec_base_url=session["onec_base_url"],
        date=body.date,
        provider=body.provider,
    )
    return JSONResponse(result)


@app.post("/api/digest/ask")
async def api_digest_ask(request: Request, body: AskBody):
    session, _ = require_session(request)
    if not session:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    result = ask_question(
        login=session["user"],
        password=session["password"],
        onec_base_url=session["onec_base_url"],
        question=body.question,
        provider=body.provider,
    )
    return JSONResponse(result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
