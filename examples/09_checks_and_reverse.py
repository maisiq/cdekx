"""Пример 09: «прочие» разделы API — реверс, ограничения, чеки, фото, преалерты.

Показывает:
* проверку доступности реверса (пустой ответ 200 = доступно, 400 = нет);
* ограничения по международным направлениям (ТН ВЭД, весогабариты);
* форму ответа «список + ошибки»: HTTP 200 не гарантирует успех;
* работу с фото документов: список готовых заказов и скачивание ZIP;
* регистрацию преалерта (HTTP 202) и расхождения после его закрытия.

В учебной среде часть методов может отвечать ошибкой — пример печатает её
и продолжает работу: это нормальное поведение для разделов, которые требуют
боевого договора (чеки, реестры НП, преалерты).

Запуск::

    python 09_checks_and_reverse.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from cdekx import ApiError, CdekClient, ConfigError
from cdekx.models import (
    PhotoRequest,
    PrealertCreate,
    RestrictionItem,
    RestrictionPackage,
    RestrictionRequest,
    ReverseContragent,
    ReverseLocation,
    ReverseValidateRequest,
)
from cdekx.models.common import Location

MOSCOW = 44
#: Дубай (ОАЭ) — направление с реальными ограничениями по ТН ВЭД.
DUBAI = 176
MSK = timezone(timedelta(hours=3))


async def check_reverse(client: CdekClient) -> None:
    """Реверс доступен — API ответит пустым телом с кодом 200."""
    request = ReverseValidateRequest(
        tariff_code=136,
        delivery_point="MSK",
        from_location=ReverseLocation(code=MOSCOW, address="ул. Тестовая, 1"),
        sender=ReverseContragent(contragent_type="INDIVIDUAL", phones=["89001234567"]),
        recipient=ReverseContragent(contragent_type="INDIVIDUAL", phones=["+79007654321"]),
    )
    try:
        await client.misc.reverse_availability(request)
    except ApiError as exc:
        # Недоступность реверса приходит как HTTP 400 с описанием причины
        print(f"[реверс] недоступен: {exc}")
        for detail in exc.errors:
            print(f"          {detail.code}: {detail.message}")
    else:
        print("[реверс] доступен (пустой ответ 200)")

    # Телефоны нормализуются автоматически: «89001234567» → «+79001234567»
    print(f"          в запрос уйдёт: {request.to_api()['sender']}")


async def check_restrictions(client: CdekClient) -> None:
    """Ограничения по международному направлению (Москва → Дубай)."""
    request = RestrictionRequest(
        tariff_code=136,
        from_location=Location(code=MOSCOW, address="ул. Тестовая, 1"),
        to_location=Location(code=DUBAI, country_code="AE"),
        packages=[
            RestrictionPackage(
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
                    ),
                    RestrictionItem(
                        name="Парфюмерная вода 50 мл",
                        amount=1,
                        item_id="SKU-2",
                        feacn_code="330300",
                    ),
                ],
            )
        ],
    )
    try:
        hints = await client.misc.international_restrictions(request)
    except ApiError as exc:
        print(f"[ограничения] API ответил ошибкой: {exc}")
        return

    if hints.has_errors:
        print(f"[ограничения] ошибки в теле ответа: {hints.error_codes}")

    for package in hints.packages or []:
        status = package.status
        print(f"[ограничения] место {package.package_id}: {status.code if status else '—'}")
        if package.description:
            print(f"              {package.description}")
        for item in package.items or []:
            item_status = item.status
            reason = item_status.reason if item_status else None
            print(
                f"              товар {item.item_id} (ТН ВЭД {item.feacn_code}): "
                f"{item_status.code if item_status else '—'}"
                + (f", причина {reason.code}" if reason else "")
            )
            for document in item.documents or []:
                print(f"                  нужен документ: {document}")

    print(f"[ограничения] отправка разрешена целиком: {hints.is_allowed}")
    for package in hints.forbidden:
        print(f"              запрещены товары: {[i.item_id for i in package.forbidden_items]}")


async def fetch_checks(client: CdekClient, cdek_number: str) -> None:
    """Фискальные чеки по заказу.

    Метод требует хотя бы один параметр поиска; если не передать ни одного,
    ``cdekx`` бросит ``ValueError`` и не станет отправлять бессмысленный запрос.
    """
    try:
        response = await client.misc.checks(cdek_number=cdek_number)
    except ValueError as exc:
        print(f"[чеки] некорректный вызов: {exc}")
        return
    except ApiError as exc:
        print(f"[чеки] API ответил ошибкой: {exc}")
        return

    if response.has_errors:
        # Важно: HTTP 200 + ошибки в теле — обычный сценарий для этой формы ответа
        print(f"[чеки] ошибки в теле: {response.error_codes}")

    for check in response.checks:
        print(
            f"[чеки] {check.type} от {check.date}: ФН {check.fiscal_storage_number}, "
            f"ФД {check.document_number}, ФП {check.fiscal_sign}, смена {check.shift_no}"
        )
        for payment in check.payment_info:
            print(f"       {payment.type}: {payment.sum}")
        print(f"       итого: {check.total}")


async def fetch_photo_documents(client: CdekClient) -> None:
    """Заказы с готовыми фото документов и скачивание архива."""
    now = datetime.now(tz=MSK)
    request = PhotoRequest(
        # datetime сериализуется в формат СДЭК: 2026-04-01T00:00:00+0300
        period_begin=now - timedelta(days=30),
        period_end=now,
    )
    print(f"[фото] период: {request.to_api()['period_begin']} … {request.to_api()['period_end']}")

    try:
        response = await client.misc.photo_ready_orders(request)
    except ApiError as exc:
        print(f"[фото] API ответил ошибкой: {exc}")
        return

    orders = response.orders or []
    print(f"[фото] заказов в ответе: {len(orders)}, готово к скачиванию: {len(response.ready)}")

    for order in response.ready[:1]:
        archive_uuid = order.archive_uuid
        print(f"       заказ {order.cdek_number}: статус {order.status}, архив {archive_uuid}")
        if archive_uuid:
            try:
                data = await client.misc.photo_archive(archive_uuid)
            except ApiError as exc:
                print(f"       архив не отдан: {exc}")
            else:
                print(f"       скачано байт: {len(data)} (ZIP начинается с {data[:2]!r})")


async def register_prealert(client: CdekClient, cdek_number: str) -> None:
    """Преалерт: асинхронная регистрация (202) и проверка расхождений."""
    planned = (datetime.now(tz=MSK) + timedelta(days=3)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    try:
        task = await client.misc.prealert_create(
            PrealertCreate(
                planned_date=planned,
                shipment_point="MSK",
                orders=[{"cdek_number": cdek_number}],
            )
        )
    except ApiError as exc:
        print(f"[преалерт] регистрация отклонена: {exc}")
        return

    uuid = task.uuid
    print(f"[преалерт] принят: uuid={uuid}, state={task.state} (202 — ещё не создан)")
    if not uuid:
        return

    envelope = await client.misc.prealert_get(uuid)
    prealert = envelope.entity
    if prealert is None:
        print("[преалерт] API не вернул сущность")
        return

    print(f"[преалерт] номер {prealert.prealert_number}, ПВЗ {prealert.shipment_point}")
    if prealert.is_closed:
        print(f"           закрыт {prealert.closed_date}")
        print(f"           фактический ПВЗ: {prealert.fact_shipment_point}")
        for package in prealert.discrepancies:
            print(f"           расхождение: упаковка {package.number} → {package.status}")
    else:
        print("           ещё не закрыт — расхождений нет")


async def main() -> None:
    """Точка входа примера."""
    try:
        client = CdekClient.sandbox()
    except ConfigError as exc:
        print(f"Не удалось создать клиент: {exc}")
        return

    async with client:
        await check_reverse(client)
        await check_restrictions(client)
        # Номер заказа подставьте свой: в учебной среде чеков и фото может не быть
        await fetch_checks(client, cdek_number="1234567890")
        await fetch_photo_documents(client)
        await register_prealert(client, cdek_number="1234567890")


if __name__ == "__main__":
    asyncio.run(main())
