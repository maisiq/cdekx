"""Интеграционные тесты против учебной среды СДЭК (api.edu.cdek.ru).

Запускаются **только вручную**::

    CDEKX_RUN_INTEGRATION=1 \
    CDEKX_CLIENT_ID=... CDEKX_CLIENT_SECRET=... \
    pytest -m integration -v

Без переменных окружения используются публичные тестовые ключи СДЭК из
документации (apidoc.cdek.ru → «Подключение к сервису»). Заказы в учебной
среде не доставляются.

Учебная среда бывает нестабильна, поэтому тесты не входят в обязательный CI.
"""

from __future__ import annotations

import contextlib
import os
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest

from cdekx import ApiError, CdekClient, Environment, TimeoutExceeded
from cdekx.endpoints.webhooks import WebhooksEndpoint
from cdekx.models import (
    MAX_WEBHOOK_SUBSCRIPTIONS,
    TOO_MANY_WEBHOOKS_ERROR,
    CalculatorLocation,
    CalculatorPackage,
    Contact,
    DeliveryPointFilter,
    Item,
    ListResponse,
    Location,
    Money,
    OrderCreate,
    Package,
    PhotoOrder,
    PhotoRequest,
    PhotoResponse,
    PrealertCreate,
    PrealertOrder,
    RegistriesResponse,
    RestrictionHintsResponse,
    RestrictionItem,
    RestrictionPackage,
    RestrictionRequest,
    ReverseContragent,
    ReverseLocation,
    ReverseValidateRequest,
    TariffListRequest,
)

RUN = os.getenv("CDEKX_RUN_INTEGRATION") in {"1", "true", "yes"}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not RUN, reason="нужен CDEKX_RUN_INTEGRATION=1"),
]

MOSCOW = 44
YEKATERINBURG = 270
#: Зарубежный «город» без почтовых индексов (ОАЭ) — API отдаёт ``postal_codes: [null]``.
DUBAI = 176


@pytest.fixture
async def client() -> AsyncIterator[CdekClient]:
    """Клиент учебной среды."""
    client_id = os.getenv("CDEKX_CLIENT_ID") or os.getenv("CDEK_CLIENT_ID")
    client_secret = os.getenv("CDEKX_CLIENT_SECRET") or os.getenv("CDEK_CLIENT_SECRET")

    if client_id and client_secret:
        instance = CdekClient(client_id, client_secret, environment=Environment.SANDBOX)
    else:
        instance = CdekClient.sandbox()

    try:
        yield instance
    finally:
        await instance.aclose()


async def test_oauth_token_is_issued(client: CdekClient) -> None:
    """Авторизация работает: справочный метод отвечает без 401."""
    cities = await client.locations.cities({"code": MOSCOW, "size": 1})
    assert cities


async def test_calculator_tariff(client: CdekClient) -> None:
    result = await client.calculator.tariff(
        {
            "tariff_code": 136,
            "from_location": {"code": MOSCOW},
            "to_location": {"code": YEKATERINBURG},
            "packages": [{"weight": 1000, "length": 30, "width": 20, "height": 10}],
            # Валюта расчёта — ЧИСЛОВОЙ код из «Приложения 14» (1 = RUB).
            # Строку "RUB" API отклоняет: v2_invalid_value_type in [currency].
            "currency": 1,
            "lang": "rus",
        }
    )

    assert result.delivery_sum > 0
    assert result.period_min >= 0
    assert result.weight_calc > 0


async def test_calculator_tariff_list(client: CdekClient) -> None:
    result = await client.calculator.tariff_list(
        TariffListRequest(
            from_location=CalculatorLocation(code=MOSCOW),
            to_location=CalculatorLocation(code=YEKATERINBURG),
            packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
        )
    )

    assert result.tariff_codes, "учебная среда должна вернуть хотя бы один тариф"
    assert result.viable
    assert all(t.delivery_sum > 0 for t in result.viable)


async def test_available_tariffs(client: CdekClient) -> None:
    available = await client.calculator.available_tariffs()

    assert available.tariff_codes
    assert available.all_tariff_codes()


async def test_delivery_points_for_moscow(client: CdekClient) -> None:
    points = await client.delivery_points.list(DeliveryPointFilter(city_code=MOSCOW, type="ALL"))

    assert points
    assert all(p.code and p.location.address for p in points)


async def test_cities_pagination(client: CdekClient) -> None:
    codes = []
    async for city in client.locations.paginate_cities(page_size=100):
        codes.append(city.code)
        if len(codes) >= 250:
            break

    assert len(codes) >= 101  # значит, пагинация реально переключает страницы


async def test_postalcodes(client: CdekClient) -> None:
    """Ответ — объект ``{code, postal_codes}`` (``PostcodesResponseDto``)."""
    postcodes = await client.locations.postalcodes(MOSCOW)

    assert postcodes.code == MOSCOW
    assert postcodes.postal_codes, "у Москвы должны быть почтовые индексы"
    assert all(isinstance(code, str) and code.isdigit() for code in postcodes.values)
    assert postcodes.values == [code for code in postcodes.postal_codes if code]


async def test_postalcodes_foreign_city(client: CdekClient) -> None:
    """У зарубежных «городов» индексов нет: API отдаёт ``[null]`` (code=176, ОАЭ)."""
    postcodes = await client.locations.postalcodes(DUBAI)

    assert postcodes.code == DUBAI
    assert postcodes.values == []
    assert all(code is None for code in postcodes.postal_codes)


async def test_suggest_cities(client: CdekClient) -> None:
    suggestions = await client.locations.suggest_cities("Новосиб", country_code="RU")

    assert suggestions
    assert any("Новосиб" in s.full_name for s in suggestions)


async def test_webhooks_list(client: CdekClient) -> None:
    hooks = await client.webhooks.list()

    # Учебный аккаунт публичный: подписки в нём создают и другие интеграторы,
    # поэтому количество не утверждаем — проверяем только разбор ответа.
    assert isinstance(hooks, list)
    for hook in hooks:
        assert hook.uuid
        assert hook.type
        assert hook.url


async def test_webhooks_limit_is_enforced_by_api(client: CdekClient) -> None:
    """Лимит «2 активные подписки» в спецификации не описан — проверяем API.

    Общий учебный аккаунт: свои подписки создавать нельзя (их пришлось бы
    удалять за всеми, а в аккаунте работают другие интеграторы). Поэтому
    проверяем только отказ сервера, когда активные подписки уже заняты.
    """
    hooks = await client.webhooks.list()
    if len(hooks) < MAX_WEBHOOK_SUBSCRIPTIONS:
        pytest.skip("в общем учебном аккаунте есть свободный слот — отказ не воспроизвести")

    with pytest.raises(ApiError) as excinfo:
        await client.webhooks.create("https://example.invalid/cdekx-integration-test")

    exc = excinfo.value
    assert exc.status_code == 400
    assert exc.has_code(TOO_MANY_WEBHOOKS_ERROR)
    assert WebhooksEndpoint.is_limit_error(exc)
    assert "Maximum allowed is 2" in (exc.errors[0].message or "")


async def test_order_lifecycle(client: CdekClient) -> None:
    """Полный цикл: регистрация → чтение → ожидание → удаление.

    Общий учебный аккаунт бывает сильно нагружен: СДЭК декларирует обработку
    запроса до 60 с, фактически она может занимать дольше. Заказ доступен для
    чтения по UUID сразу после регистрации (ещё до окончания обработки),
    поэтому чтение и удаление проверяются всегда, а ожидание конечного
    состояния — только если песочница успела обработать запрос.
    """
    number = f"CDEKX-TEST-{uuid_lib.uuid4().hex[:8].upper()}"
    order = OrderCreate(
        type=1,
        number=number,
        tariff_code=136,
        from_location=Location(code=MOSCOW, address="ул. Тестовая, 1"),
        to_location=Location(code=YEKATERINBURG, address="ул. Проверочная, 2, кв. 5"),
        sender=Contact(name="Тест Тестович", phones=["+79001234567"]),
        recipient=Contact(name="Проверка Проверочкина", phones=["+79007654321"]),
        packages=[
            Package(
                number="PKG-1",
                weight=1000,
                length=30,
                width=20,
                height=10,
                items=[
                    Item(
                        name="Тестовый товар",
                        ware_key="TEST-1",
                        payment=Money(value=100.0, vat_rate=22),
                        cost=100.0,
                        weight=1000,
                        amount=1,
                    )
                ],
            )
        ],
    )

    task = await client.orders.create(order)
    assert task.uuid
    assert task.state in {"ACCEPTED", None, "SUCCESSFUL"}

    try:
        # Заказ читается по UUID сразу, даже пока запрос в состоянии ACCEPTED.
        pending = await client.orders.get(task.uuid)
        assert pending.number == number

        try:
            envelope = await client.orders.wait(task.uuid, timeout=90, interval=3)
        except TimeoutExceeded:
            pytest.skip("песочница не завершила обработку заказа (нагрузка общего аккаунта)")
        assert envelope.entity is not None

        created = await client.orders.get_by_client_number(number)
        assert created.number == number
        assert created.cdek_number
    finally:
        await client.orders.delete(task.uuid)


async def test_order_without_items_is_rejected(client: CdekClient) -> None:
    """Синхронный отказ 400: ошибки лежат в конверте ``requests[].errors``."""
    number = f"CDEKX-BAD-{uuid_lib.uuid4().hex[:6].upper()}"
    payload = {
        "type": 1,
        "number": number,
        "tariff_code": 136,
        "from_location": {"code": MOSCOW, "address": "ул. Тестовая, 1"},
        "to_location": {"code": YEKATERINBURG, "address": "ул. Проверочная, 2"},
        "sender": {"name": "Тест Тестович", "phones": [{"number": "+79001234567"}]},
        "recipient": {"name": "Проверка Проверочкина", "phones": [{"number": "+79007654321"}]},
        "packages": [{"number": "PKG-1", "weight": 1000}],  # без items — невалидно
    }

    with pytest.raises(ApiError) as excinfo:
        await client.orders.create(payload)

    exc = excinfo.value
    assert exc.status_code == 400
    assert exc.errors, "ошибки должны извлекаться из requests[].errors конверта"
    assert exc.errors[0].code == "v2_field_is_empty"
    assert "items" in (exc.errors[0].message or "")


async def test_duplicate_order_number_is_rejected(client: CdekClient) -> None:
    """Дубликат номера заказа отклоняется при асинхронной обработке (INVALID).

    Синхронно СДЭК отвечает 202 ACCEPTED и на дубликат — отказ приходит позже,
    в состоянии запроса. На нагруженной песочнице обработка может не успеть
    завершиться, тогда тест пропускается.
    """
    number = f"CDEKX-DUP-{uuid_lib.uuid4().hex[:6].upper()}"

    def payload() -> dict:
        return {
            "type": 1,
            "number": number,
            "tariff_code": 136,
            "from_location": {"code": MOSCOW, "address": "ул. Тестовая, 1"},
            "to_location": {"code": YEKATERINBURG, "address": "ул. Проверочная, 2"},
            "sender": {"name": "Тест Тестович", "phones": [{"number": "+79001234567"}]},
            "recipient": {
                "name": "Проверка Проверочкина",
                "phones": [{"number": "+79007654321"}],
            },
            "packages": [
                {
                    "number": "PKG-1",
                    "weight": 1000,
                    "items": [
                        {
                            "name": "Тестовый товар",
                            "ware_key": "TEST-1",
                            "payment": {"value": 100.0, "vat_rate": 22},
                            "cost": 100.0,
                            "weight": 1000,
                            "amount": 1,
                        }
                    ],
                }
            ],
        }

    first = await client.orders.create(payload())
    assert first.uuid
    second_uuid: str | None = None
    try:
        second = await client.orders.create(payload())
        second_uuid = second.uuid

        try:
            await client.orders.wait(second.uuid, timeout=90, interval=3)
        except TimeoutExceeded:
            pytest.skip("песочница не завершила обработку запросов (нагрузка общего аккаунта)")
        except ApiError as exc:
            # Ожидаемый исход: дубликат отклонён при обработке.
            assert exc.errors
        else:
            pytest.fail("дубликат номера заказа не был отклонён")
    finally:
        for uuid in (first.uuid, second_uuid):
            if uuid:
                # отклонённый заказ мог не сохраниться — удаление может ответить ошибкой
                with contextlib.suppress(ApiError):
                    await client.orders.delete(uuid)


# --- прочие разделы (чеки, паспорта, реестры, фото, преалерты, реверс) -------
# Учебный аккаунт общий и «пустой»: заказов, чеков и фото документов в нём
# может не быть. Поэтому тесты проверяют **контракт** (форму ответа, коды
# ошибок, разбор моделью), а не наличие данных.


async def test_passports_returns_list_with_errors_shape(client: CdekClient) -> None:
    """``GET /v2/passport`` отвечает «списком с ошибками», а не конвертом.

    Реальный ответ учебной среды на несуществующий заказ::

        {"errors": [{"code": "v2_entity_empty", ...}],
         "warnings": [{"code": "v2_order_not_found", ...}]}

    HTTP при этом 200 — то есть форму ответа проверяем по телу.
    """
    response = await client.misc.passports(cdek_number="1234567890", client="ALL")

    assert isinstance(response, ListResponse)
    assert response.has_errors or response.orders is not None
    assert response.error_codes == () or all(
        code.startswith("v2_") for code in response.error_codes
    )
    for order in response.orders or []:
        assert order.passport.client in {"SENDER", "RECEIVER", "ALL"}
        assert isinstance(order.ok, bool)


async def test_registries_parses_by_date(client: CdekClient) -> None:
    """``GET /v2/registries``: единственный параметр ``date`` обязателен.

    В учебной среде реестров наложенного платежа нет — API отвечает ``{}``,
    что модель разбирает в пустой список.
    """
    yesterday = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    registries = await client.misc.registries(yesterday)

    assert isinstance(registries, RegistriesResponse)
    assert registries.registries in (None, [])
    assert registries.total == 0.0


async def test_checks_requires_search_parameter(client: CdekClient) -> None:
    """Без параметров метод не отправляется: API ответил бы 400."""
    with pytest.raises(ValueError, match="order_uuid"):
        await client.misc.checks()


async def test_checks_unknown_order_is_api_error(client: CdekClient) -> None:
    """Чеки несуществующего заказа — это HTTP 400/404, а не пустой список."""
    with pytest.raises(ApiError) as excinfo:
        await client.misc.checks(cdek_number="1234567890")

    assert excinfo.value.status_code in {400, 404}
    assert excinfo.value.errors


async def test_photo_documents_rejects_empty_body(client: CdekClient) -> None:
    """``POST /v2/photoDocument`` с пустым телом: ``v2_field_is_empty: [orders]``."""
    with pytest.raises(ApiError) as excinfo:
        await client.misc.raw("POST", "/v2/photoDocument", json_body={})

    assert excinfo.value.has_code("v2_field_is_empty")


async def test_photo_documents_accepts_cdek_datetime_format(client: CdekClient) -> None:
    """Период принимается только в формате ``yyyy-MM-dd'T'HH:mm:ssZ``.

    ``Z``-суффикс и ISO-смещение ``+03:00`` API отклоняет с
    ``v2_invalid_value_type`` — это подтверждает, что сериализация
    :data:`cdekx.types.CdekDateTimeOut` нужна именно такой.
    """
    now = datetime.now(tz=timezone.utc)
    correct = PhotoRequest(
        period_begin=now - timedelta(days=1),
        period_end=now,
        orders=[PhotoOrder(cdek_number="1234567890")],
    )
    body = correct.to_api()
    assert body["period_begin"].endswith("+0000"), body

    # корректный формат проходит валидацию полей (данные в песочнице могут
    # отсутствовать, а метод без фото документов иногда отвечает 500)
    try:
        response = await client.misc.photo_ready_orders(correct)
    except ApiError as exc:
        assert exc.status_code >= 500, f"неожиданный отказ: {exc}"
    else:
        assert isinstance(response, PhotoResponse)
        for order in response.orders or []:
            assert order.status
            assert order.archive_uuid or not order.link

    # ISO-смещение с двоеточием API не принимает
    with pytest.raises(ApiError) as excinfo:
        await client.misc.raw(
            "POST",
            "/v2/photoDocument",
            json_body={"period_begin": (now - timedelta(days=1)).isoformat(), "orders": []},
        )
    assert excinfo.value.has_code("v2_invalid_value_type")


async def test_restrictions_item_id_is_snake_case_not_item_id(client: CdekClient) -> None:
    """Спецификация объявляет поле как ``itemId``, но API требует ``item_id``.

    На ``itemId`` метод отвечает, что ``item_id`` пуст, — то есть camelCase
    из схемы запроса не читается вовсе (проверено на учебной среде).
    """
    base = {
        "tariff_code": 136,
        "from_location": {"code": MOSCOW, "address": "ул. Тестовая, 1"},
        "to_location": {"code": DUBAI, "country_code": "AE"},
        "packages": [
            {
                "package_id": "pkg-1",
                "weight": 1500,
                "items": [
                    {"name": "Джинсы мужские Henry, размер M", "amount": 1, "itemId": "SKU-1"}
                ],
            }
        ],
    }

    with pytest.raises(ApiError) as excinfo:
        await client.misc.raw("POST", "/v2/international/package/restrictions", json_body=base)

    exc = excinfo.value
    assert exc.has_code("v2_field_is_empty")
    assert "item_id" in (exc.errors[0].message or "")


async def test_restrictions_requires_package_id_and_items(client: CdekClient) -> None:
    """В схеме все поля необязательны, фактически обязательны ``package_id`` и ``items``."""
    with pytest.raises(ApiError) as excinfo:
        await client.misc.international_restrictions(
            RestrictionRequest(
                tariff_code=136,
                from_location=Location(code=MOSCOW, address="ул. Тестовая, 1"),
                to_location=Location(code=DUBAI, country_code="AE"),
                packages=[RestrictionPackage(weight=1500)],
            )
        )

    exc = excinfo.value
    assert exc.has_code("v2_field_is_empty")
    messages = " ".join(e.message or "" for e in exc.errors)
    assert "package_id" in messages


async def test_restrictions_valid_request_passes_field_validation(client: CdekClient) -> None:
    """Корректное тело проходит валидацию полей: дальше — расчёт или 500.

    В учебной среде метод на полном теле отвечает ``v2_internal_error``
    (международные ограничения требуют боевого договора), поэтому 500 здесь —
    ожидаемый исход, а не ошибка модели.
    """
    try:
        response = await client.misc.international_restrictions(
            RestrictionRequest(
                tariff_code=136,
                from_location=Location(code=MOSCOW, address="ул. Тестовая, 1"),
                to_location=Location(code=DUBAI, country_code="AE"),
                packages=[
                    RestrictionPackage(
                        package_id="pkg-1",
                        weight=1500,
                        length=35,
                        width=25,
                        height=15,
                        items=[
                            RestrictionItem(
                                name="Джинсы мужские Henry, размер M",
                                amount=1,
                                item_id="SKU-1",
                                feacn_code="620342",
                            )
                        ],
                    )
                ],
            )
        )
    except ApiError as exc:
        assert exc.status_code >= 500, f"валидация полей не пройдена: {exc}"
    else:
        assert isinstance(response, RestrictionHintsResponse)
        for package in response.packages or []:
            assert package.status is None or package.status.code in {
                "FORBIDDEN",
                "LIMITED",
                "ALLOWED",
            }


async def test_reverse_availability_reports_reasons(client: CdekClient) -> None:
    """``POST /v2/reverse/availability``: пустое тело 200 либо 400 с причиной.

    В учебной среде реверс по тарифу «Постамат» недоступен, и API перечисляет
    причины отдельными кодами (``reverse_order_*``), которых нет в
    OpenAPI-спецификации. Метод обязан отдать их в ``ApiError.errors``.
    """
    points = await client.delivery_points.list(
        DeliveryPointFilter(city_code=MOSCOW, type="ALL", size=1)
    )
    if not points:
        pytest.skip("в учебной среде нет офисов Москвы")

    request = ReverseValidateRequest(
        tariff_code=136,
        delivery_point=points[0].code,
        from_location=ReverseLocation(code=MOSCOW, address="ул. Тестовая, 1"),
        sender=ReverseContragent(contragent_type="INDIVIDUAL", phones=["+79001234567"]),
        recipient=ReverseContragent(contragent_type="INDIVIDUAL", phones=["+79007654321"]),
    )

    try:
        result = await client.misc.reverse_availability(request)
    except ApiError as exc:
        assert exc.status_code == 400, f"неожиданный статус: {exc}"
        assert exc.errors, "причина недоступности реверса не возвращена"
    else:
        assert result is None


async def test_reverse_availability_requires_delivery_point(client: CdekClient) -> None:
    """Для тарифа «до постамата» ``delivery_point`` обязателен (режим «до склада»)."""
    with pytest.raises(ApiError) as excinfo:
        await client.misc.reverse_availability(
            {
                "tariff_code": 136,
                "from_location": {"code": MOSCOW, "address": "ул. Тестовая, 1"},
                "to_location": {"code": MOSCOW, "address": "ул. Проверочная, 2"},
                "sender": {"phones": [{"number": "+79001234567"}]},
                "recipient": {"phones": [{"number": "+79007654321"}]},
            }
        )

    assert excinfo.value.has_code("v2_field_is_empty")
    assert "delivery_point" in (excinfo.value.errors[0].message or "")


async def test_prealert_create_and_read(client: CdekClient) -> None:
    """Преалерт: 202 с ``uuid``, затем чтение по этому ``uuid``.

    Заказ ``1234567890`` в учебной среде не существует, поэтому обработка
    завершается состоянием ``INVALID`` (``v2_orders_number_is_empty``) — это
    штатный сценарий, он и проверяется. Отдельно проверяем, что живой ответ
    ``GET /v2/prealert/{uuid}`` **не содержит** ``uuid`` преалерта и
    ``order_uuid`` заказа, хотя схема объявляет их обязательными.

    Note:
        Метода удаления преалерта в API нет — созданные в учебной среде
        преалерты остаются там (они не влияют на лимиты аккаунта).
    """
    planned = (datetime.now(tz=timezone.utc) + timedelta(days=5)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    try:
        task = await client.misc.prealert_create(
            PrealertCreate(
                planned_date=planned,
                shipment_point="MSK",
                orders=[PrealertOrder(cdek_number="1234567890")],
            )
        )
    except ApiError as exc:
        # INVALID приходит как ApiError из raise_if_invalid — тоже штатный исход
        assert exc.status_code in {202, 400}, f"неожиданный отказ: {exc}"
        pytest.skip(f"песочница отклонила преалерт на входе: {exc}")

    uuid = task.uuid
    assert uuid, "ответ 202 не содержит uuid преалерта"

    envelope = await client.misc.prealert_get(uuid)
    prealert = envelope.entity
    assert prealert is not None, "GET /v2/prealert/{uuid} не вернул entity"

    # Живой API не возвращает uuid преалерта — модель обязана это пережить
    assert prealert.uuid is None
    assert prealert.shipment_point == "MSK"
    assert prealert.orders, "список заказов преалерта пуст"
    assert prealert.orders[0].order_uuid is None
    assert prealert.orders[0].cdek_number == "1234567890"  # int64 → str
    assert prealert.discrepancies == []
