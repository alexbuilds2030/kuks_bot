#!/usr/bin/env bash
# Первый запуск на чистой Ubuntu/Debian: ставит зависимости и Docker, создаёт .env, поднимает бота.
# Запускать под root или пользователем с sudo.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
command -v apt-get >/dev/null || { echo "!! Нужна Ubuntu/Debian (apt-get не найден)"; exit 1; }

echo ">> Ставлю базовые пакеты"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq curl git openssl ca-certificates dnsutils >/dev/null

if ! command -v docker >/dev/null; then
  echo ">> Ставлю Docker"
  curl -fsSL https://get.docker.com | $SUDO sh
fi
$SUDO systemctl enable --now docker >/dev/null 2>&1 || true

# Права на docker: если не root и нет доступа — перезапускаем скрипт через sudo
if ! docker info >/dev/null 2>&1; then
  if [ -n "$SUDO" ]; then
    echo ">> Нет прав на docker для $USER, запускаю дальше через sudo"
    exec sudo -E bash "$0" "$@"
  fi
  echo "!! Docker не отвечает"; exit 1
fi

# Файрвол: если ufw включён, открываем ssh, http, https
if command -v ufw >/dev/null && $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
  echo ">> Открываю порты 22, 80, 443 в ufw"
  $SUDO ufw allow 22/tcp >/dev/null; $SUDO ufw allow 80/tcp >/dev/null; $SUDO ufw allow 443/tcp >/dev/null
fi

if [ ! -f .env ]; then
  read -rp "Домен (A-запись должна указывать на этот сервер): " DOMAIN
  read -rsp "Токен бота MAX (ввод скрыт): " TOKEN; echo
  read -rp "user_id для уведомлений о заявках через запятую (Enter — пропустить): " ADMINS
  umask 077
  {
    echo "DOMAIN=${DOMAIN}"
    echo "MAX_BOT_TOKEN=${TOKEN}"
    echo "ADMIN_USER_IDS=${ADMINS}"
    echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 24)"
    echo "TZ=Europe/Moscow"
  } > .env
  echo ">> .env создан (в git не попадает)"
fi

set -a; . ./.env; set +a
IP=$(curl -fsS https://api.ipify.org || true)
DNS=$(dig +short "$DOMAIN" | tail -1 || true)
if [ -n "$IP" ] && [ "$DNS" != "$IP" ]; then
  echo "!! Домен $DOMAIN указывает на '${DNS:-ничего}', а IP этого сервера $IP."
  echo "   Без этого HTTPS-сертификат не выпустится. Поправьте A-запись, подождите 5-10 минут и запустите ./scripts/setup.sh снова."
  exit 1
fi

exec ./scripts/deploy.sh
