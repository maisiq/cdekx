"""Тесты разбора входящих вебхуков и ASGI-приёмника."""

from __future__ import annotations

import json
from typing import Any

import pytest

from cdekx.webhooks import (
    CourierInfoAttributes,
    OrderStatusAttributes,
    PrintFormAttributes,
    UnknownEventError,
    WebhookEvent,
    parse_event,
)
from cdekx.webhooks.asgi import WebhookApp
from cdekx.webhooks.security import compare_signature, is_cdek_ip, verify_ip
from conftest import load_fixture

# --- parse_event ------------------------------------------------------------


def test_parse_order_status_event() -> None:
    event = parse_event(load_fixture("webhooks", "order_status_event.json"))

    assert event.type == "ORDER_STATUS"
    assert event.uuid == "8dea00e3-9aab-4d8e-887c-ef2aaa546456"
    assert isinstance(event.attributes, OrderStatusAttributes)
    assert event.attributes.code == "IN_TRANSIT"
    assert event.attributes.status_reason_code == "RECEIVED_AT_WAREHOUSE"
    assert event.attributes.cdek_number == "1234567890"
    assert event.attributes.city_code == 44
    assert event.attributes.related_entities is not None
    assert event.attributes.related_entities[0].type == "direct_order"
    assert event.is_known_type


def test_parse_event_from_json_bytes() -> None:
    raw = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    event = parse_event(raw)

    assert isinstance(event.attributes, OrderStatusAttributes)


def test_parse_event_from_json_string() -> None:
    raw = json.dumps(load_fixture("webhooks", "print_form_event.json"))

    event = parse_event(raw)

    assert isinstance(event.attributes, PrintFormAttributes)
    assert event.attributes.url is not None


def test_parse_courier_info_event() -> None:
    event = parse_event(load_fixture("webhooks", "courier_info_event.json"))

    assert isinstance(event.attributes, CourierInfoAttributes)
    assert event.attributes.task_type == "DELIVERY"
    assert event.attributes.courier_phone == "+79001234567"


def test_parse_unknown_event_type_keeps_dict() -> None:
    payload = {
        "type": "SOME_FUTURE_EVENT",
        "date_time": "2026-05-06T18:30:00+0300",
        "uuid": "u",
        "attributes": {"new_field": 1},
    }

    event = parse_event(payload)

    assert event.type == "SOME_FUTURE_EVENT"
    assert not event.is_known_type
    assert event.attributes == {"new_field": 1}


def test_parse_event_rejects_garbage() -> None:
    with pytest.raises(UnknownEventError):
        parse_event({"no_type": True})

    with pytest.raises(UnknownEventError):
        parse_event("не json")

    with pytest.raises(UnknownEventError):
        parse_event(None)


def test_event_datetime_is_parsed() -> None:
    event = parse_event(load_fixture("webhooks", "order_status_event.json"))

    assert event.date_time is not None
    assert getattr(event.date_time, "year", None) == 2026


def test_as_order_status_helper() -> None:
    event = parse_event(load_fixture("webhooks", "order_status_event.json"))
    attrs = event.as_order_status()

    assert isinstance(attrs, OrderStatusAttributes)
    assert attrs.code == "IN_TRANSIT"


# --- WebhookApp -------------------------------------------------------------


async def _noop(event: WebhookEvent) -> None:
    return None


async def test_webhook_app_accepts_valid_event() -> None:
    seen: list[WebhookEvent] = []

    async def handler(event: WebhookEvent) -> None:
        seen.append(event)

    app = WebhookApp(on_event=handler)
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, payload = await app.handle_raw(body)

    assert status == 200
    assert payload["type"] == "ORDER_STATUS"
    assert len(seen) == 1


async def test_webhook_app_rejects_wrong_secret() -> None:
    app = WebhookApp(on_event=_noop, path_secret="s3cr3t")
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, _ = await app.handle_raw(body, path="/webhooks/cdek/wrong")

    assert status == 404


async def test_webhook_app_accepts_correct_secret() -> None:
    app = WebhookApp(on_event=_noop, path_secret="s3cr3t")
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, _ = await app.handle_raw(body, path="/webhooks/cdek/s3cr3t")

    assert status == 200


async def test_webhook_app_rejects_untrusted_ip() -> None:
    app = WebhookApp(on_event=_noop, ip_ranges=("10.0.0.0/8",))
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, _ = await app.handle_raw(body, client_ip="8.8.8.8")

    assert status == 403


async def test_webhook_app_allows_trusted_ip() -> None:
    app = WebhookApp(on_event=_noop, ip_ranges=("10.0.0.0/8",))
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, _ = await app.handle_raw(body, client_ip="10.1.2.3")

    assert status == 200


async def test_webhook_app_ignores_unsubscribed_types() -> None:
    calls: list[str] = []

    async def handler(event: WebhookEvent) -> None:
        calls.append(event.type)

    app = WebhookApp(on_event=handler, accept_types=["PRINT_FORM"])
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, payload = await app.handle_raw(body)

    assert status == 200
    assert payload["detail"] == "ignored"
    assert calls == []


async def test_webhook_app_returns_200_on_handler_error_by_default() -> None:
    """СДЭК удалит подписку при не-200, поэтому по умолчанию глотаем ошибку."""

    async def broken(event: WebhookEvent) -> None:
        raise RuntimeError("база упала")

    app = WebhookApp(on_event=broken)
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, _ = await app.handle_raw(body)

    assert status == 200


async def test_webhook_app_can_propagate_handler_error() -> None:
    async def broken(event: WebhookEvent) -> None:
        raise RuntimeError("база упала")

    app = WebhookApp(on_event=broken, raise_on_handler_error=True)
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, _ = await app.handle_raw(body)

    assert status == 500


async def test_webhook_app_supports_sync_handler() -> None:
    seen: list[str] = []

    def handler(event: WebhookEvent) -> None:
        seen.append(event.type)

    app = WebhookApp(on_event=handler)  # type: ignore[arg-type]
    body = json.dumps(load_fixture("webhooks", "order_status_event.json")).encode()

    status, _ = await app.handle_raw(body)

    assert status == 200
    assert seen == ["ORDER_STATUS"]


async def test_webhook_app_rejects_malformed_body() -> None:
    app = WebhookApp(on_event=_noop)

    status, _ = await app.handle_raw(b"{not json}")

    assert status == 400


starlette = pytest.importorskip("starlette", reason="extra 'webhooks' не установлен")


async def test_webhook_app_asgi_handles_post() -> None:
    """Проверяем реальное ASGI-приложение через starlette TestClient."""
    from starlette.testclient import TestClient

    seen: list[WebhookEvent] = []

    async def handler(event: WebhookEvent) -> None:
        seen.append(event)

    app = WebhookApp(on_event=handler, path_secret="s3cr3t").asgi

    with TestClient(app) as test_client:
        ok = test_client.post(
            "/s3cr3t",
            content=json.dumps(load_fixture("webhooks", "order_status_event.json")),
            headers={"Content-Type": "application/json"},
        )
        forbidden = test_client.post("/wrong-secret", content=b'{"type": "ORDER_STATUS"}')
        health = test_client.get("/healthz")

    assert ok.status_code == 200
    assert forbidden.status_code == 404
    assert health.status_code == 200
    assert len(seen) == 1
    assert seen[0].attributes.code == "IN_TRANSIT"


async def test_webhook_app_asgi_reads_client_ip_from_headers() -> None:
    from starlette.testclient import TestClient

    app = WebhookApp(on_event=_noop, ip_ranges=("10.0.0.0/8",)).asgi
    body = json.dumps(load_fixture("webhooks", "order_status_event.json"))

    with TestClient(app) as test_client:
        allowed = test_client.post("/", content=body, headers={"X-Forwarded-For": "10.9.9.9"})
        blocked = test_client.post("/", content=body, headers={"X-Real-IP": "8.8.8.8"})

    assert allowed.status_code == 200
    assert blocked.status_code == 403


def test_webhook_app_requires_starlette(monkeypatch: pytest.MonkeyPatch) -> None:
    """Если starlette не установлен, выдаём понятную ошибку."""
    import builtins

    app = WebhookApp(on_event=_noop)
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("starlette"):
            raise ImportError("no starlette")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="cdekx\\[webhooks\\]"):
        _ = app.asgi


# --- security ---------------------------------------------------------------


def test_is_cdek_ip_with_empty_ranges_returns_false() -> None:
    assert is_cdek_ip("8.8.8.8") is False
    assert is_cdek_ip("8.8.8.8", ranges=()) is False


def test_is_cdek_ip_matches_range() -> None:
    assert is_cdek_ip("10.1.2.3", ranges=("10.0.0.0/8",)) is True
    assert is_cdek_ip("11.1.2.3", ranges=("10.0.0.0/8",)) is False
    assert is_cdek_ip("не-ip", ranges=("10.0.0.0/8",)) is False
    assert is_cdek_ip(None, ranges=("10.0.0.0/8",)) is False


def test_verify_ip_raises_for_untrusted() -> None:
    with pytest.raises(PermissionError):
        verify_ip("8.8.8.8", ranges=("10.0.0.0/8",))

    verify_ip("10.0.0.1", ranges=("10.0.0.0/8",))  # не должно бросать
    verify_ip("8.8.8.8", ranges=())  # проверка отключена


def test_compare_signature() -> None:
    import hashlib
    import hmac

    body = b'{"type": "ORDER_STATUS"}'
    secret = "s3cr3t"
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert compare_signature(body, signature, secret)
    assert compare_signature(body, f"sha256={signature}", secret)
    assert not compare_signature(body, "deadbeef", secret)
    assert not compare_signature(body, None, secret)
