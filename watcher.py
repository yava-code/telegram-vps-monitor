import json
import os
import struct
import select
import threading
import time
import ctypes
import ctypes.util

import store

# linux inotify, no extra pip deps
libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.inotify_init.restype = ctypes.c_int
libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
libc.inotify_add_watch.restype = ctypes.c_int

IN_MODIFY = 0x2
IN_CLOSE_WRITE = 0x8
IN_MOVED_TO = 0x80
MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO
EVENT_SZ = struct.calcsize("iIII")


def _read_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


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


def _load_path(path, path_map):
    info = path_map.get(path)
    if not info:
        return
    data = _read_file(path)
    if data:
        store.set_project(info["id"], data)


def _poll_fallback(projects_cfg, interval=5.0):
    mtimes = {}
    paths = {}
    for p in projects_cfg:
        if p.get("source") != "file":
            continue
        path = p.get("path")
        pid = p.get("id")
        if path and pid:
            paths[path] = {"id": pid}

    def loop():
        while True:
            for path in paths:
                try:
                    m = os.path.getmtime(path)
                except OSError:
                    m = 0
                if m != mtimes.get(path):
                    mtimes[path] = m
                    _load_path(path, paths)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()


def start_file_watcher(projects_cfg):
    paths = {}
    for p in projects_cfg:
        if p.get("source") != "file":
            continue
        path = p.get("path")
        pid = p.get("id")
        if path and pid:
            paths[path] = {"id": pid}

    if not paths:
        return

    for path in paths:
        _load_path(path, paths)

    fd = libc.inotify_init()
    if fd < 0:
        _poll_fallback(projects_cfg)
        return

    wd_map = {}
    for path in paths:
        d = os.path.dirname(path) or "."
        base = os.path.basename(path)
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        wd = libc.inotify_add_watch(fd, d.encode(), MASK)
        if wd >= 0:
            wd_map[wd] = (path, base)

    if not wd_map:
        os.close(fd)
        _poll_fallback(projects_cfg)
        return

    def loop():
        while True:
            try:
                r, _, _ = select.select([fd], [], [], 30)
                if not r:
                    continue
                buf = os.read(fd, 4096)
                off = 0
                while off + 16 <= len(buf):
                    wd, mask, cookie, name_len = struct.unpack_from("iIII", buf, off)
                    off += 16
                    name = ""
                    if name_len:
                        name = buf[off : off + name_len].split(b"\0")[0].decode(errors="ignore")
                        off += name_len
                    off = (off + 3) & ~3
                    hit = wd_map.get(wd)
                    if not hit:
                        continue
                    path, base = hit
                    if name and name != base:
                        continue
                    _load_path(path, paths)
            except Exception:
                time.sleep(2)

    threading.Thread(target=loop, daemon=True).start()
