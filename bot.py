import asyncio
import json
import os
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import api_server
import emoji_layer as em
import formatters as fmt
import keyboards as kb
import store
import sysinfo as si
import watcher
from watcher import sync_file_projects

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")

cfg = {}
alert_last = {}


def load_cfg():
    global cfg
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return cfg


def is_admin(chat_id):
    return chat_id in cfg.get("admin_chat_ids", [])


def project_name(pid):
    for p in cfg.get("projects", []):
        if p["id"] == pid:
            return p.get("name", pid)
    return pid


def service_by_unit(unit):
    for s in cfg.get("services", []):
        if s["unit"] == unit:
            return s
    return {"name": unit, "unit": unit}


def allowed_unit(unit):
    return any(s["unit"] == unit for s in cfg.get("services", []))


async def notify_all(bot, text):
    for cid in store.load_chat_ids():
        try:
            await bot.send_message(cid, text, parse_mode="HTML")
        except Exception:
            pass


def can_alert(key):
    cd = cfg.get("alert_cooldown_sec", 300)
    now = time.time()
    last = alert_last.get(key, 0)
    if now - last < cd:
        return False
    alert_last[key] = now
    return True


async def alert_loop(bot):
    st = store.load_state()
    thresholds = cfg.get("alert_thresholds", {})

    while True:
        statuses = store.get_all_projects()
        prev = st.get("projects", {})
        for pid, data in statuses.items():
            old = prev.get(pid, {}).get("status")
            new = data.get("status")
            if old != new and new in ("running", "completed", "failed"):
                name = project_name(pid)
                if new == "running":
                    msg = f"{em.html('🚀')} <b>{name}</b> started"
                else:
                    msg = fmt.fmt_project_detail(data, name)
                if can_alert(f"proj:{pid}:{new}"):
                    await notify_all(bot, msg)
            prev[pid] = {"status": new}
        st["projects"] = prev

        disk = si.disk_use_pct()
        ram = si.ram_use_pct()
        load1 = float(si.load_avg().split()[0]) if si.load_avg() != "n/a" else 0

        if disk >= thresholds.get("disk_pct", 85) and can_alert("disk"):
            await notify_all(bot, f"{em.html('⚠️')} disk / is {disk}%")
        if ram >= thresholds.get("ram_pct", 90) and can_alert("ram"):
            await notify_all(bot, f"{em.html('⚠️')} ram {ram}%")
        if load1 >= thresholds.get("load_1m", 4) and can_alert("load"):
            await notify_all(bot, f"{em.html('⚠️')} load {load1}")

        for s in cfg.get("services", []):
            unit = s["unit"]
            active, _ = si.service_status(unit)
            key = f"svc:{unit}"
            old = st.get("services", {}).get(unit)
            if old and old == "active" and active != "active" and can_alert(key):
                await notify_all(bot, f"{em.html('❌')} service <b>{s.get('name', unit)}</b> is {active}")
            st.setdefault("services", {})[unit] = active

        store.save_state(st)
        await asyncio.sleep(15)


async def cmd_start(msg: Message):
    ids = store.load_chat_ids()
    if msg.chat.id not in ids:
        ids.append(msg.chat.id)
        store.save_chat_ids(ids)

    prem = "ON" if em.enabled() else "off"
    text = (
        f"{em.html('👋')} <b>VPS Monitor</b>\n\n"
        f"сервер + проекты в одном боте\n"
        f"premium emoji: <code>{prem}</code>\n\n"
        f"кнопки снизу или /help"
    )
    await msg.answer(text, parse_mode="HTML", reply_markup=kb.main_menu())


async def cmd_help(msg: Message):
    lines = [
        f"{em.html('📖')} <b>commands</b>\n",
        "/start — меню",
        "/projects — список проектов",
        "/status &lt;id&gt; — детали",
        "/ping — жив ли бот",
    ]
    if is_admin(msg.chat.id):
        lines += [
            "",
            "<b>admin:</b>",
            "/restart &lt;unit&gt;",
            "/tail &lt;unit&gt; [n]",
            "/ps — top процессы",
            "/who — подписчики",
        ]
    await msg.answer("\n".join(lines), parse_mode="HTML")


async def cmd_ping(msg: Message):
    await msg.answer(f"{em.html('🏓')} pong {int(time.time())}", parse_mode="HTML")


async def cmd_projects(msg: Message):
    statuses = store.get_all_projects()
    text = fmt.fmt_project_list(cfg.get("projects", []), statuses)
    await msg.answer(text, parse_mode="HTML", reply_markup=kb.projects_inline(cfg.get("projects", [])))


async def cmd_status(msg: Message):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("usage: /status polysniper")
        return
    pid = parts[1].strip()
    st = store.get_project(pid)
    text = fmt.fmt_project_detail(st, project_name(pid))
    await msg.answer(text, parse_mode="HTML")


async def cmd_restart(msg: Message):
    if not is_admin(msg.chat.id):
        await msg.answer("nope")
        return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("/restart reviewbot.service")
        return
    unit = parts[1].strip()
    if not allowed_unit(unit):
        await msg.answer("unit not in whitelist")
        return
    out = si.restart_service(unit)
    await msg.answer(f"restart {unit}\n<pre>{out or 'ok'}</pre>", parse_mode="HTML")


async def cmd_tail(msg: Message):
    if not is_admin(msg.chat.id):
        await msg.answer("nope")
        return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await msg.answer("/tail reviewbot.service 30")
        return
    unit = parts[1]
    lines = 20
    if len(parts) > 2:
        try:
            lines = int(parts[2])
        except ValueError:
            pass
    if not allowed_unit(unit):
        await msg.answer("unit not in whitelist")
        return
    log = si.tail_journal(unit, lines)[:3800]
    await msg.answer(f"<pre>{log}</pre>", parse_mode="HTML")


async def cmd_ps(msg: Message):
    if not is_admin(msg.chat.id):
        return
    await msg.answer(fmt.fmt_top(), parse_mode="HTML")


async def cmd_who(msg: Message):
    if not is_admin(msg.chat.id):
        return
    ids = store.load_chat_ids()
    await msg.answer(f"subscribers: <code>{ids}</code>", parse_mode="HTML")


async def on_text(msg: Message):
    t = (msg.text or "").strip()
    if t == "📦 Projects":
        await cmd_projects(msg)
    elif t == "🖥 Server":
        await msg.answer(fmt.fmt_server(), parse_mode="HTML")
    elif t == "💾 Disk":
        await msg.answer(fmt.fmt_disk(), parse_mode="HTML")
    elif t == "🌐 Network":
        await msg.answer(fmt.fmt_net(), parse_mode="HTML")
    elif t == "📈 Top":
        await msg.answer(fmt.fmt_top(), parse_mode="HTML")
    elif t == "⚙️ Services":
        adm = is_admin(msg.chat.id)
        text = fmt.fmt_services(cfg.get("services", []))
        await msg.answer(text, parse_mode="HTML", reply_markup=kb.services_inline(cfg.get("services", []), admin=adm))
    elif t == "📜 Logs":
        await msg.answer("pick service:", reply_markup=kb.logs_inline(cfg.get("services", [])))
    elif t == "🔔 Alerts":
        load1 = si.load_avg().split()[0] if si.load_avg() != "n/a" else "?"
        await msg.answer(
            fmt.fmt_alerts(cfg.get("alert_thresholds", {}), si.disk_use_pct(), si.ram_use_pct(), load1),
            parse_mode="HTML",
        )
    else:
        await msg.answer("use buttons or /help", reply_markup=kb.main_menu())


async def on_callback(cq: CallbackQuery, bot: Bot):
    data = cq.data or ""
    if data == "noop":
        await cq.answer()
        return
    if data.startswith("refresh:"):
        kind = data.split(":", 1)[1]
        if kind == "projects":
            sync_file_projects(cfg.get("projects", []))
            statuses = store.get_all_projects()
            await cq.message.edit_text(
                fmt.fmt_project_list(cfg.get("projects", []), statuses),
                parse_mode="HTML",
                reply_markup=kb.projects_inline(cfg.get("projects", [])),
            )
        elif kind == "services":
            adm = is_admin(cq.from_user.id)
            await cq.message.edit_text(
                fmt.fmt_services(cfg.get("services", [])),
                parse_mode="HTML",
                reply_markup=kb.services_inline(cfg.get("services", []), admin=adm),
            )
        await cq.answer("ok")
        return
    if data.startswith("proj:"):
        pid = data.split(":", 1)[1]
        st = store.get_project(pid)
        await cq.message.answer(fmt.fmt_project_detail(st, project_name(pid)), parse_mode="HTML")
        await cq.answer()
        return
    if data.startswith("log:"):
        unit = data.split(":", 1)[1]
        if not allowed_unit(unit):
            await cq.answer("nope")
            return
        log = si.tail_journal(unit, 25)[:3800]
        await cq.message.answer(f"<pre>{log}</pre>", parse_mode="HTML")
        await cq.answer()
        return
    if data.startswith("restart:"):
        if not is_admin(cq.from_user.id):
            await cq.answer("admin only")
            return
        unit = data.split(":", 1)[1]
        if not allowed_unit(unit):
            await cq.answer("not allowed")
            return
        si.restart_service(unit)
        await cq.answer(f"restarted {unit}")
        await cq.message.answer(f"{em.html('🔄')} restarted <code>{unit}</code>", parse_mode="HTML")
        return
    await cq.answer()


async def main():
    load_cfg()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN missing in .env")

    # migrate chat ids from polysniper if empty
    if not store.load_chat_ids():
        old = "/opt/polysniper/data/tg_chat_ids.json"
        if os.path.exists(old):
            with open(old) as f:
                store.save_chat_ids(json.load(f))

    sync_file_projects(cfg.get("projects", []))
    api_server.start_api(cfg.get("api_port", 8787))
    watcher.start_file_watcher(cfg.get("projects", []))

    bot = Bot(token)
    dp = Dispatcher()

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_ping, Command("ping"))
    dp.message.register(cmd_projects, Command("projects"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_restart, Command("restart"))
    dp.message.register(cmd_tail, Command("tail"))
    dp.message.register(cmd_ps, Command("ps"))
    dp.message.register(cmd_who, Command("who"))
    dp.message.register(on_text, F.text)
    dp.callback_query.register(on_callback)

    asyncio.create_task(alert_loop(bot))
    print("telegramvps bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    # load .env manually (no python-dotenv dep)
    env_path = os.path.join(BASE, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    asyncio.run(main())