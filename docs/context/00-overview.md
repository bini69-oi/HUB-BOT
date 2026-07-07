# 00 — Overview / Обзор

> **Что это за файл.** `docs/context/` — это большой «контекст-массив» для нейросети и для людей:
> домен, потоки данных, платёжный пайплайн, мат-модель рефералки/промо и грабли.
> Прежде чем писать бота или миниаппу — прочитай эти файлы. Порядок: 00 → 01 → 02 → 03 → 04 → 07.

## Что мы строим

Чистый, хорошо организованный **фундамент («база», ядро)** для Telegram-бота + web-миниаппы,
которые продают VPN-подписки (VLESS/XTLS) и провижнят их на самохостовой панели **Remnawave**.

База = **строгая слоистая архитектура** + **широкий набор бизнес-фич**.
Базу пишем **до** хендлеров бота и UI миниаппы:
она даёт конфиг, модели БД, DAO, клиент панели, абстракцию платежей, бизнес-сервисы, DI,
фоновые задачи и i18n. Хендлеры и UI подключаются к ней позже.

## Стек (зафиксирован)

- **Python 3.12**, полностью async.
- **aiogram 3** — бот (пишется позже; в базе только FSM-хранилище/типы).
- **SQLAlchemy 2.0 (async)** + **Alembic** + **PostgreSQL** (asyncpg).
- **Redis** — FSM, кэш, распределённые локи, pending-referral, сессии.
- **taskiq** (+ taskiq-redis) — фоновые задачи (worker + scheduler).
- **Dishka** — DI, инжектится и в будущий aiogram-dispatcher, и в taskiq-worker.
- **FastAPI** — тонкий web-шов (вебхуки платежей/панели + health); cabinet/mini-app API — позже.
- **httpx** — клиент Remnawave и платёжных шлюзов.
- **Панель — только Remnawave** (версия ≥ 2.8.0, с probe возможностей).

## Наш выбор для базы

Четыре кольца, строгая структура + прагматизм:

- **core/** — framework-agnostic. pydantic-settings по concern'ам; enums; константы; исключения;
  Money (целые minor-units); i18n-loader; utils.
- **application/** — бизнес-ядро. Protocol'ы в `application/common` (UnitOfWork, per-aggregate DAO,
  RemnawaveClient, PaymentGateway, Notifier, EventBus, Translator). Сервис-классы с явными
  зависимостями (PricingService, PurchaseService, SubscriptionService, ReferralService,
  PromoService, NotificationService). Доменные события несут `(i18n_key, kwargs)`.
  Без церемонии «один Interactor = один файл»; держим композируемые методы сервисов,
  командный объект — только для платёжно-покупочного пайплайна.
- **infrastructure/** — конкретные адаптеры. SQLAlchemy DAO (generic base + per-aggregate),
  RemnawaveClient+Service, платёжные шлюзы, taskiq broker/tasks, Redis DAO, Dishka DI, backup, health.
- **web/** — тонкий FastAPI (вебхуки + health). Бот и cabinet API — позже, но швы готовы.

DI — Dishka: `Scope.APP` для SDK панели, брокера, gateway-factory; `Scope.REQUEST` для DAO,
UnitOfWork, сервисов. Контейнер инжектится и в aiogram, и в taskiq-worker, чтобы фоновые
джобы гоняли ту же бизнес-логику. Синтетический **SYSTEM**-актор (Role.SYSTEM, id -1) обходит
RBAC для вебхуков/воркеров/сидинга.

## Куда смотреть в базе

| Нужно | Файл(ы) базы |
|---|---|
| Конфиг/секреты | `src/core/config/` |
| Enums/деньги | `src/core/enums.py`, `src/core/money.py` |
| Контракты (интерфейсы) | `src/application/common/` |
| Бизнес-логика | `src/application/services/` |
| Модели БД | `src/infrastructure/database/models/` |
| Клиент/сервис панели | `src/infrastructure/remnawave/` |
| Платежи | `src/infrastructure/payments/` |
| Фоновые задачи | `src/infrastructure/taskiq/` |
| DI | `src/infrastructure/di/` |
| Вебхуки | `src/web/` |

