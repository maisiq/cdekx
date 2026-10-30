"""Models of courier pickup requests (intakes): ``/v2/intakes``.

Verified against the apidoc.cdek.ru OpenAPI specification: ``IntakeDto``,
``IntakeInfoDto``, ``IntakeInfoResponseEntity``, ``IntakeStatusDto``,
``IntakeChangeStatusDto``, ``IntakeStatusPatchDto``,
``IntakeAvailableDaysRequestDto``/``ResponseDto``, ``IntakeContactDto``,
``IntakeLocationDto``.

API specifics:

* there is **no** list of intakes (``GET /v2/intakes``) — only fetching by UUID
  and fetching all intakes of an order (``GET /v2/orders/{orderUuid}/intakes``);
* there is no intake modification either — ``PATCH /v2/intakes`` changes the status;
* cargo pickup intakes are linked to an order through ``cdek_number``
  or ``order_uuid``.
"""

from __future__ import annotations

from pydantic import Field

from ..types import CdekDate, CdekDateTime
from .base import ApiWarning, CdekModel, ErrorInfo
from .common import Contact, Location

__all__ = [
    "Intake",
    "IntakeAdditionalStatusCode",
    "IntakeAvailableDays",
    "IntakeAvailableDaysLocation",
    "IntakeAvailableDaysRequest",
    "IntakeInfo",
    "IntakePackage",
    "IntakeStatus",
    "IntakeStatusChange",
    "IntakeStatusCode",
    "IntakeStatusPatch",
]


class IntakeStatusCode:
    """Intake status codes (``IntakeStatusPatchDto.code``)."""

    PROCESSING_REQUIRED = "PROCESSING_REQUIRED"
    """Processing is required."""

    CANCELLED = "CANCELLED"
    """The intake is cancelled."""


class IntakeAdditionalStatusCode:
    """Additional intake status codes (``IntakeStatusPatchDto.add_status``)."""

    CANCELLED_BY_CLIENT = "CANCELLED_BY_CLIENT"
    COURIER_DID_NOT_ARRIVE = "COURIER_DID_NOT_ARRIVE"


class Intake(CdekModel):
    """Registration of an intake (``POST /v2/intakes`` → ``IntakeDto``).

    ``intake_date``, ``intake_time_from`` and ``intake_time_to`` are required.
    The order is specified through ``cdek_number`` **or** ``order_uuid``; if
    neither is given, an intake for a consolidated cargo pickup is created
    (several orders from one address).
    """

    cdek_number: str | None = Field(
        default=None, description="CDEK order number (required if there is no order_uuid)"
    )
    order_uuid: str | None = Field(
        default=None,
        description="Order UUID in the CDEK system (required if there is no cdek_number)",
    )
    intake_date: str = Field(
        description="Date of waiting for the courier (at most +14 days, not today after 15:00)"
    )
    intake_time_from: str = Field(
        description="Start of waiting for the courier, not earlier than 9:00 local time"
    )
    intake_time_to: str = Field(
        description="End of waiting for the courier, not later than 22:00 local time"
    )
    lunch_time_from: str | None = Field(
        default=None, description="Start of the lunch break (inside the waiting interval)"
    )
    lunch_time_to: str | None = Field(default=None, description="End of the lunch break")
    name: str | None = Field(
        default=None, description="Cargo description (needed if no order number is given)"
    )
    weight: int | None = Field(default=None, description="Total weight, grams")
    length: int | None = Field(default=None, description="Length, cm")
    width: int | None = Field(default=None, description="Width, cm")
    height: int | None = Field(default=None, description="Height, cm")
    comment: str | None = Field(default=None, description="Comment for the courier")
    courier_power_of_attorney: bool | None = Field(
        default=None, description="The courier needs a power of attorney (false by default)"
    )
    courier_identity_card: bool | None = Field(
        default=None, description="The courier needs an identity document"
    )
    sender: Contact | None = Field(default=None, description="Sender")
    from_location: Location | None = Field(default=None, description="Cargo pickup address")
    need_call: bool | None = Field(
        default=None, description="A confirmation call to the sender is required"
    )


class IntakeStatus(CdekModel):
    """Intake status (``IntakeStatusDto``)."""

    code: str = Field(description="Status code")
    name: str = Field(description="Status name")
    date_time: CdekDateTime | str = Field(description="Date and time when the status was set")


class IntakePackage(CdekModel):
    """Package of an intake (``IntakePackageDto``).

    Differs from an order package: there is no ``number``, ``items`` or
    ``barcode`` here — only ``package_id`` and the weight/size parameters.
    """

    package_id: str | None = Field(
        default=None, description="Unique package number in the CDEK information system"
    )
    weight: int | None = Field(default=None, description="Total weight, grams")
    length: int | None = Field(default=None, description="Length, cm")
    width: int | None = Field(default=None, description="Width, cm")
    height: int | None = Field(default=None, description="Height, cm")


class IntakeInfo(CdekModel):
    """Intake information (``IntakeInfoResponseEntity``).

    The same schema is used in two responses:
    ``GET /v2/intakes/{uuid}`` (as the ``entity`` of the ``IntakeInfoDto``
    envelope) and ``GET /v2/orders/{orderUuid}/intakes`` (as a "bare" array).
    """

    uuid: str = Field(description="Intake identifier in the CDEK information system")
    cdek_number: str | None = Field(default=None, description="CDEK order number")
    order_uuid: str | None = Field(default=None, description="Order UUID")
    intake_date: str = Field(description="Date of waiting for the courier")
    intake_number: str | None = Field(default=None, description="Intake number in the CDEK system")
    intake_time_from: str = Field(description="Start of waiting for the courier")
    intake_time_to: str = Field(description="End of waiting for the courier")
    lunch_time_from: str | None = Field(default=None, description="Start of the lunch break")
    lunch_time_to: str | None = Field(default=None, description="End of the lunch break")
    name: str | None = Field(default=None, description="Cargo description")
    weight: int | None = Field(default=None, description="Total weight, grams")
    length: int | None = Field(default=None, description="Length, cm")
    width: int | None = Field(default=None, description="Width, cm")
    height: int | None = Field(default=None, description="Height, cm")
    comment: str | None = Field(default=None, description="Comment for the courier")
    courier_power_of_attorney: bool | None = Field(
        default=None, description="A power of attorney is required"
    )
    courier_identity_card: bool | None = Field(
        default=None, description="The courier needs a document"
    )
    sender: Contact | None = Field(default=None, description="Sender")
    from_location: Location = Field(description="Cargo pickup address")
    to_location: Location | None = Field(default=None, description="Delivery address")
    need_call: bool | None = Field(
        default=None, description="A confirmation call to the sender is required"
    )
    statuses: list[IntakeStatus] = Field(
        default_factory=list, description="Intake statuses (by date)"
    )
    packages: list[IntakePackage] | None = Field(
        default=None, description="Information about the intake packages"
    )

    @property
    def current_status(self) -> IntakeStatus | None:
        """Return the last status of the intake."""
        return self.statuses[-1] if self.statuses else None


class IntakeStatusPatch(CdekModel):
    """New status of the intake (``IntakeStatusPatchDto``)."""

    code: str = Field(description="Status code, for example PROCESSING_REQUIRED or CANCELLED")
    add_status: str = Field(description="Additional status code, for example CANCELLED_BY_CLIENT")


class IntakeStatusChange(CdekModel):
    """Intake status change (``PATCH /v2/intakes`` → ``IntakeChangeStatusDto``)."""

    uuid: str = Field(description="Intake identifier in the CDEK information system")
    status: IntakeStatusPatch = Field(description="New intake status")


class IntakeAvailableDaysLocation(CdekModel):
    """Location for the available courier dates request (``IntakeAvailableDaysLocationDto``)."""

    code: int | None = Field(default=None, description="CDEK settlement code")
    city: str | None = Field(default=None, description="Settlement name")
    fias_guid: str | None = Field(default=None, description="FIAS identifier")
    country_code: str | None = Field(default=None, description="ISO 3166-1 alpha-2 country code")
    region: str | None = Field(default=None, description="Region name")
    region_code: int | None = Field(default=None, description="CDEK region code")
    sub_region: str | None = Field(default=None, description="Region district")
    longitude: float | None = Field(default=None, description="Longitude")
    latitude: float | None = Field(default=None, description="Latitude")
    postal_code: str | None = Field(default=None, description="Postal code")
    address: str | None = Field(
        default=None, description="Address string (required if no code is given)"
    )


class IntakeAvailableDaysRequest(CdekModel):
    """Request of the available courier call dates (``POST /v2/intakes/availableDays``)."""

    from_location: IntakeAvailableDaysLocation = Field(description="Cargo pickup location")
    date: str | None = Field(
        default=None, description="Up to which date (inclusive) to fetch the available dates"
    )


class IntakeAvailableDays(CdekModel):
    """Response with the available courier call dates (``IntakeAvailableDaysResponseDto``).

    The response shape is "list + errors", not the ``{entity, requests}``
    envelope: the same style as :class:`cdekx.models.ListResponse`.

    Note:
        If pickup is available on all days of the requested range, the API
        returns ``all_days = true`` and does **not** return the ``date`` list.

    """

    date: list[CdekDate] | None = Field(
        default=None, description="Dates available for a courier pickup (``YYYY-MM-DD``)"
    )
    all_days: bool | None = Field(
        default=None, description='Flag "pickup is available on all days"'
    )
    errors: list[ErrorInfo] | None = Field(default=None, description="Errors")
    warnings: list[ApiWarning] | None = Field(default=None, description="Warnings")

    @property
    def has_errors(self) -> bool:
        """Return whether the response has errors (the dates were not fetched)."""
        return bool(self.errors)
