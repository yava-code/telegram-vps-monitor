import os
import subprocess
import time


def _run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, timeout=8).strip()
    except Exception:
        return None


def uptime_line():
    return _run("uptime") or "n/a"


def load_avg():
    try:
        return open("/proc/loadavg").read().strip()
    except Exception:
        return "n/a"


def cpu_pct():
    try:
        a = open("/proc/stat").readline().split()[1:]
        idle = int(a[3]) + int(a[4])
        total = sum(int(x) for x in a)
        time.sleep(0.15)
        b = open("/proc/stat").readline().split()[1:]
        idle2 = int(b[3]) + int(b[4])
        total2 = sum(int(x) for x in b)
        dt = total2 - total
        if dt <= 0:
            return 0.0
        return round(100.0 * (1 - (idle2 - idle) / dt), 1)
    except Exception:
        return None


def mem_info():
    return _run("free -h") or "n/a"


def disk_root():
    return _run("df -h /") or "n/a"


def disk_all():
    return _run("df -h") or "n/a"


def disk_use_pct():
    out = _run("df / --output=pcent | tail -1")
    if not out:
        return 0
    try:
        return int(out.replace("%", "").strip())
    except Exception:
        return 0


def ram_use_pct():
    try:
        lines = open("/proc/meminfo").read().splitlines()
        mem = {}
        for ln in lines:
            k, v = ln.split(":", 1)
            mem[k.strip()] = int(v.strip().split()[0])
        total = mem.get("MemTotal", 1)
        avail = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = total - avail
        return round(100.0 * used / total, 1)
    except Exception:
        return 0.0


def net_stats():
    try:
        lines = open("/proc/net/dev").read().splitlines()[2:]
        rx = tx = 0
        for ln in lines:
            if ":" not in ln:
                continue
            parts = ln.split(":", 1)[1].split()
            if len(parts) < 9:
                continue
            iface = ln.split(":")[0].strip()
            if iface == "lo":
                continue
            rx += int(parts[0])
            tx += int(parts[8])
        return rx, tx
    except Exception:
        return 0, 0


def fmt_bytes(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}" if u != "B" else f"{n}{u}"
        n /= 1024
    return f"{n:.1f}PB"


def local_ip():
    return _run("hostname -I | awk '{print $1}'") or "?"


def top_procs(n=5):
    out = _run(f"ps aux --sort=-%mem | head -n {n + 1}")
    if not out:
        return "n/a"
    return out


def service_status(unit):
    st = _run(f"systemctl is-active {unit}")
    sub = _run(f"systemctl show {unit} --property=SubState --value")
    return st or "unknown", sub or ""


def tail_journal(unit, lines=20):
    return _run(f"journalctl -u {unit} -n {lines} --no-pager") or "no logs"


def restart_service(unit):
    return _run(f"sudo systemctl restart {unit}")
