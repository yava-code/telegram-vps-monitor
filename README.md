# telegram-vps-monitor

A small Telegram bot + local API for watching a VPS and the progress of your scripts, bots, and batch jobs — from your phone instead of `htop` and `tail -f`.

Pet / uni side project. MIT licensed.

## Features

- **Server**: CPU, RAM, disk, network, top processes
- **systemd**: service status, log tail, restart (admin only)
- **Multi-project**: progress bars, ETA, completion alerts
- **Auto-alerts**: disk/RAM/load thresholds, service down, job failed/finished
- **Premium emoji**: random custom emoji in messages and inline buttons (requires Telegram Premium on the **bot owner** account)

## Quick start

```bash
git clone https://github.com/yava-code/telegram-vps-monitor.git
cd telegram-vps-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set BOT_TOKEN from @BotFather
python bot.py
```

## Connect your project

Report **domain data** (pipeline step, counts, errors, business metrics) — not server CPU/RAM; the hub already tracks that.

### Option 1 — JSON file (legacy / simple)

Add to `config.json`:

```json
{
  "id": "myjob",
  "name": "My Job",
  "source": "file",
  "path": "/path/to/status.json"
}
```

`status.json` format:

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

Statuses: `idle`, `running`, `completed`, `failed`.

### Option 2 — HTTP API (recommended)

Copy `client/report.py` into your project:

```python
from report import push_status

push_status("myjob", step="train", current=10, total=100, message="epoch 2")
push_status("myjob", status="completed", verdict="OK", summary="rows=10k\nerrors=0")
```

Or curl:

```bash
curl -X POST http://127.0.0.1:8787/report \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"myjob","status":"running","step":"sync","message":"wallet 0xabc","records":1542}'
```

Register API-only projects in `config.json`:

```json
{"id": "myjob", "name": "My Job", "source": "api"}
```

API endpoints (localhost only):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | health check |
| GET | `/projects` | all project statuses |
| POST | `/report` | push status update |

## Premium emoji

Custom emoji works only if the **bot owner** (BotFather account) has Telegram Premium.

1. `ENABLE_CUSTOM_EMOJI=true` in `.env`
2. Add document IDs to `PREMIUM_EMOJI_POOL` (via @idstickerbot or forward to a userbot)
3. The bot picks random IDs for text (`<tg-emoji>`) and inline button icons

## systemd

```bash
sudo cp systemd/telegramvps.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegramvps
```

## Admin

Set `admin_chat_ids` in `config.json`. Admins get `/restart`, `/tail`, `/ps`, `/who`, and inline restart buttons.

## CI

GitHub Actions runs on push/PR: install deps + `py_compile` on all modules. No bot token required.

## License

MIT — do whatever, just don't commit your token.