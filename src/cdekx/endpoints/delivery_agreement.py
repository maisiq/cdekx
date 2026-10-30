"""Delivery agreement: ``/v2/delivery``.

Verified against the OpenAPI specification at apidoc.cdek.ru:

==========================================  ==================================
Method                                      Operation
==========================================  ==================================
``POST /v2/delivery``                       Register an agreement (202)
``GET /v2/delivery/{uuid}``                 Agreement details
``GET /v2/delivery/intervals``              Delivery intervals for an order
``POST /v2/delivery/estimatedIntervals``    Intervals **before** the order is created
==========================================  ==================================

Scenario: agree on a delivery date and time window "to the door" with the
recipient. Registration typically fails with ``delivery_date_too_early`` or
``delivery_date_too_late``; obtain the allowed range via
:meth:`DeliveryAgreementEndpoint.intervals`.
"""

from __future__ import annotations

from typing import Any

from ..exceptions import NotFoundError
from ..models.base import RequestState, ResponseEnvelope, RootEntity
from ..models.delivery_agreement import (
    AvailableIntervalsResponse,
    DeliveryAgreement,
    DeliveryAgreementInfo,
    DeliveryAgreementResponse,
    EstimatedIntervalsRequest,
    EstimatedIntervalsResponse,
)
from .base import Endpoint, poll_until, raise_if_invalid

__all__ = ["DeliveryAgreementEndpoint", "TaskEnvelope"]


class TaskEnvelope(ResponseEnvelope[RootEntity]):
    """Response envelope of an agreement registration (HTTP 202)."""


class DeliveryAgreementEndpoint(Endpoint):
    """Agreeing on a delivery date and time window."""

    base_path = "/v2/delivery"

    async def create(self, agreement: DeliveryAgreement | dict[str, Any]) -> TaskEnvelope:
        """Register a delivery agreement (``POST /v2/delivery``, 202).

        Args:
            agreement: a :class:`DeliveryAgreement` model or a dict. The order is
                identified by ``cdek_number`` or ``order_uuid``; ``date`` is required,
                and ``time_from``/``time_to`` only for "to the door" orders.

        """
        return await self._post_model(TaskEnvelope, self.base_path, json_body=self._dump(agreement))

    async def get(self, uuid: str) -> DeliveryAgreementInfo:
        """Agreement details (``GET /v2/delivery/{uuid}``)."""
        envelope = await self.get_envelope(uuid)
        if envelope.entity is None:
            raise NotFoundError(
                f"delivery agreement {uuid} has no entity in response", status_code=404
            )
        return envelope.entity

    async def get_envelope(self, uuid: str) -> DeliveryAgreementResponse:
        """Full response envelope for an agreement UUID."""
        return await self._get_model(DeliveryAgreementResponse, f"{self.base_path}/{uuid}")

    async def intervals(
        self, *, cdek_number: str | None = None, order_uuid: str | None = None
    ) -> AvailableIntervalsResponse:
        """Delivery intervals available for an existing order.

        ``GET /v2/delivery/intervals?cdek_number=...`` or ``?order_uuid=...``.

        Args:
            cdek_number: CDEK order number.
            order_uuid: order UUID (an alternative to the number).

        """
        params: dict[str, Any] = {}
        if cdek_number:
            params["cdek_number"] = cdek_number
        if order_uuid:
            params["order_uuid"] = order_uuid
        return await self._get_model(
            AvailableIntervalsResponse, f"{self.base_path}/intervals", params=params or None
        )

    async def estimated_intervals(
        self, request: EstimatedIntervalsRequest | dict[str, Any]
    ) -> EstimatedIntervalsResponse:
        """Delivery intervals **before** an order is created.

        ``POST /v2/delivery/estimatedIntervals``. Lets you compute the slots available
        to the agreement widget in advance, based on the direction and tariff.
        """
        return await self._post_model(
            EstimatedIntervalsResponse,
            f"{self.base_path}/estimatedIntervals",
            json_body=self._dump(request),
        )

    async def wait(
        self, uuid: str, *, timeout: float = 60.0, interval: float = 2.0, backoff: float = 1.5
    ) -> DeliveryAgreementResponse:
        """Wait for the asynchronous agreement registration to finish."""

        async def fetch() -> DeliveryAgreementResponse:
            return await self.get_envelope(uuid)

        def is_done(envelope: DeliveryAgreementResponse) -> bool:
            states = [r.state for r in (envelope.requests or [])]
            return RequestState.SUCCESSFUL in states or RequestState.INVALID in states

        envelope: DeliveryAgreementResponse = await poll_until(
            fetch,
            is_done,
            timeout=timeout,
            interval=interval,
            backoff=backoff,
            on_timeout=f"delivery agreement {uuid} was not processed",
        )
        raise_if_invalid(envelope, entity_name="delivery agreement")
        return envelope
