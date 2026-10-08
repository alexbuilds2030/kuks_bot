# Кукс-бот: перенос сценария Robochat в n8n

Бот поддержки магазинов (интернет, оборудование, 1С, Service Desk). Сценарий был в Robochat;
здесь он разобран из выгрузки страницы и собран в workflow для n8n (мессенджер MAX).

## Как это устроено
1. `parse_robochat.py` — читает сохранённый HTML/XML страницы редактора → `scenario.json` (шаги, кнопки, переходы).
2. `build_n8n.py` — собирает из `scenario.json` → `n8n/kuks_bot.workflow.json`.
3. В n8n: Webhook → разбор update → Code-нода «Сценарий» (движок, сценарий зашит внутри) → цикл: сообщение / пауза / ответ на нажатие.

## Установка на втором Mac
```bash
git clone <URL репозитория>
cd kuks_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Обновление: `git pull`.

## Пересборка workflow
```bash
python parse_robochat.py kuks.xml -o scenario.json   # выгрузку кладёте в папку проекта
python build_n8n.py
```

## Развёртывание на VPS (Ubuntu/Debian)
Полная пошаговая инструкция для чистой машины: [DEPLOY.md](DEPLOY.md).

Нужно: VPS с публичным IP и домен, A-запись которого указывает на этот IP (для HTTPS, без него MAX не пришлёт webhook).
```bash
git clone <URL репозитория> kuks_bot
cd kuks_bot
./scripts/setup.sh
```
Скрипт спросит домен, токен бота (ввод скрыт) и id для уведомлений, поставит Docker, поднимет n8n + Caddy,
загрузит workflow, включит его и подпишет бота на webhook. Токен остаётся только в `.env` на сервере.

Обновление сценария: `git pull && ./scripts/deploy.sh`. Логи: `docker compose logs -f n8n`.
Редактор n8n откроется на `https://<домен>` (при первом входе создайте учётную запись владельца).

## Что пока не сделано
- Картинки из сценария (в выгрузке есть только первые 4 из блока).
- Таймаут «нет ответа 23 ч» из стартового шага.
- Форматы запросов MAX заданы по памяти, по документации dev.max.ru не сверены.
