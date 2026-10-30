"""Тесты моделей: сериализация, конверт ответа, терпимость к новым полям.

Фикстуры отражают реальные схемы OpenAPI-спецификации apidoc.cdek.ru.
"""

from __future__ import annotations

import warnings
from datetime import datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from cdekx.models import (
    CalculatorPackage,
    City,
    CityQuery,
    Contact,
    DeliveryAgreement,
    DeliveryPoint,
    DeliveryPointFilter,
    DeliveryPointPolygonFilter,
    EstimatedIntervalsRequest,
    Item,
    Location,
    Money,
    Order,
    OrderCreate,
    Package,
    Phone,
    TariffListResponse,
    TariffRequest,
)
from cdekx.models.base import ResponseEnvelope, RootEntity
from cdekx.types.enums import DeliveryMode
from conftest import load_fixture


def sample_order() -> OrderCreate:
    """Минимально валидный заказ по спецификации СДЭК."""
    return OrderCreate(
        type=1,
        number="ORDER-0001",
        tariff_code=136,
        from_location=Location(code=44, address="ул. Тестовая, 1"),
        to_location=Location(code=270, address="ул. Проверочная, 2"),
        sender=Contact(name="Иван Петров", phones=["+79001234567"]),
        recipient=Contact(name="Мария Смирнова", phones=["+79007654321"]),
        packages=[Package(number="PKG-1", weight=1500, length=35, width=25, height=15)],
    )


# --- запросы ----------------------------------------------------------------


def test_order_create_serializes_without_none() -> None:
    payload = sample_order().to_api()

    assert payload["type"] == 1
    assert payload["tariff_code"] == 136
    assert "comment" not in payload
    assert payload["packages"][0]["weight"] == 1500
    assert payload["recipient"]["name"] == "Мария Смирнова"


def test_phones_are_sent_as_objects() -> None:
    """Ключевая деталь API v2: phones — список объектов, а не строк."""
    payload = sample_order().to_api()

    assert payload["sender"]["phones"] == [{"number": "+79001234567"}]
    assert payload["recipient"]["phones"] == [{"number": "+79007654321"}]


def test_phone_accepts_object_with_additional() -> None:
    contact = Contact(name="Иван", phones=[{"number": "+79001234567", "additional": "123"}])

    assert contact.phones[0].additional == "123"
    assert contact.to_api()["phones"] == [{"number": "+79001234567", "additional": "123"}]


def test_phone_string_is_normalized() -> None:
    contact = Contact(name="Иван", phones=["8 (900) 123-45-67"])

    assert contact.phone_numbers == ["+79001234567"]


def test_phone_respects_max_length_from_spec() -> None:
    """``PhoneDto.number`` ограничен 24 символами — длиннее нельзя."""
    with pytest.raises(PydanticValidationError):
        Phone(number="+7" + "9" * 40)


def test_phone_additional_is_optional() -> None:
    phone = Phone(number="+79001234567")

    assert phone.additional is None
    assert phone.to_api() == {"number": "+79001234567"}


def test_enum_and_raw_values_are_interchangeable() -> None:
    from cdekx.types.enums import TariffCode

    base = {
        "from_location": {"code": 44},
        "to_location": {"code": 270},
        "packages": [{"weight": 1000}],
    }
    by_enum = TariffRequest(tariff_code=TariffCode.EXPRESS_LIGHT_DOOR_DOOR, **base)
    by_number = TariffRequest(tariff_code=136, **base)
    unknown = TariffRequest(tariff_code=2483, **base)  # тариф, которого нет в enum

    assert by_enum.to_api()["tariff_code"] == by_number.to_api()["tariff_code"] == 136
    assert unknown.to_api()["tariff_code"] == 2483


def test_money_has_no_currency_field() -> None:
    """В MoneyDto нет поля currency — валюта задаётся на уровне расчёта."""
    money = Money(value=990.0, vat_rate=22)

    assert money.to_api() == {"value": 990.0, "vat_rate": 22}
    assert "currency" not in Money.model_fields


def test_vat_rates_of_2026_are_supported() -> None:
    """Ставки НДС с 01.01.2026: 0, 5, 7, 10, 16, 22."""
    for rate in (0, 5, 7, 10, 16, 22):
        assert Money(value=1.0, vat_rate=rate).to_api()["vat_rate"] == rate


def test_item_uses_real_api_field_names() -> None:
    """``marking`` (не marking_code), ``feacn_code`` (не tn_ved_code), ``jewel_uin``."""
    item = Item(
        name="Товар",
        ware_key="SKU-1",
        payment=Money(value=10.0),
        weight=100,
        amount=1,
        cost=10.0,
        marking="010460372502012321ABCDEF",
        feacn_code="6109100000",
        jewel_uin="1234567890123456",
    )
    payload = item.to_api()

    assert payload["marking"].startswith("0104")
    assert payload["feacn_code"] == "6109100000"
    assert payload["jewel_uin"] == "1234567890123456"


def test_order_create_limits_packages() -> None:
    """По спецификации в заказе от 1 до 255 мест."""
    with pytest.raises(PydanticValidationError):
        sample_order().model_copy(update={"packages": []})
        OrderCreate(
            tariff_code=136,
            recipient=Contact(name="x", phones=["+79001234567"]),
            packages=[],
        )


def test_delivery_point_filter_query_serialization() -> None:
    query = DeliveryPointFilter(city_code=44, type="PVZ", have_cash=True).to_query()

    assert query == {"city_code": 44, "type": "PVZ", "have_cash": True}


def test_delivery_point_polygon_filter_only_supported_fields() -> None:
    """``byPolygons`` поддерживает меньше фильтров, чем список офисов."""
    supported = {
        "type",
        "city_uuid",
        "have_cashless",
        "have_cash",
        "allowed_cod",
        "is_dressing_room",
        "weight_max",
        "weight_min",
        "lang",
    }
    assert set(DeliveryPointPolygonFilter.model_fields) == supported

    query = DeliveryPointPolygonFilter(type="PVZ", have_cash=True, weight_max=10).to_query()
    assert query == {"type": "PVZ", "have_cash": True, "weight_max": 10}


def test_delivery_point_parses_localized_name() -> None:
    """С 10.2025 в ``OfficeDto`` есть локализованное наименование офиса."""
    points = [DeliveryPoint.model_validate(p) for p in load_fixture("delivery", "list.json")]

    assert points[0].name == "Охотный ряд"
    assert points[1].name is None  # поле необязательное


def test_delivery_mode_covers_postamat_values() -> None:
    """``OrderResponseDto.delivery_mode``: 1–4 и 6–10 (значения 5 нет)."""
    assert [mode.value for mode in DeliveryMode] == [1, 2, 3, 4, 6, 7, 8, 9, 10]
    assert DeliveryMode.DOOR_POSTAMAT == 6
    assert DeliveryMode.POSTAMAT_POSTAMAT == 10

    raw = load_fixture("orders", "get.json")
    raw["entity"]["delivery_mode"] = 7
    order = ResponseEnvelope[Order].model_validate(raw).entity

    assert order is not None
    assert order.delivery_mode == 7
    assert DeliveryMode(order.delivery_mode) is DeliveryMode.PICKUP_POSTAMAT


def test_estimated_intervals_from_location_optional() -> None:
    """``from_location`` обязателен только для тарифов «от двери»."""
    request = EstimatedIntervalsRequest(
        date_time="2026-10-28T10:00:00Z",
        tariff_code=137,
        shipment_point="MSK1",
        to_location=Location(code=270, address="ул. Проверочная, 2"),
    )
    body = request.to_api()

    assert "from_location" not in body
    assert body["shipment_point"] == "MSK1"

    door = EstimatedIntervalsRequest(
        date_time="2026-10-28T10:00:00Z",
        tariff_code=136,
        from_location=Location(code=44, address="ул. Тестовая, 1"),
        to_location=Location(code=270, address="ул. Проверочная, 2"),
    )
    assert door.to_api()["from_location"]["address"] == "ул. Тестовая, 1"


def test_delivery_agreement_time_only_required_for_door_delivery() -> None:
    """``time_from``/``time_to`` обязательны, только если заказ «до двери»."""
    pickup = DeliveryAgreement(cdek_number="1234567890", date="2026-10-28")

    assert pickup.to_api() == {"cdek_number": "1234567890", "date": "2026-10-28"}

    door = DeliveryAgreement(
        cdek_number="1234567890", date="2026-10-28", time_from="10:00", time_to="14:00"
    )
    assert door.to_api()["time_from"] == "10:00"
    assert door.to_api()["time_to"] == "14:00"


def test_fias_region_guid_marked_deprecated() -> None:
    """Поле устарело по спецификации apidoc.cdek.ru — чтение предупреждает."""
    schema = CityQuery.model_json_schema()["properties"]["fias_region_guid"]
    assert schema.get("deprecated") is True

    city = City.model_validate(
        {
            "code": 44,
            "city_uuid": "34c7352b-1dfa-4827-8614-9710fb326513",
            "city": "Москва",
            "country_code": "RU",
            "country": "Россия",
            "payment_limit": 500000,
            "fias_region_guid": "7c453ecd-d053-4008-ba49-d4a3bae6e662",
        }
    )

    with pytest.warns(DeprecationWarning, match="Deprecated field"):
        assert city.fias_region_guid == "7c453ecd-d053-4008-ba49-d4a3bae6e662"

    # сериализация запроса/ответа предупреждений не вызывает
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        query = CityQuery(fias_region_guid="7c453ecd-d053-4008-ba49-d4a3bae6e662")
        assert query.to_query()["fias_region_guid"] == "7c453ecd-d053-4008-ba49-d4a3bae6e662"
        assert city.to_api()["fias_region_guid"] == "7c453ecd-d053-4008-ba49-d4a3bae6e662"


def test_city_payment_limit_special_values_documented() -> None:
    """-1 — ограничения нет, 0 — наложенный платёж не принимается."""
    description = City.model_fields["payment_limit"].description or ""
    query_description = CityQuery.model_fields["payment_limit"].description or ""

    for text in (description, query_description):
        assert "-1" in text
        assert "not accepted" in text


# --- ответы -----------------------------------------------------------------


def test_order_response_parses_from_envelope() -> None:
    """GET /v2/orders/{uuid} возвращает конверт entity/requests/related_entities."""
    raw = load_fixture("orders", "get.json")

    envelope = ResponseEnvelope[Order].model_validate(raw)
    order = envelope.entity

    assert order is not None
    assert order.uuid == "8dea00e3-9aab-4d8e-887c-ef2aaa546456"
    assert order.cdek_number == "1234567890"
    assert order.tariff_code == 136
    assert order.is_reverse is False
    assert order.delivery_mode == 1
    assert order.has_reverse_order is True
    assert envelope.state == "SUCCESSFUL"
    assert envelope.is_successful


def test_order_related_entities_are_parsed() -> None:
    envelope = ResponseEnvelope[Order].model_validate(load_fixture("orders", "get.json"))

    assert envelope.related_entities is not None
    assert len(envelope.related_entities) == 2
    assert envelope.related("reverse_order")[0].cdek_number == "1234567891"

    waybill = envelope.related("waybill")[0]
    assert waybill.url is not None and waybill.url.endswith(".pdf")


def test_order_requests_carry_state_and_errors() -> None:
    envelope = ResponseEnvelope[Order].model_validate(load_fixture("orders", "invalid_task.json"))

    assert envelope.state == "INVALID"
    assert envelope.is_invalid
    assert [e.code for e in envelope.errors] == [
        "v2_sender_location_not_recognized",
        "v2_outdated_tariff",
    ]


def test_order_phones_are_parsed_as_objects() -> None:
    order = Order.model_validate(load_fixture("orders", "entity.json"))

    assert order.sender is not None
    assert isinstance(order.sender.phones[0], Phone)
    assert order.sender.phones[0].number == "+79001234567"
    assert order.sender.phones[0].additional == "123"
    assert order.sender.phone_numbers == ["+79001234567"]


def test_order_statuses_use_real_field_names() -> None:
    """``city``/``city_uuid``/``name``/``deleted`` — не ``city_name``/``city_code``."""
    order = Order.model_validate(load_fixture("orders", "entity.json"))

    assert order.statuses is not None
    current = order.current_status
    assert current is not None
    assert current.code == "IN_TRANSIT"
    assert current.name == "В пути"
    assert current.city == "Москва"
    assert current.city_uuid == "0c5b2444-70a0-4932-980c-b4dc0d3f02b5"
    assert current.deleted is False
    assert order.status_code == "IN_TRANSIT"


def test_order_packages_response_fields() -> None:
    order = Order.model_validate(load_fixture("orders", "entity.json"))

    assert order.packages is not None
    package = order.packages[0]
    assert package.barcode == "00001234567"
    assert package.weight_volume == 2625
    assert package.weight_calc == 2625
    assert order.barcodes == ["00001234567"]


def test_order_delivery_detail_is_money_not_interval() -> None:
    detail = Order.model_validate(load_fixture("orders", "entity.json")).delivery_detail

    assert detail is not None
    assert detail.delivery_sum == 350.0
    assert detail.total_sum == 2340.0
    assert detail.payment_sum == 1990.0
    assert detail.payment_info is not None
    assert detail.payment_info[0].type == "CARD"


def test_datetime_with_offset_is_parsed() -> None:
    order = Order.model_validate(load_fixture("orders", "entity.json"))
    created = order.statuses[0].date_time if order.statuses else None

    assert isinstance(created, datetime)
    assert created is not None
    assert created.utcoffset() is not None
    assert created.year == 2026


def test_unknown_fields_are_preserved() -> None:
    """СДЭК добавил новое поле — модель не падает, поле доступно в extra."""
    order = Order.model_validate(load_fixture("orders", "entity.json"))

    assert order.extra["some_new_cdek_field"] == {"unexpected": True}


def test_task_envelope_exposes_uuid() -> None:
    envelope = ResponseEnvelope[RootEntity].model_validate(load_fixture("orders", "create.json"))

    assert envelope.uuid == "8dea00e3-9aab-4d8e-887c-ef2aaa546456"
    assert envelope.state == "ACCEPTED"
    assert envelope.last_request is not None
    assert envelope.last_request.type == "CREATE"


def test_warnings_are_parsed() -> None:
    envelope = ResponseEnvelope[RootEntity].model_validate(load_fixture("orders", "update.json"))

    assert [w.code for w in envelope.warnings] == ["v2_cost_change_by_tariff"]


def test_tariff_list_response_helpers() -> None:
    response = TariffListResponse.model_validate(load_fixture("calculator", "tarifflist.json"))

    assert len(response.tariff_codes) == 2
    best = response.best()
    fastest = response.fastest()
    assert best is not None and best.tariff_code == 5  # 320 ₽ дешевле 480.5 ₽
    assert fastest is not None and fastest.tariff_code == 136  # 2 раб. дня против 4


def test_tariff_list_filters_out_broken_tariffs() -> None:
    raw = load_fixture("calculator", "tarifflist.json")
    raw["tariff_codes"].append(
        {
            "tariff_code": 62,
            "tariff_name": "Магистральный грузовой",
            "tariff_description": "",
            "delivery_mode": 4,
            "delivery_sum": 0,
            "period_min": 0,
            "period_max": 0,
            "errors": [{"code": "v2_outdated_tariff", "message": "Tariff 62 is outdated"}],
        }
    )
    response = TariffListResponse.model_validate(raw)

    assert len(response.tariff_codes) == 3
    assert len(response.viable) == 2
    assert response.best().tariff_code == 5  # type: ignore[union-attr]


def test_calculator_package_requires_weight() -> None:
    with pytest.raises(PydanticValidationError):
        CalculatorPackage()  # type: ignore[call-arg]
