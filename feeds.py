import xml.etree.ElementTree as ET

import requests

import emoji_layer as em

_UA = {"User-Agent": "telegramvps-monitor/1.0"}


def _text(el, tag):
    if el is None:
        return ""
    node = el.find(tag)
    return (node.text or "").strip() if node is not None else ""


def fetch_items(url, limit=5):
    try:
        r = requests.get(url, timeout=15, headers=_UA)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        return [], str(e)

    items = []
    for item in root.findall(".//item"):
        title = _text(item, "title")
        link = _text(item, "link")
        guid = _text(item, "guid") or link or title
        if title:
            items.append({"id": guid, "title": title, "link": link})
        if len(items) >= limit:
            break

    if not items:
        atom_ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", atom_ns):
            title = (entry.findtext("a:title", default="", namespaces=atom_ns) or "").strip()
            link_el = entry.find("a:link", atom_ns)
            link = link_el.get("href", "") if link_el is not None else ""
            uid = entry.findtext("a:id", default=link, namespaces=atom_ns)
            if title:
                items.append({"id": uid, "title": title, "link": link})
            if len(items) >= limit:
                break

    return items, None


def format_feeds(feeds_cfg, limit=5):
    if not feeds_cfg:
        return f"{em.html('📰')} no feeds in config.json"
    lines = [f"{em.html('📰')} <b>Feeds</b>\n"]
    for f in feeds_cfg:
        name = f.get("name", "feed")
        url = f.get("url", "")
        lim = f.get("limit", limit)
        items, err = fetch_items(url, lim)
        lines.append(f"<b>{name}</b>")
        if err:
            lines.append(f"<i>err: {err}</i>\n")
            continue
        if not items:
            lines.append("<i>empty</i>\n")
            continue
        for it in items:
            t = it["title"][:120]
            link = it.get("link", "")
            if link:
                lines.append(f"• <a href=\"{link}\">{t}</a>")
            else:
                lines.append(f"• {t}")
        lines.append("")
    return "\n".join(lines)[:3800]


def new_items_since(feeds_cfg, seen_ids):
    """return list of (feed_name, item) not in seen_ids"""
    fresh = []
    for f in feeds_cfg:
        name = f.get("name", "feed")
        url = f.get("url", "")
        items, err = fetch_items(url, f.get("limit", 8))
        if err:
            continue
        for it in items:
            iid = it.get("id") or it.get("title")
            key = f"{name}:{iid}"
            if key not in seen_ids:
                fresh.append((name, it, key))
    return fresh