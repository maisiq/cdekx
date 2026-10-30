"""Models of print forms: ``/v2/print/*``.

Verified against the apidoc.cdek.ru OpenAPI specification: ``WaybillRequestDto``,
``WaybillPrintResponseDto``, ``WaybillDto``, ``BarcodeRequestDto``,
``BarcodeGetResponseDto``, ``BarcodeDto``, ``PrintOrderDto``, ``PrintStatusDto``.

Important differences from the outdated documentation:

* an order is given as an **object** ``{"order_uuid": ...}`` or ``{"cdek_number": ...}``,
  not as a UUID string;
* the parameters are passed in the **JSON body**, not in the query string;
* the waybill and the package barcode have different status paths:
  ``GET /v2/print/orders/{uuid}`` and ``GET /v2/print/barcodes/{uuid}``;
* the finished file is downloaded from ``GET /v2/print/orders/{uuid}.pdf``
  (authorisation required), while ``url`` is present in the response only in the
  ready status;
* there is **no** ``copy_order`` format in the API — only the waybill and the
  package barcode.
"""

from __future__ import annotations

from pydantic import Field

from ..types import CdekDateTime
from ..types.enums import PrintFormat
from .base import CdekModel, RelatedEntity, RequestInfo, ResponseEnvelope

__all__ = [
    "Barcode",
    "BarcodeCreate",
    "BarcodeResponse",
    "PrintOrder",
    "PrintStatus",
    "Waybill",
    "WaybillCreate",
    "WaybillFormType",
    "WaybillResponse",
]


class PrintOrder(CdekModel):
    """An order reference for printing (``PrintOrderDto``).

    Exactly one of the fields must be given: ``order_uuid`` or ``cdek_number``.
    """

    order_uuid: str | None = Field(
        default=None, description="Order UUID (required if cdek_number is not given)"
    )
    cdek_number: str | None = Field(
        default=None, description="CDEK order number (required if order_uuid is not given)"
    )

    @classmethod
    def of_uuid(cls, order_uuid: str) -> PrintOrder:
        """Create a reference from an order UUID."""
        return cls(order_uuid=order_uuid)

    @classmethod
    def of_number(cls, cdek_number: str) -> PrintOrder:
        """Create a reference from a CDEK number."""
        return cls(cdek_number=cdek_number)


class WaybillFormType:
    """Waybill form type (``WaybillRequestDto.type``)."""

    RUSSIA = "tpl_russia"
    ENGLISH = "tpl_english"
    CHINA = "tpl_china"
    ARMENIA = "tpl_armenia"
    ITALIAN = "tpl_italian"
    KOREAN = "tpl_korean"
    LATVIAN = "tpl_latvian"
    LITHUANIAN = "tpl_lithuanian"
    GERMAN = "tpl_german"
    TURKISH = "tpl_turkish"
    CZECH = "tpl_czech"
    THAILAND = "tpl_thailand"
    INVOICE = "tpl_invoice"

    ALL: tuple[str, ...] = (
        RUSSIA,
        ENGLISH,
        CHINA,
        ARMENIA,
        ITALIAN,
        KOREAN,
        LATVIAN,
        LITHUANIAN,
        GERMAN,
        TURKISH,
        CZECH,
        THAILAND,
        INVOICE,
    )


class WaybillCreate(CdekModel):
    """Request to form a waybill (``POST /v2/print/orders``)."""

    orders: list[PrintOrder] = Field(min_length=1, description="Order list")
    copy_count: int = Field(
        default=2,
        description="Number of copies per sheet. ≥2 is recommended: for the cargo and the sender",
    )
    type: str | None = Field(
        default=None, description="Waybill form, Russian by default (see WaybillFormType)"
    )


class BarcodeCreate(CdekModel):
    """Request to form a package barcode (``POST /v2/print/barcodes``)."""

    orders: list[PrintOrder] = Field(min_length=1, description="Order list")
    copy_count: int = Field(default=1, description="Number of copies (1 by default)")
    format: PrintFormat | str = Field(
        default=PrintFormat.A4, description="Print format: A4, A5, A6, A7"
    )
    lang: str | None = Field(default=None, description="Form language in ISO 639-3: RUS or ENG")


class PrintStatus(CdekModel):
    """Status of a print file (``PrintStatusDto``)."""

    code: str | None = Field(default=None, description="Status code")
    name: str | None = Field(default=None, description="Status name")
    date_time: CdekDateTime | str | None = Field(
        default=None, description="Date when the status was set"
    )


class Waybill(CdekModel):
    """Waybill of an order (``WaybillDto``)."""

    uuid: str = Field(description="Identifier of the order waybill")
    orders: list[PrintOrder] | None = Field(default=None, description="Order list")
    copy_count: int | None = Field(default=None, description="Number of copies per sheet")
    type: str | None = Field(default=None, description="Waybill form")
    url: str | None = Field(default=None, description="File link — only in the ready status")
    statuses: list[PrintStatus] = Field(default_factory=list, description="Waybill statuses")

    @property
    def is_ready(self) -> bool:
        """Return whether the file is ready for download."""
        return bool(self.url)

    @property
    def state(self) -> str | None:
        """Return the code of the last formation status."""
        return self.statuses[-1].code if self.statuses else None


class Barcode(CdekModel):
    """Package barcode of an order (``BarcodeDto``)."""

    uuid: str = Field(description="Identifier of the package barcode file")
    orders: list[PrintOrder] | None = Field(default=None, description="Order list")
    copy_count: int | None = Field(default=None, description="Number of copies per sheet")
    format: PrintFormat | str | None = Field(default=None, description="Print format")
    url: str | None = Field(default=None, description="File link — only in the ready status")
    lang: str | None = Field(default=None, description="Form language (ISO 639-3), RUS by default")
    statuses: list[PrintStatus] = Field(default_factory=list, description="File statuses")

    @property
    def is_ready(self) -> bool:
        """Return whether the file is ready for download."""
        return bool(self.url)

    @property
    def state(self) -> str | None:
        """Return the code of the last formation status."""
        return self.statuses[-1].code if self.statuses else None


class WaybillResponse(ResponseEnvelope[Waybill]):
    """Response envelope of ``GET /v2/print/orders/{uuid}``."""


class BarcodeResponse(ResponseEnvelope[Barcode]):
    """Response envelope of ``GET /v2/print/barcodes/{uuid}``."""


class PrintTaskCreated(CdekModel):
    """Response to creating a print task (``entity`` of ``*PrintResponseDto``)."""

    uuid: str | None = Field(
        default=None, description="Print task identifier in the CDEK information system"
    )


class PrintTaskEnvelope(CdekModel):
    """Response envelope of ``POST /v2/print/{orders|barcodes}`` (HTTP 202)."""

    entity: PrintTaskCreated | None = Field(default=None, description="The created print task")
    requests: list[RequestInfo] | None = Field(default=None, description="Requests over the form")
    related_entities: list[RelatedEntity] | None = Field(
        default=None, description="Related entities"
    )

    @property
    def uuid(self) -> str | None:
        """Return the print task UUID."""
        return self.entity.uuid if self.entity else None
