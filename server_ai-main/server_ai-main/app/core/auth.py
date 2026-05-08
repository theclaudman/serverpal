from __future__ import annotations

from secrets import compare_digest

from fastapi import Header, HTTPException, WebSocket

from app.core.config import settings


def verify_service_key(x_service_api_key: str = Header(default="")) -> None:
    if not compare_digest(x_service_api_key, settings.service_api_key):
        raise HTTPException(status_code=403, detail="Invalid service API key")


async def verify_ws_service_key(websocket: WebSocket) -> bool:
    if compare_digest(websocket.headers.get("x-service-api-key", ""), settings.service_api_key):
        return True
    await websocket.close(code=4403, reason="Invalid service API key")
    return False
