# Деплой на VPS (systemd)

Альтернатива [Docker-установке](/guide/install) для тех, кто хочет запускать процессы напрямую через systemd. Проверено на Ubuntu 24.04, 1 vCPU / 1 GB RAM (на 1 GB обязателен swap 2 GB).

## Раскладка на сервере

- `/opt/vpnshop/app` — код, `.venv`, `.env` с секретами, `admin/dist` (собранная SPA)
- `/opt/vpnshop/compose.dev.yml` — Postgres 16 + Redis 7 в docker, доступ только с localhost
- systemd-юниты, все с `MemoryMax` под размер RAM:

| Юнит | Что | Порт |
|---|---|---|
| `vpnshop-web` | uvicorn: admin API, cabinet API, вебхуки, статика | :8000 |
| `vpnshop-bot` | Telegram-бот (long polling) | — |
| `vpnshop-worker` | taskiq: рассылки, бэкапы, синк, обработка оплат | — |
| `vpnshop-scheduler` | taskiq: задачи по расписанию | — |
| `vpnshop-mockpanel` | мок-панель Remnawave | :3010 |

- nginx: 443 с сертификатом Let's Encrypt (авто-обновление certbot) → `/` на :8000, `/sub/` на :3010

Что где доступно после провижининга:

| Что | Где |
|---|---|
| Админ-кабинет | `https://your-domain/admin/` (логин/пароль — `ADMIN__USERNAME`/`ADMIN__PASSWORD` из `.env`) |
| Мини-аппа | `https://your-domain/app/` (превью тем: `?mock=1&variant=a..h&mode=dark`) |
| Admin API | `https://your-domain/api/admin/…` |
| Cabinet API | `https://your-domain/api/cabinet/…` |
| Ссылки подписки мок-панели | `https://your-domain/sub/<short>` |

## Деплой обновлений

С локальной машины, из корня репозитория:

```bash
./scripts/deploy.sh user@your-server https://your-domain
```

Что происходит по шагам:

1. SPA кабинета собирается локально (`npm run build --prefix admin`) — Node на сервере не нужен.
2. `rsync` рабочей копии в `/opt/vpnshop/app` — git на сервере не нужен; `.env`, `backups/`, `uploads/` не трогаются.
3. На сервере: `uv sync --frozen --no-dev` → `alembic upgrade head` → `systemctl restart vpnshop-*` → вывод статуса юнитов.
4. Health-check: скрипт ждёт до 90 секунд ответа 200 от `/admin/` и проверяет `/app/`. Домен — второй аргумент; без него шаг пропускается.

## Замена мок-панели на живую Remnawave

В `/opt/vpnshop/app/.env`:

```
REMNAWAVE__BASE_URL=https://panel.example.com
REMNAWAVE__TOKEN=<api token>
```

и `systemctl restart vpnshop-web vpnshop-worker vpnshop-bot`. Больше ничего не меняется — [мок](/panel/mock) реализует те же эндпоинты и схемы, что использует клиент панели.

## Логи

```bash
journalctl -u vpnshop-web -f      # api
journalctl -u vpnshop-bot -f      # бот
journalctl -u vpnshop-worker -f   # рассылки/бэкапы/синк
```

::: info
Скрипт [`update.sh`](/guide/update) — только для Docker-установки. В systemd-варианте обновление — всегда `deploy.sh` с локальной машины.
:::
