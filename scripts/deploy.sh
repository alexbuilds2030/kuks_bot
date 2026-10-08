#!/usr/bin/env bash
# Поднимает контейнеры, загружает в n8n токен и workflow, включает его и подписывает бота на webhook.
# Безопасно запускать повторно (после git pull — это и есть обновление).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
: "${DOMAIN:?нужен DOMAIN в .env}" "${MAX_BOT_TOKEN:?нужен MAX_BOT_TOKEN в .env}" "${N8N_ENCRYPTION_KEY:?нужен N8N_ENCRYPTION_KEY в .env}"

DC="docker compose"
$DC up -d
echo ">> Жду запуска n8n"
for i in $(seq 1 60); do
  $DC exec -T n8n wget -qO- http://localhost:5678/healthz >/dev/null 2>&1 && break
  sleep 2
done

echo ">> Токен MAX → credential n8n (хранится зашифрованным в n8n)"
printf '[{"id":"maxbot0000000001","name":"MAX Bot Token","type":"httpHeaderAuth","data":{"name":"Authorization","value":"%s"}}]' "$MAX_BOT_TOKEN" \
  | $DC exec -T n8n sh -c 'cat > /tmp/cred.json && n8n import:credentials --input=/tmp/cred.json; rm -f /tmp/cred.json'

echo ">> Workflow"
$DC exec -T n8n n8n import:workflow --input=/import/kuks_bot.workflow.json
$DC exec -T n8n n8n update:workflow --id=kuksbot0000000001 --active=true \
  || $DC exec -T n8n n8n publish:workflow --id=kuksbot0000000001   # на новых версиях n8n команда называется иначе
$DC restart n8n   # чтобы webhook зарегистрировался
sleep 10

echo ">> Подписываю бота на webhook https://${DOMAIN}/webhook/max-bot"
curl -fsS -X POST "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: ${MAX_BOT_TOKEN}" -H "Content-Type: application/json" \
  -d "{\"url\":\"https://${DOMAIN}/webhook/max-bot\",\"update_types\":[\"message_created\",\"message_callback\",\"bot_started\"]}" \
  && echo || echo "!! Подписка не удалась — проверьте токен и что https://${DOMAIN} открывается"

echo ">> Готово. Логи: docker compose logs -f n8n"
