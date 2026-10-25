"""Loads tanda.toml. See examples/ for complete files."""
import os
import tomllib
from dataclasses import dataclass, field

# Ready-made command lines for common agent CLIs. {model} and {prompt} are filled in per run.
# Any CLI works as long as it takes a prompt, can run shell commands, and exits when done.
AGENT_PRESETS = {
    "claude": ["claude", "-p", "--model", "{model}", "{prompt}"],
    "opencode": ["opencode", "run", "--model", "{model}", "{prompt}"],  # any provider: xai/grok-*, deepseek/*, ...
    "codex": ["codex", "exec", "--model", "{model}", "{prompt}"],
}


@dataclass
class Role:
    name: str
    agent: list
    model: str = ""
    prompt: str = ""
    mode: str = "worker"           # "worker": claims items in a loop · "once": runs one time per tanda
    count: int = 1
    claims: list = field(default_factory=list)
    working: str = ""
    verdicts: list = field(default_factory=list)
    timeout_minutes: int = 60


@dataclass
class Config:
    path: str
    root: str
    name: str
    db: str
    initial_state: str
    hold_state: str
    wait_states: list
    poll_seconds: float
    max_hours: float
    group_cap: int
    blocked_groups: list
    roles: dict
    states: list

    def role(self, name):
        if name not in self.roles:
            raise SystemExit(f"tanda: unknown role {name!r} (have: {', '.join(self.roles)})")
        return self.roles[name]

    def prompt_text(self, role):
        if not role.prompt:
            return ""
        with open(os.path.join(self.root, role.prompt), encoding="utf-8") as f:
            return f.read()


def find_config(start=None):
    env = os.environ.get("TANDA_CONFIG")
    if env:
        return os.path.abspath(env)
    d = os.path.abspath(start or os.getcwd())
    while True:
        p = os.path.join(d, "tanda.toml")
        if os.path.exists(p):
            return p
        if os.path.dirname(d) == d:
            raise SystemExit("tanda: no tanda.toml here or in a parent directory (try `tanda init`)")
        d = os.path.dirname(d)


def load(path=None):
    path = path or find_config()
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    root = os.path.dirname(os.path.abspath(path))
    t = raw.get("tanda", {})
    limits = raw.get("limits", {})
    agents = {**AGENT_PRESETS, **{k: v["cmd"] for k, v in raw.get("agents", {}).items()}}
    roles = {}
    for name, r in raw.get("roles", {}).items():
        a = r.get("agent", "claude")
        cmd = a if isinstance(a, list) else agents.get(a)
        if cmd is None:
            raise SystemExit(f"tanda: role {name}: unknown agent {a!r} (define it under [agents.{a}])")
        roles[name] = Role(
            name=name, agent=cmd, model=r.get("model", ""), prompt=r.get("prompt", ""),
            mode=r.get("mode", "worker"), count=int(r.get("count", 1)), claims=r.get("claims", []),
            working=r.get("working", f"{name.upper()}-WIP"), verdicts=r.get("verdicts", []),
            timeout_minutes=int(r.get("timeout_minutes", 60)))
        if roles[name].mode == "worker" and not roles[name].claims:
            raise SystemExit(f"tanda: worker role {name} needs `claims = [...]`")
    hold = t.get("hold_state", "HOLD")
    states = [t.get("initial_state", "TODO")]
    for r in roles.values():
        for s in r.claims + ([r.working] if r.mode == "worker" else []) + r.verdicts:
            if s not in states and s not in (hold, "DONE", "DROPPED"):
                states.append(s)
    for s in t.get("extra_states", []) + [hold, "DONE", "DROPPED"]:
        if s not in states:
            states.append(s)
    return Config(
        path=os.path.abspath(path), root=root, name=t.get("name", os.path.basename(root)),
        db=os.path.join(root, t.get("db", ".tanda/queue.db")),
        initial_state=t.get("initial_state", "TODO"), hold_state=hold,
        wait_states=t.get("wait_states", []), poll_seconds=float(t.get("poll_seconds", 5)),
        max_hours=float(t.get("max_hours", 4)), group_cap=int(limits.get("group_cap", 0)),
        blocked_groups=limits.get("blocked_groups", []), roles=roles, states=states)
