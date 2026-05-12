from __future__ import annotations

import argparse
import base64
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ZERO_GUID = "00000000-0000-0000-0000-000000000000"
PLACEHOLDERS = {"", "change-me", "change_me", "changeme", "replace-me", "replace_me"}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if value and value[0] in {"'", '"'} and value[-1:] == value[0]:
            value = value[1:-1]
        values[name.strip()] = value
    return values


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in PLACEHOLDERS or normalized.startswith("change-me")


def is_false(value: str) -> bool:
    return value.strip().lower() in {"false", "0", "no", "off"}


def is_true(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "on"}


def require_present(env: dict[str, str], name: str, errors: list[str]) -> str:
    value = env.get(name, "").strip()
    if is_placeholder(value):
        errors.append(f"{name} must be set and must not be a placeholder")
    return value


def require_url(env: dict[str, str], name: str, errors: list[str]) -> None:
    value = env.get(name, "").strip()
    if not value:
        errors.append(f"{name} must be set")
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append(f"{name} must be an absolute http(s) URL")


def check_fernet_key(value: str, errors: list[str]) -> None:
    try:
        Fernet(value.encode())
    except Exception:
        errors.append("ENCRYPTION_KEY must be a valid Fernet key")
        return

    try:
        decoded = base64.urlsafe_b64decode(value.encode())
    except Exception:
        errors.append("ENCRYPTION_KEY must be url-safe base64")
        return
    if len(decoded) != 32:
        errors.append("ENCRYPTION_KEY must decode to 32 bytes")


def check_allowed_origins(value: str, errors: list[str]) -> None:
    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    if not origins:
        errors.append("ALLOWED_ORIGINS must contain at least one origin")
        return
    if "*" in origins:
        errors.append("ALLOWED_ORIGINS must not contain *")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ServerPal .env before production-like runs.")
    parser.add_argument("--prod", action="store_true", help="Enable stricter production checks.")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    if not ENV_PATH.exists():
        print(f"ERROR: root .env not found: {ENV_PATH}")
        return 1

    env = parse_env(ENV_PATH)

    secret_key = require_present(env, "SECRET_KEY", errors)
    if secret_key and "change-before-prod" in secret_key.lower():
        warnings.append("SECRET_KEY still looks like a local development value")

    encryption_key = require_present(env, "ENCRYPTION_KEY", errors)
    if encryption_key:
        check_fernet_key(encryption_key, errors)

    require_present(env, "SERVICE_API_KEY", errors)

    if not is_false(env.get("REGISTRATION_ENABLED", "")):
        errors.append("REGISTRATION_ENABLED must be false")

    if args.prod and not is_true(env.get("COOKIE_SECURE", "")):
        errors.append("COOKIE_SECURE must be true in --prod mode")

    cookie_samesite = env.get("COOKIE_SAMESITE", "").strip().lower()
    if cookie_samesite and cookie_samesite not in {"lax", "strict", "none"}:
        errors.append("COOKIE_SAMESITE must be lax, strict, or none")

    check_allowed_origins(env.get("ALLOWED_ORIGINS", ""), errors)

    for name in (
        "AI_SERVICE_URL",
        "DIGEST_SERVICE_URL",
        "OPENAI_BASE_URL",
        "LMSTUDIO_BASE_URL",
        "DIGEST_OPENAI_BASE_URL",
    ):
        require_url(env, name, errors)

    for name in ("OPENAI_MODEL", "LMSTUDIO_MODEL", "DIGEST_OPENAI_MODEL"):
        require_present(env, name, errors)

    digest_key = env.get("DIGEST_OPENAI_API_KEY", "").strip()
    openai_key = env.get("OPENAI_API_KEY", "").strip()
    external_digest_key = digest_key or openai_key
    if args.prod and (not external_digest_key or external_digest_key == "lm-studio"):
        errors.append("DIGEST_OPENAI_API_KEY must be set for Digest external provider in --prod mode")
    elif not digest_key and openai_key and openai_key != "lm-studio":
        warnings.append("Digest external provider is using OPENAI_API_KEY fallback; prefer DIGEST_OPENAI_API_KEY")

    for name in ("PRICE_TYPE_RETAIL", "PRICE_TYPE_WHOLESALE"):
        value = env.get(name, "").strip()
        if value == ZERO_GUID:
            warnings.append(f"{name} is zero GUID; per-client settings should contain real price GUIDs")

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("prod check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())