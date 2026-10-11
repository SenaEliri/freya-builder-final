"""tools/run_cases.py with retries for transient platform errors, and a wait for any running simulation first.

    python3 tools/run_cases_retry.py <agent_id> --brief A --only PUB-06 --out results/x.json   # same arguments

Seen on 11 Oct: GET /api/v2/simulations/{id} answered HTTP 504 while the simulation kept running; the kit's runner
then stopped without scoring it. Only GET requests are retried (5xx, timeouts, connection errors), so a retry can
never start a second simulation (the one POST retried opens a practice session). The kit files (freya.py, tools/run_cases.py) are used unmodified.
"""
import json
import os
import pathlib
import re
import socket
import sys
import time
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import freya  # noqa: E402
import run_cases  # noqa: E402
import score  # noqa: E402

TRIES, BACKOFF_S, MAX_WAIT_S = 20, 15, 120


def _retrying(fn, is_get):
    def call(*args, **kw):
        for i in range(TRIES):
            try:
                return fn(*args, **kw)
            except RuntimeError as e:
                if not is_get(args, kw) or not re.search(r"-> 5\d\d", str(e)) or i == TRIES - 1:
                    raise
                err = str(e)[:120]
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ValueError) as e:
                if not is_get(args, kw) or i == TRIES - 1:
                    raise
                err = repr(e)[:120]
            wait = min(MAX_WAIT_S, BACKOFF_S * (i + 1))
            print("transient platform error on a GET, retrying in %d s: %s" % (wait, err), flush=True)
            time.sleep(wait)
    return call


freya.api = _retrying(freya.api, lambda a, k: (a[0] if a else k.get("method")) == "GET")
# the practice bank: reads, and opening a practice session (a fresh synthetic customer, nothing scored yet)
run_cases.http = score.http = _retrying(score.http, lambda a, k: (len(a) < 2 and k.get("body") is None) or
                                        (a and a[0] == "/v1/practice/sessions"))


def _out_path():
    a = sys.argv
    return a[a.index("--out") + 1] if "--out" in a and a.index("--out") + 1 < len(a) else None


_run_simulation = freya.run_simulation


def run_simulation_recorded(agent_id, name, variables_by_persona, *a, **k):
    """Keep the practice customers of this run on disk before polling, so a run whose poller dies can still be scored
    from the bank's ledgers (tools/recover_run.py)."""
    out = _out_path()
    rec = {"agent_id": agent_id, "name": name, "variables_by_persona": variables_by_persona, "argv": sys.argv[1:]}
    if out:
        pathlib.Path(out + ".pending.json").write_text(json.dumps(rec, indent=1))
    orig_api = freya.api

    def api_seeing_sim(method, path, body=None, **params):  # note the simulation id as soon as it exists
        r = orig_api(method, path, body, **params)
        if out and method == "POST" and path == "/api/v2/simulations":
            sim = (r.get("simulation") or r) if isinstance(r, dict) else {}
            rec["simulation_id"] = sim.get("id")
            pathlib.Path(out + ".pending.json").write_text(json.dumps(rec, indent=1))
        return r
    freya.api = api_seeing_sim
    try:
        return _run_simulation(agent_id, name, variables_by_persona, *a, **k)
    finally:
        freya.api = orig_api


freya.run_simulation = run_simulation_recorded


def wait_for_idle_workspace():
    ws = os.environ.get("FREYA_WORKSPACE_ID") or freya.workspace_id()
    while True:
        r = freya.api("GET", "/api/v2/simulations", workspaceId=ws, status="running")
        running = r.get("simulations") or r.get("items") or []
        if not running:
            return
        print("simulation %s is running in this workspace; waiting 60 s" % running[0].get("id"), flush=True)
        time.sleep(60)


if __name__ == "__main__":
    wait_for_idle_workspace()
    run_cases.main()
