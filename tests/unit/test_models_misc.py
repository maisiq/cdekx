"""Тесты моделей «прочих» разделов API и формы ответа «список + ошибки».

Схемы взяты из OpenAPI-спецификации apidoc.cdek.ru:

* ``CheckResponseDto``/``CheckInfoDto`` — чеки (``GET /v2/check``);
* ``PassportResponseDto`` — паспортные данные (``GET /v2/passport``);
* ``RegistriesResponseDto`` — реестры НП (``GET /v2/registries``);
* ``PhotoRequestDto``/``PhotoResponseDto`` — фото документов;
* ``RegisterPrealertRequestDto``/``GetPrealertResponseDto`` — преалерты;
* ``RestrictionHints*Dto`` — международные ограничения;
* ``ReverseValidateRequestDto`` — проверка доступности реверса;
* ``FailedCallResponseDto``/``RescheduledCallResponseDto`` — прозвоны;
* ``IntakePackageDto``, ``IntakeChangeStatusResponseDto`` — заявки.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from cdekx.models import (
    CdekModel,
    CheckResponse,
    FailedCall,
    IntakeAvailableDays,
    IntakePackage,
    ListResponse,
    PassportResponse,
    PhotoReadyOrder,
    PhotoRequest,
    Prealert,
    PrealertCreate,
    RegistriesResponse,
    RescheduledCall,
    RestrictionHintsResponse,
    RestrictionItem,
    RestrictionRequest,
    ReverseContragent,
    ReverseValidateRequest,
)
from cdekx.models.base import ResponseEnvelope
from cdekx.models.misc import PrealertOrderInfo, ReverseLocation
from conftest import load_fixture

MSK = timezone(timedelta(hours=3))


# --- форма ответа «список + ошибки» ------------------------------------------


def test_list_response_exposes_errors_and_warnings() -> None:
    """HTTP 200 не гарантирует успех: ошибки лежат в теле ответа."""
    response = ListResponse.model_validate(
        {"errors": [{"code": "v2_entity_not_found", "message": "не найдено"}], "warnings": []}
    )

    assert response.has_errors is True
    assert response.error_codes == ("v2_entity_not_found",)


def test_list_response_without_errors_is_ok() -> None:
    response = ListResponse.model_validate({})

    assert response.has_errors is False
    assert response.error_codes == ()
    assert response.errors is None


def test_list_response_keeps_unknown_fields() -> None:
    """СДЭК добавляет поля — extra='allow' не должен их терять."""
    response = CheckResponse.model_validate({"check_info": [], "brand_new_field": 42, "errors": []})

    assert response.extra == {"brand_new_field": 42}
    assert isinstance(response, CdekModel)


# --- чеки --------------------------------------------------------------------


def test_check_info_parses_int64_cdek_number_as_string() -> None:
    """В CheckInfoDto cdek_number — int64, хотя в OrderResponseDto это строка."""
    response = CheckResponse.model_validate_json(
        b'{"check_info": [{"order_uuid": "u1", "cdek_number": 1234567890,'
        b' "date": "2026-05-05T10:12:33+0000", "fiscal_storage_number": "1",'
        b' "document_number": "2", "fiscal_sign": 3, "type": "CASH_RECEIPT_IN",'
        b' "payment_info": [{"sum": 100.0, "type": "CARD"}]}]}'
    )
    check = response.checks[0]

    assert check.cdek_number == "1234567890"
    assert check.type == "CASH_RECEIPT_IN"
    assert check.payment_info[0].type == "CARD"
    assert isinstance(check.date, datetime)


def test_check_info_sums_payment_info() -> None:
    response = CheckResponse.model_validate(load_fixture("misc", "check.json"))

    assert response.checks[0].total == 2400.5


def test_check_response_empty_check_info_gives_empty_list() -> None:
    assert CheckResponse.model_validate({}).checks == []


# --- паспортные данные -------------------------------------------------------


def test_passport_response_filters_unsatisfied() -> None:
    response = PassportResponse.model_validate(load_fixture("misc", "passport.json"))

    assert len(response.orders or []) == 2
    assert response.orders[0].passport.client == "ALL"
    assert response.orders[0].ok is True
    assert [o.cdek_number for o in response.unsatisfied] == ["1234567891"]


# --- реестры наложенного платежа ---------------------------------------------


def test_registries_parses_sums_and_dates() -> None:
    response = RegistriesResponse.model_validate(load_fixture("misc", "registries.json"))
    registry = response.registries[0]

    assert registry.registry_number == 123456
    assert registry.sum == 2400.5
    assert registry.payment_date == date(2026, 5, 6)
    assert registry.payment_order_number == "778"
    assert registry.orders[0].basis_type == "ORDER"
    assert response.total == 2400.5


def test_registries_total_of_empty_response_is_zero() -> None:
    assert RegistriesResponse.model_validate({}).total == 0.0


# --- фото документов ---------------------------------------------------------


def test_photo_request_serializes_datetime_in_cdek_format() -> None:
    """СДЭК ждёт ``yyyy-MM-dd'T'HH:mm:ssZ`` — без двоеточия в смещении."""
    request = PhotoRequest(
        period_begin=datetime(2026, 4, 1, 0, 0, tzinfo=MSK),
        period_end=datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc),
    )

    assert request.to_api() == {
        "period_begin": "2026-04-01T00:00:00+0300",
        "period_end": "2026-04-30T23:59:59+0000",
    }


def test_photo_request_passes_string_dates_through() -> None:
    """Строку в формате СДЭК не переформатируем: что передали, то и ушло."""
    request = PhotoRequest(period_begin="2026-04-01T00:00:00+0000")

    assert request.to_api() == {"period_begin": "2026-04-01T00:00:00+0000"}


def test_photo_ready_order_extracts_archive_uuid() -> None:
    order = PhotoReadyOrder(
        link="https://api.cdek.ru/v2/photoDocument/2f4a0f4c-6f7f-4a2f-8f5b-4b8b0e4b8b0e",
        status="DONE",
    )

    assert order.archive_uuid == "2f4a0f4c-6f7f-4a2f-8f5b-4b8b0e4b8b0e"
    assert order.is_ready is True


def test_photo_ready_order_without_link_has_no_uuid() -> None:
    assert PhotoReadyOrder(status="IN_PROGRESS").archive_uuid is None
    assert PhotoReadyOrder(status="IN_PROGRESS").is_ready is False


def test_photo_response_ready_filters_by_done() -> None:
    from cdekx.models import PhotoResponse

    response = PhotoResponse.model_validate(load_fixture("misc", "photo_document.json"))

    assert len(response.orders or []) == 2
    assert [o.status for o in response.ready] == ["DONE"]


# --- преалерты ---------------------------------------------------------------


def test_prealert_create_serializes_planned_date_in_cdek_format() -> None:
    prealert = PrealertCreate(
        planned_date=datetime(2026, 5, 12, 0, 0, tzinfo=MSK),
        shipment_point="MSK",
        orders=[{"cdek_number": 1234567890}],
    )

    assert prealert.to_api() == {
        "planned_date": "2026-05-12T00:00:00+0300",
        "shipment_point": "MSK",
        # cdek_number в схеме запроса — int64: значение не нормализуется к строке
        "orders": [{"cdek_number": 1234567890}],
    }


def test_prealert_create_requires_all_three_fields() -> None:
    with pytest.raises(PydanticValidationError) as exc:
        PrealertCreate(shipment_point="MSK")  # type: ignore[call-arg]

    assert {"planned_date", "orders"} <= {e["loc"][0] for e in exc.value.errors()}


def test_prealert_parses_what_live_api_actually_returns() -> None:
    """Живой GET /v2/prealert/{uuid} не возвращает ни uuid, ни order_uuid.

    Ответ учебной среды (преалерт, созданный по cdek_number):
    ``{"planned_date": ..., "shipment_point": "MSK", "orders": [{"cdek_number": 1234567890}]}``
    — по схеме все три поля plus uuid обязательны, по факту их нет.
    """
    prealert = Prealert.model_validate(
        {
            "planned_date": "2026-11-02T21:00:00+0000",
            "shipment_point": "MSK",
            "orders": [{"cdek_number": 1234567890}],
        }
    )

    assert prealert.uuid is None
    assert prealert.orders[0].order_uuid is None
    assert prealert.orders[0].cdek_number == "1234567890"  # int64 → str
    assert prealert.is_closed is False


def test_prealert_collects_discrepancies_across_orders() -> None:
    envelope = load_fixture("misc", "prealert_get.json")
    prealert = Prealert.model_validate(envelope["entity"])

    assert prealert.is_closed is True
    assert prealert.prealert_number == "PR-000123"
    assert prealert.fact_shipment_point == "MSK2"
    assert [p.number for p in prealert.discrepancies] == ["pkg-2"]
    assert prealert.orders[0].packages[0].is_accepted is True


def test_prealert_order_info_cdek_number_is_string() -> None:
    """В GetPrealertResponseDtoOrderDto cdek_number объявлен как int64."""
    order = PrealertOrderInfo.model_validate(
        {"order_uuid": "u1", "cdek_number": 1234567890, "packages": []}
    )

    assert order.cdek_number == "1234567890"


def test_prealert_open_state_has_no_discrepancies() -> None:
    prealert = Prealert.model_validate(
        {"uuid": "p1", "planned_date": "2026-05-12T00:00:00+0300", "shipment_point": "MSK"}
    )

    assert prealert.is_closed is False
    assert prealert.orders == []
    assert prealert.discrepancies == []


# --- ограничения международных заказов ---------------------------------------


def test_restriction_item_sends_snake_case_item_id() -> None:
    """В спецификации поле ``itemId``, но живой API требует ``item_id``.

    Проверено на ``api.edu.cdek.ru``: на ``itemId`` метод отвечает
    ``v2_field_is_empty: [packages[0].items[0].item_id] is empty``.
    """
    item = RestrictionItem(name="Джинсы мужские Henry, размер M", amount=1, item_id="SKU-1")

    assert item.to_api() == {
        "name": "Джинсы мужские Henry, размер M",
        "amount": 1,
        "item_id": "SKU-1",
    }
    assert "itemId" not in item.to_api()


def test_restriction_request_dumps_locations_and_packages() -> None:
    request = RestrictionRequest(
        tariff_code=136,
        from_location={"code": 44, "address": "ул. Тестовая, 1"},
        to_location={"code": 176, "country_code": "AE"},
        packages=[{"weight": 1000, "items": [{"name": "Товар", "amount": 2}]}],
    )
    body = request.to_api()

    assert body["tariff_code"] == 136
    assert body["from_location"]["code"] == 44
    assert body["to_location"]["country_code"] == "AE"
    assert body["packages"][0]["items"][0]["amount"] == 2


def test_restriction_hints_forbidden_item_forbids_package() -> None:
    """Статус места может быть LIMITED, хотя товар внутри — FORBIDDEN."""
    response = RestrictionHintsResponse.model_validate(load_fixture("misc", "restrictions.json"))
    package = response.packages[0]

    assert package.status is not None and package.status.code == "LIMITED"
    assert package.status.reason is not None and package.status.reason.is_feacn is True
    assert package.is_forbidden is True
    assert response.is_allowed is False
    assert [i.item_id for i in package.forbidden_items] == ["1"]
    assert package.items[0].documents == ["Инвойс"]
    assert package.items[1].status is not None and package.items[1].status.is_allowed is True


def test_restriction_hints_all_allowed() -> None:
    response = RestrictionHintsResponse.model_validate(
        {"packages": [{"package_id": "p1", "status": {"code": "ALLOWED", "name": "Разрешено"}}]}
    )

    assert response.is_allowed is True
    assert response.forbidden == []


# --- проверка доступности реверса --------------------------------------------


def test_reverse_request_requires_tariff_and_contacts() -> None:
    with pytest.raises(PydanticValidationError) as exc:
        ReverseValidateRequest()  # type: ignore[call-arg]

    assert {"tariff_code", "sender", "recipient"} <= {e["loc"][0] for e in exc.value.errors()}


def test_reverse_contragent_normalizes_phones() -> None:
    """Телефоны реверса — те же PhoneDto, но без ФИО контрагента."""
    contragent = ReverseContragent(phones=["89001234567", {"number": "+79007654321"}])

    assert contragent.phones[0].number == "+79001234567"
    assert contragent.phones[1].number == "+79007654321"
    assert contragent.to_api() == {
        "phones": [{"number": "+79001234567"}, {"number": "+79007654321"}]
    }


def test_reverse_contragent_requires_phones() -> None:
    with pytest.raises(PydanticValidationError):
        ReverseContragent()  # type: ignore[call-arg]


def test_reverse_request_dumps_only_filled_fields() -> None:
    request = ReverseValidateRequest(
        tariff_code=136,
        delivery_point="MSK",
        from_location=ReverseLocation(code=44, address="ул. Тестовая, 1"),
        sender=ReverseContragent(phones=["+79001234567"]),
        recipient=ReverseContragent(phones=["+79007654321"]),
    )
    body = request.to_api()

    assert body["delivery_point"] == "MSK"
    assert body["from_location"] == {"code": 44, "address": "ул. Тестовая, 1"}
    assert "to_location" not in body
    assert "shipment_point" not in body


def test_reverse_location_has_no_city_uuid_field() -> None:
    """Набор полей уже, чем у Location: city_uuid/kladr_code/time_zone не ожидаются."""
    from cdekx.models import Location

    extra = set(Location.model_fields) - set(ReverseLocation.model_fields)

    assert {"city_uuid", "kladr_code", "time_zone", "payment_limit"} <= extra
    assert set(ReverseLocation.model_fields) <= set(Location.model_fields)


# --- прозвоны получателя ------------------------------------------------------


def test_failed_call_uses_reason_code_from_spec() -> None:
    call = FailedCall.model_validate({"date_time": "2026-05-05T10:00:00+0300", "reason_code": 3})

    assert call.reason_code == 3
    assert call.reason is None  # поля нет в спецификации — сохранено для совместимости


def test_failed_call_requires_reason_code() -> None:
    with pytest.raises(PydanticValidationError):
        FailedCall.model_validate({"date_time": "2026-05-05T10:00:00+0300"})


def test_rescheduled_call_parses_next_date_and_time() -> None:
    call = RescheduledCall.model_validate(
        {
            "date_time": "2026-05-05T10:00:00+0300",
            "date_next": "2026-05-06",
            "time_next": "09:00",
            "comment": "получатель попросил перенести",
        }
    )

    assert call.date_next == date(2026, 5, 6)
    assert call.time_next == "09:00"
    assert call.comment == "получатель попросил перенести"


def test_rescheduled_call_requires_next_slot() -> None:
    with pytest.raises(PydanticValidationError) as exc:
        RescheduledCall.model_validate({"date_time": "2026-05-05T10:00:00+0300"})

    assert {"date_next", "time_next"} <= {e["loc"][0] for e in exc.value.errors()}


# --- заявки: упаковки и конверт смены статуса ---------------------------------


def test_intake_package_has_no_number_field() -> None:
    """IntakePackageDto отличается от упаковки заказа: нет number/items/barcode."""
    from cdekx.models import Package, PackageResponse

    package = IntakePackage.model_validate({"package_id": "p1", "weight": 1500})

    assert package.weight == 1500
    assert {"number", "items"} <= set(Package.model_fields)
    assert "barcode" in set(PackageResponse.model_fields)
    assert not {"number", "items", "barcode"} & set(IntakePackage.model_fields)


def test_intake_info_parses_typed_packages() -> None:
    from cdekx.models import IntakeInfo

    intake = IntakeInfo.model_validate(
        {
            "uuid": "i1",
            "intake_date": "2026-05-10",
            "intake_time_from": "10:00",
            "intake_time_to": "18:00",
            "from_location": {"code": 44, "address": "ул. Тестовая, 1"},
            "statuses": [],
            "packages": [{"package_id": "p1", "weight": 1500, "length": 30}],
        }
    )

    assert isinstance(intake.packages[0], IntakePackage)
    assert intake.packages[0].length == 30


def test_intake_change_status_envelope_entity_is_root_entity() -> None:
    """IntakeChangeStatusResponseEntity содержит только uuid → RootEntity."""
    from cdekx.endpoints import IntakeEnvelope

    envelope = IntakeEnvelope.model_validate(
        {"entity": {"uuid": "i1"}, "requests": [{"type": "UPDATE", "state": "SUCCESSFUL"}]}
    )

    assert isinstance(envelope, ResponseEnvelope)
    assert envelope.uuid == "i1"
    assert envelope.is_successful is True


def test_intake_available_days_types_errors_and_dates() -> None:
    days = IntakeAvailableDays.model_validate(load_fixture("intakes", "available_days.json"))

    assert days.date == [date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13)]
    assert days.has_errors is False


def test_intake_available_days_all_days_without_dates() -> None:
    """Если забор доступен по всем дням, список date не возвращается."""
    days = IntakeAvailableDays.model_validate({"all_days": True})

    assert days.all_days is True
    assert days.date is None
