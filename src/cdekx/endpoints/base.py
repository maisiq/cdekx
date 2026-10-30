"""Endpoint plumbing: transport helpers, envelope parsing, task polling."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from ..exceptions import ApiError, CdekxError, TimeoutExceeded
from ..models.base import CdekModel, ErrorInfo, RequestState
from ..types import ApiErrorDetail

__all__ = [
    "Endpoint",
    "ResponseParseError",
    "parse_envelope",
    "parse_list",
    "parse_list_json",
    "parse_model",
    "parse_model_json",
    "poll_until",
    "raise_if_invalid",
    "unwrap_entities",
]

ModelT = TypeVar("ModelT", bound=BaseModel)
EnvelopeT = TypeVar("EnvelopeT", bound=CdekModel)


class ResponseParseError(CdekxError, ValueError):
    """The API response does not match the expected schema.

    Raised when CDEK has changed the contract. The exception keeps the raw data
    (``raw``) so the problem can be diagnosed and reported.
    """

    def __init__(self, message: str, *, raw: Any = None, cause: Exception | None = None) -> None:
        """Store the message, the raw API response and the original validation error."""
        super().__init__(message)
        self.raw = raw
        self.cause = cause


class Endpoint:
    """Base class of all resource endpoints.

    Endpoints are thin wrappers: they know the API path, the parameters and the
    response model, but nothing about authentication, retries or connection
    pooling.
    """

    #: Path prefix of the resource, for example ``/v2/orders``.
    base_path: str = ""

    def __init__(self, http: Any) -> None:
        """Bind the endpoint to an HTTP client (``CdekClient`` normally does this)."""
        self._http = http

    @property
    def http(self) -> Any:
        """The HTTP client (for non-standard requests and tests)."""
        return self._http

    # -- requests -----------------------------------------------------------
    async def _get(self, path: str, *, params: Any = None, auth: bool = True) -> Any:
        """GET with a JSON response."""
        return await self._http.request_json("GET", path, params=params, auth=auth)

    async def _post(self, path: str, *, json_body: Any = None, params: Any = None) -> Any:
        """POST with a JSON response."""
        return await self._http.request_json("POST", path, json_body=json_body, params=params)

    async def _put(self, path: str, *, json_body: Any = None) -> Any:
        """PUT with a JSON response."""
        return await self._http.request_json("PUT", path, json_body=json_body)

    async def _patch(self, path: str, *, json_body: Any = None) -> Any:
        """PATCH with a JSON response."""
        return await self._http.request_json("PATCH", path, json_body=json_body)

    async def _delete(self, path: str, *, params: Any = None) -> Any:
        """DELETE with a JSON response."""
        return await self._http.request_json("DELETE", path, params=params)

    async def _get_bytes(self, path: str, *, params: Any = None) -> bytes:
        """GET with a binary response (PDF)."""
        data: bytes = await self._http.request_bytes("GET", path, params=params)
        return data

    async def _request_empty(
        self, method: str, path: str, *, json_body: Any = None, params: Any = None
    ) -> None:
        """Perform a request whose successful response is an empty body (HTTP 200/204).

        ``POST /v2/reverse/availability`` works this way: reverse availability is
        expressed by the **absence** of an error. Statuses >= 400 are handled by
        :meth:`HttpClient.request_raw`, so all that is left here is to return
        ``None``.
        """
        await self._raw(method, path, json_body=json_body, params=params)
        return

    # -- fast path: body straight into the model (model_validate_json) -------
    async def _raw(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform a request and return the raw response (:class:`Response`)."""
        return await self._http.request_raw(method.upper(), path, **kwargs)

    async def _get_model(self, model: type[ModelT], path: str, *, params: Any = None) -> ModelT:
        """GET and parse the body straight into a model (no ``json.loads``)."""
        response = await self._raw("GET", path, params=params)
        return parse_model_json(model, response.content)

    async def _post_model(self, model: type[ModelT], path: str, *, json_body: Any = None) -> ModelT:
        """POST and parse the body straight into a model."""
        response = await self._raw("POST", path, json_body=json_body)
        return parse_model_json(model, response.content)

    async def _patch_model(
        self, model: type[ModelT], path: str, *, json_body: Any = None
    ) -> ModelT:
        """PATCH and parse the body straight into a model."""
        response = await self._raw("PATCH", path, json_body=json_body)
        return parse_model_json(model, response.content)

    async def _delete_model(self, model: type[ModelT], path: str) -> ModelT:
        """DELETE and parse the body straight into a model."""
        response = await self._raw("DELETE", path)
        return parse_model_json(model, response.content)

    async def _get_list(
        self, model: type[ModelT], path: str, *, params: Any = None, key: str = "entities"
    ) -> list[ModelT]:
        """GET and parse the body straight into a list of models (single pass)."""
        response = await self._raw("GET", path, params=params)
        return parse_list_json(model, response.content, key=key)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an arbitrary request (escape hatch)."""
        return await self._http.request_json(method.upper(), path, **kwargs)

    # -- serialisation ------------------------------------------------------
    @staticmethod
    def _dump(model: BaseModel | dict[str, Any] | None, *, exclude_none: bool = True) -> Any:
        """Turn a pydantic model or dict into a JSON-compatible object."""
        if model is None:
            return None
        if isinstance(model, BaseModel):
            return model.model_dump(mode="json", by_alias=True, exclude_none=exclude_none)
        return model

    @staticmethod
    def _query(model: BaseModel | dict[str, Any] | None) -> dict[str, Any] | None:
        """Turn a filter model into query parameters."""
        if model is None:
            return None
        if isinstance(model, BaseModel):
            return model.model_dump(mode="json", by_alias=True, exclude_none=True)
        return {k: v for k, v in model.items() if v is not None}


# --- response parsing -------------------------------------------------------
# CDEK returns data in several shapes:
#   * an envelope {"entity": ..., "requests": [...], "related_entities": [...]}
#     — almost every entity operation;
#   * a bare array — directories (cities, offices);
#   * {"errors": [...], "warnings": [...]} with HTTP 400;
#   * HTTP 200 with errors inside — the calculator.


def unwrap_entity(payload: Any) -> Any:
    """Return ``entity`` from a response envelope (or the payload as-is)."""
    if isinstance(payload, dict) and "entity" in payload:
        return payload["entity"]
    return payload


def unwrap_entities(payload: Any, *, key: str = "entities") -> list[Any]:
    """Extract a list of entities from a response of any shape."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for candidate in (key, "entity", "items", "data", "tariff_codes"):
            value = payload.get(candidate)
            if isinstance(value, list):
                return value
            if isinstance(value, dict) and candidate == "entity":
                return [value]
        return [payload]
    return [payload]


def parse_model(model: type[ModelT], payload: Any, *, unwrap: bool = True) -> ModelT:
    """Parse an object into a model, unwrapping ``entity`` by default.

    Args:
        model: pydantic model class.
        payload: raw JSON.
        unwrap: take the value of the ``entity`` key when present.

    Raises:
        ResponseParseError: the response schema did not match the model.

    """
    data = unwrap_entity(payload) if unwrap else payload
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ResponseParseError(
            f"failed to parse {model.__name__}: {exc}", raw=data, cause=exc
        ) from exc


def parse_model_json(model: type[ModelT], content: bytes | str) -> ModelT:
    """Parse the **raw response body** straight into a model.

    Uses ``model_validate_json``: pydantic parses the JSON with its Rust parser in
    a single pass, without an intermediate ``json.loads`` and dict. On CDEK
    responses this gives ~1.7x for a single entity and ~1.9x for large lists
    (see ``benchmarks/parse_benchmark.py``).

    Args:
        model: pydantic model class (including a parameterised envelope such as
            ``ResponseEnvelope[Order]``).
        content: response body as bytes or str.

    Raises:
        ResponseParseError: the body is empty or does not match the schema.

    """
    if not content:
        raise ResponseParseError(
            f"{_model_name(model)}: the API returned an empty body", raw=content
        )
    try:
        return model.model_validate_json(content)
    except ValidationError as exc:
        raise ResponseParseError(
            f"failed to parse {_model_name(model)}: {exc}", raw=_preview(content), cause=exc
        ) from exc
    except ValueError as exc:  # invalid JSON
        raise ResponseParseError(
            f"{_model_name(model)}: response is not valid JSON: {exc}",
            raw=_preview(content),
            cause=exc,
        ) from exc


def parse_list_json(
    model: type[ModelT], content: bytes | str, *, key: str = "entities"
) -> list[ModelT]:
    """Parse the **raw response body** into a list of models in a single pass.

    When the response is an envelope (``{"entity": ...}`` / ``{"entities": [...]}``)
    the fast path is unavailable and the body is parsed via :func:`parse_list`.
    """
    if _starts_with_array(content):
        try:
            # The whole list is parsed by a single Rust-parser call. Per-item
            # validation (`for item in ...: model.model_validate(item)`) cancels
            # out the gain: see benchmarks/parse_benchmark.py for measurements.
            adapter: TypeAdapter[Any] = TypeAdapter(list[model])  # type: ignore[valid-type]
            return cast("list[ModelT]", adapter.validate_json(content))
        except ValidationError as exc:
            raise ResponseParseError(
                f"failed to parse list[{model.__name__}]: {exc}",
                raw=_preview(content),
                cause=exc,
            ) from exc
        except ValueError as exc:
            raise ResponseParseError(
                f"list[{model.__name__}]: response is not valid JSON: {exc}",
                raw=_preview(content),
                cause=exc,
            ) from exc

    # an envelope or another shape — the generic path via json.loads
    import json

    try:
        payload = json.loads(content) if content else None
    except ValueError as exc:
        raise ResponseParseError(
            f"list[{model.__name__}]: response is not valid JSON: {exc}",
            raw=_preview(content),
            cause=exc,
        ) from exc
    return parse_list(model, payload, key=key)


def _starts_with_array(content: bytes | str) -> bool:
    """Check whether the response body starts with a JSON array (fast path)."""
    if isinstance(content, bytes):
        return content.lstrip().startswith(b"[")
    return content.lstrip().startswith("[")


def _model_name(model: Any) -> str:
    """Return a human-readable model name (including parameterised generics)."""
    return getattr(model, "__name__", None) or str(model)


def _preview(content: bytes | str, limit: int = 500) -> Any:
    """Return a snippet of the response body for diagnostics (it can be megabytes)."""
    if isinstance(content, bytes):
        return content[:limit].decode("utf-8", errors="replace")
    return content[:limit]


def parse_envelope(envelope: type[EnvelopeT], payload: Any) -> EnvelopeT:
    """Populate a :class:`ResponseEnvelope` from a raw response.

    Args:
        envelope: envelope class, for example ``ResponseEnvelope[Order]``.
        payload: raw JSON of the CDEK response.

    """
    try:
        return envelope.model_validate(payload)
    except ValidationError as exc:
        raise ResponseParseError(
            f"failed to parse {getattr(envelope, '__name__', envelope)}: {exc}",
            raw=payload,
            cause=exc,
        ) from exc


def parse_list(model: type[ModelT], payload: Any, *, key: str = "entities") -> list[ModelT]:
    """Parse a list of objects into a list of models."""
    items = unwrap_entities(payload, key=key)
    try:
        return [model.model_validate(item) for item in items]
    except ValidationError as exc:
        raise ResponseParseError(
            f"failed to parse list[{model.__name__}]: {exc}", raw=items, cause=exc
        ) from exc


def parse_errors(payload: Any) -> list[ErrorInfo]:
    """Extract ``errors`` from a payload returned with HTTP 200."""
    if isinstance(payload, dict):
        raw = payload.get("errors")
        if isinstance(raw, list):
            return [ErrorInfo.model_validate(item) for item in raw if isinstance(item, dict)]
    return []


async def poll_until(
    fetch: Callable[[], Awaitable[Any]],
    is_done: Callable[[Any], bool],
    *,
    timeout: float = 60.0,
    interval: float = 1.0,
    backoff: float = 1.5,
    max_interval: float = 5.0,
    on_timeout: str = "the operation did not complete",
) -> Any:
    """Poll ``fetch`` until ``is_done`` holds or the timeout expires.

    Asynchronous processing at CDEK usually takes 200-500 ms, but up to 30-60
    seconds under peak load. The documentation recommends waiting 2-3 seconds
    before the first poll.

    Args:
        fetch: argument-less coroutine returning the fresh state.
        is_done: completion predicate (success or an unrecoverable error).
        timeout: maximum time to wait, in seconds.
        interval: initial pause between polls, in seconds.
        backoff: pause multiplier.
        max_interval: upper bound of the pause, in seconds.
        on_timeout: message of the exception raised on timeout.

    Returns:
        The state for which the ``is_done`` predicate returned true.

    Raises:
        TimeoutExceeded: the state did not become final within the allotted time.

    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    delay = interval

    while True:
        state = await fetch()
        if is_done(state):
            return state
        if loop.time() + delay > deadline:
            raise TimeoutExceeded(f"{on_timeout} within {timeout} s")
        await asyncio.sleep(delay)
        delay = min(delay * backoff, max_interval)


def raise_if_invalid(state: Any, *, entity_name: str = "entity") -> None:
    """Raise :class:`ApiError` when an asynchronous request was rejected (``INVALID``)."""
    requests = getattr(state, "requests", None) or []
    invalid = [r for r in requests if r.state == RequestState.INVALID]
    if not invalid:
        return
    errors: list[ErrorInfo] = []
    for request in invalid:
        errors.extend(request.errors or [])
    details = [
        ApiErrorDetail(code=e.code, message=e.message, field=None, value=e.additional_code)
        for e in errors
    ]
    raise ApiError(
        f"{entity_name} was rejected: " + ("; ".join(str(e) for e in errors) or "INVALID"),
        status_code=202,
        errors=details,
        body={"requests": [r.to_api() for r in invalid]},
    )
