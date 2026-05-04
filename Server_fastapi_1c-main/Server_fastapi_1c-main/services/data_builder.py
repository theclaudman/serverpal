# services/data_builder.py

from config import PRICE_COLUMNS


def build_price_list(nomenclature, prices, stocks, reserves, groups):
    """Собирает итоговый список товаров с ценами и остатками"""
    nomenclature = [
        n for n in nomenclature
        if not n.get("IsFolder", False)
        and not n.get("ИсключитьИзПрайсЛистов", False)
        and not n.get("Недействителен", False)
    ]

    # Индексируем цены: {номенклатура_key: {вид_цен_key: цена}}
    prices_index = {}
    for price in prices:
        nom_key = price["Номенклатура_Key"]
        vid_key = price["ВидЦен_Key"]
        if nom_key not in prices_index:
            prices_index[nom_key] = {}
        prices_index[nom_key][vid_key] = price.get("Цена", 0)

    # Индексируем остатки: {номенклатура_key: количество}
    stocks_index = {}
    for stock in stocks:
        nom_key = stock["Номенклатура_Key"]
        stocks_index[nom_key] = stocks_index.get(nom_key, 0) + stock.get("КоличествоBalance", 0)

    # Индексируем резервы: {номенклатура_key: количество}
    reserves_index = {}
    for reserve in reserves:
        nom_key = reserve["Номенклатура_Key"]
        reserves_index[nom_key] = reserves_index.get(nom_key, 0) + reserve.get("КоличествоBalance", 0)

    # Индексируем группы: {ref_key: {Description, Parent_Key}}
    groups_index = {g["Ref_Key"]: g for g in groups}

    # Собираем итоговый список
    result = []
    for nom in nomenclature:
        nom_key = nom["Ref_Key"]
        group_key = nom.get("Parent_Key", "")
        group_name = groups_index.get(group_key, {}).get("Description", "Без группы")

        # Цены по каждому виду
        nom_prices = prices_index.get(nom_key, {})

        # Пропускаем если нет ни одной цены
        has_price = any(nom_prices.get(k, 0) > 0 for k in PRICE_COLUMNS)
        if not has_price:
            continue

        ostatok = stocks_index.get(nom_key, 0)
        rezerv = reserves_index.get(nom_key, 0)
        svobodno = max(ostatok - rezerv, 0)

        row = {
            "Наименование": nom.get("Description", "Без наименования"),
            "Артикул": nom.get("Артикул", "") or "—",
            "Группа": group_name,
            "Group_Key": group_key,
            "ЕдиницаИзмерения": "",
            "Остаток": ostatok,
            "Свободно": svobodno,
        }

        # Добавляем колонки цен
        for price_key, price_name in PRICE_COLUMNS.items():
            row[price_name] = nom_prices.get(price_key, 0)

        result.append(row)

    # Сортируем по группе и наименованию
    result.sort(key=lambda x: (x["Группа"], x["Наименование"]))

    return result


def build_groups_hierarchy(groups):
    return [
        {
            "Ref_Key":     g["Ref_Key"],
            "Description": g["Description"],
            "Parent_Key":  g["Parent_Key"] if g["Parent_Key"] != "00000000-0000-0000-0000-000000000000" else None
        }
        for g in groups
        if g.get("IsFolder", False)
        and not g.get("Недействителен", False)
    ]


def get_unique_groups(price_list):
    """Возвращает список уникальных групп из итогового прайса"""
    seen = set()
    result = []
    for row in price_list:
        if row["Группа"] not in seen:
            seen.add(row["Группа"])
            result.append(row["Группа"])
    return sorted(result)