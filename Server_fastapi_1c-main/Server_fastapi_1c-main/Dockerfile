FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASHBOARD_DB_PATH=/data/users.db

WORKDIR /app

COPY Server_fastapi_1c-main/Server_fastapi_1c-main/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY Server_fastapi_1c-main/Server_fastapi_1c-main/ /app/

EXPOSE 9001

CMD ["python", "main.py"]
