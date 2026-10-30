"""Order models.

Verified against the apidoc.cdek.ru OpenAPI specification:
``OrderCreateRequestDto``, ``OrderUpdateRequestDto``, ``OrderResponseDto``,
``OrderStatusDto``, ``ResponseDeliveryDetailDto``, ``AccompanyingWaybillDto``,
``CallsResponseDto``, ``OrderDelayReason``, ``DeliveryProblemResponseDto``.

Key point: responses of the order methods arrive in the envelope
``{"entity": ..., "requests": [...], "related_entities": [...]}``
(:class:`cdekx.models.base.ResponseEnvelope`).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..types import CdekDate, CdekDateTime
from ..types.enums import DeliveryMode, OrderType, TariffCode
from .base import CdekModel, QueryModel
from .common import (
    Contact,
    DeliveryCostThreshold,
    Location,
    Money,
    Package,
    PackageResponse,
    Seller,
    Service,
    ServiceResponse,
)

__all__ = [
    "AccompanyingWaybill",
    "Calls",
    "DeliveryDetail",
    "DeliveryProblem",
    "FailedCall",
    "Order",
    "OrderCreate",
    "OrderDelayReason",
    "OrderNumberQuery",
    "OrderStatus",
    "OrderUpdate",
    "RescheduledCall",
]


class OrderCreate(CdekModel):
    """Order registration (``POST /v2/orders`` → ``OrderCreateRequestDto``).

    Per the specification ``tariff_code``, ``recipient`` and ``packages`` are
    required. The rest of the fields are required **conditionally** — depending
    on the order type, the tariff (door/warehouse) and the international nature
    of the shipment:

    * ``type`` — for an online-shop/delivery contract;
    * ``number`` — for "online shop" type orders;
    * ``sender`` — if the order is not from a natural person;
    * ``from_location``/``to_location`` or ``shipment_point``/``delivery_point``;
    * ``date_invoice``, ``shipper_name``, ``shipper_address`` — an international
      online-shop order.

    Limit: from 1 to 255 cargo places per order, no more than 126 items.
    """

    type: OrderType | int | None = Field(
        default=None,
        description="Order type: 1 — online shop, 2 — delivery, 3 — supplier, "
        "4 — return, 7 — service, etc.",
    )
    additional_order_types: list[int] | None = Field(
        default=None,
        description="Additional order types, e.g. 2 — consolidated cargo (LTL), 10 — tyres",
    )
    number: str | None = Field(
        default=None,
        description="Order number in the client system (for online-shop orders). Digits, "
        "Latin letters and punctuation are allowed (see number on apidoc.cdek.ru)",
    )
    accompanying_number: str | None = Field(
        default=None, description="Number of the accompanying goods note (SNT)"
    )
    tariff_code: TariffCode | int = Field(description="Tariff code (required)")
    comment: str | None = Field(default=None, description="Comment on the order")
    shipment_point: str | None = Field(
        default=None, description="Code of the office the client brings the cargo to themselves"
    )
    delivery_point: str | None = Field(
        default=None, description="Code of the office the parcel is delivered to"
    )
    date_invoice: str | None = Field(
        default=None, description="Invoice date (required for an international online-shop order)"
    )
    shipper_name: str | None = Field(default=None, description="Shipper")
    shipper_address: str | None = Field(default=None, description="Shipper address")
    delivery_recipient_cost: Money | None = Field(
        default=None, description="Fixed extra delivery fee charged to the recipient"
    )
    delivery_recipient_cost_adv: list[DeliveryCostThreshold] | None = Field(
        default=None, description="Dynamic extra fee with buyout thresholds (threshold/sum)"
    )
    sender: Contact | None = Field(default=None, description="Sender")
    seller: Seller | None = Field(default=None, description="True seller")
    recipient: Contact = Field(description="Recipient (required)")
    from_location: Location | None = Field(default=None, description="Sender location")
    to_location: Location | None = Field(default=None, description="Recipient location")
    services: list[Service] | None = Field(default=None, description="Additional services")
    packages: list[Package] = Field(
        min_length=1, max_length=255, description="Cargo places: from 1 to 255"
    )
    delivery_types: list[Any] | None = Field(default=None, description="Delivery types")
    print: str | None = Field(
        default=None, description="Type of the print form to be generated for the order"
    )
    widgetToken: str | None = Field(  # noqa: N815 — the field name is dictated by the API
        default=None, description="CMS token with additional order data"
    )
    is_client_return: bool | None = Field(
        default=None, description="Client return flag (the forward order went to another recipient)"
    )
    has_reverse_order: bool | None = Field(
        default=None,
        description="A reverse order is needed (replaces the deprecated REVERSE service)",
    )
    developer_key: str | None = Field(default=None, description="Developer key")


class OrderUpdate(CdekModel):
    """Order modification (``PATCH /v2/orders`` → ``OrderUpdateRequestDto``).

    The identifier is passed **in the request body**: ``uuid`` or ``cdek_number``.
    Only orders in the ``CREATED`` or ``ACCEPTED`` statuses can be modified
    (otherwise CDEK returns ``v2_update_forbidden``).
    """

    uuid: str | None = Field(
        default=None,
        description="Order UUID in the CDEK system (not required if cdek_number is given)",
    )
    cdek_number: str | None = Field(
        default=None, description="CDEK order number (not required if uuid is given)"
    )
    type: OrderType | int = Field(description="Order type (required)")
    number: str | None = Field(
        default=None, description="Order number in the client information system"
    )
    accompanying_number: str | None = Field(default=None, description="SNT number")
    tariff_code: TariffCode | int | None = Field(default=None, description="Tariff code")
    comment: str | None = Field(default=None, description="Comment on the order")
    shipment_point: str | None = Field(default=None, description="Code of the shipment office")
    delivery_point: str | None = Field(default=None, description="Code of the handout office")
    delivery_recipient_cost: Money | None = Field(default=None, description="Extra delivery fee")
    delivery_recipient_cost_adv: list[DeliveryCostThreshold] | None = Field(
        default=None, description="Dynamic extra fee with thresholds"
    )
    sender: Contact | None = Field(default=None, description="Sender")
    seller: Seller | None = Field(default=None, description="True seller")
    recipient: Contact = Field(description="Recipient (required)")
    from_location: Location | None = Field(default=None, description="Sender location")
    to_location: Location | None = Field(default=None, description="Recipient location")
    services: list[Service] | None = Field(default=None, description="Additional services")
    packages: list[Package] | None = Field(default=None, description="Cargo places")
    has_reverse_order: bool | None = Field(default=None, description="A reverse order is needed")
    delivery_types: list[Any] | None = Field(default=None, description="Delivery types")


class OrderStatus(CdekModel):
    """Order status (``OrderStatusDto``).

    Note: the field is called ``city`` (not ``city_name``), there is
    ``city_uuid`` (not ``city_code``) and a ``deleted`` flag.
    """

    code: str | None = Field(default=None, description="Status code (Appendix 15)")
    name: str | None = Field(default=None, description="Status name")
    date_time: CdekDateTime | str | None = Field(
        default=None, description="Date when the status was set"
    )
    reason_code: str | None = Field(default=None, description="Additional status code")
    city: str | None = Field(default=None, description="Place where the status originated")
    city_uuid: str | None = Field(default=None, description="City identifier of the status")
    deleted: bool | None = Field(
        default=None, description="true — the status is deleted, false — active"
    )


class AccompanyingWaybill(CdekModel):
    """Accompanying waybill for the goods (SNT)."""

    client_name: str = Field(description="Name of the client legal entity creating the SNT")
    flight_number: str | None = Field(default=None, description="Flight number")
    air_waybill_numbers: list[str] | None = Field(
        default=None, description="Carrier waybills for the flight"
    )
    vehicle_numbers: list[str] | None = Field(
        default=None, description="Vehicle registration numbers"
    )
    vehicle_driver: str | None = Field(default=None, description="Full name of the driver")
    planned_departure_date_time: CdekDateTime | str | None = Field(
        default=None, description="Planned departure date"
    )


class PaymentInfo(CdekModel):
    """Payment information (``PaymentInfoDto``)."""

    sum: float | None = Field(default=None, description="Receipt amount")
    type: str | None = Field(default=None, description="Payment type")


class DeliveryDetail(CdekModel):
    """Delivery details in the response (``ResponseDeliveryDetailDto``).

    This is **not** the agreed delivery interval but the cost calculation and
    the actual cash-on-delivery amount.
    """

    date: str | None = Field(default=None, description="Delivery date")
    recipient_name: str | None = Field(default=None, description="Recipient at delivery")
    payment_sum: float | None = Field(
        default=None, description="Cash-on-delivery amount taken from the recipient"
    )
    delivery_sum: float = Field(description="Cost of the delivery service")
    total_sum: float = Field(description="Total cost of the order")
    payment_info: list[PaymentInfo] | None = Field(default=None, description="Payment data")
    delivery_vat_rate: int | None = Field(
        default=None, description="VAT percentage for the delivery"
    )
    delivery_vat_sum: float | None = Field(default=None, description="VAT amount for the delivery")
    delivery_discount_percent: float | None = Field(default=None, description="Discount percentage")
    delivery_discount_sum: float | None = Field(default=None, description="Discount amount")


class OrderDelayReason(CdekModel):
    """Reason for a delivery delay (``OrderDelayReason``)."""

    create_date: CdekDateTime | str | None = Field(
        default=None, description="Date when the reason was created"
    )
    description: str | None = Field(default=None, description="Description of the delay reason")


class DeliveryProblem(CdekModel):
    """A delivery problem the courier faced (``DeliveryProblemResponseDto``)."""

    code: str | None = Field(default=None, description="Problem code")
    create_date: CdekDateTime | str | None = Field(default=None, description="Date of occurrence")


class FailedCall(CdekModel):
    """Information about a failed call (``FailedCallResponseDto``).

    In the specification a failed call has two fields: ``date_time`` and
    ``reason_code`` (a numeric reason code). The ``reason`` field is kept for
    compatibility with earlier ``cdekx`` versions: the API does not return it,
    so the value is always ``None`` — use :attr:`reason_code`.
    """

    date_time: CdekDateTime | str = Field(
        description="Date and time when the failed call was created"
    )
    reason_code: int = Field(description="Numeric code of the failed call reason")
    reason: str | None = Field(
        default=None,
        description="Deprecated: no such field in the API (see reason_code). Kept for old code",
    )


class RescheduledCall(CdekModel):
    """Information about a rescheduled recipient call (``RescheduledCallResponseDto``).

    ``date_next``/``time_next`` are the agreed date and time of the repeated
    call. The ``reason`` field is kept for compatibility: the specification has
    no such field, the API returns ``comment`` instead.
    """

    date_time: CdekDateTime | str = Field(
        description="Date and time when the call reschedule was created"
    )
    date_next: CdekDate | str = Field(description="Date the repeated call is agreed for")
    time_next: str = Field(description="Time of the repeated call, HH:mm")
    comment: str | None = Field(default=None, description="Comment on the call reschedule")
    reason: str | None = Field(
        default=None,
        description="Deprecated: no such field in the API (see comment). Kept for old code",
    )


class Calls(CdekModel):
    """Recipient calls (``CallsResponseDto``)."""

    failed_calls: list[FailedCall] | None = Field(default=None, description="Failed calls")
    rescheduled_calls: list[RescheduledCall] | None = Field(
        default=None, description="Call reschedules"
    )


class Order(CdekModel):
    """Order information (``OrderResponseDto``).

    Arrives inside the ``entity`` of the response envelope. The model is
    deliberately tolerant of the field composition: the set depends on the order
    type, status and contract, and unknown fields are available in
    :attr:`extra`.

    Note:
        Per the specification ``is_return``, ``is_reverse``, ``is_client_return``,
        ``tariff_code``, ``recipient``, ``packages`` and ``statuses`` are required
        in the response. The model still gives them default values: an order that
        is being processed may arrive incomplete, and failing during parsing is
        the worst behaviour for an SDK. Check ``cdek_number``/``status_code`` if
        you need a sign of a fully processed order.

    """

    uuid: str = Field(description="Order identifier in the CDEK information system")
    type: OrderType | int | None = Field(default=None, description="Order type")
    additional_order_types: list[int] | None = Field(
        default=None, description="Additional order types"
    )
    is_return: bool = Field(default=False, description="Return order flag")
    is_reverse: bool = Field(default=False, description="Reverse order flag")
    cdek_number: str | None = Field(
        default=None, description="CDEK order number (the waybill number)"
    )
    number: str | None = Field(
        default=None, description="Order number in the client information system"
    )
    accompanying_number: str | None = Field(default=None, description="SNT number")
    accompanying_waybill: AccompanyingWaybill | None = Field(
        default=None, description="Accompanying waybill data"
    )
    tariff_code: TariffCode | int | None = Field(default=None, description="Tariff code")
    comment: str | None = Field(default=None, description="Comment on the order")
    shipment_point: str | None = Field(default=None, description="Code of the shipment office")
    delivery_point: str | None = Field(default=None, description="Code of the handout office")
    date_invoice: str | None = Field(default=None, description="Invoice date")
    keep_free_until: str | None = Field(
        default=None, description="For an order to an office: free storage until"
    )
    shipper_name: str | None = Field(default=None, description="Shipper")
    shipper_address: str | None = Field(default=None, description="Shipper address")
    delivery_recipient_cost: Money | None = Field(default=None, description="Extra delivery fee")
    delivery_recipient_cost_adv: list[DeliveryCostThreshold] | None = Field(
        default=None, description="Dynamic extra fee with thresholds"
    )
    sender: Contact | None = Field(default=None, description="Sender")
    seller: Seller | None = Field(default=None, description="True seller")
    recipient: Contact | None = Field(default=None, description="Recipient")
    from_location: Location | None = Field(default=None, description="Sender location")
    to_location: Location | None = Field(default=None, description="Recipient location")
    services: list[ServiceResponse] | None = Field(default=None, description="Additional services")
    packages: list[PackageResponse] | None = Field(default=None, description="Cargo places")
    statuses: list[OrderStatus] | None = Field(
        default=None, description="Order statuses, sorted by date and time"
    )
    is_client_return: bool = Field(default=False, description="Client return flag")
    delivery_mode: DeliveryMode | int | None = Field(
        default=None,
        description="Actual order mode: 1 — door to door, 2 — door to warehouse, "
        "3 — warehouse to door, 4 — warehouse to warehouse, 6 — door to parcel locker, "
        "7 — warehouse to parcel locker, 8 — parcel locker to door, "
        "9 — parcel locker to warehouse, 10 — parcel locker to parcel locker",
    )
    has_reverse_order: bool | None = Field(
        default=None, description="Flag that a reverse is required"
    )
    delay_reasons: list[OrderDelayReason] | None = Field(
        default=None, description="Delivery delay reasons"
    )
    delivery_types: list[Any] | None = Field(default=None, description="Delivery types")
    planned_delivery_date: str | None = Field(
        default=None, description="Planned delivery date (passed on acceptance at the warehouse)"
    )
    delivery_detail: DeliveryDetail | None = Field(
        default=None, description="Delivery cost and cash on delivery"
    )
    delivery_problem: list[DeliveryProblem] | None = Field(
        default=None, description="Delivery problems the courier faced"
    )
    developer_key: str | None = Field(default=None, description="Developer key")
    calls: Calls | None = Field(default=None, description="Information about the recipient calls")

    @property
    def current_status(self) -> OrderStatus | None:
        """Return the last active order status."""
        active = [s for s in (self.statuses or []) if not s.deleted]
        return active[-1] if active else (self.statuses[-1] if self.statuses else None)

    @property
    def status_code(self) -> str | None:
        """Return the current status code."""
        status = self.current_status
        return status.code if status else None

    @property
    def barcodes(self) -> list[str]:
        """Return the barcodes of all cargo places."""
        return [p.barcode for p in (self.packages or []) if p.barcode]


class OrderNumberQuery(QueryModel):
    """Parameters of ``GET /v2/orders`` — a search for one order by number.

    The method returns **one order**, not a list: either ``cdek_number`` or
    ``im_number`` is passed.
    """

    cdek_number: str | None = Field(default=None, description="CDEK order number")
    im_number: str | None = Field(
        default=None, description="Order number in the client information system"
    )


class ClientReturnCreate(CdekModel):
    """Registration of a client return (``POST /v2/orders/{uuid}/clientReturn``)."""

    packages: list[Package] | None = Field(default=None, description="Cargo places being returned")
    return_tariff_code: TariffCode | int | None = Field(
        default=None, description="Return tariff code"
    )
    return_location: Location | None = Field(
        default=None, description="Where the order is returned to"
    )
    comment: str | None = Field(default=None, description="Comment")
    item_details: list[dict[str, Any]] | None = Field(
        default=None, description="Details of the returned items"
    )


class RefusalCreate(CdekModel):
    """Registration of an order refusal (``POST /v2/orders/{uuid}/refusal``)."""

    comment: str | None = Field(default=None, description="Comment on the refusal")
    packages: list[Package] | None = Field(default=None, description="Cargo places of the refusal")
