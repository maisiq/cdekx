"""Models of offices and pickup points: ``/v2/deliverypoints``.

Verified against the apidoc.cdek.ru OpenAPI specification: ``OfficeDto``,
``OfficeLocationDto``, ``OfficeWorkTimeDto``, ``OfficeWorkTimeExceptionDto``,
``OfficeCellDimensionsDto``, ``OfficeImageDto``.

The response of the method is an **array of ``OfficeDto`` objects** (without the
``entity`` envelope).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import CdekModel, ErrorInfo, QueryModel
from .common import Phone

__all__ = [
    "ApiWarningShort",
    "DeliveryPoint",
    "DeliveryPointFilter",
    "DeliveryPointPolygon",
    "DeliveryPointPolygonFilter",
    "OfficeCellDimensions",
    "OfficeImage",
    "OfficeLocation",
    "OfficeWorkTime",
    "OfficeWorkTimeException",
]


class OfficeLocation(CdekModel):
    """Address and coordinates of an office (``OfficeLocationDto``)."""

    country_code: str = Field(description="ISO 3166-1 alpha-2 country code")
    region_code: int = Field(description="CDEK region code")
    region: str = Field(description="Region name")
    city_code: int = Field(description="CDEK settlement code")
    city: str = Field(description="Settlement name")
    fias_guid: str | None = Field(default=None, description="FIAS identifier")
    postal_code: str | None = Field(default=None, description="Postal code")
    longitude: float = Field(description="Longitude")
    latitude: float = Field(description="Latitude")
    address: str = Field(description="Address string")
    address_full: str = Field(description="Full address: country, region, city, etc.")
    city_uuid: str | None = Field(
        default=None, description="City identifier in the CDEK information system"
    )


class OfficeWorkTime(CdekModel):
    """A day of the office work schedule (``OfficeWorkTimeDto``).

    Days are numbered from one: Monday = 1, Sunday = 7.
    """

    day: int = Field(description="Ordinal number of the day: Monday = 1 … Sunday = 7")
    time: str = Field(description='Working period, for example "09:00-18:00" (empty — closed)')


class OfficeWorkTimeException(CdekModel):
    """An exception in the work schedule (``OfficeWorkTimeExceptionDto``)."""

    date_start: str = Field(description="Start date of the exception")
    date_end: str = Field(description="End date of the exception")
    time_start: str | None = Field(default=None, description="Start of work time on that date")
    time_end: str | None = Field(default=None, description="End of work time")
    is_working: bool = Field(description="Flag of a working/non-working day")


class OfficeCellDimensions(CdekModel):
    """Parcel locker cell size (``OfficeCellDimensionsDto``)."""

    width: int = Field(description="Width, cm")
    height: int = Field(description="Height, cm")
    depth: int = Field(description="Depth, cm")


class OfficeImage(CdekModel):
    """Photo of an office (``OfficeImageDto``)."""

    number: int | None = Field(default=None, description="Ordinal number of the photo")
    url: str = Field(description="Photo link")


class ApiWarningShort(CdekModel):
    """A warning in the office response."""

    code: str | None = Field(default=None, description="Warning code")
    message: str | None = Field(default=None, description="Text")


class DeliveryPoint(CdekModel):
    """A CDEK office / pickup point / parcel locker (``OfficeDto``).

    Fields required by the specification: ``code``, ``uuid``, ``work_time``,
    ``phones``, ``type``, ``owner_code``, ``take_only``, ``is_handout``,
    ``is_reception``, ``is_dressing_room``, ``have_cashless``, ``have_cash``,
    ``have_fast_payment_system``, ``allowed_cod``, ``work_time_list``,
    ``status``, ``location``.
    """

    code: str = Field(description="Pickup point code")
    name: str | None = Field(default=None, max_length=255, description="Localised office name")
    uuid: str = Field(description="Office identifier in the CDEK information system")
    address_comment: str | None = Field(default=None, description="Location description")
    nearest_station: str | None = Field(default=None, description="Nearest transport station/stop")
    nearest_metro_station: str | None = Field(default=None, description="Nearest metro station")
    work_time: str = Field(description='Work schedule as a string, e.g. "Mon-Fri 9-18, Sat 9-16"')
    phones: list[Phone] = Field(default_factory=list, description="List of phones")
    email: str | None = Field(default=None, description="Email address")
    note: str | None = Field(default=None, description="Note about the pickup point")
    type: str = Field(description="Type: PVZ — a CDEK warehouse, POSTAMAT — a parcel locker")
    owner_code: str = Field(description="Ownership: CDEK — own, otherwise — a partner")
    take_only: bool = Field(description="Handout only (no reception)")
    is_handout: bool = Field(description="Is a handout point")
    is_reception: bool = Field(description="Is a reception point")
    is_dressing_room: bool = Field(description="Has a dressing room")
    is_marketplace: bool | None = Field(
        default=None, description='Office for "To the marketplace" delivery'
    )
    is_ltl: bool | None = Field(default=None, description="Works with consolidated cargo (LTL)")
    have_cashless: bool = Field(description="Has cashless payment")
    have_cash: bool = Field(description="Accepts cash")
    have_fast_payment_system: bool = Field(
        description="Accepts payment via the faster payments system"
    )
    allowed_cod: bool = Field(description="Cash on delivery is allowed")
    site: str | None = Field(default=None, description="Link to the office on the CDEK website")
    office_image_list: list[OfficeImage] | None = Field(default=None, description="Office photos")
    work_time_list: list[OfficeWorkTime] = Field(
        default_factory=list, description="Work schedule for the week"
    )
    work_time_exception_list: list[OfficeWorkTimeException] | None = Field(
        default=None, description="Exceptions in the work schedule"
    )
    weight_min: float | None = Field(default=None, description="Minimum accepted weight, kg")
    weight_max: float | None = Field(default=None, description="Maximum accepted weight, kg")
    dimensions: list[OfficeCellDimensions] | None = Field(
        default=None, description="Maximum cell dimensions (parcel lockers only)"
    )
    status: str = Field(description="Office status: ACTIVE, OPENED, CLOSED, etc.")
    errors: list[ErrorInfo] | None = Field(default=None, description="Error list")
    warnings: list[ApiWarningShort] | None = Field(default=None, description="Warnings")
    location: OfficeLocation = Field(description="Address and coordinates of the office")
    distance: float | None = Field(default=None, description="Distance to the search point, m")
    ltl_acceptance_partners: bool | None = Field(
        default=None, description="Accepts LTL orders delivered by partners"
    )
    ltl_issuance_partners: bool | None = Field(
        default=None, description="Hands out LTL orders delivered by partners"
    )
    fulfillment: bool | None = Field(default=None, description='Works with "Fulfillment. Inbound"')
    length_max: int | None = Field(default=None, description="Max. cargo place length, cm")
    width_max: int | None = Field(default=None, description="Max. cargo place width, cm")
    height_max: int | None = Field(default=None, description="Max. cargo place height, cm")

    @property
    def address(self) -> str:
        """Return the office address string."""
        return self.location.address

    @property
    def city_code(self) -> int:
        """Return the office city code."""
        return self.location.city_code


class DeliveryPointFilter(QueryModel):
    """Filter of ``GET /v2/deliverypoints``.

    CDEK understands boolean parameters as ``1``/``true`` or ``0``/``false`` —
    the HTTP layer converts ``bool`` to ``"true"``/``"false"`` automatically.

    To search for the nearest offices use ``/v2/deliverypoints/byPolygons``
    (a separate method with its own filter :class:`DeliveryPointPolygonFilter`),
    not the coordinates in the filter.
    """

    code: str | None = Field(default=None, description="Pickup point code")
    type: str | None = Field(default=None, description="POSTAMAT, PVZ or ALL")
    postal_code: str | None = Field(default=None, description="City postal code")
    city_code: int | None = Field(default=None, description="CDEK settlement code")
    country_code: str | None = Field(default=None, description="ISO 3166-1 alpha-2 country code")
    region_code: int | None = Field(default=None, description="CDEK region code")
    have_cashless: bool | None = Field(default=None, description="Has a payment terminal")
    have_cash: bool | None = Field(default=None, description="Accepts cash")
    allowed_cod: bool | None = Field(default=None, description="Cash on delivery is allowed")
    is_dressing_room: bool | None = Field(default=None, description="Has a dressing room")
    weight_max: float | None = Field(default=None, description="Max. accepted weight, kg")
    weight_min: float | None = Field(default=None, description="Min. accepted weight, kg")
    length: int | None = Field(
        default=None, description="Cargo place length, cm (a capacity filter)"
    )
    width: int | None = Field(default=None, description="Cargo place width, cm")
    height: int | None = Field(default=None, description="Cargo place height, cm")
    lang: str | None = Field(default=None, description="Office localisation")
    take_only: bool | None = Field(default=None, description="Handout point only")
    is_handout: bool | None = Field(default=None, description="Is a handout point")
    is_reception: bool | None = Field(default=None, description="Accepts orders")
    is_marketplace: bool | None = Field(default=None, description='"To the marketplace" delivery')
    is_ltl: bool | None = Field(default=None, description="Works with LTL")
    ltl_acceptance_partners: bool | None = Field(default=None, description="Partner LTL reception")
    ltl_issuance_partners: bool | None = Field(default=None, description="Partner LTL handout")
    fulfillment: bool | None = Field(default=None, description="Fulfillment zone")
    fias_guid: str | None = Field(default=None, description="FIAS city code")
    size: int | None = Field(default=None, description="Page size")
    page: int | None = Field(default=None, description="Page number")


class DeliveryPointPolygonFilter(QueryModel):
    """Filter of ``GET /v2/deliverypoints/byPolygons``.

    The method supports **fewer** parameters than the office list: only type,
    city, payment methods, dressing room, weight and localisation. It has no
    pagination (``size``/``page``) — all offices of the rectangle are returned.
    """

    type: str | None = Field(default=None, description="POSTAMAT, PVZ or ALL")
    city_uuid: str | None = Field(
        default=None, description="City identifier in the CDEK information system"
    )
    have_cashless: bool | None = Field(default=None, description="Has a payment terminal")
    have_cash: bool | None = Field(default=None, description="Accepts cash")
    allowed_cod: bool | None = Field(default=None, description="Cash on delivery is allowed")
    is_dressing_room: bool | None = Field(default=None, description="Has a dressing room")
    weight_max: int | None = Field(
        default=None,
        ge=0,
        description="Max. weight in kg the office can accept "
        "(>0 — offices accepting this weight; 0 — zero-weight offices are not returned)",
    )
    weight_min: int | None = Field(
        default=None,
        ge=0,
        description="Min. weight in kg the office accepts "
        "(offices with a minimum weight up to the given value are returned)",
    )
    lang: str | None = Field(default=None, description="Office localisation (rus by default)")


class DeliveryPointPolygon(CdekModel):
    """A coordinate rectangle for ``/v2/deliverypoints/byPolygons``."""

    lat_min: float | None = Field(default=None, description="Minimum latitude")
    lat_max: float | None = Field(default=None, description="Maximum latitude")
    long_min: float | None = Field(default=None, description="Minimum longitude")
    long_max: float | None = Field(default=None, description="Maximum longitude")

    def to_query(self) -> dict[str, Any]:
        """Serialise into query parameters, dropping empty ones."""
        return self.to_api(exclude_none=True)
