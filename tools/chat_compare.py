"""Conversation-quality comparison of two agent versions over the chat API (webCall), with the platform's own
post-call analysis.

    python3 tools/chat_compare.py --out qa/chat-compare/run.json

Each scenario runs once per version on a fresh practice customer (same case, same customer words). The customer is a
small deterministic responder: it answers whatever the agent asks with the scenario's fixed lines, so both versions
hear the same customer. Every chat is closed with /chat/end, which runs the platform's post-call analysis; the
sentiment is read back from the call's own tags (`{"tag": "sentiment", "source": "system"}`) — never assigned here.
A call without that tag after the wait is reported as unmeasured. The bank ledger of each chat is scored with the
kit's scorer as a functional sanity check (one run each: this is not a three-run validation).
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import run_cases_retry  # noqa: E402,F401  (GET retries for the platform and the practice bank)
import freya  # noqa: E402
import score  # noqa: E402
from builder import platform as P  # noqa: E402

VERSIONS = {  # workflow ids; the chat runs each workflow's published version
    "v5": {"A": "eb8c91b8-ef17-4e43-ad6b-831096b299dd", "B": "310fbf87-6c7c-4aef-bef3-fbc5709842e3"},
    "c3.1": {"A": "7fd77242-9be6-4fe1-805b-673e9b99c08c", "B": "0a367732-07cf-45da-a6e0-f72de353077a"},
}
SCENARIOS = [
    {"id": "S1 hardship + discount question", "case": "PUB-05", "brief": "A",
     "confirm": "Yes, this is Tomas Novak.", "dob": ["Nine September nineteen ninety."], "phone": "Eight eight four six.",
     "first": "I lost my job last month and I cannot pay anything.",
     "support": "No, I do not want to be transferred. Can I get a discount?"},
    {"id": "S2 'cannot pay today because my salary...'", "case": "PUB-04", "brief": "A",
     "confirm": "Yes, speaking.", "dob": ["30 January 1984."], "phone": "2219.",
     "first": "I cannot pay today because my salary arrives on the sixth of November and I can pay then.",
     "day": "The sixth of November."},
    {"id": "S3 event date before the date of birth", "case": "PUB-01", "brief": "A",
     "confirm": "Yes, speaking.",
     "dob": ["My cousin's wedding is coming up on the thirtieth, so I am a bit distracted. My date of birth is the "
             "fourteenth of March nineteen eighty-eight.", "The fourteenth of March nineteen eighty-eight."],
     "phone": "4471.", "first": "Yes, I can pay the full amount today."},
    {"id": "S4 month without a day (two products)", "case": "PUB-13", "brief": "B",
     "confirm": "Yes, this is Elena Rossi.", "dob": ["8 January 1991."], "phone": "6604.",
     "first": "Not today. I want to pay both of them in October.", "day": "The thirtieth."},
    {"id": "S5 control: shared day for three products", "case": "PUB-11", "brief": "B",
     "confirm": "Yes, this is Sofia Almeida.", "dob": ["3 June 1987."], "phone": "2288.",
     "first": "Not today, but I can pay all three this Friday."},
]
MAX_TURNS = 16


def respond(agent, sc, mem):
    """The customer's next line for the agent's last message, or None when the agent said goodbye."""
    t = (agent or "").lower()
    if "goodbye" in t:
        return None
    if "am i speaking with" in t or "may i speak with" in t:
        return sc["confirm"]
    if "date of birth" in t:
        mem["dob"] = mem.get("dob", -1) + 1
        return sc["dob"][min(mem["dob"], len(sc["dob"]) - 1)]
    if "last four digits" in t:
        return sc["phone"]
    if "identity is verified" in t:
        return "Okay, what is this about?"
    if "connect you with" in t:
        return sc.get("support", "No, thank you.")
    if "which exact day" in t or "which day in" in t:
        return sc.get("day", "The sixteenth of October.")
    if "do you confirm" in t:
        return "Yes, I confirm."
    if "can you make this payment today" in t or "can you pay all of them today" in t:
        mem["first"] = mem.get("first", 0) + 1
        return sc["first"] if mem["first"] == 1 else "Yes."
    if "latest date" in t or "would that work" in t or "can you pay by then" in t or "did you mean" in t:
        return "Yes, that works."
    if "could you pay" in t:
        return "Yes, I can do that."
    if "what would you like to change" in t:
        return "Nothing, it is fine as it is."
    mem["other"] = mem.get("other", 0) + 1
    return "Okay." if mem["other"] < 3 else None


def turn(workflow_id, message, variables, call_id):
    """One chat turn, never repeated blindly: after a gateway timeout the call's own log says whether it ran."""
    try:
        r = P.chat(workflow_id, message, variables=variables, call_id=call_id, retries=0, timeout_s=120)
        return r.get("callId") or call_id, r.get("response") or "", None
    except RuntimeError as e:
        if not call_id:
            return None, "", "first turn failed: %s" % str(e)[:80]
        time.sleep(20)
        msgs = [m for m in (P.get_call(call_id).get("messages") or []) if m.get("role") in ("user", "assistant")]
        if msgs and msgs[-1]["role"] == "assistant" and any(m["role"] == "user" and m.get("message") == message for m in msgs):
            return call_id, msgs[-1].get("message") or "", "reply read from the call log after: %s" % str(e)[:60]
        return call_id, "", "turn failed: %s" % str(e)[:80]


def run_chat(version, sc):
    session = score.http("/v1/practice/sessions", {"case": sc["case"]})["variables"]
    wid = VERSIONS[version][sc["brief"]]
    call_id, agent, notes, transcript, mem = None, "", [], [], {}
    call_id, agent, err = turn(wid, "Hello?", session, None)
    if err:
        return {"version": version, "scenario": sc["id"], "error": err}
    transcript.append(("customer", "Hello?"))
    transcript.append(("agent", agent))
    for _ in range(MAX_TURNS):
        line = respond(agent, sc, mem)
        if line is None:
            break
        transcript.append(("customer", line))
        call_id, agent, err = turn(wid, line, None, call_id)
        if err:
            notes.append(err)
            if not agent:
                break
        transcript.append(("agent", agent))
    end = P.chat_end(call_id)
    led = score.http("/v1/practice/ledger/" + session["customer_id"])
    case = next(c for c in json.load(open(ROOT / "public-test-set.json")) if c["id"] == sc["case"])
    return {"version": version, "scenario": sc["id"], "case": sc["case"], "call_id": call_id,
            "customer_id": session["customer_id"], "chat_end": end, "notes": notes, "transcript": transcript,
            "ledger": {"outcome": led.get("outcome"), "reason": led.get("reason"),
                       "promises": led.get("promises"), "notes": led.get("notes"),
                       "tools": [c["tool"] for c in led.get("calls") or []]},
            "ledger_check": score.score_ledger(case, led)}


def analysis_of(call_id):
    c = P.get_call(call_id)
    tags = [t for t in (c.get("tags") or []) if t.get("tag") == "sentiment"]
    a = c.get("analysis") if isinstance(c.get("analysis"), dict) else {}
    return {"sentiment": tags[0] if tags else None, "summary": (a or {}).get("summary"), "type": c.get("type"),
            "ended": c.get("endedReason"), "duration": c.get("duration")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--wait", type=int, default=600, help="seconds to wait for the post-call analysis")
    a = ap.parse_args()
    results = []
    for sc in SCENARIOS:
        for version in ("v5", "c3.1"):
            r = run_chat(version, sc)
            print("%-5s %-45s call %s ledger %s %s" % (version, sc["id"][:45], (r.get("call_id") or "-")[:8],
                                                       "pass" if (r.get("ledger_check") or {}).get("pass") else "FAIL",
                                                       r.get("error") or r.get("notes") or ""), flush=True)
            results.append(r)
            pathlib.Path(a.out).write_text(json.dumps({"results": results}, indent=1))
    deadline = time.time() + a.wait
    while True:  # the platform's post-call analysis is asynchronous: wait for it, never fill it in
        for r in results:
            if r.get("call_id"):
                r["analysis"] = analysis_of(r["call_id"])
        if all((r.get("analysis") or {}).get("sentiment") for r in results if r.get("call_id")) or time.time() > deadline:
            break
        time.sleep(30)
    pathlib.Path(a.out).write_text(json.dumps({"results": results, "waited_s": a.wait}, indent=1))
    for r in results:
        s = (r.get("analysis") or {}).get("sentiment")
        print("%-5s %-45s sentiment %s" % (r["version"], r["scenario"][:45], (s or {}).get("value") if s else "UNMEASURED"))


if __name__ == "__main__":
    main()
