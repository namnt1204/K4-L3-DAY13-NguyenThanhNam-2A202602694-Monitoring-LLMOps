import re
import secrets
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_PATTERN = re.compile(r"^req-[0-9a-fA-F]{8}$")


def _get_or_create_request_id(raw_id: str | None) -> str:
    if raw_id and REQUEST_ID_PATTERN.fullmatch(raw_id.strip()):
        return raw_id.strip().lower()
    return f"req-{secrets.token_hex(4)}"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_contextvars()

        correlation_id = _get_or_create_request_id(request.headers.get("x-request-id"))
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            pass

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.2f}"

        return response

