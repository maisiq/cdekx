"""CDEK webhooks: event models, parsing, and receiving them in an ASGI app.

Typical setup::

    from cdekx.webhooks import WebhookEvent, parse_event
    from cdekx.webhooks.asgi import WebhookApp

    app = WebhookApp(on_event=handle)   # Starlette/FastAPI-compatible ASGI app

CDEK expects ``200 OK`` within 15 seconds; on failure it retries up to 12 times
over 75 minutes and then disables the subscriptions of the offending URL. Keep
the handler fast: persist the event and process it in the background.

An account may have at most two active subscriptions: the API answers HTTP 400
with code ``v2_too_many_webhooks`` for a third one (the limit is not described
in the OpenAPI specification — it was confirmed by measurement). See
:meth:`cdekx.endpoints.webhooks.WebhooksEndpoint.has_capacity` and
:meth:`~cdekx.endpoints.webhooks.WebhooksEndpoint.replace`.
"""

from __future__ import annotations

from .events import (
    CourierInfoAttributes,
    DelivAgreementAttributes,
    DelivProblemAttributes,
    DownloadPhotoAttributes,
    OfficeAvailabilityAttributes,
    OrderModifiedAttributes,
    OrderStatusAttributes,
    PrealertClosedAttributes,
    PrintFormAttributes,
    RelatedEntity,
    UnknownEventError,
    WebhookEvent,
    parse_event,
)
from .security import CDEK_IP_RANGES, is_cdek_ip, verify_ip

__all__ = [
    "CDEK_IP_RANGES",
    "CourierInfoAttributes",
    "DelivAgreementAttributes",
    "DelivProblemAttributes",
    "DownloadPhotoAttributes",
    "OfficeAvailabilityAttributes",
    "OrderModifiedAttributes",
    "OrderStatusAttributes",
    "PrealertClosedAttributes",
    "PrintFormAttributes",
    "RelatedEntity",
    "UnknownEventError",
    "WebhookEvent",
    "is_cdek_ip",
    "parse_event",
    "verify_ip",
]
