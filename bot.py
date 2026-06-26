import asyncio
import html
import json
import os
import time

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import api_server
import emoji_layer as em
import feeds
import freebies
import formatters as fmt
import gitinfo
import keyboards as kb
import probes
import shellrun
import sslcheck
import store
import sysinfo as si
import watchurl
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


async def safe_answer(msg, text, **kwargs):
    try:
        await msg.answer(text, parse_mode="HTML", **kwargs)
    except TelegramBadRequest as e:
        if "DOCUMENT_INVALID" not in str(e):
            raise
        await msg.answer(em.strip_premium(text), parse_mode="HTML", **kwargs)


async def safe_send(bot, chat_id, text):
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except TelegramBadRequest as e:
        err = str(e)
        if "DOCUMENT_INVALID" in err or "can't parse entities" in err:
            await bot.send_message(chat_id, em.strip_premium(text), parse_mode="HTML")
            return
        raise
    except Exception:
        pass


async def notify_all(bot, text):
    for cid in store.load_chat_ids():
        await safe_send(bot, cid, text)


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

        snap = si.snapshot()
        disk = snap["disk_pct"]
        ram = snap["ram_pct"]
        load1 = snap["load1"]

        if disk >= thresholds.get("disk_pct", 85) and can_alert("disk"):
            await notify_all(bot, f"{em.html('⚠️')} disk / is {disk}%")
        if ram >= thresholds.get("ram_pct", 90) and can_alert("ram"):
            await notify_all(bot, f"{em.html('⚠️')} ram {ram}%")
        if load1 >= thresholds.get("load_1m", 4) and can_alert("load"):
            await notify_all(bot, f"{em.html('⚠️')} load {load1}")

        units = [s["unit"] for s in cfg.get("services", [])]
        svc_states = si.services_snapshot(units)
        for s in cfg.get("services", []):
            unit = s["unit"]
            active, _ = svc_states.get(unit, ("unknown", ""))
            key = f"svc:{unit}"
            old = st.get("services", {}).get(unit)
            if old and old == "active" and active != "active" and can_alert(key):
                await notify_all(bot, f"{em.html('❌')} service <b>{s.get('name', unit)}</b> is {active}")
            st.setdefault("services", {})[unit] = active

        store.save_state(st)
        await asyncio.sleep(15)


async def probe_loop():
    while True:
        plist = cfg.get("probes", [])
        probes.run_probes(plist)
        interval = plist[0].get("interval_sec", 60) if plist else 60
        await asyncio.sleep(interval)


async def watch_loop(bot):
    interval = cfg.get("watch_interval_sec", 300)
    while True:
        urls = cfg.get("watch_urls", [])
        if urls:
            _, changes = watchurl.check_all(urls)
            for ch in changes:
                if can_alert(f"watch:{ch['url']}"):
                    await notify_all(
                        bot,
                        f"{em.html('👁')} <b>{ch['name']}</b> page changed\n"
                        f"<a href=\"{ch['url']}\">open</a>",
                    )
        await asyncio.sleep(interval)


async def freebies_digest_loop(bot):
    while True:
        try:
            fb_cfg = cfg.get("freebies", {})
            if fb_cfg.get("enabled", True):
                st = store.load_state()
                if freebies.digest_due(cfg, st):
                    items, err = freebies.collect_all(cfg)
                    text = freebies.format_digest(items, cfg, err=err)
                    for chunk in freebies.split_messages(text):
                        await notify_all(bot, chunk)
                    st["freebies_last_date"] = freebies.today_key(cfg)
                    store.save_state(st)
        except Exception as e:
            print(f"freebies digest error: {e}")
        await asyncio.sleep(60)


async def feed_digest_loop(bot):
    hours = cfg.get("feed_digest_hours", 6)
    while True:
        feeds_cfg = cfg.get("feeds", [])
        if feeds_cfg:
            st = store.load_state()
            seen = set(st.get("feed_seen", []))
            fresh = feeds.new_items_since(feeds_cfg, seen)
            if fresh:
                had_seen = bool(seen)
                for _, _, key in fresh:
                    seen.add(key)
                st["feed_seen"] = list(seen)[-500:]
                store.save_state(st)
                if had_seen:
                    lines = [f"{em.html('📰')} <b>New feed items</b>\n"]
                    for name, it, key in fresh[:8]:
                        t = it["title"][:100]
                        link = it.get("link", "")
                        if link:
                            lines.append(f"<b>{name}</b>: <a href=\"{link}\">{t}</a>")
                        else:
                            lines.append(f"<b>{name}</b>: {t}")
                    if can_alert("feed_digest"):
                        await notify_all(bot, "\n".join(lines))
        await asyncio.sleep(hours * 3600)


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
    await safe_answer(msg, text, reply_markup=kb.main_menu())


async def cmd_help(msg: Message):
    lines = [
        f"{em.html('📖')} <b>commands</b>\n",
        "/start — меню",
        "/projects — список проектов",
        "/status &lt;id&gt; — детали",
        "/ping — жив ли бот",
        "/feeds — RSS дайджест",
        "/freebies — халява (игры + сервисы)",
    ]
    if is_admin(msg.chat.id):
        lines += [
            "",
            "<b>admin:</b>",
            "/restart &lt;unit&gt;",
            "/tail &lt;unit&gt; [n]",
            "/ps — top процессы",
            "/who — подписчики",
            "/run &lt;cmd&gt; — shell (admin)",
        ]
    await safe_answer(msg, "\n".join(lines))


async def cmd_ping(msg: Message):
    await safe_answer(msg, f"{em.html('🏓')} pong {int(time.time())}")


async def cmd_feeds(msg: Message):
    await safe_answer(msg, feeds.format_feeds(cfg.get("feeds", [])))


async def cmd_freebies(msg: Message):
    items, err = freebies.collect_all(cfg)
    text = freebies.format_digest(items, cfg, err=err)
    for chunk in freebies.split_messages(text):
        await safe_answer(msg, chunk)


async def cmd_projects(msg: Message):
    statuses = store.get_all_projects()
    text = fmt.fmt_project_list(cfg.get("projects", []), statuses)
    await safe_answer(msg, text, reply_markup=kb.projects_inline(cfg.get("projects", [])))


async def cmd_status(msg: Message):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("usage: /status polysniper")
        return
    pid = parts[1].strip()
    st = store.get_project(pid)
    text = fmt.fmt_project_detail(st, project_name(pid))
    await safe_answer(msg, text)


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
    await safe_answer(msg, fmt.fmt_top())


async def cmd_who(msg: Message):
    if not is_admin(msg.chat.id):
        return
    ids = store.load_chat_ids()
    await msg.answer(f"subscribers: <code>{ids}</code>", parse_mode="HTML")


async def cmd_run(msg: Message):
    if not is_admin(msg.chat.id):
        await msg.answer("admin only")
        return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer(
            "/run ls -la\n/run git -C /opt/telegramvps status\n"
            "cwd: " + cfg.get("shell", {}).get("cwd", "/opt")
        )
        return
    cmd = parts[1].strip()
    out, code = shellrun.run(cmd, msg.chat.id, cfg.get("shell", {}))
    text = (
        f"<b>$</b> <code>{html.escape(cmd[:200])}</code>\n"
        f"<b>exit</b> {code}\n\n<pre>{html.escape(out)}</pre>"
    )
    await safe_answer(msg, text[:4000])


async def on_text(msg: Message):
    t = (msg.text or "").strip()
    if t == "📦 Projects":
        await cmd_projects(msg)
    elif t == "🖥 Server":
        await safe_answer(msg, fmt.fmt_server())
    elif t == "📰 Feeds":
        await cmd_feeds(msg)
    elif t == "🎁 Freebies":
        await cmd_freebies(msg)
    elif t == "👁 Watch":
        await safe_answer(msg, watchurl.format_watch(cfg.get("watch_urls", [])))
    elif t == "🔒 SSL":
        await safe_answer(msg, sslcheck.format_ssl(cfg.get("ssl_domains", [])))
    elif t == "📂 Git":
        await safe_answer(msg, gitinfo.format_git(cfg.get("git_dirs", [])))
    elif t == "💾 Disk":
        await safe_answer(msg, fmt.fmt_disk())
    elif t == "🌐 Network":
        await safe_answer(msg, fmt.fmt_net())
    elif t == "📈 Top":
        await safe_answer(msg, fmt.fmt_top())
    elif t == "⚙️ Services":
        adm = is_admin(msg.chat.id)
        text = fmt.fmt_services(cfg.get("services", []))
        await safe_answer(msg, text, reply_markup=kb.services_inline(cfg.get("services", []), admin=adm))
    elif t == "📜 Logs":
        await msg.answer("pick service:", reply_markup=kb.logs_inline(cfg.get("services", [])))
    elif t == "🔔 Alerts":
        snap = si.snapshot()
        await safe_answer(
            msg,
            fmt.fmt_alerts(cfg.get("alert_thresholds", {}), snap["disk_pct"], snap["ram_pct"], snap["load1"]),
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
        await safe_answer(cq.message, fmt.fmt_project_detail(st, project_name(pid)))
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
        await safe_answer(cq.message, f"{em.html('🔄')} restarted <code>{unit}</code>")
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
    dp.message.register(cmd_feeds, Command("feeds"))
    dp.message.register(cmd_freebies, Command("freebies"))
    dp.message.register(cmd_projects, Command("projects"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_restart, Command("restart"))
    dp.message.register(cmd_tail, Command("tail"))
    dp.message.register(cmd_ps, Command("ps"))
    dp.message.register(cmd_who, Command("who"))
    dp.message.register(cmd_run, Command("run"))
    dp.message.register(on_text, F.text)
    dp.callback_query.register(on_callback)

    asyncio.create_task(alert_loop(bot))
    asyncio.create_task(probe_loop())
    asyncio.create_task(watch_loop(bot))
    asyncio.create_task(feed_digest_loop(bot))
    asyncio.create_task(freebies_digest_loop(bot))
    probes.run_probes(cfg.get("probes", []))
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