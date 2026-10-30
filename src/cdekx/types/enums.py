"""Enumerations of the CDEK API.

Two principles:

1. **CDEK directories change.** Tariff codes, extra-service codes and webhook
   types gain new entries several times a year. The "long" enumerations are
   therefore declared as ``StrEnum``/``IntEnum`` with the *known* values, while
   the models also accept any value of the same type (``int``/``str``) — see
   :data:`cdekx.types.TariffCodeLike`. A new directory entry will not break your
   code and will not require an urgent library release.
2. **No stringly-typed magic.** Everything a user might type by hand has a named
   constant.
"""

from __future__ import annotations

from enum import IntEnum

from . import StrEnum  # backport for Python 3.10

__all__ = [
    "CheckType",
    "ContragentType",
    "Currency",
    "DeliveryMode",
    "HintReasonCode",
    "HintStatusCode",
    "Language",
    "OrderRequestState",
    "OrderStatus",
    "OrderType",
    "PackageType",
    "PassportClient",
    "PaymentType",
    "PhotoTaskStatus",
    "PrealertPackageStatus",
    "PrintFormat",
    "PrintLang",
    "PrintType",
    "RegistryBasisType",
    "ServiceCode",
    "StatusReasonCode",
    "TariffCode",
    "VatRate",
    "WebhookType",
]


class OrderType(IntEnum):
    """Order type (the ``type`` field)."""

    E_COMMERCE = 1
    """Online store (delivery to the buyer)."""
    DELIVERY = 2
    """Delivery."""
    SUPPLIER = 3
    """Supplier."""
    RETURN = 4
    """Return."""
    SERVICE = 7
    """Service order."""
    CARGO_PICKUP = 8
    """Cargo pickup (door to warehouse)."""
    FULFILLMENT = 9
    """Fulfillment."""
    SHOPPING = 10
    """CDEK Shopping."""


class DeliveryMode(IntEnum):
    """The real delivery mode of an order (``OrderResponseDto.delivery_mode``).

    Outdated documentation described these as the strings ``door``/``pickup`` —
    the current API returns integers. There is no value 5 in the specification:
    the parcel-locker modes (6-10) follow warehouse-to-warehouse directly.
    """

    DOOR_DOOR = 1
    """Door to door."""
    DOOR_PICKUP = 2
    """Door to warehouse."""
    PICKUP_DOOR = 3
    """Warehouse to door."""
    PICKUP_PICKUP = 4
    """Warehouse to warehouse."""
    DOOR_POSTAMAT = 6
    """Door to parcel locker."""
    PICKUP_POSTAMAT = 7
    """Warehouse to parcel locker."""
    POSTAMAT_DOOR = 8
    """Parcel locker to door."""
    POSTAMAT_PICKUP = 9
    """Parcel locker to warehouse."""
    POSTAMAT_POSTAMAT = 10
    """Parcel locker to parcel locker."""


class TariffCode(IntEnum):
    """The most commonly used tariff codes.

    The complete, current list comes from ``GET /v2/calculator/tariffs``
    (see :meth:`cdekx.endpoints.calculator.CalculatorEndpoint.tariffs`) and
    apidoc.cdek.ru. A code not listed here can be passed as a plain number.
    """

    EXPRESS_DOOR_DOOR = 1
    EXPRESS_DOOR_PICKUP = 2
    EXPRESS_PICKUP_DOOR = 3
    EXPRESS_PICKUP_PICKUP = 4
    ECONOMY_DOOR_DOOR = 5
    ECONOMY_DOOR_PICKUP = 6
    ECONOMY_PICKUP_DOOR = 7
    ECONOMY_PICKUP_PICKUP = 8
    SUPER_EXPRESS_9_18 = 10
    SUPER_EXPRESS_10_16 = 11
    SUPER_EXPRESS_18_20 = 12
    OVERNIGHT = 15
    ECONOMY_EXPRESS = 16
    CARGO_DOOR_DOOR = 62
    CARGO_DOOR_PICKUP = 63
    CARGO_PICKUP_DOOR = 64
    CARGO_PICKUP_PICKUP = 65
    EXPRESS_LIGHT_DOOR_DOOR = 136
    POSTAMAT = 137
    ECONOMY_PICKUP_POSTAMAT = 138
    CARGO_PICKUP_CARGO_PICKUP = 158
    """Cargo pickup, door to warehouse (required for a consolidated intake)."""
    SUPER_EXPRESS_9_18_DOCUMENTS = 233
    ECONOMY_EXPRESS_PICKUP_PICKUP = 234
    ECONOMY_EXPRESS_DOOR_PICKUP = 235
    ECONOMY_EXPRESS_PICKUP_DOOR = 236
    FULFILLMENT_ISSUANCE = 358
    ECONOMY_DOOR_DOOR_STANDARD = 366
    POSTAMAT_DOOR = 480
    POSTAMAT_PICKUP = 481
    EXPRESS_LIGHT_PICKUP = 482
    EXPRESS_LIGHT_DOOR = 483
    CARGO_EXPRESS_DOOR_DOOR = 485
    CARGO_EXPRESS_PICKUP_PICKUP = 486


class ServiceCode(StrEnum):
    """Extra service codes.

    The current list comes from ``GET /v2/handbook/services`` and apidoc.cdek.ru.
    A code missing here can be passed as a plain string.
    """

    INSURANCE = "INSURANCE"
    """Insurance (``parameter`` is the declared value)."""
    DANGEROUS_GOODS = "DANGEROUS_GOODS"
    TRYING_ON = "TRYING_ON"
    """Try-on."""
    PARTIAL_DELIVERY = "PARTIAL_DELIVERY"
    """Partial delivery."""
    INSPECTION_CARGO = "INSPECTION_CARGO"
    """Cargo inspection."""
    DELIVERY_TO_FLOOR = "DELIVERY_TO_FLOOR"
    """Carrying to the door or floor."""
    SMS_NOTIFICATION = "SMS_NOTIFICATION"
    NOTIFICATIONS = "NOTIFICATIONS"
    FRAGILE_CARGO = "FRAGILE_CARGO"
    OVERSIZED_CARGO = "OVERSIZED_CARGO"
    HEAVY_CARGO = "HEAVY_CARGO"
    TEMPERATURE_MODE = "TEMPERATURE_MODE"
    RETURN_RECEIPT = "RETURN_RECEIPT"
    """Return of the waybill."""
    DOCUMENTS_COPY = "DOCUMENTS_COPY"
    PHOTO_DOCUMENT = "PHOTO_DOCUMENT"
    """Photos of documents."""
    PERSONAL_DELIVERY = "PERSONAL_DELIVERY"
    PAYMENT_CARD = "PAYMENT_CARD"
    CARGO_CHECK = "CARGO_CHECK"
    COURIER_PACKAGE_A2 = "COURIER_PACKAGE_A2"
    COURIER_PACKAGE_A3 = "COURIER_PACKAGE_A3"
    COURIER_PACKAGE_A4 = "COURIER_PACKAGE_A4"
    COURIER_PACKAGE_A5 = "COURIER_PACKAGE_A5"
    BOX_LINER = "BOX_LINER"
    """Internal crating."""
    COURIER_SERVICE = "COURIER_SERVICE"
    GREEN_ENVELOPE = "GREEN_ENVELOPE_CDEK"
    DESCENT_FROM_THE_FLOOR = "DESCENT_FROM_THE_FLOOR"
    REVERSE = "REVERSE"
    """Deprecated: use the ``has_reverse_order`` flag on the order."""


class OrderStatus(StrEnum):
    """Main statuses of an order/package (``code`` in the status table)."""

    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"
    IN_TRANSIT = "IN_TRANSIT"
    ISSUED_FOR_DELIVERY = "ISSUED_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    NOT_DELIVERED = "NOT_DELIVERED"
    RETURNED = "RETURNED"
    RETURN_IN_PROGRESS = "RETURN_IN_PROGRESS"
    RETURN_DELIVERED = "RETURN_DELIVERED"
    CANCELLED = "CANCELLED"
    LOST = "LOST"
    DELETED = "DELETED"


class StatusReasonCode(StrEnum):
    """Common additional statuses (``status_reason_code``).

    The full list is Appendix 2 on apidoc.cdek.ru. Values outside this enum are
    valid: pass a string.
    """

    RECEIVED_AT_WAREHOUSE = "RECEIVED_AT_WAREHOUSE"
    RECEIVED_BY_RECIPIENT = "RECEIVED_BY_RECIPIENT"
    COURIER_ARRIVED = "COURIER_ARRIVED"
    DELIVERY_POSTPONED = "DELIVERY_POSTPONED"
    DELIVERY_REFUSED = "DELIVERY_REFUSED"
    WRONG_PHONE = "WRONG_PHONE"
    LOST_IN_TRANSPORT = "LOST_IN_TRANSPORT"
    DAMAGED = "DAMAGED"


class ContragentType(StrEnum):
    """Contragent type."""

    LEGAL_ENTITY = "LEGAL_ENTITY"
    """Legal entity."""
    INDIVIDUAL = "INDIVIDUAL"
    """Individual."""
    INDIVIDUAL_ENTREPRENEUR = "INDIVIDUAL_ENTREPRENEUR"
    """Sole proprietor."""


class PackageType(StrEnum):
    """Package type."""

    PACKAGE = "package"
    ENVELOPE = "envelope"
    BOX = "box"


class Currency(IntEnum):
    """Numeric currency codes for the cost-calculation methods (CDEK Appendix 14).

    Important: in calculator **requests** the ``currency`` field is a numeric code
    (``int32``); the string ``"RUB"`` is rejected with ``v2_invalid_value_type``.
    In **responses** the currency comes back as a three-letter string (``"RUB"``),
    where this enum is not used.
    """

    RUB = 1
    KZT = 2
    USD = 3
    EUR = 4
    GBP = 5
    CNY = 6
    BYR = 7
    UAH = 8
    KGS = 9
    AMD = 10
    TRY = 11
    THB = 12
    KRW = 13
    AED = 14
    UZS = 15
    MNT = 16
    PLN = 17
    AZN = 18
    GEL = 19
    JPY = 55
    VND = 704


class VatRate(IntEnum):
    """VAT rates effective from 01.01.2026 (``null`` means no VAT).

    Allowed values: 0, 5, 7, 10, 16, 22. The former rate 20 is rejected by the
    API; it still appears in responses for historical data — response fields are
    typed as ``float`` and accept any value.
    """

    ZERO = 0
    FIVE = 5
    SEVEN = 7
    TEN = 10
    SIXTEEN = 16
    TWENTY_TWO = 22


class Language(StrEnum):
    """Language of directory information (``lang``)."""

    RU = "rus"
    EN = "eng"
    ZH = "zho"


class PrintFormat(StrEnum):
    """Print form format (``BarcodeRequestDto.format``)."""

    A4 = "A4"
    A5 = "A5"
    A6 = "A6"
    A7 = "A7"


class PrintLang(StrEnum):
    """Print form language in ISO 639-3 encoding (``BarcodeRequestDto.lang``)."""

    RU = "RUS"
    EN = "ENG"


class OrderRequestState(StrEnum):
    """State of an asynchronous request (``requests[].state``).

    It describes the **request**, not the entity: ``ACCEPTED`` does not guarantee
    that the order was created.
    """

    ACCEPTED = "ACCEPTED"
    """The request was accepted and passed initial validation."""
    SUCCESSFUL = "SUCCESSFUL"
    """The entity was successfully created in the CDEK system."""
    INVALID = "INVALID"
    """Error: fix the data and submit the request again."""


class PrintType(StrEnum):
    """Kinds of print form in the API (path names, not field values).

    The current API has no ``copy_order`` form — only the waybill and the package
    barcode.
    """

    ORDERS = "orders"
    """Order waybill (``/v2/print/orders``)."""
    BARCODES = "barcodes"
    """Package barcode (``/v2/print/barcodes``)."""


class WebhookType(StrEnum):
    """CDEK webhook types.

    An account may have at most **two** active subscriptions: a third one gets
    HTTP 400 with code ``v2_too_many_webhooks``. The limit is not described in
    the OpenAPI specification — it was confirmed by measurement against
    ``api.edu.cdek.ru``.
    """

    ORDER_STATUS = "ORDER_STATUS"
    """Order status change."""
    PRINT_FORM = "PRINT_FORM"
    """Print form is ready."""
    PREALERT_CLOSED = "PREALERT_CLOSED"
    """Prealert closed."""
    ACCOMPANYING_WAYBILL = "ACCOMPANYING_WAYBILL"
    """Transport information for the accompanying waybill."""
    OFFICE_AVAILABILITY = "OFFICE_AVAILABILITY"
    """Office availability change."""
    ORDER_MODIFIED = "ORDER_MODIFIED"
    """Order modified."""
    DELIV_AGREEMENT = "DELIV_AGREEMENT"
    """Delivery agreement change."""
    DELIV_PROBLEM = "DELIV_PROBLEM"
    """Delivery problems for an order."""
    COURIER_INFO = "COURIER_INFO"
    """Details of the courier assigned to an order or intake."""
    DOWNLOAD_PHOTO = "DOWNLOAD_PHOTO"
    """Order document photos are ready."""


# --- checks, registries, passport data, photos, restrictions -----------------
# The values below are described in the OpenAPI specification, but the
# corresponding fields are declared as plain strings without an ``enum``
# (``PhotoReadyOrderDto.status`` is the exception). The models therefore accept
# arbitrary strings too: CDEK keeps extending its directories.


class CheckType(StrEnum):
    """Fiscal receipt type (``CheckInfoDto.type``)."""

    CASH_RECEIPT_IN = "CASH_RECEIPT_IN"
    #: Income receipt.
    CASH_RECEIPT_REFUND = "CASH_RECEIPT_REFUND"
    #: Income refund receipt.


class PaymentType(StrEnum):
    """Payment type (``PaymentInfoDto.type``, at most 4 characters)."""

    CASH = "CASH"
    #: Cash.
    CARD = "CARD"
    #: Cashless (card).


class PassportClient(StrEnum):
    """Which party the passport data is returned for (query parameter ``client``).

    When the parameter is omitted, CDEK returns information for both the sender
    and the receiver, and the response carries ``client = ALL``.
    """

    SENDER = "SENDER"
    #: Sender.
    RECEIVER = "RECEIVER"
    #: Receiver.
    ALL = "ALL"
    #: Both sender and receiver (the default value in responses).


class RegistryBasisType(StrEnum):
    """Assignment type in a registry line (``RegistryOrderDto.basis_type``)."""

    ORDER = "ORDER"
    #: An "order" assignment.
    SAS = "SAS"
    #: Sale of fulfillment services.


class PhotoTaskStatus(StrEnum):
    """Status of a photo task (``PhotoReadyOrderDto.status``).

    The archive is ready for download once the task reaches ``DONE``.
    """

    CREATED = "CREATED"
    #: Created.
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    #: Ready for execution.
    IN_PROGRESS = "IN_PROGRESS"
    #: In progress.
    DONE = "DONE"
    #: Done — the archive can be downloaded.
    SENT = "SENT"
    #: Sent.
    DELIVERED = "DELIVERED"
    #: Delivered.
    NOT_DELIVERED = "NOT_DELIVERED"
    #: Not handed over.
    ERROR = "ERROR"
    #: Error.


class HintStatusCode(StrEnum):
    """Restriction status for an international destination (``HintStatusDto.code``)."""

    FORBIDDEN = "FORBIDDEN"
    #: Order creation is strictly forbidden.
    LIMITED = "LIMITED"
    #: Does not block the order but adds conditions (for example "an invoice is required").
    ALLOWED = "ALLOWED"
    #: Allowed.


class HintReasonCode(StrEnum):
    """Reason for the restriction (``HintReasonDto.code``)."""

    FEACN_RESTRICTION = "FEACN_RESTRICTION"
    #: Restriction on specific goods, by FEACN code.
    GENERAL_RESTRICTION = "GENERAL_RESTRICTION"
    #: General restriction on a package for the destination (weight, dimensions, price).


class PrealertPackageStatus(StrEnum):
    """Status of a prealert package (``GetPrealertResponseDtoPackageInfoDto.status``).

    Filled in after the prealert is closed: it shows discrepancies between what
    was declared and what was actually handed over.
    """

    ACCEPTED = "ACCEPTED"
    #: Package accepted.
    NOT_ACCEPTED = "NOT_ACCEPTED"
    #: Package not accepted.
    DELETED = "DELETED"
    #: Package deleted.
