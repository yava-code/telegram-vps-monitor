import socket
import ssl
from datetime import datetime, timezone

import emoji_layer as em


def _check_host(host, port=443):
    host = host.strip().replace("https://", "").replace("http://", "").split("/")[0]
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        exp = cert.get("notAfter")
        if not exp:
            return host, None, "no expiry in cert"
        exp_dt = datetime.strptime(exp, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days = (exp_dt - datetime.now(timezone.utc)).days
        return host, days, exp
    except Exception as e:
        return host, None, str(e)


def format_ssl(domains):
    if not domains:
        return (
            f"{em.html('🔒')} <b>SSL</b>\n\n"
            "no ssl_domains in config.json\n"
            "add: <code>[\"example.com\"]</code>"
        )
    lines = [f"{em.html('🔒')} <b>SSL certs</b>\n"]
    for d in domains:
        host, days, detail = _check_host(d)
        if days is None:
            lines.append(f"❌ <b>{host}</b> — <code>{detail}</code>")
        elif days < 14:
            lines.append(f"⚠️ <b>{host}</b> — {days}d left")
        else:
            lines.append(f"✅ <b>{host}</b> — {days}d left")
    return "\n".join(lines)