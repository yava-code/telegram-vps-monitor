from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import emoji_layer as em


def _ib(text, data):
    kwargs = {"text": text, "callback_data": data}
    eid = em.btn_id()
    if eid:
        kwargs["icon_custom_emoji_id"] = eid
    return InlineKeyboardButton(**kwargs)


def main_menu():
    rows = [
        [KeyboardButton(text="📦 Projects"), KeyboardButton(text="🖥 Server")],
        [KeyboardButton(text="📰 Feeds"), KeyboardButton(text="🎁 Freebies")],
        [KeyboardButton(text="👁 Watch"), KeyboardButton(text="🔒 SSL")],
        [KeyboardButton(text="📂 Git"), KeyboardButton(text="⚙️ Services")],
        [KeyboardButton(text="📜 Logs"), KeyboardButton(text="💾 Disk")],
        [KeyboardButton(text="🔔 Alerts")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def projects_inline(projects_cfg):
    buttons = []
    for p in projects_cfg:
        pid = p["id"]
        name = p.get("name", pid)[:28]
        buttons.append([_ib(name, f"proj:{pid}")])
    if not buttons:
        buttons = [[_ib("empty", "noop")]]
    buttons.append([_ib("refresh", "refresh:projects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def services_inline(services, admin=False):
    rows = []
    for s in services:
        name = s.get("name", s["unit"])
        rows.append([_ib(f"log {name}", f"log:{s['unit']}")])
        if admin:
            rows.append([_ib(f"restart {name}", f"restart:{s['unit']}")])
    rows.append([_ib("refresh", "refresh:services")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def logs_inline(services):
    rows = []
    for s in services:
        name = s.get("name", s["unit"])
        rows.append([_ib(name, f"log:{s['unit']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)