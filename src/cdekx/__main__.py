"""A small CLI for debugging and quickly sanity-checking an integration.

    cdekx --sandbox tariff --from 44 --to 270 --weight 1000
    cdekx --sandbox order --number TEST-1 ...
    cdekx --sandbox points --city-code 44 --type PVZ

The CLI is deliberately minimal: this is an SDK, not a utility. Still, being able
to poke the API without writing a script is very handy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="cdekx",
        description="Debugging CLI for the CDEK API (cdekx)",
    )
    parser.add_argument("--sandbox", action="store_true", help="use api.edu.cdek.ru")
    parser.add_argument("--client-id", default=None, help="account identifier")
    parser.add_argument("--client-secret", default=None, help="account password")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="print the result as JSON"
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="request timeout in seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    tariff = sub.add_parser("tariff", help="calculate delivery cost for a tariff")
    tariff.add_argument(
        "--from", dest="from_code", type=int, required=True, help="origin city code"
    )
    tariff.add_argument(
        "--to", dest="to_code", type=int, required=True, help="destination city code"
    )
    tariff.add_argument("--weight", type=int, default=1000, help="weight in grams")
    tariff.add_argument("--tariff-code", type=int, default=None, help="tariff code")

    points = sub.add_parser("points", help="list pickup points")
    points.add_argument("--city-code", type=int, default=None)
    points.add_argument("--type", dest="point_type", default="ALL")
    points.add_argument("--limit", type=int, default=10)

    city = sub.add_parser("city", help="look up a city by name")
    city.add_argument("name")
    city.add_argument("--country", default=None, help="ISO 3166-1 alpha-2 country code")

    order = sub.add_parser("order", help="order details by UUID")
    order.add_argument("uuid")

    by_number = sub.add_parser("order-by-number", help="order details by CDEK number")
    by_number.add_argument("number")

    sub.add_parser("tariffs", help="list tariffs available under the contract")

    sub.add_parser("token", help="obtain an OAuth token (verifies the credentials)")

    return parser


async def run(args: argparse.Namespace) -> int:
    """Run the command and return the exit code."""
    from cdekx import CdekClient

    client_id = args.client_id or os.getenv("CDEKX_CLIENT_ID") or os.getenv("CDEK_CLIENT_ID")
    client_secret = (
        args.client_secret or os.getenv("CDEKX_CLIENT_SECRET") or os.getenv("CDEK_CLIENT_SECRET")
    )

    client: CdekClient
    if args.sandbox and not client_id:
        client = CdekClient.sandbox()
    else:
        client = CdekClient(client_id, client_secret, sandbox=args.sandbox)

    async with client:
        result: Any
        if args.command == "token":
            auth = getattr(client.http, "_auth", None)
            transport = getattr(client.http, "_client", None)
            if auth is None or transport is None:
                raise ValueError("the client was created without an auth provider")
            token = str(await auth.get_token(transport) or "")
            result = {"access_token": f"{token[:8]}…", "length": len(token)}
        elif args.command == "tariff":
            from cdekx.models import CalculatorLocation, CalculatorPackage, TariffRequest
            from cdekx.types.enums import Currency

            request = TariffRequest(
                tariff_code=args.tariff_code,
                from_location=CalculatorLocation(code=args.from_code),
                to_location=CalculatorLocation(code=args.to_code),
                packages=[CalculatorPackage(weight=args.weight)],
                currency=Currency.RUB,
                lang="rus",
            )
            response = await client.calculator.tariff(request)
            result = response.to_api()
            if response.has_errors:
                result["_errors"] = response.errors
        elif args.command == "points":
            from cdekx.models import DeliveryPointFilter

            points_list = await client.delivery_points.list(
                DeliveryPointFilter(city_code=args.city_code, type=args.point_type)
            )
            result = [p.to_api() for p in points_list[: args.limit]]
        elif args.command == "tariffs":
            available = await client.calculator.available_tariffs(lang="rus")
            result = {
                "count": len(available.tariff_codes),
                "tariff_codes": available.all_tariff_codes()[:200],
            }
        elif args.command == "city":
            suggestions = await client.locations.suggest_cities(
                args.name, country_code=args.country
            )
            result = [s.to_api() for s in suggestions]
        elif args.command == "order":
            order_info = await client.orders.get(args.uuid)
            result = order_info.to_api()
        elif args.command == "order-by-number":
            order_info = await client.orders.get_by_number(args.number)
            result = order_info.to_api()
        else:  # pragma: no cover - guarded by argparse
            raise ValueError(f"unknown command: {args.command}")

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(args.command, result)
    return 0


def _print_human(command: str, result: Any) -> None:
    """Human-readable output for the common commands."""
    if command == "tariff" and isinstance(result, dict):
        print(
            f"cost: {result.get('delivery_sum')} {result.get('currency')}, "
            f"delivery time {result.get('period_min')}-{result.get('period_max')} business days, "
            f"chargeable weight {result.get('weight_calc')} g"
        )
        if result.get("_errors"):
            print("calculation errors:", result["_errors"])
    elif command == "tariffs" and isinstance(result, dict):
        print(f"tariffs available: {result.get('count')}")
        print(f"codes: {result.get('tariff_codes')}")
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                print(json.dumps(item, ensure_ascii=False, default=str)[:200])
            else:
                print(item)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    """Console entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
