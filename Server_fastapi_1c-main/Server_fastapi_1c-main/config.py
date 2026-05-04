SECRET_KEY       = "change-me-in-production-use-random-string"

# IP внешнего AI-сервиса (1C AI Bridge). Заполнить вручную, например: "http://192.168.1.50:8000"
AI_SERVICE_URL   = "http://localhost:8001"

# Ref_Key видов цен из Catalog_ВидыЦен
PRICE_TYPE_RETAIL     = "55a36684-62bc-11f0-89d6-d8625b865b03"  # Розничная
PRICE_TYPE_WHOLESALE  = "05baa3c2-5ea9-11f0-aa16-10ffe0a68931"  # Оптовая

# Названия колонок цен для HTML
PRICE_COLUMNS = {
    PRICE_TYPE_RETAIL:    "Розничная",
    PRICE_TYPE_WHOLESALE: "Оптовая",
}
DIGEST_SERVICE_URL = "http://localhost:8002"