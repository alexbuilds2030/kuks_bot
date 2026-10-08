#!/usr/bin/env bash
# Первый запуск на VPS (Ubuntu/Debian): ставит Docker, создаёт .env, поднимает бота.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null; then
  echo ">> Ставлю Docker"
  curl -fsSL https://get.docker.com | sh
fi

if [ ! -f .env ]; then
  cp .env.example .env
  read -rp "Домен (A-запись должна указывать на этот сервер): " DOMAIN
  read -rsp "Токен бота MAX (ввод скрыт): " TOKEN; echo
  read -rp "user_id для уведомлений о заявках через запятую (Enter — пропустить): " ADMINS
  KEY=$(openssl rand -hex 24)
  sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|; s|^MAX_BOT_TOKEN=.*|MAX_BOT_TOKEN=${TOKEN}|; s|^ADMIN_USER_IDS=.*|ADMIN_USER_IDS=${ADMINS}|; s|^N8N_ENCRYPTION_KEY=.*|N8N_ENCRYPTION_KEY=${KEY}|" .env
  chmod 600 .env
  echo ">> .env создан (в git не попадает)"
fi

exec ./scripts/deploy.sh
