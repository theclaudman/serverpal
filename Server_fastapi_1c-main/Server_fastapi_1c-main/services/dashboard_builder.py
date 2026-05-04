# services/dashboard_builder.py

def build_managers_dashboard(
    employees, orders, revenues, payments, debts, events, contragents
):
    # Индекс контрагентов: {ref_key: название}
    print("🔥 build_managers_dashboard ВЫЗВАН")
    contragents_index = {
        c["Ref_Key"]: c["Description"]
        for c in contragents
    }

    active_employees = {
        e["Ref_Key"]: e["Description"]
        for e in employees
        if not e.get("ВАрхиве", False)
        and not e.get("Недействителен", False)
    }

    # Индекс заказов: {order_key: {manager_key, sum, contragent}}
    orders_index = {
        o["Ref_Key"]: {
            "manager": o.get("Ответственный_Key", ""),
            "sum":     o.get("СуммаДокумента", 0),
            "contragent": o.get("Контрагент_Key", ""),
            "date":    o.get("Date", ""),
            "variant": o.get("ВариантЗавершения", ""),
        }
        for o in orders
    }

    # Индекс доходов/расходов по заказу: {order_key: {revenue, expenses}}
    revenue_index = {}
    for r in revenues:
        key = r.get("ЗаказПокупателя_Key", "")
        if not key or key == "00000000-0000-0000-0000-000000000000":
            continue
        if key not in revenue_index:
            revenue_index[key] = {"revenue": 0, "expenses": 0}
        revenue_index[key]["revenue"]  += r.get("СуммаДоходовTurnover", 0)
        revenue_index[key]["expenses"] += r.get("СуммаРасходовTurnover", 0)

    # Индекс оплат по заказу: {order_key: сумма}
    payments_index = {}
    for p in payments:
        key = p.get("Заказ", "")
        if not key or key == "00000000-0000-0000-0000-000000000000":
            continue
        if p.get("ТипРасчетов") == "Долг":
            payments_index[key] = payments_index.get(key, 0) + p.get("СуммаReceipt", 0)

    # Индекс долгов по заказу: {order_key: сумма}
    debts_by_order = {}
    debts_by_contragent = {}
    for d in debts:
        if d.get("ТипРасчетов") != "Долг":
            continue
        сумма = d.get("СуммаBalance", 0)
        if сумма <= 0:
            continue
        order_key = d.get("Заказ", "")
        contragent_key = d.get("Контрагент_Key", "")
        if order_key and order_key != "00000000-0000-0000-0000-000000000000":
            debts_by_order[order_key] = debts_by_order.get(order_key, 0) + сумма
        if contragent_key:
            debts_by_contragent[contragent_key] = debts_by_contragent.get(contragent_key, 0) + сумма

    # Индекс событий по менеджеру: {manager_key: {calls, emails}}
    events_index = {}
    for e in events:
        manager = e.get("Ответственный_Key", "")
        if not manager:
            continue
        if manager not in events_index:
            events_index[manager] = {"calls": 0, "emails": 0, "details": []}
        tip = e.get("ТипСобытия", "")
        if tip == "ТелефонныйЗвонок":
            events_index[manager]["calls"] += 1
        elif tip == "ЭлектронноеПисьмо":
            events_index[manager]["emails"] += 1
        events_index[manager]["details"].append({
            "type": tip,
            "date": e.get("Date", "")
        })

    # Собираем данные по каждому менеджеру
    managers_data = []
    totals = {
        "revenue": 0, "profit": 0, "payments": 0,
        "orders": 0, "debt": 0, "events": 0
    }

    for idx, (manager_key, manager_name) in enumerate(active_employees.items()):

        # Заказы менеджера
        manager_orders = [
            (key, val) for key, val in orders_index.items()
            if val["manager"] == manager_key
        ]

        orders_count  = len(manager_orders)
        orders_sum    = sum(v["sum"] for _, v in manager_orders)

        # Выручка и прибыль через ДоходыИРасходы
        revenue  = sum(revenue_index.get(k, {}).get("revenue", 0)  for k, _ in manager_orders)
        expenses = sum(revenue_index.get(k, {}).get("expenses", 0) for k, _ in manager_orders)
        profit   = revenue - expenses

        # Если доходов нет — берём сумму заказов как выручку
        if revenue == 0:
            revenue = orders_sum

        # Оплаты
        paid = sum(payments_index.get(k, 0) for k, _ in manager_orders)

        # Долги
        manager_debt = sum(
            debts_by_order.get(k, 0) for k, _ in manager_orders
        )
        # Уникальные должники
        debtors = set(
            v["contragent"] for k, v in manager_orders
            if debts_by_order.get(k, 0) > 0
        )

        # Детализация заказов
        orders_details = [
            {
                "contragent": contragents_index.get(v["contragent"], v["contragent"]),
                "sum":        v["sum"],
                "profit":     revenue_index.get(k, {}).get("revenue", 0)
                              - revenue_index.get(k, {}).get("expenses", 0),
                "date":       v["date"],
                "status":     v["variant"],
            }
            for k, v in manager_orders
        ]

        # События
        ev = events_index.get(manager_key, {"calls": 0, "emails": 0, "details": []})
        events_count = ev["calls"] + ev["emails"]

        manager_data = {
            "id":              str(idx),
            "name":            _short_name(manager_name),
            "full_name":       manager_name,
            "revenue":         round(revenue,  2),
            "profit":          round(profit,   2),
            "payments":        round(paid,     2),
            "orders":          orders_count,
            "orders_sum":      round(orders_sum, 2),
            "orders_paid":     0,  # детальный статус оплаты требует доп. запроса
            "orders_unpaid":   0,
            "orders_partial":  0,
            "orders_details":  orders_details,
            "debt":            round(manager_debt, 2),
            "debtors_count":   len(debtors),
            "debt_details":    [
                {
                    "contragent": contragents_index.get(v["contragent"], v["contragent"]),
                    "debt":       round(debts_by_order.get(k, 0), 2),
                }
                for k, v in manager_orders
                if debts_by_order.get(k, 0) > 0
            ],
            "events":          events_count,
            "events_calls":    ev["calls"],
            "events_emails":   ev["emails"],
            "events_details":  ev["details"],
            "revenue_details": orders_details,
        }

        managers_data.append(manager_data)

        # Накапливаем итоги
        totals["revenue"]  += revenue
        totals["profit"]   += profit
        totals["payments"] += paid
        totals["orders"]   += orders_count
        totals["debt"]     += manager_debt
        totals["events"]   += events_count

    # Убираем менеджеров без активности
    # managers_data = [m for m in managers_data if m["orders"] > 0 or m["events"] > 0]

    # Округляем итоги
    for key in totals:
        totals[key] = round(totals[key], 2)


    print(managers_data, totals)
    return managers_data, totals


def _short_name(full_name: str) -> str:
    """Иванов Иван Петрович → Иванов И.П."""
    parts = full_name.strip().split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    elif len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    return full_name