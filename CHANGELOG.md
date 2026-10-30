# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект придерживается [семантического версионирования](https://semver.org/lang/ru/).

Записи ведутся **от публичного релиза к публичному релизу**: здесь только то,
что изменилось для пользователей библиотеки.

Внутренняя история разработки до первой публикации здесь не отражается — она
разнесена по профильным документам: расхождения между спецификацией и живым
API и приоритеты доработки — в `docs/API_COVERAGE.md`, устройство библиотеки
и релизный процесс — в `docs/ARCHITECTURE.md`, происхождение кода и лицензия —
в `NOTICE` и `docs/license.md`.

## [Unreleased]

## [0.1.0] - 2026-10-29

Первый публичный релиз.

Асинхронный клиент [API СДЭК v2](https://apidoc.cdek.ru/) — независимая
реализация по OpenAPI-спецификации СДЭК (секция `api_v2_integration`,
OpenAPI 3.0.1, 41 путь). Python 3.10+, зависимости — `httpx` и `pydantic` v2.
Распространяется под Apache-2.0 (см. `LICENSE` и `NOTICE`).

### Added

**Транспорт и авторизация**

- `CdekClient` — точка входа: один `httpx.AsyncClient` на всё время жизни
  клиента (connection pooling), HTTP/1.1 и HTTP/2, работа как контекстный
  менеджер (`async with`) плюс явный `aclose()`. Конструкторы `CdekClient(...)`,
  `CdekClient.from_env(**overrides)` и `CdekClient.sandbox()` для учебных ключей.
- `with_concurrency_limit()` — ограничение числа одновременных запросов.
- `OAuth2ClientCredentials` — поток `client_credentials` под `asyncio.Lock`
  (один токен на N конкурентных запросов), с запасом до истечения и хуком
  `on_token=` для внешнего кэша; для отладки есть `StaticTokenProvider`.
- `RetryPolicy` — экспоненциальный backoff с джиттером: уважает `Retry-After`,
  повторяет сетевые ошибки, 429 и 5xx, заново проходит 401 после обновления
  токена. Таймауты настраиваются через `Timeouts`.
- Иерархия ошибок `CdekxError` → `ApiError` → `AuthError`, `NotFoundError`,
  `RateLimitError`, `ServerError`; отдельно `TransportError`, `TimeoutExceeded`,
  `ValidationError`, `ConfigError`. У `ApiError` разобраны `errors[]`,
  `request_id` и `retry_after`.
- Стандартный `logging` без обязательной настройки: логгеры `cdekx`,
  `cdekx.http`, `cdekx.auth`, `cdekx.webhooks`.
- `ClientConfig` / `Settings` / `Environment` — конфигурация через конструктор
  и переменные окружения с префиксом `CDEKX_`.

**Модели**

- Строгие модели pydantic v2 на все разделы спецификации: заказы, статусы,
  калькулятор, офисы и ПВЗ, населённые пункты и почтовые индексы, договоры
  доставки, заявки на курьера, печать, вебхуки, а также «прочие» разделы —
  чеки, паспортные данные, реестры наложенного платежа, фото документов,
  преалерты, международные ограничения и реверс.
- `ResponseEnvelope` — ответ API отдаётся целиком: `entity`, `requests`
  (с `state` асинхронной задачи) и `related_entities`.
- `ListResponse` — база второй формы ответа СДЭК («список + ошибки»):
  `has_errors` и `error_codes`, потому что у таких методов HTTP 200
  не гарантирует успех.
- `CdekDateTime` / `CdekDateTimeOut` — терпимый разбор на входе и сериализация
  в формат СДЭК `yyyy-MM-dd'T'HH:mm:ssZ` (`+0300`, без двоеточия):
  `datetime.isoformat()` живой API отклоняет с `v2_invalid_value_type`.
- `CdekNumber`, `Money`, `Phone` — специфичные типы СДЭК; строки в `phones`
  приводятся к `[{number, additional}]` автоматически.
- `DeliveryPointPolygonFilter` — фильтр `by_polygon()` только с параметрами,
  которые реально поддерживает `GET /v2/deliverypoints/byPolygons`.
- Enum'ы принимают известные значения **и** произвольные `int`/`str`:
  справочники СДЭК расширяются без breaking change.
- `fias_region_guid` помечен устаревшим по спецификации: чтение вызывает
  `DeprecationWarning`, сериализация работает без предупреждений.

**Эндпоинты**

- `orders` — создание, изменение, удаление, получение (по UUID, номеру СДЭК
  и номеру клиента), заявки по заказу (`orders.intakes()`), клиентский возврат
  и отказ; ожидание завершения асинхронной задачи — `orders.wait()`
  и `client.wait_order()`.
- `calculator` — `tariff()`, `tariff_list()`, `tariff_and_service()`
  и `available_tariffs()` (`GET /v2/calculator/alltariffs`), ошибки расчёта
  через `errors_of()`.
- `delivery_points` — офисы, ПВЗ и постаматы: `list()`, `paginate()`, `get()`,
  `by_polygon()`.
- `locations` — города и регионы (`cities()`, `regions()`, `paginate_cities()`,
  `paginate_regions()`), подсказки `suggest_cities()`, город по координатам
  `city_by_coordinates()`, почтовые индексы `postalcodes()`.
- `delivery_agreement` — договоры доставки и согласование интервалов:
  `create()`, `get()`, `get_envelope()`, `intervals()`,
  `estimated_intervals()`, `wait()`.
- `intakes` — заявки на курьерский забор: `create()`, `get()`,
  `get_envelope()`, `change_status()`, `delete()`, `available_days()`, `wait()`.
- `printing` — печатная форма и ШК-места: `waybill()` / `barcodes()` →
  `waybill_status()` / `barcode_status()` → `waybill_pdf()` / `barcode_pdf()`,
  сквозные `download_waybill()` и `download_barcodes()` отдают готовый PDF,
  а не UUID задачи.
- `webhooks` — все 10 типов подписок: `create()`, `list()`, `get()`,
  `get_envelope()`, `delete()`, `delete_all()`, `replace()`, `has_capacity()`
  и `is_limit_error()`. Лимит СДЭК — две активные подписки, отказ приходит
  как HTTP 400 с кодом `v2_too_many_webhooks`.
- `misc` — реверс (`reverse_availability()`), чеки, паспортные данные, реестры
  наложенного платежа, фото документов (`photo_ready_orders()`,
  `photo_archive()`), преалерты (`prealert_create()`, `prealert_get()`)
  и международные ограничения; escape hatch `misc.raw()` для ещё не описанных
  методов.
- `Paginator` с `async for` — пагинация без ручного `size`/`page`.
- Короткие алиасы разделов на клиенте: `tariffs`, `points`, `courier`,
  `agreements`, `handbook`; доступ к HTTP-слою через `client.http`.

**Вебхуки**

- Проверка подписи СДЭК и типизированный разбор событий (`cdekx.webhooks.security`,
  `cdekx.webhooks.events`).
- Модели `attributes` для каждого из 10 типов событий.
- ASGI-приёмник `cdekx.webhooks.asgi` (extra `webhooks` → `starlette`).

**Инструменты и материалы**

- `cdekx` — CLI-утилита для отладки (`cdekx --help`).
- 9 запускаемых примеров в `examples/` (расчёт тарифа, заказ, печать, ПВЗ,
  приём вебхуков, отслеживание, обработка ошибок, пакетные заказы,
  чеки и реверс).
- Документация в `docs/` (mkdocs + mkdocstrings), карта покрытия API —
  `docs/API_COVERAGE.md`, описание устройства — `docs/ARCHITECTURE.md`.
- `scripts/fetch_openapi.py` и `scripts/generate_from_openapi.py` — скачивание
  спецификации СДЭК и проверка дрейфа моделей (126 пар «схема → модель»);
  job `drift` в CI по расписанию и вручную.
- Unit-тесты с мокированием транспорта (`respx`), `mypy --strict`,
  покрытие веток; интеграционные тесты против `api.edu.cdek.ru` —
  по явному флагу `CDEKX_RUN_INTEGRATION=1`.

### Documentation

- README и сайт документации — на русском; исходный код библиотеки
  (докстринги, описания полей, сообщения об ошибках) и описание на странице
  PyPI — на английском. Английская версия README — `README.en.md`.

[Unreleased]: https://github.com/maisiq/cdekx/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/maisiq/cdekx/releases/tag/v0.1.0
