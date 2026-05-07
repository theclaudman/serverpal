FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY server_digest_ai-main/server_digest_ai-main/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY server_digest_ai-main/server_digest_ai-main/ /app/

EXPOSE 8002

CMD ["python", "server.py"]
