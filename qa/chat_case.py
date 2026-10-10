"""Drive one practice customer through a live workflow with the chat API (no simulation queue).

    python3 -m qa.chat_case <slot> PUB-01 [--brief A]

The customer lines come from tests/test_walk_public.py SCRIPTS (only the text; Freya's real extractor
interprets them). Afterwards: the call's event log, the bank ledger, score_ledger and the lesson checks.
A 504 from the chat route is not retried (the turn may have run); the call log is polled instead.
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import platform as P  # noqa: E402
from qa import lessons  # noqa: E402
from tools.score import score_ledger  # noqa: E402


def turn(workflow_id, msg, variables, call_id, timeout_s=75):
    t0 = time.time()
    body = {"workflowId": workflow_id, "message": msg}
    if call_id:
        body["callId"] = call_id
    else:
        body["customerVariables"] = variables
    try:
        r = P.freya.api("POST", "/api/v2/chat/message", body)
        return r, round(time.time() - t0, 1), None
    except RuntimeError as e:
        return None, round(time.time() - t0, 1), str(e)[:160]


def call_events(call):
    """(kind, text, node) list for lesson checks, tool results included."""
    out = []
    for e in P.events(call):
        if e["role"] == "assistant" and e.get("text"):
            out.append(("agent", e["text"], e["node"]))
        elif e["role"] == "user":
            out.append(("customer", e.get("text") or "", e["node"]))
        elif e["role"] == "system":
            ev = e["event"]
            if ev.get("event") == "function_call_complete" and ev.get("function") == "api_call":
                pass
    return out


def tool_events_from_ledger(led):
    return [("tool", "%s:%s:%s" % (c.get("tool"), "ok" if (c.get("result") or {}).get("ok") else "fail",
                                   (c.get("args") or {}).get("product_id", "")), "") for c in led.get("calls") or []]


def merge(events, led):
    """Interleave tool events with agent lines in order of recording claims: tools first are conservative."""
    return tool_events_from_ledger(led) + events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slot")
    ap.add_argument("case")
    ap.add_argument("--policy")
    a = ap.parse_args()
    from tests.test_walk_public import SCRIPTS, CASES, POL
    state = json.loads((ROOT / ".freya-agents.json").read_text())
    wid = state[a.slot]["workflow_id"]
    case = CASES[a.case]
    pol = json.load(open(a.policy)) if a.policy else POL[case["brief"]]
    variables = P.practice_session(a.case)
    call_id, log = None, []
    r, secs, err = turn(wid, "Hello?", variables, None)
    if r:
        call_id = r.get("callId")
        log.append(("Hello?", r.get("response"), secs))
        print("AGENT(%.1fs): %s" % (secs, r.get("response")))
    else:
        print("first turn failed:", err)
        return
    for msg, _ex in SCRIPTS[a.case]:
        print("CUSTOMER:", msg)
        r, secs, err = turn(wid, msg, variables, call_id)
        if r is None:
            print("  (chat route: %s after %.1fs; not retried)" % (err, secs))
            time.sleep(5)
            call = P.get_call(call_id)
            if call.get("endedReason"):
                print("  call ended:", call.get("endedReason"))
                break
            continue
        print("AGENT(%.1fs): %s" % (secs, r.get("response")))
        if r.get("endedByAgent"):
            break
    time.sleep(6)
    call = P.get_call(call_id)
    led = P.ledger(variables["customer_id"])
    sc = score_ledger(case, led)
    ev = merge(call_events(call), led)
    fails = lessons.check(ev, led, pol)
    out = ROOT / "results" / ("chat-%s-%s-%s.json" % (a.slot, a.case, time.strftime("%H%M%S")))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"call_id": call_id, "events": P.events(call), "ledger": led, "score": sc, "lessons": fails},
                              indent=1, ensure_ascii=False))
    print("ledger:", led.get("outcome"), led.get("reason"), led.get("promises"), led.get("notes"), led.get("callbacks"), led.get("transfers"))
    print("tools:", [c.get("tool") + ("" if (c.get("result") or {}).get("ok") else "(fail)") for c in led.get("calls") or []])
    print("score:", sc)
    print("lesson checks:", fails or "ok")
    print("ended:", call.get("endedReason"), "| log:", out.name)


if __name__ == "__main__":
    main()
