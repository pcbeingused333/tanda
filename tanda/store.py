"""SQLite-backed work queue: items move through states, every move is logged as an event."""
import json
import os
import sqlite3
import time

ACTIVE_EXCLUDED = ("DONE", "DROPPED")


def now():
    return int(time.time())


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              state TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '', grp TEXT NOT NULL DEFAULT '',
              ref TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
              owner TEXT NOT NULL DEFAULT '', priority INTEGER NOT NULL DEFAULT 5,
              fields TEXT NOT NULL DEFAULT '{}', note TEXT NOT NULL DEFAULT '',
              created INTEGER NOT NULL, updated INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, item INTEGER, at INTEGER NOT NULL,
              actor TEXT NOT NULL DEFAULT '', old TEXT, new TEXT, note TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, worker TEXT NOT NULL,
              item INTEGER, pid INTEGER, started INTEGER NOT NULL, ended INTEGER,
              exit INTEGER, log TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
            """
        )

    # -- helpers -------------------------------------------------------------
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")

    @staticmethod
    def as_dict(row):
        if row is None:
            return None
        d = dict(row)
        d["fields"] = json.loads(d.get("fields") or "{}")
        return d

    def log(self, item, actor, old, new, note=""):
        self.db.execute(
            "INSERT INTO events(item, at, actor, old, new, note) VALUES (?,?,?,?,?,?)",
            (item, now(), actor, old, new, note),
        )

    def meta(self, k, v=None):
        if v is None:
            r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
            return r["v"] if r else None
        self.db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES (?,?)", (k, str(v)))

    # -- items ---------------------------------------------------------------
    def get(self, item_id):
        return self.as_dict(self.db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone())

    def add(self, state, title, kind="", grp="", ref="", priority=5, fields=None, note="", actor="",
            group_cap=None, blocked=()):
        """Add an item; refuses duplicates (same grp+ref still active), blocked groups and full groups."""
        self._tx()
        try:
            if grp and any(grp.lower().startswith(b.lower()) for b in blocked):
                raise ValueError(f"group {grp!r} is blocked in tanda.toml")
            if ref:
                dup = self.db.execute(
                    f"SELECT id, state FROM items WHERE grp=? AND ref=? AND state NOT IN {ACTIVE_EXCLUDED}",
                    (grp, ref)).fetchone()
                if dup:
                    raise ValueError(f"duplicate of #{dup['id']} ({dup['state']})")
            if grp and group_cap:
                n = self.db.execute(
                    f"SELECT COUNT(*) FROM items WHERE grp=? AND state NOT IN {ACTIVE_EXCLUDED}", (grp,)
                ).fetchone()[0]
                if n >= group_cap:
                    raise ValueError(f"group {grp!r} already has {n} active items (cap {group_cap})")
            t = now()
            cur = self.db.execute(
                "INSERT INTO items(state, kind, grp, ref, title, priority, fields, note, created, updated)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (state, kind, grp, ref, title, int(priority), json.dumps(fields or {}), note, t, t))
            self.log(cur.lastrowid, actor, None, state, note)
            self.db.execute("COMMIT")
            return cur.lastrowid
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def claim(self, states, to_state, owner):
        """Atomically take the best item in one of `states` and move it to `to_state`."""
        self._tx()
        try:
            q = ",".join("?" * len(states))
            row = self.db.execute(
                f"SELECT * FROM items WHERE state IN ({q}) ORDER BY priority, id LIMIT 1", states).fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            self.db.execute("UPDATE items SET state=?, owner=?, updated=? WHERE id=?",
                            (to_state, owner, now(), row["id"]))
            self.log(row["id"], owner, row["state"], to_state, "claimed")
            self.db.execute("COMMIT")
            return self.get(row["id"])
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def set(self, item_id, state, actor="", note="", fields=None, allowed_from=None):
        self._tx()
        try:
            row = self.db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if row is None:
                raise ValueError(f"no item #{item_id}")
            if allowed_from is not None and row["state"] not in allowed_from:
                raise ValueError(f"#{item_id} is {row['state']}; {state} only from {sorted(allowed_from)}")
            f = json.loads(row["fields"] or "{}")
            f.update(fields or {})
            self.db.execute("UPDATE items SET state=?, fields=?, note=?, updated=? WHERE id=?",
                            (state, json.dumps(f), note or row["note"], now(), item_id))
            self.log(item_id, actor, row["state"], state, note)
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def items(self, state=None):
        if state:
            rows = self.db.execute("SELECT * FROM items WHERE state=? ORDER BY priority, id", (state,))
        else:
            rows = self.db.execute("SELECT * FROM items ORDER BY id")
        return [self.as_dict(r) for r in rows]

    def count(self, states):
        q = ",".join("?" * len(states))
        return self.db.execute(f"SELECT COUNT(*) FROM items WHERE state IN ({q})", list(states)).fetchone()[0]

    def events(self, item_id=None, limit=200):
        if item_id is None:
            rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        else:
            rows = self.db.execute("SELECT * FROM events WHERE item=? ORDER BY id", (item_id,))
        return [dict(r) for r in rows]

    # -- runs (one row per agent invocation) ----------------------------------
    def run_start(self, role, worker, item, pid, log):
        cur = self.db.execute("INSERT INTO runs(role, worker, item, pid, started, log) VALUES (?,?,?,?,?,?)",
                              (role, worker, item, pid, now(), log))
        return cur.lastrowid

    def run_end(self, run_id, code):
        self.db.execute("UPDATE runs SET ended=?, exit=? WHERE id=?", (now(), code, run_id))

    def runs(self, limit=100):
        return [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]
