import json
import os
import time
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
CHAT_IDS_FILE = os.path.join(DATA_DIR, "chat_ids.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

_lock = threading.Lock()


def _ensure():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_json(path, default):
    _ensure()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    _ensure()
    with open(path, "w") as f:
        json.dump(data, f)


def get_all_projects():
    with _lock:
        return load_json(PROJECTS_FILE, {})


def set_project(project_id, payload):
    with _lock:
        allp = load_json(PROJECTS_FILE, {})
        payload = dict(payload)
        payload["project_id"] = project_id
        payload["updated_at"] = payload.get("updated_at") or time.time()
        allp[project_id] = payload
        save_json(PROJECTS_FILE, allp)


def get_project(project_id):
    return get_all_projects().get(project_id)


def load_chat_ids():
    return load_json(CHAT_IDS_FILE, [])


def save_chat_ids(ids):
    save_json(CHAT_IDS_FILE, list(set(ids)))


def load_state():
    return load_json(STATE_FILE, {})


def save_state(st):
    save_json(STATE_FILE, st)