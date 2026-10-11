"""Score a live run whose poller died (platform 504s), from what tools/run_cases_retry.py saved before polling.

    python3 tools/recover_run.py results/c2v3/focusB-pieces.json.pending.json [--simulation <id>]
    python3 tools/recover_run.py results/c2v3/focusB-pieces.json --simulation <id>   # no pending file: the customer
                                                                                     # ids are read from each call's log

Reads the practice customers of the run (<out>.pending.json), waits for the simulation to finish, then scores every
case exactly like tools/run_cases.py: the bank's ledger (tools/score.py) plus the judge's verdict. Writes <out> with
"recovered": true. Read-only: it never starts a simulation.
"""
import argparse
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import run_cases_retry  # noqa: E402,F401  (GET retries)
import freya  # noqa: E402
from score import score_ledger  # noqa: E402
import score  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pending")
    ap.add_argument("--simulation")
    a = ap.parse_args()
    if a.pending.endswith(".pending.json"):
        rec = json.load(open(a.pending))
        out = a.pending[:-len(".pending.json")]
    else:
        rec, out = {"variables_by_persona": None, "agent_id": None}, a.pending
    sim_id = a.simulation or rec.get("simulation_id")
    if not sim_id:
        sys.exit("no simulation id recorded; pass --simulation")
    personas = json.load(open(ROOT / ".personas.json"))
    case_of = dict((pid, key.split(":")[0]) for key, pid in personas.items())
    cases = dict((c["id"], c) for c in json.load(open(ROOT / "public-test-set.json")))
    while True:
        s = freya.api("GET", "/api/v2/simulations/%s" % sim_id)
        s = s.get("simulation") or s
        if s.get("status") in ("completed", "failed", "paused"):
            break
        time.sleep(20)
    its = freya.api("GET", "/api/v2/simulations/%s/iterations" % sim_id)
    it = (its.get("iterations") or its.get("items") or its)[0]
    judge = dict((r["personaId"], r) for r in freya.get_iteration(sim_id, it["id"])["runs"])
    if not rec.get("variables_by_persona"):
        rec["agent_id"] = s.get("agentId")
        rec["variables_by_persona"] = {}
        for pid, j in judge.items():
            cid = None
            for m in freya.get_call(j["callId"]).get("messages") or []:
                if m.get("role") == "system" and '"customer_id"' in (m.get("message") or ""):
                    try:
                        cid = json.loads(m["message"])["variable_table"]["customer_id"]["value"]
                        break
                    except Exception:
                        continue
            rec["variables_by_persona"][pid] = {"customer_id": cid}
    rows = []
    for pid, variables in rec["variables_by_persona"].items():
        cid = case_of.get(pid)
        c = cases[cid]
        led = score.http("/v1/practice/ledger/" + variables["customer_id"])
        r = score_ledger(c, led)
        j = judge.get(pid, {})
        if j.get("outcome") != "pass":
            r["failed"].append("conversation: " + " ".join(str(j.get("reason") or "no verdict").split())[:400])
        rows.append({"id": cid, "level": c["level"], "family": c["family"], "pass": not r["failed"], "failed": r["failed"],
                     "call_id": j.get("callId"), "tools": [x["tool"] for x in led["calls"]],
                     "customer_id": variables["customer_id"]})
        print(("PASS" if not r["failed"] else "FAIL"), cid, "|", " > ".join(x["tool"] for x in led["calls"]))
        for f in r["failed"]:
            print("       -", f[:260])
    rows.sort(key=lambda x: x["id"])
    json.dump({"agent_id": rec["agent_id"], "simulation_id": sim_id, "iteration_id": it["id"], "status": s.get("status"),
               "seconds": None, "passed": sum(r["pass"] for r in rows), "total": len(rows), "runs": 1, "rows": rows,
               "all_rows": [rows], "recovered": True, "agent_version": it.get("agentVersionNumber")},
              open(out, "w"), indent=1)
    print("%d / %d passed (recovered), simulation %s, agent version %s" % (sum(r["pass"] for r in rows), len(rows), sim_id,
                                                                          it.get("agentVersionNumber")))


if __name__ == "__main__":
    main()
