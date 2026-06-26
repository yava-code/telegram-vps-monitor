import os
import re
import subprocess
import time

import store

LOG = os.path.join(os.path.dirname(__file__), "data", "shell_log.json")

# block obviously bad stuff — admin can still shoot foot, just not rm -rf /
_BLOCKED = [
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?(/|~)",
    r"rm\s+-rf\s+",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"chmod\s+-R\s+777\s+/",
    r"\b(shutdown|reboot|poweroff|halt)\b",
    r"\buserdel\b",
    r"curl\s+[^\|]+\|\s*(ba)?sh",
    r"wget\s+[^\|]+\|\s*sh",
]


def _blocked(cmd):
    low = cmd.lower().strip()
    for pat in _BLOCKED:
        if re.search(pat, low):
            return pat
    return None


def _allowed(cmd, prefixes):
    if not prefixes:
        return True
    low = cmd.strip()
    for p in prefixes:
        if low.startswith(p):
            return True
    return False


def _log_entry(chat_id, cmd, code, preview):
    rows = store.load_json(LOG, [])
    rows.append({
        "ts": time.time(),
        "chat_id": chat_id,
        "cmd": cmd[:200],
        "exit": code,
        "out": preview[:120],
    })
    store.save_json(LOG, rows[-80:])


def run(cmd, chat_id, shell_cfg=None):
    shell_cfg = shell_cfg or {}
    if not shell_cfg.get("enabled", True):
        return "shell disabled in config", 1

    cmd = (cmd or "").strip()
    if not cmd:
        return "empty command", 1

    bad = _blocked(cmd)
    if bad:
        return f"blocked by safety rule", 1

    prefixes = shell_cfg.get("allowed_prefixes") or []
    if prefixes and not _allowed(cmd, prefixes):
        return "not in allowed_prefixes — add to config.json shell.allowed_prefixes", 1

    cwd = shell_cfg.get("cwd", "/opt")
    timeout = int(shell_cfg.get("timeout_sec", 20))
    max_out = int(shell_cfg.get("max_output", 3500))

    try:
        p = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (p.stdout or "") + (p.stderr or "")
        if len(out) > max_out:
            out = out[:max_out] + "\n... truncated"
        if not out.strip():
            out = f"(exit {p.returncode}, no output)"
        _log_entry(chat_id, cmd, p.returncode, out)
        return out, p.returncode
    except subprocess.TimeoutExpired:
        _log_entry(chat_id, cmd, -1, "timeout")
        return f"timeout after {timeout}s", -1
    except Exception as e:
        _log_entry(chat_id, cmd, -1, str(e))
        return str(e), -1