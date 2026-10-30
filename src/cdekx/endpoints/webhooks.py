"""Webhook subscriptions: ``/v2/webhooks``.

Verified against the OpenAPI specification at apidoc.cdek.ru:

==============================  =============================================
Method                          Operation
==============================  =============================================
``POST /v2/webhooks``           Add a subscription (body: ``{type, url}``)
``GET /v2/webhooks``            List subscriptions (an array of ``WebhookDto``)
``GET /v2/webhooks/{uuid}``     A subscription by UUID (envelope with ``entity``)
``DELETE /v2/webhooks/{uuid}``  Delete a subscription
==============================  =============================================

Limits:

* at most **two** active subscriptions per account. The OpenAPI specification
  does not state this limit, but the API enforces it: HTTP 400 with code
  ``v2_too_many_webhooks`` ("Too many active webhooks. Maximum allowed is 2.")
  — see :data:`cdekx.models.TOO_MANY_WEBHOOKS_ERROR`;
* the response timeout for your URL is 15 seconds;
* at most 12 redeliveries over 75 minutes, after which all subscriptions of
  the offending URL are disabled;
* if CDEK never receives ``200 OK``, the subscription is deleted after 24 hours.

The first three points come from the "General information -> Webhook structure"
section of the apidoc.cdek.ru documentation; the subscription limit was
confirmed by measurement against ``api.edu.cdek.ru``.

Parsing of inbound events lives in :mod:`cdekx.webhooks.events`.
"""

from __future__ import annotations

import builtins

from ..exceptions import ApiError
from ..models.base import ResponseEnvelope
from ..models.webhooks import (
    MAX_WEBHOOK_SUBSCRIPTIONS,
    TOO_MANY_WEBHOOKS_ERROR,
    Webhook,
    WebhookCreate,
    WebhookInfoResponse,
    WebhookResponse,
)
from ..types.enums import WebhookType
from .base import Endpoint

__all__ = ["WebhooksEndpoint"]


class WebhooksEndpoint(Endpoint):
    """Managing event subscriptions."""

    base_path = "/v2/webhooks"

    async def create(
        self,
        url: str,
        type: WebhookType | str = WebhookType.ORDER_STATUS,  # noqa: A002
    ) -> WebhookResponse:
        """Add a subscription (``POST /v2/webhooks``).

        Args:
        url: HTTPS address that receives the events. Including a secret path
        segment is recommended — CDEK does not sign the webhook body.
        type: event type (``ORDER_STATUS``, ``PRINT_FORM``, ...).

        Note:
        Per the specification a duplicate type is not rejected: "if the client
        already has a subscription with the given type, another subscription with
        the same type will be created" — but only until you hit the limit of two
        active subscriptions.

        Raises:
        ApiError: the subscription limit was exceeded (HTTP 400, code
        ``v2_too_many_webhooks`` — see
        :data:`cdekx.models.TOO_MANY_WEBHOOKS_ERROR`) or the event type is
        invalid (``v2_webhook_type_incorrect``).

        """
        return await self._post_model(
            WebhookResponse,
            self.base_path,
            json_body=self._dump(WebhookCreate(url=url, type=type)),
        )

    async def list(self) -> builtins.list[Webhook]:
        """Subscriptions of the account (``GET /v2/webhooks``).

        The response is an array of ``{uuid, type, url}`` objects, without an envelope.
        """
        return await self._get_list(Webhook, self.base_path, key="items")

    async def get(self, uuid: str) -> Webhook:
        """Subscription details by UUID (``GET /v2/webhooks/{uuid}``)."""
        envelope = await self.get_envelope(uuid)
        return envelope.entity or Webhook.model_construct(uuid=uuid, type="", url="")

    async def get_envelope(self, uuid: str) -> WebhookInfoResponse:
        """Full response envelope for a subscription UUID."""
        return await self._get_model(WebhookInfoResponse, f"{self.base_path}/{uuid}")

    async def delete(self, uuid: str) -> WebhookResponse:
        """Delete a subscription (``DELETE /v2/webhooks/{uuid}``)."""
        return await self._delete_model(WebhookResponse, f"{self.base_path}/{uuid}")

    async def delete_all(self) -> builtins.list[str]:
        """Delete every subscription of the account.

        Returns:
        UUIDs of the deleted subscriptions.

        """
        removed: builtins.list[str] = []
        for webhook in await self.list():
            if webhook.uuid:
                await self.delete(webhook.uuid)
                removed.append(webhook.uuid)
        return removed

    async def has_capacity(self) -> bool:
        """Whether a slot is free for a new subscription (the CDEK limit is 2).

        The check is approximate: ``GET /v2/webhooks`` may return more than two
        records — for example a subscription marked for deletion in 24 hours is no
        longer counted as active by the API (three records were observed in the
        sandbox list while the error message reported two active ones). The server
        enforces the limit for real: ``POST /v2/webhooks`` answers HTTP 400 with code
        ``v2_too_many_webhooks`` — see :meth:`is_limit_error`.
        """
        return len(await self.list()) < MAX_WEBHOOK_SUBSCRIPTIONS

    @staticmethod
    def is_limit_error(exc: BaseException) -> bool:
        """Whether the error means "too many active subscriptions".

        Example::

        try:
        await client.webhooks.create(url)
        except ApiError as exc:
        if WebhooksEndpoint.is_limit_error(exc):
            await client.webhooks.delete_all()
            ...

        The ``v2_too_many_webhooks`` code is not described in the OpenAPI
        specification but is really returned by the API (verified against
        ``api.edu.cdek.ru``).
        """
        return isinstance(exc, ApiError) and exc.has_code(TOO_MANY_WEBHOOKS_ERROR)

    async def replace(
        self,
        url: str,
        type: WebhookType | str = WebhookType.ORDER_STATUS,  # noqa: A002
    ) -> WebhookResponse:
        """Free up a slot and create a subscription (handy when moving a URL).

        Deletes all existing subscriptions, then creates a new one.

        Warning:
        Events are lost between the deletion and the creation — perform the
        operation at a time of minimal traffic.

        """
        await self.delete_all()
        return await self.create(url, type)


_ = ResponseEnvelope  # re-exported type for the documentation
