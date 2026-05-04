# Service FastAPI 1C — Техническое описание

Этот документ описывает архитектуру, механизмы аутентификации, маршрутизации и хранения данных сервиса `Service_FastAPI_1c`. Документ предназначен для создания новых сервисов, которые будут работать поверх текущего или рядом с ним.

---

## 1. Обзор архитектуры

Сервис — это **FastAPI-приложение**, которое выступает прослойкой между браузером пользователя и сервером **1С:УНФ** (Управление Небольшой Фирмой). Данные не хранятся локально: всё получается напрямую из **1С OData API** по запросу.

### Структура проекта

```
Service_FastAPI_1c/
├── main.py                   # Роуты FastAPI, аутентификация, сессии
├── config.py                 # Константы конфигурации
├── database.py               # SQLite: инициализация, CRUD пользователей
├── users.db                  # SQLite-база (создаётся автоматически при запуске)
├── services/
│   ├── onec_client.py        # HTTP-клиент к 1С OData API
│   ├── data_builder.py       # Сборка прайс-листа
│   ├── dashboard_builder.py  # Дашборд КПЭ менеджеров
│   └── sales_builder.py      # Отчёт по продажам
└── templates/
    ├── login.html
    ├── register.html
    ├── index.html
    ├── price_list.html
    ├── managers_dashboard.html
    └── sales_report.html
```

### Технологический стек

| Компонент        | Решение                           |
|------------------|-----------------------------------|
| Веб-фреймворк    | FastAPI                           |
| ASGI-сервер      | Uvicorn                           |
| HTTP-клиент      | `urllib` (стандартная библиотека) |
| Сессии           | HMAC-подписанные cookie           |
| БД пользователей | SQLite (`users.db`, `sqlite3`)    |
| Кэш              | Отсутствует                       |
| Шаблоны          | HTML с вставкой JSON через f-строки |

---

## 2. Запросы к 1С

### 2.1 Протокол и формат

Сервис обращается к **1С OData API** по HTTP. Путь к API строится **динамически** из профиля пользователя:

```
http://{server_ip}/{onec_publication}/odata/standard.odata
```

Где `onec_publication` — имя публикации базы 1С на веб-сервере (задаётся пользователем при регистрации, например `unf_dashboard`).

Полный адрес запроса:

```
http://{server_ip}/{onec_publication}/odata/standard.odata/{ИмяСущности}?$format=json&...
```

Все запросы — только **GET**. Никакие данные в 1С не записываются.

### 2.2 Аутентификация в 1С

Каждый запрос использует **HTTP Basic Authentication**:

```
Authorization: Basic <base64(username:password)>
Accept: application/json
```

Логин и пароль берутся из контекстных переменных текущего запроса (см. раздел 3).

### 2.3 Реализация HTTP-клиента (`services/onec_client.py`)

```python
# Псевдокод функции safe_get()
def safe_get(url: str) -> dict | None:
    credentials = base64.b64encode(f"{_user()}:{_password()}".encode()).decode()
    req = urllib.request.Request(encoded_url)
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Accept", "application/json")
    # таймаут 30 секунд
    # возвращает None при ошибке соединения или HTTP-ошибке

# Сигнатура set_credentials
def set_credentials(server_ip: str, user: str, password: str, onec_publication: str) -> None:
    _ctx_base_url.set(f"http://{server_ip}/{onec_publication}/odata/standard.odata")
    _ctx_user.set(user)
    _ctx_password.set(password)
```

Кириллица в URL экранируется через `urllib.parse.quote(...)`.

### 2.4 Сущности 1С, к которым обращается сервис

| Сущность OData                                     | Назначение                                      |
|----------------------------------------------------|--------------------------------------------------|
| `Catalog_Номенклатура`                             | Каталог товаров                                  |
| `InformationRegister_ЦеныНоменклатуры`            | Цены (розничные и оптовые)                       |
| `AccumulationRegister_ЗапасыНаСкладах`            | Остатки на складе                                |
| `AccumulationRegister_РезервыТоваровОрганизаций`  | Зарезервированные товары                         |
| `Document_ЗаказПокупателя`                         | Заказы покупателей                               |
| `Document_РасходнаяНакладная`                      | Расходные накладные (продажи)                    |
| `Catalog_Сотрудники`                               | Сотрудники (менеджеры)                           |
| `Catalog_Контрагенты`                              | Контрагенты (клиенты)                            |
| `AccumulationRegister_ДоходыИРасходы`             | Обороты доходов и расходов                       |
| `AccumulationRegister_РасчетыСПокупателями`       | Расчёты с покупателями (долги, оплаты)           |
| `Document_Событие`                                 | CRM-события (звонки, письма)                     |

### 2.5 OData-параметры запросов

| Параметр   | Назначение                          | Пример                         |
|------------|-------------------------------------|--------------------------------|
| `$format`  | Формат ответа                       | `$format=json`                 |
| `$select`  | Список возвращаемых полей           | `$select=Ref_Key,Description`  |
| `$filter`  | Условия фильтрации                  | `$filter=Date ge datetime'...'`|
| `$orderby` | Сортировка                          | `$orderby=Date desc`           |

Специальные суффиксы OData:
- `/Turnovers(...)` — агрегированные обороты за период
- `/SliceLast` — последний срез регистра сведений
- `/Balance` — остаток накопительного регистра

---

## 3. Идентификация запросов

### 3.1 Принцип работы

Система использует два уровня:

1. **SQLite (`users.db`)** — постоянное хранилище профилей. При регистрации сюда сохраняются `username`, `password`, `server_ip`, `onec_publication`. При входе отсюда берутся `server_ip` и `onec_publication` по логину.
2. **Подписанные cookie-сессии** — после успешного входа выдаётся cookie, содержащая `server_ip`, `onec_publication`, `user`, `password`. При каждом запросе к защищённым страницам данные читаются из cookie — SQLite больше не опрашивается.

### 3.2 Схема базы данных (`database.py`)

```sql
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    UNIQUE NOT NULL,
    password         TEXT    NOT NULL,
    server_ip        TEXT    NOT NULL,
    onec_publication TEXT    NOT NULL DEFAULT 'unf_dashboard'
)
```

> При запуске `init_db()` автоматически выполняет миграцию для существующих баз — добавляет колонку `onec_publication` через `ALTER TABLE`, если её ещё нет.

Функции модуля `database.py`:

| Функция | Назначение |
|---|---|
| `init_db()` | Создаёт таблицу при первом запуске (идемпотентна); мигрирует существующую БД |
| `get_user(username)` | Возвращает `dict` с профилем (включая `onec_publication`) или `None` |
| `username_exists(username)` | Проверяет уникальность логина |
| `create_user(username, password, server_ip, onec_publication)` | Сохраняет нового пользователя |

`init_db()` вызывается один раз при старте приложения.

### 3.3 Структура сессии (cookie)

```json
{
  "server_ip": "192.168.1.10",
  "onec_publication": "unf_dashboard",
  "user": "admin",
  "password": "secret"
}
```

| Поле               | Тип    | Назначение                                       |
|--------------------|--------|--------------------------------------------------|
| `server_ip`        | string | IP или hostname сервера 1С                       |
| `onec_publication` | string | Имя публикации базы 1С на веб-сервере            |
| `user`             | string | Имя пользователя в 1С                            |
| `password`         | string | Пароль в 1С (хранится открытым текстом в cookie) |

### 3.4 Формат cookie

Cookie называется `session`. Формат значения:

```
{base64url(json_payload)}.{hmac_sha256_signature}
```

**Кодирование (при входе):**
```python
payload = base64.urlsafe_b64encode(json.dumps(session_data).encode()).decode()
signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
cookie_value = f"{payload}.{signature}"
```

**Декодирование (при каждом запросе):**
```python
payload, sig = cookie.rsplit(".", 1)
if not hmac.compare_digest(expected_sig, sig):
    return None  # cookie подделана
session = json.loads(base64.urlsafe_b64decode(payload).decode())
```

Параметры cookie:
- `httponly=True` — недоступна из JavaScript
- `samesite="lax"` — защита от CSRF
- `max_age=43200` — время жизни 12 часов

### 3.5 Процесс регистрации

```
POST /register
  form: server_ip, onec_publication, username, password
        ↓
  Проверка уникальности username в SQLite
        ↓
  Тестовый вызов fetch_employees() к 1С
        ↓
  Сохранение в users.db (включая onec_publication)
        ↓
  Создание cookie-сессии → Redirect /
```

### 3.6 Процесс входа

```
POST /login
  form: username, password
        ↓
  get_user(username) → поиск в SQLite
  Если не найден → ошибка "Пользователь не найден"
        ↓
  Сравнение password с users.password
  Если не совпадает → ошибка "Неверный пароль"
        ↓
  server_ip и onec_publication берутся из users.*
        ↓
  Тестовый вызов fetch_employees() к 1С
        ↓
  Создание cookie-сессии → Redirect /
```

После входа SQLite не используется до следующей сессии.

### 3.7 Цикл жизни аутентифицированного запроса

```
Браузер: GET /price-list (с cookie "session")
    ↓
main.py: require_session(request)
    ├─ get_session() → decode_session(cookie)
    ├─ HMAC-проверка подписи
    ├─ Извлечение server_ip, user, password
    └─ set_credentials() → запись в ContextVar

services/onec_client.py: safe_get(url)
    ├─ _base_url() → читает ContextVar → строит URL
    ├─ _user()     → читает ContextVar
    ├─ _password() → читает ContextVar
    └─ HTTP GET к 1С с Basic Auth
```

SQLite на этом этапе **не задействована**.

### 3.8 Контекстные переменные (изоляция запросов)

Учётные данные передаются между слоями через `contextvars.ContextVar`. Это гарантирует изоляцию между параллельными async-запросами:

```python
_ctx_base_url: ContextVar[str] = ContextVar("onec_base_url", default="")
_ctx_user:     ContextVar[str] = ContextVar("onec_user",     default="")
_ctx_password: ContextVar[str] = ContextVar("onec_password", default="")
```

Значения устанавливаются в начале каждого запроса и не пересекаются между запросами.

`_ctx_base_url` формируется в `set_credentials` как `http://{server_ip}/{onec_publication}/odata/standard.odata` — путь к API больше не является глобальной константой в `config.py`.

---

## 4. Хранение данных

### 4.1 Схема хранения

| Данные                        | Где хранится              | Область видимости | Время жизни             |
|-------------------------------|---------------------------|-------------------|-------------------------|
| Профили пользователей         | SQLite `users.db`         | Постоянно         | До удаления записи      |
| Активная сессия               | Cookie браузера           | Браузер-сессия    | 12 часов                |
| Учётные данные (runtime)      | Python ContextVar         | Один HTTP-запрос  | Время запроса           |
| Данные из 1С                  | Нигде (только RAM)        | Один HTTP-запрос  | Время запроса           |
| Имя публикации OData          | SQLite `users.db` + cookie | Пользователь     | До смены профиля        |
| Ключ подписи сессий           | `config.py` (код)         | Приложение        | Пока работает процесс   |
| Конфигурация                  | `config.py` (код)         | Приложение        | Статично                |

### 4.2 Конфигурация (`config.py`)

```python
# Ключ подписи HMAC-сессий
SECRET_KEY = "change-me-in-production-use-random-string"

# UUID типов цен в справочнике «Виды цен»
PRICE_TYPE_RETAIL    = "7481362d-b5b8-11e4-8355-74d02b7dfd8c"
PRICE_TYPE_WHOLESALE = "72e9e83e-fb07-11e4-8005-74d02b7dfd8c"

# Отображаемые названия колонок цен
PRICE_COLUMNS = {
    PRICE_TYPE_RETAIL:    "Розничная",
    PRICE_TYPE_WHOLESALE: "Оптовая",
}
```

### 4.3 Идентификаторы (GUID) в 1С

Все сущности в 1С имеют поля `Ref_Key` — UUID (GUID). Именно они используются для:
- Связи между сущностями (например, `Номенклатура_Key` в ценах указывает на товар)
- Фильтрации OData-запросов (`$filter=ВидЦен_Key eq guid'...'`)

Статически заданные GUID в коде — UUID типов цен в справочнике `Catalog_ВидыЦен` (см. выше).

---

## 5. API эндпоинты

Все эндпоинты возвращают **HTML** с вложенным JSON для клиентской отрисовки. Чистого JSON API нет.

### Открытые эндпоинты (без авторизации)

| Метод  | Путь         | Описание                         |
|--------|--------------|----------------------------------|
| GET    | `/login`     | Страница входа                   |
| POST   | `/login`     | Обработка формы входа            |
| GET    | `/register`  | Страница регистрации             |
| POST   | `/register`  | Обработка формы регистрации      |
| GET    | `/logout`    | Удаление сессии и редирект       |

**POST /login** — принимает форму:
```
Content-Type: application/x-www-form-urlencoded
username=admin&password=secret
```

**POST /register** — принимает форму:
```
Content-Type: application/x-www-form-urlencoded
server_ip=192.168.1.10&onec_publication=unf_dashboard&username=admin&password=secret
```

### Защищённые эндпоинты (требуют cookie-сессию)

| Метод | Путь                  | Query-параметры              | Описание                     |
|-------|-----------------------|------------------------------|------------------------------|
| GET   | `/`                   | —                            | Главная страница              |
| GET   | `/price-list`         | —                            | Прайс-лист товаров            |
| GET   | `/dashboard/managers` | `start_date`, `end_date`     | Дашборд КПЭ менеджеров       |
| GET   | `/report/sales`       | `start_date`, `end_date`     | Отчёт по продажам            |

Формат дат: `YYYY-MM-DD`.

**Значения по умолчанию для дат:**

| Эндпоинт              | `start_date` по умолч.        | `end_date` по умолч. |
|-----------------------|-------------------------------|----------------------|
| `/dashboard/managers` | Сегодня − 30 дней             | Сегодня              |
| `/report/sales`       | Первый день текущего месяца   | Сегодня              |

### Обработка ошибок

| Ситуация                        | Ответ                                    |
|---------------------------------|------------------------------------------|
| Нет / невалидная сессия         | `302 Redirect → /login`                 |
| Пользователь не найден в БД     | `401 HTML` с сообщением об ошибке        |
| Неверный пароль                 | `401 HTML` с сообщением об ошибке        |
| Логин уже занят (регистрация)   | `400 HTML` с сообщением об ошибке        |
| 1С недоступна                   | `502 HTML / Bad Gateway`                 |
| Ошибка обработки данных         | `500 Internal Server Error`              |

---

## 6. Модели данных

Сервис не использует Pydantic-модели. Данные передаются как обычные Python-словари и списки, полученные из JSON-ответов 1С.

### Данные сессии

```python
{
    "server_ip":        str,   # IP-адрес сервера 1С
    "onec_publication": str,   # Имя публикации базы 1С на веб-сервере
    "user":             str,   # Имя пользователя
    "password":         str    # Пароль
}
```

### Ключевые объекты из 1С

**Товар (`Catalog_Номенклатура`)**
```python
{
    "Ref_Key":                    str,   # UUID
    "Description":                str,   # Наименование
    "Артикул":                    str,
    "Parent_Key":                 str,   # UUID родительской группы
    "IsFolder":                   bool,
    "ИсключитьИзПрайсЛистов":    bool,
    "Недействителен":             bool
}
```

**Цена (`InformationRegister_ЦеныНоменклатуры/SliceLast`)**
```python
{
    "Номенклатура_Key": str,    # UUID товара
    "ВидЦен_Key":       str,    # UUID типа цены
    "Цена":             float
}
```

**Остаток (`AccumulationRegister_ЗапасыНаСкладах/Balance`)**
```python
{
    "Номенклатура_Key":   str,
    "КоличествоBalance":  float
}
```

**Заказ покупателя (`Document_ЗаказПокупателя`)**
```python
{
    "Ref_Key":              str,
    "Date":                 str,     # ISO datetime
    "Ответственный_Key":    str,     # UUID менеджера
    "Контрагент_Key":       str,     # UUID клиента
    "СуммаДокумента":       float,
    "Posted":               bool,
    "ВариантЗавершения":    str      # Статус выполнения
}
```

**Расходная накладная (`Document_РасходнаяНакладная`)**
```python
{
    "Ref_Key":              str,
    "Date":                 str,
    "Контрагент_Key":       str,
    "Ответственный_Key":    str,
    "Posted":               bool,
    "Запасы": [                      # Табличная часть
        {
            "Номенклатура_Key":      str,
            "Характеристика_Key":    str,
            "Заказ":                 str,   # UUID заказа
            "Количество":            float,
            "Сумма":                 float
        }
    ]
}
```

**Сотрудник (`Catalog_Сотрудники`)**
```python
{
    "Ref_Key":       str,
    "Description":   str,
    "ВАрхиве":       bool,
    "Недействителен": bool
}
```

### Агрегированные модели (результат сборки)

**Позиция прайс-листа**
```python
{
    "Наименование":     str,
    "Артикул":          str,
    "Группа":           str,
    "Group_Key":        str,
    "Остаток":          float,
    "Свободно":         float,   # Остаток − резерв
    "Розничная":        float,
    "Оптовая":          float
}
```

**Показатели менеджера (дашборд)**
```python
{
    "id":              str,
    "name":            str,     # Краткое ФИО
    "full_name":       str,
    "revenue":         float,
    "profit":          float,
    "payments":        float,
    "orders":          int,
    "orders_sum":      float,
    "debt":            float,
    "debtors_count":   int,
    "events":          int,
    "events_calls":    int,
    "events_emails":   int,
    "orders_details":  list[dict],
    "debt_details":    list[dict],
    "events_details":  list[dict]
}
```

**Строка отчёта по продажам**
```python
{
    "Номенклатура_Key":     str,
    "Контрагент_Key":       str,
    "ЗаказПокупателя_Key":  str,
    "Ответственный_Key":    str,
    "Документ":             str,   # UUID накладной
    "Сумма":                float,
    "Количество":           float,
    "Себестоимость":        float,
    "Дата":                 str,
    "Номенклатура":         str,   # Название товара
    "Контрагент":           str,   # Название клиента
    "ЗаказПокупателя":      str,   # Номер заказа
    "Ответственный":        str    # Имя менеджера
}
```

---

## 7. Диаграмма потока данных

### Регистрация

```
Браузер: POST /register (server_ip, onec_publication, username, password)
    ↓
database.py: username_exists() → SQLite
    ↓
onec_client: fetch_employees() → тест подключения к 1С
    ↓
database.py: create_user() → SQLite INSERT (включая onec_publication)
    ↓
Выдача cookie-сессии → Redirect /
```

### Вход

```
Браузер: POST /login (username, password)
    ↓
database.py: get_user() → SQLite SELECT → получаем server_ip и onec_publication
    ↓
Сравнение пароля
    ↓
onec_client: fetch_employees() → тест подключения к 1С
    ↓
Выдача cookie-сессии (включая onec_publication) → Redirect /
```

### Защищённый запрос

```
Браузер: GET /price-list + cookie "session"
    ↓
main.py: require_session()
    ├─ decode_session(cookie) + HMAC-проверка
    └─ set_credentials(server_ip, user, password) → ContextVar
    ↓
Сервисы: fetch_*() → читают ContextVar → HTTP Basic Auth к 1С
    ↓
Сборка данных → HTML-ответ
```

SQLite при защищённых запросах **не задействована**.

---

## 8. Важные ограничения и замечания

### Безопасность

| Проблема                              | Описание                                                         |
|---------------------------------------|------------------------------------------------------------------|
| Пароль в открытом виде в cookie       | Пароль 1С хранится незашифрованным внутри подписанной cookie    |
| Нет HTTPS                             | Конфиг использует `http://` — пароль передаётся открытым текстом |
| Хардкод `SECRET_KEY`                  | Должен быть вынесен в переменную окружения и изменён            |
| Нет rate limiting                     | Эндпоинт `/login` уязвим к брутфорсу                           |
| Нет логирования                       | Нет аудита доступа и ошибок                                      |

### Производительность

- Нет кэширования: при каждом запросе страницы данные заново запрашиваются из 1С
- Для прайс-листа выполняется несколько параллельных OData-запросов через `asyncio`
- Таймаут каждого запроса к 1С — 30 секунд

### Для создания нового сервиса поверх текущего

Новый сервис может:

1. **Использовать ту же cookie-сессию** — если работает в том же домене, cookie `session` будет автоматически передана. Нужно только знать `SECRET_KEY` для проверки или создания своих сессий.

2. **Добавить JSON-эндпоинты** — текущий сервис возвращает только HTML. Можно добавить отдельные эндпоинты, возвращающие `application/json`, при этом используя те же сервисы `onec_client`, `data_builder` и пр.

3. **Переиспользовать функции из `services/`** — все функции `fetch_*()` в `onec_client.py` и `build_*()` в билдерах не зависят от HTTP-слоя FastAPI. Их можно вызывать из любого контекста, предварительно установив ContextVar через `set_credentials(server_ip, user, password)`.

4. **Расширить `config.py`** — добавить новые UUID типов цен, новые OData-пути и т.д.

5. **Расширить профиль пользователя** — в таблицу `users` можно добавить новые поля (роль, email, дата создания и т.д.) без изменения логики сессий.

---

## 9. Минимальный пример: вызов 1С из внешнего кода

```python
# Подключаем клиент и устанавливаем учётные данные
from services.onec_client import set_credentials, fetch_nomenclature

set_credentials(
    server_ip="192.168.1.10",
    user="admin",
    password="secret",
    onec_publication="unf_dashboard"
)

# Получаем список товаров
products = fetch_nomenclature()  # возвращает list[dict]
for p in products:
    print(p["Ref_Key"], p["Description"])
```

Функция `set_credentials` записывает данные в `ContextVar`. После этого все `fetch_*` функции автоматически используют эти данные для запросов к 1С.

---

*Документ сгенерирован на основе анализа исходного кода. Актуален для текущей версии проекта.*
