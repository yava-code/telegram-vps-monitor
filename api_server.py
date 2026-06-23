import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import store


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._json(200, {"ok": True})
        elif self.path == "/projects":
            self._json(200, store.get_all_projects())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/report":
            self._json(404, {"error": "not found"})
            return
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw)
        except Exception:
            self._json(400, {"error": "bad json"})
            return
        pid = data.get("project_id")
        if not pid:
            self._json(400, {"error": "project_id required"})
            return
        store.set_project(pid, data)
        self._json(200, {"ok": True, "project_id": pid})


def start_api(port, on_update=None):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def run():
        srv.serve_forever(poll_interval=0.5)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return srv