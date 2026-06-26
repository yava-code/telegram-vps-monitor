"""premium emoji — only works if bot owner has TG Premium"""

import os
import random
import re

# verified ids only (from review-roadmap .env). don't add random ids from internet
_VERIFIED = [
    "5420323339723881652",
    "5447644880824181073",
    "5231012545799666522",
    "5443038326535759644",
    "5337080053119336309",
    "5296369303661067030",
    "5296461632573032328",
]


def ai_icon():
    if not enabled():
        return "🤖"
    return f'<tg-emoji emoji-id="5296461632573032328">🤖</tg-emoji>'


def _pool():
    ids = list(_VERIFIED)
    extra = os.getenv("PREMIUM_EMOJI_POOL", "")
    for x in extra.split(","):
        x = x.strip()
        if x and x not in ids:
            ids.append(x)
    return ids


def enabled():
    return os.getenv("ENABLE_CUSTOM_EMOJI", "true").lower() in ("1", "true", "yes")


def html(fallback):
    if not enabled():
        return fallback
    pool = _pool()
    if not pool:
        return fallback
    doc = random.choice(pool)
    ch = fallback[0] if fallback else "?"
    return f'<tg-emoji emoji-id="{doc}">{ch}</tg-emoji>'


def btn_id():
    # inline button icons break easy, skip for now
    return None


def strip_premium(text):
    return re.sub(r'<tg-emoji emoji-id="[^"]+">(.?)</tg-emoji>', r"\1", text)