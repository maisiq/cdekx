"""Base models, response envelopes and serialisation conventions.

``cdekx`` conventions (verified against the apidoc.cdek.ru OpenAPI specification):

* **snake_case everywhere** — field names match the API field names.
* **``extra="allow"``** — CDEK adds fields regularly; unknown ones are not lost
  and stay available through :attr:`CdekModel.extra`.
* **``None`` is not serialised** — :meth:`CdekModel.to_api` emits only the
  populated fields.
* **Separate request and response models.** At CDEK they differ: for example, a
  location in a request has no ``barcode``/``weight_calc``, while a contact in a
  response returns phones exactly as they were sent. We do not try to make them
  "universal".
* **Response envelope.** Almost all methods return
  ``{"entity": ..., "requests": [...], "related_entities": [...]}`` —
  see :class:`ResponseEnvelope`.
* **Second response shape** — "list + errors" (``{"<list>": [...],
  "errors": [...], "warnings": [...]}``) without an envelope: receipts, passport
  data, registries, document photos, restrictions and available courier days
  answer this way. See :class:`ListResponse`.
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from ..types import CdekDateTime

__all__ = [
    "ApiWarning",
    "CdekModel",
    "ErrorInfo",
    "ListResponse",
    "QueryModel",
    "RelatedEntity",
    "RequestInfo",
    "RequestState",
    "RequestType",
    "ResponseEnvelope",
]

EntityT = TypeVar("EntityT", bound=BaseModel)


class CdekModel(BaseModel):
    """Base of all ``cdekx`` models."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
        validate_default=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )

    @property
    def extra(self) -> dict[str, Any]:
        """Extra fields that the API returned but the model schema does not define."""
        return dict(self.__pydantic_extra__ or {})

    def to_api(self, *, exclude_none: bool = True, **kwargs: Any) -> dict[str, Any]:
        """Serialise the model into a CDEK request body."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=exclude_none, **kwargs)


class QueryModel(CdekModel):
    """Base for query parameters (filters) — serialised without ``None``."""

    def to_query(self) -> dict[str, Any]:
        """Serialise into query parameters, dropping empty values."""
        return self.to_api(exclude_none=True)


class ErrorInfo(CdekModel):
    """A processing error on the CDEK side (``ErrorDto1``/``ErrorDto2``)."""

    code: str | None = Field(default=None, description="Error code, for example v2_order_invalid")
    message: str | None = Field(default=None, description="Error description")
    additional_code: str | None = Field(
        default=None, description="Additional code for the support service"
    )

    def __str__(self) -> str:
        """Return a short human-readable representation."""
        return ": ".join(p for p in (self.code, self.message) if p) or repr(self)


class ApiWarning(CdekModel):
    """A CDEK warning (``WarningDto``) — the request was accepted with a caveat.

    Examples: ``v2_cost_change_by_tariff`` (the cost will change),
    ``v2_late_intake`` (a request for today placed after 15:00 is fulfilled
    tomorrow), ``v2_delivery_point_changed`` (redirection to another office).
    """

    code: str | None = Field(default=None, description="Warning code")
    message: str | None = Field(default=None, description="Warning text")

    def __str__(self) -> str:
        """Return a short human-readable representation."""
        return ": ".join(p for p in (self.code, self.message) if p) or repr(self)


class RequestState:
    """States of an asynchronous request (``requests[].state``).

    Important: the state belongs to the **request**, not to the entity.
    ``ACCEPTED`` does not guarantee that the order was created.
    """

    ACCEPTED = "ACCEPTED"
    """The request was accepted and passed the initial validation."""

    SUCCESSFUL = "SUCCESSFUL"
    """The entity was successfully created in the CDEK information system."""

    INVALID = "INVALID"
    """Error: fix the data and send the request again."""

    ALL: tuple[str, ...] = (ACCEPTED, SUCCESSFUL, INVALID)


class RequestType:
    """Request types (``requests[].type``)."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    AUTH = "AUTH"
    GET = "GET"
    CREATE_CLIENT_RETURN = "CREATE_CLIENT_RETURN"
    REFUSAL = "REFUSAL"


class RequestInfo(CdekModel):
    """Information about a request over an entity (``RequestDto``/``RequestInfoDto``)."""

    request_uuid: str | None = Field(
        default=None, description="Request identifier in the CDEK information system"
    )
    type: str | None = Field(default=None, description="Request type: CREATE, UPDATE, DELETE…")
    date_time: CdekDateTime | str | None = Field(
        default=None, description="Date and time when the state was set"
    )
    state: str | None = Field(default=None, description="State: ACCEPTED, SUCCESSFUL, INVALID")
    errors: list[ErrorInfo] | None = Field(default=None, description="Request execution errors")
    warnings: list[ApiWarning] | None = Field(
        default=None, description="Request execution warnings"
    )

    @property
    def is_successful(self) -> bool:
        """Return whether the request was processed successfully."""
        return self.state == RequestState.SUCCESSFUL

    @property
    def is_invalid(self) -> bool:
        """Return whether the request was rejected during processing."""
        return self.state == RequestState.INVALID

    @property
    def error_codes(self) -> tuple[str, ...]:
        """Return the request error codes."""
        return tuple(e.code for e in (self.errors or []) if e.code)


class RelatedEntity(CdekModel):
    """A related entity (``RelatedEntityDto``).

    Through ``related_entities`` CDEK returns reverse/return orders, client
    returns, as well as links to print forms (``url``).
    """

    uuid: str = Field(description="Related entity identifier")
    type: str = Field(
        description="Type: return_order, direct_order, reverse_order, waybill, barcode, "
        "client_direct_order and others"
    )
    url: str | None = Field(
        default=None, description="File link — only for the waybill and barcode types"
    )
    create_time: CdekDateTime | str | None = Field(default=None, description="Creation time")
    cdek_number: str | None = Field(
        default=None, description="CDEK order number — for return_order/direct_order/reverse_order"
    )
    date: str | None = Field(default=None, description="Delivery date agreed with the recipient")
    time_from: str | None = Field(default=None, description="Start of waiting for the courier")
    time_to: str | None = Field(default=None, description="End of waiting for the courier")


class RootEntity(CdekModel):
    """A minimal entity from an asynchronous operation response (``RootEntityDto``)."""

    uuid: str | None = Field(
        default=None, description="Entity identifier in the CDEK information system"
    )


class ResponseEnvelope(CdekModel, Generic[EntityT]):
    """The universal CDEK response envelope (``ResponseDto*``).

    Format::

        {
          "entity": {...},              // the entity the request was performed on
          "requests": [...],            // state of the asynchronous processing
          "related_entities": [...]     // related entities (reverse, print forms)
        }

    The ``requests`` and ``related_entities`` fields are present in responses of
    ``GET /v2/orders/{uuid}``, ``POST/PATCH/DELETE /v2/orders``,
    ``GET /v2/print/...`` and others.
    """

    entity: EntityT | None = Field(default=None, description="Response entity")
    requests: list[RequestInfo] | None = Field(
        default=None, description="Information about the requests over the entity"
    )
    related_entities: list[RelatedEntity] | None = Field(
        default=None, description="Related entities"
    )

    @property
    def uuid(self) -> str | None:
        """Return the entity UUID (a shortcut for ``entity.uuid``)."""
        entity = self.entity
        return getattr(entity, "uuid", None)

    @property
    def last_request(self) -> RequestInfo | None:
        """Return the last request of the list (usually there is only one)."""
        return self.requests[-1] if self.requests else None

    @property
    def state(self) -> str | None:
        """Return the state of the asynchronous processing: ACCEPTED / SUCCESSFUL / INVALID."""
        request = self.last_request
        return request.state if request else None

    @property
    def is_successful(self) -> bool:
        """Return whether the request was processed successfully."""
        return self.state == RequestState.SUCCESSFUL

    @property
    def is_invalid(self) -> bool:
        """Return whether the request was rejected: see ``errors`` of the last request."""
        return self.state == RequestState.INVALID

    @property
    def errors(self) -> list[ErrorInfo]:
        """Return the asynchronous processing errors (from ``requests[].errors``)."""
        result: list[ErrorInfo] = []
        for request in self.requests or []:
            result.extend(request.errors or [])
        return result

    @property
    def warnings(self) -> list[ApiWarning]:
        """Return the CDEK warnings (from ``requests[].warnings``)."""
        result: list[ApiWarning] = []
        for request in self.requests or []:
            result.extend(request.warnings or [])
        return result

    def related(self, entity_type: str) -> list[RelatedEntity]:
        """Return related entities of the given type (for example, ``"waybill"``)."""
        return [e for e in (self.related_entities or []) if e.type == entity_type]


class ListResponse(CdekModel):
    """Base of responses in the "list + errors" shape (no ``entity``/``requests`` envelope).

    CDEK uses two response shapes:

    1. the ``{entity, requests, related_entities}`` envelope — see
       :class:`ResponseEnvelope`;
    2. ``{"errors": [...], "warnings": [...], "<list>": [...]}`` — the methods
       ``GET /v2/check``, ``GET /v2/passport``, ``GET /v2/registries``,
       ``POST /v2/photoDocument``, ``POST /v2/international/package/restrictions``,
       ``POST /v2/intakes/availableDays``.

    In the second shape the HTTP status can be 200 while the errors lie in the
    body (a partial failure). Therefore check :attr:`has_errors`, not only the
    absence of an exception.

    Example:
        >>> checks = await client.misc.checks(cdek_number="1234567890")  # doctest: +SKIP
        >>> if checks.has_errors:  # doctest: +SKIP
        ...     print(checks.error_codes)  # doctest: +SKIP

    """

    errors: list[ErrorInfo] | None = Field(default=None, description="Error list")
    warnings: list[ApiWarning] | None = Field(default=None, description="Warning list")

    @property
    def has_errors(self) -> bool:
        """Return whether the response body has errors (the data may be incomplete)."""
        return bool(self.errors)

    @property
    def error_codes(self) -> tuple[str, ...]:
        """Return the response error codes, e.g. ``("v2_entity_not_found",)``."""
        return tuple(e.code for e in (self.errors or []) if e.code)
