#!/usr/bin/env python3
"""Замер двух стратегий разбора ответов СДЭК.

Сравнивает:

1. ``Model.model_validate(json.loads(body))`` — классический путь: сначала
   ``json.loads`` в словарь, затем валидация словаря;
2. ``Model.model_validate_json(body)`` — байты уходят напрямую в Rust-парсер
   pydantic, промежуточного словаря нет.

Запуск::

    python benchmarks/parse_benchmark.py
    python benchmarks/parse_benchmark.py --repeat 9 --size 500

Результаты на эталонной машине (Python 3.11, pydantic 2.14), фикстуры из
``tests/fixtures``:

===============================  ============  ============  ========
_payload                          json.loads   validate_json  выигрыш
===============================  ============  ============  ========
конверт заказа, 1.8 КБ              65 мкс       41 мкс        1.6×
список 300 ПВЗ, 374 КБ            11.9 мс      6.9 мс         1.7×
===============================  ============  ============  ========

Важно: выигрыш даёт именно **единый** вызов ``validate_json`` для всего
массива. Гибрид «Rust-парсер для JSON + поэлементный ``model_validate``»
оказывается медленнее классического пути из-за стоимости Python-цикла.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from cdekx.endpoints.base import parse_list_json, parse_model_json
from cdekx.models import DeliveryPoint, Order
from cdekx.models.base import ResponseEnvelope

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def bench(fn: Callable[[], Any], *, iterations: int, repeat: int = 7) -> float:
    """Медианное время одного вызова в микросекундах."""
    fn()  # прогрев
    samples: list[float] = []
    for _ in range(repeat):
        started = time.perf_counter()
        for _ in range(iterations):
            fn()
        samples.append((time.perf_counter() - started) / iterations * 1e6)
    return statistics.median(samples)


def report(title: str, size: int, slow: float, fast: float) -> None:
    """Напечатать строку сравнения."""
    print(f"\n{title} ({size:,} bytes)".replace(",", " "))
    print(f"  json.loads + model_validate : {slow:10.1f} мкс")
    print(f"  model_validate_json         : {fast:10.1f} мкс")
    print(f"  выигрыш                     : {slow / fast:10.2f}× (−{slow - fast:.1f} мкс)")


def run_envelope_benchmark(iterations: int, repeat: int) -> None:
    """Конверт ответа по заказу (``ResponseEnvelope[Order]``)."""
    content = (FIXTURES / "orders" / "get.json").read_bytes()
    model = ResponseEnvelope[Order]

    slow = bench(
        lambda: model.model_validate(json.loads(content)), iterations=iterations, repeat=repeat
    )
    fast = bench(lambda: parse_model_json(model, content), iterations=iterations, repeat=repeat)
    report("конверт заказа", len(content), slow, fast)


def run_list_benchmark(objects: int, iterations: int, repeat: int) -> None:
    """Большой список офисов — самый тяжёлый ответ в API."""
    base = json.loads((FIXTURES / "delivery" / "list.json").read_text(encoding="utf-8"))
    payload = base * max(objects // len(base), 1)
    content = json.dumps(payload, ensure_ascii=False).encode()
    adapter: TypeAdapter[Any] = TypeAdapter(list[DeliveryPoint])

    def slow_path() -> list[DeliveryPoint]:
        return [DeliveryPoint.model_validate(item) for item in json.loads(content)]

    slow = bench(slow_path, iterations=iterations, repeat=repeat)
    fast = bench(
        lambda: parse_list_json(DeliveryPoint, content), iterations=iterations, repeat=repeat
    )
    theoretical = bench(
        lambda: adapter.validate_json(content), iterations=iterations, repeat=repeat
    )

    report(f"список ПВЗ, {len(payload)} объектов", len(content), slow, fast)
    print(f"  теоретический предел (validate_json целиком): {theoretical:.1f} мкс")

    # антипример: поэлементная валидация после Rust-парсинга
    raw_adapter: TypeAdapter[Any] = TypeAdapter(list[Any])
    hybrid = bench(
        lambda: [DeliveryPoint.model_validate(i) for i in raw_adapter.validate_json(content)],
        iterations=iterations,
        repeat=repeat,
    )
    print(f"  антипример (Rust-парсинг + поэлементно)     : {hybrid:.1f} мкс")


def main(argv: list[str] | None = None) -> int:
    """Точка входа бенчмарка."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200, help="итераций в замере")
    parser.add_argument("--repeat", type=int, default=7, help="сколько замеров для медианы")
    parser.add_argument("--size", type=int, default=300, help="число объектов в списке ПВЗ")
    args = parser.parse_args(argv)

    import pydantic

    print(f"pydantic {pydantic.VERSION}")
    run_envelope_benchmark(args.iterations * 10, args.repeat)
    run_list_benchmark(args.size, args.iterations, args.repeat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
