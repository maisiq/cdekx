"""Пример 01: расчёт стоимости доставки.

Показывает:
* расчёт по конкретному тарифу;
* расчёт по всем доступным тарифам и выбор лучшего;
* работу с ошибками расчёта внутри HTTP 200.

Запуск::

    python 01_calculate_tariff.py
"""

from __future__ import annotations

import asyncio

from cdekx import CdekClient
from cdekx.models import CalculatorLocation, CalculatorPackage, TariffListRequest, TariffRequest
from cdekx.types.enums import Currency

MOSCOW = 44
YEKATERINBURG = 270


async def single_tariff(client: CdekClient) -> None:
    """Расчёт по одному тарифу."""
    result = await client.calculator.tariff(
        TariffRequest(
            tariff_code=136,  # «Экспресс лайт дверь-дверь»
            from_location=CalculatorLocation(code=MOSCOW),
            to_location=CalculatorLocation(code=YEKATERINBURG),
            packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
            currency=Currency.RUB,
            lang="rus",
        )
    )

    print(f"[один тариф] стоимость {result.delivery_sum} {result.currency}")
    print(
        f"  срок:     {result.period_min}–{result.period_max} раб. дн."
        f" ({result.calendar_min}–{result.calendar_max} календ.)"
    )
    print(f"  итого:    {result.total_sum} (с доп. услугами и НДС)")
    print(f"  вес:      {result.weight_calc} г")
    if result.delivery_date_range:
        print(f"  даты:     {result.delivery_date_range.min} … {result.delivery_date_range.max}")
    for service in result.services or []:
        print(f"  доп. услуга {service.code}: {service.sum}")
    for error in result.errors or []:
        print(f"  ! ошибка расчёта: {error}")


async def all_tariffs(client: CdekClient) -> None:
    """Расчёт по всем доступным тарифам договора."""
    result = await client.calculator.tariff_list(
        TariffListRequest(
            from_location=CalculatorLocation(code=MOSCOW),
            to_location=CalculatorLocation(code=YEKATERINBURG),
            packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
        )
    )

    viable = [t for t in result.tariff_codes if not t.has_errors]
    broken = [t for t in result.tariff_codes if t.has_errors]

    print(f"\n[все тарифы] доступно {len(viable)}, с ошибками расчёта {len(broken)}")
    for tariff in sorted(viable, key=lambda t: t.delivery_sum)[:5]:
        print(
            f"  {int(tariff.tariff_code):>4} {tariff.tariff_name:<45} "
            f"{tariff.delivery_sum:>8} ₽  {tariff.period_min}–{tariff.period_max} раб. дн."
        )

    cheapest = result.best()
    fastest = result.fastest()
    if cheapest:
        print(f"\n  дешевле всего: {cheapest.tariff_name} — {cheapest.delivery_sum} ₽")
    if fastest:
        print(f"  быстрее всего: {fastest.tariff_name} — {fastest.period_min} дн.")

    for tariff in broken:
        print(f"\n  тариф {tariff.tariff_code} не рассчитан: {tariff.extra}")


async def contract_tariffs(client: CdekClient) -> None:
    """Справочник тарифов, доступных по договору (GET /v2/calculator/alltariffs)."""
    available = await client.calculator.available_tariffs(lang="rus")

    print(f"\n[тарифы договора] позиций: {len(available.tariff_codes)}")
    print(f"  все коды: {available.all_tariff_codes()[:20]}…")
    for tariff in available.tariff_codes[:3]:
        print(
            f"  {tariff.tariff_name}: вес {tariff.weight_min}–{tariff.weight_max} г, "
            f"типы заказов {tariff.order_types or 'любые'}"
        )


async def main() -> None:
    """Точка входа примера."""
    async with CdekClient.sandbox() as client:
        await single_tariff(client)
        await all_tariffs(client)
        await contract_tariffs(client)


if __name__ == "__main__":
    asyncio.run(main())
