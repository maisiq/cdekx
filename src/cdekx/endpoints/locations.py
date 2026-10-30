"""Location directories: ``/v2/location/*``.

Verified against the OpenAPI specification at apidoc.cdek.ru:

======================================  =====================================
Method                                  Operation
======================================  =====================================
``GET /v2/location/cities``             List of settlements (paginated)
``GET /v2/location/regions``            List of regions (paginated)
``GET /v2/location/suggest/cities``     Location lookup by city name
``GET /v2/location/coordinates``        City resolution by coordinates
``GET /v2/location/postalcodes``        Postal codes of a city
======================================  =====================================
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models.locations import (
    City,
    CityByCoordinates,
    CityQuery,
    Postcodes,
    Region,
    RegionQuery,
    SuggestCity,
)
from ..pagination import Paginator
from .base import Endpoint

__all__ = ["LocationsEndpoint"]


class LocationsEndpoint(Endpoint):
    """Cities, regions, postal codes and location lookup."""

    base_path = "/v2/location"

    async def cities(self, query: CityQuery | dict[str, Any] | None = None) -> list[City]:
        """List of settlements (``GET /v2/location/cities``) — a single page.

        By default CDEK returns up to 1000 records; the maximum ``size`` is 10000.
        Use :meth:`paginate_cities` to fetch everything.
        """
        return await self._get_list(City, f"{self.base_path}/cities", params=self._query(query))

    def paginate_cities(
        self, query: CityQuery | dict[str, Any] | None = None, *, page_size: int = 1000
    ) -> Paginator[City]:
        """Iterate over all pages of the settlement list."""
        from ..pagination import Paginator

        return Paginator(
            fetch=self._fetch_cities_page,
            model=City,
            page_size=page_size,
            params=self._query(query) or {},
        )

    async def regions(self, query: RegionQuery | dict[str, Any] | None = None) -> list[Region]:
        """List of regions (``GET /v2/location/regions``) — a single page."""
        return await self._get_list(Region, f"{self.base_path}/regions", params=self._query(query))

    def paginate_regions(
        self, query: RegionQuery | dict[str, Any] | None = None, *, page_size: int = 1000
    ) -> Paginator[Region]:
        """Iterate over all pages of the region list."""
        from ..pagination import Paginator

        return Paginator(
            fetch=self._fetch_regions_page,
            model=Region,
            page_size=page_size,
            params=self._query(query) or {},
        )

    async def suggest_cities(
        self, name: str, *, country_code: str | None = None
    ) -> list[SuggestCity]:
        """Location lookup by city name (``GET /v2/location/suggest/cities``).

        Handy for address autocompletion: it accepts a partial match (unlike
        ``cities``, where ``city`` has to match exactly).

        Args:
            name: search string, for example "Novosib" (required).
            country_code: ISO 3166-1 alpha-2 country code.

        """
        params: dict[str, Any] = {"name": name}
        if country_code:
            params["country_code"] = country_code
        return await self._get_list(SuggestCity, f"{self.base_path}/suggest/cities", params=params)

    async def city_by_coordinates(self, latitude: float, longitude: float) -> CityByCoordinates:
        """Resolve a settlement by coordinates (``GET /v2/location/coordinates``)."""
        return await self._get_model(
            CityByCoordinates,
            f"{self.base_path}/coordinates",
            params={"latitude": latitude, "longitude": longitude},
        )

    async def postalcodes(self, city_code: int) -> Postcodes:
        """Postal codes of a city (``GET /v2/location/postalcodes?code=...``).

        The API response is an object ``{"code": ..., "postal_codes": ["101000", ...]}``
        (``PostcodesResponseDto``), not a list of entities: all the codes belong to
        a single city. Codes are strings; for some foreign cities the API returns
        ``[null]`` (see :attr:`Postcodes.values`).
        """
        return await self._get_model(
            Postcodes, f"{self.base_path}/postalcodes", params={"code": city_code}
        )

    # -- internals ----------------------------------------------------------
    async def _fetch_cities_page(self, params: Mapping[str, Any]) -> Any:
        """Load a page of the city list (for :class:`Paginator`)."""
        return await self._get(f"{self.base_path}/cities", params=params)

    async def _fetch_regions_page(self, params: Mapping[str, Any]) -> Any:
        """Load a page of the region list (for :class:`Paginator`)."""
        return await self._get(f"{self.base_path}/regions", params=params)
