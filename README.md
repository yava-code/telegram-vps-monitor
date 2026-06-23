# telegram-vps-monitor

pet project — телеграм бот для мониторинга VPS и прогресса своих скриптов/проектов.

сделал потому что надоело смотреть `htop` и `tail -f` с телефона.

## что умеет

- сервер: cpu, ram, disk, network, top processes
- systemd сервисы + tail логов + restart (admin)
- несколько проектов сразу (progress bar, eta)
- авто-алерты когда диск/ram/load или проект упал/закончился
- premium emoji если у владельца бота есть TG Premium (рандомные кастомные)

## быстрый старт

```bash
git clone https://github.com/yava-code/telegram-vps-monitor.git
cd telegram-vps-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# вписать BOT_TOKEN от @BotFather
python bot.py
```

## подключить свой проект

### вариант 1 — json файл (как polysniper)

в `config.json`:

```json
{
  "id": "myjob",
  "name": "My Job",
  "source": "file",
  "path": "/path/to/status.json"
}
```

формат status.json:

```json
{
  "status": "running",
  "step": "downloading",
  "progress": 42.5,
  "current_item": 85,
  "total_items": 200,
  "message": "batch 3",
  "started_at": 1710000000
}
```

### вариант 2 — http api

скопируй `client/report.py` и дергай:

```python
from report import push_status
push_status("myjob", step="train", current=10, total=100)
```

или curl:

```bash
curl -X POST http://127.0.0.1:8787/report \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"myjob","status":"running","progress":50}'
```

## premium emoji

бот может слать `<tg-emoji>` только если **у владельца бота** (аккаунт в BotFather) есть Telegram Premium.

1. `ENABLE_CUSTOM_EMOJI=true` в `.env`
2. добавь id кастомных эмодзи в `PREMIUM_EMOJI_POOL` (через @idstickerbot или форвард в userbot)
3. бот рандомит их в тексте и на inline-кнопках

## systemd

```bash
sudo cp systemd/telegramvps.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegramvps
```

## admin

в `config.json` → `admin_chat_ids`. админ может `/restart`, `/tail`, restart-кнопки.

## license

MIT — делай что хочешь, только токен не коммить
