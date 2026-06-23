import json
import os
import time
import threading

import store


def _read_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0


def sync_file_projects(projects_cfg):
    for p in projects_cfg:
        if p.get("source") != "file":
            continue
        path = p.get("path")
        pid = p.get("id")
        if not path or not pid:
            continue
        data = _read_file(path)
        if data:
            store.set_project(pid, data)


def start_file_watcher(projects_cfg, interval=2.0):
    mtimes = {}

    def loop():
        while True:
            for p in projects_cfg:
                if p.get("source") != "file":
                    continue
                path = p.get("path")
                pid = p.get("id")
                if not path or not pid:
                    continue
                m = _mtime(path)
                if m != mtimes.get(path):
                    mtimes[path] = m
                    data = _read_file(path)
                    if data:
                        store.set_project(pid, data)
            time.sleep(interval)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
