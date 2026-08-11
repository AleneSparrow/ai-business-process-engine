"""Correlation, request-size enforcement, and safe request logging."""

import logging
import re
from time import monotonic
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from .observability import log_event


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, max_request_body_bytes: int) -> None:
        super().__init__(app)
        self.max_request_body_bytes = max_request_body_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else str(uuid4())
        )
        request.state.request_id = request_id
        started = monotonic()

        content_length = request.headers.get("Content-Length")
        if content_length is not None:
            try:
                too_large = int(content_length) > self.max_request_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "request_too_large",
                            "message": "Request body exceeds the allowed size",
                            "request_id": request_id,
                        }
                    },
                )
                response.headers["X-Request-ID"] = request_id
                self._log_completion(request, response.status_code, started)
                return response

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        self._log_completion(request, response.status_code, started)
        return response

    @staticmethod
    def _log_completion(request: Request, status_code: int, started: float) -> None:
        route = request.scope.get("route")
        endpoint = getattr(route, "path", request.url.path)
        log_event(
            logging.INFO,
            "http_request_completed",
            request_id=getattr(request.state, "request_id", None),
            business_id=getattr(request.state, "business_id", None),
            endpoint=endpoint,
            method=request.method,
            status_code=status_code,
            resulting_state=getattr(request.state, "resulting_state", None),
            duration_ms=round((monotonic() - started) * 1000, 2),
        )
