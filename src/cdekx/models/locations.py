"""Models of the location directories: ``/v2/location/*``.

Verified against the apidoc.cdek.ru OpenAPI specification:
``V2LocationCityDto``, ``RegionsResponseDto``, ``SuggestCityResponseDto``,
``V2LocationCityByCoordinatesDto``, ``PostcodesResponseDto``.
"""

from __future__ import annotations

from pydantic import Field

from .base import CdekModel, QueryModel

__all__ = [
    "City",
    "CityByCoordinates",
    "CityQuery",
    "Postcodes",
    "Region",
    "RegionQuery",
    "SuggestCity",
]


DEPRECATED_FIAS_REGION = "Deprecated field - the values may be outdated"


class CityQuery(QueryModel):
    """Parameters of ``GET /v2/location/cities``.

    ``city`` must match **exactly**; for a partial match use
    ``GET /v2/location/suggest/cities``.
    """

    country_codes: list[str] | None = Field(
        default=None, description="Array of ISO 3166-1 alpha-2 country codes"
    )
    region_code: int | None = Field(default=None, description="Region code (CDEK directory)")
    fias_region_guid: str | None = Field(
        default=None,
        description="Unique FIAS identifier of the region",
        deprecated=DEPRECATED_FIAS_REGION,
    )
    kladr_code: str | None = Field(default=None, description="KLADR code of the settlement")
    fias_guid: str | None = Field(default=None, description="FIAS identifier of the settlement")
    postal_code: str | None = Field(default=None, description="Postal code")
    code: int | None = Field(default=None, description="CDEK settlement code")
    city: str | None = Field(default=None, description="Settlement name (exact)")
    payment_limit: float | None = Field(
        default=None,
        description="Limit on the cash-on-delivery amount. "
        "Special values: -1 — no limit; 0 — cash on delivery is not accepted",
    )
    size: int | None = Field(default=None, description="Page size (1000 by default, ≤10000)")
    page: int | None = Field(default=None, description="Page number (0 by default)")
    lang: str | None = Field(
        default=None, description="Response localisation language: rus/eng/zho"
    )


class RegionQuery(QueryModel):
    """Parameters of ``GET /v2/location/regions``."""

    country_codes: list[str] | None = Field(default=None, description="List of country codes")
    fias_region_guid: str | None = Field(
        default=None,
        description="Unique FIAS identifier of the region",
        deprecated=DEPRECATED_FIAS_REGION,
    )
    size: int | None = Field(default=None, description="Page size (1000 by default)")
    page: int | None = Field(default=None, description="Page number (0 by default)")
    lang: str | None = Field(
        default=None, description="Localisation: rus (eng and zho are available)"
    )


class City(CdekModel):
    """A settlement (``V2LocationCityDto``)."""

    code: int = Field(description="CDEK settlement code")
    city_uuid: str = Field(description="Settlement identifier in the CDEK information system")
    city: str = Field(description="Settlement name")
    fias_guid: str | None = Field(default=None, description="FIAS identifier")
    country_code: str = Field(description="ISO 3166-1 alpha-2 country code")
    country: str = Field(description="Country name")
    #: The specification declares the field as required, but the real API omits
    #: it (together with region_code/sub_region/time_zone) for foreign
    #: "cities" — for example, code=176 (UAE). Hence the relaxed type.
    region: str | None = Field(default=None, description="Region name")
    region_code: int | None = Field(default=None, description="CDEK region code")
    fias_region_guid: str | None = Field(
        default=None,
        description="Unique FIAS identifier of the region of the settlement",
        deprecated=DEPRECATED_FIAS_REGION,
    )
    sub_region: str | None = Field(default=None, description="Name of the region district")
    longitude: float | None = Field(default=None, description="Longitude of the centre")
    latitude: float | None = Field(default=None, description="Latitude of the centre")
    time_zone: str | None = Field(default=None, description="Time zone")
    payment_limit: float = Field(
        description="Limit on the cash-on-delivery amount in the settlement. "
        "Special values: -1 — no limit; 0 — cash on delivery is not accepted"
    )

    # Note: the V2LocationCityDto schema has no kladr_code and postal_code —
    # city postcodes are returned by the separate GET /v2/location/postalcodes.
    # If the API returns them anyway, the values land in `.extra` (extra="allow").


class CityByCoordinates(CdekModel):
    """Response of ``GET /v2/location/coordinates`` (``V2LocationCityByCoordinatesDto``)."""

    code: int = Field(description="CDEK settlement code")
    city_uuid: str = Field(description="Settlement identifier in the CDEK information system")
    city: str = Field(description="Settlement name")
    fias_guid: str | None = Field(default=None, description="FIAS identifier")


class SuggestCity(CdekModel):
    """Result of a location suggestion by name (``SuggestCityResponseDto``)."""

    city_uuid: str = Field(description="CDEK settlement identifier")
    code: int = Field(description="CDEK settlement code")
    full_name: str = Field(description="Full name: city, district, region")
    country_code: str = Field(description="ISO 3166-1 alpha-2 country code")


class Region(CdekModel):
    """A region (``RegionsResponseDto``)."""

    country_code: str = Field(description="ISO 3166-1 alpha-2 country code")
    country: str = Field(description="Name of the region country")
    region: str = Field(description="Region name")
    region_code: int | None = Field(default=None, description="CDEK region code")
    fias_region_guid: str | None = Field(
        default=None,
        description="Unique FIAS identifier of the region",
        deprecated=DEPRECATED_FIAS_REGION,
    )


class Postcodes(CdekModel):
    """City postcodes — the response of ``GET /v2/location/postalcodes``.

    Corresponds to ``PostcodesResponseDto``: an object ``{code, postal_codes}``,
    not a list of entities. All postcodes belong to a single city, so a separate
    model per postcode would be redundant.

    Note: for foreign "cities" the API returns ``[null]`` (verified on code=176,
    UAE) — hence ``str | None`` in the elements.
    """

    code: int = Field(description="Code of the city the postcodes belong to")
    postal_codes: list[str | None] = Field(default_factory=list, description="City postcodes")

    @property
    def values(self) -> list[str]:
        """Return postcodes without ``None`` (the API answers ``[null]`` for some cities)."""
        return [code for code in self.postal_codes if code is not None]
