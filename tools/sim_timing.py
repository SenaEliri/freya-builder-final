"""Where the time of a live run went: queue, calls, judge analysis, polling; and per-turn latency inside the calls.

    python3 tools/sim_timing.py results/c2v3/focusA-plain.json [more run files ...]

From the platform's own timestamps (read-only GETs):
  queue     simulation created -> iteration started (the platform had not started any call yet)
  calls     iteration started -> last call ended (all calls; they run concurrently)
  analysis  last call ended -> iteration completed (the judge reading the transcripts)
  polling   the runner's wall time (run file 'seconds') minus created -> completed (our 10 s poll and the GETs)
Per customer turn, from the call's event log (secondsFromStart): extraction = customer message -> first routing
after it (the platform's model); decide = that -> code step finished; reply = customer message -> agent message.
"""
import datetime
import json
import os
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya  # noqa: E402

if os.environ.get("FREYA_WORKSPACE_ID"):
    freya._ws = os.environ["FREYA_WORKSPACE_ID"]


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def secs(a, b):
    return round((b - a).total_seconds(), 1) if a and b else None


def turns(call):
    """Per customer turn: (extraction_s, decide_s, reply_s)."""
    out, cur = [], None
    for m in call.get("messages") or []:
        t, role = m.get("secondsFromStart"), m.get("role")
        if t is None:
            continue
        if role == "user":
            cur = {"user": t}
        elif role == "system" and cur is not None:
            try:
                ev = json.loads(m.get("message") or "{}")
            except Exception:
                ev = {}
            if ev.get("event") == "route_evaluated" and "routed" not in cur:
                cur["routed"] = t
            if ev.get("function") == "code_exec" and ev.get("event") in ("function_call_complete", "function_call_error"):
                cur["code"] = t
        elif role == "assistant" and cur is not None:
            out.append((round(cur["routed"] - cur["user"], 1) if "routed" in cur else None,
                        round(cur["code"] - cur["routed"], 1) if "code" in cur and "routed" in cur else None,
                        round(t - cur["user"], 1)))
            cur = None
    return out


def med(xs):
    xs = [x for x in xs if x is not None]
    return (round(statistics.median(xs), 1), round(max(xs), 1)) if xs else (None, None)


def main(paths):
    print("| run file | simulation | queue s | calls s | analysis s | polling s | runner s | reply median/max s | "
          "extraction median/max s | decide median/max s |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for p in paths:
        r = json.load(open(p))
        sid = r["simulation_id"]
        sim = freya.api("GET", "/api/v2/simulations/%s" % sid)
        sim = sim.get("simulation") or sim
        its = freya.api("GET", "/api/v2/simulations/%s/iterations" % sid)
        its = its.get("iterations") or its.get("items") or its
        it = [i for i in its if i["id"] == r.get("iteration_id")] or its[:1]
        it = it[0]
        runs = freya.get_iteration(sid, it["id"])["runs"]
        created, started, completed = ts(sim.get("createdAt")), ts(it.get("startedAt")), ts(it.get("completedAt"))
        ends = [ts(x.get("endedAt")) for x in runs if x.get("endedAt")]
        last_end = max(ends) if ends else None
        per_turn = []
        for x in runs:
            if x.get("callId"):
                try:
                    per_turn += turns(freya.get_call(x["callId"]))
                except Exception:
                    pass
        total = secs(created, completed)
        poll = round(r["seconds"] - total, 1) if total is not None and r.get("seconds") is not None else None
        rep, ext, dec = med([t[2] for t in per_turn]), med([t[0] for t in per_turn]), med([t[1] for t in per_turn])
        print("| %s | %s | %s | %s | %s | %s | %s | %s/%s | %s/%s | %s/%s |" % (
            pathlib.Path(p).name, sid[:8], secs(created, started), secs(started, last_end), secs(last_end, completed),
            poll, r.get("seconds"), rep[0], rep[1], ext[0], ext[1], dec[0], dec[1]))


if __name__ == "__main__":
    main(sys.argv[1:])
