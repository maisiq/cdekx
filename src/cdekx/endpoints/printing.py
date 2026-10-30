"""Print forms: ``/v2/print/*``.

Verified against the OpenAPI specification at apidoc.cdek.ru:

===================================  =========================================
Method                               Operation
===================================  =========================================
``POST /v2/print/orders``            Forming an order waybill (202)
``GET  /v2/print/orders/{uuid}``     Waybill status and url
``GET  /v2/print/orders/{uuid}.pdf`` Downloading the finished waybill
``POST /v2/print/barcodes``          Forming package barcodes for an order (202)
``GET  /v2/print/barcodes/{uuid}``   Barcode status and url
``GET  /v2/print/barcodes/{uuid}.pdf`` Downloading the finished barcode
===================================  =========================================

Important properties of the current API:

* orders are passed as objects ``{"order_uuid": ...}`` or ``{"cdek_number": ...}``
  in the **JSON body**, not as a UUID string in the query;
* status and download use different paths for the waybill and for the barcode;
* there is no "order copy" file (``copy_order``) in the API;
* downloading requires authentication: the file is served by ``GET .../{uuid}.pdf``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..exceptions import NotFoundError, TimeoutExceeded
from ..models.base import RequestState
from ..models.print import (
    Barcode,
    BarcodeCreate,
    BarcodeResponse,
    PrintOrder,
    PrintTaskEnvelope,
    Waybill,
    WaybillCreate,
    WaybillResponse,
)
from ..types.enums import PrintFormat
from .base import Endpoint, poll_until

__all__ = ["PrintEndpoint"]


def _to_print_orders(orders: Sequence[str | PrintOrder | dict[str, Any]]) -> list[PrintOrder]:
    """Coerce a list of UUIDs/numbers into :class:`PrintOrder`.

    Strings are interpreted as follows: a value that looks like a UUID becomes
    ``order_uuid``, otherwise ``cdek_number``.
    """
    result: list[PrintOrder] = []
    for item in orders:
        if isinstance(item, PrintOrder):
            result.append(item)
        elif isinstance(item, dict):
            result.append(PrintOrder.model_validate(item))
        elif isinstance(item, str):
            if _looks_like_uuid(item):
                result.append(PrintOrder(order_uuid=item))
            else:
                result.append(PrintOrder(cdek_number=item))
        else:  # pragma: no cover - guards against wrong types
            raise TypeError(f"unsupported order reference: {item!r}")
    return result


def _looks_like_uuid(value: str) -> bool:
    parts = value.split("-")
    return len(parts) == 5 and all(p.isalnum() for p in parts) and len(value) >= 32


class PrintEndpoint(Endpoint):
    """Order waybills and package barcodes."""

    base_path = "/v2/print"

    # -- waybill ----------------------------------------------------------
    async def waybill(
        self,
        orders: Sequence[str | PrintOrder | dict[str, Any]],
        *,
        copy_count: int = 2,
        type: str | None = None,  # noqa: A002 - the field name is dictated by the API
    ) -> PrintTaskEnvelope:
        """Form an order waybill (``POST /v2/print/orders``, answer 202).

        Args:
        orders: order UUIDs or CDEK numbers (plain strings are accepted for convenience).
        copy_count: number of copies per sheet. CDEK recommends >= 2: one for the
        cargo, one kept by the sender.
        type: waybill form type (``tpl_russia``, ``tpl_english``, ... — see
        :class:`cdekx.models.WaybillFormType`). Defaults to the Russian form.

        """
        body = WaybillCreate(orders=_to_print_orders(orders), copy_count=copy_count, type=type)
        return await self._post_model(
            PrintTaskEnvelope, f"{self.base_path}/orders", json_body=self._dump(body)
        )

    async def waybill_status(self, uuid: str) -> Waybill:
        """Waybill generation status (``GET /v2/print/orders/{uuid}``)."""
        envelope: WaybillResponse = await self._get_model(
            WaybillResponse, f"{self.base_path}/orders/{uuid}"
        )
        if envelope.entity is None:
            raise NotFoundError(f"waybill {uuid} has no entity in response", status_code=404)
        return envelope.entity

    async def waybill_pdf(self, uuid: str) -> bytes:
        """Download the finished waybill (``GET /v2/print/orders/{uuid}.pdf``)."""
        return await self._get_bytes(f"{self.base_path}/orders/{uuid}.pdf")

    # -- package barcode -----------------------------------------------------------
    async def barcodes(
        self,
        orders: Sequence[str | PrintOrder | dict[str, Any]],
        *,
        copy_count: int = 1,
        format: PrintFormat | str = PrintFormat.A4,  # noqa: A002
        lang: str | None = None,
    ) -> PrintTaskEnvelope:
        """Form package barcodes for an order (``POST /v2/print/barcodes``, answer 202).

        Args:
        orders: order UUIDs or CDEK numbers.
        copy_count: number of copies (1 by default).
        format: print format — A4, A5, A6, A7.
        lang: form language in ISO 639-3 (``RUS`` or ``ENG``).

        """
        body = BarcodeCreate(
            orders=_to_print_orders(orders), copy_count=copy_count, format=format, lang=lang
        )
        return await self._post_model(
            PrintTaskEnvelope, f"{self.base_path}/barcodes", json_body=self._dump(body)
        )

    async def barcode_status(self, uuid: str) -> Barcode:
        """Barcode generation status (``GET /v2/print/barcodes/{uuid}``)."""
        envelope: BarcodeResponse = await self._get_model(
            BarcodeResponse, f"{self.base_path}/barcodes/{uuid}"
        )
        if envelope.entity is None:
            raise NotFoundError(f"barcode {uuid} has no entity in response", status_code=404)
        return envelope.entity

    async def barcode_pdf(self, uuid: str) -> bytes:
        """Download the finished barcode file (``GET /v2/print/barcodes/{uuid}.pdf``)."""
        return await self._get_bytes(f"{self.base_path}/barcodes/{uuid}.pdf")

    # -- waiting and end-to-end flows ---------------------------------------
    async def wait_waybill(
        self, uuid: str, *, timeout: float = 90.0, interval: float = 2.0, backoff: float = 1.5
    ) -> Waybill:
        """Wait until the waybill is ready (a ``url`` appears).

        Raises:
        TimeoutExceeded: the file was not generated within the allotted time.

        """
        state: Waybill = await poll_until(
            lambda: self.waybill_status(uuid),
            lambda waybill: bool(waybill.url) or _failed(waybill.statuses),
            timeout=timeout,
            interval=interval,
            backoff=backoff,
            on_timeout=f"waybill {uuid} was not generated",
        )
        if not state.url:
            raise TimeoutExceeded(
                f"waybill {uuid} was not generated: {_last_status(state.statuses)}"
            )
        return state

    async def wait_barcode(
        self, uuid: str, *, timeout: float = 90.0, interval: float = 2.0, backoff: float = 1.5
    ) -> Barcode:
        """Wait until the package barcode file is ready.

        Raises:
        TimeoutExceeded: the file was not generated within the allotted time.

        """
        state: Barcode = await poll_until(
            lambda: self.barcode_status(uuid),
            lambda barcode: bool(barcode.url) or _failed(barcode.statuses),
            timeout=timeout,
            interval=interval,
            backoff=backoff,
            on_timeout=f"barcode {uuid} was not generated",
        )
        if not state.url:
            raise TimeoutExceeded(
                f"barcode {uuid} was not generated: {_last_status(state.statuses)}"
            )
        return state

    async def download_waybill(
        self,
        orders: Sequence[str | PrintOrder | dict[str, Any]],
        *,
        copy_count: int = 2,
        timeout: float = 90.0,
    ) -> bytes:
        """End-to-end flow: form a waybill, wait for it and download the PDF."""
        task = await self.waybill(orders, copy_count=copy_count)
        if not task.uuid:
            raise ValueError("CDEK did not return the uuid of the waybill print task")
        ready = await self.wait_waybill(task.uuid, timeout=timeout)
        return await self.waybill_pdf(ready.uuid)

    async def download_barcodes(
        self,
        orders: Sequence[str | PrintOrder | dict[str, Any]],
        *,
        format: PrintFormat | str = PrintFormat.A4,  # noqa: A002
        copy_count: int = 1,
        timeout: float = 90.0,
    ) -> bytes:
        """End-to-end flow: form package barcodes, wait for them and download the PDF."""
        task = await self.barcodes(orders, copy_count=copy_count, format=format)
        if not task.uuid:
            raise ValueError("CDEK did not return the uuid of the barcode print task")
        ready = await self.wait_barcode(task.uuid, timeout=timeout)
        return await self.barcode_pdf(ready.uuid)


def _failed(statuses: Any) -> bool:
    """Check whether generation finished with an error."""
    if not statuses:
        return False
    last = str(getattr(statuses[-1], "code", "") or "").upper()
    return last in {"ERROR", "FAILED", "INVALID"} or last == RequestState.INVALID


def _last_status(statuses: Any) -> str:
    """Return the text of the last generation status (for an error message)."""
    if not statuses:
        return "no statuses"
    last = statuses[-1]
    return f"{getattr(last, 'code', '?')} / {getattr(last, 'name', '')}".strip()
