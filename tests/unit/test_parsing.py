"""Тесты быстрого пути разбора ответов: ``model_validate_json`` / ``validate_json``.

Смысл оптимизации: тело ответа **не** проходит через ``json.loads`` — байты
уходят напрямую в Rust-парсер pydantic. Замеры — в ``benchmarks/parse_benchmark.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cdekx.endpoints.base import (
    ResponseParseError,
    parse_list_json,
    parse_model_json,
    unwrap_entities,
)
from cdekx.models import City, DeliveryPoint, Order
from cdekx.models.base import ResponseEnvelope, RootEntity
from conftest import FIXTURES_DIR

# --- parse_model_json -------------------------------------------------------


def test_parses_envelope_from_bytes() -> None:
    content = (FIXTURES_DIR / "orders" / "get.json").read_bytes()

    envelope = parse_model_json(ResponseEnvelope[Order], content)

    assert envelope.state == "SUCCESSFUL"
    assert envelope.entity is not None
    assert envelope.entity.cdek_number == "1234567890"
    assert envelope.related_entities is not None
    assert len(envelope.related_entities) == 2


def test_parses_from_str_too() -> None:
    content = (FIXTURES_DIR / "orders" / "get.json").read_text(encoding="utf-8")

    envelope = parse_model_json(ResponseEnvelope[Order], content)

    assert envelope.uuid == "8dea00e3-9aab-4d8e-887c-ef2aaa546456"


def test_result_matches_dict_path() -> None:
    """Быстрый и универсальный пути дают идентичный результат."""
    content = (FIXTURES_DIR / "orders" / "get.json").read_bytes()

    fast = parse_model_json(ResponseEnvelope[Order], content)
    slow = ResponseEnvelope[Order].model_validate(json.loads(content))

    assert fast.model_dump() == slow.model_dump()


def test_empty_body_raises_parse_error() -> None:
    with pytest.raises(ResponseParseError) as exc_info:
        parse_model_json(ResponseEnvelope[Order], b"")

    assert "empty body" in str(exc_info.value)


def test_invalid_json_raises_parse_error_with_preview() -> None:
    """HTML вместо JSON (типичный ответ прокси на 502) — понятная диагностика."""
    with pytest.raises(ResponseParseError) as exc_info:
        parse_model_json(ResponseEnvelope[Order], b"<html>502 Bad Gateway</html>")

    error = exc_info.value
    assert "Invalid JSON" in str(error)  # pydantic json_invalid
    assert "502 Bad Gateway" in str(error.raw)  # сырое тело сохранено


def test_schema_mismatch_raises_parse_error_with_raw() -> None:
    """СДЭК изменил контракт — получаем диагностику, а не тихий ``None``."""
    with pytest.raises(ResponseParseError) as exc_info:
        parse_model_json(ResponseEnvelope[Order], b'{"entity": {"no_uuid": 1}}')

    assert exc_info.value.raw is not None


def test_preview_is_truncated() -> None:
    huge = b'{"a": "' + b"x" * 5000 + b'"'
    with pytest.raises(ResponseParseError) as exc_info:
        parse_model_json(ResponseEnvelope[Order], huge)

    assert len(str(exc_info.value.raw)) <= 600


# --- parse_list_json --------------------------------------------------------


def test_parses_array_of_offices_from_bytes() -> None:
    content = (FIXTURES_DIR / "delivery" / "list.json").read_bytes()

    points = parse_list_json(DeliveryPoint, content)

    assert [p.code for p in points] == ["MSK1", "MSK2"]
    assert points[0].location.city_code == 44


def test_parses_array_of_cities() -> None:
    content = (FIXTURES_DIR / "locations" / "cities.json").read_bytes()

    cities = parse_list_json(City, content)

    assert [c.code for c in cities] == [44, 270]


def test_list_result_matches_dict_path() -> None:
    content = (FIXTURES_DIR / "delivery" / "list.json").read_bytes()

    fast = parse_list_json(DeliveryPoint, content)
    slow = [DeliveryPoint.model_validate(item) for item in json.loads(content)]

    assert [p.model_dump() for p in fast] == [p.model_dump() for p in slow]


def test_falls_back_to_envelope_parsing() -> None:
    """Если ответ — конверт, а не массив, работает универсальный путь."""
    content = json.dumps({"entities": [{"uuid": "a"}, {"uuid": "b"}]}).encode()

    items = parse_list_json(RootEntity, content)

    assert [item.uuid for item in items] == ["a", "b"]


def test_empty_array_is_ok() -> None:
    assert parse_list_json(DeliveryPoint, b"[]") == []


def test_whitespace_before_array_is_ok() -> None:
    content = b"\n\t " + (FIXTURES_DIR / "locations" / "cities.json").read_bytes()

    assert len(parse_list_json(City, content)) == 2


def test_invalid_json_array_raises_parse_error() -> None:
    with pytest.raises(ResponseParseError):
        parse_list_json(DeliveryPoint, b"[{not json}]")


def test_schema_mismatch_in_array_raises_parse_error() -> None:
    with pytest.raises(ResponseParseError) as exc_info:
        parse_list_json(City, '[{"code": "не число"}]'.encode())

    assert "failed to parse list[City]" in str(exc_info.value)


# --- ленивость json в транспортном слое -------------------------------------


def test_response_json_is_lazy() -> None:
    """``json.loads`` не вызывается, пока не запрошен ``.json``."""
    from cdekx._http import Response

    response = Response(status_code=200, content=b'{"a": 1}')

    assert response._json_loaded is False
    assert response.json == {"a": 1}
    assert response._json_loaded is True
    assert response.json == {"a": 1}  # повторная отдача из кэша


def test_response_json_handles_non_json() -> None:
    from cdekx._http import Response

    assert Response(status_code=200, content=b"plain text").json == "plain text"
    assert Response(status_code=204, content=b"").json is None


async def test_endpoint_does_not_json_loads_entity_body(token_route: Any, make_client: Any) -> None:
    """Тело успешного ответа не проходит через ``json.loads``.

    Токен OAuth разбирается httpx'ом (``response.json()``) — это отдельный
    запрос на 1 вызов за время жизни токена, поэтому проверяем именно тело
    заказа: оно должно уйти в ``model_validate_json`` байтами.
    """
    import httpx

    entity_body = (FIXTURES_DIR / "orders" / "get.json").read_bytes()
    token_route.get("/v2/orders/u1").mock(
        return_value=httpx.Response(
            200, content=entity_body, headers={"Content-Type": "application/json"}
        )
    )
    client = make_client()
    await client.orders.get("u1")  # прогрев: получаем и кэшируем токен

    parsed: list[Any] = []
    original_loads = json.loads

    def spy(data: Any) -> Any:
        parsed.append(data)
        return original_loads(data)

    json.loads = spy  # type: ignore[assignment]
    try:
        order = await client.orders.get("u1")
    finally:
        json.loads = original_loads  # type: ignore[assignment]

    assert order.cdek_number == "1234567890"
    assert parsed == [], f"json.loads вызывался {len(parsed)} раз(а) для тела заказа"


async def test_error_path_still_parses_body(token_route: Any, make_client: Any) -> None:
    """На ошибке тело разбирается: коды и request_id доступны."""
    import httpx

    from cdekx import NotFoundError

    token_route.get("/v2/orders/u1").mock(
        return_value=httpx.Response(
            404,
            json={"errors": [{"code": "v2_entity_not_found", "message": "не найден"}]},
            headers={"X-Request-Id": "req-9"},
        )
    )
    client = make_client()

    with pytest.raises(NotFoundError) as exc_info:
        await client.orders.get("u1")

    assert exc_info.value.codes == ("v2_entity_not_found",)
    assert exc_info.value.request_id == "req-9"


def test_unwrap_entities_still_works() -> None:
    assert unwrap_entities([1, 2]) == [1, 2]
    assert unwrap_entities({"entities": [1]}) == [1]
    assert unwrap_entities({"entity": {"a": 1}}) == [{"a": 1}]
    assert unwrap_entities(None) == []


def test_fixtures_are_valid_json() -> None:
    """Все фикстуры остаются валидным JSON (их читают и тесты, и бенчмарки)."""
    for path in Path(FIXTURES_DIR).rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
