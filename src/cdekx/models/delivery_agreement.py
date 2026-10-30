"""Models of the delivery agreement: ``/v2/delivery``.

Verified against the apidoc.cdek.ru OpenAPI specification: ``ScheduleDto``,
``ScheduleInfoDto``, ``ScheduleStatusDto``, ``ResponseDtoScheduleInfoDto``,
``AvailableDeliveryIntervalsResponseDto``, ``EstimatedDeliveryIntervalsRequestDto``.

The section allows agreeing with the recipient on a "to the door" delivery date
and interval — both for an already created order and before it is created.
"""

from __future__ import annotations

from pydantic import Field

from ..types import CdekDateTime
from ..types.enums import TariffCode
from .base import CdekModel, RelatedEntity, RequestInfo
from .common import Location

__all__ = [
    "DeliveryAgreement",
    "DeliveryAgreementInfo",
    "DeliveryAgreementResponse",
    "DeliveryAgreementStatus",
    "EstimatedIntervalsRequest",
    "TimeInterval",
]


class DeliveryAgreement(CdekModel):
    """Registration of a delivery agreement (``POST /v2/delivery`` → ``ScheduleDto``).

    The order is specified through ``cdek_number`` **or** ``order_uuid``.
    ``date`` is required; ``time_from`` and ``time_to`` are required only if the
    order is "to the door".
    """

    cdek_number: str | None = Field(
        default=None, description="CDEK order number (required if there is no order_uuid)"
    )
    order_uuid: str | None = Field(
        default=None, description="Order UUID (required if there is no cdek_number)"
    )
    date: str = Field(description="Delivery date agreed with the recipient (yyyy-MM-dd)")
    time_from: str | None = Field(
        default=None,
        description='Delivery time "from", agreed with the recipient (HH:mm). '
        'Required if the order is "to the door"',
    )
    time_to: str | None = Field(
        default=None,
        description='Delivery time "to", agreed with the recipient (HH:mm). '
        'Required if the order is "to the door"',
    )
    comment: str | None = Field(default=None, description="Comment on the agreement")
    delivery_point: str | None = Field(
        default=None, description="Code of the CDEK office the parcel will be delivered to"
    )
    to_location: Location | None = Field(default=None, description="New delivery address")


class DeliveryAgreementStatus(CdekModel):
    """Status of the delivery agreement (``ScheduleStatusDto``)."""

    code: str = Field(description="Status code")
    name: str = Field(description="Status name")
    date_time: CdekDateTime | str = Field(description="Date and time when the status was set")


class DeliveryAgreementInfo(CdekModel):
    """Delivery agreement information (``ScheduleInfoDto``)."""

    uuid: str = Field(description="Entity identifier in the CDEK information system")
    order_uuid: str = Field(description="Order UUID")
    cdek_number: str | None = Field(default=None, description="CDEK order number")
    date: str = Field(description="Delivery date")
    time_from: str = Field(description='Time "from"')
    time_to: str = Field(description='Time "to"')
    comment: str | None = Field(default=None, description="Comment")
    delivery_point: str | None = Field(default=None, description="New office code")
    to_location: Location | None = Field(default=None, description="New delivery address")
    statuses: list[DeliveryAgreementStatus] = Field(
        default_factory=list, description="Delivery agreement statuses"
    )
    source: str | None = Field(
        default=None, description="Source of the agreement (a module, an external system)"
    )

    @property
    def current_status(self) -> DeliveryAgreementStatus | None:
        """Return the last status of the delivery agreement."""
        return self.statuses[-1] if self.statuses else None


class DeliveryAgreementResponse(CdekModel):
    """Response envelope of ``GET /v2/delivery/{uuid}`` (``ResponseDtoScheduleInfoDto``)."""

    entity: DeliveryAgreementInfo | None = Field(default=None, description="Delivery agreement")
    requests: list[RequestInfo] = Field(
        default_factory=list, description="Requests over the entity"
    )
    related_entities: list[RelatedEntity] | None = Field(
        default=None, description="Related entities"
    )


class TimeInterval(CdekModel):
    """A delivery time interval."""

    start_time: str = Field(description="Start time of the interval")
    end_time: str = Field(description="End time of the interval")
    agreed_count: int | None = Field(
        default=None, description="How many deliveries are already agreed in the interval"
    )
    total_count: int | None = Field(default=None, description="Total deliveries in the interval")


class DateIntervals(CdekModel):
    """Available intervals for a specific date."""

    date: str = Field(description="Date of the interval, yyyy-MM-dd")
    time_intervals: list[TimeInterval] = Field(
        default_factory=list, description="Time intervals for delivery"
    )


class AvailableIntervalsResponse(CdekModel):
    """Response of ``GET /v2/delivery/intervals`` (for an existing order)."""

    date_intervals: list[DateIntervals] = Field(
        default_factory=list, description="Available delivery intervals"
    )


class EstimatedIntervalsRequest(CdekModel):
    """Request intervals **before** creating the order (``POST /v2/delivery/estimatedIntervals``).

    ``date_time``, ``tariff_code`` and ``to_location`` are required.
    ``from_location`` is required only if the order uses a "from the door" tariff
    and cannot be used together with ``shipment_point`` (the latter is required
    for tariffs with the "from the warehouse" mode).
    """

    date_time: str = Field(description="Date and time of the planned shipment")
    from_location: Location | None = Field(
        default=None,
        description="Origin address. Cannot be used together with "
        'shipment_point. Required if the order uses a "from the door" tariff',
    )
    to_location: Location = Field(description="Recipient location")
    tariff_code: TariffCode | int = Field(description="Tariff code")
    shipment_point: str | None = Field(
        default=None,
        description="Code of the CDEK office to which the client will bring the parcel "
        "themselves. Cannot be used together with from_location. "
        'Required if the tariff uses the "from the warehouse" mode',
    )
    additional_order_types: list[int] | None = Field(
        default=None,
        description="Additional order type: 2 — consolidated cargo (LTL), 4 — Forward, "
        "6 — Fulfillment. Inbound, 7 — Fulfillment. Outbound, 9 — Forward. Express, "
        '10 — tyre delivery ("Economy express"), 11 — "One office", '
        "14 — CDEK.Shopping, 15 — last-mile service",
    )


class EstimatedIntervalsResponse(CdekModel):
    """Response of ``POST /v2/delivery/estimatedIntervals``."""

    date_intervals: list[DateIntervals] = Field(
        default_factory=list, description="Available delivery intervals before the order is created"
    )
