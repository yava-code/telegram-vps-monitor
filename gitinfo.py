import os
import subprocess

import emoji_layer as em


def _run(cmd, cwd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, cwd=cwd, timeout=5).strip()
    except Exception:
        return None


def scan_dirs(paths):
    rows = []
    for path in paths:
        if not os.path.isdir(path):
            continue
        if not os.path.isdir(os.path.join(path, ".git")):
            rows.append({"path": path, "skip": "not a git repo"})
            continue
        branch = _run("git rev-parse --abbrev-ref HEAD", path) or "?"
        dirty = _run("git status --porcelain", path)
        n_dirty = len([x for x in (dirty or "").splitlines() if x.strip()])
        last = _run("git log -1 --format=%cr", path) or "?"
        rows.append({
            "path": path,
            "branch": branch,
            "dirty": n_dirty,
            "last": last,
        })
    return rows


def format_git(paths):
    rows = scan_dirs(paths)
    if not rows:
        return f"{em.html('📂')} add git_dirs to config.json"
    lines = [f"{em.html('📂')} <b>Git repos</b>\n"]
    for r in rows:
        if r.get("skip"):
            lines.append(f"⏭ <code>{r['path']}</code> — {r['skip']}")
            continue
        mark = "⚠️" if r["dirty"] else "✅"
        lines.append(
            f"{mark} <code>{r['path']}</code>\n"
            f"   branch <b>{r['branch']}</b> · dirty {r['dirty']} · {r['last']}"
        )
    return "\n".join(lines)