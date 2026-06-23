"""copy this file into your project and call push_status()"""

import requests

API = "http://127.0.0.1:8787/report"


def push_status(project_id, status="running", step="", current=0, total=0, message="", **extra):
    payload = {
        "project_id": project_id,
        "status": status,
        "step": step,
        "current_item": current,
        "total_items": total,
        "message": message,
    }
    payload.update(extra)
    if total > 0:
        payload["progress"] = min(100.0, round(current / total * 100, 1))
    try:
        requests.post(API, json=payload, timeout=2)
    except Exception:
        pass  # monitor down, whatever