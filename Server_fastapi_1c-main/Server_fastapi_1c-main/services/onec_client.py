import urllib.request
import urllib.parse
import base64
import json
from contextvars import ContextVar

# Контекстные переменные — устанавливаются из сессии для каждого запроса
_ctx_base_url: ContextVar[str] = ContextVar("onec_base_url", default="")
_ctx_user:     ContextVar[str] = ContextVar("onec_user",     default="")
_ctx_password: ContextVar[str] = ContextVar("onec_password", default="")


def set_credentials(onec_base_url: str, user: str, password: str) -> None:
    """Устанавливает учётные данные для текущего запроса."""
    _ctx_base_url.set(f"{onec_base_url}/odata/standard.odata")
    _ctx_user.set(user)
    _ctx_password.set(password)


def _base_url() -> str:
    return _ctx_base_url.get()

def _user() -> str:
    return _ctx_user.get()

def _password() -> str:
    return _ctx_password.get()


def safe_get(url: str) -> dict:
    """Выполняет GET запрос с кириллицей в URL через urllib"""
    credentials = base64.b64encode(
        f"{_user()}:{_password()}".encode("utf-8")
    ).decode("utf-8")

    # Кодируем только нелатинские символы, оставляя спецсимволы URL нетронутыми
    encoded_url = urllib.parse.quote(url, safe=":/?=&'().,@!$-_~#+%")

    req = urllib.request.Request(encoded_url)
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Accept", "application/json")

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_client():
    """Оставляем для совместимости — возвращает None"""
    return None


def fetch_nomenclature(client=None) -> list:
    url = (
        f"{_base_url()}/Catalog_Номенклатура"
        f"?$format=json"
        f"&$select=Ref_Key,Description,Артикул,Parent_Key,IsFolder,ИсключитьИзПрайсЛистов,Недействителен"
    )
    return safe_get(url).get("value", [])


def fetch_prices(client=None, price_type_keys: list = []) -> list:
    guids = " or ".join(
        [f"ВидЦен_Key eq guid'{key}'" for key in price_type_keys]
    )
    url = (
        f"{_base_url()}/InformationRegister_ЦеныНоменклатуры/SliceLast"
        f"?$format=json"
        f"&$filter={guids}"
        f"&$select=Номенклатура_Key,ВидЦен_Key,Цена"
    )
    return safe_get(url).get("value", [])


def fetch_stocks(client=None) -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_ЗапасыНаСкладах/Balance"
        f"?$format=json"
        f"&$select=Номенклатура_Key,КоличествоBalance"
    )
    return safe_get(url).get("value", [])


def fetch_reserves(client=None) -> list:
    try:
        url = (
            f"{_base_url()}/AccumulationRegister_РезервыТоваровОрганизаций/Balance"
            f"?$format=json"
            f"&$select=Номенклатура_Key,КоличествоBalance"
        )
        return safe_get(url).get("value", [])
    except Exception:
        return []


def fetch_groups(client=None) -> list:
    url = (
        f"{_base_url()}/Catalog_Номенклатура"
        f"?$format=json"
        f"&$select=Ref_Key,Description,Parent_Key,IsFolder,Недействителен"
    )
    return safe_get(url).get("value", [])


def fetch_employees(client=None) -> list:
    url = (
        f"{_base_url()}/Catalog_Сотрудники"
        f"?$format=json"
        f"&$select=Ref_Key,Description,ВАрхиве,Недействителен"
    )
    return safe_get(url).get("value", [])


def fetch_orders(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/Document_ЗаказПокупателя"
        f"?$format=json"
        f"&$select=Ref_Key,Date,Ответственный_Key,СуммаДокумента,Контрагент_Key,Posted,ВариантЗавершения"
        f"&$filter=Date ge datetime'{start_date}T00:00:00'"
        f" and Date le datetime'{end_date}T23:59:59'"
        f" and Posted eq true"
    )
    return safe_get(url).get("value", [])


def fetch_revenues(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_ДоходыИРасходы/Turnovers"
        f"(StartPeriod=datetime'{start_date}T00:00:00',EndPeriod=datetime'{end_date}T23:59:59')"
        f"?$format=json"
        f"&$select=ЗаказПокупателя_Key,СуммаДоходовTurnover,СуммаРасходовTurnover"
    )
    return safe_get(url).get("value", [])


def fetch_payments(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_РасчетыСПокупателями/Turnovers"
        f"(StartPeriod=datetime'{start_date}T00:00:00',EndPeriod=datetime'{end_date}T23:59:59')"
        f"?$format=json"
        f"&$select=Заказ,ТипРасчетов,СуммаReceipt"
    )
    return safe_get(url).get("value", [])


def fetch_debts(client=None) -> list:
    url = (
        f"{_base_url()}/AccumulationRegister_РасчетыСПокупателями/Balance"
        f"?$format=json"
        f"&$select=Заказ,Контрагент_Key,СуммаBalance,ТипРасчетов"
    )
    return safe_get(url).get("value", [])


def fetch_events(client=None, start_date: str = "", end_date: str = "") -> list:
    url = (
        f"{_base_url()}/Document_Событие"
        f"?$format=json"
        f"&$select=Ref_Key,Date,Ответственный_Key,ТипСобытия,Posted"
        f"&$filter=Date ge datetime'{start_date}T00:00:00'"
        f" and Date le datetime'{end_date}T23:59:59'"
    )
    return safe_get(url).get("value", [])


def fetch_contragents(client=None) -> list:
    """Получает контрагентов для расшифровки долгов"""
    url = (
        f"{_base_url()}/Catalog_Контрагенты"
        f"?$format=json"
        f"&$select=Ref_Key,Description"
    )
    return safe_get(url).get("value", [])


def fetch_sales(client=None, start_date: str = "", end_date: str = "") -> list:
    """Получает расходные накладные с табличной частью за период"""
    url = (
        f"{_base_url()}/Document_РасходнаяНакладная"
        f"?$format=json"
        f"&$select=Ref_Key,Date,Контрагент_Key,Ответственный_Key,Posted,Запасы"
        f"&$filter=Date ge datetime'{start_date}T00:00:00'"
        f" and Date le datetime'{end_date}T23:59:59'"
        f" and Posted eq true"
    )
    return safe_get(url).get("value", [])


def fetch_order_numbers(client=None) -> list:
    """Получает номера всех заказов для расшифровки UUID в накладных"""
    url = (
        f"{_base_url()}/Document_ЗаказПокупателя"
        f"?$format=json"
        f"&$select=Ref_Key,Number"
    )
    return safe_get(url).get("value", [])


def fetch_cost_by_orders(client=None, start_date: str = "", end_date: str = "") -> list:
    """Получает себестоимость в разрезе заказов из ДоходыИРасходы"""
    url = (
        f"{_base_url()}/AccumulationRegister_ДоходыИРасходы/Turnovers"
        f"(StartPeriod=datetime'{start_date}T00:00:00',EndPeriod=datetime'{end_date}T23:59:59')"
        f"?$format=json"
        f"&$select=ЗаказПокупателя_Key,СуммаРасходовTurnover"
    )
    return safe_get(url).get("value", [])
