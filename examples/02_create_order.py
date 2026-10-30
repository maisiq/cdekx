"""Пример 02: регистрация заказа и ожидание результата.

Показывает:
* сборку модели заказа;
* асинхронность API v2 (задача → ожидание → чтение);
* чтение статусов.

Запуск::

    python 02_create_order.py

!!! В учебной среде заказ создастся, но посылка не поедет.
"""

from __future__ import annotations

import asyncio
import uuid

from cdekx import ApiError, CdekClient
from cdekx.models import (
    Contact,
    Item,
    Location,
    Money,
    OrderCreate,
    Package,
)
from cdekx.types.enums import OrderType, ServiceCode, TariffCode


def build_order(number: str) -> OrderCreate:
    """Собрать тестовый заказ «дверь-дверь»."""
    return OrderCreate(
        type=OrderType.E_COMMERCE,
        number=number,
        tariff_code=TariffCode.EXPRESS_LIGHT_DOOR_DOOR,
        comment="Создан примером cdekx",
        from_location=Location(code=44, address="ул. Тестовая, 1, офис 10"),
        to_location=Location(code=270, address="ул. Проверочная, 2, кв. 5"),
        sender=Contact(
            company="ООО «Ромашка»",
            name="Иван Петров",
            phones=["+79001234567"],
            email="sender@example.com",
        ),
        recipient=Contact(
            name="Мария Смирнова",
            phones=["+79007654321"],
            email="recipient@example.com",
        ),
        packages=[
            Package(
                number="PKG-1",
                weight=1500,
                length=35,
                width=25,
                height=15,
                comment="Коробка с товаром",
                items=[
                    Item(
                        name="Тестовый товар",
                        ware_key="SKU-001",
                        payment=Money(value=1990.0, vat_rate=22),
                        cost=1990.0,
                        weight=1500,
                        amount=1,
                    )
                ],
            )
        ],
        services=[
            {"code": ServiceCode.INSURANCE, "parameter": "1990"},
        ],
        has_reverse_order=True,
    )


async def main() -> None:
    """Создать заказ, дождаться обработки и показать результат."""
    number = f"CDEKX-DEMO-{uuid.uuid4().hex[:8].upper()}"

    async with CdekClient.sandbox() as client:
        print(f"Создаём заказ {number}…")
        try:
            task = await client.orders.create(build_order(number))
        except ApiError as exc:
            print(f"СДЭК отклонил заказ: {exc}")
            for detail in exc.errors:
                print(f"  - {detail.code}: {detail.message}")
            return

        if not task.uuid:
            print("СДЭК не вернул UUID задачи")
            return

        print(f"UUID заказа: {task.uuid}")
        print(f"Состояние запроса: {task.state}")  # ACCEPTED — это ещё не «создан»
        print("Ждём завершения асинхронной обработки…")

        # СДЭК обрабатывает заказ 200–500 мс, под нагрузкой — до 30–60 с.
        # Документация рекомендует 2–3 секунды до первого опроса.
        try:
            envelope = await client.orders.wait(task.uuid, timeout=120, interval=3)
        except ApiError as exc:
            print(f"Заказ отклонён при обработке: {exc}")
            for detail in exc.errors:
                print(f"  - {detail.code}: {detail.message}")
            return

        order = envelope.entity
        print(f"Состояние запроса: {envelope.state}")
        if order:
            print(f"\nНомер СДЭК: {order.cdek_number}")
            print(f"Тариф:      {order.tariff_code}, режим {order.delivery_mode}")
            detail = order.delivery_detail
            print(f"Доставка:   {detail.delivery_sum if detail else '?'} ₽")
            print("История статусов:")
            for entry in order.statuses or []:
                print(f"  {entry.date_time} {entry.code} «{entry.name}» {entry.reason_code or ''}")

            # Реверсный заказ и печатные формы приходят в related_entities.
            for related in envelope.related_entities or []:
                print(f"  связана сущность: {related.type} {related.uuid} {related.url or ''}")

            # В учебной среде заказ можно сразу удалить.
            await client.orders.delete(order.uuid)
            print("\nЗаказ удалён.")


if __name__ == "__main__":
    asyncio.run(main())
