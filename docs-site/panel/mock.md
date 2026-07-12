# Мок-панель

`scripts/mock_panel.py` — встроенная заглушка Remnawave: точная имитация всех эндпоинтов, которые дёргает клиент бота. Позволяет пощупать весь стек — бота, кабинет, миниапп, фоновые синки — на машине, где нет реальной панели. Переход на живую панель потом — одна правка env.

## Запуск

Локально:

```bash
uvicorn scripts.mock_panel:app --port 3010
```

и в `.env`:

```bash
REMNAWAVE__BASE_URL=http://127.0.0.1:3010
```

В докере мок-панель — сервис `mockpanel` за compose-профилем `mock`:

```bash
COMPOSE_PROFILES=mock
REMNAWAVE__BASE_URL=http://mockpanel:3010
```

`install.sh` включает это сам, если при установке не указать URL панели (токен подставляется `mock-panel-token`; мок авторизацию не проверяет, подойдёт любой).

## Что внутри

- Версия панели — `2.8.4` (проходит probe минимальной версии, см. [Подключение](/panel/)).
- Два internal squad'а: `NL-AMS`, `DE-FRA`.
- Три ноды: `NL-AMS-1`, `DE-FRA-1`, `FI-HEL-1` — со стабильной идентичностью и «живыми» плавающими метриками онлайна и трафика, чтобы дашборд выглядел настоящим.
- Пользователи создаются/меняются по-настоящему: состояние хранится в `scripts/mock_panel_state.json` рядом со скриптом и переживает рестарты. Удалил файл — чистый старт.
- `GET /sub/{short_id}` — фейковый подписочный эндпоинт (то, что клиент импортировал бы как конфиг). За прокси публичную базу подписочных ссылок задаёт переменная `MOCK_PANEL_PUBLIC_URL`.

## Эндпоинты

Ровно те, что использует клиент бота:

| Эндпоинт | Что имитирует |
|---|---|
| `GET /api/system/health` | Здоровье + версия |
| `POST /api/users` · `GET/PATCH/DELETE /api/users/{uuid}` | CRUD пользователей |
| `GET /api/users/by-telegram-id/{id}` | Поиск по Telegram ID |
| `POST /api/users/{uuid}/actions/{action}` | `enable` / `disable` / `reset-traffic` / `revoke` (ротирует ссылку) / `drop-connections` |
| `GET /api/hwid/devices/{uuid}` · `POST /api/hwid/devices/delete` | HWID-устройства (два демо-устройства) |
| `POST/GET /api/ip-control/fetch-users-ips/...` | Сбор онлайн-IP по ноде |
| `GET /api/internal-squads` | Сквады |
| `GET /api/nodes` | Ноды с метриками |

## Переход на реальную панель

Поменяй `REMNAWAVE__BASE_URL` и `REMNAWAVE__TOKEN` на реальные, убери `COMPOSE_PROFILES=mock` — больше ничего не требуется.

::: warning
Подписки, созданные против мок-панели, живут только в её JSON-состоянии — на реальную панель они не переносятся. Мок — для обкатки стека, не для продажи.
:::
