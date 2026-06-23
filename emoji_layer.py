"""premium custom emoji — works only if bot owner has TG Premium"""

import os
import random

_DEFAULT_POOL = [
    "5420323339723881652",
    "5447644880824181073",
    "5231012545799666522",
    "5443038326535759644",
    "5337080053119336309",
    "5296369303661067030",
    "5368324170671202286",
    "5457574567310965622",
    "5402288107568619523",
    "5285410812430231384",
]


def _pool():
    extra = os.getenv("PREMIUM_EMOJI_POOL", "")
    ids = list(_DEFAULT_POOL)
    if extra:
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
    ch = fallback[0] if fallback else "⭐"
    return f'<tg-emoji emoji-id="{doc}">{ch}</tg-emoji>'


def btn_id():
    if not enabled():
        return None
    pool = _pool()
    if not pool:
        return None
    return random.choice(pool)
