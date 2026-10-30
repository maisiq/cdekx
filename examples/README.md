# Примеры использования cdekx

Готовые к запуску сценарии. Перед запуском задайте учётные данные:

```bash
cp ../.env.example ../.env      # и заполните
export CDEKX_CLIENT_ID=... CDEKX_CLIENT_SECRET=... CDEKX_ENVIRONMENT=sandbox

pip install -e ..
python 01_calculate_tariff.py
```

Без переменных окружения часть примеров использует учебную среду СДЭК
с публичными тестовыми ключами (`CdekClient.sandbox()`) — заказы там
не доставляются, но расчёты и справочники работают.

| Файл | Что показывает |
| --- | --- |
| `01_calculate_tariff.py` | расчёт по тарифу, по всем тарифам, тарифы договора |
| `02_create_order.py` | регистрация заказа, `ACCEPTED → SUCCESSFUL`, статусы, `related_entities` |
| `03_print_labels.py` | ШК места и квитанция: задача → ожидание → PDF |
| `04_delivery_points.py` | ПВЗ города, поиск в прямоугольнике координат, пагинация |
| `05_webhooks_receive.py` | приём вебхуков (ASGI-приложение на Starlette) |
| `06_track_status.py` | история статусов, причины задержек, поллинг |
| `07_error_handling.py` | разбор ошибок API и повтор при 429 |
| `08_batch_orders.py` | массовое создание заказов с ограничением нагрузки |
| `09_checks_and_reverse.py` | реверс, ограничения по ТН ВЭД, чеки, фото документов, преалерты |
