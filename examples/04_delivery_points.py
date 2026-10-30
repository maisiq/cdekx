"""Пример 04: пункты выдачи заказов (ПВЗ, постаматы, склады).

Показывает:
* выборку офисов по городу;
* поиск офисов внутри прямоугольника координат (штатный способ «рядом»);
* обход больших списков через пагинатор;
* фильтрацию по возможностям (примерка, наложенный платёж, СБП).

Запуск::

    python 04_delivery_points.py
"""

from __future__ import annotations

import asyncio

from cdekx import CdekClient
from cdekx.models import DeliveryPointFilter, DeliveryPointPolygonFilter

MOSCOW = 44


async def city_points(client: CdekClient) -> None:
    """Все офисы города."""
    points = await client.delivery_points.list(DeliveryPointFilter(city_code=MOSCOW, type="ALL"))
    print(f"[город] найдено офисов: {len(points)}")

    for point in points[:5]:
        print(f"  {point.code:<10} {point.type:<8} {point.location.address}")
        print(f"      статус: {point.status}, время работы: {point.work_time}")
        print(
            f"      безнал={point.have_cashless} нал={point.have_cash} "
            f"сбп={point.have_fast_payment_system} "
            f"примерка={point.is_dressing_room} НП={point.allowed_cod}"
        )


async def nearby(client: CdekClient) -> None:
    """ПВЗ внутри прямоугольника вокруг Красной площади (~±0.03°)."""
    points = await client.delivery_points.by_polygon(
        latitude_right_top=55.7839,
        longitude_right_top=37.6508,
        latitude_left_bottom=55.7239,
        longitude_left_bottom=37.5908,
        # byPolygons поддерживает только эти фильтры: type, city_uuid,
        # have_cashless, have_cash, allowed_cod, is_dressing_room,
        # weight_max, weight_min, lang
        filter=DeliveryPointPolygonFilter(type="PVZ", allowed_cod=True),
    )
    print(f"\n[рядом] найдено ПВЗ в прямоугольнике: {len(points)}")
    for point in points[:5]:
        distance = f", {point.distance:.0f} м" if point.distance else ""
        name = f" — {point.name}" if point.name else ""
        print(f"  {point.code:<10} {point.location.address}{name}{distance}")


async def with_pagination(client: CdekClient) -> None:
    """Обход списка страницами (удобно для выгрузки в свою БД)."""
    total = 0
    async for _point in client.delivery_points.paginate(
        DeliveryPointFilter(city_code=MOSCOW, allowed_cod=True), page_size=200
    ):
        total += 1
    print(f"\n[пагинация] офисов с наложенным платежом: {total}")


async def by_code(client: CdekClient, code: str) -> None:
    """Информация об одном офисе."""
    try:
        point = await client.delivery_points.get(code)
    except Exception as exc:  # пример: ловим всё
        print(f"\n[офис {code}] не найден: {exc}")
        return

    print(f"\n[офис {code}] {point.location.address_full}")
    print(f"  тип={point.type} статус={point.status} город={point.location.city}")
    print(f"  координаты: {point.location.latitude}, {point.location.longitude}")
    schedule = ", ".join(f"{d.day}: {d.time or 'выходной'}" for d in point.work_time_list)
    print(f"  график: {schedule}")


async def main() -> None:
    """Точка входа примера."""
    async with CdekClient.sandbox() as client:
        await city_points(client)
        await nearby(client)
        await with_pagination(client)
        await by_code(client, "MSK1")


if __name__ == "__main__":
    asyncio.run(main())
