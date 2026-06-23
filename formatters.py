import time

import emoji_layer as em


def progress_bar(pct, width=12):
    filled = int(round(pct / 100.0 * width))
    filled = max(0, min(width, filled))
    chunks = []
    for i in range(width):
        chunks.append(em.html("🟢") if i < filled else em.html("⚪"))
    return "".join(chunks)


def fmt_duration(sec):
    if not sec or sec < 0:
        return "00:00:00"
    return time.strftime("%H:%M:%S", time.gmtime(sec))


def fmt_project_list(projects_cfg, statuses):
    if not projects_cfg:
        return "нет проектов в config.json"
    lines = [f"{em.html('📦')} <b>Projects</b>\n"]
    for p in projects_cfg:
        pid = p["id"]
        name = p.get("name", pid)
        st = statuses.get(pid, {})
        status = st.get("status", "idle")
        prog = st.get("progress", 0)
        icon = {
            "running": em.html("🏃"),
            "completed": em.html("✅"),
            "failed": em.html("❌"),
            "idle": em.html("💤"),
        }.get(status, em.html("❓"))
        lines.append(f"{icon} <b>{name}</b> — <code>{status}</code> {prog}%")
    return "\n".join(lines)


def fmt_project_detail(st, name):
    if not st:
        return f"{em.html('📭')} нет данных по проекту"
    status = st.get("status", "unknown")
    if status == "running":
        started = st.get("started_at", 0)
        elapsed = time.time() - started if started else 0
        prog = float(st.get("progress", 0))
        eta = "n/a"
        if prog > 0:
            total_est = elapsed / (prog / 100.0)
            eta = fmt_duration(max(0, total_est - elapsed))
        bar = progress_bar(prog)
        return (
            f"{em.html('🏃')} <b>{name}</b> — running\n\n"
            f"<b>step:</b> <code>{st.get('step', '?')}</code>\n"
            f"<b>progress:</b> {prog}% {bar}\n"
            f"<b>items:</b> {st.get('current_item', 0)} / {st.get('total_items', 0)}\n"
            f"<b>msg:</b> <i>{st.get('message', '')}</i>\n\n"
            f"<b>elapsed:</b> {fmt_duration(elapsed)}\n"
            f"<b>eta:</b> {eta}"
        )
    if status == "completed":
        started = st.get("started_at", 0)
        done = st.get("completed_at", 0)
        dur = done - started if done and started else 0
        return (
            f"{em.html('✅')} <b>{name}</b> done\n"
            f"<b>duration:</b> {fmt_duration(dur)}\n"
            f"<b>verdict:</b> <code>{st.get('verdict', '?')}</code>\n\n"
            f"<pre>{st.get('summary', '')[:3500]}</pre>"
        )
    if status == "failed":
        return (
            f"{em.html('❌')} <b>{name}</b> failed\n\n"
            f"<pre>{st.get('error', '')[:3500]}</pre>"
        )
    return f"{em.html('💤')} <b>{name}</b> — idle"


def fmt_server():
    import sysinfo as si

    cpu = si.cpu_pct()
    ram = si.ram_use_pct()
    disk = si.disk_use_pct()
    load = si.load_avg()
    rx, tx = si.net_stats()
    cpu_s = f"{cpu}%" if cpu is not None else "?"
    return (
        f"{em.html('🖥')} <b>Server</b>\n\n"
        f"<b>uptime:</b>\n<code>{si.uptime_line()}</code>\n"
        f"<b>load:</b> <code>{load}</code>\n"
        f"<b>cpu:</b> <code>{cpu_s}</code>  <b>ram:</b> <code>{ram}%</code>  <b>disk /:</b> <code>{disk}%</code>\n\n"
        f"<b>mem:</b>\n<pre>{si.mem_info()}</pre>\n"
        f"<b>disk /:</b>\n<pre>{si.disk_root()}</pre>\n"
        f"<b>net:</b> rx {si.fmt_bytes(rx)} / tx {si.fmt_bytes(tx)}\n"
        f"<b>ip:</b> <code>{si.local_ip()}</code>"
    )


def fmt_disk():
    import sysinfo as si

    return f"{em.html('💾')} <b>Disk</b>\n\n<pre>{si.disk_all()}</pre>"


def fmt_net():
    import sysinfo as si

    rx, tx = si.net_stats()
    return (
        f"{em.html('🌐')} <b>Network</b>\n\n"
        f"<b>ip:</b> <code>{si.local_ip()}</code>\n"
        f"<b>rx:</b> {si.fmt_bytes(rx)}\n"
        f"<b>tx:</b> {si.fmt_bytes(tx)}"
    )


def fmt_top():
    import sysinfo as si

    return f"{em.html('📈')} <b>Top processes</b>\n\n<pre>{si.top_procs(8)}</pre>"


def fmt_services(services):
    import sysinfo as si

    lines = [f"{em.html('⚙️')} <b>Services</b>\n"]
    for s in services:
        unit = s["unit"]
        name = s.get("name", unit)
        active, sub = si.service_status(unit)
        mark = em.html("✅") if active == "active" else em.html("❌")
        lines.append(f"{mark} <b>{name}</b> — <code>{active}</code> ({sub})")
    return "\n".join(lines)


def fmt_alerts(thresholds, disk, ram, load1):
    return (
        f"{em.html('🔔')} <b>Alert thresholds</b>\n\n"
        f"disk &gt; {thresholds.get('disk_pct', 85)}% (now {disk}%)\n"
        f"ram &gt; {thresholds.get('ram_pct', 90)}% (now {ram}%)\n"
        f"load 1m &gt; {thresholds.get('load_1m', 4)} (now {load1})\n"
        f"\ncooldown 5 min between same alert"
    )
