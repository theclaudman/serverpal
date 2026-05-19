import httpx
import base64
import inspect
import logging
import time
from contextvars import ContextVar
from urllib.parse import urljoin

# Контекстные переменные — устанавливаются из сессии для каждого запроса
_ctx_base_url: ContextVar[str] = ContextVar("onec_base_url", default="")
_ctx_user:     ContextVar[str] = ContextVar("onec_user",     default="")
_ctx_password: ContextVar[str] = ContextVar("onec_password", default="")

logger = logging.getLogger("dashboard.odata")


def set_credentials(onec_base_url: str, user: str, password: str) -> None:
    _ctx_base_url.set(_normalize_odata_base_url(onec_base_url))
    _ctx_user.set(user)
    _ctx_password.set(password)


def _normalize_odata_base_url(onec_base_url: str) -> str:
    url = onec_base_url.strip().rstrip("/")
    marker = "/odata/standard.odata"
    marker_index = url.lower().find(marker)
    if marker_index >= 0:
        return url[: marker_index + len(marker)]
    return f"{url}{marker}"


def _base_url() -> str:
    return _ctx_base_url.get()

def _user() -> str:
    return _ctx_user.get()

def _password() -> str:
    return _ctx_password.get()


async def safe_get(url: str, *, optional_statuses: set[int] | None = None) -> dict:
    """Execute GET against 1C OData and return a merged value list."""
    operation = _caller_name()
    entity = _entity_name(url)
    started = time.perf_counter()
    response = None
    next_url = url
    pages = 0
    rows: list = []
    size_bytes = 0
    status_codes: list[int] = []
    auth = httpx.BasicAuth(_user(), _password())
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            while next_url:
                response = await client.get(next_url, auth=auth)
                status_codes.append(response.status_code)
                size_bytes += len(response.content)

                if optional_statuses and response.status_code in optional_statuses:
                    duration = time.perf_counter() - started
                    logger.info(
                        "OData %s entity=%s optional_missing status=%s rows=0 pages=%s bytes=%s size=%s duration=%.3fs",
                        operation,
                        entity,
                        response.status_code,
                        pages,
                        size_bytes,
                        _format_size(size_bytes),
                        duration,
                    )
                    return {"value": []}

                response.raise_for_status()
                payload = response.json()
                page_rows = payload.get("value", [])
                if isinstance(page_rows, list):
                    rows.extend(page_rows)
                pages += 1
                next_url = _next_link(payload, response.url)

        duration = time.perf_counter() - started
        logger.info(
            "OData %s entity=%s status=%s rows=%s pages=%s bytes=%s size=%s duration=%.3fs",
            operation,
            entity,
            ",".join(str(code) for code in status_codes),
            len(rows),
            pages,
            size_bytes,
            _format_size(size_bytes),
            duration,
        )
        return {"value": rows}
    except Exception:
        duration = time.perf_counter() - started
        status = response.status_code if response is not None else "n/a"
        logger.exception(
            "OData %s entity=%s failed status=%s rows=%s pages=%s bytes=%s size=%s duration=%.3fs",
            operation,
            entity,
            status,
            len(rows),
            pages,
            size_bytes,
            _format_size(size_bytes),
            duration,
        )
        raise


def _caller_name() -> str:
    frame = inspect.currentframe()
    caller = frame.f_back.f_back if frame and frame.f_back and frame.f_back.f_back else None
    return caller.f_code.co_name if caller else "safe_get"


def _entity_name(url: str) -> str:
    marker = "/odata/standard.odata/"
    if marker in url:
        tail = url.split(marker, 1)[1]
    else:
        tail = url.rsplit("/", 1)[-1]
    return tail.split("?", 1)[0]


def _next_link(payload: dict, current_url) -> str:
    next_link = (
        payload.get("@odata.nextLink")
        or payload.get("odata.nextLink")
        or payload.get("__next")
    )
    if not next_link:
        return ""
    return urljoin(str(current_url), str(next_link))


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f}MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes}B"


def get_client():
    return None


async def fetch_nomenclature(client=None) -> list:
    url = (
        f"{_base_url()}/Catalog_Номенклатура"
        f"?$format=json"
        f"&$select=Ref_Key,Description,Артикул,Parent_Key,IsFolder,ИсключитьИзПрайсЛистов,Недействителен"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_prices(client=None, price_type_keys: list = []) -> list:
    if not price_type_keys:
        logger.info("OData fetch_prices skipped: no price type keys")
        return []
    guids = " or ".join(
        [f"ВидЦен_Key eq guid'{key}'" for key in price_type_keys]
    )
    url = (
        f"{_base_url()}/InformationRegister_ЦеныНоменклатуры/SliceLast"
        f"?$format=json"
        f"&$filter={guids}"
        f"&$select=Номенклатура_Key,ВидЦен_Key,Цена"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_stocks(client=None) -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_ЗапасыНаСкладах/Balance"
        f"?$format=json"
        f"&$select=Номенклатура_Key,КоличествоBalance"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_reserves(client=None) -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_РезервыТоваровОрганизаций/Balance"
        f"?$format=json"
        f"&$select=Номенклатура_Key,КоличествоBalance"
    )
    return (await safe_get(url, optional_statuses={404})).get("value", [])


async def fetch_groups(client=None) -> list:
    url = (
        f"{_base_url()}/Catalog_Номенклатура"
        f"?$format=json"
        f"&$select=Ref_Key,Description,Parent_Key,IsFolder,Недействителен"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_employees(client=None) -> list:
    url = (
        f"{_base_url()}/Catalog_Сотрудники"
        f"?$format=json"
        f"&$select=Ref_Key,Description,ВАрхиве,Недействителен"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_orders(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/Document_ЗаказПокупателя"
        f"?$format=json"
        f"&$select=Ref_Key,Date,Ответственный_Key,СуммаДокумента,Контрагент_Key,Posted,ВариантЗавершения"
        f"&$filter=Date ge datetime'{start_date}T00:00:00'"
        f" and Date le datetime'{end_date}T23:59:59'"
        f" and Posted eq true"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_revenues(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_ДоходыИРасходы/Turnovers"
        f"(StartPeriod=datetime'{start_date}T00:00:00',EndPeriod=datetime'{end_date}T23:59:59')"
        f"?$format=json"
        f"&$select=ЗаказПокупателя_Key,СуммаДоходовTurnover,СуммаРасходовTurnover"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_payments(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_РасчетыСПокупателями/Turnovers"
        f"(StartPeriod=datetime'{start_date}T00:00:00',EndPeriod=datetime'{end_date}T23:59:59')"
        f"?$format=json"
        f"&$select=Заказ,ТипРасчетов,СуммаReceipt"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_debts(client=None) -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_РасчетыСПокупателями/Balance"
        f"?$format=json"
        f"&$select=Заказ,Контрагент_Key,СуммаBalance,ТипРасчетов"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_events(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/Document_Событие"
        f"?$format=json"
        f"&$select=Ref_Key,Date,Ответственный_Key,ТипСобытия,Posted"
        f"&$filter=Date ge datetime'{start_date}T00:00:00'"
        f" and Date le datetime'{end_date}T23:59:59'"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_contragents(client=None) -> list:
    url = (
        f"{_base_url()}/Catalog_Контрагенты"
        f"?$format=json"
        f"&$select=Ref_Key,Description"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_sales(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/Document_РасходнаяНакладная"
        f"?$format=json"
        f"&$select=Ref_Key,Date,Контрагент_Key,Ответственный_Key,Posted,Запасы"
        f"&$filter=Date ge datetime'{start_date}T00:00:00'"
        f" and Date le datetime'{end_date}T23:59:59'"
        f" and Posted eq true"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_order_numbers(client=None) -> list:
    url = (
        f"{_base_url()}/Document_ЗаказПокупателя"
        f"?$format=json"
        f"&$select=Ref_Key,Number"
    )
    return (await safe_get(url)).get("value", [])


async def fetch_cost_by_orders(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_ДоходыИРасходы/Turnovers"
        f"(StartPeriod=datetime'{start_date}T00:00:00',EndPeriod=datetime'{end_date}T23:59:59')"
        f"?$format=json"
        f"&$select=ЗаказПокупателя_Key,СуммаРасходовTurnover"
    )
    return (await safe_get(url)).get("value", [])
