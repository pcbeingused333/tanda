"""`tanda ui`: a local dashboard (stdlib only). Board by state, live workers, activity, and human actions."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .store import Store

HTML = os.path.join(os.path.dirname(__file__), "ui.html")


def tail(path, n=200):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError as e:
        return f"(no log: {e})"


def serve(cfg, host, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            st = Store(cfg.db)
            p = self.path.split("?")[0]
            if p == "/":
                with open(HTML, "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if p == "/api/state":
                week = time.time() - 7 * 86400
                items = [i for i in st.items() if i["state"] not in ("DONE", "DROPPED") or i["updated"] > week]
                roles = [{"name": r.name, "mode": r.mode, "count": r.count, "model": r.model, "agent": r.agent[0],
                          "claims": r.claims, "working": r.working, "verdicts": r.verdicts}
                         for r in cfg.roles.values()]
                return self.send(200, {
                    "name": cfg.name, "states": cfg.states, "hold": cfg.hold_state, "roles": roles,
                    "items": items, "runs": st.runs(40), "events": st.events(limit=60), "now": int(time.time()),
                    "run_state": st.meta("run_state") or "never", "stop": st.meta("stop") == "1"})
            if p.startswith("/api/item/"):
                i = st.get(int(p.rsplit("/", 1)[1]))
                return self.send(200 if i else 404, {"item": i, "events": st.events(i["id"]) if i else []})
            if p.startswith("/api/log/"):
                rid = int(p.rsplit("/", 1)[1])
                r = next((x for x in st.runs(1000) if x["id"] == rid), None)
                return self.send(200, {"log": tail(r["log"]) if r else "(unknown run)"})
            self.send(404, {"error": "not found"})

        def do_POST(self):
            st = Store(cfg.db)
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            try:
                if self.path == "/api/set":
                    st.set(int(body["id"]), body["state"], actor="human", note=body.get("note", ""))
                elif self.path == "/api/add":
                    st.add(cfg.initial_state, body["title"], grp=body.get("group", ""), ref=body.get("ref", ""),
                           kind=body.get("kind", ""), priority=int(body.get("priority") or 5),
                           note=body.get("note", ""), actor="human",
                           group_cap=cfg.group_cap, blocked=cfg.blocked_groups)
                elif self.path == "/api/stop":
                    st.meta("stop", "1")
                else:
                    return self.send(404, {"error": "not found"})
            except (ValueError, KeyError) as e:
                return self.send(400, {"error": str(e)})
            self.send(200, {"ok": True})

    srv = ThreadingHTTPServer((host, port), H)
    print(f"tanda ui: http://{host}:{port}  (Ctrl+C to quit)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
