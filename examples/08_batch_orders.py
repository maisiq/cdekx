"""Пример 08: массовое создание заказов с ограничением нагрузки.

Показывает:
* конкурентную отправку через ``asyncio.Semaphore``;
* ограничение на уровне клиента (``max_concurrency``);
* сбор результатов и ошибок без падения всего батча;
* ожидание задач пачкой.

Запуск::

    python 08_batch_orders.py orders.json

Формат ``orders.json``::

    [
      {"number": "ORDER-1", "to_city_code": 270, "weight": 1000},
      ...
    ]
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from cdekx import ApiError, CdekClient, TransportError
from cdekx.models import Contact, Item, Location, Money, OrderCreate, Package
from cdekx.types.enums import OrderType, TariffCode

#: Сколько заказов отправляем одновременно.
#: СДЭК гарантирует ~200 RPS на договор, но упираться в потолок не стоит.
CONCURRENCY = 10

WAREHOUSE_CITY = 44


def build_order(row: dict[str, Any]) -> OrderCreate:
    """Собрать заказ из строки входного файла."""
    weight = int(row.get("weight", 1000))
    return OrderCreate(
        type=OrderType.E_COMMERCE,
        number=row["number"],
        tariff_code=row.get("tariff_code", TariffCode.EXPRESS_LIGHT_DOOR_DOOR),
        from_location=Location(code=WAREHOUSE_CITY, address=row.get("from_address", "склад")),
        to_location=Location(
            code=int(row["to_city_code"]),
            address=row.get("to_address", "адрес получателя"),
        ),
        sender=Contact(name=row.get("sender", "Отправитель"), phones=["+79001234567"]),
        recipient=Contact(
            name=row.get("recipient", "Получатель"),
            phones=[row.get("recipient_phone", "+79007654321")],
        ),
        packages=[
            Package(
                number=f"{row['number']}-PKG-1",
                weight=weight,
                items=[
                    Item(
                        name=row.get("item_name", "Товар"),
                        ware_key=row.get("sku", "SKU"),
                        payment=Money(value=float(row.get("price", 100.0)), vat_rate=22),
                        cost=float(row.get("price", 100.0)),
                        weight=weight,
                        amount=int(row.get("amount", 1)),
                    )
                ],
            )
        ],
    )


async def create_all(client: CdekClient, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Отправить все заказы, собрав успехи и ошибки."""
    semaphore = asyncio.Semaphore(CONCURRENCY)
    ok: dict[str, str] = {}
    failed: dict[str, str] = {}

    async def one(row: dict[str, Any]) -> None:
        number = str(row.get("number") or uuid.uuid4().hex[:8])
        async with semaphore:
            try:
                task = await client.orders.create(build_order(row))
            except ApiError as exc:
                failed[number] = f"{exc.status_code}: {'; '.join(exc.codes) or exc}"
                return
            except TransportError as exc:
                failed[number] = f"транспорт: {exc}"
                return

        if task.uuid:
            ok[number] = task.uuid
        else:
            failed[number] = "СДЭК не вернул UUID задачи"

    await asyncio.gather(*(one(row) for row in rows))
    return {"created": ok, "failed": failed}


async def wait_all(client: CdekClient, mapping: dict[str, str]) -> None:
    """Дождаться обработки всех созданных заказов."""

    async def one(number: str, order_uuid: str) -> None:
        try:
            envelope = await client.orders.wait(order_uuid, timeout=180, interval=3)
        except ApiError as exc:
            print(f"  {number}: заказ отклонён — {exc.codes}")
            return
        order = envelope.entity
        print(f"  {number}: {envelope.state}, номер СДЭК {order.cdek_number if order else '?'}")

    await asyncio.gather(*(one(number, u) for number, u in mapping.items()))


def load_rows(argv: list[str]) -> list[dict[str, Any]]:
    """Загрузить входной файл или вернуть демо-набор."""
    if argv:
        return json.loads(Path(argv[0]).read_text(encoding="utf-8"))

    return [
        {"number": f"CDEKX-BATCH-{i}", "to_city_code": 270, "weight": 1000 + i * 100}
        for i in range(1, 6)
    ]


async def main(argv: list[str]) -> None:
    """Точка входа примера."""
    rows = load_rows(argv)
    print(f"Отправляем {len(rows)} заказов (параллелизм: {CONCURRENCY})…")

    # max_concurrency дополнительно ограничивает пул соединений httpx
    async with CdekClient.sandbox(max_concurrency=CONCURRENCY * 2) as client:
        result = await create_all(client, rows)

        print(f"\nСоздано: {len(result['created'])}, с ошибками: {len(result['failed'])}")
        for number, reason in result["failed"].items():
            print(f"  ✗ {number}: {reason}")

        if result["created"]:
            print("\nЖдём обработки задач…")
            await wait_all(client, result["created"])

            # Чистим за собой учебную среду.
            for number, order_uuid in result["created"].items():
                try:
                    await client.orders.delete(order_uuid)
                    print(f"  удалён {number}")
                except ApiError as exc:
                    print(f"  не удалось удалить {number}: {exc}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
