"""Courier pickup requests (intakes): ``/v2/intakes``.

Verified against the OpenAPI specification at apidoc.cdek.ru:

=================================  ==========================================
Method                             Operation
=================================  ==========================================
``POST /v2/intakes``               Register an intake (HTTP 202)
``GET /v2/intakes/{uuid}``         Intake details
``PATCH /v2/intakes``              Change the intake status
``DELETE /v2/intakes/{uuid}``      Delete an intake
``POST /v2/intakes/availableDays``  Courier dates available for a settlement
``GET /v2/orders/{uuid}/intakes``  All intakes of an order (see ``OrdersEndpoint``)
=================================  ==========================================

Important: there is **no** list of intakes (``GET /v2/intakes``) and no intake
update (``PUT``) in the API, even though both are easy to assume "by analogy"
with the other sections.

A consolidated pickup (several waybills from one address) requires an order
under the "cargo pickup, door to warehouse" tariff (code 158): pass its number
or UUID in the intake to link them. If no waybill is linked to the intake,
CDEK creates one automatically; if that auto-creation fails, the intake is
still created and the system deletes the auto-created order after 120 days.
"""

from __future__ import annotations

from typing import Any

from ..exceptions import NotFoundError
from ..models.base import RequestState, ResponseEnvelope, RootEntity
from ..models.intakes import (
    Intake,
    IntakeAvailableDays,
    IntakeAvailableDaysRequest,
    IntakeInfo,
    IntakeStatusChange,
    IntakeStatusPatch,
)
from .base import Endpoint, poll_until, raise_if_invalid

__all__ = ["IntakeEnvelope", "IntakeInfoEnvelope", "IntakesEndpoint", "TaskEnvelope"]


class TaskEnvelope(ResponseEnvelope[RootEntity]):
    """Response envelope of an intake registration/deletion (HTTP 202)."""


class IntakeInfoEnvelope(ResponseEnvelope[IntakeInfo]):
    """Response envelope of ``GET /v2/intakes/{uuid}`` (``IntakeInfoDto``)."""


class IntakeEnvelope(ResponseEnvelope[RootEntity]):
    """Response envelope of ``PATCH /v2/intakes``.

    In the specification this is ``IntakeChangeStatusResponseDto``, whose entity
    (``IntakeChangeStatusResponseEntity``) has exactly one field — the ``uuid`` of
    the intake. Structurally that is a :class:`RootEntity`, so no separate model
    is introduced: ``entity.uuid`` is typed and available.
    """


class IntakesEndpoint(Endpoint):
    """Courier pickup requests (intakes)."""

    base_path = "/v2/intakes"

    async def create(self, intake: Intake | dict[str, Any]) -> TaskEnvelope:
        """Register an intake (``POST /v2/intakes``, answer 202).

        Args:
        intake: an :class:`Intake` model or a dict with the request body.

        Returns:
        A task envelope: the intake ``uuid`` and ``state`` = ``ACCEPTED``.

        """
        return await self._post_model(TaskEnvelope, self.base_path, json_body=self._dump(intake))

    async def get(self, uuid: str) -> IntakeInfo:
        """Intake details by UUID (``GET /v2/intakes/{uuid}``)."""
        envelope = await self.get_envelope(uuid)
        if envelope.entity is None:
            raise NotFoundError(f"intake {uuid} has no entity in response", status_code=404)
        return envelope.entity

    async def get_envelope(self, uuid: str) -> IntakeInfoEnvelope:
        """Full response envelope for an intake UUID (with ``requests``)."""
        return await self._get_model(IntakeInfoEnvelope, f"{self.base_path}/{uuid}")

    async def change_status(
        self,
        uuid: str,
        *,
        code: str,
        add_status: str,
    ) -> IntakeEnvelope:
        """Change the intake status (``PATCH /v2/intakes``).

        Args:
        uuid: identifier of the intake in the CDEK system.
        code: status code, for example ``CANCELLED`` (``IntakeStatusCode``).
        add_status: additional code, for example ``CANCELLED_BY_CLIENT``.

        """
        body = IntakeStatusChange(
            uuid=uuid, status=IntakeStatusPatch(code=code, add_status=add_status)
        )
        return await self._patch_model(IntakeEnvelope, self.base_path, json_body=self._dump(body))

    async def delete(self, uuid: str) -> TaskEnvelope:
        """Delete an intake (``DELETE /v2/intakes/{uuid}``).

        Note:
        An intake in a final status cannot be deleted — CDEK answers
        ``v2_entity_has_final_status``.

        """
        return await self._delete_model(TaskEnvelope, f"{self.base_path}/{uuid}")

    async def available_days(
        self, request: IntakeAvailableDaysRequest | dict[str, Any]
    ) -> IntakeAvailableDays:
        """Courier pickup dates available for a settlement.

        ``POST /v2/intakes/availableDays``.

        Example:
        >>> days = await client.intakes.available_days({  # doctest: +SKIP
        ...     "from_location": {"code": 44},
        ...     "date": "2026-06-30",
        ... })

        """
        return await self._post_model(
            IntakeAvailableDays, f"{self.base_path}/availableDays", json_body=self._dump(request)
        )

    async def wait(
        self, uuid: str, *, timeout: float = 60.0, interval: float = 2.0, backoff: float = 1.5
    ) -> IntakeInfoEnvelope:
        """Wait for the asynchronous intake processing to finish."""

        async def fetch() -> IntakeInfoEnvelope:
            return await self.get_envelope(uuid)

        def is_done(envelope: IntakeInfoEnvelope) -> bool:
            return envelope.state in (RequestState.SUCCESSFUL, RequestState.INVALID)

        envelope: IntakeInfoEnvelope = await poll_until(
            fetch,
            is_done,
            timeout=timeout,
            interval=interval,
            backoff=backoff,
            on_timeout=f"intake {uuid} was not processed",
        )
        raise_if_invalid(envelope, entity_name="intake")
        return envelope


# an alias for consistent naming in the documentation
IntakeInfoResponse = IntakeInfoEnvelope
