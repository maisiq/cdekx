"""Webhook subscription models: ``/v2/webhooks``.

Verified against the OpenAPI specification at apidoc.cdek.ru: ``WebhookDto``,
``WebhookResponseDto``, ``ResponseDtoWebhookDto``, ``ResponseDtoWebhookResponseDto``.

``WebhookDto`` has exactly three fields: ``uuid`` (read-only), ``type``
and ``url``.

The "at most two active subscriptions" limit is not described in the OpenAPI
specification but is enforced by the API: a third subscription returns HTTP 400
with code ``v2_too_many_webhooks`` (verified against ``api.edu.cdek.ru``).
"""

from __future__ import annotations

from pydantic import Field

from ..types.enums import WebhookType
from .base import CdekModel, RelatedEntity, RequestInfo

__all__ = [
    "MAX_WEBHOOK_SUBSCRIPTIONS",
    "TOO_MANY_WEBHOOKS_ERROR",
    "Webhook",
    "WebhookCreate",
    "WebhookCreated",
    "WebhookResponse",
]

#: Maximum number of active subscriptions per account. Not stated in the
#: specification — confirmed by the ``v2_too_many_webhooks`` error
#: ("Maximum allowed is 2").
MAX_WEBHOOK_SUBSCRIPTIONS = 2

#: CDEK error code returned when the subscription limit is exceeded
#: (``ApiError.has_code(...)``).
TOO_MANY_WEBHOOKS_ERROR = "v2_too_many_webhooks"


class WebhookCreate(CdekModel):
    """Request body of ``POST /v2/webhooks`` (``WebhookDto`` without ``uuid``)."""

    type: WebhookType | str = Field(description="Event type (see types.enums.WebhookType)")
    url: str = Field(description="URL the event is delivered to")


class Webhook(CdekModel):
    """A webhook subscription (``WebhookDto``)."""

    uuid: str | None = Field(default=None, description="Webhook identifier (read-only)")
    type: WebhookType | str = Field(description="Event type")
    url: str = Field(description="URL of the event receiver")


class WebhookCreated(CdekModel):
    """Entity returned when a subscription is created or deleted (``WebhookResponseDto``)."""

    uuid: str | None = Field(default=None, description="Webhook identifier")


class WebhookResponse(CdekModel):
    """Response envelope of ``POST``/``DELETE /v2/webhooks`` (``ResponseDtoWebhookResponseDto``)."""

    entity: WebhookCreated | None = Field(
        default=None, description="The created or deleted subscription"
    )
    requests: list[RequestInfo] | None = Field(default=None, description="Request list")
    related_entities: list[RelatedEntity] | None = Field(
        default=None, description="Related entities"
    )

    @property
    def uuid(self) -> str | None:
        """UUID of the subscription."""
        return self.entity.uuid if self.entity else None


class WebhookInfoResponse(CdekModel):
    """Response envelope of ``GET /v2/webhooks/{uuid}`` (``ResponseDtoWebhookDto``)."""

    entity: Webhook | None = Field(default=None, description="The subscription")
    requests: list[RequestInfo] | None = Field(default=None, description="Request list")
