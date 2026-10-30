"""Models of the cost calculator.

Verified against the apidoc.cdek.ru OpenAPI specification:
``CalculatorRequestDto``, ``CalculatorTariffListRequestDto``,
``CalculatorTariffWithServicesRequestDto``, ``CalculatorResponseDto``,
``CalculatorTariffListResponseDto``, ``TariffCodeDto``,
``CalculatorAvailableTariffsResponseDto``, ``CalcPackageRequestDto``,
``CalculatorLocationDto``, ``DeliveryDateRangeDto``.

Note: the customs duty calculation method (``/v2/calculator/customsduty``) is
**absent** from the current specification — it appeared only in the outdated
documentation.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..types.enums import ContragentType, Currency, Language, OrderType, TariffCode
from .base import CdekModel, ErrorInfo
from .common import Location, Service

__all__ = [
    "AvailableTariff",
    "AvailableTariffDeliveryMode",
    "AvailableTariffsResponse",
    "CalcService",
    "CalculatorLocation",
    "CalculatorPackage",
    "DeliveryDateRange",
    "TariffCalculation",
    "TariffCodeItem",
    "TariffListRequest",
    "TariffListResponse",
    "TariffRequest",
    "TariffWithService",
    "TariffWithServiceResult",
    "TariffWithServicesRequest",
    "TariffWithServicesResponse",
]


class CalculatorLocation(CdekModel):
    """Location for the calculator (``CalculatorLocationDto``).

    The calculator has its own reduced set of location fields — plus
    ``contragent_type``: it affects the tariff calculation.
    """

    code: int | None = Field(default=None, description="CDEK settlement code")
    postal_code: str | None = Field(default=None, description="Postal code")
    country_code: str | None = Field(
        default=None, description="ISO 3166-1 alpha-2 country code (RU by default)"
    )
    city: str | None = Field(default=None, description="Settlement name")
    address: str | None = Field(default=None, description="Address string")
    contragent_type: ContragentType | str | None = Field(
        default=None, description="LEGAL_ENTITY / INDIVIDUAL / INDIVIDUAL_ENTREPRENEUR"
    )
    longitude: float | None = Field(default=None, description="Longitude")
    latitude: float | None = Field(default=None, description="Latitude")

    @classmethod
    def from_location(cls, location: Location) -> CalculatorLocation:
        """Build a calculator location from a full :class:`Location`."""
        return cls(
            code=location.code,
            postal_code=location.postal_code,
            country_code=location.country_code,
            city=location.city,
            address=location.address,
            longitude=location.longitude,
            latitude=location.latitude,
        )


class CalculatorPackage(CdekModel):
    """A cargo place for the calculation (``CalcPackageRequestDto``)."""

    weight: int = Field(description="Total weight, grams")
    length: int | None = Field(default=None, description="Length, cm")
    width: int | None = Field(default=None, description="Width, cm")
    height: int | None = Field(default=None, description="Height, cm")


class _CalculatorRequestBase(CdekModel):
    """Common fields of calculator requests."""

    date: str | None = Field(
        default=None, description="Date and time of the planned order handover (now by default)"
    )
    type: OrderType | int | None = Field(
        default=None, description="Order type: 1 — online shop, 2 — delivery"
    )
    currency: Currency | int | None = Field(
        default=None,
        description=(
            "Currency of the calculation — a numeric code from Appendix 14 (1 — RUB). "
            "The API rejects string codes like 'RUB'. Defaults to the contract currency"
        ),
    )
    lang: Language | str | None = Field(
        default=None, description="Language of the tariff information output: rus, eng, zho"
    )
    from_location: CalculatorLocation = Field(description="Sender location")
    to_location: CalculatorLocation = Field(description="Recipient location")
    packages: list[CalculatorPackage] = Field(min_length=1, description="Cargo places")
    additional_order_types: list[int] | None = Field(
        default=None, description="Additional order type: 2 — consolidated cargo (LTL)"
    )
    shipment_point: str | None = Field(default=None, description="Code of the shipment office")
    delivery_point: str | None = Field(default=None, description="Code of the receiving office")


class TariffRequest(_CalculatorRequestBase):
    """Calculation by a tariff code (``POST /v2/calculator/tariff``)."""

    tariff_code: TariffCode | int = Field(description="Tariff code (required)")
    services: list[Service] | None = Field(default=None, description="Additional services")


class TariffListRequest(_CalculatorRequestBase):
    """Calculation by available tariffs (``POST /v2/calculator/tarifflist``).

    Note:
        Unlike ``tariff`` and ``tariffAndService``, this method does **not
        accept** ``services`` — additional services are not included in the
        calculation.

    """


class TariffWithServicesRequest(_CalculatorRequestBase):
    """Calculation by tariffs and services (``POST /v2/calculator/tariffAndService``)."""

    services: list[Service] | None = Field(default=None, description="Additional services")


class DeliveryDateRange(CdekModel):
    """Predicted delivery date range (``DeliveryDateRangeDto``)."""

    min: str | None = Field(default=None, description="Minimum date")
    max: str | None = Field(default=None, description="Maximum date")


class CalcService(CdekModel):
    """Calculation of an additional service (``CalcResponseAdditionalServiceDto``)."""

    code: str = Field(description="Additional service code")
    sum: float = Field(description="Service cost")
    total_sum: float | None = Field(default=None, description="Cost including VAT and discount")
    discount_percent: float | None = Field(default=None, description="Discount percentage")
    discount_sum: float | None = Field(default=None, description="Discount amount")
    vat_rate: float | None = Field(default=None, description="VAT percentage")
    vat_sum: float | None = Field(default=None, description="VAT amount")


class _CalculationResult(CdekModel):
    """Common fields of a calculation result."""

    delivery_sum: float = Field(
        description="Base delivery cost without VAT and additional services"
    )
    period_min: int = Field(description="Minimum delivery time, working days")
    period_max: int = Field(description="Maximum delivery time, working days")
    calendar_min: int | None = Field(default=None, description="Minimum in calendar days")
    calendar_max: int | None = Field(default=None, description="Maximum in calendar days")
    weight_calc: int = Field(description="Calculated weight, grams")
    total_sum: float = Field(description="Cost including additional services and VAT")
    currency: str | None = Field(
        default=None, description="Currency of the calculation (three-letter code, e.g. RUB)"
    )
    services: list[CalcService] | None = Field(
        default=None, description="Calculation of additional services"
    )
    delivery_date_range: DeliveryDateRange | None = Field(
        default=None, description="Predicted delivery date range"
    )
    errors: list[dict[str, Any]] | None = Field(default=None, description="Calculation errors")
    warnings: list[dict[str, Any]] | None = Field(default=None, description="Warnings")

    @property
    def has_errors(self) -> bool:
        """Return whether the calculation has errors (the HTTP code may still be 200)."""
        return bool(self.errors)


class TariffCalculation(_CalculationResult):
    """Result of a calculation by tariff code (``CalculatorResponseDto``)."""


class TariffWithServiceResult(_CalculationResult):
    """Result of a tariff calculation with additional services.

    Schema: ``CalculatorTariffWithServiceResultResponseDto``.
    """


class TariffWithService(CdekModel):
    """A tariff with a calculation result (``CalculatorTariffWithServicesResponseDto``)."""

    tariff_code: TariffCode | int = Field(description="Tariff code")
    status: str | None = Field(default=None, description="Calculation status")
    result: TariffWithServiceResult = Field(description="Calculation result")

    @property
    def delivery_sum(self) -> float:
        """Return the delivery cost (a shortcut)."""
        return self.result.delivery_sum

    @property
    def has_errors(self) -> bool:
        """Return whether the calculation has errors."""
        return self.result.has_errors


class TariffCodeItem(CdekModel):
    """An item of the available-tariffs calculation (``TariffCodeDto``)."""

    tariff_code: TariffCode | int = Field(description="Tariff code")
    tariff_name: str = Field(description="Tariff name in the output language")
    tariff_description: str = Field(description="Tariff description")
    delivery_mode: int = Field(
        description="Tariff mode: 1 — door to door, 2 — door to warehouse, "
        "3 — warehouse to door, 4 — warehouse to warehouse"
    )
    delivery_sum: float = Field(description="Base delivery cost")
    period_min: int = Field(description="Minimum term, working days")
    period_max: int = Field(description="Maximum term, working days")
    calendar_min: int | None = Field(default=None, description="Minimum in calendar days")
    calendar_max: int | None = Field(default=None, description="Maximum in calendar days")
    delivery_date_range: DeliveryDateRange | None = Field(
        default=None, description="Delivery date range"
    )
    errors: list[ErrorInfo] | None = Field(
        default=None,
        description="Calculation errors for the tariff (CDEK may return HTTP 200 with an error)",
    )

    @property
    def has_errors(self) -> bool:
        """Return whether this tariff has calculation errors."""
        return bool(self.errors)


class TariffListResponse(CdekModel):
    """Response of ``POST /v2/calculator/tarifflist``.

    The list items are :class:`TariffCodeItem`: code, name, delivery mode, cost
    and terms.
    """

    tariff_codes: list[TariffCodeItem] = Field(
        default_factory=list, description="Available tariffs with the calculation"
    )
    errors: list[dict[str, Any]] | None = Field(default=None, description="Calculation errors")
    warnings: list[dict[str, Any]] | None = Field(default=None, description="Warnings")

    @property
    def viable(self) -> list[TariffCodeItem]:
        """Return the tariffs without calculation errors."""
        return [t for t in self.tariff_codes if not t.has_errors]

    def best(self) -> TariffCodeItem | None:
        """Return the cheapest tariff without calculation errors."""
        candidates = self.viable
        return min(candidates, key=lambda t: t.delivery_sum) if candidates else None

    def fastest(self) -> TariffCodeItem | None:
        """Return the fastest tariff without calculation errors."""
        candidates = [t for t in self.viable if t.period_min is not None]
        return min(candidates, key=lambda t: (t.period_min, t.delivery_sum)) if candidates else None


class TariffWithServicesResponse(CdekModel):
    """Response of ``POST /v2/calculator/tariffAndService``."""

    tariff_codes: list[TariffWithService] = Field(
        default_factory=list, description="Tariffs including additional services"
    )
    errors: list[dict[str, Any]] | None = Field(default=None, description="Errors")
    warnings: list[dict[str, Any]] | None = Field(default=None, description="Warnings")

    @property
    def viable(self) -> list[TariffWithService]:
        """Return the tariffs without calculation errors."""
        return [t for t in self.tariff_codes if not t.has_errors]

    def best(self) -> TariffWithService | None:
        """Return the cheapest tariff."""
        candidates = self.viable
        return min(candidates, key=lambda t: t.delivery_sum) if candidates else None


class AvailableTariffDeliveryMode(CdekModel):
    """Delivery mode in the available tariffs directory."""

    delivery_mode: int | None = Field(default=None, description="Delivery mode code")
    delivery_mode_name: str | None = Field(default=None, description="Mode name")
    tariff_code: TariffCode | int | None = Field(default=None, description="Tariff code")


class AvailableTariff(CdekModel):
    """A tariff available under the contract (``CalculatorAvailableTariffsResponseTariffCodeDto``).

    Response of ``GET /v2/calculator/alltariffs``. Note: the tariff code lies
    here in the ``delivery_modes`` items, and the limits are on size and weight.
    """

    tariff_name: str | None = Field(default=None, description="Service name")
    weight_min: float | None = Field(default=None, description="Minimum shipment weight, kg")
    weight_max: float | None = Field(default=None, description="Maximum shipment weight, kg")
    weight_calc_max: float | None = Field(default=None, description="Maximum calculated weight, kg")
    length_min: int | None = Field(default=None, description="Minimum package length")
    length_max: int | None = Field(default=None, description="Maximum package length")
    width_min: int | None = Field(default=None, description="Minimum package width")
    width_max: int | None = Field(default=None, description="Maximum package width")
    height_min: int | None = Field(default=None, description="Minimum package height")
    height_max: int | None = Field(default=None, description="Maximum package height")
    order_types: list[int] | None = Field(
        default=None, description="Available order types (empty — any)"
    )
    payer_contragent_type: list[str] | None = Field(
        default=None, description="Allowed payer contragent types"
    )
    sender_contragent_type: list[str] | None = Field(
        default=None, description="Allowed sender contragent types"
    )
    recipient_contragent_type: list[str] | None = Field(
        default=None, description="Allowed recipient contragent types"
    )
    delivery_modes: list[AvailableTariffDeliveryMode] | None = Field(
        default=None, description="Delivery modes with tariff codes"
    )
    additional_order_types_param: dict[str, Any] | None = Field(
        default=None, description="Parameters of additional order types"
    )

    @property
    def tariff_codes(self) -> list[int]:
        """Return all tariff codes of this item (by delivery modes)."""
        codes: list[int] = []
        for mode in self.delivery_modes or []:
            if mode.tariff_code is not None:
                codes.append(int(mode.tariff_code))
        return codes


class AvailableTariffsResponse(CdekModel):
    """Response of ``GET /v2/calculator/alltariffs``."""

    tariff_codes: list[AvailableTariff] = Field(
        default_factory=list, description="List of tariffs available under the contract"
    )

    def all_tariff_codes(self) -> list[int]:
        """Return a flat list of all contract tariff codes."""
        return [code for tariff in self.tariff_codes for code in tariff.tariff_codes]
