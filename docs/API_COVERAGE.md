# Покрытие API СДЭК

Карта методов API и их состояния в `cdekx`.

**Источник истины:** OpenAPI-спецификация портала apidoc.cdek.ru
(секция `api_v2_integration`, OpenAPI 3.0.1, 41 путь). Скачивается скриптом:

```bash
python scripts/fetch_openapi.py                 # → .apidoc/api_v2_integration.json
python scripts/generate_from_openapi.py .apidoc/api_v2_integration.json --list
python scripts/generate_from_openapi.py .apidoc/api_v2_integration.json --drift
```

Обозначения:

* ✅ реализовано и покрыто тестами;
* 🟡 реализовано, но возвращает сырой JSON (модели ещё не описаны);
* ⬜ не реализовано;
* ❌ в актуальном API не существует (реализовывать не нужно).

Разделов с 🟡 в библиотеке не осталось: все методы секции
`api_v2_integration` покрыты типизированными моделями.

## Авторизация

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Получение токена | `POST /v2/oauth/token` | ✅ | `_auth.OAuth2ClientCredentials` |

Ответ 401 приходит с телом `{"error": ..., "error_description": ...}`
(`ErrorDto`) — обработано в `_auth._oauth_error_message`.

## Заказы

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Регистрация заказа | `POST /v2/orders` (202) | ✅ | `orders.create()` |
| Изменение заказа | `PATCH /v2/orders` (202) | ✅ | `orders.update()` |
| Информация о заказе по UUID | `GET /v2/orders/{uuid}` | ✅ | `orders.get()` / `orders.get_envelope()` |
| Информация по номеру СДЭК/ИМ | `GET /v2/orders?cdek_number=` / `?im_number=` | ✅ | `orders.get_by_number()` / `get_by_client_number()` |
| Удаление заказа | `DELETE /v2/orders/{uuid}` (202) | ✅ | `orders.delete()` |
| Регистрация клиентского возврата | `POST /v2/orders/{uuid}/clientReturn` | ✅ | `orders.client_return()` |
| Регистрация отказа | `POST /v2/orders/{uuid}/refusal` | ✅ | `orders.refuse()` |
| Все заявки по заказу | `GET /v2/orders/{orderUuid}/intakes` | ✅ | `orders.intakes()` |
| Ожидание асинхронной обработки | — (поллинг `GET`) | ✅ | `orders.wait()` / `client.wait_order()` |
| Список заказов с пагинацией | — | ❌ | такого метода в API нет |
| `PUT /v2/orders/{uuid}` | — | ❌ | изменение идёт через `PATCH` |
| Статусы задач `GET /v2/statuses/{uuid}` | — | ❌ | статуса задачи нет: состояние в `requests[].state` ответа по сущности |

## Калькулятор

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Расчёт по коду тарифа | `POST /v2/calculator/tariff` | ✅ | `calculator.tariff()` |
| Расчёт по доступным тарифам | `POST /v2/calculator/tarifflist` | ✅ | `calculator.tariff_list()` |
| Расчёт по тарифам и доп. услугам | `POST /v2/calculator/tariffAndService` | ✅ | `calculator.tariff_and_service()` |
| Список доступных тарифов | `GET /v2/calculator/alltariffs` | ✅ | `calculator.available_tariffs()` |
| Расчёт таможенной пошлины | `/v2/calculator/customsduty` | ❌ | метода нет в актуальной спецификации |

## Локации

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Список населённых пунктов | `GET /v2/location/cities` | ✅ | `locations.cities()` / `paginate_cities()` |
| Список регионов | `GET /v2/location/regions` | ✅ | `locations.regions()` / `paginate_regions()` |
| Подбор локации по названию | `GET /v2/location/suggest/cities` | ✅ | `locations.suggest_cities()` |
| Локация по координатам | `GET /v2/location/coordinates` | ✅ | `locations.city_by_coordinates()` |
| Почтовые индексы города | `GET /v2/location/postalcodes` | ✅ | `locations.postalcodes()` → `Postcodes` (`code` + `postal_codes`) |

## Офисы и ПВЗ

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Список офисов | `GET /v2/deliverypoints` | ✅ | `delivery_points.list()` / `get()` / `paginate()` |
| Офисы внутри прямоугольника координат | `GET /v2/deliverypoints/byPolygons` | ✅ | `delivery_points.by_polygon()` |
| Поиск «в радиусе от точки» | — | ❌ | в API нет: используется прямоугольник координат |

## Договорённость о доставке

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Регистрация договорённости | `POST /v2/delivery` (202) | ✅ | `delivery_agreement.create()` |
| Информация о договорённости | `GET /v2/delivery/{uuid}` | ✅ | `delivery_agreement.get()` |
| Интервалы доставки по заказу | `GET /v2/delivery/intervals` | ✅ | `delivery_agreement.intervals()` |
| Интервалы до создания заказа | `POST /v2/delivery/estimatedIntervals` | ✅ | `delivery_agreement.estimated_intervals()` |

## Заявки на вызов курьера

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Регистрация заявки | `POST /v2/intakes` (202) | ✅ | `intakes.create()` |
| Информация о заявке | `GET /v2/intakes/{uuid}` | ✅ | `intakes.get()` / `get_envelope()` |
| Изменение статуса заявки | `PATCH /v2/intakes` | ✅ | `intakes.change_status()` |
| Удаление заявки | `DELETE /v2/intakes/{uuid}` | ✅ | `intakes.delete()` |
| Доступные даты вызова курьера | `POST /v2/intakes/availableDays` | ✅ | `intakes.available_days()` |
| Список заявок | `GET /v2/intakes` | ❌ | метода нет в актуальной спецификации |
| Изменение заявки | `PUT /v2/intakes/{uuid}` | ❌ | метода нет — только смена статуса |

## Печатные формы

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Формирование квитанции | `POST /v2/print/orders` (202) | ✅ | `printing.waybill()` |
| Получение квитанции | `GET /v2/print/orders/{uuid}` | ✅ | `printing.waybill_status()` |
| Скачивание квитанции | `GET /v2/print/orders/{uuid}.pdf` | ✅ | `printing.waybill_pdf()` |
| Формирование ШК места | `POST /v2/print/barcodes` (202) | ✅ | `printing.barcodes()` |
| Получение ШК места | `GET /v2/print/barcodes/{uuid}` | ✅ | `printing.barcode_status()` |
| Скачивание ШК места | `GET /v2/print/barcodes/{uuid}.pdf` | ✅ | `printing.barcode_pdf()` |
| Ожидание готовности | — (поллинг) | ✅ | `printing.wait_waybill()` / `wait_barcode()` |
| Сквозная печать | — | ✅ | `printing.download_waybill()` / `download_barcodes()` |
| Копия заказа | `/v2/print/copy_order` | ❌ | метода нет в актуальной спецификации |

## Вебхуки

| Метод | Путь | Статус | Где в cdekx |
| --- | --- | --- | --- |
| Добавление подписки | `POST /v2/webhooks` | ✅ | `webhooks.create()` |
| Список подписок | `GET /v2/webhooks` | ✅ | `webhooks.list()` |
| Подписка по UUID | `GET /v2/webhooks/{uuid}` | ✅ | `webhooks.get()` |
| Удаление подписки | `DELETE /v2/webhooks/{uuid}` | ✅ | `webhooks.delete()` |
| Замена подписок | — | ✅ | `webhooks.replace()`, `delete_all()`, `has_capacity()` |

### Типы событий (все 10 поддержаны в `webhooks.events`)

`ORDER_STATUS`, `PRINT_FORM`, `PREALERT_CLOSED`, `ACCOMPANYING_WAYBILL`,
`OFFICE_AVAILABILITY`, `ORDER_MODIFIED`, `DELIV_AGREEMENT`, `DELIV_PROBLEM`,
`COURIER_INFO`, `DOWNLOAD_PHOTO`.

Типизированные модели атрибутов есть для всех, кроме `ACCOMPANYING_WAYBILL`
(схема в документации не раскрыта — событие парсится со словарём `attributes`).

## Прочие разделы

Все методы типизированы. Обратите внимание: ответы здесь приходят **не**
конвертом `{entity, requests}`, а «списком с ошибками» — см.
`cdekx.models.ListResponse`. HTTP 200 не гарантирует успех: проверяйте
`response.has_errors` / `response.error_codes`.

| Метод | Путь | Статус | Где в cdekx | Модель ответа |
| --- | --- | --- | --- | --- |
| Проверка доступности реверса | `POST /v2/reverse/availability` | ✅ | `misc.reverse_availability()` | `None` (пустое тело 200 = доступен; иначе `ApiError`) |
| Информация о чеках | `GET /v2/check` | ✅ | `misc.checks()` | `CheckResponse` → `list[CheckInfo]` |
| Паспортные данные | `GET /v2/passport` | ✅ | `misc.passports(client=…)` | `PassportResponse` → `list[PassportOrder]` |
| Реестры наложенных платежей | `GET /v2/registries` | ✅ | `misc.registries(date)` | `RegistriesResponse` → `list[Registry]` |
| Заказы с готовыми фото | `POST /v2/photoDocument` | ✅ | `misc.photo_ready_orders()` | `PhotoResponse` → `list[PhotoReadyOrder]` |
| Скачивание архива фото | `GET /v2/photoDocument/{uuid}` | ✅ | `misc.photo_archive()` | `bytes` (ZIP) |
| Регистрация преалерта | `POST /v2/prealert` (202) | ✅ | `misc.prealert_create()` | `PrealertTaskEnvelope` |
| Информация о преалерте | `GET /v2/prealert/{uuid}` | ✅ | `misc.prealert_get()` | `PrealertEnvelope` → `Prealert` |
| Ограничения международных заказов | `POST /v2/international/package/restrictions` | ✅ | `misc.international_restrictions()` | `RestrictionHintsResponse` → `list[PackageHint]` |
| Произвольный запрос | любой | ✅ | `misc.raw(method, path)` | сырой JSON |

Особенности, найденные при сверке со спецификацией:

* `POST /v2/reverse/availability` **не имеет схемы ответа**: доступность
  реверса выражается пустым телом с кодом 200, а недоступность — HTTP 400 с
  описанием. Поэтому метод возвращает `None` и бросает `ApiError`.
* `POST /v2/international/package/restrictions` отдаёт тело с типом `*/*`,
  а не `application/json` — на разбор это не влияет.
* `GET /v2/registries` имеет единственный и **обязательный** параметр `date`.
* `GET /v2/check` требует хотя бы один из `order_uuid` / `cdek_number` /
  `date`; `cdekx` не отправляет пустой запрос и бросает `ValueError`.
* `RestrictionItemRequestDto.itemId` — единственное поле в спецификации,
  объявленное в camelCase (`writeOnly`), но **живой API его не читает**:
  на `itemId` он отвечает `v2_field_is_empty: [packages[0].items[0].item_id]
  is empty`. Модель отправляет `item_id` (проверено на `api.edu.cdek.ru`).
* В `RestrictionPackageRequestDto` все поля необязательны, однако без
  `package_id` и `items` API отвечает `v2_field_is_empty` — фактически они
  обязательны.
* `GET /v2/prealert/{uuid}` не возвращает `uuid` преалерта и `order_uuid`
  заказа, хотя схема объявляет их обязательными: идентификатор нужно хранить
  у себя (получить его можно из ответа на создание).
* Даты в телах запросов (`PhotoRequestDto.period_*`,
  `RegisterPrealertRequestDto.planned_date`) принимаются **только** в формате
  `yyyy-MM-dd'T'HH:mm:ssZ` (`+0300`); `Z`-суффикс и ISO-смещение `+03:00`
  отклоняются с `v2_invalid_value_type`. `cdekx.types.CdekDateTimeOut`
  сериализует `datetime` в нужный формат.
* `POST /v2/reverse/availability` для тарифов с режимом «до склада»/
  «до постамата» требует `delivery_point`, а причины недоступности отдаёт
  кодами `reverse_order_*` (`reverse_order_reverse_tariff_not_found`,
  `reverse_order_macrozone_partner`, `reverse_order_receiver_office_empty`),
  которых нет в спецификации.
* `GET /v2/check` на неизвестный заказ отвечает 400/404 (`v2_order_not_found`
  / `v2_entity_not_found`), а `GET /v2/passport` — 200 с
  `errors: [v2_entity_empty]` и `warnings: [v2_order_not_found]` в теле.
  Один и тот же сценарий обработан по-разному, поэтому `checks()` бросает
  исключение, а `passports()` возвращает ответ с `has_errors`.
* `cdek_number` описан в спецификации несогласованно: строка в
  `OrderResponseDto` и `int64` в `CheckInfoDto`/`PassportOrderDto`/
  `RegistryOrderDto`/`PhotoReadyOrderDto`/`GetPrealertResponseDtoOrderDto`.
  В ответах `cdekx` нормализует его к `str` (тип `CdekNumber`), в запросах
  оставляет как передано.
* Статус ограничения `FORBIDDEN` может стоять на товаре внутри грузоместа,
  хотя у самого места статус `LIMITED` — `PackageHint.is_forbidden` проверяет
  оба уровня.

## Справочники

Методов `/v2/handbook/*` в актуальной спецификации **нет** — они встречались
только в устаревшей документации. Актуальные источники справочных данных:

| Данные | Как получить |
| --- | --- |
| Тарифы по договору | `calculator.available_tariffs()` |
| Города / регионы / индексы | `locations.*` |
| Офисы и их возможности | `delivery_points.list()` |
| Доп. услуги, статусы, материалы | Приложения 6, 15, 7 на apidoc.cdek.ru (статичные таблицы) |

## Соответствие актуальной спецификации

Старая документация СДЭК расходится с реальным контрактом API. Там, где это так,
`cdekx` следует спецификации apidoc.cdek.ru:

| В актуальном API | В `cdekx` |
| --- | --- |
| `phones: [{number, additional}]` (`PhoneDto`) | `list[Phone]`, обычные строки приводятся автоматически |
| `PATCH /v2/orders`, идентификатор в теле | `orders.update(OrderUpdate)` |
| `GET /v2/orders` возвращает **один** заказ по номеру | `orders.get_by_number()` |
| ответ — `{entity, requests, related_entities}` | `ResponseEnvelope` с `state`, `errors`, `warnings`, `related()` |
| `tariff_name`/`description`/`mode` есть только у `tarifflist` (`TariffCodeDto`) | раздельные модели `TariffCalculation` и `TariffCodeItem` |
| `GET /v2/calculator/customs-duty` отсутствует | метод не реализован |
| `/v2/print/*`: JSON-тело, раздельные пути статуса и `.pdf` | `printing.waybill` / `barcodes` / `*_status` / `*_pdf` |
| `GET /v2/statuses/{uuid}` отсутствует | `requests[].state` + `orders.wait()` |
| 10 типов вебхуков | все 10 + модели атрибутов для каждого |
| ставки НДС 0, 5, 7, 10, 16, 22 (действуют с 01.01.2026) | `VatRate` полностью |
| `country_code: string(2)` | `str` |

Расхождения проверяются автоматически: `scripts/fetch_openapi.py` скачивает
спецификацию, `scripts/generate_from_openapi.py --drift` сверяет её с моделями.

## Приоритеты доработки

1. Проверить на живом API тела `POST /v2/orders/{uuid}/clientReturn` и
   `POST /v2/orders/{uuid}/refusal`: в спецификации у первого только
   `{tariff_code}`, у второго requestBody отсутствует вовсе, а модели `cdekx`
   допускают более широкую форму.
2. Расширить проверку дрейфа: сейчас маппинг покрывает 126 схем из 188
   (остальные — алиасы, неиспользуемые схемы и конверты), сравниваются только
   имена полей, без типов.
3. Добавить секции `fulfillment`, `marketplace_integration`,
   `customs_client_integration`, `fourth_pl_protocol` — они скачиваются тем же
   `scripts/fetch_openapi.py`.
4. Внешний кэш токенов (Redis) через `OAuth2ClientCredentials(on_token=...)` +
   пример для мультипроцессных деплоев.

CI-проверка дрейфа уже настроена: задание `drift` в `.github/workflows/ci.yml`
по расписанию (еженедельно) и вручную скачивает спецификацию и запускает
`generate_from_openapi.py --drift`.
