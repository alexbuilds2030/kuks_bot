> **Два варианта файла.** `n8n/kuks_bot.visual.workflow.json` — основной: по ноде на каждый шаг сценария, кнопки — связи между нодами
> (82 ноды). `n8n/kuks_bot.workflow.json` — компактный (8 нод, сценарий внутри одной ноды). Скрипты по умолчанию ставят visual;
> compact: `./scripts/import-to-existing.sh ИМЯ compact` или `WORKFLOW_VARIANT=compact` в `.env`.
> У обоих один webhook `/webhook/max-bot`: **включайте только один**, иначе n8n откажется активировать второй.
> В командах вручную ниже замените имя файла на `kuks_bot.visual.workflow.json`.

# Если n8n и Docker на сервере уже стоят

Новый стек и домен ставить не нужно: бот — это один файл `n8n/kuks_bot.workflow.json`. Нужно, чтобы ваш n8n был доступен из интернета по HTTPS (MAX шлёт на него webhook).

## Вариант А. Одной командой
```bash
git clone https://github.com/alexbuilds2030/kuks_bot.git && cd kuks_bot
docker ps --format '{{.Names}}'                      # узнать имя контейнера n8n
./scripts/import-to-existing.sh ИМЯ_КОНТЕЙНЕРА
```
Спросит токен бота (скрыт) и публичный адрес n8n. Загрузит токен и workflow, включит его, перезапустит n8n (несколько секунд простоя для других workflow) и подпишет бота на webhook.

## Вариант Б. Вручную через интерфейс n8n (без перезапуска)
1. Скачайте файл на свой компьютер: `scp root@IP:~/kuks_bot/n8n/kuks_bot.workflow.json .` (или откройте его на GitHub → Raw → скопируйте).
2. n8n → **Workflows → ⋯ → Import from File** (или вставьте JSON через Ctrl+V прямо на холст).
3. **Credentials → Create → Header Auth**: имя `MAX Bot Token`, Name `Authorization`, Value — токен бота. В нодах «Отправить сообщение» и «Ответ на нажатие» выберите этот credential.
4. Включите переключатель **Active**. Откройте ноду «MAX Webhook» и скопируйте **Production URL**.
5. Подпишите бота (команда с сервера или с любого компьютера):
```bash
curl -X POST https://platform-api.max.ru/subscriptions \
  -H "Authorization: ТОКЕН_БОТА" -H "Content-Type: application/json" \
  -d '{"url":"PRODUCTION_URL_ИЗ_ШАГА_4","update_types":["message_created","message_callback","bot_started"]}'
```
6. Уведомления о заявках: в ноде «Сценарий» впишите id в `adminIds` (например `'111,222'`) либо задайте `ADMIN_USER_IDS` в окружении n8n.

---

# Развёртывание на чистой Ubuntu (пошагово)

Проверено логикой скриптов; на реальной машине ещё не гонялось — если что-то упадёт, пришлите последние строки вывода.

## 0. Что подготовить заранее
| Что | Зачем |
|---|---|
| VPS с **Ubuntu 22.04 или 24.04**, 1 ГБ RAM и больше, публичный IP | сам сервер |
| **Домен**, A-запись → IP сервера (например `bot.example.com`) | HTTPS и webhook MAX. Проверка: `nslookup bot.example.com` должен показать IP сервера |
| Открытые порты **22, 80, 443** у провайдера (в панели хостинга, «Security groups»/«Firewall») | ssh, выпуск сертификата, приём webhook |
| **Токен бота MAX** (создаётся в @MasterBot) | бот |
| **Логин GitHub + personal access token (classic, scope `repo`)** | клон приватного репозитория |
| Ваш **user_id в MAX** (по желанию) | уведомления о заявках |

Корпоративный VPN для сервера не нужен, но сервер должен иметь выход в интернет. Если боту потребуется доступ к `*.alfaintra.net`, он с обычного VPS недоступен — тогда нужна машина внутри сети.

## 1. Подключиться к серверу
```bash
ssh root@IP_СЕРВЕРА
```
(или `ssh ваш_пользователь@IP_СЕРВЕРА`, если root отключён; тогда у пользователя должен быть sudo)

## 2. Поставить git и скачать проект
```bash
apt-get update && apt-get install -y git      # под обычным пользователем: sudo apt-get ...
git clone https://github.com/alexbuilds2030/kuks_bot.git
cd kuks_bot
```
Логин: `alexbuilds2030`, пароль: **token** (вводится в терминале, символы не отображаются).

## 3. Запустить установку
```bash
./scripts/setup.sh
```
Скрипт сам:
1. доустановит `curl`, `openssl`, `dnsutils` и **Docker**;
2. откроет порты в `ufw`, если он включён;
3. спросит домен, токен бота (ввод скрыт) и user_id, создаст `.env`;
4. проверит, что домен указывает на этот сервер (иначе остановится с подсказкой);
5. поднимет n8n и Caddy, загрузит токен и workflow, включит его, подпишет бота на webhook.

Занимает 3–5 минут.

## 4. Проверить
```bash
docker compose ps                    # n8n и caddy в состоянии Up
docker compose logs -f n8n           # логи (выход Ctrl+C)
curl -I https://bot.example.com      # должен ответить 200 и без ошибки сертификата
```
Потом напишите боту в MAX `/start`: через ~5 секунд придёт приветствие с вопросом про магазин.
Открыть редактор n8n: `https://bot.example.com` (при первом входе создайте учётную запись владельца).

## 5. Обновление и обслуживание
```bash
cd ~/kuks_bot && git pull && ./scripts/deploy.sh   # обновить сценарий
docker compose restart                              # перезапуск
docker compose down                                 # остановка (данные сохраняются)
```

## Если что-то не работает
| Симптом | Что делать |
|---|---|
| setup.sh: «Домен указывает на …» | поправить A-запись, подождать, запустить снова |
| `curl -I https://…` ошибка сертификата | `docker compose logs caddy`: чаще всего закрыт порт 80/443 у провайдера |
| Бот молчит | `docker compose logs -f n8n`; в n8n → Executions видно, приходят ли запросы от MAX |
| В скрипте «Подписка не удалась» | проверить токен в `.env`, затем `./scripts/deploy.sh` ещё раз |
| Нужно поменять токен/домен | править `.env`, затем `./scripts/deploy.sh` (ключ `N8N_ENCRYPTION_KEY` не менять) |
