"""Builder self-tests: local walks of customers made up from the extracted policy itself.

Hidden briefs have no practice cases (hard rule 3), so nothing here comes from a test set: the products, identity
answers, bands and expected outcomes are all derived from the policy and the tool API the builder just read. The
walks run the generated workflow against the local bank stub (qa/localwalk.py) speaking the brief's own tool API.
"""
import copy
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "builder" / "runtime"))
import agent_runtime as R  # noqa: E402
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402

YES = {"reply": "yes"}


def business_now(policy, start=None):
    d = start or datetime.date.today()
    while not R.is_business(d, policy["calendar"]):
        d += datetime.timedelta(days=1)
    return d


def identity_for(policy):
    true, right, wrong = {}, {}, {}
    for q in policy["identity"]["questions"]:
        f, kind = q["field"], q["kind"]
        if kind == "date":
            true[f], right[f], wrong[f] = "1988-03-14", "14 March 1988.", "1 January 1970."
        elif kind == "digits":
            n = int(q.get("length") or 4)
            true[f] = ("4471" * 4)[:n]
            right[f], wrong[f] = true[f], ("9032" * 4)[:n]
        elif kind == "year":
            true[f], right[f], wrong[f] = "1988", "1988.", "1970."
        elif kind == "code":
            true[f], right[f], wrong[f] = "AB12CD", "AB12CD.", "ZZ99ZZ."
            if q.get("upper") is False:
                true[f] = "ab12cd"
                right[f] = "ab12cd."
        else:
            true[f], right[f], wrong[f] = "Rosewood", "Rosewood.", "Maple."
    return true, right, wrong


def make_case(policy, n_products=1, band_index=0, now=None):
    types = list(policy["products"].keys()) or ["product"]
    bands = sorted(policy["bands"], key=lambda b: b["min"])
    band = bands[min(band_index, len(bands) - 1)]
    prods = []
    for i in range(n_products):
        t = types[i % len(types)]
        spec = policy["products"].get(t) or {}
        p = {"type": t, "past_due": 400.0 + 100 * i, "days_late": band["min"]}
        if spec.get("floor_field"):
            p[spec["floor_field"]] = 120.0 + 10 * i
        for ph in re.findall(r"\{(\w+)\}", spec.get("phrase") or ""):
            p.setdefault(ph, "4821")
        prods.append(p)
    true, right, wrong = identity_for(policy)
    now = now or business_now(policy)
    case = {"id": "SELF", "variables": {"title": "Mr", "first_name": "Alex", "last_name": "Morgan",
                                        "now": "%sT11:00" % now.isoformat()},
            "identity": true, "products": prods,
            "expected": {"outcome": None, "reason": None, "promises": [], "notes": [], "callbacks": [], "transfers": []}}
    for n in policy.get("call_variables") or []:
        case["variables"].setdefault(n, "Test")
    return case, right, wrong


def reasons_table(policy):
    tab = {}
    for o, r in policy["outcomes"].values():
        tab.setdefault(o, [])
        if r and r not in tab[o]:
            tab[o].append(r)
    return tab


def verified_prefix(policy, right):
    return [("Yes, speaking.", YES)] + [(right[q["field"]], {}) for q in policy["identity"]["questions"]] + \
        [("Okay.", {"reply": "ack"})]


def scenarios(policy):
    multi = bool((policy.get("multi") or {}).get("enabled"))
    n = 2 if multi else 1
    out = []
    case, right, wrong = make_case(policy, n_products=n)
    today = case["variables"]["now"][:10]
    fa = policy.get("first_ask") or {"date_rule": "today", "amount_rule": "full"}
    promises = None
    if (fa.get("date_rule"), fa.get("amount_rule")) == ("today", "full"):
        promises = [{"product_id": "p%d" % (i + 1), "amount": p["past_due"], "date": today} for i, p in enumerate(case["products"])]
    happy = verified_prefix(policy, right) + [
        ("Yes, I can pay the full amount today." if n == 1 else "Yes, I can pay all of them today.", YES),
        ("Yes, I confirm.", YES)]
    out.append(("happy path: pays in full at the first ask", case, happy, "promise", promises))
    case2, _, _ = make_case(policy, n_products=n)
    out.append(("wrong number", case2, [("Sorry, you have the wrong number.", {"intent": "wrong_number", "reply": "no"})],
                "wrong_number", []))
    case3, right3, wrong3 = make_case(policy, n_products=n)
    q0 = policy["identity"]["questions"][0]["field"]
    script3 = [("Yes, speaking.", YES)] + [(wrong3[q0], {})] * int(policy["identity"].get("max_wrong") or 3)
    out.append(("identity fails after the allowed wrong answers", case3, script3, "id_failed", []))
    case4, right4, _ = make_case(policy, n_products=n)
    out.append(("already paid", case4, verified_prefix(policy, right4) + [
        ("I already paid this." if n == 1 else "I already paid all of them.", {"topic": "already_paid"})], "paid", []))
    case5, right5, _ = make_case(policy, n_products=1)
    refusals = [("No, I won't pay.", {"reply": "no", "intent": "refuse_pay"})] * (2 + max(b["attempts"] for b in policy["bands"]))
    out.append(("refuses every offer", case5, verified_prefix(policy, right5) + refusals, "refused", []))
    case6, right6, _ = make_case(policy, n_products=n)
    out.append(("asks for a new payment plan", case6, verified_prefix(policy, right6) + [
        ("I want a new payment plan with lower instalments.", {"topic": "restructuring"})], "transfer_restructuring", []))
    case7, right7, _ = make_case(policy, n_products=1)
    out.append(("hardship, declines the transfer", case7, verified_prefix(policy, right7) + [
        ("I lost my job last month, I can't pay anything.", {"topic": "hardship", "intent": "too_much"}),
        ("No, thank you, I don't want to be transferred.", {"reply": "no", "intent": "decline"})], "hardship", []))
    case8, right8, _ = make_case(policy, n_products=1)
    out.append(("insists on a person", case8, verified_prefix(policy, right8) + [
        ("I want to speak to a real person.", {"topic": "human", "intent": "wants_human"}),
        ("No, I want a human, please put me through.", {"topic": "human", "intent": "wants_human", "reply": "no"})],
        "transfer_human", []))
    case9, right9, _ = make_case(policy, n_products=1)
    out.append(("disputes the debt", case9, verified_prefix(policy, right9) + [
        ("This debt is not mine, I never had this product.", {"topic": "dispute"})], "dispute", []))
    cb = callback_slot(policy, case["variables"]["now"])
    if cb:
        case10, _, _ = make_case(policy, n_products=1)
        say = "They can be reached on %d %s at %s." % (cb.day, R.MONTH_NAMES[cb.month - 1], cb.strftime("%H:%M"))
        out.append(("someone else answers, callback booked", case10, [
            ("No, this is a colleague of theirs.", {"intent": "someone_else", "reply": "no"}),
            (say, {"pay_date": "on %d %s" % (cb.day, R.MONTH_NAMES[cb.month - 1])})], "callback", None))
    return out


def callback_slot(policy, now):
    """A day and time the policy allows for a callback, an hour into the window."""
    c = policy.get("callback") or {}
    today = datetime.date.fromisoformat(now[:10])
    now_t = now[11:16]
    start, end = c.get("start", "09:00"), c.get("end", "17:00")
    days = []
    if "today" in (c.get("days") or []):
        days.append(today)
    if "tomorrow" in (c.get("days") or []):
        days.append(today + datetime.timedelta(days=1))
    if "next_business_day" in (c.get("days") or []):
        days.append(R.add_business(today, 1, policy["calendar"]))
    for d in days:
        h, m = [int(x) for x in start.split(":")]
        t = datetime.datetime(d.year, d.month, d.day, h, m) + datetime.timedelta(hours=1)
        if d == today and t.strftime("%H:%M") <= now_t:
            t = datetime.datetime(d.year, d.month, d.day, int(now_t[:2]) + 1, 0)
        if t.strftime("%H:%M") <= end:
            return t
    return None


def run_one(policy, ts, wf, name, case, script, situation, promises):
    expected = tuple(policy["outcomes"].get(situation) or (None, None))
    bank = LW.Bank(case, api=ts.get("api"), reasons=reasons_table(policy))
    bank.max_wrong = int(policy["identity"].get("max_wrong") or 3)
    w = LW.Walk(wf, dict(case["variables"], customer_id="c_self"), bank)
    try:
        w.start()
        for txt, ex in script:
            if w.ended:
                break
            w.customer(txt, ex)
    except Exception as e:
        return {"name": name, "ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:200])}
    led = bank.ledger
    problems = []
    if not w.ended:
        problems.append("the call did not end")
    got = (led.get("outcome"), led.get("reason"))
    if got != (expected[0], expected[1] or None):
        problems.append("outcome %s, expected %s" % (got, expected))
    if promises is not None:
        key = lambda p: (p["product_id"], round(float(p["amount"]), 2), p["date"])  # noqa: E731
        if sorted(map(key, led["promises"])) != sorted(map(key, promises)):
            problems.append("promises %s, expected %s" % (sorted(map(key, led["promises"])), sorted(map(key, promises))))
    if situation == "callback" and len(led["callbacks"]) != 1:
        problems.append("callbacks %s, expected one" % led["callbacks"])
    if situation.startswith("transfer_"):
        q = (policy.get("queues") or {}).get(situation[len("transfer_"):])
        if [t.get("queue") for t in led["transfers"]] != [q]:
            problems.append("transfers %s, expected queue %s" % (led["transfers"], q))
    problems += lessons.check(LW.events(w), led, policy, code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    if w.rejected:
        problems.append("writes the platform rejects: %s" % sorted(set(w.rejected)))
    res = {"name": name, "ok": not problems, "outcome": got, "tools": [c["tool"] for c in led["calls"]]}
    if problems:
        res["problems"] = problems[:6]
        res["transcript_tail"] = LW.text_of(w).splitlines()[-6:]
    return res


def run_all(policy, ts, wf):
    pol = copy.deepcopy(policy)
    if not pol.get("api"):
        pol["api"] = ts.get("api")
    return [run_one(pol, ts, wf, *s) for s in scenarios(pol)]
