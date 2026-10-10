"""Lesson checks over the calls of a run_cases output file (live gate runs).

    python3 -m qa.check_run results/gate1.json results/policy-a-extracted.json

For each case: the call's event log (agent/customer lines, code steps per customer turn, node entries), the bank
ledger, then qa.lessons.check. Prints one line per case plus the transcript of failing ones (--show for all).
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import platform as P  # noqa: E402
from qa import lessons  # noqa: E402


def analyse(call):
    events, steps, cur, entries, last_url = [], [], None, {}, ""
    for e in P.events(call):
        role = e["role"]
        if role == "user":
            if cur is not None:
                steps.append(cur)
            cur = 0
            events.append(("customer", e.get("text") or "", e["node"]))
        elif role == "assistant" and e.get("text"):
            events.append(("agent", e["text"], e["node"]))
        elif role == "system":
            ev = e.get("event") or {}
            if ev.get("event") == "node_enter":
                entries[ev.get("node")] = entries.get(ev.get("node"), 0) + 1
            if ev.get("event") == "function_call_start" and ev.get("function") == "code_exec" and cur is not None:
                cur += 1
            if ev.get("event") == "function_call_start" and ev.get("function") == "api_call":
                last_url = (ev.get("args") or {}).get("url") or ""
            if ev.get("event") == "function_call_complete" and ev.get("function") == "api_call":
                res = ev.get("result") or {}
                data = res.get("data") or {}
                url = ((ev.get("args") or {}).get("url") or last_url)
                tool = url.rstrip("/").split("/")[-1] if url else "api"
                ok = res.get("status") == "success" and (data.get("ok") is not False)
                events.append(("tool", "%s:%s" % (tool, "ok" if ok else "fail"), e["node"]))
    if cur is not None:
        steps.append(cur)
    return events, steps, entries


def transcript(events):
    return "\n".join("   %-8s %s" % (k, t) for k, t, _ in events)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("policy")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    run = json.load(open(a.run))
    pol = json.load(open(a.policy))
    bad = 0
    for row in run["rows"]:
        if not row.get("call_id"):
            print("NOCALL", row["id"])
            continue
        call = P.get_call(row["call_id"])
        ev, steps, entries = analyse(call)
        led = P.ledger(row["customer_id"])
        fails = lessons.check(ev, led, pol, code_steps=steps, max_node_entries=entries)
        bad += bool(fails)
        print("%s %s | run:%s | code steps per turn %s | %s" % ("OK  " if not fails else "FAIL", row["id"],
                                                               "pass" if row["pass"] else "fail", steps, fails or ""))
        if fails or a.show or not row["pass"]:
            print(transcript(ev))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
