"""Other API sections: reverse, receipts, passports, registries, photos, prealerts.

The methods are grouped in a single endpoint because they are used sporadically.
Paths and schemas are verified against the apidoc.cdek.ru OpenAPI specification:

=================================================  =============================
Method                                             Operation
=================================================  =============================
``POST /v2/reverse/availability``                  Reverse availability
``GET /v2/check``                                  Receipt information
``GET /v2/passport``                               Passport data status
``GET /v2/registries``                             COD payment registries
``POST /v2/photoDocument``                         Orders with ready photos
``GET /v2/photoDocument/{uuid}``                   Photo archive download (ZIP)
``POST /v2/prealert``                              Prealert registration
``GET /v2/prealert/{uuid}``                        Prealert information
``POST /v2/international/package/restrictions``    International restrictions
=================================================  =============================

Response models: :class:`cdekx.models.CheckResponse`, ``PassportResponse``,
``RegistriesResponse``, ``PhotoResponse``, ``RestrictionHintsResponse``,
:class:`PrealertTaskEnvelope`, :class:`PrealertEnvelope`; reverse returns
``None``, the photo archive returns ``bytes``.

Response shape
--------------

Most methods of this section answer with a "list with errors" instead of the
``{entity, requests}`` envelope — see :class:`cdekx.models.ListResponse`.
HTTP 200 does not guarantee success here: check ``response.has_errors``.

For ``POST /v2/reverse/availability`` a successful answer is an **empty body**
with code 200, while reverse unavailability arrives as HTTP 400, i.e. as an
:class:`cdekx.exceptions.ApiError` exception. That is why the method returns
``None``.

:meth:`MiscEndpoint.raw` remains an escape hatch for arbitrary requests.
"""

from __future__ import annotations

from typing import Any

from ..models.base import ResponseEnvelope, RootEntity
from ..models.misc import (
    CheckResponse,
    PassportClientLike,
    PassportResponse,
    PhotoRequest,
    PhotoResponse,
    Prealert,
    PrealertCreate,
    RegistriesResponse,
    RestrictionHintsResponse,
    RestrictionRequest,
    ReverseValidateRequest,
)
from .base import Endpoint, raise_if_invalid

__all__ = [
    "MiscEndpoint",
    "PrealertEnvelope",
    "PrealertTaskEnvelope",
]


class PrealertTaskEnvelope(ResponseEnvelope[RootEntity]):
    """Response envelope of ``POST /v2/prealert`` (HTTP 202, ``RegisterPrealertResponseDto``).

    The entity (``EntityDto``) holds only the prealert ``uuid`` — look at
    ``requests`` for the creation state.
    """


class PrealertEnvelope(ResponseEnvelope[Prealert]):
    """Response envelope of ``GET /v2/prealert/{uuid}`` (``GetPrealertResponseDto``).

    Note:
        Unlike the order envelope, the specification declares no
        ``related_entities`` here — only ``entity`` and ``requests``.

    """


class MiscEndpoint(Endpoint):
    """Sporadic API methods: receipts, passports, registries, photos, prealerts, reverse."""

    # -- reverse logistics --------------------------------------------------
    async def reverse_availability(self, request: ReverseValidateRequest | dict[str, Any]) -> None:
        """Check reverse availability before creating the forward order.

        ``POST /v2/reverse/availability``.
        The request carries the same data as order creation: direction, tariff,
        sender and recipient.

        Args:
            request: :class:`cdekx.models.ReverseValidateRequest` or a dict.
                ``tariff_code``, ``sender`` and ``recipient`` are required; the
                direction is ``from_location``/``to_location`` **or**
                ``shipment_point``/``delivery_point``.

        Returns:
            ``None`` — reverse is available (the API answers with an empty body
            and code 200).

        Raises:
            ApiError: reverse is unavailable or the request is invalid (HTTP 400
                with the reason described).

        Example:
            >>> await client.misc.reverse_availability({  # doctest: +SKIP
            ...     "tariff_code": 136,
            ...     "delivery_point": "MSK",
            ...     "from_location": {"code": 44, "address": "1 Test Street"},
            ...     "sender": {"contragent_type": "INDIVIDUAL", "phones": ["+79001234567"]},
            ...     "recipient": {"contragent_type": "INDIVIDUAL", "phones": ["+79007654321"]},
            ... })

        """
        return await self._request_empty(
            "POST", "/v2/reverse/availability", json_body=self._dump(request)
        )

    # -- receipts and payments ----------------------------------------------
    async def checks(
        self,
        *,
        order_uuid: str | None = None,
        cdek_number: str | None = None,
        date: str | None = None,
    ) -> CheckResponse:
        """Fiscal receipt information (``GET /v2/check``).

        Args:
            order_uuid: order UUID in the CDEK information system.
            cdek_number: CDEK order number.
            date: receipt creation date, ``yyyy-MM-dd``.

        Returns:
            :class:`cdekx.models.CheckResponse` with the ``check_info`` list.

        Raises:
            ValueError: none of the search parameters was given — the API
                answers HTTP 400 in that case, so the request is not sent at all.

        Note:
            Per the documentation each parameter is "required unless the others
            are given", i.e. at least one of the three is needed.

        """
        params: dict[str, Any] = {}
        if order_uuid:
            params["order_uuid"] = order_uuid
        if cdek_number:
            params["cdek_number"] = cdek_number
        if date:
            params["date"] = date
        if not params:
            raise ValueError(
                "GET /v2/check: at least one parameter required — order_uuid, cdek_number, date"
            )
        return await self._get_model(CheckResponse, "/v2/check", params=params)

    async def passports(
        self,
        *,
        order_uuid: str | None = None,
        cdek_number: str | None = None,
        client: PassportClientLike | None = None,
    ) -> PassportResponse:
        """Passport data information (``GET /v2/passport``).

        The method does **not** return the passport data itself — only a flag
        that the requirements for it are met (relevant for international orders).

        Args:
            order_uuid: order UUID.
            cdek_number: CDEK order number.
            client: whose data to return — ``SENDER``, ``RECEIVER`` or ``ALL``
                (see :class:`cdekx.types.enums.PassportClient`). If omitted,
                CDEK returns data for both the sender and the recipient.

        """
        params: dict[str, Any] = {}
        if order_uuid:
            params["order_uuid"] = order_uuid
        if cdek_number:
            params["cdek_number"] = cdek_number
        if client:
            params["client"] = str(client)
        return await self._get_model(PassportResponse, "/v2/passport", params=params or None)

    async def registries(self, date: str) -> RegistriesResponse:
        """Cash-on-delivery payment registries for a date (``GET /v2/registries``).

        Args:
            date: date in ``yyyy-MM-dd`` format. The parameter is **required**
                (the only one of this method): registries whose cash-on-delivery
                payment was transferred on that day are returned.

        """
        return await self._get_model(RegistriesResponse, "/v2/registries", params={"date": date})

    # -- document photos ----------------------------------------------------
    async def photo_ready_orders(self, request: PhotoRequest | dict[str, Any]) -> PhotoResponse:
        """Orders with ready document photos (``POST /v2/photoDocument``).

        Args:
            request: :class:`cdekx.models.PhotoRequest` or a dict — the period
                (``period_begin``/``period_end`` in ``yyyy-MM-dd'T'HH:mm:ssZ``
                format) and/or a list of orders.

        Returns:
            :class:`cdekx.models.PhotoResponse`; the archive is ready to be
            downloaded when ``status == "DONE"`` (see ``PhotoResponse.ready``).

        """
        return await self._post_model(
            PhotoResponse, "/v2/photoDocument", json_body=self._dump(request)
        )

    async def photo_archive(self, uuid: str) -> bytes:
        """Download the ready document photo archive (``GET /v2/photoDocument/{uuid}``).

        Args:
            uuid: archive identifier from ``PhotoReadyOrder.link``
                (see :attr:`cdekx.models.PhotoReadyOrder.archive_uuid`).

        Returns:
            ZIP archive content.

        Raises:
            NotFoundError: the archive is not ready yet or does not exist (HTTP 404).
            ApiError: access denied (403) or a gateway error (502).

        """
        return await self._get_bytes(f"/v2/photoDocument/{uuid}")

    # -- prealerts ----------------------------------------------------------
    async def prealert_create(
        self, prealert: PrealertCreate | dict[str, Any]
    ) -> PrealertTaskEnvelope:
        """Register a prealert (``POST /v2/prealert``, response 202).

        A prealert is required for international shipments: it describes handing
        a group of orders over to a specific office on a specific date.

        Args:
            prealert: :class:`cdekx.models.PrealertCreate` or a dict.
                ``planned_date``, ``shipment_point`` and ``orders`` are required.

        Returns:
            Task envelope with the prealert ``uuid``.

        Raises:
            ApiError: the prealert was rejected during validation
                (``requests[].state == INVALID``) — for example, the handover
                date is earlier than the contract allows or the office is unknown.

        """
        envelope = await self._post_model(
            PrealertTaskEnvelope, "/v2/prealert", json_body=self._dump(prealert)
        )
        raise_if_invalid(envelope, entity_name="prealert")
        return envelope

    async def prealert_get(self, uuid: str) -> PrealertEnvelope:
        """Prealert information (``GET /v2/prealert/{uuid}``).

        Once the prealert is closed, ``closed_date``, ``fact_shipment_point`` and
        package statuses appear in the response — they reveal discrepancies
        (see :attr:`cdekx.models.Prealert.discrepancies`).
        """
        return await self._get_model(PrealertEnvelope, f"/v2/prealert/{uuid}")

    # -- international restrictions ----------------------------------------
    async def international_restrictions(
        self, request: RestrictionRequest | dict[str, Any]
    ) -> RestrictionHintsResponse:
        """Restrictions for international orders.

        ``POST /v2/international/package/restrictions``. Checks weight and size
        parameters and the composition of attachments for the direction.

        Args:
            request: :class:`cdekx.models.RestrictionRequest` or a dict.

        Returns:
            :class:`cdekx.models.RestrictionHintsResponse`; the quick verdict is
            ``response.is_allowed`` and ``response.forbidden``.

        Note:
            The specification declares the response with content type ``*/*``
            (not ``application/json``) — this does not affect parsing.

        """
        return await self._post_model(
            RestrictionHintsResponse,
            "/v2/international/package/restrictions",
            json_body=self._dump(request),
        )

    # -- escape hatch -------------------------------------------------------
    async def raw(
        self,
        method: str,
        path: str,
        *,
        params: Any = None,
        json_body: Any = None,
        headers: Any = None,
    ) -> Any:
        """Perform an arbitrary API request (raw JSON).

        Use it when the method you need is not covered by the library yet — and
        file an issue or add the endpoint so that coverage catches up with the
        documentation (see ``docs/API_COVERAGE.md``).

        Example:
            >>> data = await client.misc.raw("GET", "/v2/location/cities")  # doctest: +SKIP

        """
        return await self._request(
            method, path, params=params, json_body=json_body, headers=headers
        )
