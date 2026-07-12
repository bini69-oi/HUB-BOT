# Добавить модель БД

Postgres-first, но переносимо: тесты гоняют те же модели против aiosqlite. Схема слоёв и правила — в [Архитектуре](/dev/architecture).

## Шаги

1. **Модель.** Новый файл `src/infrastructure/database/models/<name>.py` — модель-на-файл, никаких «всё в models.py». Наследуйте `Base` (+ `IntPk`, `TimestampMixin` при нужде) из `src/infrastructure/database/base.py`:
   - деньги → `BigInt`, суффикс `_minor` (целые minor-units, ADR-0002);
   - даты → `AwareDateTime` (UTC-aware). Никаких наивных `datetime`;
   - JSON/массивы → `JsonB` (JSONB на Postgres, JSON на sqlite). UUID → `Uuid()`;
   - enum-колонки → `Enum(MyEnum, native_enum=False, length=N)` — переносимо, без PG-enum-типов;
   - partial-unique индексы → `Index(..., postgresql_where=text(...), sqlite_where=text(...))`.

2. **Регистрация.** Добавьте импорт и запись в `__all__` в `src/infrastructure/database/models/__init__.py` — иначе миграция и `create_all` не увидят таблицу.

3. **DAO.** Тонкий `class <Name>DAO(BaseDAO[<Model>])` в `src/infrastructure/database/dao/` (или в `catalog.py` для справочников). Доменные запросы — сюда же при необходимости.

4. **UnitOfWork.** Заведите атрибут в `src/infrastructure/database/uow.py`: `self.<name>s = <Name>DAO(session)`.

5. **Миграция.** При живом Postgres:

   ```bash
   make revision m="add <name>"   # автоген
   # глазами проверить диф миграции!
   make migrate
   ```

   Autogenerate против Postgres корректнее рукописной миграции — JSONB и partial-index он выводит правильно.

6. **Тест/фабрика.** При необходимости — helper в `tests/factories.py` и тест на новый флоу.

## Проверка

```bash
make check
```

::: warning Держите модель переносимой
Тесты создают схему через `Base.metadata.create_all` на aiosqlite. Кастомный тип без sqlite-варианта или PG-специфичная конструкция без `sqlite_where`-парного условия — и тесты отвалятся. Все нужные переносимые типы уже есть в `base.py`.
:::
