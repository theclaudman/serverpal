from collections import defaultdict


def build_sales_report(invoices, nomenclature_index, contragents_index, employees_index, costs, orders_index=None):
    """Строит отчёт о продажах с себестоимостью по заказам"""

    if orders_index is None:
        orders_index = {}

    # Индекс себестоимости по заказу: {order_key: сумма_расходов}
    cost_by_order = defaultdict(float)
    for c in costs:
        key = c.get("ЗаказПокупателя_Key", "")
        if key and key != "00000000-0000-0000-0000-000000000000":
            cost_by_order[key] += c.get("СуммаРасходовTurnover", 0)

    # Считаем суммарную выручку по каждому заказу для пропорции
    order_revenue = defaultdict(float)
    for invoice in invoices:
        for line in invoice.get("Запасы", []):
            order_key = line.get("Заказ", "")
            if order_key and order_key != "00000000-0000-0000-0000-000000000000":
                order_revenue[order_key] += line.get("Сумма", 0) or 0

    sales_data = []
    daily_totals = defaultdict(float)

    for invoice in invoices:
        date        = invoice.get("Date", "")
        doc_key     = invoice.get("Ref_Key", "")
        contragent  = contragents_index.get(invoice.get("Контрагент_Key", ""), "—")
        responsible = employees_index.get(invoice.get("Ответственный_Key", ""), "—")
        lines       = invoice.get("Запасы", [])

        day = date[:10] + "T00:00:00.000" if date else ""

        for line in lines:
            nom_key   = line.get("Номенклатура_Key", "")
            nom       = nomenclature_index.get(nom_key, nom_key)
            сумма     = line.get("Сумма", 0) or 0
            кол       = line.get("Количество", 0) or 0

            # Заказ — правильное поле из табличной части
            order_key = line.get("Заказ", "")
            if order_key == "00000000-0000-0000-0000-000000000000":
                order_key = ""

            # Себестоимость пропорционально доле строки в выручке заказа
            себестоимость = 0.0
            if order_key and order_revenue[order_key] > 0:
                доля = сумма / order_revenue[order_key]
                себестоимость = round(cost_by_order[order_key] * доля, 2)

            row = {
                "Номенклатура_Key":     nom_key,
                "Характеристика_Key":   line.get("Характеристика_Key", ""),
                "Контрагент_Key":       invoice.get("Контрагент_Key", ""),
                "ЗаказПокупателя_Key":  order_key,
                "Ответственный_Key":    invoice.get("Ответственный_Key", ""),
                "Документ":             doc_key,
                "Сумма":                round(сумма, 2),
                "Количество":           кол,
                "Себестоимость":        себестоимость,
                "Дата":                 date,
                "Номенклатура":         nom,
                "Контрагент":           contragent,
                "ЗаказПокупателя":      orders_index.get(order_key, order_key),
                "Ответственный":        responsible,
            }
            sales_data.append(row)

            if day:
                daily_totals[day] += сумма

    daily_sales_data = [
        {"date": day, "revenue": round(rev, 2)}
        for day, rev in sorted(daily_totals.items())
    ]

    return sales_data, daily_sales_data