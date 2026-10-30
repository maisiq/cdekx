"""Practical helpers that are commonly needed alongside the CDEK API.

These are conveniences rather than part of the wire protocol: unit conversion,
dimensional weight, phone number normalisation. Every function is pure and free
of side effects.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

# models.common импортирует utils, поэтому Package доступен только под
# TYPE_CHECKING: рантайм-импорт дал бы цикл. Аннотация строковая.
if TYPE_CHECKING:
    from .models.common import Package

__all__ = [
    "DIMENSIONAL_DIVISOR",
    "calc_volume_weight",
    "grams_to_kg",
    "kg_to_grams",
    "normalize_phone",
    "packages_summary",
]

#: Divisor for dimensional weight (the algorithm carriers use: L x W x H / 5000).
DIMENSIONAL_DIVISOR = 5000


def kg_to_grams(kg: float) -> int:
    """Kilograms to grams (the CDEK API takes weight in grams)."""
    return round(kg * 1000)


def grams_to_kg(grams: int) -> float:
    """Grams to kilograms."""
    return round(grams / 1000, 3)


def calc_volume_weight(
    length_cm: int, width_cm: int, height_cm: int, *, divisor: int = DIMENSIONAL_DIVISOR
) -> float:
    """Dimensional weight in kilograms, from dimensions in centimetres."""
    return round(length_cm * width_cm * height_cm / divisor / 1000 * 1000, 3)


def normalize_phone(phone: str, *, default_country_code: str = "7") -> str:
    """Normalise a phone number to the international ``+79001234567`` format.

    Useful before submitting an order: CDEK rejects numbers without a leading
    ``+`` and numbers in the domestic ``8 (900) 123-45-67`` form.
    """
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("8") and len(digits) == 11:
        digits = default_country_code + digits[1:]
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits.startswith("+"):
        digits = f"+{digits}" if digits.startswith(default_country_code) else digits
    return digits if digits.startswith("+") else f"+{digits}"


def packages_summary(packages: list[Package]) -> dict[str, float | int]:
    """Summarise a list of packages: total weight, volume and chargeable weight.

    Returns:
        A dict with the keys ``count``, ``weight_g``, ``volume_cm3``,
        ``volume_weight_g`` and ``chargeable_weight_g``.

    """
    weight_g = sum(p.weight for p in packages)
    volume_cm3 = sum((p.length or 0) * (p.width or 0) * (p.height or 0) for p in packages)
    volume_weight_g = int(volume_cm3 / DIMENSIONAL_DIVISOR * 1000) if volume_cm3 else 0
    return {
        "count": len(packages),
        "weight_g": weight_g,
        "volume_cm3": volume_cm3,
        "volume_weight_g": volume_weight_g,
        "chargeable_weight_g": max(weight_g, volume_weight_g),
    }
