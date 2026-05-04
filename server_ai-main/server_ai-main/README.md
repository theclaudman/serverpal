# 1C AI Bridge

Сервис-посредник между базами 1С УНФ 3.0 и GigaChat AI.

## Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env из шаблона
cp .env.example .env
# Заполнить GIGACHAT_CREDENTIALS и SERVICE_API_KEY

# 3. Запустить сервис
uvicorn app.main:app --host 0.0.0.0 --port 8888 --reload
```

## Документация API

После запуска: http://localhost:8000/docs

## Структура хранилища

```
data/connected_bases/
  {base_id}/
    daily_reports/     — ежедневные отчёты
    weekly_reports/    — еженедельные отчёты
    monthly_reports/   — ежемесячные отчёты (по таймеру, 1-е число)
    quarterly_reports/ — ежеквартальные отчёты (по таймеру, 1 января/апреля/июля/октября)
```

## Эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| POST | `/report/daily` | Ежедневный отчёт из 1С |
| POST | `/report/weekly` | Еженедельный отчёт из 1С |
| POST | `/chat/` | Произвольный запрос к AI |
| POST | `/bases/register` | Регистрация базы 1С |
| GET | `/bases/` | Список баз |
| POST | `/query/` | Выполнить запрос на языке 1С к базе |
| GET | `/health` | Статус сервиса |
