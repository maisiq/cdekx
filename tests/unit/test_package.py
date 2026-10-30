"""Тесты публичного API пакета: экспорт, ленивые подмодули, py.typed."""

from __future__ import annotations

from pathlib import Path

import cdekx


def test_public_exports_are_importable() -> None:
    for name in cdekx.__all__:
        assert hasattr(cdekx, name), f"cdekx.{name} объявлен в __all__, но недоступен"


def test_lazy_submodules_are_importable() -> None:
    assert cdekx.models.OrderCreate is not None
    assert cdekx.endpoints.OrdersEndpoint is not None
    assert cdekx.types.enums.TariffCode is not None
    assert cdekx.webhooks.parse_event is not None


def test_unknown_attribute_raises() -> None:
    import pytest

    with pytest.raises(AttributeError):
        _ = cdekx.does_not_exist


def test_dir_includes_lazy_submodules() -> None:
    listing = dir(cdekx)
    assert "models" in listing
    assert "webhooks" in listing
    assert "CdekClient" in listing


def test_version_is_exposed() -> None:
    assert cdekx.__version__

    version_file = Path(cdekx.__file__).parent / "_version.py"
    assert version_file.exists()
    assert cdekx.__version__ in version_file.read_text(encoding="utf-8")


def test_py_typed_marker_shipped() -> None:
    """PEP 561: без py.typed mypy у пользователей не увидит аннотации."""
    assert (Path(cdekx.__file__).parent / "py.typed").exists()


def test_exception_hierarchy_is_public() -> None:
    assert issubclass(cdekx.AuthError, cdekx.ApiError)
    assert issubclass(cdekx.NotFoundError, cdekx.ApiError)
    assert issubclass(cdekx.RateLimitError, cdekx.ApiError)
    assert issubclass(cdekx.ServerError, cdekx.ApiError)
    assert issubclass(cdekx.TimeoutExceeded, cdekx.TransportError)
    assert issubclass(cdekx.TransportError, cdekx.CdekxError)
    assert issubclass(cdekx.ConfigError, cdekx.CdekxError)


def test_optional_dependencies_are_not_imported_eagerly() -> None:
    """``cdekx`` не должен тянуть необязательные зависимости при импорте.

    Starlette нужен только для ``cdekx.webhooks.asgi``, pytest/mkdocs — тем более.
    """
    import subprocess
    import sys

    code = (
        "import sys, cdekx, cdekx.webhooks;"
        "mods = ['starlette', 'fastapi', 'aiohttp', 'loguru', 'pytest', 'mkdocs'];"
        "print([m for m in mods if m in sys.modules])"
    )
    output = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert output == "[]", f"при импорте cdekx подтянулись: {output}"


def test_public_annotations_resolve_at_runtime() -> None:
    """Аннотации публичного API должны резолвиться в рантайме.

    При ``from __future__ import annotations`` имя из-под ``TYPE_CHECKING``
    остаётся строкой, и ``typing.get_type_hints()`` /
    ``inspect.signature(eval_str=True)`` у пользователя падают с ``NameError``.
    Поэтому всё, что участвует в сигнатурах, импортируется в рантайме
    (см. также ignore TC001-TC003 в pyproject.toml).
    """
    import importlib
    import inspect
    import pkgutil
    import typing

    # models.common импортирует utils, поэтому Package в utils доступен только
    # под TYPE_CHECKING: рантайм-импорт дал бы цикл. Это единственное исключение.
    allowed = {("cdekx.utils", "packages_summary")}

    broken: list[str] = []
    checked = 0
    for mod in pkgutil.walk_packages(cdekx.__path__, "cdekx."):
        module = importlib.import_module(mod.name)
        for name, obj in vars(module).items():
            if name.startswith("_"):
                continue
            candidates = [obj] if inspect.isfunction(obj) or inspect.isclass(obj) else []
            if inspect.isclass(obj):
                candidates += [
                    fn for _, fn in inspect.getmembers(obj, predicate=inspect.isfunction)
                ]
            for fn in candidates:
                if getattr(fn, "__module__", None) != module.__name__:
                    continue
                qualname = getattr(fn, "__qualname__", name)
                try:
                    typing.get_type_hints(fn)
                except NameError:
                    if (module.__name__, qualname) not in allowed:
                        broken.append(f"{module.__name__}.{qualname}")
                else:
                    checked += 1

    assert checked > 300, f"проверено подозрительно мало аннотаций: {checked}"
    assert not broken, f"аннотации не резолвятся в рантайме: {broken}"


def test_pagination_has_no_module_level_cycle_with_endpoints() -> None:
    """``endpoints`` импортируют ``Paginator`` в рантайме — цикла быть не должно.

    ``pagination`` использует ``unwrap_entities`` из ``endpoints.base``, но
    импортирует его внутри метода: иначе ``endpoints.delivery -> pagination ->
    endpoints.__init__ -> endpoints.delivery`` замыкается.
    """
    import subprocess
    import sys

    code = (
        "from cdekx.pagination import Paginator;"
        "from cdekx.endpoints.delivery import DeliveryPointsEndpoint;"
        "from cdekx.endpoints.locations import LocationsEndpoint;"
        "import typing;"
        "typing.get_type_hints(DeliveryPointsEndpoint.paginate);"
        "typing.get_type_hints(LocationsEndpoint.paginate_cities);"
        "typing.get_type_hints(Paginator.__init__);"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "ok"
