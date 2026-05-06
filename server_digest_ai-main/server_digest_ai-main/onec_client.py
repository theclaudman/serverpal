"""
onec_client.py — запросы к 1С УНФ через OData
Все функции параметризованы: base_url, login, password
Работает с любой базой клиента, не только 127.0.0.1
"""

import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _get(base_url: str, login: str, password: str,
         entity: str, params: dict) -> list:
    """
    Выполняет GET-запрос к OData.
    OData-параметры передаются как готовая строка чтобы 1С их понял.
    """
    # Собираем query string вручную — requests не должен трогать $ и кириллицу
    params["$format"] = "json"
    query_string = "&".join(f"{k}={v}" for k, v in params.items())

    # Кодируем только кириллицу в query, оставляя $, =, &, ', () нетронутыми
    import urllib.parse
    query_encoded = urllib.parse.quote(query_string, safe="$=&(),. ':_@!+")

    # Кодируем кириллицу в пути (entity)
    entity_encoded = urllib.parse.quote(entity, safe="/_")

    url = f"{base_url}/{entity_encoded}?{query_encoded}"

    response = requests.get(
        url,
        auth=HTTPBasicAuth(login, password),
        timeout=30
    )
    response.raise_for_status()
    return response.json().get("value", [])


def _fmt_date(dt: datetime) -> str:
    """Форматирует дату для OData фильтра: datetime'2026-04-17T00:00:00'"""
    return f"datetime'{dt.strftime('%Y-%m-%dT%H:%M:%S')}'"


# ---------------------------------------------------------------------------
# Публичные функции — данные для дайджеста
# ---------------------------------------------------------------------------

def fetch_sales(base_url: str, login: str, password: str,
                date_from: datetime, date_to: datetime) -> list[dict]:
    """
    Продажи из расходных накладных за период.
    """
    return _get(base_url, login, password,
        "Document_РасходнаяНакладная",
        {
            "$select": "Date,Number,СуммаДокумента,Контрагент_Key,Ответственный_Key,Posted",
            "$filter": (
                f"Date ge {_fmt_date(date_from)} "
                f"and Date le {_fmt_date(date_to)} "
                f"and Posted eq true"
            ),
            "$orderby": "Date desc",
        }
    )


def fetch_stocks(base_url: str, login: str, password: str) -> list[dict]:
    """
    Остатки товаров на складах.
    """
    return _get(base_url, login, password,
        "AccumulationRegister_ЗапасыНаСкладах/Balance",
        {
            "$select": "Номенклатура_Key,СтруктурнаяЕдиница_Key,КоличествоBalance",
            "$filter": "КоличествоBalance gt 0",
        }
    )


def fetch_debts(base_url: str, login: str, password: str) -> list[dict]:
    """
    Дебиторская задолженность — кто должен и сколько.
    """
    return _get(base_url, login, password,
        "AccumulationRegister_РасчетыСПокупателями/Balance",
        {
            "$select": "Контрагент_Key,Договор_Key,СуммаBalance,ТипРасчетов",
            "$filter": "СуммаBalance gt 0",
            "$orderby": "СуммаBalance desc",
        }
    )


def fetch_money(base_url: str, login: str, password: str) -> list[dict]:
    """
    Остатки денежных средств по счетам и кассам.
    """
    return _get(base_url, login, password,
        "AccumulationRegister_ДенежныеСредства/Balance",
        {
            "$select": "ТипДенежныхСредств,БанковскийСчетКасса,СуммаBalance",
            "$filter": "СуммаBalance gt 0",
        }
    )


def fetch_orders_pending(base_url: str, login: str, password: str) -> list[dict]:
    """
    Заказы покупателей которые ещё не закрыты (в воронке).
    """
    return _get(base_url, login, password,
        "Document_ЗаказПокупателя",
        {
            "$select": "Date,КонтрагентName,СуммаДокумента,МенеджерName,Статус",
            "$filter": "Проведен eq true and Статус ne 'Закрыт'",
            "$orderby": "Date desc",
            "$top": "100",
        }
    )


def fetch_orders_items(base_url: str, login: str, password: str) -> list[dict]:
    """
    Состав заказов покупателей — какой товар и сколько штук.
    Возвращает список: [{Ref_Key, Номенклатура, Количество, Резерв}, ...]
    """
    return _get(base_url, login, password,
        "Document_ЗаказПокупателя_Запасы",
        {
            "$select": "Ref_Key,Номенклатура,Количество,Резерв",
            "$filter": "Количество gt 0",
        }
    )


# ---------------------------------------------------------------------------
# Быстрая проверка подключения
# ---------------------------------------------------------------------------

def check_connection(base_url: str, login: str, password: str) -> bool:
    """
    Проверяет что 1С доступна и авторизация работает.
    """
    try:
        response = requests.get(
            f"{base_url}?$format=json&$top=1",
            auth=HTTPBasicAuth(login, password),
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"  Детали ошибки: {e}")
        return False


# ---------------------------------------------------------------------------
# Точка входа для ручного теста
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    BASE_URL = "http://127.0.0.1/Eu/odata/standard.odata"
    LOGIN    = "admin_r"
    PASSWORD = "123"

    print("Проверка подключения к 1С...")
    if not check_connection(BASE_URL, LOGIN, PASSWORD):
        print("❌ Не удалось подключиться. Проверь URL, логин и пароль.")
        exit(1)
    print("✅ Подключение успешно\n")

    # Продажи за вчера
    yesterday = datetime.now() - timedelta(days=1)
    date_from = yesterday.replace(hour=0,  minute=0,  second=0)
    date_to   = yesterday.replace(hour=23, minute=59, second=59)

    print(f"Продажи за {yesterday.strftime('%d.%m.%Y')}:")
    try:
        sales = fetch_sales(BASE_URL, LOGIN, PASSWORD, date_from, date_to)
        print(f"  Накладных: {len(sales)}")
        if sales:
            total = sum(float(s.get("СуммаДокумента", 0)) for s in sales)
            print(f"  Сумма: {total:,.0f} ₽")
            print(f"  Первая запись: {sales[0]}")
        else:
            print("  Продаж за вчера нет")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")

    print()

    print("Остатки на складе:")
    try:
        stocks = fetch_stocks(BASE_URL, LOGIN, PASSWORD)
        print(f"  Позиций с остатком: {len(stocks)}")
        if stocks:
            print(f"  Первая запись: {stocks[0]}")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")

    print()

    print("Дебиторская задолженность:")
    try:
        debts = fetch_debts(BASE_URL, LOGIN, PASSWORD)
        print(f"  Контрагентов с долгом: {len(debts)}")
        if debts:
            total = sum(float(d.get("СуммаBalance", 0)) for d in debts)

            print(f"  Итого должны: {total:,.0f} ₽")
            print(f"  Первая запись: {debts[0]}")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")

    print()

    print("Денежные средства:")
    try:
        money = fetch_money(BASE_URL, LOGIN, PASSWORD)
        if money:
            total = sum(float(m.get("СуммаBalance", 0)) for m in money)

            print(f"  Итого на счетах: {total:,.0f} ₽")
            for m in money:
                print(f"  {m.get('ТипДенежныхСредств', '?')}: {float(m.get('СуммаBalance', 0)):,.0f} ₽")
        else:
            print("  Данных нет")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")

    print("Состав заказов (товары):")
    try:
        items = fetch_orders_items(BASE_URL, LOGIN, PASSWORD)
        print(f"  Строк в заказах: {len(items)}")
        if items:
            print(f"  Первая запись: {items[0]}")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")


def fetch_names_by_guids(base_url: str, login: str, password: str,
                         catalog: str, guids: list[str]) -> dict[str, str]:
    """
    Возвращает {guid: название} для списка GUIDов из любого справочника.
    catalog — например 'Catalog_Номенклатура' или 'Catalog_Контрагенты'
    """
    if not guids:
        return {}

    # Собираем фильтр: Ref_Key eq guid'...' or Ref_Key eq guid'...'
    parts = " or ".join(f"Ref_Key eq guid'{g}'" for g in guids)

    result = _get(base_url, login, password,
        catalog,
        {
            "$select": "Ref_Key,Description",
            "$filter": parts,
        }
    )
    return {r["Ref_Key"]: r["Description"] for r in result}


def fetch_nomenclature_names(base_url: str, login: str, password: str,
                              guids: list[str]) -> dict[str, str]:
    """Названия номенклатуры по списку GUIDов."""
    return fetch_names_by_guids(base_url, login, password,
                                "Catalog_Номенклатура", guids)


def fetch_contractor_names(base_url: str, login: str, password: str,
                            guids: list[str]) -> dict[str, str]:
    """Названия контрагентов по списку GUIDов."""
    return fetch_names_by_guids(base_url, login, password,
                                "Catalog_Контрагенты", guids)


if __name__ == "__main__":
    BASE_URL = "http://127.0.0.1/Eu/odata/standard.odata"
    LOGIN    = "admin_r"
    PASSWORD = "123"

    # Смотрим какие поля есть в заказах покупателей
    result = _get(BASE_URL, LOGIN, PASSWORD,
        "Document_ЗаказПокупателя",
        {
            "$top": "1"
        }
    )
    if result:
        print("Поля заказа покупателя:")
        for k, v in result[0].items():
            print(f"  {k}: {v}")