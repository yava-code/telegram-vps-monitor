import html
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

import emoji_layer as em

_UA = {"User-Agent": "telegramvps-monitor/1.0"}

_PLATFORM_ORDER = [
    "steam",
    "epic-games-store",
    "gog",
    "itch.io",
    "ubisoft",
    "origin",
    "battlenet",
    "android",
    "ios",
    "ps4",
    "xbox-one",
    "switch",
    "drm-free",
    "other",
]

_PLATFORM_LABELS = {
    "steam": "Steam",
    "epic-games-store": "Epic",
    "gog": "GOG",
    "itch.io": "itch.io",
    "ubisoft": "Ubisoft",
    "origin": "EA / Origin",
    "battlenet": "Battle.net",
    "android": "Android",
    "ios": "iOS",
    "ps4": "PS4",
    "xbox-one": "Xbox",
    "switch": "Switch",
    "drm-free": "DRM-free",
    "other": "Other",
}


def _cfg(cfg):
    return cfg.get("freebies", {})


def load_env_file(path):
    keys = {}
    if not path or not os.path.exists(path):
        return keys
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
    except Exception:
        pass
    return keys


def _norm_platforms(raw):
    if not raw:
        return ["other"]
    parts = [p.strip().lower() for p in str(raw).split(",") if p.strip()]
    return parts or ["other"]


def _primary_platform(platforms):
    for p in _PLATFORM_ORDER:
        if p in platforms:
            return p
    return platforms[0] if platforms else "other"


def _item_key(item):
    return item.get("id") or f"{item.get('source')}:{item.get('title', '').lower()}"


def fetch_gamerpower(fb_cfg):
    url = "https://www.gamerpower.com/api/giveaways"
    want_platforms = {p.lower() for p in fb_cfg.get("platforms", [])}
    want_types = {t.lower() for t in fb_cfg.get("types", [])}

    try:
        r = requests.get(url, timeout=20, headers=_UA)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [], str(e)

    if not isinstance(data, list):
        return [], "bad gamerpower response"

    items = []
    for g in data:
        if g.get("status") != "Active":
            continue
        platforms = _norm_platforms(g.get("platforms", ""))
        gtype = (g.get("type") or "game").strip().lower()
        if want_platforms and not (set(platforms) & want_platforms):
            continue
        if want_types and gtype not in want_types:
            continue
        link = g.get("open_giveaway") or g.get("open_giveaway_url") or g.get("gamerpower_url", "")
        items.append(
            {
                "id": f"gp:{g.get('id')}",
                "title": (g.get("title") or "").strip(),
                "url": link,
                "worth": (g.get("worth") or "").strip(),
                "type": (g.get("type") or "game").strip(),
                "platforms": platforms,
                "platform": _primary_platform(platforms),
                "source": "gamerpower",
            }
        )
    return items, None


def fetch_steam_free_specials():
    url = (
        "https://store.steampowered.com/search/results/"
        "?query&start=0&count=50&dynamic_data=&sort_by=Released_DESC"
        "&maxprice=free&specials=1&supportedlang=english&infinite=1&cc=us"
    )
    try:
        r = requests.get(url, timeout=20, headers={**_UA, "Accept": "application/json"})
        r.raise_for_status()
        payload = r.json()
        html_block = payload.get("results_html", "")
    except Exception as e:
        return [], str(e)

    ids = re.findall(r'data-ds-appid="(\d+)"', html_block)
    names = re.findall(r'<span class="title">([^<]+)</span>', html_block)
    items = []
    seen = set()
    for appid, name in zip(ids, names):
        if appid in seen:
            continue
        seen.add(appid)
        title = html.unescape(name.strip())
        items.append(
            {
                "id": f"steam:{appid}",
                "title": title,
                "url": f"https://store.steampowered.com/app/{appid}/",
                "worth": "free",
                "type": "game",
                "platforms": ["steam"],
                "platform": "steam",
                "source": "steam",
            }
        )
    return items, None


def collect_all(cfg):
    fb = _cfg(cfg)
    if not fb.get("enabled", True):
        return [], None

    merged = []
    errors = []

    gp_items, gp_err = fetch_gamerpower(fb)
    if gp_err:
        errors.append(f"gamerpower: {gp_err}")
    merged.extend(gp_items)

    if fb.get("include_steam_search", True):
        st_items, st_err = fetch_steam_free_specials()
        if st_err:
            errors.append(f"steam: {st_err}")
        seen_titles = {it["title"].lower() for it in merged if it.get("title")}
        for it in st_items:
            if it["title"].lower() not in seen_titles:
                merged.append(it)

    max_items = fb.get("max_items", 50)
    if len(merged) > max_items:
        merged = merged[:max_items]

    err = "; ".join(errors) if errors else None
    return merged, err


def _group_items(items):
    groups = {}
    for it in items:
        plat = it.get("platform", "other")
        groups.setdefault(plat, []).append(it)
    ordered = []
    for plat in _PLATFORM_ORDER:
        if plat in groups:
            ordered.append((plat, groups.pop(plat)))
    for plat, bucket in sorted(groups.items()):
        ordered.append((plat, bucket))
    return ordered


def format_digest(items, cfg, err=None):
    fb = _cfg(cfg)
    tz_name = fb.get("timezone", "Europe/Kyiv")
    try:
        now = datetime.now(ZoneInfo(tz_name))
        stamp = now.strftime("%d %b %Y")
    except Exception:
        stamp = datetime.utcnow().strftime("%d %b %Y")

    lines = [f"{em.html('🎁')} <b>Freebies</b> — {stamp}\n"]
    if err:
        lines.append(f"<i>partial: {html.escape(err)}</i>\n")

    if not items:
        lines.append("<i>nothing active right now</i>")
        return "\n".join(lines)

    total = len(items)
    lines.append(f"<i>{total} active</i>\n")

    for plat, bucket in _group_items(items):
        label = _PLATFORM_LABELS.get(plat, plat)
        lines.append(f"<b>{html.escape(label)}</b> ({len(bucket)})")
        for it in bucket:
            title = html.escape((it.get("title") or "?")[:100])
            url = it.get("url", "")
            worth = it.get("worth", "")
            kind = it.get("type", "")
            extra = []
            if worth and worth.lower() != "n/a":
                extra.append(html.escape(worth))
            if kind and kind.lower() != "game":
                extra.append(html.escape(kind))
            suffix = f" — {', '.join(extra)}" if extra else ""
            if url:
                lines.append(f"• <a href=\"{html.escape(url, quote=True)}\">{title}</a>{suffix}")
            else:
                lines.append(f"• {title}{suffix}")
        lines.append("")

    return "\n".join(lines).strip()


def split_messages(text, limit=3800):
    if len(text) <= limit:
        return [text]
    chunks = []
    block = ""
    for line in text.split("\n"):
        candidate = f"{block}\n{line}".strip() if block else line
        if len(candidate) > limit and block:
            chunks.append(block.strip())
            block = line
        else:
            block = candidate
    if block:
        chunks.append(block.strip())
    return chunks or [text[:limit]]


def digest_due(cfg, st):
    fb = _cfg(cfg)
    if not fb.get("enabled", True):
        return False

    tz_name = fb.get("timezone", "Europe/Kyiv")
    hour = int(fb.get("digest_hour", 13))
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.utcnow()

    today = now.strftime("%Y-%m-%d")
    if now.hour != hour:
        return False
    if st.get("freebies_last_date") == today:
        return False
    return True


def today_key(cfg):
    fb = _cfg(cfg)
    tz_name = fb.get("timezone", "Europe/Kyiv")
    try:
        return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")