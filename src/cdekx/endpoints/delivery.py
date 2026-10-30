"""Offices and pickup points: ``/v2/deliverypoints``.

Verified against the OpenAPI specification at apidoc.cdek.ru: ``OfficeDto``
(the response is an array of objects, without an ``entity`` envelope),
``GET /v2/deliverypoints`` and ``GET /v2/deliverypoints/byPolygons``.

The API has no "offices within a radius of a point" search — a bounding-box
method is used instead: :meth:`DeliveryPointsEndpoint.by_polygon`.
"""

from __future__ import annotations

import builtins
from typing import Any

from ..exceptions import NotFoundError
from ..models.delivery import (
    DeliveryPoint,
    DeliveryPointFilter,
    DeliveryPointPolygon,
    DeliveryPointPolygonFilter,
)
from ..pagination import Paginator
from .base import Endpoint

__all__ = ["DeliveryPointsEndpoint"]


class DeliveryPointsEndpoint(Endpoint):
    """CDEK pickup points, parcel lockers and warehouses."""

    base_path = "/v2/deliverypoints"

    async def list(
        self,
        filter: DeliveryPointFilter | dict[str, Any] | None = None,  # noqa: A002
    ) -> builtins.list[DeliveryPoint]:
        """List offices by filter (``GET /v2/deliverypoints``) — a single page.

        Args:
            filter: selection criteria (city, type, payment, try-on, weight, dimensions).

        Note:
            The response can be large: use ``city_code``/``type``/``size``.

        """
        return await self._get_list(DeliveryPoint, self.base_path, params=self._query(filter))

    def paginate(
        self,
        filter: DeliveryPointFilter | dict[str, Any] | None = None,  # noqa: A002
        *,
        page_size: int = 500,
    ) -> Paginator[DeliveryPoint]:
        """Iterate over the office list page by page (``async for``)."""
        from ..pagination import Paginator

        return Paginator(
            fetch=self._fetch_page,
            model=DeliveryPoint,
            page_size=page_size,
            params=self._query(filter) or {},
        )

    async def get(self, code: str) -> DeliveryPoint:
        """Fetch an office by code.

        Raises:
            NotFoundError: no office with that code was found.

        """
        points = await self.list(DeliveryPointFilter(code=code))
        if not points:
            raise NotFoundError(f"delivery point {code!r} not found", status_code=404)
        return points[0]

    async def by_polygon(
        self,
        *,
        latitude_right_top: float,
        longitude_right_top: float,
        latitude_left_bottom: float,
        longitude_left_bottom: float,
        filter: DeliveryPointPolygonFilter | dict[str, Any] | None = None,  # noqa: A002
    ) -> builtins.list[DeliveryPoint]:
        """Offices inside a bounding box (``GET /v2/deliverypoints/byPolygons``).

        This is the standard way to find the nearest pickup points: define a box
        around the location and filter the result if needed. Coordinates carry up
        to 6 decimal places.

        Note:
            This method supports **fewer** filters than the office list: only
            ``type``, ``city_uuid``, ``have_cashless``, ``have_cash``,
            ``allowed_cod``, ``is_dressing_room``, ``weight_max``,
            ``weight_min`` and ``lang``. There is no pagination — every office in
            the box is returned. Use :class:`DeliveryPointPolygonFilter`.

        Args:
            latitude_right_top: latitude of the top-right corner.
            longitude_right_top: longitude of the top-right corner.
            latitude_left_bottom: latitude of the bottom-left corner.
            longitude_left_bottom: longitude of the bottom-left corner.
            filter: extra criteria (type, city, payment, try-on, weight).

        """
        polygon = DeliveryPointPolygon(
            lat_max=latitude_right_top,
            long_max=longitude_right_top,
            lat_min=latitude_left_bottom,
            long_min=longitude_left_bottom,
        )
        params: dict[str, Any] = {
            "latitude_right_top": polygon.lat_max,
            "longitude_right_top": polygon.long_max,
            "latitude_left_bottom": polygon.lat_min,
            "longitude_left_bottom": polygon.long_min,
        }
        params.update(self._query(filter) or {})
        return await self._get_list(DeliveryPoint, f"{self.base_path}/byPolygons", params=params)

    async def _fetch_page(self, params: Any) -> Any:
        """Load one page of the office list (for :class:`Paginator`)."""
        return await self._get(self.base_path, params=params)
