"""Скачать OpenAPI-спецификацию СДЭК (портал apidoc.cdek.ru берёт её отсюда)."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

SECTIONS = {
    "api_v2_integration": "Клиентский протокол интеграции с логистикой (основной)",
    "fulfillment": "Фулфилмент",
    "marketplace_integration": "Маркетплейсы",
    "customs_client_integration": "Таможенная логистика",
    "fourth_pl_protocol": "4PL",
}

BASE = "https://gateway.cdek.ru/api-cdek-docs/web/docs/merged?sectionId={section}"
OUT = Path(__file__).resolve().parent.parent / ".apidoc"


def fetch(section: str) -> bytes:
    """Скачать спецификацию секции."""
    url = BASE.format(section=section)
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data: bytes = response.read()
    return data


def main(argv: list[str]) -> int:
    """Точка входа."""
    OUT.mkdir(parents=True, exist_ok=True)
    sections = argv or list(SECTIONS)
    for section in sections:
        try:
            raw = fetch(section)
        except Exception as exc:
            print(f"[FAIL] {section}: {exc}")
            continue
        path = OUT / f"{section}.json"
        path.write_bytes(raw)
        try:
            data = json.loads(raw)
        except ValueError:
            print(f"[????] {section}: {len(raw)} bytes, не JSON: {raw[:120]!r}")
            continue
        info = data.get("info", {}) if isinstance(data, dict) else {}
        paths = data.get("paths", {}) if isinstance(data, dict) else {}
        print(
            f"[ OK ] {section}: {len(raw)} bytes, openapi={data.get('openapi')}, "
            f"paths={len(paths)}, title={info.get('title')!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
