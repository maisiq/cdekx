"""Models of incoming webhook events and their parsing.

Event structure (the same for all types)::

    {
      "type": "ORDER_STATUS",
      "date_time": "2026-05-01T12:30:00+0300",
      "uuid": "8dea00e3-9aab-4d8e-887c-ef2aaa546456",
      "attributes": { ... }
    }

The composition of ``attributes`` depends on ``type`` — see the section
"Description of the webhook structure" on apidoc.cdek.ru.
"""

from __future__ import annotations

import contextlib
from typing import Any, Literal, TypeVar

from pydantic import Field, ValidationError

from ..models.base import CdekModel
from ..types import CdekDateTime

__all__ = [
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
    "parse_event",
]


class UnknownEventError(ValueError):
    """The payload does not look like a CDEK webhook event."""


class RelatedEntity(CdekModel):
    """A related entity (a forward order, a client return)."""

    type: str | None = Field(default=None, description="direct_order / client_direct_order")
    cdek_number: str | None = Field(default=None, description="CDEK order number")
    uuid: str | None = Field(default=None, description="UUID of the related entity")


class OrderStatusAttributes(CdekModel):
    """``attributes`` of an ``ORDER_STATUS`` event."""

    code: str = Field(description="Status code (Appendix 1)")
    status_code: str | None = Field(default=None, description="Status code (a deprecated field)")
    status_reason_code: str | None = Field(
        default=None, description="Additional status code (Appendix 2)"
    )
    status_date_time: CdekDateTime | str | None = Field(
        default=None, description="Date and time when the status was set"
    )
    cdek_number: str | None = Field(default=None, description="CDEK order number")
    number: str | None = Field(
        default=None, description="Order number in the client information system"
    )
    city_code: int | None = Field(
        default=None, description="Code of the city where the status originated"
    )
    city_name: str | None = Field(default=None, description="City name")
    is_return: bool | None = Field(default=None, description="Return order flag")
    is_reverse: bool | None = Field(default=None, description="Reverse order flag")
    is_client_return: bool | None = Field(default=None, description="Client return flag")
    deleted: bool | None = Field(
        default=None, description="Status deletion flag (for a delivery agreement)"
    )
    related_entities: list[RelatedEntity] | None = Field(
        default=None, description="Related entities"
    )


class PrintFormAttributes(CdekModel):
    """``attributes`` of a ``PRINT_FORM`` event (a print form is ready)."""

    type: str | None = Field(default=None, description="Form type: a waybill or a barcode")
    format: str | None = Field(default=None, description="Format: A4/A5/A6")
    url: str | None = Field(default=None, description="URL of the ready file")


class PrealertClosedAttributes(CdekModel):
    """``attributes`` of a ``PREALERT_CLOSED`` event."""

    prealert_uuid: str | None = Field(default=None, description="Prealert UUID")
    prealert_number: str | None = Field(default=None, description="Prealert number")
    date_closed: CdekDateTime | str | None = Field(default=None, description="Closing date")


class OfficeAvailabilityAttributes(CdekModel):
    """``attributes`` of an ``OFFICE_AVAILABILITY`` event."""

    office_code: str | None = Field(default=None, description="Office code")
    is_available: bool | None = Field(default=None, description="Whether the office is available")
    reason: str | None = Field(default=None, description="Reason for the availability change")


class OrderModifiedAttributes(CdekModel):
    """``attributes`` of an ``ORDER_MODIFIED`` event."""

    cdek_number: str | None = Field(default=None, description="CDEK order number")
    number: str | None = Field(
        default=None, description="Order number in the client information system"
    )
    modified_fields: list[str] | None = Field(default=None, description="Modified fields")


class DelivAgreementAttributes(CdekModel):
    """``attributes`` of a ``DELIV_AGREEMENT`` event (a delivery agreement)."""

    cdek_number: str | None = Field(default=None, description="CDEK order number")
    date_delivery_min: str | None = Field(default=None, description="New start of the interval")
    date_delivery_max: str | None = Field(default=None, description="New end of the interval")
    receiver_fio: str | None = Field(default=None, description="Full name of the recipient")


class DelivProblemAttributes(CdekModel):
    """``attributes`` of a ``DELIV_PROBLEM`` event (delivery problems)."""

    cdek_number: str | None = Field(default=None, description="CDEK order number")
    problem_code: str | None = Field(default=None, description="Problem code")
    problem_description: str | None = Field(default=None, description="Problem description")
    date_time: CdekDateTime | str | None = Field(default=None, description="Date of occurrence")


class CourierInfoAttributes(CdekModel):
    """``attributes`` of a ``COURIER_INFO`` event."""

    task_type: Literal["DELIVERY", "DEMAND"] | str | None = Field(
        default=None, description="DELIVERY — an order, DEMAND — an intake"
    )
    courier_fio: str | None = Field(default=None, description="Full name of the courier")
    courier_phone: str | None = Field(default=None, description="Courier phone")
    car_model: str | None = Field(default=None, description="Car brand")
    car_number: str | None = Field(default=None, description="Car registration number")


class DownloadPhotoAttributes(CdekModel):
    """``attributes`` of a ``DOWNLOAD_PHOTO`` event (document photos of orders)."""

    url: str | None = Field(default=None, description="URL of the photo archive")
    cdek_number: str | None = Field(default=None, description="CDEK order number")


#: Mapping "event type → attributes model".
#: The keys are the string values of WebhookType (duplicating the enum makes
#: no sense, and pydantic with ``use_enum_values`` stringifies them in-class).
_ATTRIBUTES_BY_TYPE: dict[str, type[CdekModel]] = {
    "ORDER_STATUS": OrderStatusAttributes,
    "PRINT_FORM": PrintFormAttributes,
    "PREALERT_CLOSED": PrealertClosedAttributes,
    "ACCOMPANYING_WAYBILL": CdekModel,
    "OFFICE_AVAILABILITY": OfficeAvailabilityAttributes,
    "ORDER_MODIFIED": OrderModifiedAttributes,
    "DELIV_AGREEMENT": DelivAgreementAttributes,
    "DELIV_PROBLEM": DelivProblemAttributes,
    "COURIER_INFO": CourierInfoAttributes,
    "DOWNLOAD_PHOTO": DownloadPhotoAttributes,
}


class WebhookEvent(CdekModel):
    """A CDEK webhook event.

    ``attributes`` is typed automatically by ``type``; if the type is unknown,
    it stays a dict and no data is lost.
    """

    type: str = Field(description="Event type (see WebhookType)")
    date_time: CdekDateTime | str | None = Field(
        default=None, description="Date and time of the event"
    )
    uuid: str | None = Field(default=None, description="UUID of the event source entity")
    attributes: Any = Field(default=None, description="Event attributes")

    @property
    def is_known_type(self) -> bool:
        """Return whether the event type is known to the library."""
        return self.type in _ATTRIBUTES_BY_TYPE

    def as_order_status(self) -> OrderStatusAttributes | None:
        """Coerce ``attributes`` to the status model (or ``None``)."""
        return _cast(self, OrderStatusAttributes)


def parse_event(payload: Any) -> WebhookEvent:
    """Parse the body of an incoming webhook.

    Args:
        payload: a dict or a JSON string from CDEK.

    Returns:
        :class:`WebhookEvent` with typed ``attributes`` if the type is known.

    Raises:
        UnknownEventError: the payload has none of the required event fields.

    Example:
        >>> event = parse_event({  # doctest: +SKIP
        ...     "type": "ORDER_STATUS",
        ...     "date_time": "2026-05-01T12:30:00+0300",
        ...     "uuid": "8dea00e3-9aab-4d8e-887c-ef2aaa546456",
        ...     "attributes": {"code": "DELIVERED", "cdek_number": "1234567890"},
        ... })

    """
    if isinstance(payload, str | bytes | bytearray):
        import json

        try:
            payload = json.loads(payload)
        except ValueError as exc:
            raise UnknownEventError(f"webhook payload is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or "type" not in payload:
        preview = str(payload)[:200]
        raise UnknownEventError(f"payload does not look like a CDEK webhook event: {preview}")

    try:
        event = WebhookEvent.model_validate(payload)
    except ValidationError as exc:
        raise UnknownEventError(f"invalid CDEK webhook event: {exc}") from exc

    model = _ATTRIBUTES_BY_TYPE.get(event.type)
    if model is not None and isinstance(event.attributes, dict):
        # an unknown/extended attributes structure — keep the dict
        with contextlib.suppress(ValidationError):
            event.attributes = model.model_validate(event.attributes)
    return event


AttributesT = TypeVar("AttributesT", bound=CdekModel)


def _cast(event: WebhookEvent, model: type[AttributesT]) -> AttributesT | None:
    """Coerce the event ``attributes`` to a concrete attributes model."""
    attributes = event.attributes
    if isinstance(attributes, model):
        return attributes
    if isinstance(attributes, dict):
        try:
            return model.model_validate(attributes)
        except ValidationError:
            return None
    return None
