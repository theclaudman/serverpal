import hashlib
from app.models.schemas import BaseCredentials


def make_base_id(credentials: BaseCredentials) -> str:
    """Генерирует уникальный идентификатор базы из ip + login."""
    raw = f"{credentials.ip}_{credentials.login}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]
