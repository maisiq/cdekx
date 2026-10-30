---
name: Ошибка
about: Что-то работает не так
title: ""
labels: bug
assignees: ""
---

## Что случилось

<!-- Кратко: ожидали X, получили Y -->

## Как воспроизвести

```python
# минимальный воспроизводимый пример
```

## Ответ СДЭК (если есть)

```json
{
  "errors": [ ... ]
}
```

Укажите `request_id` из исключения — он нужен для обращения в поддержку СДЭК:

```
<request_id>
```

## Окружение

- cdekx: `pip show cdekx | grep Version`
- Python: `python -V`
- ОС:
- Среда API: production / sandbox

## Дополнительно

- [ ] Проверил(а) [docs/API_COVERAGE.md](../../docs/API_COVERAGE.md): метод покрыт
- [ ] Включил(а) `logging.getLogger("cdekx").setLevel(logging.DEBUG)` и приложил(а) вывод
