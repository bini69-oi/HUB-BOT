#!/usr/bin/env bash
# VPN-HUB BOT — safe one-command update.
#
#   cd HUB-BOT && ./scripts/update.sh
#
# Order matters so a broken update never loses data:
#   1. dump the DB into ./backups/  (rollback insurance)
#   2. git pull --ff-only           (never rewrites local history)
#   3. rebuild images + restart     (web runs alembic migrations on start)
#   4. wait for /health             (fail loudly with rollback instructions)
set -euo pipefail

say()  { printf "\033[1;32m==>\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31m ✗ %s\033[0m\n" "$*"; exit 1; }

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker/compose.prod.yml"
[ -f .env ] || fail ".env не найден — сначала установка: ./scripts/install.sh"

OLD_REV=$(git rev-parse --short HEAD)

# --- 1. backup ----------------------------------------------------------------
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="backups/pre-update-$STAMP.sql.gz"
DB_USER=$(grep '^DATABASE__USER=' .env | cut -d= -f2)
DB_NAME=$(grep '^DATABASE__NAME=' .env | cut -d= -f2)
say "Бэкап БД → $BACKUP"
$COMPOSE exec -T postgres pg_dump -U "${DB_USER:-vpn}" "${DB_NAME:-vpn}" | gzip > "$BACKUP" \
  || fail "бэкап не снялся — обновление отменено (стек запущен? $COMPOSE ps)"
[ -s "$BACKUP" ] || fail "бэкап пустой — обновление отменено"

# --- 2. pull ------------------------------------------------------------------
say "Забираю обновления (git pull --ff-only)…"
git pull --ff-only || fail "git pull не прошёл — есть локальные правки? (git stash, затем повторить)"
NEW_REV=$(git rev-parse --short HEAD)
if [ "$OLD_REV" = "$NEW_REV" ]; then
  say "Уже последняя версия ($NEW_REV) — пересобираю на всякий случай"
fi

# --- 3. rebuild + restart -------------------------------------------------------
say "Пересобираю и перезапускаю стек ($OLD_REV → $NEW_REV)…"
$COMPOSE up -d --build

# --- 4. health-gate -------------------------------------------------------------
say "Жду миграции и /health…"
for _ in $(seq 1 90); do
  if $COMPOSE exec -T web \
       python -c "import urllib.request as u; u.urlopen('http://localhost:8080/health', timeout=3)" \
       >/dev/null 2>&1; then
    say "Готово! Обновлено до $NEW_REV, бэкап: $BACKUP"
    exit 0
  fi
  sleep 2
done

printf "\033[1;31m ✗ web не поднялся после обновления.\033[0m\n"
echo
echo "  Логи:   $COMPOSE logs --tail 100 web"
echo "  Откат:  git checkout $OLD_REV && $COMPOSE up -d --build"
echo "  БД:     gunzip -c $BACKUP | $COMPOSE exec -T postgres psql -U ${DB_USER:-vpn} ${DB_NAME:-vpn}"
exit 1
