import hashlib
import os

import requests

import emoji_layer as em
import store

_UA = {"User-Agent": "telegramvps-monitor/1.0"}
HASH_FILE = os.path.join(os.path.dirname(__file__), "data", "watch_hashes.json")


def _load_hashes():
    return store.load_json(HASH_FILE, {})


def _save_hashes(h):
    store.save_json(HASH_FILE, h)


def _fetch_hash(url):
    try:
        r = requests.get(url, timeout=20, headers=_UA)
        body = (r.text or "")[:12000]
        return hashlib.sha256(body.encode(errors="ignore")).hexdigest()[:16], r.status_code
    except Exception as e:
        return None, str(e)


def check_all(urls_cfg):
    hashes = _load_hashes()
    changes = []
    status_lines = []

    for entry in urls_cfg:
        name = entry.get("name", entry.get("url", "?"))
        url = entry.get("url", "")
        if not url:
            continue
        h, meta = _fetch_hash(url)
        key = url
        old = hashes.get(key)
        if h is None:
            status_lines.append(f"❌ <b>{name}</b> — {meta}")
            continue
        status_lines.append(f"{'🟢' if h == old else '🟡'} <b>{name}</b> — http {meta} · hash <code>{h}</code>")
        if old and h != old:
            changes.append({"name": name, "url": url, "old": old, "new": h})
        hashes[key] = h

    _save_hashes(hashes)
    return status_lines, changes


def format_watch(urls_cfg):
    lines, _ = check_all(urls_cfg)
    if not lines:
        return f"{em.html('👁')} add watch_urls to config.json"
    return f"{em.html('👁')} <b>Watch URLs</b>\n\n" + "\n".join(lines)