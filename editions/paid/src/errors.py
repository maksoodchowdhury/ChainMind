from typing import Any


def error_payload(
    *,
    request_id: str | None,
    code: str,
    message: str,
    details: Any = None,
) -> dict:
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload
