import time

import requests

import store

_UA = {"User-Agent": "telegramvps-monitor/1.0"}


def poll_review_roadmap(url):
    try:
        r = requests.get(url, timeout=8, headers=_UA)
        data = r.json()
        caps = data.get("capabilities", {})
        llm = caps.get("llm", {})
        tg = caps.get("telegram", {})
        ready = data.get("ready", False)
        status = "running" if ready else "failed"
        msg = f"db={data.get('database')} · llm={llm.get('mode')} · tg={tg.get('mode')}"
        store.set_project("review-roadmap", {
            "status": status,
            "step": "serving",
            "progress": 100.0 if ready else 0.0,
            "message": msg,
            "verdict": "OK" if ready else "DEGRADED",
            "summary": "\n".join(f"{k}: {v.get('mode')}" for k, v in caps.items()),
            "started_at": time.time(),
        })
        return True
    except Exception as e:
        store.set_project("review-roadmap", {
            "status": "failed",
            "error": str(e),
            "failed_at": time.time(),
        })
        return False


def run_probes(probes_cfg):
    for p in probes_cfg:
        pid = p.get("id")
        url = p.get("url", "")
        if pid == "review-roadmap" and url:
            poll_review_roadmap(url)