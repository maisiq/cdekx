"""Тесты калькулятора, локаций, ПВЗ, печати, вебхуков, заявок и договорённостей.

Все пути и формы ответов сверены с OpenAPI-спецификацией apidoc.cdek.ru.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest
import respx

from cdekx import ApiError, NotFoundError, TimeoutExceeded, ValidationError
from cdekx._http import HttpClient
from cdekx.endpoints.printing import PrintEndpoint
from cdekx.endpoints.webhooks import WebhooksEndpoint
from cdekx.models import (
    TOO_MANY_WEBHOOKS_ERROR,
    CalculatorLocation,
    CalculatorPackage,
    DeliveryPointFilter,
    DeliveryPointPolygonFilter,
    Location,
    PhotoOrder,
    PhotoRequest,
    PrealertCreate,
    PrealertOrder,
    RestrictionItem,
    RestrictionPackage,
    RestrictionRequest,
    ReverseContragent,
    ReverseLocation,
    ReverseValidateRequest,
    TariffListRequest,
    TariffRequest,
)
from cdekx.types.enums import Currency
from conftest import load_fixture

# --- calculator -------------------------------------------------------------


async def test_calculator_tariff(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/calculator/tariff").mock(
        return_value=httpx.Response(200, json=load_fixture("calculator", "tariff.json"))
    )
    client = make_client()

    result = await client.calculator.tariff(
        TariffRequest(
            tariff_code=136,
            from_location=CalculatorLocation(code=44),
            to_location=CalculatorLocation(code=270),
            packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
            currency=Currency.RUB,
            lang="rus",
        )
    )

    # В запрос валюта уходит числовым кодом («Приложение 14»: RUB = 1) —
    # строку "RUB" API отклоняет с v2_invalid_value_type.
    sent = json.loads(route.calls.last.request.content)
    assert sent["currency"] == 1

    assert result.delivery_sum == 480.5
    assert result.period_min == 2
    assert result.calendar_max == 4
    assert result.weight_calc == 2625
    assert result.delivery_date_range is not None
    assert result.delivery_date_range.min == "2026-05-10"
    assert not result.has_errors
    assert route.called


async def test_calculator_errors_inside_200(token_route: Any, make_client: Any) -> None:
    """Калькулятор возвращает HTTP 200 с ошибками внутри — их нельзя терять."""
    token_route.post("/v2/calculator/tariff").mock(
        return_value=httpx.Response(200, json=load_fixture("calculator", "tariff_with_errors.json"))
    )
    client = make_client()

    result = await client.calculator.tariff(
        {
            "tariff_code": 62,
            "from_location": {"code": 44},
            "to_location": {"code": 270},
            "packages": [{"weight": 30000}],
        }
    )

    assert result.has_errors
    assert result.errors is not None
    assert result.errors[0]["code"] == "v2_outdated_tariff"


async def test_calculator_tariff_list(token_route: Any, make_client: Any) -> None:
    token_route.post("/v2/calculator/tarifflist").mock(
        return_value=httpx.Response(200, json=load_fixture("calculator", "tarifflist.json"))
    )
    client = make_client()

    result = await client.calculator.tariff_list(
        TariffListRequest(
            from_location=CalculatorLocation(code=44),
            to_location=CalculatorLocation(code=270),
            packages=[CalculatorPackage(weight=1000)],
        )
    )

    assert len(result.tariff_codes) == 2
    assert result.best().tariff_code == 5  # type: ignore[union-attr]
    assert result.fastest().tariff_code == 136  # type: ignore[union-attr]


async def test_calculator_tariff_and_service(token_route: Any, make_client: Any) -> None:
    token_route.post("/v2/calculator/tariffAndService").mock(
        return_value=httpx.Response(200, json=load_fixture("calculator", "tariff_and_service.json"))
    )
    client = make_client()

    result = await client.calculator.tariff_and_service(
        {
            "from_location": {"code": 44},
            "to_location": {"code": 270},
            "packages": [{"weight": 1000}],
            "services": [{"code": "INSURANCE", "parameter": "1000"}],
        }
    )

    assert len(result.tariff_codes) == 2
    assert result.viable[0].tariff_code == 136
    assert result.viable[0].result.total_sum == 520.3
    assert result.best().tariff_code == 136  # type: ignore[union-attr]


async def test_calculator_available_tariffs(token_route: Any, make_client: Any) -> None:
    """Список тарифов по договору: GET /v2/calculator/alltariffs."""
    route = token_route.get("/v2/calculator/alltariffs").mock(
        return_value=httpx.Response(200, json=load_fixture("calculator", "alltariffs.json"))
    )
    client = make_client()

    result = await client.calculator.available_tariffs(lang="rus")

    assert len(result.tariff_codes) == 2
    assert result.all_tariff_codes() == [136, 137, 5, 62]
    assert result.tariff_codes[0].weight_max == 30000
    assert route.calls.last.request.headers["X-User-Lang"] == "rus"


# --- locations --------------------------------------------------------------


async def test_locations_cities(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/location/cities").mock(
        return_value=httpx.Response(200, json=load_fixture("locations", "cities.json"))
    )
    client = make_client()

    cities = await client.locations.cities({"city": "Москва", "size": 10})

    assert cities[0].code == 44
    assert cities[0].city_uuid == "0c5b2444-70a0-4932-980c-b4dc0d3f02b5"
    assert cities[0].payment_limit == 500000
    assert "size=10" in str(route.calls.last.request.url)


async def test_locations_paginate_cities(token_route: Any, make_client: Any) -> None:
    page = load_fixture("locations", "cities.json")

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page if request.url.params.get("page") == "0" else [])

    token_route.get("/v2/location/cities").mock(side_effect=responder)
    client = make_client()

    codes = [c.code async for c in client.locations.paginate_cities(page_size=2)]

    assert codes == [44, 270]


async def test_locations_suggest_path(token_route: Any, make_client: Any) -> None:
    """Правильный путь — /v2/location/suggest/cities (не /cities/suggest)."""
    route = token_route.get("/v2/location/suggest/cities").mock(
        return_value=httpx.Response(200, json=load_fixture("locations", "suggest.json"))
    )
    client = make_client()

    suggestions = await client.locations.suggest_cities("Новосиб", country_code="RU")

    assert suggestions[0].code == 532
    assert suggestions[0].full_name.startswith("г. Новосибирск")
    url = str(route.calls.last.request.url)
    assert "country_code=RU" in url


async def test_locations_regions(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/location/regions").mock(
        return_value=httpx.Response(200, json=load_fixture("locations", "regions.json"))
    )
    client = make_client()

    regions = await client.locations.regions({"country_codes": "RU", "size": 100})

    assert [r.region_code for r in regions] == [77, 66]
    assert regions[0].country == "Россия"


async def test_locations_by_coordinates(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/location/coordinates").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 44,
                "city_uuid": "0c5b2444-70a0-4932-980c-b4dc0d3f02b5",
                "city": "Москва",
                "fias_guid": "0c5b2444-70a0-4932-980c-b4dc0d3f02b5",
            },
        )
    )
    client = make_client()

    city = await client.locations.city_by_coordinates(55.75322, 37.622513)

    assert city.code == 44
    assert "latitude=55.75322" in str(route.calls.last.request.url)


async def test_locations_postalcodes(token_route: Any, make_client: Any) -> None:
    """Ответ — объект {code, postal_codes} (PostcodesResponseDto), не список."""
    route = token_route.get("/v2/location/postalcodes").mock(
        return_value=httpx.Response(200, json=load_fixture("locations", "postalcodes.json"))
    )
    client = make_client()

    postcodes = await client.locations.postalcodes(44)

    assert postcodes.code == 44
    assert postcodes.postal_codes[0] == "101000"
    assert len(postcodes.postal_codes) == 5
    assert postcodes.values == postcodes.postal_codes
    assert "code=44" in str(route.calls.last.request.url)


async def test_locations_postalcodes_foreign_null(token_route: Any, make_client: Any) -> None:
    """Для зарубежных городов API отдаёт postal_codes=[null] (code=176, ОАЭ)."""
    token_route.get("/v2/location/postalcodes").mock(
        return_value=httpx.Response(200, json=load_fixture("locations", "postalcodes_foreign.json"))
    )
    client = make_client()

    postcodes = await client.locations.postalcodes(176)

    assert postcodes.code == 176
    assert postcodes.postal_codes == [None]
    assert postcodes.values == []


# --- delivery points --------------------------------------------------------


async def test_delivery_points_list(token_route: Any, make_client: Any) -> None:
    """Ответ — массив OfficeDto без конверта entity."""
    route = token_route.get("/v2/deliverypoints").mock(
        return_value=httpx.Response(200, json=load_fixture("delivery", "list.json"))
    )
    client = make_client()

    points = await client.delivery_points.list(DeliveryPointFilter(city_code=44, type="ALL"))

    assert len(points) == 2
    assert points[0].code == "MSK1"
    assert points[0].status == "ACTIVE"
    assert points[0].have_fast_payment_system is True
    assert points[0].ltl_acceptance_partners is False
    assert points[0].work_time_list[0].day == 1
    assert points[0].phones[0].number == "+74951234567"
    assert points[0].address == "ул. Тестовая, 1"
    assert points[0].city_code == 44
    assert "city_code=44" in str(route.calls.last.request.url)


async def test_delivery_points_get_raises_not_found(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/deliverypoints").mock(return_value=httpx.Response(200, json=[]))
    client = make_client()

    with pytest.raises(NotFoundError):
        await client.delivery_points.get("NOPE")


async def test_delivery_points_by_polygon(token_route: Any, make_client: Any) -> None:
    """Поиск ближайших офисов — через прямоугольник координат."""
    route = token_route.get("/v2/deliverypoints/byPolygons").mock(
        return_value=httpx.Response(200, json=load_fixture("delivery", "list.json"))
    )
    client = make_client()

    points = await client.delivery_points.by_polygon(
        latitude_right_top=55.78,
        longitude_right_top=37.65,
        latitude_left_bottom=55.73,
        longitude_left_bottom=37.60,
        filter=DeliveryPointPolygonFilter(type="PVZ", allowed_cod=True),
    )

    assert len(points) == 2
    url = str(route.calls.last.request.url)
    assert "latitude_right_top=55.78" in url
    assert "longitude_left_bottom=37.6" in url
    assert "type=PVZ" in url
    assert "allowed_cod=true" in url
    # byPolygons не поддерживает фильтры списка офисов (is_handout, size, page…)
    assert "is_handout" not in url
    assert "size" not in url


async def test_delivery_points_paginate(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/deliverypoints").mock(
        return_value=httpx.Response(200, json=load_fixture("delivery", "list.json"))
    )
    client = make_client()

    points = [p async for p in client.delivery_points.paginate(page_size=500)]

    assert len(points) == 2


# --- printing ---------------------------------------------------------------


async def test_waybill_print_uses_json_body(token_route: Any, make_client: Any) -> None:
    """Параметры печати передаются телом JSON, а не query-строкой."""
    route = token_route.post("/v2/print/orders").mock(
        return_value=httpx.Response(202, json=load_fixture("printing", "task.json"))
    )
    client = make_client()

    task = await client.printing.waybill(["8dea00e3-9aab-4d8e-887c-ef2aaa546456"], copy_count=2)

    assert task.uuid == "c02f3f41-4a5b-4c6d-8e9f-0a1b2c3d4e5f"
    body = route.calls.last.request.read().decode().replace(" ", "")
    assert '"order_uuid":"8dea00e3-9aab-4d8e-887c-ef2aaa546456"' in body
    assert '"copy_count":2' in body


async def test_barcodes_accept_cdek_numbers(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/print/barcodes").mock(
        return_value=httpx.Response(202, json=load_fixture("printing", "task.json"))
    )
    client = make_client()

    await client.printing.barcodes(["1234567890"], copy_count=1, format="A4", lang="RUS")

    body = route.calls.last.request.read().decode().replace(" ", "")
    assert '"cdek_number":"1234567890"' in body
    assert '"format":"A4"' in body
    assert '"lang":"RUS"' in body


async def test_waybill_status_and_wait(token_route: Any, make_client: Any) -> None:
    """Статус квитанции — GET /v2/print/orders/{uuid}."""
    responses = [
        httpx.Response(200, json=load_fixture("printing", "waybill_pending.json")),
        httpx.Response(200, json=load_fixture("printing", "waybill_ready.json")),
    ]
    route = token_route.get("/v2/print/orders/task-1").mock(side_effect=responses)
    client = make_client()

    ready = await client.printing.wait_waybill("task-1", timeout=5, interval=0.001)

    assert ready.is_ready
    assert ready.url is not None and ready.url.endswith(".pdf")
    assert route.call_count == 2


async def test_barcode_download_path(token_route: Any, make_client: Any) -> None:
    """Файл скачивается с /v2/print/barcodes/{uuid}.pdf (с авторизацией)."""
    token_route.get("/v2/print/barcodes/task-1").mock(
        return_value=httpx.Response(200, json=load_fixture("printing", "barcode_ready.json"))
    )
    token_route.get("/v2/print/barcodes/task-1.pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.7 barcode")
    )
    client = make_client()

    barcode = await client.printing.barcode_status("task-1")
    data = await client.printing.barcode_pdf("task-1")

    assert barcode.is_ready
    assert data == b"%PDF-1.7 barcode"


async def test_printing_wait_timeout(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/print/orders/x").mock(
        return_value=httpx.Response(200, json=load_fixture("printing", "waybill_pending.json"))
    )
    client = make_client()

    with pytest.raises(TimeoutExceeded):
        await client.printing.wait_waybill("x", timeout=0.05, interval=0.02)


async def test_printing_download_uses_authorized_api_path() -> None:
    """Скачивание идёт через тот же http-клиент: отдельный хост не нужен."""
    with respx.mock(base_url="https://api.cdek.ru") as router:
        router.get("/v2/print/orders/t1.pdf").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.7")
        )
        endpoint = PrintEndpoint(HttpClient(base_url="https://api.cdek.ru", auth=None))

        data = await endpoint.waybill_pdf("t1")

    assert data == b"%PDF-1.7"


# --- webhooks ---------------------------------------------------------------


async def test_webhooks_create(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/webhooks").mock(
        return_value=httpx.Response(200, json=load_fixture("webhooks", "create.json"))
    )
    client = make_client()

    result = await client.webhooks.create("https://example.com/hook/secret", "ORDER_STATUS")

    assert result.uuid == "cc33dd44-ee55-ff66-7788-990011223344"
    body = route.calls.last.request.read().decode().replace(" ", "")
    assert body == '{"type":"ORDER_STATUS","url":"https://example.com/hook/secret"}'


async def test_webhooks_list_returns_array(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/webhooks").mock(
        return_value=httpx.Response(200, json=load_fixture("webhooks", "list.json"))
    )
    client = make_client()

    hooks = await client.webhooks.list()

    assert [h.type for h in hooks] == ["ORDER_STATUS", "PRINT_FORM"]
    assert hooks[0].uuid == "aa11bb22-cc33-dd44-ee55-ff6677889900"


async def test_webhooks_capacity_limit(token_route: Any, make_client: Any) -> None:
    two = load_fixture("webhooks", "list.json")
    client = make_client()

    token_route.get("/v2/webhooks").mock(return_value=httpx.Response(200, json=two[:1]))
    assert await client.webhooks.has_capacity()

    token_route.get("/v2/webhooks").mock(return_value=httpx.Response(200, json=two))
    assert not await client.webhooks.has_capacity()


async def test_webhooks_create_over_limit(token_route: Any, make_client: Any) -> None:
    """Лимит «2 активные подписки» не описан в спецификации, но API его соблюдает.

    Реальный ответ песочницы: HTTP 400 с кодом
    ``v2_too_many_webhooks`` и списком активных UUID в сообщении.
    """
    body = {
        "requests": [
            {
                "type": "CREATE",
                "date_time": "2026-10-28T13:54:45+0000",
                "state": "INVALID",
                "errors": [
                    {
                        "code": "v2_too_many_webhooks",
                        "message": "Too many active webhooks. Maximum allowed is 2. "
                        "Active webhooks uuids: #[aa11bb22-cc33-dd44-ee55-ff6677889900]",
                    }
                ],
            }
        ]
    }
    token_route.post("/v2/webhooks").mock(return_value=httpx.Response(400, json=body))
    client = make_client()

    with pytest.raises(ValidationError) as exc_info:
        await client.webhooks.create("https://example.com/hook/secret")

    assert exc_info.value.status_code == 400
    assert exc_info.value.has_code(TOO_MANY_WEBHOOKS_ERROR)
    assert WebhooksEndpoint.is_limit_error(exc_info.value)


async def test_webhooks_is_limit_error_false_for_other_codes(
    token_route: Any, make_client: Any
) -> None:
    body = {"requests": [{"errors": [{"code": "v2_webhook_type_incorrect"}]}]}
    token_route.post("/v2/webhooks").mock(return_value=httpx.Response(400, json=body))
    client = make_client()

    with pytest.raises(ValidationError) as exc_info:
        await client.webhooks.create("https://example.com/hook", "NOPE")

    assert not WebhooksEndpoint.is_limit_error(exc_info.value)
    assert not WebhooksEndpoint.is_limit_error(ValueError("не ошибка API"))


async def test_webhooks_delete_all(token_route: Any, make_client: Any) -> None:
    hooks = load_fixture("webhooks", "list.json")
    token_route.get("/v2/webhooks").mock(return_value=httpx.Response(200, json=hooks))
    for hook in hooks:
        token_route.delete(f"/v2/webhooks/{hook['uuid']}").mock(
            return_value=httpx.Response(200, json=load_fixture("webhooks", "create.json"))
        )
    client = make_client()

    removed = await client.webhooks.delete_all()

    assert removed == [h["uuid"] for h in hooks]


# --- intakes ----------------------------------------------------------------


async def test_intake_create_and_get(token_route: Any, make_client: Any) -> None:
    create_route = token_route.post("/v2/intakes").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "create.json"))
    )
    token_route.get("/v2/intakes/f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c").mock(
        return_value=httpx.Response(200, json=load_fixture("intakes", "info.json"))
    )
    client = make_client()

    task = await client.intakes.create(
        {
            "cdek_number": "1234567890",
            "intake_date": "2026-05-10",
            "intake_time_from": "10:00",
            "intake_time_to": "18:00",
            "from_location": {"code": 44, "address": "ул. Тестовая, 1"},
        }
    )
    intake = await client.intakes.get("f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c")

    assert task.uuid == "8dea00e3-9aab-4d8e-887c-ef2aaa546456"
    assert create_route.called
    assert intake.intake_number == "40000001"
    assert intake.sender is not None and intake.sender.phones[0].number == "+79001234567"
    assert intake.current_status is not None and intake.current_status.code == "ACCEPTED"


async def test_intake_change_status_uses_patch(token_route: Any, make_client: Any) -> None:
    """Изменение заявки в API — это смена статуса через PATCH /v2/intakes."""
    route = token_route.patch("/v2/intakes").mock(
        return_value=httpx.Response(
            200, json={"entity": {"uuid": "i1"}, "requests": [{"state": "SUCCESSFUL"}]}
        )
    )
    client = make_client()

    result = await client.intakes.change_status(
        "i1", code="CANCELLED", add_status="CANCELLED_BY_CLIENT"
    )

    assert route.called
    body = route.calls.last.request.read().decode().replace(" ", "")
    assert '"code":"CANCELLED"' in body
    assert '"add_status":"CANCELLED_BY_CLIENT"' in body
    assert result.state == "SUCCESSFUL"


async def test_intake_available_days_uses_post(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/intakes/availableDays").mock(
        return_value=httpx.Response(200, json=load_fixture("intakes", "available_days.json"))
    )
    client = make_client()

    days = await client.intakes.available_days(
        {"from_location": {"code": 44}, "date": "2026-06-30"}
    )

    # В спецификации date — массив `format: date`, поэтому модель отдаёт `date`,
    # а не строки (см. IntakeAvailableDays).
    assert days.date == [date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13)]
    assert days.all_days is False
    assert days.has_errors is False
    assert route.called


async def test_intake_delete(token_route: Any, make_client: Any) -> None:
    route = token_route.delete("/v2/intakes/i1").mock(
        return_value=httpx.Response(200, json=load_fixture("orders", "create.json"))
    )
    client = make_client()

    await client.intakes.delete("i1")

    assert route.called


# --- delivery agreement -----------------------------------------------------


async def test_delivery_intervals(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/delivery/intervals").mock(
        return_value=httpx.Response(200, json=load_fixture("agreements", "intervals.json"))
    )
    client = make_client()

    intervals = await client.delivery_agreement.intervals(cdek_number="1234567890")

    assert len(intervals.date_intervals) == 2
    assert intervals.date_intervals[0].date == "2026-05-11"
    assert intervals.date_intervals[0].time_intervals[1].agreed_count == 8
    assert "cdek_number=1234567890" in str(route.calls.last.request.url)


async def test_delivery_agreement_create(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/delivery").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "create.json"))
    )
    client = make_client()

    task = await client.delivery_agreement.create(
        {
            "cdek_number": "1234567890",
            "date": "2026-05-11",
            "time_from": "09:00",
            "time_to": "13:00",
        }
    )

    assert route.called
    assert task.state == "ACCEPTED"


async def test_estimated_intervals(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/delivery/estimatedIntervals").mock(
        return_value=httpx.Response(200, json=load_fixture("agreements", "intervals.json"))
    )
    client = make_client()

    result = await client.delivery_agreement.estimated_intervals(
        {
            "date_time": "2026-05-10T10:00:00+0300",
            "from_location": {"code": 44},
            "to_location": {"code": 270},
            "tariff_code": 136,
        }
    )

    assert route.called
    assert result.date_intervals[0].time_intervals[0].start_time == "09:00"


# --- misc -------------------------------------------------------------------
# Формы ответов взяты из OpenAPI-спецификации apidoc.cdek.ru: методы этого
# раздела отвечают «списком с ошибками» (ListResponse), а не конвертом.


async def test_reverse_availability_empty_body_means_available(
    token_route: Any, make_client: Any
) -> None:
    """Доступный реверс — это пустое тело с кодом 200 (в спецификации нет схемы)."""
    route = token_route.post("/v2/reverse/availability").mock(
        return_value=httpx.Response(200, content=b"")
    )
    client = make_client()

    result = await client.misc.reverse_availability(
        ReverseValidateRequest(
            tariff_code=136,
            delivery_point="MSK",
            from_location=ReverseLocation(code=44, address="ул. Тестовая, 1"),
            sender=ReverseContragent(phones=["89001234567"]),
            recipient=ReverseContragent(phones=["+79007654321"]),
        )
    )

    assert result is None
    assert route.called
    sent = json.loads(route.calls.last.request.content)
    # телефон нормализуется до международного формата, как и в Contact
    assert sent["sender"]["phones"] == [{"number": "+79001234567"}]
    assert sent["tariff_code"] == 136


async def test_reverse_availability_unavailable_raises(token_route: Any, make_client: Any) -> None:
    """Недоступность реверса приходит как HTTP 400 с описанием причины."""
    token_route.post("/v2/reverse/availability").mock(
        return_value=httpx.Response(
            400,
            json={"errors": [{"code": "v2_reverse_unavailable", "message": "Реверс недоступен"}]},
        )
    )
    client = make_client()

    with pytest.raises(ValidationError) as exc:
        await client.misc.reverse_availability({"tariff_code": 136})

    assert exc.value.errors[0].code == "v2_reverse_unavailable"


async def test_checks_returns_typed_list(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/check").mock(
        return_value=httpx.Response(200, json=load_fixture("misc", "check.json"))
    )
    client = make_client()

    checks = await client.misc.checks(cdek_number="1234567890", date="2026-05-05")

    assert route.calls.last.request.url.params["cdek_number"] == "1234567890"
    assert checks.has_errors is False
    assert len(checks.checks) == 1
    check = checks.checks[0]
    assert check.type == "CASH_RECEIPT_IN"
    assert check.cdek_number == "1234567890"  # int64 в API → строка в модели
    assert check.payment_info[0].type == "CARD"
    assert check.total == 2400.5
    assert check.date is not None


async def test_checks_requires_at_least_one_param(make_client: Any) -> None:
    """API ответил бы 400 — не отправляем бессмысленный запрос вовсе."""
    client = make_client()

    with pytest.raises(ValueError, match="order_uuid"):
        await client.misc.checks()


async def test_passports_reports_unsatisfied(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/passport").mock(
        return_value=httpx.Response(200, json=load_fixture("misc", "passport.json"))
    )
    client = make_client()

    passports = await client.misc.passports(cdek_number="1234567890", client="RECEIVER")

    assert route.calls.last.request.url.params["client"] == "RECEIVER"
    assert len(passports.orders or []) == 2
    assert passports.orders[0].ok is True
    assert [o.cdek_number for o in passports.unsatisfied] == ["1234567891"]


async def test_registries_requires_date_and_sums(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/registries").mock(
        return_value=httpx.Response(200, json=load_fixture("misc", "registries.json"))
    )
    client = make_client()

    registries = await client.misc.registries("2026-05-06")

    assert route.calls.last.request.url.params["date"] == "2026-05-06"
    registry = registries.registries[0]
    assert registry.registry_number == 123456
    assert registry.orders[0].basis_type == "ORDER"
    assert registry.orders[0].agent_commission_sum == 60.5
    assert registries.total == 2400.5


async def test_photo_documents_ready_only(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/photoDocument").mock(
        return_value=httpx.Response(200, json=load_fixture("misc", "photo_document.json"))
    )
    client = make_client()

    photo = await client.misc.photo_ready_orders(
        PhotoRequest(
            period_begin="2026-04-01T00:00:00+0000",
            period_end="2026-04-30T23:59:59+0000",
            orders=[PhotoOrder(cdek_number="1234567890")],
        )
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["period_begin"] == "2026-04-01T00:00:00+0000"
    assert sent["orders"] == [{"cdek_number": "1234567890"}]
    assert len(photo.orders or []) == 2
    assert [o.cdek_number for o in photo.ready] == ["1234567890"]
    assert photo.ready[0].archive_uuid == "2f4a0f4c-6f7f-4a2f-8f5b-4b8b0e4b8b0e"
    assert route.called


async def test_photo_archive_downloads_bytes(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/photoDocument/2f4a0f4c").mock(
        return_value=httpx.Response(200, content=b"PK\x03\x04fake-zip")
    )
    client = make_client()

    data = await client.misc.photo_archive("2f4a0f4c")

    assert data.startswith(b"PK")
    assert route.called


async def test_prealert_create_is_async_task(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/prealert").mock(
        return_value=httpx.Response(202, json=load_fixture("misc", "prealert_create.json"))
    )
    client = make_client()

    task = await client.misc.prealert_create(
        PrealertCreate(
            planned_date="2026-05-12T00:00:00+0300",
            shipment_point="MSK",
            orders=[PrealertOrder(cdek_number="1234567890")],
        )
    )

    # 202 ACCEPTED — это «запрос принят», а не «преалерт создан»
    assert task.state == "ACCEPTED"
    assert task.uuid == "d1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a"
    assert route.called


async def test_prealert_create_invalid_raises(token_route: Any, make_client: Any) -> None:
    token_route.post("/v2/prealert").mock(
        return_value=httpx.Response(
            202,
            json={
                "entity": None,
                "requests": [
                    {
                        "type": "CREATE",
                        "state": "INVALID",
                        "errors": [{"code": "v2_prealert_invalid", "message": "дата раньше срока"}],
                    }
                ],
            },
        )
    )
    client = make_client()

    with pytest.raises(ApiError, match="v2_prealert_invalid"):
        await client.misc.prealert_create({"planned_date": "2026-05-12T00:00:00+0300"})


async def test_prealert_get_shows_discrepancies(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/prealert/d1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a").mock(
        return_value=httpx.Response(200, json=load_fixture("misc", "prealert_get.json"))
    )
    client = make_client()

    envelope = await client.misc.prealert_get("d1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a")
    prealert = envelope.entity

    assert prealert is not None
    assert prealert.is_closed is True
    assert prealert.fact_shipment_point == "MSK2"
    assert prealert.prealert_number == "PR-000123"
    packages = prealert.orders[0].packages or []
    assert [p.status for p in packages] == ["ACCEPTED", "NOT_ACCEPTED"]
    assert [p.number for p in prealert.discrepancies] == ["pkg-2"]


async def test_international_restrictions(token_route: Any, make_client: Any) -> None:
    route = token_route.post("/v2/international/package/restrictions").mock(
        return_value=httpx.Response(200, json=load_fixture("misc", "restrictions.json"))
    )
    client = make_client()

    hints = await client.misc.international_restrictions(
        RestrictionRequest(
            tariff_code=136,
            from_location=Location(code=44, address="ул. Тестовая, 1"),
            to_location=Location(code=176, country_code="AE"),
            packages=[
                RestrictionPackage(
                    weight=1000,
                    length=30,
                    width=20,
                    height=10,
                    items=[
                        RestrictionItem(
                            name="Джинсы мужские Henry, размер M", amount=1, item_id="1"
                        )
                    ],
                )
            ],
        )
    )

    # идентификатор товара уходит как item_id: camelCase itemId из спецификации
    # живой API отклоняет (v2_field_is_empty: [...].item_id is empty)
    sent = json.loads(route.calls.last.request.content)
    assert sent["packages"][0]["items"][0]["item_id"] == "1"
    assert hints.is_allowed is False
    package = hints.packages[0]
    assert package.status is not None and package.status.code == "LIMITED"
    assert package.status.reason is not None and package.status.reason.is_feacn is True
    assert [i.item_id for i in package.forbidden_items] == ["1"]
    assert package.items[0].documents == ["Инвойс"]


async def test_misc_raw_escape_hatch(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/brand/new/method").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = make_client()

    data = await client.misc.raw("GET", "/v2/brand/new/method")

    assert data == {"ok": True}
