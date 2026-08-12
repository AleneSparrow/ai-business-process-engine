"""Runtime-configured CORS middleware for public widget requests."""

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ConfiguredCORSMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if origin is None:
            await self.app(scope, receive, send)
            return
        application = scope.get("app")
        container = getattr(getattr(application, "state", None), "container", None)
        allowed_origins = getattr(getattr(container, "settings", None), "cors_allowed_origins", ())
        allowed = origin in allowed_origins or "*" in allowed_origins
        is_preflight = (
            scope["method"] == "OPTIONS"
            and headers.get("access-control-request-method") is not None
        )
        if is_preflight:
            response_headers = {
                "Vary": "Origin",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-Request-ID, Authorization",
                "Access-Control-Max-Age": "600",
            }
            if allowed:
                response_headers["Access-Control-Allow-Origin"] = (
                    "*" if "*" in allowed_origins else origin
                )
            response = PlainTextResponse(
                "OK" if allowed else "CORS origin denied",
                status_code=200 if allowed else 400,
                headers=response_headers,
            )
            await response(scope, receive, send)
            return

        async def send_with_cors(message: Message) -> None:
            if allowed and message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers.append("Vary", "Origin")
                response_headers["Access-Control-Allow-Origin"] = (
                    "*" if "*" in allowed_origins else origin
                )
            await send(message)

        await self.app(scope, receive, send_with_cors)
