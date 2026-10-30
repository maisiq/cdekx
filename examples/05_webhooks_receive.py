"""Пример 05: приём вебхуков СДЭК.

Показывает:
* управление подписками (создание/список/удаление);
* ASGI-приложение для приёма событий;
* разбор типизированных ``attributes``.

Запуск сервера::

    pip install "cdekx[webhooks]" uvicorn
    uvicorn 05_webhooks_receive:app --host 0.0.0.0 --port 8000

Затем подпишите СДЭК на ``https://<ваш-домен>/webhooks/cdek/<SECRET>``.

Локально, без публичного адреса, удобно проверять через ``ngrok``/``cloudflared``
или вызывать обработчик напрямую (см. ``__main__``).
"""

from __future__ import annotations

import asyncio
import logging
import os

from cdekx import CdekClient
from cdekx.types.enums import WebhookType
from cdekx.webhooks import WebhookEvent, parse_event

try:
    from cdekx.webhooks.asgi import WebhookApp
except ImportError:  # pragma: no cover
    WebhookApp = None  # type: ignore[assignment, misc]

logger = logging.getLogger("cdekx.example.webhooks")

#: Секретная часть пути — защита от посторонних вызовов.
PATH_SECRET = os.getenv("CDEKX_WEBHOOK_SECRET", "change-me-to-a-long-random-string")


async def on_event(event: WebhookEvent) -> None:
    """Обработчик события вебхука.

    Держите его быстрым: у СДЭК таймаут 15 секунд, после серии ошибок
    подписка отключается. Тяжёлую обработку выносите в очередь/фон.
    """
    logger.info("событие %s по сущности %s", event.type, event.uuid)

    match event.type:
        case "ORDER_STATUS":
            attrs = event.attributes
            logger.info(
                "заказ %s (ИМ: %s) → статус %s / %s в %s",
                attrs.cdek_number,
                attrs.number,
                attrs.code,
                attrs.status_reason_code,
                attrs.city_name,
            )
            if attrs.code == "DELIVERED":
                ...  # например, закрыть заказ в своей системе
        case "PRINT_FORM":
            logger.info("печатная форма готова: %s", event.attributes.url)
        case "COURIER_INFO":
            logger.info(
                "курьер: %s, %s (%s)",
                event.attributes.courier_fio,
                event.attributes.courier_phone,
                event.attributes.task_type,
            )
        case "DELIV_PROBLEM":
            logger.warning(
                "проблема доставки по заказу %s: %s",
                event.attributes.cdek_number,
                event.attributes.problem_description,
            )
        case _:
            logger.info("необрабатываемый тип события, attributes=%s", event.attributes)


#: ASGI-приложение: всегда отвечает 200, чтобы СДЭК не удалил подписку.
app = (
    WebhookApp(
        on_event=on_event,
        path_secret=PATH_SECRET,
        accept_types=[
            WebhookType.ORDER_STATUS.value,
            WebhookType.PRINT_FORM.value,
            WebhookType.COURIER_INFO.value,
            WebhookType.DELIV_PROBLEM.value,
        ],
    ).asgi
    if WebhookApp is not None
    else None
)


async def manage_subscriptions() -> None:
    """Показать управление подписками через API."""
    async with CdekClient.sandbox() as client:
        current = await client.webhooks.list()
        print("Текущие подписки:")
        for hook in current:
            print(f"  {hook.uuid} {hook.type} → {hook.url} (активна: {hook.is_active})")

        if not await client.webhooks.has_capacity():
            print("Достигнут лимит СДЭК (2 подписки) — освободите слот.")
            return

        public_url = os.getenv("WEBHOOK_PUBLIC_URL")
        if not public_url:
            print("Задайте WEBHOOK_PUBLIC_URL, чтобы создать подписку.")
            return

        created = await client.webhooks.create(
            f"{public_url.rstrip('/')}/webhooks/cdek/{PATH_SECRET}",
            WebhookType.ORDER_STATUS,
        )
        print(f"Создана подписка: {created.uuid}")


async def demo_local_parse() -> None:
    """Разбор события без HTTP-сервера — удобно для отладки логики."""
    payload = {
        "type": "ORDER_STATUS",
        "date_time": "2026-05-06T18:30:00+0300",
        "uuid": "8dea00e3-9aab-4d8e-887c-ef2aaa546456",
        "attributes": {
            "code": "DELIVERED",
            "status_reason_code": "RECEIVED_BY_RECIPIENT",
            "cdek_number": "1234567890",
            "number": "ORDER-0001",
            "city_code": 270,
            "city_name": "Екатеринбург",
            "is_return": False,
            "is_reverse": False,
        },
    }
    await on_event(parse_event(payload))


async def main() -> None:
    """Точка входа примера."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    await demo_local_parse()
    await manage_subscriptions()


if __name__ == "__main__":
    asyncio.run(main())
