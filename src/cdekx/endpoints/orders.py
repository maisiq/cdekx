"""Orders: ``/v2/orders``.

Verified against the OpenAPI specification at apidoc.cdek.ru:

===============================  ============================================
Method                           Operation
===============================  ============================================
``POST /v2/orders``              Register an order (HTTP 202)
``PATCH /v2/orders``             Update an order — the identifier goes **in the body**
``GET /v2/orders``               Order by ``cdek_number`` or ``im_number``
``GET /v2/orders/{uuid}``        Order by UUID
``DELETE /v2/orders/{uuid}``     Delete an order (HTTP 202)
``GET /v2/orders/{uuid}/intakes`` All intakes of an order
``POST /v2/orders/{uuid}/clientReturn``  Client return
``POST /v2/orders/{uuid}/refusal``       Order refusal
===============================  ============================================

Important properties of the current API:

* updates go through ``PATCH /v2/orders`` (not ``PUT /v2/orders/{uuid}``);
* there is **no** paginated list of orders — ``GET /v2/orders`` returns a
  single order by number;
* responses arrive in a ``{entity, requests, related_entities}`` envelope.
"""

from __future__ import annotations

from typing import Any

from ..exceptions import NotFoundError
from ..models.base import RequestState, ResponseEnvelope, RootEntity
from ..models.intakes import IntakeInfo
from ..models.orders import (
    ClientReturnCreate,
    Order,
    OrderCreate,
    OrderNumberQuery,
    OrderUpdate,
    RefusalCreate,
)
from .base import Endpoint, poll_until, raise_if_invalid

__all__ = ["OrderEnvelope", "OrdersEndpoint", "TaskEnvelope"]


class OrderEnvelope(ResponseEnvelope[Order]):
    """Response envelope of the order methods (``ResponseDtoOrderResponseDto``).

    Contains ``entity`` (the order), ``requests`` (state of the asynchronous
    processing) and ``related_entities`` (reverse logistics, returns, print forms).
    """


class TaskEnvelope(ResponseEnvelope[RootEntity]):
    """Response envelope of registration/update/deletion (HTTP 202)."""


class OrdersEndpoint(Endpoint):
    """Order operations."""

    base_path = "/v2/orders"

    # -- creation and updates ----------------------------------------------
    async def create(self, order: OrderCreate | dict[str, Any]) -> TaskEnvelope:
        """Register an order (``POST /v2/orders``, answer 202).

        Args:
        order: an :class:`OrderCreate` model or a dict with the request body.

        Returns:
        A task envelope. ``uuid`` is the order identifier in the CDEK system,
        ``state`` is ``ACCEPTED`` (the request was accepted but the order is not
        created yet).

        Note:
        The ``ACCEPTED`` state describes the **request**, not the order, and does
        not guarantee creation. Learn the outcome via :meth:`wait`, :meth:`get` or
        the ``ORDER_STATUS`` webhook.

        """
        return await self._post_model(TaskEnvelope, self.base_path, json_body=self._dump(order))

    async def update(self, order: OrderUpdate | dict[str, Any]) -> TaskEnvelope:
        """Update an order (``PATCH /v2/orders``, answer 202).

        The identifier is passed in the body: ``uuid`` or ``cdek_number``.
        Only orders in the ``CREATED``/``ACCEPTED`` statuses can be updated,
        otherwise CDEK returns the ``v2_update_forbidden`` error.

        Example:
        >>> await client.orders.update(  # doctest: +SKIP
        ...     OrderUpdate(uuid="...", type=1, recipient=..., comment="address clarified")
        ... )

        """
        return await self._patch_model(TaskEnvelope, self.base_path, json_body=self._dump(order))

    async def delete(self, uuid: str) -> TaskEnvelope:
        """Delete an order (``DELETE /v2/orders/{uuid}``, answer 202)."""
        return await self._delete_model(TaskEnvelope, f"{self.base_path}/{uuid}")

    async def client_return(
        self, uuid: str, data: ClientReturnCreate | dict[str, Any]
    ) -> TaskEnvelope:
        """Register a client return (``POST /v2/orders/{uuid}/clientReturn``)."""
        return await self._post_model(
            TaskEnvelope, f"{self.base_path}/{uuid}/clientReturn", json_body=self._dump(data)
        )

    async def refuse(
        self, uuid: str, data: RefusalCreate | dict[str, Any] | None = None
    ) -> TaskEnvelope:
        """Register an order refusal (``POST /v2/orders/{uuid}/refusal``)."""
        return await self._post_model(
            TaskEnvelope, f"{self.base_path}/{uuid}/refusal", json_body=self._dump(data)
        )

    # -- reading -------------------------------------------------------------
    async def get(self, uuid: str) -> Order:
        """Order details by UUID (``GET /v2/orders/{uuid}``).

        Returns:
        The order from the ``entity`` field of the response.

        Raises:
        NotFoundError: the order was not found (error code ``v2_entity_not_found``).

        """
        envelope = await self.get_envelope(uuid)
        if envelope.entity is None:
            raise NotFoundError(f"order {uuid} has no entity in response", status_code=404)
        return envelope.entity

    async def get_envelope(self, uuid: str) -> OrderEnvelope:
        """Full response envelope by UUID: order + ``requests`` + ``related_entities``."""
        return await self._get_model(OrderEnvelope, f"{self.base_path}/{uuid}")

    async def get_by_number(self, cdek_number: str) -> Order:
        """Order by CDEK number (``GET /v2/orders?cdek_number=...``)."""
        return await self._get_one(OrderNumberQuery(cdek_number=cdek_number), cdek_number)

    async def get_by_client_number(self, im_number: str) -> Order:
        """Order by the number in your own system (``GET /v2/orders?im_number=...``)."""
        return await self._get_one(OrderNumberQuery(im_number=im_number), im_number)

    async def get_envelope_by_number(self, cdek_number: str) -> OrderEnvelope:
        """Response envelope by CDEK number (including ``requests`` and ``related_entities``)."""
        return await self._get_model(
            OrderEnvelope,
            self.base_path,
            params=OrderNumberQuery(cdek_number=cdek_number).to_query(),
        )

    async def _get_one(self, query: OrderNumberQuery, identifier: str) -> Order:
        envelope = await self._get_model(OrderEnvelope, self.base_path, params=query.to_query())
        if envelope.entity is None:
            raise NotFoundError(f"order {identifier!r} not found", status_code=404)
        return envelope.entity

    async def intakes(self, order_uuid: str) -> list[IntakeInfo]:
        """All intakes of an order (``GET /v2/orders/{orderUuid}/intakes``).

        The response is a "bare" array of ``IntakeInfoResponseEntity[]`` (no envelope).
        In the specification this schema is identical to ``IntakeInfoDto``, so a list of
        :class:`cdekx.models.IntakeInfo` is returned.

        Note:
        This is the only way to get a **list** of intakes: the API has no generic
        ``GET /v2/intakes`` method.

        """
        return await self._get_list(IntakeInfo, f"{self.base_path}/{order_uuid}/intakes")

    # -- asynchronous processing ---------------------------------------------
    async def wait(
        self,
        uuid: str,
        *,
        timeout: float = 60.0,
        interval: float = 2.0,
        backoff: float = 1.5,
    ) -> OrderEnvelope:
        """Wait for the asynchronous processing of an order to finish.

        CDEK answers order creation with HTTP 202 and the ``ACCEPTED`` state, which
        only means "the request was accepted". Processing usually takes 200-500 ms,
        up to 30-60 s under peak load. The documentation recommends waiting 2-3
        seconds before the first poll.

        Returns:
        An envelope with an order whose ``state`` became ``SUCCESSFUL`` or
        ``INVALID``, or which gained a ``cdek_number``.

        Raises:
        ApiError: the order was rejected during processing (carries ``errors``).
        TimeoutExceeded: the state stayed ``ACCEPTED``.

        """

        async def fetch() -> OrderEnvelope:
            return await self.get_envelope(uuid)

        def is_done(envelope: OrderEnvelope) -> bool:
            if envelope.state in (RequestState.SUCCESSFUL, RequestState.INVALID):
                return True
            entity = envelope.entity
            return bool(entity and entity.cdek_number)

        envelope: OrderEnvelope = await poll_until(
            fetch,
            is_done,
            timeout=timeout,
            interval=interval,
            backoff=backoff,
            on_timeout=f"order {uuid} was not processed",
        )
        raise_if_invalid(envelope, entity_name="order")
        return envelope
