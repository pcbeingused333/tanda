"""`tanda run`: starts every role, feeds items to workers one at a time, and stops when the queue is drained.

Waiting happens here, in Python, not inside an agent: an agent is only started when there is an item
for it, and it exits when it has given its verdict. Idle roles cost no tokens.
"""
import json
import os
import shlex
import subprocess
import sys
import threading
import time

from .store import Store

TANDA_CMD = f"{shlex.quote(sys.executable)} -m tanda"


def footer(cfg, role, item):
    lines = ["", "---", "## How to report back (tanda)",
             f"You are `{role.name}` in the tanda `{cfg.name}`. Use these commands; nothing else updates the queue."]
    if item:
        lines += [f"Your item is #{item['id']}. When you finish, give exactly ONE verdict:",
                  *[f"  {TANDA_CMD} set {item['id']} {v} --note \"<one line: why>\" [--field key=value ...]"
                    for v in role.verdicts],
                  "Fields you set (branch, commit, draft path, ...) are shown to the next role and in the UI.",
                  f"Read the full item with: {TANDA_CMD} show {item['id']}"]
    else:
        lines += ["Add each piece of work you find (one per call):",
                  f"  {TANDA_CMD} add --title \"<what and why>\" --group <owner/repo or area> --ref <issue id or key>"
                  " [--kind <type>] [--priority 1-9] [--field key=value ...]",
                  "The command refuses duplicates, blocked groups and groups at their cap: do not retry those.",
                  f"See what is already queued with: {TANDA_CMD} list"]
    return "\n".join(lines) + "\n"


def render(cfg, role, item):
    text = cfg.prompt_text(role)
    if item:
        values = {"item_id": item["id"], "title": item["title"], "group": item["grp"], "ref": item["ref"],
                  "kind": item["kind"], "note": item["note"], "fields": json.dumps(item["fields"], indent=1)}
        for k, v in values.items():
            text = text.replace("{" + k + "}", str(v))
    return text + footer(cfg, role, item)


class Runner:
    def __init__(self, cfg, only_roles=None, echo=print):
        self.cfg = cfg
        self.echo = echo
        self.roles = [r for r in cfg.roles.values() if not only_roles or r.name in only_roles]
        self.once_left = 0
        self.lock = threading.Lock()
        self.logdir = os.path.join(os.path.dirname(cfg.db), "logs")
        os.makedirs(self.logdir, exist_ok=True)

    def store(self):
        return Store(self.cfg.db)  # one connection per thread

    # -- one agent invocation -------------------------------------------------
    def invoke(self, st, role, worker, item):
        prompt = render(self.cfg, role, item)
        cmd = [a.replace("{model}", role.model).replace("{prompt}", prompt) for a in role.agent]
        tag = f"{worker}-{item['id']}" if item else worker
        log = os.path.join(self.logdir, f"{time.strftime('%Y%m%d-%H%M%S')}-{tag}.log")
        env = {**os.environ, "TANDA_CONFIG": self.cfg.path, "TANDA_ROLE": role.name, "TANDA_WORKER": worker,
               "TANDA_ITEM": str(item["id"]) if item else ""}
        with open(log, "w", encoding="utf-8") as out:
            try:
                p = subprocess.Popen(cmd, cwd=self.cfg.root, env=env, stdout=out, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL)
            except FileNotFoundError:
                out.write(f"tanda: agent command not found: {cmd[0]}\n")
                return 127, log
            run_id = st.run_start(role.name, worker, item["id"] if item else None, p.pid, log)
            try:
                code = p.wait(timeout=role.timeout_minutes * 60)
            except subprocess.TimeoutExpired:
                p.kill()
                code = p.wait()
                out.write(f"\ntanda: killed after {role.timeout_minutes} min\n")
            st.run_end(run_id, code)
        return code, log

    # -- role loops -------------------------------------------------------------
    def once(self, role, worker):
        st = self.store()
        self.echo(f"[{worker}] start")
        code, log = self.invoke(st, role, worker, None)
        self.echo(f"[{worker}] done (exit {code})  {log}")
        with self.lock:
            self.once_left -= 1

    def worker(self, role, worker):
        st = self.store()
        while not self.should_stop(st):
            item = st.claim(role.claims, role.working, worker)
            if item is None:
                time.sleep(self.cfg.poll_seconds)
                continue
            self.echo(f"[{worker}] #{item['id']} {item['title'][:60]}")
            code, log = self.invoke(st, role, worker, item)
            after = st.get(item["id"])
            if after["state"] == role.working:  # the agent exited without a verdict
                st.set(item["id"], self.cfg.hold_state, actor="tanda",
                       note=f"{worker} exited ({code}) without a verdict; see {os.path.basename(log)}")
                after = st.get(item["id"])
            self.echo(f"[{worker}] #{item['id']} -> {after['state']}")

    # -- finish condition ---------------------------------------------------------
    def pending_states(self):
        s = set(self.cfg.wait_states)
        for r in self.roles:
            if r.mode == "worker":
                s.update(r.claims)
                s.add(r.working)
        return sorted(s)

    def should_stop(self, st):
        if st.meta("stop") == "1":
            return True
        if time.time() > self.deadline:
            return True
        with self.lock:
            once_left = self.once_left
        return once_left == 0 and st.count(self.pending_states()) == 0

    def run(self):
        st = self.store()
        st.meta("stop", "0")
        st.meta("run_started", int(time.time()))
        st.meta("run_state", "running")
        self.deadline = time.time() + self.cfg.max_hours * 3600
        threads = []
        for role in self.roles:
            n = 1 if role.mode == "once" else role.count
            for i in range(1, n + 1):
                name = role.name if n == 1 else f"{role.name}-{i}"
                fn = self.once if role.mode == "once" else self.worker
                if role.mode == "once":
                    self.once_left += 1
                threads.append(threading.Thread(target=fn, args=(role, name), daemon=True))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        why = "stopped" if st.meta("stop") == "1" else ("timeout" if time.time() > self.deadline else "drained")
        st.meta("run_state", why)
        return why
