"""Cost calculator: ``/v2/calculator/*``.

Verified against the OpenAPI specification at apidoc.cdek.ru:

====================================  =======================================
Method                                Operation
====================================  =======================================
``POST /v2/calculator/tariff``        Calculation by tariff code
``POST /v2/calculator/tarifflist``    Calculation across available tariffs
``POST /v2/calculator/tariffAndService`` Calculation with extra services
``GET  /v2/calculator/alltariffs``    Tariffs available under the contract
====================================  =======================================

The customs-duty calculation method (``customsduty``) is absent from the
current specification — it only appeared in outdated documentation.
"""

from __future__ import annotations

from typing import Any

from ..models.base import ErrorInfo
from ..models.calculator import (
    AvailableTariffsResponse,
    TariffCalculation,
    TariffListRequest,
    TariffListResponse,
    TariffRequest,
    TariffWithServicesRequest,
    TariffWithServicesResponse,
)
from .base import Endpoint, parse_model_json

__all__ = ["CalculatorEndpoint"]


class CalculatorEndpoint(Endpoint):
    """Delivery cost and time calculation."""

    base_path = "/v2/calculator"

    async def tariff(self, request: TariffRequest | dict[str, Any]) -> TariffCalculation:
        """Calculate by tariff code (``POST /v2/calculator/tariff``).

        Args:
            request: a :class:`TariffRequest` model or a dict with the request body.

        Returns:
            The calculation result: cost, delivery time (business and calendar
            days), chargeable weight, extra services.

        Note:
            The calculator may answer HTTP 200 with errors inside — check
            :attr:`TariffCalculation.has_errors`.

        """
        return await self._post_model(
            TariffCalculation, f"{self.base_path}/tariff", json_body=self._dump(request)
        )

    async def tariff_list(self, request: TariffListRequest | dict[str, Any]) -> TariffListResponse:
        """Calculate across all available tariffs (``POST /v2/calculator/tarifflist``).

        Handy selections: :attr:`TariffListResponse.viable`,
        :meth:`TariffListResponse.best`, :meth:`TariffListResponse.fastest`.
        """
        return await self._post_model(
            TariffListResponse, f"{self.base_path}/tarifflist", json_body=self._dump(request)
        )

    async def tariff_and_service(
        self, request: TariffWithServicesRequest | dict[str, Any]
    ) -> TariffWithServicesResponse:
        """Calculate for available tariffs together with extra services.

        ``POST /v2/calculator/tariffAndService``. Unlike ``tarifflist``, it
        returns the cost **including** the extra services passed in, plus a
        success flag for each tariff.
        """
        return await self._post_model(
            TariffWithServicesResponse,
            f"{self.base_path}/tariffAndService",
            json_body=self._dump(request),
        )

    async def available_tariffs(self, *, lang: str | None = None) -> AvailableTariffsResponse:
        """Tariffs available under the contract (``GET /v2/calculator/alltariffs``).

        Args:
            lang: output language — sent in the ``X-User-Lang`` header (rus/eng/zho).

        """
        headers = {"X-User-Lang": lang} if lang else None
        response = await self._raw("GET", f"{self.base_path}/alltariffs", headers=headers)
        return parse_model_json(AvailableTariffsResponse, response.content)

    @staticmethod
    def errors_of(payload: Any) -> list[ErrorInfo]:
        """Parse ``errors`` out of a calculator response (returned with HTTP 200)."""
        if isinstance(payload, dict):
            raw = payload.get("errors") or []
            return [ErrorInfo.model_validate(e) for e in raw if isinstance(e, dict)]
        return []


# Note: /v2/calculator/customsduty is absent from the current specification,
# so customs-duty calculation is not implemented.
