"""The ``cdekx`` exception hierarchy.

Rules:

1. Every library failure is a ``CdekxError``; there is no need to catch ``Exception``.
2. An API response with a status >= 400 becomes an ``ApiError`` (or a subclass).
   The response body and the parsed error list are available as exception
   attributes, so nothing is lost.
3. Network failures and timeouts surface as ``TransportError`` only once retries
   are exhausted; otherwise the request is retried transparently (see ``RetryPolicy``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .types import ApiErrorDetail

__all__ = [
    "ApiError",
    "AuthError",
    "CdekxError",
    "ConfigError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "TimeoutExceeded",
    "TransportError",
    "ValidationError",
    "raise_for_status",
]


class CdekxError(Exception):
    """Base exception of the library."""


class ConfigError(CdekxError, ValueError):
    """Invalid client configuration (missing credentials, bad URL, and so on)."""


class TransportError(CdekxError):
    """Network error or timeout after retries have been exhausted."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        """Store the message and the original cause of the failure."""
        super().__init__(message)
        self.cause = cause


class TimeoutExceeded(TransportError):  # noqa: N818 - reads as a state, not an object
    """The request timed out."""


class ApiError(CdekxError):
    """The CDEK API returned an error (HTTP 4xx/5xx).

    Attributes:
        status_code: HTTP status of the response.
        errors: parsed entries of the ``errors`` array from the response body.
        body: the response body as-is (a ``dict``, or ``str`` when it is not JSON).
        request_id: ``X-Request-Id``/``traceparent`` from the headers, when present —
            handy when contacting CDEK support.

    """

    #: HTTP statuses mapped to this class.
    status_codes: tuple[int, ...] = ()

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        errors: Sequence[ApiErrorDetail] = (),
        body: Any = None,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Store the status, parsed errors, response body and request metadata."""
        super().__init__(message)
        self.status_code = status_code
        self.errors: tuple[ApiErrorDetail, ...] = tuple(errors)
        self.body = body
        self.request_id = request_id
        self.retry_after = retry_after

    @property
    def codes(self) -> tuple[str, ...]:
        """CDEK error codes (``error_validate_...`` and similar)."""
        return tuple(e.code for e in self.errors if e.code)

    def has_code(self, code: str) -> bool:
        """Check whether a specific error code is present."""
        return code in self.codes

    def __str__(self) -> str:
        """Representation in the form ``[HTTP 400] code: message``."""
        details = "; ".join(str(e) for e in self.errors) or super().__str__()
        return f"[HTTP {self.status_code}] {details}"


class AuthError(ApiError):
    """401/403 — bad credentials, or an expired/revoked token."""

    status_codes = (401, 403)


class NotFoundError(ApiError):
    """404 — entity not found."""

    status_codes = (404,)


class ValidationError(ApiError):
    """400/422 — the request failed validation on the CDEK side."""

    status_codes = (400, 422)


class RateLimitError(ApiError):
    """429 — rate limit exceeded (see ``retry_after``)."""

    status_codes = (429,)


class ServerError(ApiError):
    """5xx — an error on the CDEK side."""

    status_codes = (500, 501, 502, 503, 504, 505)


_ERROR_CLASSES: tuple[type[ApiError], ...] = (
    AuthError,
    NotFoundError,
    ValidationError,
    RateLimitError,
    ServerError,
)


def error_class_for(status_code: int) -> type[ApiError]:
    """Pick the most specific exception class for an HTTP status."""
    for cls in _ERROR_CLASSES:
        if status_code in cls.status_codes:
            return cls
    return ApiError


def raise_for_status(
    status_code: int,
    body: Any,
    *,
    headers: Mapping[str, str] | None = None,
) -> None:
    """Raise the appropriate exception when ``status_code`` >= 400."""
    if status_code < 400:
        return

    errors: list[ApiErrorDetail] = []
    message = ""
    if isinstance(body, dict):
        raw_errors = body.get("errors") or []
        if not isinstance(raw_errors, list):
            raw_errors = []
        if not raw_errors:
            # Asynchronous envelope response: errors live in requests[].errors
            # (for example, a 400 on POST /v2/orders with state=INVALID).
            requests_list = body.get("requests")
            if isinstance(requests_list, list):
                for req in requests_list:
                    if isinstance(req, dict) and isinstance(req.get("errors"), list):
                        raw_errors.extend(req["errors"])
        if raw_errors:
            from .types import ApiErrorDetail  # local import: keeps pydantic off the import path

            errors = [ApiErrorDetail.from_raw(e) for e in raw_errors]
        message = body.get("message") or ""
    elif isinstance(body, str):
        message = body.strip()

    if not message:
        message = "; ".join(str(e) for e in errors) or f"HTTP {status_code}"

    headers = headers or {}
    retry_after_raw = headers.get("retry-after") or headers.get("Retry-After")
    retry_after: float | None = None
    if retry_after_raw:
        try:
            retry_after = float(retry_after_raw)
        except ValueError:
            retry_after = None

    raise error_class_for(status_code)(
        message,
        status_code=status_code,
        errors=errors,
        body=body,
        request_id=headers.get("x-request-id") or headers.get("X-Request-Id"),
        retry_after=retry_after,
    )
