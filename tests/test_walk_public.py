"""Local walks of the 13 practice customers with an ideal extractor (scripted extraction values).

These test routing, the decide code and the ledger offline. Real extraction is tested live (gates).
Each scenario: list of (customer text, extraction dict). Missing 'utterance' defaults to the text.
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(ROOT))
from builder.emit import workflow as W  # noqa: E402
from builder.policy import openapi  # noqa: E402
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402
from tools.score import score_ledger  # noqa: E402

TS = openapi.load(str(ROOT / "tools" / "openapi.json"))
CASES = dict((c["id"], c) for c in json.load(open(ROOT / "public-test-set.json")))
POL = {"A": json.load(open(ROOT / "tests" / "fixtures" / "policy-a.json")),
       "B": json.load(open(ROOT / "tests" / "fixtures" / "policy-ab.json"))}
WF = dict((k, W.build(p, TS)) for k, p in POL.items())

DOB = {"PUB-01": "Fourteenth of March, nineteen eighty-eight.", "PUB-04": "30 January 1984.", "PUB-05": "9 September 1990.",
       "PUB-06": "The 17th of May 1986.", "PUB-07": "December 5th, 1975.", "PUB-08": "28 April 1993.",
       "PUB-09": "11 August 1981.", "PUB-10": "23 February 1989.", "PUB-11": "3 June 1987.", "PUB-12": "19 October 1983.",
       "PUB-13": "8 January 1991."}
PHONE = {"PUB-01": "4471", "PUB-04": "2219", "PUB-05": "8846", "PUB-06": "1502", "PUB-07": "7093", "PUB-08": "3317",
         "PUB-09": "5560", "PUB-10": "9904", "PUB-11": "2288", "PUB-12": "4410", "PUB-13": "6604"}


def verified_prefix(cid):
    return [("Yes, speaking.", {"reply": "yes"}), (DOB[cid], {}), (PHONE[cid], {}), ("Okay.", {"reply": "ack"})]


SCRIPTS = {
    "PUB-01": verified_prefix("PUB-01") + [
        ("Yes, I can pay the full amount today.", {"reply": "yes"}),
        ("Yes, I confirm.", {"reply": "yes"})],
    "PUB-02": [
        ("Hello? I'm her husband. What is this about?", {"intent": "someone_else", "topic": "what_about"}),
        ("I can pay it for her if you want.", {"intent": "propose", "topic": "other_question"}),
        ("She can be reached tomorrow morning, around eleven.", {"pay_date": "tomorrow morning"})],
    "PUB-03": [
        ("Yes, that's me.", {"reply": "yes"}),
        ("12 July 1991.", {}), ("21 August 1992.", {}),
        ("21 July 1990. How much do I owe anyway?", {"topic": "how_much"})],
    "PUB-04": verified_prefix("PUB-04") + [
        ("My salary arrives on 6 November, I can pay then.", {"intent": "propose", "pay_date": "on 6 November"}),
        ("Wait, am I talking to a robot?", {"topic": "robot"}),
        ("Okay, the 23rd is fine.", {"reply": "yes", "pay_date": "the 23rd"}),
        ("Yes, I confirm.", {"reply": "yes"})],
    "PUB-05": verified_prefix("PUB-05") + [
        ("I lost my job last month, I can't pay anything. Can I get a discount?", {"topic": "hardship", "reply": "no"}),
        ("No, I don't want to be transferred.", {"reply": "no", "intent": "decline"})],
    "PUB-06": verified_prefix("PUB-06") + [
        ("The full amount is too much right now.", {"intent": "too_much", "reply": "no"}),
        ("Not today, but I can pay the minimum on Friday.", {"intent": "propose", "pay_date": "on Friday", "pay_amount": "the minimum"}),
        ("Yes, I confirm.", {"reply": "yes"})],
    "PUB-07": verified_prefix("PUB-07") + [
        ("I can't pay today. Maybe the week after next.", {"intent": "vague_time", "reply": "no", "pay_date": "the week after next"}),
        ("Monday the 26th.", {"pay_date": "Monday the 26th", "intent": "propose"}),
        ("Yes, that works.", {"reply": "yes"}),
        ("Yes, I confirm.", {"reply": "yes"})],
    "PUB-08": verified_prefix("PUB-08") + [
        ("I already paid it in the app this morning.", {"topic": "already_paid"})],
    "PUB-09": verified_prefix("PUB-09") + [
        ("I can't pay this amount. I want lower instalments.", {"topic": "restructuring", "reply": "no"})],
    "PUB-10": verified_prefix("PUB-10") + [
        ("No, not today.", {"reply": "no"}),
        ("Yes, I can do that.", {"reply": "yes"}),
        ("Yes, I confirm.", {"reply": "yes"})],
    "PUB-11": verified_prefix("PUB-11") + [
        ("Not today, but I can pay all three this Friday.", {"reply": "no", "intent": "propose", "pay_date": "this Friday"}),
        ("Yes, I confirm.", {"reply": "yes"})],
    "PUB-12": [("Yes, speaking.", {"reply": "yes"}), (DOB["PUB-12"], {}), ("4401", {}), ("Sorry, 4410.", {}),
               ("Okay.", {"reply": "ack"}),
               ("I'll pay the credit card tomorrow, but not the others.", {"intent": "propose", "pay_date": "tomorrow"}),
               ("No.", {"reply": "no", "intent": "refuse_pay"}), ("No, I won't.", {"reply": "no", "intent": "refuse_pay"}),
               ("No.", {"reply": "no", "intent": "refuse_pay"}),
               ("Yes, I confirm.", {"reply": "yes"})],
    "PUB-13": verified_prefix("PUB-13") + [
        ("Not today. I'd like to pay both on 30 October.", {"reply": "no", "intent": "propose", "pay_date": "on 30 October"}),
        ("Okay, yes, I confirm.", {"reply": "yes"})],
}


def walk(cid, script=None, faults=None):
    case = CASES[cid]
    pol = POL[case["brief"]]
    bank = LW.Bank(case, faults=faults)
    V = dict(case["variables"], customer_id="c_" + cid)
    w = LW.Walk(WF[case["brief"]], V, bank)
    w.start()
    for txt, ex in (script or SCRIPTS[cid]):
        if w.ended:
            break
        w.customer(txt, ex)
    return w, bank, pol


@pytest.mark.parametrize("cid", sorted(SCRIPTS))
def test_public_case_local(cid):
    w, bank, pol = walk(cid)
    assert w.ended, "call did not end:\n" + LW.text_of(w)
    r = score_ledger(CASES[cid], bank.ledger)
    assert r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))
    fails = lessons.check(LW.events(w), bank.ledger, pol, code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, LW.text_of(w))
    assert not w.rejected, "the platform would reject these code-step writes: %s" % sorted(set(w.rejected))


def test_lint_clean():
    for k, wf in WF.items():
        assert W.lint(wf) == [], (k, W.lint(wf))
