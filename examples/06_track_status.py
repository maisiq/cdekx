"""Пример 06: отслеживание статуса заказа.

Показывает:
* получение заказа по номеру СДЭК и по номеру в вашей ИС;
* историю статусов и причины задержки;
* периодический опрос (поллинг) с backoff'ом.

Запуск::

    python 06_track_status.py 1234567890
    python 06_track_status.py --im-number ORDER-0001
"""

from __future__ import annotations

import asyncio
import sys

from cdekx import CdekClient, NotFoundError
from cdekx.models import Order

#: Статусы, после которых опрос можно прекращать.
TERMINAL_STATUSES = {"DELIVERED", "RETURNED", "CANCELLED", "LOST", "RETURN_DELIVERED"}


def print_order(order: Order) -> None:
    """Напечатать сводку по заказу."""
    print(f"Заказ СДЭК: {order.cdek_number}   (ваш номер: {order.number})")
    print(f"UUID:       {order.uuid}")
    print(f"Тариф:      {order.tariff_code}, режим доставки {order.delivery_mode}")
    if order.from_location and order.to_location:
        print(f"Маршрут:    {order.from_location.city} → {order.to_location.city}")
    if order.delivery_detail:
        print(
            f"Доставка:   {order.delivery_detail.delivery_sum} ₽, "
            f"итого {order.delivery_detail.total_sum} ₽"
        )

    print("Статусы:")
    for status in order.statuses or []:
        marker = " (удалён)" if status.deleted else ""
        print(
            f"  {status.date_time}  {status.code!s:<22} "
            f"{status.name!s:<20} {status.reason_code or '':<28} "
            f"{status.city or ''}{marker}"
        )

    current = order.current_status
    if current:
        print(f"\nТекущий статус: {current.code}")
        if current.code in TERMINAL_STATUSES:
            print("Заказ в конечном статусе — опрос можно остановить")

    for reason in order.delay_reasons or []:
        print(f"Причина задержки ({reason.create_date}): {reason.description}")

    for problem in order.delivery_problem or []:
        print(f"Проблема доставки: {problem.code} от {problem.create_date}")


async def track(
    client: CdekClient,
    *,
    cdek_number: str | None = None,
    im_number: str | None = None,
    poll_seconds: float = 0,
) -> None:
    """Найти заказ и (опционально) опрашивать его статус."""
    while True:
        try:
            if cdek_number:
                order = await client.orders.get_by_number(cdek_number)
            elif im_number:
                order = await client.orders.get_by_client_number(im_number)
            else:
                raise ValueError("нужен cdek_number или im_number")
        except NotFoundError as exc:
            print(f"Заказ не найден: {exc}")
            return

        print("-" * 78)
        print_order(order)

        if not poll_seconds:
            return
        if order.current_status and order.current_status.code in TERMINAL_STATUSES:
            print("Достигнут конечный статус, опрос завершён.")
            return

        print(f"\nСледующая проверка через {poll_seconds} с… (Ctrl-C для выхода)")
        await asyncio.sleep(poll_seconds)


def parse_args(argv: list[str]) -> dict[str, object]:
    """Разобрать аргументы командной строки."""
    options: dict[str, object] = {"poll_seconds": 0.0}
    if not argv:
        return options

    if argv[0] == "--im-number" and len(argv) > 1:
        options["im_number"] = argv[1]
    else:
        options["cdek_number"] = argv[0]

    if "--poll" in argv:
        index = argv.index("--poll")
        options["poll_seconds"] = float(argv[index + 1]) if len(argv) > index + 1 else 60.0

    return options


async def main(argv: list[str]) -> None:
    """Точка входа примера."""
    options = parse_args(argv)
    if not options.get("cdek_number") and not options.get("im_number"):
        print(__doc__ or "")
        return

    async with CdekClient.from_env() as client:
        await track(client, **options)  # type: ignore[arg-type]


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
