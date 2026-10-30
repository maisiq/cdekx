# cdekx

> Современный асинхронный клиент [API СДЭК v2](https://apidoc.cdek.ru/) — независимая реализация по OpenAPI-спецификации СДЭК: типизация, ретраи, пагинация, вебхуки.

**Русский** | [English](https://github.com/maisiq/cdekx/blob/master/README.en.md)

[![CI](https://github.com/maisiq/cdekx/actions/workflows/ci.yml/badge.svg)](https://github.com/maisiq/cdekx/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cdekx.svg)](https://pypi.org/project/cdekx/)
[![Python](https://img.shields.io/pypi/pyversions/cdekx.svg)](https://pypi.org/project/cdekx/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/maisiq/cdekx/blob/master/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

📖 **Полная документация:** [maisiq.github.io/cdekx](https://maisiq.github.io/cdekx/) —
быстрый старт, рецепты, справочник API, архитектура и карта покрытия API.

**Статус:** `0.1.0` — транспорт, авторизация, модели и эндпоинты **сверены с
OpenAPI-спецификацией** apidoc.cdek.ru (секция `api_v2_integration`, 41 путь).
Карта покрытия: [`docs/API_COVERAGE.md`](https://github.com/maisiq/cdekx/blob/master/docs/API_COVERAGE.md).

> Исходный код библиотеки (докстринги, описания полей, сообщения об ошибках) —
> на английском языке; этот README и
> [сайт документации](https://maisiq.github.io/cdekx/) — на русском.

---

## Почему `cdekx`

| Возможность | Что это даёт |
| --- | --- |
| Один `httpx.AsyncClient` на всё время жизни клиента | connection pooling вместо новой HTTP-сессии на каждый запрос |
| `RetryPolicy`: экспоненциальный backoff + джиттер | уважает `Retry-After`, повторяет 401 после обновления токена |
| `OAuth2ClientCredentials` с `asyncio.Lock` | один токен на N конкурентных запросов, запас до истечения, хук для внешнего кэша |
| Иерархия `ApiError` → `AuthError` / `NotFoundError` / `RateLimitError` / `ServerError` | разобранные `errors[]`, `request_id`, `retry_after` вместо безликого `Exception` |
| `Paginator` + `async for` | пагинация без ручного `size=1000, page=0` |
| `orders.wait()` / `client.wait_order()` | API v2 асинхронный: опрос задачи до `SUCCESSFUL`/`INVALID` с разбором ошибок |
| `printing.waybill()` / `barcodes()` → `wait_*()` → `*_pdf()`, сквозные `download_waybill()` / `download_barcodes()` | печатная форма как готовый PDF, а не UUID задачи |
| Все 10 типов вебхуков + модели `attributes` для каждого + ASGI-приёмник | проверка подписи и типизированный разбор событий из коробки |
| Enum'ы принимают известные значения **и** произвольный `int`/`str` | справочники СДЭК расширяются без breaking change; плюс `calculator.available_tariffs()` |
| `ResponseEnvelope`: `entity` + `requests` (с `state`) + `related_entities` | ответ API отдаётся целиком, ничего не теряется |
| `phones: [{number, additional}]` как в `PhoneDto` | обычные строки приводятся автоматически |
| Стандартный `logging` (`cdekx`, `cdekx.http`, `cdekx.auth`) | нулевая настройка и никаких лог-зависимостей |
| Явные `_get` / `_post` / `_put` / `_delete` | никакой магии с `sys._getframe()` для определения HTTP-метода |
| `httpx`: HTTP/1.1 + HTTP/2, единый API для sync/async | транспорт, который легко мокировать в тестах |

### Соответствие актуальной спецификации

Модели и пути методов сверены с OpenAPI-спецификацией apidoc.cdek.ru
(секция `api_v2_integration`, 41 путь). Там, где старая документация и
сторонние интеграции расходятся с реальным API, `cdekx` следует спецификации:

- `PATCH /v2/orders` с идентификатором в теле, а не `PUT /v2/orders/{uuid}`;
- `GET /v2/orders` — это поиск **одного** заказа по номеру, списка заказов в API нет;
- состояние асинхронной задачи живёт в `requests[].state`, отдельного `GET /v2/statuses/{uuid}` не существует;
- печать: JSON-тело запроса, раздельные пути статуса и `…/{uuid}.pdf`;
- ставки НДС `0/5/7/10/16/20/22`, а не устаревшие `0/10/20`.

Расхождения проверяются автоматически: `scripts/fetch_openapi.py` скачивает
спецификацию, `scripts/generate_from_openapi.py --drift` сверяет её с кодом.

Подробнее: [`docs/ARCHITECTURE.md`](https://github.com/maisiq/cdekx/blob/master/docs/ARCHITECTURE.md)
и [`docs/API_COVERAGE.md`](https://github.com/maisiq/cdekx/blob/master/docs/API_COVERAGE.md).

## Установка

```bash
pip install cdekx                # ядро
pip install "cdekx[webhooks]"    # + приём вебхуков (starlette)
pip install "cdekx[dev]"         # + тесты, линтеры, документация
```

Требуется Python 3.10+.

## Быстрый старт

```python
import asyncio

from cdekx import CdekClient, Environment
from cdekx.models import CalculatorLocation, CalculatorPackage, TariffRequest
from cdekx.types.enums import Currency


async def main() -> None:
    async with CdekClient(
        client_id="...",
        client_secret="...",
        environment=Environment.SANDBOX,  # api.edu.cdek.ru
    ) as client:
        tariff = await client.calculator.tariff(
            TariffRequest(
                tariff_code=136,  # «Экспресс лайт»
                from_location=CalculatorLocation(code=44),  # Москва
                to_location=CalculatorLocation(code=270),  # Екатеринбург
                packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
                currency=Currency.RUB,  # числовой код из «Приложения 14»: RUB = 1
                lang="rus",
            )
        )
        # сроки — в рабочих днях (period_*) и календарных (calendar_*)
        print(tariff.delivery_sum, tariff.total_sum, tariff.period_min, tariff.period_max)
        print(tariff.delivery_date_range)  # прогноз дат доставки


asyncio.run(main())
```

Учётные данные можно не передавать — клиент возьмёт их из окружения
(`CDEKX_CLIENT_ID`, `CDEKX_CLIENT_SECRET`):

```python
client = CdekClient.from_env()
```

Для учебной среды есть готовый конструктор с публичными тестовыми ключами СДЭК:

```python
client = CdekClient.sandbox()
```

### Создание заказа

```python
from cdekx.models import Contact, Item, Location, Money, OrderCreate, Package
from cdekx.types.enums import OrderType, ServiceCode, TariffCode

order = OrderCreate(
    type=OrderType.E_COMMERCE,
    number="ORDER-0001",
    tariff_code=TariffCode.EXPRESS_LIGHT_DOOR_DOOR,
    from_location=Location(code=44, address="ул. Ленина, 1"),
    to_location=Location(code=270, address="ул. Мира, 10, кв. 5"),
    # phones — список объектов {number, additional}; строки приводятся сами
    sender=Contact(name="Иван Петров", phones=["+79001234567"]),
    recipient=Contact(name="Мария Смирнова", phones=[{"number": "+79007654321"}]),
    packages=[
        Package(
            number="PKG-1",
            weight=1000,
            length=30,
            width=20,
            height=10,
            items=[
                Item(
                    name="Книга",
                    ware_key="SKU-42",
                    payment=Money(value=990.0, vat_rate=22),
                    cost=990.0,
                    weight=1000,
                    amount=1,
                )
            ],
        )
    ],
    services=[{"code": ServiceCode.INSURANCE, "parameter": "990"}],
    has_reverse_order=True,
)

# API v2 асинхронный: POST отвечает 202 + состояние ACCEPTED — это статус
# запроса, а не заказа. Заказ создаётся фоном за 200–500 мс (до 60 с в пике).
task = await client.orders.create(order)
envelope = await client.orders.wait(task.uuid, interval=3)  # → SUCCESSFUL

created = envelope.entity
print(created.cdek_number, created.status_code)
print(envelope.requests)  # состояние и ошибки асинхронной обработки
print(envelope.related_entities)  # реверсный заказ, печатные формы
```

### ПВЗ: выгрузка города и поиск ближайших

```python
from cdekx.models import DeliveryPointFilter

async for point in client.delivery_points.paginate(
    DeliveryPointFilter(city_code=44, type="PVZ"), page_size=500
):
    print(point.code, point.location.address, point.status)

# «Рядом с точкой» в API делается прямоугольником координат (byPolygons)
from cdekx.models import DeliveryPointPolygonFilter

points = await client.delivery_points.by_polygon(
    latitude_right_top=55.78,
    longitude_right_top=37.65,
    latitude_left_bottom=55.73,
    longitude_left_bottom=37.60,
    # byPolygons поддерживает только: type, city_uuid, have_cashless,
    # have_cash, allowed_cod, is_dressing_room, weight_max, weight_min, lang
    filter=DeliveryPointPolygonFilter(type="PVZ"),
)
```

### Печать штрихкодов и квитанций

```python
pdf = await client.printing.download_barcodes([order_uuid], format="A4")
open("barcodes.pdf", "wb").write(pdf)

# или по шагам: задача → ожидание → скачивание (.pdf требует авторизации)
task = await client.printing.waybill([order_uuid], copy_count=2)
ready = await client.printing.wait_waybill(task.uuid, timeout=120)
receipt = await client.printing.waybill_pdf(ready.uuid)
```

### Приём вебхуков (FastAPI)

```python
from cdekx.webhooks import WebhookEvent
from cdekx.webhooks.asgi import WebhookApp


async def on_event(event: WebhookEvent) -> None:
    if event.type == "ORDER_STATUS":
        attrs = event.attributes  # типизированная модель OrderStatusAttributes
        print(attrs.cdek_number, attrs.code)


webhook_app = WebhookApp(on_event=on_event, path_secret="long-random-secret")
app.mount("/webhooks/cdek", webhook_app.asgi)  # app — ваше FastAPI-приложение
```

Активных подписок на аккаунт может быть не больше двух — на третью СДЭК
отвечает HTTP 400 с кодом `v2_too_many_webhooks`
(`WebhooksEndpoint.is_limit_error(exc)`); переехать на новый URL помогает
`webhooks.replace(url, type)`. В OpenAPI-спецификации лимита нет — он
подтверждён замером на `api.edu.cdek.ru`.

### Обработка ошибок

```python
from cdekx import ApiError, AuthError, NotFoundError, RateLimitError

try:
    order = await client.orders.get(uuid)
except NotFoundError:
    ...  # заказа нет
except RateLimitError as exc:
    await asyncio.sleep(exc.retry_after or 1)
except AuthError:
    ...  # проблема с учётными данными
except ApiError as exc:
    logger.error("СДЭК: %s (request_id=%s)", exc.errors, exc.request_id)
```

## Структура проекта

```
cdekx/
├── pyproject.toml            # метаданные, зависимости, ruff/mypy/pytest
├── src/cdekx/
│   ├── client.py             # CdekClient — точка входа
│   ├── config.py             # ClientConfig / Settings (в т.ч. из env)
│   ├── _http.py              # транспорт, таймауты, RetryPolicy
│   ├── _auth.py              # OAuth2 client credentials + кэш токена
│   ├── exceptions.py         # иерархия ошибок
│   ├── pagination.py         # Paginator (async for по страницам)
│   ├── utils.py              # вес/объём/телефоны — прикладные хелперы
│   ├── types/                # Environment, даты, ApiErrorDetail, enums
│   ├── models/               # pydantic-модели по разделам API
│   ├── endpoints/            # orders, calculator, locations, delivery,
│   │                         # delivery_agreement, intakes, printing,
│   │                         # webhooks, misc
│   └── webhooks/             # события вебхуков + ASGI-приёмник
├── scripts/                  # fetch_openapi.py, generate_from_openapi.py
├── tests/                    # unit (respx) + integration (api.edu.cdek.ru)
├── docs/                     # ARCHITECTURE, API_COVERAGE, quickstart…
├── examples/                 # готовые сценарии
└── .github/workflows/        # CI + публикация в PyPI
```

## Разработка

```bash
git clone https://github.com/maisiq/cdekx && cd cdekx
uv sync --group dev        # или: pip install -e ".[dev]"

uv run pytest              # тесты
uv run ruff check .        # линтер
uv run ruff format .       # форматирование
uv run mypy src            # строгая типизация

CDEKX_RUN_INTEGRATION=1 CDEKX_CLIENT_ID=... CDEKX_CLIENT_SECRET=... \
    uv run pytest -m integration     # тесты против учебной среды
```

## Лицензия

Apache-2.0 — см. [LICENSE](https://github.com/maisiq/cdekx/blob/master/LICENSE) и [NOTICE](https://github.com/maisiq/cdekx/blob/master/NOTICE).

Библиотеку можно свободно использовать в проприетарных и коммерческих продуктах,
модифицировать и распространять; патентная оговорка Apache-2.0 включена.

### Происхождение кода

`cdekx` — **независимая реализация** публичного API СДЭК v2. Модели и пути
методов построены по OpenAPI-спецификации apidoc.cdek.ru (секция
`api_v2_integration`), которую скачивает и сверяет `scripts/fetch_openapi.py`
и `scripts/generate_from_openapi.py --drift`.

Исходный код других клиентов СДЭК не копировался и не перерабатывался.
Общее с любой другой интеграцией СДЭК ограничивается неохраняемыми фактами
о самом API: путями методов, именами полей, типами данных и значениями
справочников (коды тарифов и доп. услуг, статусы, валюты).
Детали — в [NOTICE](https://github.com/maisiq/cdekx/blob/master/NOTICE) и
[`docs/ARCHITECTURE.md`](https://github.com/maisiq/cdekx/blob/master/docs/ARCHITECTURE.md#license).

## Полезные ссылки

- [Документация cdekx](https://maisiq.github.io/cdekx/) — быстрый старт, рецепты, справочник API (клиент, модели, исключения, вебхуки)
- [Портал документации СДЭК API](https://apidoc.cdek.ru/) (там же — скачивание OpenAPI-спецификации)
- [Личный кабинет СДЭК](https://lk.cdek.ru/) → раздел «Интеграция» → «Создать ключ»
- [`docs/API_COVERAGE.md`](https://github.com/maisiq/cdekx/blob/master/docs/API_COVERAGE.md) — карта покрытия методов API
