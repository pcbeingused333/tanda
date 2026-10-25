import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tanda import config  # noqa: E402
from tanda.runner import Runner  # noqa: E402
from tanda.store import Store  # noqa: E402


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.st = Store(os.path.join(self.dir, "q.db"))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_claim_is_exclusive_and_ordered(self):
        a = self.st.add("TODO", "low", priority=7)
        b = self.st.add("TODO", "high", priority=1)
        self.assertEqual(self.st.claim(["TODO"], "WIP", "w1")["id"], b)
        self.assertEqual(self.st.claim(["TODO"], "WIP", "w2")["id"], a)
        self.assertIsNone(self.st.claim(["TODO"], "WIP", "w3"))

    def test_guards(self):
        self.st.add("TODO", "x", grp="org/repo", ref="1")
        with self.assertRaises(ValueError):
            self.st.add("TODO", "dup", grp="org/repo", ref="1")
        with self.assertRaises(ValueError):
            self.st.add("TODO", "frozen", grp="frozen-org/lib", ref="2", blocked=["frozen-org/"])
        self.st.add("TODO", "y", grp="org/repo", ref="2", group_cap=2)
        with self.assertRaises(ValueError):
            self.st.add("TODO", "z", grp="org/repo", ref="3", group_cap=2)

    def test_set_from_wrong_state_is_refused(self):
        i = self.st.add("TODO", "x")
        with self.assertRaises(ValueError):
            self.st.set(i, "DONE", allowed_from={"REVIEW"})
        self.st.set(i, "DONE", fields={"pr": "#9"})
        self.assertEqual(self.st.get(i)["fields"]["pr"], "#9")
        self.assertEqual([e["new"] for e in self.st.events(i)], ["TODO", "DONE"])


class RunTest(unittest.TestCase):
    def test_hello_example_drains(self):
        d = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(ROOT, "tanda", "examples", "hello"), d, dirs_exist_ok=True)
            os.environ["PYTHONPATH"] = ROOT
            cfg = config.load(os.path.join(d, "tanda.toml"))
            self.assertEqual(Runner(cfg, echo=lambda *_: None).run(), "drained")
            st = Store(cfg.db)
            self.assertEqual(len(st.items()), 5)
            self.assertEqual(st.count(["TODO", "FIX", "BUILDING", "BUILT", "REVIEW"]), 0)
            self.assertTrue(all(i["state"] in ("DONE", "DROPPED", "HOLD") for i in st.items()))
        finally:
            shutil.rmtree(d)

    def test_agent_without_verdict_goes_to_hold(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "tanda.toml"), "w") as f:
                f.write('[tanda]\npoll_seconds = 0.2\n[agents.mute]\ncmd = ["true"]\n'
                        '[roles.builder]\nagent = "mute"\nclaims = ["TODO"]\nworking = "WIP"\nverdicts = ["DONE"]\n')
            cfg = config.load(os.path.join(d, "tanda.toml"))
            i = Store(cfg.db).add("TODO", "x")
            Runner(cfg, echo=lambda *_: None).run()
            self.assertEqual(Store(cfg.db).get(i)["state"], "HOLD")
        finally:
            shutil.rmtree(d)

    def test_agent_cannot_give_another_roles_verdict(self):
        d = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(ROOT, "tanda", "examples", "hello"), d, dirs_exist_ok=True)
            cfg = config.load(os.path.join(d, "tanda.toml"))
            i = Store(cfg.db).add("TODO", "x")
            env = {**os.environ, "PYTHONPATH": ROOT, "TANDA_CONFIG": cfg.path, "TANDA_ROLE": "builder"}
            r = subprocess.run([sys.executable, "-m", "tanda", "set", str(i), "DONE"], env=env,
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("can only set", r.stderr)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
