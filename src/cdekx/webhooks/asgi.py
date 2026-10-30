"""Ready-made ASGI application for receiving CDEK webhooks.

Requires an extra dependency::

    pip install "cdekx[webhooks]"      # installs starlette

Mounting into FastAPI::

    from cdekx.webhooks.asgi import WebhookApp

    async def handle(event: WebhookEvent) -> None:
        logger.info("order %s -> %s", event.attributes.cdek_number, event.attributes.code)

    webhook_app = WebhookApp(on_event=handle, path_secret=settings.CDEK_WEBHOOK_SECRET)
    app.mount("/webhooks/cdek", webhook_app.asgi)

Running under a plain ASGI server (uvicorn)::

    uvicorn mymodule:webhook_app.asgi

The default behaviour is to **always answer 200**: CDEK deletes a subscription
that keeps failing to answer successfully, and a business error is better logged
than allowed to cost you the subscription. Turn this off with
``raise_on_handler_error=True``.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from .events import UnknownEventError, WebhookEvent, parse_event
from .security import CDEK_IP_RANGES, allowed_types, is_cdek_ip

# starlette — опциональная зависимость (extra "webhooks"), поэтому Request
# импортируется только под TYPE_CHECKING.
if TYPE_CHECKING:
    from starlette.requests import Request

__all__ = ["EventHandler", "WebhookApp"]

logger = logging.getLogger("cdekx.webhooks")

#: Event handler: may be either synchronous or asynchronous.
EventHandler = Callable[[WebhookEvent], Awaitable[None] | None]


class WebhookApp:
    """A small application for receiving webhooks (Starlette under the hood)."""

    def __init__(
        self,
        on_event: EventHandler,
        *,
        path_secret: str | None = None,
        ip_ranges: tuple[str, ...] | None = None,
        accept_types: list[str] | None = None,
        raise_on_handler_error: bool = False,
        health_path: str = "/healthz",
    ) -> None:
        """Build the webhook receiver application.

        Args:
            on_event: event handler (async or sync).
            path_secret: secret part of the path; ``None`` disables the check.
            ip_ranges: CDEK IP ranges; ``()``/``None`` disables the check.
            accept_types: accept only the listed event types.
            raise_on_handler_error: answer 500 when the handler fails
                (CDEK will retry the delivery but may disable the subscription).
            health_path: health-check path for the load balancer.

        """
        self.on_event = on_event
        self.path_secret = path_secret
        self.ip_ranges = CDEK_IP_RANGES if ip_ranges is None else ip_ranges
        self.accept_types = allowed_types(accept_types)
        self.raise_on_handler_error = raise_on_handler_error
        self.health_path = health_path
        self._asgi: Any = None

    @property
    def asgi(self) -> Any:
        """The ASGI app (built lazily so Starlette is not required at import time)."""
        if self._asgi is None:
            self._asgi = self._build()
        return self._asgi

    async def handle_raw(
        self,
        body: bytes,
        *,
        path: str = "",
        client_ip: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Handle a raw request body.

        Returns:
            A ``(status_code, payload)`` pair — convenient for tests and for
            integrating with frameworks other than Starlette.

        """
        if self.path_secret and self.path_secret not in path:
            logger.warning("webhook request with wrong path secret from %s", client_ip)
            return 404, {"detail": "not found"}

        if self.ip_ranges and not is_cdek_ip(client_ip, self.ip_ranges):
            logger.warning("webhook request from untrusted IP %s", client_ip)
            return 403, {"detail": "forbidden"}

        try:
            event = parse_event(body)
        except UnknownEventError as exc:
            logger.error("malformed webhook payload: %s", exc)
            return 400, {"detail": "invalid webhook payload"}

        if self.accept_types is not None and event.type not in self.accept_types:
            logger.info("ignoring webhook of type %s", event.type)
            return 200, {"detail": "ignored", "type": event.type}

        try:
            result = self.on_event(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("webhook handler failed for %s", event.uuid)
            if self.raise_on_handler_error:
                return 500, {"detail": "handler error"}

        return 200, {"detail": "ok", "type": event.type}

    # -- internals ----------------------------------------------------------
    def _build(self) -> Any:
        try:
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse
            from starlette.routing import Route
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ImportError(
                "cdekx.webhooks.asgi requires Starlette: pip install 'cdekx[webhooks]'"
            ) from exc

        app_self = self

        async def webhook(request: Request) -> JSONResponse:
            body = await request.body()
            client_ip = _client_ip(request)
            status, payload = await app_self.handle_raw(
                body, path=request.url.path, client_ip=client_ip
            )
            return JSONResponse(payload, status_code=status)

        async def healthz(request: Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        routes = [
            Route("/", webhook, methods=["POST"]),
            Route("/{secret}", webhook, methods=["POST"]),
            Route(self.health_path, healthz, methods=["GET"]),
        ]
        return Starlette(routes=routes)


def _client_ip(request: Any) -> str | None:
    """Extract the client IP, honouring proxy headers."""
    forwarded = str(request.headers.get("x-forwarded-for") or "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = str(request.headers.get("x-real-ip") or "")
    if real_ip:
        return real_ip.strip()
    client = getattr(request, "client", None)
    host: str | None = getattr(client, "host", None)
    return host
