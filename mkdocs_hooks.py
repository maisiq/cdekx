"""Хуки MkDocs для сборки документации ``cdekx``.

Единственная задача — юникод-aware slugify для якорей. Дефолтный slugify
Python-Markdown (`markdown.extensions.toc.slugify`) приводит заголовок к ASCII
через `unicodedata.normalize(...).encode('ascii', 'ignore')`, поэтому русские
заголовки теряют текст целиком: ``## Вебхуки`` → ``_1``, ``## Лицензия`` → ``_2``.
Ссылки вида ``recipes.md#вебхуки`` при этом не работают, а навигация по
документации становится невозможной.

Здесь заголовок сохраняется в lower-case с дефисами: ``## Вебхуки`` →
``#вебхуки``, ``## Быстрый старт`` → ``#быстрый-старт``.
"""

from __future__ import annotations

import re
import unicodedata

_SEPARATOR_RE = re.compile(r"[\s_]+")
_INVALID_RE = re.compile(r"[^\w\-]", re.UNICODE)
_DASHES_RE = re.compile(r"-{2,}")


def slugify(value: str, separator: str) -> str:
    """Преобразовать заголовок в якорь с сохранением кириллицы."""
    normalized = unicodedata.normalize("NFKC", value)
    lowered = normalized.casefold()
    spaced = _SEPARATOR_RE.sub(separator, lowered)
    cleaned = _INVALID_RE.sub("", spaced)
    return _DASHES_RE.sub(separator, cleaned).strip(separator)
