import httpx
import base64
from contextvars import ContextVar

# Контекстные переменные — устанавливаются из сессии для каждого запроса
_ctx_base_url: ContextVar[str] = ContextVar("onec_base_url", default="")
_ctx_user:     ContextVar[str] = ContextVar("onec_user",     default="")
_ctx_password: ContextVar[str] = ContextVar("onec_password", default="")


def set_credentials(onec_base_url: str, user: str, password: str) -> None:
    _ctx_base_url.set(f"{onec_base_url}/odata/standard.odata")
    _ctx_user.set(user)
    _ctx_password.set(password)


def _base_url() -> str:
    return _ctx_base_url.get()

def _user() -> str:
    return _ctx_user.get()

def _password() -> str:
    return _ctx_password.get()


async def safe_get(url: str) -> dict:
    """Выполняет асинхронный GET запрос к 1С OData."""
    auth = httpx.BasicAuth(_user(), _password())
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
        return response.json()


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
    try:
        url = (
            f"{_base_url()}/AccumulationRegister_РезервыТоваровОрганизаций/Balance"
            f"?$format=json"
            f"&$select=Номенклатура_Key,КоличествоBalance"
        )
        return (await safe_get(url)).get("value", [])
    except Exception:
        return []


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