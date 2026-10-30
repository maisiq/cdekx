# Рецепты

Готовые сценарии. Все примеры предполагают созданный клиент:

```python
from cdekx import CdekClient

client = CdekClient.from_env()
```

## Расчёт стоимости для корзины интернет-магазина

```python
from cdekx.models import CalculatorLocation, CalculatorPackage, TariffListRequest
from cdekx.utils import kg_to_grams


async def delivery_options(cart_items, to_city_code: int):
    packages = [
        CalculatorPackage(
            weight=kg_to_grams(item.weight_kg),
            length=item.length_cm,
            width=item.width_cm,
            height=item.height_cm,
        )
        for item in cart_items
    ]
    result = await client.calculator.tariff_list(
        TariffListRequest(
            from_location=CalculatorLocation(code=44),  # склад отправления
            to_location=CalculatorLocation(code=to_city_code),
            packages=packages,
        )
    )
    viable = [t for t in result.tariff_codes if not t.has_errors]
    return sorted(viable, key=lambda t: (t.delivery_sum, t.period_min or 0))
```

`has_errors` важен: калькулятор возвращает HTTP 200, но часть тарифов может
содержать ошибки расчёта (недоступное направление, превышение веса).

## ПВЗ рядом с адресом получателя

Поиска «в радиусе N метров» в API нет — используется прямоугольник координат
(`GET /v2/deliverypoints/byPolygons`). Отступ ~0.03° ≈ 3 км по широте.

!!! warning
    `byPolygons` поддерживает **меньше** фильтров, чем список офисов: только
    `type`, `city_uuid`, `have_cashless`, `have_cash`, `allowed_cod`,
    `is_dressing_room`, `weight_max`, `weight_min` и `lang` (без пагинации).
    В `cdekx` для него есть отдельная модель `DeliveryPointPolygonFilter`.

```python
from cdekx.models import DeliveryPointPolygonFilter


async def pickup_points_near(lat: float, lon: float, delta: float = 0.03):
    points = await client.delivery_points.by_polygon(
        latitude_right_top=lat + delta,
        longitude_right_top=lon + delta,
        latitude_left_bottom=lat - delta,
        longitude_left_bottom=lon - delta,
        filter=DeliveryPointPolygonFilter(type="PVZ", allowed_cod=True),
    )
    found = [
        {
            "code": p.code,
            "name": p.name,
            "address": p.location.address,
            "work_time": p.work_time,
            "distance": p.distance,
        }
        for p in points
    ]
    return sorted(found, key=lambda p: p["distance"] or 0)
```

## Выгрузка всех ПВЗ города

```python
from cdekx.models import DeliveryPointFilter

points = []
async for point in client.delivery_points.paginate(
    DeliveryPointFilter(city_code=44, type="ALL"), page_size=500
):
    points.append(point)  # point.location.address, point.status, point.work_time_list
```

!!! note
    Фильтры `have_cash`, `allowed_cod`, `is_handout` и т.п. СДЭК принимает в виде
    `1`/`true`/`0`/`false` — `cdekx` приводит `bool` автоматически.

## Регистрация заказа с наложенным платежом и реверсом

```python
from cdekx.models import Contact, Item, Location, Money, OrderCreate, Package
from cdekx.types.enums import OrderType, ServiceCode, TariffCode

order = OrderCreate(
    type=OrderType.E_COMMERCE,
    number="ORDER-100500",
    tariff_code=TariffCode.EXPRESS_LIGHT_DOOR_DOOR,
    from_location=Location(code=44, address="склад 1"),
    to_location=Location(code=270, address="ул. Мира, 10, кв. 5"),
    sender=Contact(
        company="ООО «Ромашка»",
        name="Иван Петров",
        phones=[{"number": "+79001234567"}],
        contragent_type="LEGAL_ENTITY",
    ),
    recipient=Contact(name="Мария Смирнова", phones=["+79007654321"]),
    packages=[
        Package(
            number="PKG-1",
            weight=2500,
            length=40,
            width=30,
            height=20,
            items=[
                Item(
                    name="Кофеварка",
                    ware_key="SKU-1",
                    payment=Money(value=8990.0, vat_rate=22),
                    cost=8990.0,
                    weight=2500,
                    amount=1,
                )
            ],
        )
    ],
    delivery_recipient_cost=Money(value=350.0),  # доставка за счёт получателя
    services=[
        {"code": ServiceCode.INSURANCE, "parameter": "8990"},
        {"code": ServiceCode.TRYING_ON},
    ],
    has_reverse_order=True,  # замена устаревшей услуги REVERSE
    # динамический сбор: при выкупе до 5000 ₽ доставка 500 ₽
    delivery_recipient_cost_adv=[{"threshold": 5000, "sum": 500}],
)

task = await client.orders.create(order)  # HTTP 202, state == ACCEPTED
envelope = await client.orders.wait(task.uuid, timeout=90, interval=3)
created = envelope.entity  # state == SUCCESSFUL
print(envelope.state, [w.code for w in envelope.warnings])
```

## Массовое создание заказов с ограничением нагрузки

```python
import asyncio

from cdekx.models import OrderCreate

LIMIT = 10  # СДЭК гарантирует ~200 RPS на договор, но лучше не упираться


async def create_all(orders: list[OrderCreate]) -> list[str]:
    sem = asyncio.Semaphore(LIMIT)

    async def one(order: OrderCreate) -> str:
        async with sem:
            task = await client.orders.create(order)
            return task.uuid or ""

    return list(await asyncio.gather(*(one(o) for o in orders)))
```

Для больших объёмов создайте клиент с `max_concurrency`:

```python
client = CdekClient.from_env(max_concurrency=20)
```

## Печать этикеток (ШК мест)

```python
async def print_labels(order_uuids: list[str], path: str = "labels.pdf") -> None:
    pdf = await client.printing.download_barcodes(order_uuids, format="A4")
    with open(path, "wb") as fh:
        fh.write(pdf)
```

Пошаговый вариант — ШК места и квитанция идут по разным путям:

```python
# ШК места (этикетки)
task = await client.printing.barcodes(order_uuids, format="A4", copy_count=1, lang="RUS")
ready = await client.printing.wait_barcode(task.uuid, timeout=90)
pdf = await client.printing.barcode_pdf(ready.uuid)

# квитанция к заказу (СДЭК рекомендует copy_count >= 2)
task = await client.printing.waybill(order_uuids, copy_count=2)
ready = await client.printing.wait_waybill(task.uuid, timeout=90)
receipt = await client.printing.waybill_pdf(ready.uuid)
```

!!! tip "Печатаете много?"
    Вместо поллинга подпишитесь на вебхук `PRINT_FORM`: СДЭК сам пришлёт `url`
    готового файла. Поллинг оставьте для разовых операций.

## Вебхуки

### Подписка

```python
from cdekx import ApiError
from cdekx.endpoints.webhooks import WebhooksEndpoint
from cdekx.types.enums import WebhookType

URL = "https://example.com/webhooks/cdek/LONG_RANDOM_SECRET"

try:
    await client.webhooks.create(URL, WebhookType.ORDER_STATUS)
except ApiError as exc:
    if not WebhooksEndpoint.is_limit_error(exc):
        raise
    # СДЭК разрешает не больше двух активных подписок на аккаунт:
    # освобождаем слоты и пересоздаём подписку на актуальный URL.
    await client.webhooks.replace(URL, WebhookType.ORDER_STATUS)
```

!!! warning "Не больше двух активных подписок"
    Лимита нет в OpenAPI-спецификации, но API его соблюдает: на третью
    подписку `POST /v2/webhooks` отвечает HTTP 400 с кодом
    `v2_too_many_webhooks` («Too many active webhooks. Maximum allowed is 2.»).
    Код доступен как `cdekx.models.TOO_MANY_WEBHOOKS_ERROR`, проверка —
    `WebhooksEndpoint.is_limit_error(exc)`.

    `has_capacity()` — оценка, а не гарантия: `GET /v2/webhooks` может
    вернуть больше двух записей, из которых API активными считает не все
    (в песочнице наблюдалось 3 записи в списке при двух активных в тексте
    ошибки — например, подписка, которая будет удалена через 24 часа
    из-за ошибок доставки). Поэтому лимит всё равно ловите исключением.

### Приём в FastAPI

```python
import logging

from fastapi import FastAPI

from cdekx.webhooks import WebhookEvent
from cdekx.webhooks.asgi import WebhookApp

logger = logging.getLogger(__name__)
app = FastAPI()


async def on_event(event: WebhookEvent) -> None:
    if event.type == "ORDER_STATUS":
        attrs = event.attributes
        logger.info(
            "order %s -> %s (%s)",
            attrs.cdek_number,
            attrs.code,
            attrs.status_reason_code,
        )
        # сохраните событие в очередь и обработайте в фоне:
        # у СДЭК таймаут 15 секунд на ответ


webhook_app = WebhookApp(on_event=on_event, path_secret="LONG_RANDOM_SECRET")
app.mount("/webhooks/cdek", webhook_app.asgi)
```

!!! warning "Всегда отвечайте 200"
    Если СДЭК не получает успешный ответ, он повторяет доставку (до 12 раз за
    75 минут), а при устойчивых ошибках удаляет подписку через 24 часа.
    `WebhookApp` по умолчанию отвечает 200 даже при падении обработчика.

## Загрузка справочников в кэш

```python
async def load_reference_data() -> dict:
    tariffs = await client.calculator.available_tariffs(lang="rus")
    cities = []
    async for city in client.locations.paginate_cities(page_size=1000):
        cities.append({"code": city.code, "city_uuid": city.city_uuid, "name": city.city})
    return {
        "tariff_codes": tariffs.all_tariff_codes(),
        "cities": cities,
    }
```

Справочники меняются редко — кэшируйте результат (Redis, файл, БД) и обновляйте
раз в сутки. Коды доп. услуг и статусов берутся из Приложений 6 и 15 на
apidoc.cdek.ru: отдельных методов-справочников для них в API нет.

## Проверка реверса перед созданием заказа

`POST /v2/reverse/availability` отвечает **пустым телом с кодом 200**, если
реверс доступен, и HTTP 400 с описанием причины — если нет. Поэтому метод
возвращает `None`, а недоступность приходит как исключение:

```python
from cdekx import ApiError
from cdekx.models import ReverseContragent, ReverseLocation, ReverseValidateRequest

request = ReverseValidateRequest(
    tariff_code=136,
    delivery_point="MSK2",  # обязателен для тарифов «до склада»/«до постамата»
    from_location=ReverseLocation(code=44, address="ул. Тестовая, 1"),
    sender=ReverseContragent(contragent_type="INDIVIDUAL", phones=["89001234567"]),
    recipient=ReverseContragent(contragent_type="INDIVIDUAL", phones=["+79007654321"]),
)

try:
    await client.misc.reverse_availability(request)
except ApiError as exc:
    # Коды причин (reverse_order_reverse_tariff_not_found,
    # reverse_order_macrozone_partner, …) в спецификации не описаны —
    # API возвращает их текстом в errors[]
    print("реверс недоступен:", [d.code for d in exc.errors])
else:
    print("реверс доступен — можно создавать прямой заказ")
```

Телефоны нормализуются автоматически (`89001234567` → `+79001234567`),
а ФИО контрагента здесь не нужно — только `contragent_type` и `phones`.

## Ограничения по международному направлению (ТН ВЭД)

```python
from cdekx.models import (
    Location,
    RestrictionItem,
    RestrictionPackage,
    RestrictionRequest,
)

hints = await client.misc.international_restrictions(
    RestrictionRequest(
        tariff_code=136,
        from_location=Location(code=44, address="ул. Тестовая, 1"),
        to_location=Location(code=176, country_code="AE"),  # Дубай
        packages=[
            RestrictionPackage(
                package_id="pkg-1",  # фактически обязателен
                weight=1500,
                length=35,
                width=25,
                height=15,
                items=[  # фактически обязателен
                    RestrictionItem(
                        name="Джинсы мужские Henry, размер M",
                        amount=1,
                        item_id="SKU-1",
                        feacn_code="620342",
                    )
                ],
            )
        ],
    )
)

if not hints.is_allowed:
    for package in hints.forbidden:
        print("нельзя отправить:", [i.item_id for i in package.forbidden_items])
for package in hints.packages or []:
    for item in package.items or []:
        if item.documents:
            print(f"товар {item.item_id}: нужны документы {item.documents}")
```

Два подводных камня, подтверждённых замером на `api.edu.cdek.ru`:

* в спецификации идентификатор товара объявлен как `itemId` (camelCase), но
  API принимает только `item_id` — модель отправляет `item_id`;
* `package_id` и `items` в схеме необязательны, однако без них API отвечает
  `v2_field_is_empty`.

Статус `FORBIDDEN` может стоять на товаре внутри грузоместа, хотя у самого
места статус `LIMITED`, поэтому `PackageHint.is_forbidden` проверяет оба
уровня.

## Чеки, реестры НП и паспортные данные

Ответы этих методов приходят не конвертом `{entity, requests}`, а «списком с
ошибками». **HTTP 200 здесь не означает успех** — проверяйте `has_errors`:

```python
# Фискальные чеки по заказу
try:
    checks = await client.misc.checks(cdek_number="1234567890")
except ApiError as exc:
    print("чеков нет:", exc)  # 400 v2_order_not_found / 404
else:
    for check in checks.checks:
        print(check.type, check.date, "итого", check.total)
        for payment in check.payment_info:
            print("   ", payment.type, payment.sum)

# Реестры наложенного платежа за дату (единственный и обязательный параметр)
registries = await client.misc.registries("2026-10-26")
for registry in registries.registries or []:
    print(registry.registry_number, registry.sum, registry.payment_order_number)
    for line in registry.orders:
        print(
            "   ",
            line.cdek_number,
            "НП:",
            line.payment_sum,
            "к начислению:",
            line.transfer_sum,
            "комиссия:",
            line.agent_commission_sum,
        )
print("сумма по всем реестрам:", registries.total)

# Паспортные данные: метод возвращает не данные, а признак, что требования
# удовлетворены (важно для международных заказов)
passports = await client.misc.passports(cdek_number="1234567890", client="RECEIVER")
if passports.has_errors:
    print("ошибки в теле ответа:", passports.error_codes)  # например v2_entity_empty
for order in passports.unsatisfied:
    print("нужно собрать паспортные данные:", order.cdek_number)
```

## Фото документов: от списка до архива

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cdekx.models import PhotoRequest

now = datetime.now(tz=timezone(timedelta(hours=3)))

# datetime сериализуется в формат СДЭК: 2026-10-27T13:40:00+0300.
# Ни «Z», ни «+03:00» API не принимает (v2_invalid_value_type).
photos = await client.misc.photo_ready_orders(
    PhotoRequest(period_begin=now - timedelta(days=30), period_end=now)
)

for order in photos.ready:  # только status == "DONE"
    archive = order.archive_uuid  # UUID из поля link
    if archive:
        data = await client.misc.photo_archive(archive)
        Path(f"{order.cdek_number}.zip").write_bytes(data)
```

## Преалерт: регистрация и расхождения

```python
from datetime import datetime, timedelta, timezone

from cdekx.models import PrealertCreate, PrealertOrder

planned = datetime.now(tz=timezone.utc) + timedelta(days=3)

task = await client.misc.prealert_create(
    PrealertCreate(
        planned_date=planned,  # уйдёт как «2026-10-30T12:15:00+0000»
        shipment_point="MSK",
        orders=[PrealertOrder(cdek_number="1234567890")],
    )
)
print("принят:", task.uuid, task.state)  # 202 + ACCEPTED — ещё не создан

# uuid преалерта API в GET не возвращает — храните его у себя
envelope = await client.misc.prealert_get(task.uuid)
prealert = envelope.entity

if prealert and prealert.is_closed:
    print("фактический ПВЗ:", prealert.fact_shipment_point)
    for package in prealert.discrepancies:  # NOT_ACCEPTED / DELETED
        print("расхождение:", package.number, package.status)
```

Если преалерт отклонён при обработке, `prealert_create()` сразу бросит
`ApiError` (состояние `INVALID` в `requests[]`) — ждать и опрашивать не нужно.
Вебхук `PREALERT_CLOSED` сообщит о закрытии преалерта без поллинга.

## Отладка без кода: CLI

```bash
export CDEKX_CLIENT_ID=... CDEKX_CLIENT_SECRET=...

cdekx --sandbox tariff --from 44 --to 270 --weight 1000 --tariff-code 136
cdekx --sandbox tariffs                    # тарифы, доступные по договору
cdekx --sandbox points --city-code 44 --type PVZ --limit 5
cdekx --sandbox city Новосибирск
cdekx --sandbox token                      # проверить учётные данные
cdekx order <uuid> --json
cdekx order-by-number 1234567890 --json
```

## Логирование

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("cdekx").setLevel(logging.DEBUG)  # всё
logging.getLogger("cdekx.http").setLevel(logging.DEBUG)  # только запросы
logging.getLogger("cdekx.auth").setLevel(logging.WARNING)  # тише про токены
```

Для детальной инспекции трафика подключите собственный транспорт httpx:

```python
import httpx

from cdekx import CdekClient

transport = httpx.AsyncHTTPTransport(retries=0)  # ретраи контролирует cdekx
client = CdekClient.from_env(http_client=httpx.AsyncClient(transport=transport))
```
