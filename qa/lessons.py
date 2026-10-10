"""Automatic lesson checks, run at every gate over every transcript and ledger (local or live).

Input: a list of events [(kind, text, node)] where kind is agent | customer | tool, and tool texts are
"<tool>:<ok|fail>[:<product_id>]"; plus the ledger dict and the policy.
"""
import re

RECORD_WORDS = re.compile(r"(promise|payment|arrangement)[^.?!]{0,80}\b(recorded|saved|booked|registered|logged|set up|in place)\b|"
                          r"\b(recorded|saved|booked|registered|logged)\b[^.?!]{0,40}(promise|payment)", re.I)
NON_ENGLISH_CHARS = re.compile("[\u011f\u00fc\u015f\u0131\u00f6\u00e7\u011e\u00dc\u015e\u0130\u00d6\u00c7]")
NON_ENGLISH_WORDS = re.compile(r"\b(bir|saniye|l\u00fctfen|lutfen|merhaba|tamam|te\u015fekk\u00fcr|tesekkur|evet|hay\u0131r|hayir)\b")


def check(events, ledger, policy, code_steps=None, max_node_entries=None):
    fails = []
    ok_promises = 0
    seen_agent = {}
    for kind, text, node in events:
        if kind == "tool":
            if text.startswith("create_promise:ok"):
                ok_promises += 1
            continue
        if kind != "agent":
            continue
        if RECORD_WORDS.search(text or "") and ok_promises == 0 and "not record" not in (text or "").lower() \
                and "could not" not in (text or "").lower():
            fails.append("L1 'recorded' said before any successful create_promise: %r" % text[:120])
        elif re.search(r"\brecorded\b", text or "", re.I) and ok_promises == 0:
            fails.append("L1 the word 'recorded' before any successful create_promise (judges read it literally): %r"
                         % text[:120])
        seen_agent[text] = seen_agent.get(text, 0) + 1
        if NON_ENGLISH_CHARS.search(text or "") or NON_ENGLISH_WORDS.search((text or "").lower()):
            fails.append("L13 non-English agent line: %r" % text[:120])
    for t, n in seen_agent.items():
        if n > 2:
            fails.append("L2 agent message repeated %d times: %r" % (n, t[:100]))
    if max_node_entries:
        for node, n in max_node_entries.items():
            if n > 25:
                fails.append("L2 node %s entered %d times" % (node, n))
    # L5: read-back equals what was written
    readbacks = [t for k, t, _ in events if k == "agent" and policy and _is_readback(t, policy)]
    if ledger and ledger.get("promises") and readbacks:
        last = readbacks[-1]
        for p in ledger["promises"]:
            amt = _money_forms(p["amount"])
            if not any(a in last for a in amt):
                fails.append("L5 written amount %s not in the last read-back: %r" % (p["amount"], last[:160]))
            if not _date_in(p["date"], last):
                fails.append("L5 written date %s not in the last read-back: %r" % (p["date"], last[:160]))
    if ledger and ledger.get("promises") and not readbacks:
        fails.append("L5 promise written without a read-back")
    # L6: required sentences on their paths
    if policy and ledger:
        agent_text = " ".join(t for k, t, _ in events if k == "agent")
        L = policy["lines"]
        if ledger.get("promises") and L["after_promise"] not in agent_text:
            fails.append("L6 after-promise sentence missing")
        sit = _situation(ledger, policy)
        req = {"id_failed": ["id_fail"], "deceased": ["deceased"], "paid": ["paid_reply"]}.get(sit, [])
        for k in req:
            if L[k] not in agent_text:
                fails.append("L6 required sentence %s missing on the %s path" % (k, sit))
        if not agent_text.startswith(re.sub(r"\{\w+\}", "", L["opening"]).split("  ")[0][:30]):
            fails.append("L6 the call does not start with the opening line")
    if code_steps is not None and any(c > 1 for c in code_steps):
        fails.append("L11 more than one code step in a customer turn: %s" % code_steps)
    if ledger is not None:
        calls = ledger.get("calls") or []
        if not calls or calls[-1].get("tool") != "close_call":
            fails.append("the call was not closed with close_call as the last tool call")
        if sum(1 for c in calls if c.get("tool") == "close_call" and (c.get("result") or {}).get("ok")) != 1:
            fails.append("close_call did not succeed exactly once")
    return fails


def _is_readback(text, policy):
    head = re.split(r"\{", policy["lines"]["readback"])[0].strip()
    return bool(head) and text.startswith(head) or policy["lines"]["confirm_question"] in (text or "")


def _money_forms(x):
    x = float(x)
    forms = []
    if abs(x - round(x)) < 0.005:
        forms.append("{:,}".format(int(round(x))))
    forms.append("{:,.2f}".format(x))
    return forms


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def _date_in(iso, text):
    y, m, d = iso.split("-")
    return ("%d %s" % (int(d), MONTHS[int(m) - 1])) in text


def _situation(ledger, policy):
    o = (ledger.get("outcome"), ledger.get("reason") or None)
    for s, v in policy["outcomes"].items():
        if (v[0], v[1] or None) == o:
            return s
    return None
