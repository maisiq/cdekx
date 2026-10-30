"""Models of the "misc" API sections: receipts, passports, registries, photos, prealerts.

Reverse availability checks and international order restrictions are modelled
here too. Verified against the apidoc.cdek.ru OpenAPI specification (section
``api_v2_integration``): ``CheckResponseDto``/``CheckInfoDto``,
``PassportResponseDto``/``PassportOrderDto``/``PassportDto``,
``RegistriesResponseDto``/``RegistryDto``/``RegistryOrderDto``,
``PhotoRequestDto``/``PhotoOrderDto``/``PhotoResponseDto``/``PhotoReadyOrderDto``,
``RegisterPrealertRequestDto``/``RegisterPrealertResponseDto``,
``GetPrealertResponseDto`` (+ the nested ``PrealertDto``/``OrderDto``/``PackageInfoDto``),
``ReverseValidateRequestDto``,
``RestrictionHintsRequestDto``/``RestrictionHintsResponseDto``.

Two CDEK response shapes
------------------------

Most methods of this section answer **not** with the
``{entity, requests, related_entities}`` envelope but with a "list with errors"::

    {"errors": [...], "warnings": [...], "check_info": [...]}

Therefore the responses inherit :class:`cdekx.models.ListResponse`: check
:attr:`~cdekx.models.ListResponse.has_errors`, because HTTP 200 does not
guarantee that the body has no errors.

Exceptions:

* ``POST /v2/prealert`` (HTTP 202) and ``GET /v2/prealert/{uuid}`` — the usual
  envelope (:class:`cdekx.models.ResponseEnvelope`);
* ``POST /v2/reverse/availability`` — returns an **empty body** with code 200
  when reverse is available; unavailability arrives as HTTP 400 with an error
  description, i.e. as an :class:`cdekx.exceptions.ApiError` exception;
* ``GET /v2/photoDocument/{uuid}`` — a binary ZIP archive.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, StringConstraints, field_validator

from ..types import CdekDate, CdekDateTime, CdekDateTimeOut
from ..types.enums import (
    ContragentType,
    HintReasonCode,
    HintStatusCode,
    PassportClient,
    PhotoTaskStatus,
    PrealertPackageStatus,
    TariffCode,
)
from .base import CdekModel, ListResponse
from .common import CdekNumber, Location, Phone, coerce_phones
from .orders import PaymentInfo

#: Value of the ``client`` query parameter of ``GET /v2/passport``:
#: an element of :class:`cdekx.types.enums.PassportClient` or just a string
#: (the CDEK directory may be extended).
PassportClientLike = PassportClient | str

__all__ = [
    "CheckInfo",
    "CheckResponse",
    "HintReason",
    "HintStatus",
    "ItemHint",
    "PackageHint",
    "Passport",
    "PassportClientLike",
    "PassportOrder",
    "PassportResponse",
    "PhotoOrder",
    "PhotoReadyOrder",
    "PhotoRequest",
    "PhotoResponse",
    "Prealert",
    "PrealertCreate",
    "PrealertOrder",
    "PrealertOrderInfo",
    "PrealertPackageInfo",
    "RegistriesResponse",
    "Registry",
    "RegistryOrder",
    "RestrictionHintsResponse",
    "RestrictionItem",
    "RestrictionPackage",
    "RestrictionRequest",
    "ReverseContragent",
    "ReverseLocation",
    "ReverseValidateRequest",
]

#: Codes in this section arrive as strings of arbitrary length (no ``maxLength`` in the schema).
Code = Annotated[str, StringConstraints(max_length=255)]


# --- receipts (GET /v2/check) ------------------------------------------------


class CheckInfo(CdekModel):
    """A fiscal receipt (``CheckInfoDto``)."""

    order_uuid: str = Field(description="Identifier of the order the receipt was generated for")
    cdek_number: CdekNumber = Field(description="Number of the order the receipt was generated for")
    date: CdekDateTime | str = Field(description="Date of receipt creation in UTC")
    fiscal_storage_number: str = Field(
        default="", max_length=255, description="Fiscal storage device number"
    )
    document_number: str = Field(
        default="", max_length=255, description="Ordinal number of the fiscal document"
    )
    fiscal_sign: int = Field(description="Fiscal attribute of the document")
    type: str = Field(
        description="Receipt type: CASH_RECEIPT_IN (income) or CASH_RECEIPT_REFUND (refund)"
    )
    payment_info: list[PaymentInfo] = Field(
        default_factory=list, description="Information about the receipt amount"
    )
    shift_no: int | None = Field(default=None, description="Cash register shift number")

    @property
    def total(self) -> float:
        """Receipt amount (the sum of all payment methods)."""
        return round(sum(p.sum or 0.0 for p in self.payment_info), 2)


class CheckResponse(ListResponse):
    """Response of ``GET /v2/check`` (``CheckResponseDto``).

    Note:
        The list is called ``check_info``, not ``entities``: CDEK has its own
        field name in this method.

    """

    check_info: list[CheckInfo] | None = Field(default=None, description="Receipt list")

    @property
    def checks(self) -> list[CheckInfo]:
        """Return the receipts from ``check_info`` (an empty list if there are none)."""
        return self.check_info or []


# --- passport data (GET /v2/passport) ----------------------------------------


class Passport(CdekModel):
    """State of the passport data (``PassportDto``).

    The method does **not** return the passport data itself — only a flag that
    the requirements are satisfied. It answers the question "can an
    international order be created".
    """

    client: str = Field(
        description="The client the information is printed for: SENDER, RECEIVER or ALL"
    )
    passport_requirements_satisfied: bool = Field(
        description="True — data is collected or not required; false — required and not collected"
    )


class PassportOrder(CdekModel):
    """Passport data in the context of an order (``PassportOrderDto``)."""

    order_uuid: str = Field(description="Order UUID")
    cdek_number: CdekNumber = Field(description="CDEK order number")
    passport: Passport = Field(description="Information about the presence of passport data")

    @property
    def ok(self) -> bool:
        """Return whether the passport data requirements are satisfied."""
        return self.passport.passport_requirements_satisfied


class PassportResponse(ListResponse):
    """Response of ``GET /v2/passport`` (``PassportResponseDto``)."""

    orders: list[PassportOrder] | None = Field(
        default=None, description="List of orders with passport data information"
    )

    @property
    def unsatisfied(self) -> list[PassportOrder]:
        """Return the orders that require passport data but do not have it."""
        return [o for o in (self.orders or []) if not o.ok]


# --- cash-on-delivery registries (GET /v2/registries) ------------------------


class RegistryOrder(CdekModel):
    """A row of the cash-on-delivery registry (``RegistryOrderDto``).

    All amounts are in the settlement currency.
    """

    cdek_number: CdekNumber = Field(description="CDEK order number")
    transfer_sum: float = Field(description="Amount to be credited")
    payment_sum: float = Field(description="Cash-on-delivery amount taken from the recipient")
    total_sum_without_agent: float = Field(description="Total order cost without the agency fee")
    agent_commission_sum: float = Field(description="Agency fee for the cash-on-delivery transfer")
    basis_type: str | None = Field(
        default=None,
        description="Type of the assignment: ORDER (an order) or SAS (fulfillment services)",
    )


class Registry(CdekModel):
    """A cash-on-delivery registry (``RegistryDto``)."""

    registry_number: int = Field(
        description="Number of the cash-on-delivery registry (int64 in the API)"
    )
    sum: float = Field(description="Registry amount in the settlement currency")
    orders: list[RegistryOrder] = Field(default_factory=list, description="Registry orders")
    payment_date: CdekDate | str | None = Field(
        default=None, description="Actual date of the registry payment"
    )
    payment_order_number: str | None = Field(
        default=None,
        description="Number of the payment order. If the field is missing or empty — "
        "ask your CDEK manager for the reason",
    )
    date_created: CdekDateTime | str | None = Field(
        default=None, description="Date of registry creation"
    )


class RegistriesResponse(ListResponse):
    """Response of ``GET /v2/registries`` (``RegistriesResponseDto``).

    Only registries whose cash-on-delivery payment has **already been
    transferred** are returned.
    """

    registries: list[Registry] | None = Field(
        default=None, description="List of paid cash-on-delivery registries"
    )

    @property
    def total(self) -> float:
        """Return the total amount of all registries in the response."""
        return round(sum(r.sum for r in (self.registries or [])), 2)


# --- document photos (POST /v2/photoDocument) --------------------------------


class PhotoOrder(CdekModel):
    """An order in the document photo request (``PhotoOrderDto``).

    Note:
        In the **request** schemas ``cdek_number`` is declared as ``int64``, so
        it is not normalised to a string here: whatever was passed
        (``1234567890`` or ``"1234567890"``) goes to the API. CDEK accepts both.

    """

    order_uuid: str | None = Field(
        default=None, description="Order UUID (required if there is no cdek_number)"
    )
    cdek_number: str | int | None = Field(
        default=None, description="CDEK order number (required if there is no order_uuid)"
    )


class PhotoRequest(CdekModel):
    """Request of orders with ready document photos (``PhotoRequestDto``).

    Either a period (``period_begin``/``period_end``), or a list of orders, or
    both are given.

    Note:
        The date is passed **strictly** in the CDEK format
        ``yyyy-MM-dd'T'HH:mm:ssZ``, for example ``2026-03-24T14:15:22+0000``.
        Neither the ``Z`` suffix nor the ISO offset ``+03:00`` is accepted: the
        API answers ``v2_invalid_value_type: Invalid value type in
        [period_begin] field`` (verified on ``api.edu.cdek.ru``).
        :data:`cdekx.types.CdekDateTimeOut` serialises ``datetime`` into the
        required format automatically.

        The method does not accept an empty body (``v2_field_is_empty:
        [orders]``): pass ``orders`` and/or a period.

    """

    period_begin: CdekDateTimeOut | str | None = Field(
        default=None, description="Start of the search period"
    )
    period_end: CdekDateTimeOut | str | None = Field(
        default=None, description="End of the search period"
    )
    orders: list[PhotoOrder] | None = Field(default=None, description="Order list")


class PhotoReadyOrder(CdekModel):
    """An order with a ready photo archive (``PhotoReadyOrderDto``)."""

    order_uuid: str | None = Field(
        default=None, description="Order UUID in the CDEK information system"
    )
    cdek_number: CdekNumber | None = Field(default=None, description="CDEK order number")
    link: str | None = Field(
        default=None,
        description="A link like https://api.cdek.ru/v2/photoDocument/{uuid} — "
        "download the archive with the misc.photo_archive() method",
    )
    status: str | None = Field(
        default=None,
        description="Status of the photo task: CREATED, READY_FOR_EXECUTION, "
        "IN_PROGRESS, DONE, SENT, DELIVERED, NOT_DELIVERED, ERROR",
    )
    create_date: CdekDateTime | str | None = Field(
        default=None, description="Date of task creation"
    )

    @property
    def archive_uuid(self) -> str | None:
        """Return the archive UUID from the ``link`` field (the last path segment)."""
        if not self.link:
            return None
        return self.link.rstrip("/").rsplit("/", 1)[-1] or None

    @property
    def is_ready(self) -> bool:
        """Return whether the archive is ready for download (the task is ``DONE``)."""
        return self.status == PhotoTaskStatus.DONE.value


class PhotoResponse(ListResponse):
    """Response of ``POST /v2/photoDocument`` (``PhotoResponseDto``)."""

    orders: list[PhotoReadyOrder] | None = Field(
        default=None, description="List of orders ready for download"
    )

    @property
    def ready(self) -> list[PhotoReadyOrder]:
        """Return only the orders with a ready archive (``status == DONE``)."""
        return [o for o in (self.orders or []) if o.is_ready]


# --- prealerts (POST/GET /v2/prealert) ---------------------------------------


class PrealertOrder(CdekModel):
    """An order in the prealert registration request (``RegisterPrealertRequestDtoOrderDto``).

    ``cdek_number`` in the request schema is ``int64``: the value is not
    normalised to a string and goes to the API exactly as it was passed.
    """

    order_uuid: str | None = Field(
        default=None, description="Order UUID (required if there is no cdek_number)"
    )
    cdek_number: str | int | None = Field(
        default=None, description="CDEK order number (required if there is no order_uuid)"
    )
    im_number: str | None = Field(
        default=None, max_length=40, description="Order number in the client information system"
    )


class PrealertCreate(CdekModel):
    """Prealert registration (``POST /v2/prealert`` → ``RegisterPrealertRequestDto``).

    A prealert describes handing a group of orders over to a specific office on
    a specific date — it is required for international shipments.

    Note:
        ``planned_date`` must not be earlier than the value set in the terms of
        the prealert processing contract. The response arrives with code
        **202**: the prealert is created asynchronously, look at ``requests``
        for the state.

    """

    planned_date: CdekDateTimeOut | str = Field(
        description="Planned date of handing the orders over to CDEK"
    )
    shipment_point: str = Field(description="Code of the office the orders are handed over to")
    orders: list[PrealertOrder] = Field(description="List of the orders planned for handover")


class PrealertPackageInfo(CdekModel):
    """Package of a prealert (``GetPrealertResponseDtoPackageInfoDto``).

    Appears after the prealert is closed and shows the discrepancies: which
    packages were accepted, which were not, which were deleted.
    """

    package_id: str = Field(description="Unique package number in the CDEK information system")
    number: str = Field(
        max_length=20, description="Package number in the client information system"
    )
    status: str = Field(description="Package status: ACCEPTED, NOT_ACCEPTED, DELETED")

    @property
    def is_accepted(self) -> bool:
        """Return whether the package was accepted by CDEK."""
        return self.status == PrealertPackageStatus.ACCEPTED.value


class PrealertOrderInfo(CdekModel):
    """An order of a prealert in the response (``GetPrealertResponseDtoOrderDto``).

    Warning:
        In the schema ``order_uuid`` and ``cdek_number`` are marked as required,
        but the live API returns only what was passed at registration: a
        prealert created by ``cdek_number`` has **no** ``order_uuid`` field in
        the response (verified on ``api.edu.cdek.ru``).
        Therefore both fields are optional — otherwise parsing the response
        would fail with :class:`cdekx.endpoints.ResponseParseError`.

    """

    order_uuid: str | None = Field(
        default=None, description="Order UUID in the CDEK information system"
    )
    cdek_number: CdekNumber | None = Field(default=None, description="CDEK order number")
    im_number: str | None = Field(
        default=None, description="Order number in the client information system"
    )
    packages: list[PrealertPackageInfo] | None = Field(
        default=None,
        description="Packages the discrepancy information was received for "
        "(appears after the prealert is closed)",
    )

    @property
    def discrepancies(self) -> list[PrealertPackageInfo]:
        """Return the packages CDEK did not accept (``NOT_ACCEPTED``/``DELETED``)."""
        return [p for p in (self.packages or []) if not p.is_accepted]


class Prealert(CdekModel):
    """A prealert in the response (``GetPrealertResponseDtoPrealertDto``).

    Warning:
        Per the schema ``uuid``, ``planned_date``, ``shipment_point`` and
        ``orders`` are required, but the live API in ``GET /v2/prealert/{uuid}``
        does **not return the prealert ``uuid``** (verified on
        ``api.edu.cdek.ru``): the identifier is known only from the request or
        from the creation response. Hence ``uuid`` is optional — keep it on your
        side.

    """

    uuid: str | None = Field(
        default=None,
        description="Prealert identifier in the CDEK system (the API does not return it)",
    )
    planned_date: CdekDateTime | str = Field(
        description="Planned date of handing the orders over to CDEK"
    )
    shipment_point: str = Field(description="Code of the office the handover was planned for")
    orders: list[PrealertOrderInfo] = Field(default_factory=list, description="Prealert orders")
    prealert_number: str | None = Field(
        default=None, description="Prealert number in the CDEK information system"
    )
    closed_date: CdekDateTime | str | None = Field(
        default=None, description="Date the prealert was closed (appears after closing)"
    )
    fact_shipment_point: str | None = Field(
        default=None,
        description="The office the orders were actually handed to (appears after closing)",
    )

    @property
    def is_closed(self) -> bool:
        """Return whether the prealert is closed (``closed_date`` is present)."""
        return self.closed_date is not None

    @property
    def discrepancies(self) -> list[PrealertPackageInfo]:
        """Return all non-accepted packages of all prealert orders."""
        result: list[PrealertPackageInfo] = []
        for order in self.orders:
            result.extend(order.discrepancies)
        return result


# --- international order restrictions ----------------------------------------
# POST /v2/international/package/restrictions


class RestrictionItem(CdekModel):
    """An item in the restrictions request (``RestrictionItemRequestDto``).

    Warning:
        In the OpenAPI specification the field is declared as ``itemId``
        (camelCase, ``writeOnly``), but the **live API expects ``item_id``**:
        for ``itemId`` it answers ``v2_field_is_empty:
        [packages[0].items[0].item_id] is empty`` (verified on
        ``api.edu.cdek.ru``). The model sends ``item_id`` — the same as in the
        response (``ItemHintDto.item_id``).

    """

    name: str | None = Field(
        default=None,
        description='Goods name. Must be specific: "Henry men\'s jeans, size M", not "item 1"',
    )
    amount: int | None = Field(default=None, description="Number of units (from 1 to 999 per item)")
    item_id: str | None = Field(
        default=None,
        description="Goods identifier. Effectively required if items is filled",
    )
    feacn_code: str | None = Field(default=None, description="FEACN code")


class RestrictionPackage(CdekModel):
    """A cargo place in the restrictions request (``RestrictionPackageRequestDto``).

    Note:
        In the schema all fields are optional, but the live API answers
        ``v2_field_is_empty: [packages[0].package_id] is empty`` if
        ``package_id`` is not passed, and the same if ``items`` is not passed.
        Effectively ``package_id``, ``items`` and the weight/size parameters are
        required. The model repeats the schema (the fields are optional) so that
        the exception shows the full CDEK error text.

    """

    weight: int | None = Field(default=None, description="Total weight, grams")
    length: int | None = Field(default=None, description="Length, cm")
    width: int | None = Field(default=None, description="Width, cm")
    height: int | None = Field(default=None, description="Height, cm")
    items: list[RestrictionItem] | None = Field(
        default=None,
        description='Items. Required for "online shop" orders: '
        "at most 126 unique items, from 1 to 999999 goods in total",
    )
    package_id: str | None = Field(
        default=None, description="Unique package number in the CDEK information system"
    )


class RestrictionRequest(CdekModel):
    """Request of restrictions for an international direction (``RestrictionHintsRequestDto``).

    The direction is given as in the calculator:
    ``from_location``/``to_location`` or office codes. ``tariff_code`` is
    required for a tariff calculation.

    Note:
        Locations here are described by the ``LocationDto1`` schema — the same
        as in the calculator, so :class:`cdekx.models.Location` is used.

    """

    tariff_code: TariffCode | int | None = Field(default=None, description="Tariff code")
    from_location: Location | None = Field(default=None, description="Origin location")
    to_location: Location | None = Field(default=None, description="Destination location")
    packages: list[RestrictionPackage] | None = Field(
        default=None,
        description="Information about the places (packages). Effectively required: "
        "without it the API answers v2_field_is_empty",
    )


class HintReason(CdekModel):
    """Reason for a restriction (``HintReasonDto``)."""

    code: str | None = Field(
        default=None,
        description="FEACN_RESTRICTION — a restriction on goods by FEACN code; "
        "GENERAL_RESTRICTION — a general restriction on the cargo place",
    )
    name: str | None = Field(default=None, description="Reason name")

    @property
    def is_feacn(self) -> bool:
        """Return whether the restriction is caused by the goods FEACN code."""
        return self.code == HintReasonCode.FEACN_RESTRICTION.value


class HintStatus(CdekModel):
    """Restriction status (``HintStatusDto``)."""

    code: str | None = Field(
        default=None, description="FORBIDDEN — banned, LIMITED — conditional, ALLOWED — allowed"
    )
    name: str | None = Field(default=None, description="Status name")
    reason: HintReason | None = Field(default=None, description="Reason for the restriction")

    @property
    def is_forbidden(self) -> bool:
        """Return whether creating an order in this direction is forbidden."""
        return self.code == HintStatusCode.FORBIDDEN.value

    @property
    def is_allowed(self) -> bool:
        """Return whether there are no restrictions."""
        return self.code == HintStatusCode.ALLOWED.value


class ItemHint(CdekModel):
    """Restrictions for an item (``ItemHintDto``).

    The ``limitations`` and ``documents`` fields are declared in the
    specification as arrays without an element schema (``items: {}``), so they
    stay ``list[Any]`` — the content depends on the direction.
    """

    item_id: str | None = Field(default=None, description="Unique goods identifier")
    feacn_code: str | None = Field(default=None, description="FEACN code of the goods")
    status: HintStatus | None = Field(default=None, description="Restriction status")
    limitations: list[Any] | None = Field(default=None, description="Restrictions for the goods")
    documents: list[Any] | None = Field(default=None, description="List of the required documents")


class PackageHint(CdekModel):
    """Restrictions for a cargo place (``PackageHintDto``)."""

    package_id: str | None = Field(default=None, description="Unique package identifier")
    status: HintStatus | None = Field(default=None, description="Restriction status of the place")
    description: str | None = Field(default=None, description="Restriction description")
    items: list[ItemHint] | None = Field(
        default=None, description="List of restrictions for the goods"
    )

    @property
    def is_forbidden(self) -> bool:
        """Return whether the cargo place or at least one item in it is forbidden.

        The place status can be ``LIMITED`` while an item inside is
        ``FORBIDDEN``: per the CDEK description the place statuses are
        "generated both by the cargo place itself and by the items in it", so
        both levels are checked.
        """
        if self.status and self.status.is_forbidden:
            return True
        return any(i.status and i.status.is_forbidden for i in (self.items or []))

    @property
    def forbidden_items(self) -> list[ItemHint]:
        """Return the forbidden items (usually they define the place status)."""
        return [i for i in (self.items or []) if i.status and i.status.is_forbidden]


class RestrictionHintsResponse(ListResponse):
    """Response of ``POST /v2/international/package/restrictions``.

    ``RestrictionHintsResponseDto``. The method returns a body with the ``*/*``
    type (not ``application/json``) — a specification quirk that does not affect
    response parsing.
    """

    packages: list[PackageHint] | None = Field(
        default=None, description="List of restrictions for the packages"
    )

    @property
    def is_allowed(self) -> bool:
        """Return whether no cargo place is forbidden for shipment."""
        return not any(p.is_forbidden for p in (self.packages or []))

    @property
    def forbidden(self) -> list[PackageHint]:
        """Return the forbidden cargo places (``FORBIDDEN``)."""
        return [p for p in (self.packages or []) if p.is_forbidden]


# --- reverse availability check (POST /v2/reverse/availability) --------------


class ReverseLocation(CdekModel):
    """Location in the reverse validation request (``ReverseValidateRequest*LocationDto``).

    The field set is narrower than in :class:`cdekx.models.Location`: there is
    no ``city_uuid``, ``kladr_code``, ``country``, ``time_zone`` or
    ``payment_limit``. You do not need to pass them — the API does not expect
    them.

    For ``to_location`` the ``address`` field is **required** (it is in
    ``required`` of the ``ReverseValidateRequestToLocationDto`` schema); for
    ``from_location`` a settlement identifier is enough.
    """

    code: int | None = Field(default=None, description="CDEK settlement code")
    fias_guid: str | None = Field(default=None, description="FIAS identifier")
    postal_code: str | None = Field(default=None, description="Postal code")
    longitude: float | None = Field(default=None, description="Longitude")
    latitude: float | None = Field(default=None, description="Latitude")
    country_code: str | None = Field(
        default=None, description="ISO 3166-1 alpha-2 country code (RU by default)"
    )
    region: str | None = Field(default=None, description="Region name")
    region_code: int | None = Field(default=None, description="CDEK region code")
    sub_region: str | None = Field(default=None, description="Name of the region district")
    city: str | None = Field(default=None, description="Settlement name")
    address: str | None = Field(
        default=None, description="Address string (required for to_location)"
    )


class ReverseContragent(CdekModel):
    """Sender/recipient in the reverse validation request.

    ``ReverseValidateRequestSenderDto``/``RecipientDto``: unlike
    :class:`cdekx.models.Contact` there is **no** full name here — only the
    contragent type and phones (required, no more than 10).
    """

    contragent_type: ContragentType | str | None = Field(
        default=None, description="LEGAL_ENTITY — a legal entity, INDIVIDUAL — a natural person"
    )
    phones: list[Phone] = Field(description="List of phones (no more than 10), a required field")

    @field_validator("phones", mode="before")
    @classmethod
    def _coerce_phones(cls, value: Any) -> Any:
        """Accept ``["+79001234567"]`` as ``[{"number": "+79001234567"}]``."""
        return coerce_phones(value)


class ReverseValidateRequest(CdekModel):
    """Request of the reverse availability check (``ReverseValidateRequestDto``).

    The same data as for creating a forward order is passed: direction, tariff,
    sender and recipient, shipment/delivery offices.

    Note:
        Locations and offices are mutually exclusive pairs: ``from_location``
        **or** ``shipment_point``, ``to_location`` **or** ``delivery_point``.
        ``delivery_point`` is required for tariffs with the "to the warehouse"
        or "to the parcel locker" mode.

        The method has no response body: HTTP 200 with an empty body means
        "reverse is available", while unavailability is returned as HTTP 400
        (in ``cdekx`` — an :class:`cdekx.exceptions.ApiError` exception).

    """

    tariff_code: TariffCode | int = Field(description="Tariff code")
    sender: ReverseContragent = Field(description="Sender")
    recipient: ReverseContragent = Field(description="Recipient")
    from_location: ReverseLocation | None = Field(
        default=None, description="Origin location (not together with shipment_point)"
    )
    to_location: ReverseLocation | None = Field(
        default=None, description="Destination location (not together with delivery_point)"
    )
    shipment_point: Code | None = Field(
        default=None,
        description="Code of the CDEK office for a client drop-off "
        "(not together with from_location)",
    )
    delivery_point: Code | None = Field(
        default=None,
        description="Code of the CDEK office for delivery. Required for tariffs "
        'with the "to the warehouse"/"to the parcel locker" mode (not to_location)',
    )
