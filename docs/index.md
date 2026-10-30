# cdekx

Асинхронный клиент [API СДЭК v2](https://apidoc.cdek.ru/) на `httpx` + `pydantic v2`.
Лицензия — Apache-2.0.

Независимая реализация публичного API СДЭК: модели и пути методов построены по
OpenAPI-спецификации apidoc.cdek.ru, код других клиентов не использовался.
Модели и пути методов сверяются со спецификацией автоматически
(``scripts/generate_from_openapi.py --drift``).

```bash
pip install cdekx
```

```python
import asyncio

from cdekx import CdekClient
from cdekx.models import CalculatorLocation, CalculatorPackage, TariffRequest


async def main() -> None:
    async with CdekClient.sandbox() as client:
        tariff = await client.calculator.tariff(
            TariffRequest(
                tariff_code=136,
                from_location=CalculatorLocation(code=44),
                to_location=CalculatorLocation(code=270),
                packages=[CalculatorPackage(weight=1000)],
            )
        )
        print(tariff.delivery_sum, tariff.period_min, tariff.period_max)


asyncio.run(main())
```

## Разделы

| Раздел | О чём |
| --- | --- |
| [Быстрый старт](quickstart.md) | установка, клиент, первые запросы |
| [Архитектура](ARCHITECTURE.md) | слои, решения, как расширять |
| [Покрытие API](API_COVERAGE.md) | какие методы СДЭК уже реализованы |
| [Рецепты](recipes.md) | типовые сценарии целиком |
| Справочник API | автодокументация классов и функций |
