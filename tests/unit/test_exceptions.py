"""Тесты разбора ошибок API и иерархии исключений."""

from __future__ import annotations

from typing import Any

import pytest

from cdekx import (
    ApiError,
    AuthError,
    CdekxError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from cdekx.exceptions import error_class_for, raise_for_status
from cdekx.types import ApiErrorDetail


def test_error_detail_parses_object() -> None:
    detail = ApiErrorDetail.from_raw({"code": "E1", "message": "текст", "field": "number"})
    assert detail.code == "E1"
    assert detail.message == "текст"
    assert detail.field == "number"
    assert str(detail) == "E1: текст"


def test_error_detail_tolerates_string() -> None:
    detail = ApiErrorDetail.from_raw("просто строка")
    assert detail.message == "просто строка"
    assert detail.code is None


def test_error_detail_keeps_unknown_keys() -> None:
    detail = ApiErrorDetail.from_raw({"code": "E1", "message": "m", "extra_key": 5})
    assert "extra_key=5" in str(detail)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, ValidationError),
        (401, AuthError),
        (403, AuthError),
        (404, NotFoundError),
        (422, ValidationError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
        (418, ApiError),
    ],
)
def test_status_maps_to_error_class(status: int, expected: type[ApiError]) -> None:
    assert error_class_for(status) is expected


def test_raise_for_status_noop_on_success() -> None:
    assert raise_for_status(200, {"ok": True}) is None
    assert raise_for_status(204, None) is None


def test_raise_for_status_parses_errors_array() -> None:
    body = {
        "errors": [
            {"code": "error_validate_1", "message": "первая"},
            {"code": "error_validate_2", "message": "вторая"},
        ]
    }
    with pytest.raises(ValidationError) as exc_info:
        raise_for_status(400, body)

    error = exc_info.value
    assert error.codes == ("error_validate_1", "error_validate_2")
    assert error.has_code("error_validate_2")
    assert not error.has_code("error_validate_3")
    assert error.body == body


def test_raise_for_status_extracts_errors_from_request_envelope() -> None:
    """400 на POST /v2/orders: ошибки лежат в requests[].errors, а не на верхнем уровне."""
    body = {
        "requests": [
            {
                "type": "CREATE",
                "date_time": "2026-10-27T16:09:15+0000",
                "state": "INVALID",
                "errors": [
                    {"code": "v2_field_is_empty", "message": "[packages[0].items] is empty"}
                ],
            }
        ],
        "related_entities": [],
    }
    with pytest.raises(ValidationError) as exc_info:
        raise_for_status(400, body)

    error = exc_info.value
    assert error.codes == ("v2_field_is_empty",)
    assert "[packages[0].items] is empty" in str(error)
    assert error.body == body


def test_raise_for_status_prefers_toplevel_errors_over_envelope() -> None:
    body = {
        "errors": [{"code": "top_level", "message": "верхний уровень"}],
        "requests": [{"state": "INVALID", "errors": [{"code": "nested", "message": "вложенная"}]}],
    }
    with pytest.raises(ValidationError) as exc_info:
        raise_for_status(400, body)

    assert exc_info.value.codes == ("top_level",)


def test_raise_for_status_uses_message_when_no_errors() -> None:
    with pytest.raises(ServerError) as exc_info:
        raise_for_status(500, {"message": "внутренняя ошибка"})

    assert "внутренняя ошибка" in str(exc_info.value)


def test_raise_for_status_handles_empty_body() -> None:
    with pytest.raises(ApiError) as exc_info:
        raise_for_status(502, None)

    assert exc_info.value.status_code == 502
    assert "502" in str(exc_info.value)


def test_retry_after_is_parsed_from_headers() -> None:
    with pytest.raises(RateLimitError) as exc_info:
        raise_for_status(429, {"message": "slow down"}, headers={"Retry-After": "3.5"})

    assert exc_info.value.retry_after == 3.5


def test_request_id_is_captured() -> None:
    with pytest.raises(NotFoundError) as exc_info:
        raise_for_status(404, {}, headers={"X-Request-Id": "req-1"})

    assert exc_info.value.request_id == "req-1"


def test_all_errors_derive_from_cdekx_error() -> None:
    classes: tuple[Any, ...] = (
        ApiError,
        AuthError,
        NotFoundError,
        ValidationError,
        RateLimitError,
        ServerError,
    )
    for cls in classes:
        assert issubclass(cls, CdekxError)


def test_api_error_str_prefers_details() -> None:
    error = ApiError(
        "fallback",
        status_code=400,
        errors=[ApiErrorDetail(code="C", message="сообщение")],
    )
    assert str(error) == "[HTTP 400] C: сообщение"
