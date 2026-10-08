#!/usr/bin/env bash
# Загрузка бота в УЖЕ работающий n8n в Docker (без Caddy и нового стека).
# Использование: ./scripts/import-to-existing.sh <имя_контейнера_n8n> [visual|compact]
# visual (по умолчанию) — по ноде на шаг; compact — весь сценарий в одной ноде.
# Имя контейнера: docker ps --format '{{.Names}}'
set -euo pipefail
cd "$(dirname "$0")/.."
VARIANT="${2:-visual}"
if [ "$VARIANT" = "compact" ]; then WF_FILE=kuks_bot.workflow.json; WF_ID=kuksbot0000000001; else WF_FILE=kuks_bot.visual.workflow.json; WF_ID=kuksbotvisual0001; fi
C="${1:?Укажите имя контейнера n8n (docker ps --format '{{.Names}}')}"

read -rsp "Токен бота MAX (ввод скрыт): " TOKEN; echo
read -rp "Публичный HTTPS-адрес вашего n8n (например https://n8n.example.com): " URL
URL="${URL%/}"

echo ">> Токен → credential n8n"
printf '[{"id":"maxbot0000000001","name":"MAX Bot Token","type":"httpHeaderAuth","data":{"name":"Authorization","value":"%s"}}]' "$TOKEN" \
  | docker exec -i "$C" sh -c 'cat > /tmp/cred.json && n8n import:credentials --input=/tmp/cred.json; rm -f /tmp/cred.json'

echo ">> Workflow"
docker cp n8n/$WF_FILE "$C":/tmp/kuks_bot.workflow.json
docker exec "$C" n8n import:workflow --input=/tmp/kuks_bot.workflow.json
docker exec "$C" n8n update:workflow --id=$WF_ID --active=true \
  || docker exec "$C" n8n publish:workflow --id=$WF_ID
docker exec "$C" rm -f /tmp/kuks_bot.workflow.json

echo ">> Перезапускаю n8n (несколько секунд простоя), чтобы зарегистрировался webhook"
docker restart "$C" >/dev/null
sleep 15

echo ">> Подписываю бота на ${URL}/webhook/max-bot"
curl -fsS -X POST "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: ${TOKEN}" -H "Content-Type: application/json" \
  -d "{\"url\":\"${URL}/webhook/max-bot\",\"update_types\":[\"message_created\",\"message_callback\",\"bot_started\"]}" \
  && echo || echo "!! Подписка не удалась — проверьте токен и что ${URL} открывается снаружи"
echo ">> Готово. Уведомления о заявках: впишите user_id в ноде «Сценарий» (ADMIN)."
