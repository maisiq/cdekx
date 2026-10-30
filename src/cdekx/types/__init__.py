"""Primitives and shared types that depend on neither the HTTP layer nor the models.

The module is deliberately kept at the bottom of the import graph: ``exceptions``,
``models`` and ``_http`` can all import it without risking circular dependencies.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any, TypeVar

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - Python 3.10

    class StrEnum(str, Enum):
        """A minimal backport of ``enum.StrEnum`` for Python 3.10.

        Reproduces the key behaviour of the standard class: ``str(member)``
        returns the value instead of ``"CLASS.MEMBER"``.
        """

        def __str__(self) -> str:
            """Return the string value of the enum member."""
            return str(self.value)


from pydantic import BeforeValidator, Field, PlainSerializer

T = TypeVar("T")

__all__ = [
    "ApiErrorDetail",
    "CdekDate",
    "CdekDateTime",
    "CdekDateTimeOut",
    "Environment",
    "Json",
    "QueryParams",
    "StrEnum",
    "coerce_environment",
    "to_cdek_date",
    "to_cdek_datetime",
]

#: A raw JSON object exactly as the API returns it.
Json = dict[str, Any]
#: Query parameters of a request.
QueryParams = Mapping[str, Any]


class Environment(StrEnum):
    """CDEK API environment."""

    PRODUCTION = "production"
    """Production environment — ``https://api.cdek.ru``."""

    SANDBOX = "sandbox"
    """Sandbox environment — ``https://api.edu.cdek.ru``."""

    @property
    def base_url(self) -> str:
        """Base URL of the environment (without a trailing slash)."""
        return _BASE_URLS[self]


def coerce_environment(value: Environment | str | None, default: Environment) -> Environment:
    """Coerce an arbitrary value (``"sandbox"``, ``None``) to an :class:`Environment`.

    Args:
        value: a string or an enum member; ``None`` means take ``default``.
        default: the fallback value.

    """
    if value is None:
        return default
    return Environment(value)


_BASE_URLS: dict[Environment, str] = {
    Environment.PRODUCTION: "https://api.cdek.ru",
    Environment.SANDBOX: "https://api.edu.cdek.ru",
}


@dataclass(frozen=True, slots=True)
class ApiErrorDetail:
    """An entry of the ``errors`` array in a CDEK response.

    CDEK returns errors in two places:

    * an HTTP 4xx/5xx status plus a ``{"errors": [...]}`` body — the request was
      rejected;
    * HTTP 200 with ``errors`` inside the payload (for example when the
      calculator could not price some of the extra services).

    That is why an error detail is a standalone type rather than part of an
    exception.
    """

    code: str | None = None
    message: str | None = None
    field: str | None = None
    value: Any = None
    additional_code: str | None = None

    @classmethod
    def from_raw(cls, raw: Any) -> ApiErrorDetail:
        """Build an error detail from an arbitrary JSON value.

        Tolerant of the format: different CDEK methods return either an object
        or a plain string.
        """
        if isinstance(raw, Mapping):
            known = {
                f: raw.get(f) for f in ("code", "message", "field", "value", "additional_code")
            }
            extra = {k: v for k, v in raw.items() if k not in known}
            detail = cls(**known)
            return detail.with_extra(extra) if extra else detail
        return cls(message=str(raw))

    def with_extra(self, extra: Mapping[str, Any]) -> ApiErrorDetail:
        """Return a copy that keeps unknown fields (folded into ``message``)."""
        if not extra:
            return self
        suffix = ", ".join(f"{k}={v}" for k, v in sorted(extra.items()))
        message = f"{self.message} ({suffix})" if self.message else suffix
        return type(self)(
            code=self.code,
            message=message,
            field=self.field,
            value=self.value,
            additional_code=self.additional_code,
        )

    def __str__(self) -> str:
        """Short human-readable representation of the error."""
        parts = [p for p in (self.code, self.message) if p]
        return ": ".join(parts) or repr(self)


@dataclass(slots=True)
class Page:
    """A page of entities returned by the API.

    CDEK uses page-based pagination with the ``page`` (0-based) and ``size``
    parameters.
    """

    items: list[Any] = field(default_factory=list)
    page: int = 0
    size: int = 0
    total: int | None = None

    @property
    def has_more(self) -> bool:
        """Whether there is presumably a next page."""
        if self.total is not None:
            return (self.page + 1) * self.size < self.total
        return len(self.items) >= self.size > 0


# --- datetime ---------------------------------------------------------------
# CDEK returns dates in ISO 8601 with an offset: "2024-05-01T12:30:00+0300".
# ``datetime.fromisoformat`` on Python < 3.11 does not understand that offset,
# so the value is normalised before parsing.


def _normalize_offset(value: str) -> str:
    """Turn ``+0300`` into ``+03:00`` when Python cannot handle it itself."""
    if len(value) >= 5 and value[-5] in "+-" and value[-3] != ":":
        return value[:-2] + ":" + value[-2:]
    return value


def to_cdek_datetime(value: Any) -> Any:
    """``BeforeValidator``: leniently coerce a value to ``datetime``."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(_normalize_offset(text))
        except ValueError:
            # for example "2024-05-01 12:30:00", or an epoch number as a string
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
    return value


def to_cdek_date(value: Any) -> Any:
    """``BeforeValidator``: leniently coerce a value to ``date``."""
    if isinstance(value, str):
        text = value.strip()[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return value
    return value


CdekDateTime = Annotated[datetime, BeforeValidator(to_cdek_datetime)]
"""CDEK date/time: ISO 8601, timezone-aware, lenient parsing."""

CdekDate = Annotated[date, BeforeValidator(to_cdek_date)]
"""CDEK date: ``YYYY-MM-DD``."""


def to_cdek_datetime_str(value: Any) -> Any:
    """``PlainSerializer``: ``datetime`` to a string in the CDEK format.

    CDEK expects ``yyyy-MM-dd'T'HH:mm:ssZ`` (see ``PhotoRequestDto.period_begin``
    and ``RegisterPrealertRequestDto.planned_date``), where ``Z`` is an offset
    such as ``+0000`` or ``+0300`` **without a colon**. The standard
    ``datetime.isoformat()`` emits ``+00:00``/``Z``, which does not match, so
    these fields are serialised manually.

    Values that arrived as strings pass through unchanged: whatever was given is
    what goes to the API.
    """
    if isinstance(value, datetime):
        text = value.strftime("%Y-%m-%dT%H:%M:%S")
        if value.utcoffset() is not None:
            text += value.strftime("%z") or "+0000"
        return text
    return value


CdekDateTimeOut = Annotated[CdekDateTime, PlainSerializer(to_cdek_datetime_str, return_type=Any)]
"""CDEK date/time for request bodies: lenient parsing, ``+0300`` format."""


def money_field(*, description: str = "") -> Any:
    """Money field: CDEK returns a ``float``, but strings appear in JSON too."""
    return Field(default=None, description=description)
