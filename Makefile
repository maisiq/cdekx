# Makefile — типовые команды разработки. Работает и с uv, и с pip.
.DEFAULT_GOAL := help
UV := $(shell command -v uv 2>/dev/null)

ifeq ($(UV),)
  RUN := python -m
  SYNC := pip install -e ".[dev]"
else
  RUN := uv run
  SYNC := uv sync --group dev
endif

.PHONY: help install test lint format typecheck check cov bench integration docs build clean release

help: ## Показать справку
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Установить зависимости разработки
	$(SYNC)

test: ## Запустить unit-тесты
	$(RUN) pytest

cov: ## Тесты с покрытием
	$(RUN) pytest --cov=cdekx --cov-report=term-missing --cov-report=html

lint: ## Ruff: линтер
	$(RUN) ruff check .

format: ## Ruff: автоформатирование
	$(RUN) ruff format . && $(RUN) ruff check --fix .

typecheck: ## Mypy в строгом режиме
	$(RUN) mypy src

check: lint typecheck test ## Полный прогон проверок (как в CI)

bench: ## Замер стратегий разбора ответов (json.loads vs model_validate_json)
	$(RUN) python benchmarks/parse_benchmark.py

drift: ## Сверить модели с OpenAPI-спецификацией СДЭК
	$(RUN) python scripts/fetch_openapi.py api_v2_integration
	$(RUN) python scripts/generate_from_openapi.py .apidoc/api_v2_integration.json --drift

integration: ## Живые тесты против api.edu.cdek.ru
	CDEKX_RUN_INTEGRATION=1 $(RUN) pytest -m integration -v

docs: ## Собрать документацию (mkdocs)
	# PYTHONPATH=. — mkdocs 1.6+ не добавляет каталог конфига в sys.path,
	# а mkdocs.yml ссылается на локальный модуль mkdocs_hooks (slugify).
	PYTHONPATH=. $(RUN) mkdocs build --strict

serve-docs: ## Локальный сервер документации
	PYTHONPATH=. $(RUN) mkdocs serve

build: clean ## Собрать sdist + wheel
	$(RUN) python -m build

clean: ## Удалить артефакты сборки и кэши
	rm -rf build dist ./*.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache site htmlcov .coverage

release: ## Подсказка по релизу
	@echo "1) обновите src/cdekx/_version.py и CHANGELOG.md"
	@echo "2) git commit -am 'release: vX.Y.Z' && git tag vX.Y.Z && git push --follow-tags"
	@echo "3) публикацию выполнит .github/workflows/release.yml"
