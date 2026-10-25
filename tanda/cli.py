import argparse
import json
import os
import shutil
import sys
import time

from . import config as C
from .store import Store


def parse_fields(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"tanda: --field expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        out[k] = v
    return out


def ago(t):
    s = int(time.time()) - int(t)
    return f"{s // 60}m" if s < 3600 else f"{s // 3600}h{s % 3600 // 60:02d}m"


def show_rows(rows):
    if not rows:
        print("(empty)")
    for r in rows:
        who = f" [{r['owner']}]" if r["owner"] else ""
        where = f" {r['grp']}#{r['ref']}" if r["grp"] or r["ref"] else ""
        print(f"#{r['id']:<4} {r['state']:<12} p{r['priority']}{where}  {r['title'][:70]}{who}  {ago(r['updated'])}")
        if r["note"]:
            print(f"       note: {r['note']}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tanda", description="Run a fleet of coding agents around one shared queue.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="copy an example tanda.toml + prompts into the current directory")
    p.add_argument("example", nargs="?", default="hello", help="hello | oss-contrib")

    p = sub.add_parser("add", help="add an item")
    p.add_argument("--title", required=True)
    p.add_argument("--group", default="")
    p.add_argument("--ref", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--priority", type=int, default=5)
    p.add_argument("--state", help="defaults to [tanda] initial_state")
    p.add_argument("--note", default="")
    p.add_argument("--field", action="append")

    p = sub.add_parser("set", help="move an item to a new state")
    p.add_argument("id", type=int)
    p.add_argument("state")
    p.add_argument("--note", default="")
    p.add_argument("--field", action="append")

    p = sub.add_parser("show", help="one item with its history")
    p.add_argument("id", type=int)

    p = sub.add_parser("list", help="items (active ones unless a state is given)")
    p.add_argument("state", nargs="?")

    p = sub.add_parser("count")
    p.add_argument("states", nargs="+")

    p = sub.add_parser("run", help="start the tanda: run every role until the queue is drained")
    p.add_argument("--roles", help="comma-separated subset of roles")

    sub.add_parser("stop", help="ask a running tanda to finish its current items and stop")
    sub.add_parser("status", help="counts per state and the latest agent runs")

    p = sub.add_parser("ui", help="local web dashboard")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--host", default="127.0.0.1")

    a = ap.parse_args(argv)

    if a.cmd == "init":
        src = os.path.join(os.path.dirname(__file__), "examples", a.example)
        if not os.path.isdir(src):
            raise SystemExit(f"tanda: no example {a.example!r}")
        if os.path.exists("tanda.toml"):
            raise SystemExit("tanda: tanda.toml already exists here")
        shutil.copytree(src, ".", dirs_exist_ok=True)
        print(f"Copied example {a.example!r}. Edit tanda.toml, then: tanda ui  (and in another terminal) tanda run")
        return

    cfg = C.load()
    st = Store(cfg.db)
    actor = os.environ.get("TANDA_WORKER") or "human"

    if a.cmd == "add":
        try:
            i = st.add(a.state or cfg.initial_state, a.title, kind=a.kind, grp=a.group, ref=a.ref,
                       priority=a.priority, fields=parse_fields(a.field), note=a.note, actor=actor,
                       group_cap=cfg.group_cap, blocked=cfg.blocked_groups)
        except ValueError as e:
            raise SystemExit(f"tanda: not added: {e}")
        print(f"#{i}")

    elif a.cmd == "set":
        state = a.state.upper()
        if state not in cfg.states:
            raise SystemExit(f"tanda: unknown state {state} (have: {' '.join(cfg.states)})")
        allowed_from = None
        role_name = os.environ.get("TANDA_ROLE")
        if role_name:  # agents may only give their own verdicts, on items they hold
            role = cfg.role(role_name)
            if state not in role.verdicts:
                raise SystemExit(f"tanda: {role_name} can only set {' '.join(role.verdicts)}")
            allowed_from = {role.working}
        try:
            st.set(a.id, state, actor=actor, note=a.note, fields=parse_fields(a.field), allowed_from=allowed_from)
        except ValueError as e:
            raise SystemExit(f"tanda: {e}")
        print(f"#{a.id} -> {state}")

    elif a.cmd == "show":
        r = st.get(a.id) or sys.exit(f"tanda: no item #{a.id}")
        print(json.dumps(r, indent=1, ensure_ascii=False))
        for e in st.events(a.id):
            print(f"  {time.strftime('%m-%d %H:%M', time.localtime(e['at']))} {e['actor']:<12} {e['old']} -> {e['new']}  {e['note']}")

    elif a.cmd == "list":
        if a.state:
            show_rows(st.items(a.state.upper()))
        else:
            show_rows([r for r in st.items() if r["state"] not in ("DONE", "DROPPED")])

    elif a.cmd == "count":
        print(st.count([s.upper() for s in a.states]))

    elif a.cmd == "run":
        from .runner import Runner
        roles = set(a.roles.split(",")) if a.roles else None
        print(f"tanda {cfg.name}: roles {', '.join(r for r in cfg.roles if not roles or r in roles)}  (UI: tanda ui)")
        why = Runner(cfg, roles).run()
        print(f"tanda {cfg.name}: {why}")

    elif a.cmd == "stop":
        st.meta("stop", "1")
        print("stop requested: workers finish their current item and exit")

    elif a.cmd == "status":
        for s in cfg.states:
            n = st.count([s])
            if n:
                print(f"{s:<12} {n}")
        print(f"run: {st.meta('run_state') or 'never'}")
        for r in st.runs(10):
            state = "running" if r["ended"] is None else f"exit {r['exit']}"
            print(f"  {r['worker']:<12} item #{r['item'] or '-':<4} {state:<8} {ago(r['started'])} ago")

    elif a.cmd == "ui":
        from .ui import serve
        serve(cfg, a.host, a.port)


if __name__ == "__main__":
    main()
