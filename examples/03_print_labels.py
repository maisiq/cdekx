"""Пример 03: печать штрихкодов (этикеток) до готового PDF.

Показывает:
* создание задачи печати (параметры — телом JSON, не query);
* ожидание готовности с backoff'ом;
* скачивание файла с ``GET /v2/print/barcodes/{uuid}.pdf``;
* сквозной хелпер ``download_barcodes``.

Запуск::

    python 03_print_labels.py <uuid_заказа> [<uuid_заказа> ...]
    python 03_print_labels.py            # без аргументов — демонстрация вызова
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from cdekx import CdekClient, TimeoutExceeded


async def print_step_by_step(client: CdekClient, order_uuids: list[str]) -> Path | None:
    """Пошаговый вариант: задача → ожидание → скачивание."""
    task = await client.printing.barcodes(order_uuids, format="A4", copy_count=1, lang="RUS")
    if not task.uuid:
        print("СДЭК не вернул UUID задачи печати")
        return None

    print(f"Задача печати: {task.uuid}, состояние запроса: {task.state}")

    try:
        ready = await client.printing.wait_barcode(task.uuid, timeout=120, interval=2)
    except TimeoutExceeded as exc:
        print(f"Файл не сформирован: {exc}")
        print("Для потоковой печати подпишитесь на вебхук PRINT_FORM вместо поллинга")
        return None

    print(f"Файл готов: {ready.url}")
    data = await client.printing.barcode_pdf(ready.uuid)
    path = Path(f"labels-{task.uuid[:8]}.pdf")
    await asyncio.to_thread(path.write_bytes, data)  # не блокируем event loop
    print(f"Сохранено: {path.resolve()} ({len(data)} байт)")
    return path


async def print_waybill(client: CdekClient, order_uuids: list[str]) -> None:
    """Квитанция к заказу — отдельный метод и отдельный путь скачивания."""
    task = await client.printing.waybill(order_uuids, copy_count=2)
    ready = await client.printing.wait_waybill(task.uuid or "", timeout=120)
    data = await client.printing.waybill_pdf(ready.uuid)
    path = Path("waybill.pdf")
    await asyncio.to_thread(path.write_bytes, data)
    print(f"Квитанция: {path.resolve()} ({len(data)} байт)")


async def print_one_call(client: CdekClient, order_uuids: list[str]) -> None:
    """То же самое одним вызовом."""
    data = await client.printing.download_barcodes(order_uuids, format="A4", timeout=120)
    path = Path("labels.pdf")
    await asyncio.to_thread(path.write_bytes, data)
    print(f"Один вызов → {path.resolve()} ({len(data)} байт)")


async def main(argv: list[str]) -> None:
    """Точка входа примера."""
    order_uuids = argv or ["8dea00e3-9aab-4d8e-887c-ef2aaa546456"]

    async with CdekClient.sandbox() as client:
        result = await print_step_by_step(client, order_uuids)
        if result:
            await print_waybill(client, order_uuids)
            await print_one_call(client, order_uuids)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
