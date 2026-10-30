# cdekx

> A modern asynchronous client for the [CDEK API v2](https://apidoc.cdek.ru/) — an independent implementation based on the CDEK OpenAPI specification: typing, retries, pagination, webhooks.

[Русский](https://github.com/maisiq/cdekx/blob/master/README.md) | **English**

[![CI](https://github.com/maisiq/cdekx/actions/workflows/ci.yml/badge.svg)](https://github.com/maisiq/cdekx/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cdekx.svg)](https://pypi.org/project/cdekx/)
[![Python](https://img.shields.io/pypi/pyversions/cdekx.svg)](https://pypi.org/project/cdekx/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/maisiq/cdekx/blob/master/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

📖 **Full documentation:** [maisiq.github.io/cdekx](https://maisiq.github.io/cdekx/) —
quick start, recipes, the full API reference, architecture and the API coverage map.

**Status:** `0.1.0` — the transport, authorisation, models and endpoints are
**verified against the OpenAPI specification** of apidoc.cdek.ru (the
`api_v2_integration` section, 41 paths). Coverage map:
[`docs/API_COVERAGE.md`](https://github.com/maisiq/cdekx/blob/master/docs/API_COVERAGE.md).

> The source code of the library (docstrings, field descriptions, error
> messages) is in English. The
> [documentation site](https://maisiq.github.io/cdekx/) is written in Russian.

---

## Why `cdekx`

| Feature | What it gives you |
| --- | --- |
| A single `httpx.AsyncClient` for the whole client lifetime | connection pooling instead of a new HTTP session per request |
| `RetryPolicy`: exponential backoff + jitter | respects `Retry-After`, retries 401 after refreshing the token |
| `OAuth2ClientCredentials` with `asyncio.Lock` | one token for N concurrent requests, an expiry margin, a hook for an external cache |
| `ApiError` → `AuthError` / `NotFoundError` / `RateLimitError` / `ServerError` hierarchy | parsed `errors[]`, `request_id`, `retry_after` instead of a faceless `Exception` |
| `Paginator` + `async for` | pagination without manual `size=1000, page=0` |
| `orders.wait()` / `client.wait_order()` | API v2 is asynchronous: poll the task until `SUCCESSFUL`/`INVALID` with error parsing |
| `printing.waybill()` / `barcodes()` → `wait_*()` → `*_pdf()`, end-to-end `download_waybill()` / `download_barcodes()` | a print form as a ready PDF instead of a task UUID |
| All 10 webhook types + an `attributes` model for each + an ASGI receiver | signature verification and typed event parsing out of the box |
| Enums accept the known values **and** an arbitrary `int`/`str` | CDEK directories can grow without a breaking change; plus `calculator.available_tariffs()` |
| `ResponseEnvelope`: `entity` + `requests` (with `state`) + `related_entities` | the whole API response is exposed, nothing is lost |
| `phones: [{number, additional}]` as in `PhoneDto` | plain strings are coerced automatically |
| Standard `logging` (`cdekx`, `cdekx.http`, `cdekx.auth`) | zero configuration and no logging dependencies |
| Explicit `_get` / `_post` / `_put` / `_delete` | no `sys._getframe()` magic to detect the HTTP method |
| `httpx`: HTTP/1.1 + HTTP/2, a single API for sync/async | a transport that is easy to mock in tests |

### Conformance with the current specification

The models and method paths are verified against the apidoc.cdek.ru OpenAPI
specification (the `api_v2_integration` section, 41 paths). Where the old
documentation and third-party integrations diverge from the real API, `cdekx`
follows the specification:

- `PATCH /v2/orders` with the identifier in the body, not `PUT /v2/orders/{uuid}`;
- `GET /v2/orders` is a search for **one** order by number; there is no order list in the API;
- the state of an asynchronous task lives in `requests[].state`; there is no separate `GET /v2/statuses/{uuid}`;
- printing: a JSON request body, separate status paths and `…/{uuid}.pdf`;
- VAT rates `0/5/7/10/16/20/22`, not the outdated `0/10/20`.

Divergences are checked automatically: `scripts/fetch_openapi.py` downloads the
specification, `scripts/generate_from_openapi.py --drift` compares it with the code.

More: [`docs/ARCHITECTURE.md`](https://github.com/maisiq/cdekx/blob/master/docs/ARCHITECTURE.md)
and [`docs/API_COVERAGE.md`](https://github.com/maisiq/cdekx/blob/master/docs/API_COVERAGE.md).

## Installation

```bash
pip install cdekx                # core
pip install "cdekx[webhooks]"    # + webhook receiver (starlette)
pip install "cdekx[dev]"         # + tests, linters, documentation
```

Python 3.10+ is required.

## Quick start

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
                tariff_code=136,  # "Express light"
                from_location=CalculatorLocation(code=44),  # Moscow
                to_location=CalculatorLocation(code=270),  # Yekaterinburg
                packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
                currency=Currency.RUB,  # a numeric code from Appendix 14: RUB = 1
                lang="eng",
            )
        )
        # terms are in working days (period_*) and calendar days (calendar_*)
        print(tariff.delivery_sum, tariff.total_sum, tariff.period_min, tariff.period_max)
        print(tariff.delivery_date_range)  # predicted delivery dates


asyncio.run(main())
```

Credentials may be omitted — the client takes them from the environment
(`CDEKX_CLIENT_ID`, `CDEKX_CLIENT_SECRET`):

```python
client = CdekClient.from_env()
```

For the sandbox there is a ready constructor with the public CDEK test keys:

```python
client = CdekClient.sandbox()
```

### Creating an order

```python
from cdekx.models import Contact, Item, Location, Money, OrderCreate, Package
from cdekx.types.enums import OrderType, ServiceCode, TariffCode

order = OrderCreate(
    type=OrderType.E_COMMERCE,
    number="ORDER-0001",
    tariff_code=TariffCode.EXPRESS_LIGHT_DOOR_DOOR,
    from_location=Location(code=44, address="1 Lenina St."),
    to_location=Location(code=270, address="10 Mira St., apt. 5"),
    # phones is a list of {number, additional} objects; strings are coerced
    sender=Contact(name="Ivan Petrov", phones=["+79001234567"]),
    recipient=Contact(name="Maria Smirnova", phones=[{"number": "+79007654321"}]),
    packages=[
        Package(
            number="PKG-1",
            weight=1000,
            length=30,
            width=20,
            height=10,
            items=[
                Item(
                    name="Book",
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

# API v2 is asynchronous: POST answers 202 + the ACCEPTED state — that is the
# state of the request, not of the order. The order is created in the background
# in 200–500 ms (up to 60 s at peak load).
task = await client.orders.create(order)
envelope = await client.orders.wait(task.uuid, interval=3)  # → SUCCESSFUL

created = envelope.entity
print(created.cdek_number, created.status_code)
print(envelope.requests)  # state and errors of the asynchronous processing
print(envelope.related_entities)  # the reverse order, print forms
```

### Pickup points: exporting a city and searching nearby

```python
from cdekx.models import DeliveryPointFilter

async for point in client.delivery_points.paginate(
    DeliveryPointFilter(city_code=44, type="PVZ"), page_size=500
):
    print(point.code, point.location.address, point.status)

# "Near a point" is done in the API with a coordinate rectangle (byPolygons)
from cdekx.models import DeliveryPointPolygonFilter

points = await client.delivery_points.by_polygon(
    latitude_right_top=55.78,
    longitude_right_top=37.65,
    latitude_left_bottom=55.73,
    longitude_left_bottom=37.60,
    # byPolygons supports only: type, city_uuid, have_cashless,
    # have_cash, allowed_cod, is_dressing_room, weight_max, weight_min, lang
    filter=DeliveryPointPolygonFilter(type="PVZ"),
)
```

### Printing barcodes and waybills

```python
pdf = await client.printing.download_barcodes([order_uuid], format="A4")
open("barcodes.pdf", "wb").write(pdf)

# or step by step: task → waiting → download (.pdf requires authorisation)
task = await client.printing.waybill([order_uuid], copy_count=2)
ready = await client.printing.wait_waybill(task.uuid, timeout=120)
receipt = await client.printing.waybill_pdf(ready.uuid)
```

### Receiving webhooks (FastAPI)

```python
from cdekx.webhooks import WebhookEvent
from cdekx.webhooks.asgi import WebhookApp


async def on_event(event: WebhookEvent) -> None:
    if event.type == "ORDER_STATUS":
        attrs = event.attributes  # the typed OrderStatusAttributes model
        print(attrs.cdek_number, attrs.code)


webhook_app = WebhookApp(on_event=on_event, path_secret="long-random-secret")
app.mount("/webhooks/cdek", webhook_app.asgi)  # app is your FastAPI application
```

An account may have no more than two active subscriptions — CDEK answers the
third one with HTTP 400 and the `v2_too_many_webhooks` code
(`WebhooksEndpoint.is_limit_error(exc)`); `webhooks.replace(url, type)` helps to
move to a new URL. The OpenAPI specification has no such limit — it was
confirmed by measurement on `api.edu.cdek.ru`.

### Error handling

```python
from cdekx import ApiError, AuthError, NotFoundError, RateLimitError

try:
    order = await client.orders.get(uuid)
except NotFoundError:
    ...  # no such order
except RateLimitError as exc:
    await asyncio.sleep(exc.retry_after or 1)
except AuthError:
    ...  # a problem with the credentials
except ApiError as exc:
    logger.error("CDEK: %s (request_id=%s)", exc.errors, exc.request_id)
```

## Project layout

```
cdekx/
├── pyproject.toml            # metadata, dependencies, ruff/mypy/pytest
├── src/cdekx/
│   ├── client.py             # CdekClient — the entry point
│   ├── config.py             # ClientConfig / Settings (including from env)
│   ├── _http.py              # transport, timeouts, RetryPolicy
│   ├── _auth.py              # OAuth2 client credentials + token cache
│   ├── exceptions.py         # error hierarchy
│   ├── pagination.py         # Paginator (async for over pages)
│   ├── utils.py              # weight/volume/phones — applied helpers
│   ├── types/                # Environment, dates, ApiErrorDetail, enums
│   ├── models/               # pydantic models per API section
│   ├── endpoints/            # orders, calculator, locations, delivery,
│   │                         # delivery_agreement, intakes, printing,
│   │                         # webhooks, misc
│   └── webhooks/             # webhook events + the ASGI receiver
├── scripts/                  # fetch_openapi.py, generate_from_openapi.py
├── tests/                    # unit (respx) + integration (api.edu.cdek.ru)
├── docs/                     # ARCHITECTURE, API_COVERAGE, quickstart…
├── examples/                 # ready scenarios
└── .github/workflows/        # CI + publishing to PyPI
```

## Development

```bash
git clone https://github.com/maisiq/cdekx && cd cdekx
uv sync --group dev        # or: pip install -e ".[dev]"

uv run pytest              # tests
uv run ruff check .        # linter
uv run ruff format .       # formatting
uv run mypy src            # strict typing

CDEKX_RUN_INTEGRATION=1 CDEKX_CLIENT_ID=... CDEKX_CLIENT_SECRET=... \
    uv run pytest -m integration     # tests against the sandbox
```

## License

Apache-2.0 — see [LICENSE](https://github.com/maisiq/cdekx/blob/master/LICENSE) and [NOTICE](https://github.com/maisiq/cdekx/blob/master/NOTICE).

The library may be freely used in proprietary and commercial products, modified
and redistributed; the Apache-2.0 patent grant is included.

### Code provenance

`cdekx` is an **independent implementation** of the public CDEK API v2. The
models and method paths are built from the apidoc.cdek.ru OpenAPI specification
(the `api_v2_integration` section), which `scripts/fetch_openapi.py` and
`scripts/generate_from_openapi.py --drift` download and verify.

The source code of other CDEK clients was neither copied nor derived. What is
shared with any other CDEK integration is limited to the unprotectable facts
about the API itself: method paths, field names, data types and directory values
(tariff and additional service codes, statuses, currencies).
Details are in [NOTICE](https://github.com/maisiq/cdekx/blob/master/NOTICE) and
[`docs/ARCHITECTURE.md`](https://github.com/maisiq/cdekx/blob/master/docs/ARCHITECTURE.md#license).

## Useful links

- [cdekx documentation](https://maisiq.github.io/cdekx/) — quick start, recipes, API reference (client, models, exceptions, webhooks)
- [CDEK API documentation portal](https://apidoc.cdek.ru/) (also where the OpenAPI specification is downloaded)
- [CDEK personal account](https://lk.cdek.ru/) → the "Integration" section → "Create a key"
- [`docs/API_COVERAGE.md`](https://github.com/maisiq/cdekx/blob/master/docs/API_COVERAGE.md) — the API method coverage map
