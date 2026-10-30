# Быстрый старт

## Установка

=== "pip"

    ```bash
    pip install cdekx                # ядро
    pip install "cdekx[webhooks]"    # приём вебхуков (starlette)
    pip install "cdekx[dev]"         # разработка: тесты, линтеры, mkdocs
    ```

=== "uv"

    ```bash
    uv add cdekx
    uv add "cdekx[webhooks]"
    ```

Требуется Python 3.10+.

## Учётные данные

Ключи выдаются в [личном кабинете СДЭК](https://lk.cdek.ru/): раздел
«Интеграция» → «Создать ключ». Для разработки используйте учебную среду
`api.edu.cdek.ru` — СДЭК публикует для неё общие тестовые ключи
(заказы в этой среде не доставляются).

Способы задать учётные данные:

```python
from cdekx import CdekClient, Environment

# 1. явно
client = CdekClient("account", "password", environment=Environment.SANDBOX)

# 2. из переменных окружения CDEKX_CLIENT_ID / CDEKX_CLIENT_SECRET / CDEKX_ENVIRONMENT
client = CdekClient.from_env()

# 3. учебная среда с публичными тестовыми ключами СДЭК
client = CdekClient.sandbox()
```

## Жизненный цикл клиента

Клиент владеет пулом HTTP-соединений — создавайте его один раз и закрывайте:

```python
async with CdekClient.from_env() as client:
    ...
```

Либо вручную:

```python
client = CdekClient.from_env()
try:
    ...
finally:
    await client.aclose()
```

!!! warning "Не создавайте клиент на каждый запрос"
    Это лишает вас keep-alive и заставляет заново получать OAuth-токен.

## Первый запрос: расчёт стоимости

```python
from cdekx.models import CalculatorLocation, CalculatorPackage, TariffRequest

tariff = await client.calculator.tariff(
    TariffRequest(
        tariff_code=136,  # «Экспресс лайт»
        from_location=CalculatorLocation(code=44),  # Москва
        to_location=CalculatorLocation(code=270),  # Екатеринбург
        packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
    )
)
print(tariff.delivery_sum, tariff.period_min, tariff.period_max)
```

Сравнить все доступные тарифы:

```python
from cdekx.models import CalculatorLocation, CalculatorPackage, TariffListRequest

result = await client.calculator.tariff_list(
    TariffListRequest(
        from_location=CalculatorLocation(code=44),
        to_location=CalculatorLocation(code=270),
        packages=[CalculatorPackage(weight=1000)],
    )
)
for option in sorted(result.viable, key=lambda t: t.delivery_sum)[:5]:
    print(option.tariff_code, option.tariff_name, option.delivery_sum)

cheapest = result.best()  # самый дешёвый из рассчитанных
fastest = result.fastest()  # самый быстрый

# тарифы, доступные именно по вашему договору
available = await client.calculator.available_tariffs()
print(available.all_tariff_codes())
```

## Заказ

```python
from cdekx.models import Contact, Item, Location, Money, OrderCreate, Package

order = OrderCreate(
    type=1,
    number="ORDER-0001",
    tariff_code=136,
    # address обязателен в запросе: по нему СДЭК определяет адрес отправителя
    from_location=Location(code=44, address="ул. Ленина, 1"),
    to_location=Location(code=270, address="ул. Мира, 10, кв. 5"),
    # phones — список объектов {"number": ..., "additional": ...};
    # строки cdekx приводит к этому формату сам
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
)

# POST /v2/orders отвечает 202 + состояние ACCEPTED: это статус запроса,
# а не заказа. Заказ создаётся фоном (обычно 200–500 мс, в пике до 60 с).
task = await client.orders.create(order)
envelope = await client.orders.wait(task.uuid, interval=3)  # → SUCCESSFUL

created = envelope.entity
print(created.cdek_number, created.status_code)
```

## Отслеживание статуса

```python
order = await client.orders.get_by_number("1234567890")
for status in order.statuses or []:
    print(status.date_time, status.code, status.name, status.reason_code, status.city)

# полный конверт ответа — с requests и related_entities (реверс, печатные формы)
envelope = await client.orders.get_envelope_by_number("1234567890")
print(envelope.state, envelope.warnings)
for related in envelope.related_entities or []:
    print(related.type, related.uuid, related.url)
```

Для потокового отслеживания используйте вебхуки — см. [Рецепты](recipes.md#вебхуки).

## Ошибки

```python
from cdekx import ApiError, AuthError, NotFoundError, RateLimitError

try:
    order = await client.orders.get(uuid)
except NotFoundError:
    print("заказа нет")
except RateLimitError as exc:
    await asyncio.sleep(exc.retry_after or 1)
except AuthError:
    print("проблема с учётными данными")
except ApiError as exc:
    print(exc.status_code, exc.codes, exc.request_id)
```

Библиотека сама повторяет запросы при 429/5xx и сетевых сбоях
(см. `RetryPolicy`), поэтому явный retry-код обычно не нужен.

## Что дальше

* [Рецепты](recipes.md) — печать этикеток, ПВЗ рядом, вебхуки, батчи.
* [Покрытие API](API_COVERAGE.md) — какие методы СДЭК уже реализованы.
* [Архитектура](ARCHITECTURE.md) — как устроена библиотека и как её расширять.
