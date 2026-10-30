"""Common API data structures.

Verified against the apidoc.cdek.ru OpenAPI specification (section
``api_v2_integration``): ``PhoneDto``, ``ContactDto``, ``MoneyDto``,
``LocationDto``, ``PackageRequestDto``/``PackageResponseDto``,
``ItemRequestDto``/``ItemResponseDto``, ``SellerDto``/``SellerItemDto``,
``AdditionalService*Dto``, ``DeliveryCostThresholdDto``.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field, StringConstraints, field_validator

from ..types import CdekDate
from ..types.enums import ContragentType, VatRate
from ..utils import normalize_phone
from .base import CdekModel

__all__ = [
    "CdekNumber",
    "Contact",
    "DeliveryCostThreshold",
    "Item",
    "ItemResponse",
    "Location",
    "Money",
    "Package",
    "PackageResponse",
    "Phone",
    "Seller",
    "SellerItem",
    "Service",
    "ServiceResponse",
    "coerce_phones",
]

#: Phone number: international format, up to 24 characters (``PhoneDto.number``).
PhoneNumber = Annotated[str, StringConstraints(max_length=24)]


def to_cdek_number(value: Any) -> Any:
    """``BeforeValidator``: coerce a CDEK order number to a string."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


CdekNumber = Annotated[str, BeforeValidator(to_cdek_number)]
"""A CDEK order number that always arrives as ``str``.

In the specification the ``cdek_number`` field is described **inconsistently**:
in ``OrderResponseDto``, ``IntakeInfoResponseEntity`` and ``RelatedEntityDto`` it
is a string, while in ``CheckInfoDto``, ``PassportOrderDto``,
``RegistryOrderDto``, ``PhotoReadyOrderDto`` and
``GetPrealertResponseDtoOrderDto`` it is ``int64``. Pydantic does not turn a
number into a string in lax mode, so we normalise it ourselves: the model always
returns ``str`` and accepts both ``1234567890`` and ``"1234567890"``.
"""


def coerce_phones(value: Any) -> Any:
    """Turn a list of strings into a list of ``{"number": ...}`` dicts.

    A common helper for all models with a ``phones`` field (``ContactDto``,
    ``ReverseValidateRequestPhoneDto``, ``IntakeContactDto``): CDEK expects
    :class:`Phone` objects, but writing ``[{"number": "+79001234567"}]`` by hand
    is inconvenient. Values that are already objects/dicts pass through unchanged
    (the number is normalised anyway).

    Args:
        value: an arbitrary value of the ``phones`` field before validation.

    Returns:
        A value suitable for ``list[Phone]``.

    """
    if not isinstance(value, list):
        return value
    result: list[Any] = []
    for item in value:
        if isinstance(item, str):
            result.append({"number": normalize_phone(item)})
        elif isinstance(item, dict) and "number" in item:
            number = item["number"]
            if isinstance(number, str):
                item = {**item, "number": normalize_phone(number)}
            result.append(item)
        else:
            result.append(item)
    return result


class Phone(CdekModel):
    """Phone of a contragent (``PhoneDto``).

    In API v2 a phone is an **object**, not a string::

        {"number": "+79001234567", "additional": "123"}

    For convenience :class:`Contact` also accepts plain strings: they are
    automatically turned into ``Phone(number=...)``.
    """

    number: PhoneNumber = Field(description="Number in the international format: +7 and 10+ digits")
    additional: str | None = Field(default=None, max_length=255, description="Extension number")


class Money(CdekModel):
    """A money amount (``MoneyDto``).

    Attention: there is **no** ``currency`` field in ``MoneyDto`` — the currency
    is set at the order/calculation level. VAT rates since 01.01.2026: 0, 5, 7,
    10, 16, 22 or ``null`` (no VAT).
    """

    value: float = Field(description="Payment amount, including VAT (no more than 50 000 000)")
    vat_sum: float | None = Field(
        default=None, description="VAT amount. Required if vat_rate is given"
    )
    vat_rate: VatRate | int | None = Field(
        default=None, description="VAT rate: 0, 5, 7, 10, 16, 22 or null (no VAT)"
    )


class DeliveryCostThreshold(CdekModel):
    """Buyout threshold and an extra delivery fee (``DeliveryCostThresholdDto``).

    Used in ``delivery_recipient_cost_adv``::

        [{"sum": 500, "threshold": 5000}]   # buyout < 5000 ₽ → delivery 500 ₽
    """

    threshold: int | None = Field(
        default=None, description='Threshold of the goods cost (the "less or equal" condition)'
    )
    sum: float | None = Field(default=None, description="Extra delivery fee")
    vat_sum: float | None = Field(default=None, description="VAT amount in the extra fee")
    vat_rate: VatRate | int | None = Field(default=None, description="VAT rate")


class Seller(CdekModel):
    """The true seller of the order (``SellerDto``)."""

    name: str | None = Field(default=None, description="Name of the true seller")
    inn: str | None = Field(
        default=None, max_length=20, description="Taxpayer identification number of the true seller"
    )
    phone: str | None = Field(default=None, description="Seller phone. Required if inn is filled")
    ownership_form: int | None = Field(default=None, description="Ownership form code")
    address: str | None = Field(default=None, description="Address of the true seller")


class SellerItem(Seller):
    """The true seller of an item (``SellerItemDto``)."""

    giis_subdivision_id: str | None = Field(
        default=None, description="IDTOP — the department identifier in the GIIS personal account"
    )


class Location(CdekModel):
    """Location of the sender/recipient (``RequestFromLocationDto``/``LocationDto1``).

    In a request ``address`` (the address string) is required; the settlement
    identifier is given by one of the fields: ``code``, ``city_uuid``,
    ``fias_guid``, ``kladr_code``, ``postal_code`` or ``city``.
    """

    code: int | None = Field(default=None, description="CDEK settlement code")
    city_uuid: str | None = Field(
        default=None, description="City identifier in the CDEK information system"
    )
    city: str | None = Field(default=None, description="Settlement name")
    fias_guid: str | None = Field(default=None, description="FIAS identifier")
    kladr_code: str | None = Field(default=None, description="KLADR code")
    country_code: str | None = Field(
        default=None, description="ISO 3166-1 alpha-2 country code (RU by default)"
    )
    country: str | None = Field(default=None, description="Country name")
    region: str | None = Field(default=None, description="Region name")
    region_code: int | None = Field(default=None, description="CDEK region code")
    fias_region_guid: str | None = Field(
        default=None,
        description="FIAS identifier of the region. In responses (orders, intakes, "
        "delivery agreements) the field is deprecated — the values may be outdated",
    )
    kladr_region_code: str | None = Field(default=None, description="KLADR code of the region")
    sub_region: str | None = Field(default=None, description="Name of the region district")
    longitude: float | None = Field(default=None, description="Longitude")
    latitude: float | None = Field(default=None, description="Latitude")
    time_zone: str | None = Field(default=None, description="Time zone")
    payment_limit: float | None = Field(
        default=None, description="Limit on the cash-on-delivery amount"
    )
    address: str | None = Field(default=None, description="Address string (required in a request)")
    postal_code: str | None = Field(default=None, description="Postal code")


class Contact(CdekModel):
    """A contragent: the sender or the recipient (``ContactDto``/``SenderContactDto``).

    ``phones`` is a list of :class:`Phone` objects (no more than 10). For
    convenience you may pass strings: they are normalised and wrapped
    automatically.
    """

    company: str | None = Field(default=None, description="Company name")
    name: str = Field(description="Full name of the contact person")
    contragent_type: ContragentType | str | None = Field(
        default=None,
        description="LEGAL_ENTITY — a legal entity, INDIVIDUAL — a person, INDIVIDUAL_ENTREPRENEUR",
    )
    passport_series: str | None = Field(default=None, description="Passport series")
    passport_number: str | None = Field(default=None, description="Passport number")
    passport_date_of_issue: CdekDate | str | None = Field(
        default=None, description="Passport issue date"
    )
    passport_organization: str | None = Field(
        default=None, description="Passport issuing authority"
    )
    tin: str | None = Field(default=None, description="Taxpayer identification number")
    passport_date_of_birth: CdekDate | str | None = Field(default=None, description="Date of birth")
    email: str | None = Field(default=None, description="Email")
    phones: list[Phone] = Field(
        default_factory=list, description="List of phones (no more than 10)"
    )
    passport_requirements_satisfied: bool | None = Field(
        default=None,
        description="Passport data is collected or not required (international orders)",
    )

    @field_validator("phones", mode="before")
    @classmethod
    def _coerce_phones(cls, value: Any) -> Any:
        """Accept ``["+79001234567"]`` as ``[{"number": "+79001234567"}]``."""
        return coerce_phones(value)

    @property
    def phone_numbers(self) -> list[str]:
        """Return the phone numbers as a list of strings (handy for logs and checks)."""
        return [phone.number for phone in self.phones]


class Service(CdekModel):
    """An additional service in a request (``AdditionalServiceRequestDto``)."""

    code: str = Field(description="Additional service code (see types.enums.ServiceCode)")
    parameter: str | int | float | None = Field(
        default=None, description="Service parameter (for example, the insurance amount)"
    )


class ServiceResponse(Service):
    """An additional service in a response (``AdditionalServiceResponseDto``)."""

    sum: float | None = Field(default=None, description="Service cost")
    total_sum: float | None = Field(default=None, description="Cost including VAT and discount")
    discount_percent: float | None = Field(default=None, description="Discount percentage")
    discount_sum: float | None = Field(default=None, description="Discount amount")
    vat_rate: float | None = Field(
        default=None, description="VAT percentage (a float in responses, 20 occurs historically)"
    )
    vat_sum: float | None = Field(default=None, description="VAT amount")


class Item(CdekModel):
    """An item in a request (``ItemRequestDto``).

    Required: ``name``, ``ware_key``, ``payment``, ``weight``, ``amount``,
    ``cost``. The ``marking`` field is the "Chestny Znak" marking code (not
    ``marking_code``), the FEACN code is called ``feacn_code``, and the unique
    jewellery number is ``jewel_uin``.
    """

    name: str = Field(description="Goods name (may include size/colour)")
    ware_key: str = Field(description="Goods identifier/article")
    payment: Money = Field(description="Payment on receipt (cash on delivery); 0 for a prepayment")
    weight: int = Field(description="Weight of one goods unit, grams")
    amount: int = Field(description="Number of goods units, pieces")
    cost: float = Field(description="Declared cost per unit — the insurance is calculated from it")
    marking: str | None = Field(default=None, description='"Chestny Znak" marking code')
    weight_gross: int | None = Field(
        default=None, description="Gross weight (required for international orders)"
    )
    name_i18n: str | None = Field(default=None, description="Name in a foreign language")
    brand: str | None = Field(default=None, description="Brand in a foreign language")
    country_code: str | None = Field(
        default=None, description="ISO 3166-1 alpha-2 manufacturer country code"
    )
    material: int | None = Field(default=None, description="Material code (Appendix 7)")
    wifi_gsm: bool | None = Field(default=None, description="Contains a Wi-Fi/GSM module")
    url: str | None = Field(default=None, description="Link to the goods in the online shop")
    seller: SellerItem | None = Field(default=None, description="Details of the true seller")
    feacn_code: str | None = Field(default=None, description="FEACN code")
    jewel_uin: str | None = Field(default=None, description="Unique jewellery number")
    used: bool | None = Field(
        default=None, description="Flag of second-hand goods (for c2c orders)"
    )


class ItemResponse(Item):
    """An item in a response (``ItemResponseDto``)."""

    delivery_amount: int | None = Field(
        default=None, description="Number of handed-out goods units"
    )
    return_item_detail: dict[str, Any] | None = Field(
        default=None,
        description="Data of the direct order/package the goods were delivered in (returns)",
    )
    excise: bool | None = Field(default=None, description="Whether the goods are excisable")


class Package(CdekModel):
    """A cargo place in a request (``PackageRequestDto``).

    ``number`` and ``weight`` are required. Dimensions are needed if ``items``
    are passed. ``package_id`` is required for an already existing package when
    the order is modified.
    """

    number: str = Field(description="Package number, unique within an order")
    weight: int = Field(description="Total weight, grams")
    length: int | None = Field(default=None, description="Length, cm")
    width: int | None = Field(default=None, description="Width, cm")
    height: int | None = Field(default=None, description="Height, cm")
    comment: str | None = Field(
        default=None, description='Comment (required for a "Delivery" type order)'
    )
    items: list[Item] | None = Field(
        default=None, description='Items (required for an "online shop" type order)'
    )
    package_id: str | None = Field(
        default=None,
        description="Unique package number in the CDEK information system (for order changes)",
    )


class PackageResponse(CdekModel):
    """A cargo place in a response (``PackageResponseDto``)."""

    number: str = Field(description="Package number")
    weight: int = Field(description="Total weight, grams")
    barcode: str | None = Field(
        default=None, description="Package barcode in the CDEK information system"
    )
    length: int | None = Field(default=None, description="Length, cm")
    width: int | None = Field(default=None, description="Width, cm")
    height: int | None = Field(default=None, description="Height, cm")
    weight_volume: int | None = Field(default=None, description="Volumetric weight, grams")
    weight_calc: int | None = Field(default=None, description="Calculated weight, grams")
    comment: str | None = Field(default=None, description="Comment on the package")
    items: list[ItemResponse] | None = Field(default=None, description="Items")
    services: list[ServiceResponse] | None = Field(
        default=None, description="Additional services for the package"
    )
    package_id: str | None = Field(
        default=None, description="Unique package number in the CDEK information system"
    )
