"""Stands in for a real agent CLI: reads TANDA_ROLE / TANDA_ITEM and reports through the tanda CLI."""
import os
import random
import subprocess
import sys
import time

tanda = [sys.executable, "-m", "tanda"]
role, item = os.environ["TANDA_ROLE"], os.environ.get("TANDA_ITEM")
time.sleep(random.uniform(1, 3))  # "thinking"

if role == "scout":
    for n, title in enumerate(["Fix off-by-one in pagination", "Handle empty config file",
                               "Retry on HTTP 429", "Typo in error message", "Support UTF-8 paths"], 1):
        subprocess.run(tanda + ["add", "--title", title, "--group", "demo/app", "--ref", str(100 + n)])
elif role == "builder":
    verdict = random.choices(["BUILT", "DROPPED"], [5, 1])[0]
    subprocess.run(tanda + ["set", item, verdict, "--note", "fake build", "--field", f"commit={random.randrange(16**7):07x}"])
elif role == "reviewer":
    verdict = random.choices(["DONE", "FIX"], [3, 1])[0]
    subprocess.run(tanda + ["set", item, verdict, "--note", "looks good" if verdict == "DONE" else "add a test"])
