"""Тесты прикладных хелперов."""

from __future__ import annotations

import pytest

from cdekx.models import Package
from cdekx.utils import (
    calc_volume_weight,
    grams_to_kg,
    kg_to_grams,
    normalize_phone,
    packages_summary,
)


@pytest.mark.parametrize(
    ("kg", "grams"),
    [(1, 1000), (0.5, 500), (2.345, 2345), (0, 0)],
)
def test_weight_conversion(kg: float, grams: int) -> None:
    assert kg_to_grams(kg) == grams
    assert grams_to_kg(grams) == kg


def test_volume_weight() -> None:
    # 30×20×10 / 5000 = 1.2 кг
    assert calc_volume_weight(30, 20, 10) == 1.2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+79001234567", "+79001234567"),
        ("89001234567", "+79001234567"),
        ("8 (900) 123-45-67", "+79001234567"),
        ("79001234567", "+79001234567"),
        ("0079001234567", "+79001234567"),
    ],
)
def test_normalize_phone_russian_numbers(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


def test_packages_summary() -> None:
    packages = [
        Package(number="1", weight=1000, length=30, width=20, height=10),
        Package(number="2", weight=5000, length=40, width=40, height=40),
    ]

    summary = packages_summary(packages)

    assert summary["count"] == 2
    assert summary["weight_g"] == 6000
    assert summary["volume_cm3"] == 6000 + 64000
    assert summary["volume_weight_g"] == 14000
    assert summary["chargeable_weight_g"] == 14000


def test_packages_summary_without_dimensions() -> None:
    summary = packages_summary([Package(number="1", weight=2000)])

    assert summary["volume_cm3"] == 0
    assert summary["volume_weight_g"] == 0
    assert summary["chargeable_weight_g"] == 2000
