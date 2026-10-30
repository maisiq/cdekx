"""Пример 07: обработка ошибок и повтор при ограничении частоты.

Показывает:
* иерархию исключений ``cdekx``;
* разбор ``errors[]`` с кодами СДЭК;
* ``request_id`` для обращения в поддержку;
* ручной повтор при 429 (автоматический уже встроен в ``RetryPolicy``).

Запуск::

    python 07_error_handling.py
"""

from __future__ import annotations

import asyncio

from cdekx import (
    ApiError,
    AuthError,
    CdekClient,
    ConfigError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutExceeded,
    TransportError,
    ValidationError,
)
from cdekx.endpoints import ResponseParseError


async def demo_not_found(client: CdekClient) -> None:
    """404: заказа не существует."""
    try:
        await client.orders.get("00000000-0000-0000-0000-000000000000")
    except NotFoundError as exc:
        print(f"[404] {exc}  (request_id={exc.request_id})")


async def demo_validation(client: CdekClient) -> None:
    """400: заказ не прошёл валидацию на стороне СДЭК."""
    try:
        await client.orders.create(
            {
                "type": 1,
                "number": "",  # пустой номер — СДЭК отклонит
                "tariff_code": 136,
                "from_location": {"code": 44, "address": "ул. Тестовая, 1"},
                "to_location": {"code": 270, "address": "ул. Проверочная, 2"},
                "recipient": {"name": "Тест", "phones": [{"number": "+79007654321"}]},
                "packages": [{"number": "1", "weight": 1000}],
            }
        )
    except ValidationError as exc:
        print(f"[400] ошибок: {len(exc.errors)}")
        for detail in exc.errors:
            print(f"      {detail.code}: {detail.message}")
        if exc.has_code("v2_order_invalid"):
            print("      → заказ не прошёл бизнес-валидацию: исправьте данные и повторите")
        if exc.has_code("v2_number_items_is_more_126"):
            print("      → в заказе больше 126 товарных позиций: разбейте на несколько")


async def demo_rate_limit(client: CdekClient) -> None:
    """429: повтор с учётом Retry-After.

    В реальности ``cdekx`` уже повторяет такие запросы сам
    (``RetryPolicy``), поэтому ручной цикл нужен редко — например,
    когда вы уперлись в лимит намеренно и хотите выровнять нагрузку.
    """
    attempts = 0
    while attempts < 3:
        try:
            await client.locations.cities({"name": "Москва", "size": 1})
            print("[200] запрос прошёл")
            return
        except RateLimitError as exc:
            attempts += 1
            delay = exc.retry_after or 2**attempts
            print(f"[429] превышен лимит, ждём {delay} с (попытка {attempts})")
            await asyncio.sleep(delay)
    print("[429] лимит так и не отпустил — снизьте частоту вызовов")


async def demo_common_handler(client: CdekClient) -> None:
    """Единый обработчик для фонового задания."""
    try:
        await client.orders.get("не-существует")
    except AuthError:
        print("Проблема с учётными данными: проверьте ключи в ЛК СДЭК")
    except (TimeoutExceeded, TransportError) as exc:
        print(f"Сеть/таймаут — задача будет повторена позже: {exc}")
    except ServerError as exc:
        print(f"Сбой на стороне СДЭК ({exc.status_code}) — повторите позже")
    except NotFoundError:
        print("Заказ не найден")
    except ResponseParseError as exc:
        # СДЭК изменил контракт: логируем сырой ответ и заводим issue
        print(f"Неожиданный формат ответа: {exc}\nraw={str(exc.raw)[:500]}")
    except ApiError as exc:
        print(f"Прочая ошибка API: {exc} request_id={exc.request_id}")


async def main() -> None:
    """Точка входа примера."""
    try:
        client = CdekClient.sandbox()
    except ConfigError as exc:
        print(f"Не удалось создать клиент: {exc}")
        return

    async with client:
        await demo_not_found(client)
        await demo_validation(client)
        await demo_common_handler(client)
        await demo_rate_limit(client)


if __name__ == "__main__":
    asyncio.run(main())
