"""Сгенерировать справочник E-кодов для сайта документации.

Источник истины — src/core/error_codes.py; страница пересобирается этим скриптом
(uv run python scripts/gen_error_docs.py), руками её не редактировать.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.error_codes import all_codes

OUT = Path(__file__).resolve().parent.parent / "docs-site" / "reference" / "error-codes.md"

RANGES = {
    1: "Система (1xxx)",
    2: "Доступ и данные (2xxx)",
    3: "Подписки и покупки (3xxx)",
    4: "Платежи (4xxx)",
    5: "Панель Remnawave (5xxx)",
    6: "Telegram Bot API (6xxx)",
    9: "Неклассифицированное (9xxx)",
}

HEADER = """\
# Коды ошибок

<!-- Эта страница генерируется из src/core/error_codes.py командой
     `uv run python scripts/gen_error_docs.py` — не редактируйте её руками. -->

Каждая ошибка в боте, кабинете и воркере получает код вида **`E5103-1a2b3c4d`**:

- **`5103`** — номер класса проблемы из таблиц ниже: по нему сразу видно, *что за*
  ошибка, ещё до чтения трейса;
- **`1a2b3c4d`** — отпечаток конкретного бага (стабилен между повторениями): по нему
  находится точный трейс на дашборде телеметрии.

Юзер видит код в сообщении «Что-то пошло не так», владелец — в JSON-ответах API
(`error_id`) и на [дашборде приёма ошибок](/features/telemetry). Повторения одного
бага дают один и тот же код целиком.

::: tip Как этим пользоваться
Юзер прислал код → первая половина говорит, куда смотреть (касса? панель? БД?),
вторая находит трейс на дашборде. Коды из «штатных» строк (например E3003 —
не хватило баланса) в телеметрию не шлются — юзер просто видит понятное сообщение.
:::
"""


def main() -> None:
    parts = [HEADER]
    by_range: dict[int, list] = {}
    for code in all_codes():
        by_range.setdefault(code.code // 1000, []).append(code)
    for key in sorted(by_range):
        parts.append(f"\n## {RANGES.get(key, f'{key}xxx')}\n")
        parts.append("| Код | Ошибка | Что случилось | Что делать |")
        parts.append("|---|---|---|---|")
        for c in by_range[key]:
            parts.append(f"| `E{c.code}` | **{c.title}** | {c.meaning} | {c.action} |")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"written: {OUT} ({len(all_codes())} codes)")


if __name__ == "__main__":
    main()
