#!/usr/bin/env python3
"""Генератор черновиков pydantic-моделей из OpenAPI-спецификации СДЭК.

Зачем
-----
Портал apidoc.cdek.ru отдаёт полную OpenAPI-спецификацию. Держать модели
вручную — значит неизбежно от неё отставать. Скрипт помогает двумя способами:

1. **генерация черновиков** новых моделей — чтобы не печатать поля руками;
2. **проверка дрейфа** — сравнить поля существующих моделей ``cdekx``
   со спецификацией и увидеть, что СДЭК добавил/убрал.

Полная автогенерация сознательно не используется: сырые схемы СДЭК содержат
``additionalProperties``-мешки и нечитаемые имена, а ценность SDK — в
эргономике и докстрингах.

Использование
-------------
::

    # 1. скачать спецификацию с apidoc.cdek.ru (кнопка «Скачать OpenAPI»)
    python scripts/generate_from_openapi.py openapi.json --list

    # черновики моделей для конкретного пути
    python scripts/generate_from_openapi.py openapi.json --path /v2/orders

    # сравнить модели cdekx со спецификацией (дрейф контракта)
    python scripts/generate_from_openapi.py openapi.json --drift

Зависимости: только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: Соответствие JSON-типов и Python-типов для черновиков.
_JSON_TYPES = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "object": "dict[str, Any]",
}

#: Пути, которые библиотека уже покрывает (сверяется с docs/API_COVERAGE.md).
KNOWN_PATHS = (
    "/v2/oauth/token",
    "/v2/orders",
    "/v2/calculator/tariff",
    "/v2/calculator/tarifflist",
    "/v2/calculator/customsduty",
    "/v2/calculator/tariffs",
    "/v2/location/cities",
    "/v2/location/regions",
    "/v2/location/cities/suggest",
    "/v2/deliverypoints",
    "/v2/intakes",
    "/v2/print",
    "/v2/statuses",
    "/v2/webhooks",
    "/v2/handbook/services",
    "/v2/handbook/packagesizes",
    "/v2/handbook/countries",
)


def load_spec(path: Path) -> dict[str, Any]:
    """Загрузить OpenAPI-спецификацию (JSON)."""
    parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or "paths" not in parsed:
        raise ValueError("это не похоже на OpenAPI-документ: нет ключа 'paths'")
    spec: dict[str, Any] = parsed
    return spec


def python_type(schema: dict[str, Any], spec: dict[str, Any]) -> str:
    """Преобразовать JSON-Schema в аннотацию Python (черновую)."""
    if not schema:
        return "Any"

    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return pascal_case(name)

    nullable = schema.get("nullable") is True or "null" in _enum_of(schema, "type")
    base = _base_type(schema, spec)
    return f"{base} | None" if nullable else base


def _enum_of(schema: dict[str, Any], key: str) -> list[Any]:
    value = schema.get(key)
    return value if isinstance(value, list) else ([value] if value else [])


def _base_type(schema: dict[str, Any], spec: dict[str, Any]) -> str:
    kind = schema.get("type")
    if kind == "array":
        return f"list[{python_type(schema.get('items', {}), spec)}]"
    if kind == "string" and schema.get("format") in {"date-time", "date"}:
        return "CdekDateTime" if schema["format"] == "date-time" else "CdekDate"
    if "enum" in schema:
        return "str" if all(isinstance(v, str) for v in schema["enum"]) else "int"
    return _JSON_TYPES.get(kind or "", "Any")


def pascal_case(name: str) -> str:
    """``order_create_request`` → ``OrderCreateRequest``."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name)
    return "".join(part.capitalize() for part in cleaned.split("_") if part)


def resolve_schema(ref_or_schema: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Разыменовать ``$ref`` на один уровень."""
    if not isinstance(ref_or_schema, dict):
        return {}
    ref = ref_or_schema.get("$ref")
    if not ref or not ref.startswith("#/"):
        return ref_or_schema
    node: Any = spec
    for part in ref.lstrip("#/").split("/"):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    resolved: dict[str, Any] = node if isinstance(node, dict) else {}
    return resolved


def render_model(name: str, schema: dict[str, Any], spec: dict[str, Any]) -> str:
    """Отрендерить черновик pydantic-модели."""
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])

    lines = [
        f"class {pascal_case(name)}(CdekModel):",
        '    """TODO: описание по документации СДЭК."""',
        "",
    ]
    if not properties:
        lines.append("    pass")
        return "\n".join(lines)

    for field_name, raw in properties.items():
        field_schema = resolve_schema(raw, spec)
        annotation = python_type(field_schema, spec)
        description = str(field_schema.get("description", "")).replace('"', "'")
        if field_name in required:
            default = ""
        else:
            annotation = f"{annotation} | None" if "| None" not in annotation else annotation
            default = " = None"
        safe_name = field_name if field_name.isidentifier() else field_name + "_"
        desc = description[:80]
        if default:
            lines.append(
                f'    {safe_name}: {annotation} = Field(default=None, description="{desc}")'
            )
        else:
            lines.append(f'    {safe_name}: {annotation} = Field(description="{desc}")')
    return "\n".join(lines)


def iter_request_schemas(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Вернуть ``(path, method, schema)`` для тел запросов."""
    result: list[tuple[str, str, dict[str, Any]]] = []
    for path, operations in (spec.get("paths") or {}).items():
        for method, operation in (operations or {}).items():
            if method.lower() not in {"post", "put", "patch"}:
                continue
            body = (operation.get("requestBody") or {}).get("content", {})
            json_body = body.get("application/json") or {}
            schema = resolve_schema(json_body.get("schema"), spec)
            if schema:
                result.append((path, method.upper(), schema))
    return result


def cmd_list(spec: dict[str, Any]) -> int:
    """Напечатать все пути спецификации с пометкой покрытия."""
    paths = sorted((spec.get("paths") or {}).keys())
    print(f"Всего путей в спецификации: {len(paths)}\n")
    for path in paths:
        covered = any(path.startswith(known) for known in KNOWN_PATHS)
        mark = "✅" if covered else "⬜"
        operations = spec["paths"][path]
        http_methods = {"get", "post", "put", "patch", "delete"}
        methods = ",".join(m.upper() for m in operations if m.lower() in http_methods)
        print(f"{mark} {methods:<20} {path}")
    return 0


def cmd_path(spec: dict[str, Any], needle: str) -> int:
    """Сгенерировать черновики моделей для указанного пути."""
    found = False
    for path, method, schema in iter_request_schemas(spec):
        if needle not in path:
            continue
        found = True
        print(f"# {method} {path}")
        print(
            render_model(f"{pascal_case(path.strip('/').replace('/', '_'))}Request", schema, spec)
        )
        print()

    for name, schema in (spec.get("components", {}).get("schemas") or {}).items():
        if needle.lower() in name.lower():
            found = True
            print(f"# components.schemas.{name}")
            print(render_model(name, schema, spec))
            print()

    if not found:
        print(f"ничего не найдено по '{needle}'", file=sys.stderr)
        return 1
    return 0


#: Поля, добавленные в модели осознанно (их нет в схеме спецификации).
INTENTIONAL_EXTRA: dict[str, set[str]] = {
    "TariffCodeDto": {"errors"},
    # IntakeInfoEnvelope наследует ResponseEnvelope, а в схеме IntakeInfoDto
    # только {entity, requests}. related_entities — осознанный суперсет:
    # extra="allow" всё равно сохранил бы поле, если бы СДЭК его вернул.
    "IntakeInfoDto": {"related_entities"},
    # RequestInfo — общая модель для RequestDto (с warnings) и RequestInfoDto
    # (без warnings): суперсет намеренный, лишнее поле просто None.
    "RequestInfoDto": {"warnings"},
    # Location покрывает объединение четырёх схем локаций; kladr_region_code,
    # time_zone и payment_limit есть не во всех из них.
    "RequestFromLocationDto": {"kladr_region_code"},
    "RequestToLocationDto": {"kladr_region_code"},
    "ResponseFromLocationDto": {"kladr_region_code"},
    "ResponseToLocationDto": {"kladr_region_code"},
    "IntakeLocationDto": {"payment_limit", "time_zone"},
    # ErrorInfo хранит additional_code — он есть только в ErrorDto2.
    "ErrorDto1": {"additional_code"},
    "ErrorDto3": {"additional_code"},
    # FailedCall/RescheduledCall сохраняют устаревшее поле reason
    # (в спецификации его нет) — чтобы не ломать существующий код.
    "FailedCallResponseDto": {"reason"},
    "RescheduledCallResponseDto": {"reason"},
    # PackageAddServiceResponseDto — это {code} без parameter (только GRID_TREE)
    "PackageAddServiceResponseDto": {"parameter"},
}

#: Поля, которые в модели намеренно называются иначе, чем в спецификации.
#: Формат: ``{"Схема": {"поле_в_спеке": "поле_в_модели"}}``.
#:
#: ``RestrictionItemRequestDto.itemId`` — единственное поле API в camelCase
#: (помечено ``writeOnly``), но живой API его **не принимает**: на ``itemId``
#: ``POST /v2/international/package/restrictions`` отвечает
#: ``v2_field_is_empty: [packages[0].items[0].item_id] is empty``
#: (проверено на api.edu.cdek.ru). Модель отправляет ``item_id`` —
#: так же, как поле называется в ответе (``ItemHintDto.item_id``).
FIELD_NAME_OVERRIDES: dict[str, dict[str, str]] = {
    "RestrictionItemRequestDto": {"itemId": "item_id"},
}

#: Соответствие «схема в спецификации → модель в cdekx».
#: Имена намеренно разные (``OrderResponseDto`` → ``Order``), поэтому маппинг явный.
SCHEMA_TO_MODEL: dict[str, str] = {
    "OrderCreateRequestDto": "OrderCreate",
    "OrderUpdateRequestDto": "OrderUpdate",
    "OrderResponseDto": "Order",
    "OrderStatusDto": "OrderStatus",
    "ResponseDeliveryDetailDto": "DeliveryDetail",
    "PhoneDto": "Phone",
    "ContactDto": "Contact",
    "SenderContactDto": "Contact",
    "RecipientContactDto": "Contact",
    "MoneyDto": "Money",
    "DeliveryCostThresholdDto": "DeliveryCostThreshold",
    "SellerDto": "Seller",
    "SellerItemDto": "SellerItem",
    "PackageRequestDto": "Package",
    "PackageResponseDto": "PackageResponse",
    # доп. услуга упаковки ({code}) — подмножество Service (code + parameter)
    "PackageAddServiceResponseDto": "Service",
    "ItemRequestDto": "Item",
    "ItemResponseDto": "ItemResponse",
    # в спецификации у AdditionalService*Dto одинаковый набор полей:
    # в запросе значимы только code/parameter, остальное возвращается в ответе
    "AdditionalServiceResponseDto": "ServiceResponse",
    # Location покрывает объединение RequestFromLocationDto и LocationDto1
    # (kladr_region_code есть только в LocationDto1 — используется при изменении заказа)
    "LocationDto1": "Location",
    "CalculatorLocationDto": "CalculatorLocation",
    "CalcPackageRequestDto": "CalculatorPackage",
    "CalculatorRequestDto": "TariffRequest",
    "CalculatorResponseDto": "TariffCalculation",
    "CalculatorTariffListRequestDto": "TariffListRequest",
    "CalculatorTariffListResponseDto": "TariffListResponse",
    # TariffCodeItem дополнительно declares `errors` — осознанное расширение:
    # тарифы с ошибкой расчёта приходится отфильтровывать (has_errors)
    "TariffCodeDto": "TariffCodeItem",
    "CalculatorAvailableTariffsResponseTariffCodeDto": "AvailableTariff",
    "CalculatorAvailableTariffsResponseDto": "AvailableTariffsResponse",
    "CalculatorTariffWithServicesRequestDto": "TariffWithServicesRequest",
    "CalculatorTariffWithServicesResponseDto": "TariffWithService",
    "V2LocationCityDto": "City",
    "V2LocationCityByCoordinatesDto": "CityByCoordinates",
    "SuggestCityResponseDto": "SuggestCity",
    "RegionsResponseDto": "Region",
    # Реальный ответ GET /v2/location/postalcodes — PostcodesResponseDto
    # ({code, postal_codes: [string]}). Схема PostcodeDto ({code, postal_codes})
    # в спецификации не используется ни одним путём — намеренно не маппим.
    "PostcodesResponseDto": "Postcodes",
    "OfficeDto": "DeliveryPoint",
    "OfficeLocationDto": "OfficeLocation",
    "OfficeWorkTimeDto": "OfficeWorkTime",
    "OfficeWorkTimeExceptionDto": "OfficeWorkTimeException",
    "OfficeCellDimensionsDto": "OfficeCellDimensions",
    "OfficeImageDto": "OfficeImage",
    "ScheduleDto": "DeliveryAgreement",
    "ScheduleInfoDto": "DeliveryAgreementInfo",
    "IntakeDto": "Intake",
    "IntakeInfoResponseEntity": "IntakeInfo",
    "IntakeStatusDto": "IntakeStatus",
    "IntakeStatusPatchDto": "IntakeStatusPatch",
    "IntakeAvailableDaysRequestDto": "IntakeAvailableDaysRequest",
    "IntakeAvailableDaysResponseDto": "IntakeAvailableDays",
    "WaybillRequestDto": "WaybillCreate",
    "WaybillDto": "Waybill",
    "BarcodeRequestDto": "BarcodeCreate",
    "BarcodeDto": "Barcode",
    "PrintOrderDto": "PrintOrder",
    "PrintStatusDto": "PrintStatus",
    "WebhookDto": "Webhook",
    "WebhookResponseDto": "WebhookCreated",
    "RequestDto": "RequestInfo",
    "RelatedEntityDto": "RelatedEntity",
    "WarningDto": "ApiWarning",
    "ErrorDto2": "ErrorInfo",
    "EntityDto": "RootEntity",
    # --- прочее: чеки, паспорта, реестры, фото, преалерты, реверс, ограничения
    "CheckInfoDto": "CheckInfo",
    "CheckResponseDto": "CheckResponse",
    "PassportDto": "Passport",
    "PassportOrderDto": "PassportOrder",
    "PassportResponseDto": "PassportResponse",
    "RegistryDto": "Registry",
    "RegistryOrderDto": "RegistryOrder",
    "RegistriesResponseDto": "RegistriesResponse",
    "PhotoOrderDto": "PhotoOrder",
    "PhotoRequestDto": "PhotoRequest",
    "PhotoReadyOrderDto": "PhotoReadyOrder",
    "PhotoResponseDto": "PhotoResponse",
    "RegisterPrealertRequestDto": "PrealertCreate",
    "RegisterPrealertRequestDtoOrderDto": "PrealertOrder",
    "GetPrealertResponseDtoPrealertDto": "Prealert",
    "GetPrealertResponseDtoOrderDto": "PrealertOrderInfo",
    "GetPrealertResponseDtoPackageInfoDto": "PrealertPackageInfo",
    "RestrictionItemRequestDto": "RestrictionItem",
    "RestrictionPackageRequestDto": "RestrictionPackage",
    "RestrictionHintsRequestDto": "RestrictionRequest",
    "PackageHintDto": "PackageHint",
    "ItemHintDto": "ItemHint",
    "HintStatusDto": "HintStatus",
    "HintReasonDto": "HintReason",
    "RestrictionHintsResponseDto": "RestrictionHintsResponse",
    "ReverseValidateRequestDto": "ReverseValidateRequest",
    # ReverseLocation покрывает обе схемы: они различаются только тем, что у
    # to_location поле address обязательное (в модели оно опционально — см. docstring)
    "ReverseValidateRequestFromLocationDto": "ReverseLocation",
    "ReverseValidateRequestToLocationDto": "ReverseLocation",
    # ReverseContragent покрывает sender и recipient: наборы полей идентичны
    "ReverseValidateRequestSenderDto": "ReverseContragent",
    "ReverseValidateRequestRecipientDto": "ReverseContragent",
    "ReverseValidateRequestPhoneDto": "Phone",
    # конверты преалертов структурно совпадают с ResponseEnvelope[...]
    "RegisterPrealertResponseDto": "PrealertTaskEnvelope",
    "GetPrealertResponseDto": "PrealertEnvelope",
    "IntakeInfoDto": "IntakeInfoEnvelope",
    "IntakeChangeStatusResponseDto": "IntakeEnvelope",
    "IntakePackageDto": "IntakePackage",
    # --- алиасы: та же схема под другим именем используется в другом методе.
    # Отдельные модели не заводим — их покрывают общие (см. NOTICE и docs).
    "AccompanyingWaybillDto": "AccompanyingWaybill",
    # в AdditionalServiceRequestDto те же поля, что в AdditionalServiceResponseDto,
    # только часть помечена readOnly — их покрывает ServiceResponse
    "AdditionalServiceRequestDto": "ServiceResponse",
    "CallsResponseDto": "Calls",
    "DeliveryDateRangeDto": "DeliveryDateRange",
    "DeliveryProblemResponseDto": "DeliveryProblem",
    "FailedCallResponseDto": "FailedCall",
    "IntakeAvailableDaysLocationDto": "IntakeAvailableDaysLocation",
    "IntakeChangeStatusDto": "IntakeStatusChange",
    "IntakeChangeStatusResponseEntity": "RootEntity",
    "IntakeContactDto": "Contact",
    "IntakeLocationDto": "Location",
    "OrderDelayReason": "OrderDelayReason",
    "RescheduledCallResponseDto": "RescheduledCall",
    "RootEntityDto": "RootEntity",
    "ScheduleStatusDto": "DeliveryAgreementStatus",
    "SenderResponseContactDto": "Contact",
    "RecipientResponseContactDto": "Contact",
    "RequestFromLocationDto": "Location",
    "RequestToLocationDto": "Location",
    "ResponseFromLocationDto": "Location",
    "ResponseToLocationDto": "Location",
    "ResponseMoneyDto": "Money",
    # ErrorDto — форма ошибки OAuth ({error, error_description}), а не errors[]
    # бизнес-методов; отдельной модели для неё нет (разбор живёт в _auth.py)
    "ErrorDto1": "ErrorInfo",
    "ErrorDto3": "ErrorInfo",
    "RequestInfoDto": "RequestInfo",
    "ResponseDtoOrderResponseDto": "OrderEnvelope",
    "ResponseDtoRootEntityDto": "TaskEnvelope",
}


def cmd_drift(spec: dict[str, Any], *, strict: bool = False) -> int:
    """Сравнить поля моделей cdekx со схемами спецификации.

    Для каждой пары «схема → модель» печатает:
    * поля, которые есть в API, но отсутствуют в модели (стоит добавить);
    * поля модели, которых нет в схеме (возможно, устарели).

    Args:
        spec: загруженная OpenAPI-спецификация.
        strict: считать расхождения ошибкой (ненулевой код возврата) — для CI.
    """
    try:
        from cdekx import endpoints as cdekx_endpoints
        from cdekx import models as cdekx_models
    except ImportError:
        print("установите пакет: pip install -e .", file=sys.stderr)
        return 1

    schemas = spec.get("components", {}).get("schemas") or {}
    if not schemas:
        print("в спецификации нет components.schemas — сравнение недоступно", file=sys.stderr)
        return 1

    report: list[str] = []
    unmapped: list[str] = []
    checked = 0

    for schema_name, model_name in SCHEMA_TO_MODEL.items():
        schema = schemas.get(schema_name)
        if schema is None:
            report.append(f"! схема {schema_name} исчезла из спецификации")
            continue
        # конверты ответов объявлены в endpoints (OrderEnvelope, TaskEnvelope…),
        # сами сущности — в models; ищем в обоих модулях
        model = getattr(cdekx_models, model_name, None) or getattr(
            cdekx_endpoints, model_name, None
        )
        if model is None:
            report.append(f"! модель {model_name} не найдена (models/endpoints)")
            continue

        checked += 1
        renames = FIELD_NAME_OVERRIDES.get(schema_name, {})
        spec_fields = {renames.get(f, f) for f in (schema.get("properties") or {})}
        # поле с alias (например `item_id` → `itemId`) в API называется по алиасу,
        # поэтому сравниваем оба имени
        model_fields = {
            field_info.alias or field_name for field_name, field_info in model.model_fields.items()
        }
        missing = sorted(spec_fields - model_fields)
        extra = sorted(
            f
            for f in model_fields
            if f not in spec_fields and f not in INTENTIONAL_EXTRA.get(schema_name, set())
        )
        if missing:
            report.append(f"~ {schema_name} -> {model_name}: нет полей {missing}")
        if extra:
            report.append(f"+ {schema_name} -> {model_name}: лишние поля {extra}")

    unmapped = sorted(set(schemas) - set(SCHEMA_TO_MODEL))

    print(f"Проверено пар схема/модель: {checked} из {len(schemas)} схем в спецификации")
    if report:
        print(f"\nРасхождений: {len(report)}\n")
        for line in report:
            print(" ", line)
    else:
        print("\nРасхождений по полям не найдено")

    if unmapped:
        print(f"\nСхемы без модели в cdekx ({len(unmapped)}) — кандидаты на покрытие:")
        for name in unmapped:
            print(f"  - {name}")

    print("\nНапоминание: extra='allow' сохраняет неизвестные поля, поэтому")
    print("расхождение не ломает работу — но модель стоит дополнить.")
    return 1 if (strict and report) else 0


def main(argv: list[str] | None = None) -> int:
    """Точка входа скрипта."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", type=Path, help="путь к openapi.json из apidoc.cdek.ru")
    parser.add_argument("--list", action="store_true", help="список путей и покрытие")
    parser.add_argument("--path", help="сгенерировать черновики для пути (подстрока)")
    parser.add_argument(
        "--drift", action="store_true", help="сравнить модели cdekx со спецификацией"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="с --drift: ненулевой код возврата при расхождениях (для CI)",
    )
    args = parser.parse_args(argv)

    if not args.spec.exists():
        print(f"файл не найден: {args.spec}", file=sys.stderr)
        return 2

    spec = load_spec(args.spec)

    if args.drift:
        return cmd_drift(spec, strict=args.strict)
    if args.path:
        return cmd_path(spec, args.path)
    return cmd_list(spec)


if __name__ == "__main__":
    raise SystemExit(main())
