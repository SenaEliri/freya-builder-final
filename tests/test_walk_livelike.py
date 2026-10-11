"""Local walks with customer lines and extraction values copied from live gate runs (Freya's real extractor).

Each scenario reproduces a live failure that was fixed, so it cannot come back unnoticed.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402
from tests.test_walk_public import CASES, walk  # noqa: E402
from tools.score import score_ledger  # noqa: E402

LIVE = {
    # gate 3, PUB-05: 'cannot pay anything' extracted as pay_amount 'anything' was taken as an own offer
    "PUB-05": [
        ("Yes, this is Tomas Novak.", {"reply": "yes"}),
        ("September ninth nineteen ninety.", {"reply": "none", "intent": "none", "topic": "none"}),
        ("Eight eight four six.", {"reply": "yes"}),
        ("I lost my job last month and I cannot pay anything. Can I get a discount?",
         {"intent": "too_much", "topic": "hardship", "pay_amount": "anything"}),
        ("No, I do not want to be transferred. I lost my job and cannot pay anything, so I need a discount.",
         {"reply": "no", "intent": "decline", "topic": "discount", "pay_amount": "anything"}),
    ],
    # gate 1, PUB-08: date of birth said as 'twenty-eight April nineteen ninety-three'
    "PUB-08": [
        ("Yes, this is Hannah Schmidt.", {"reply": "yes"}),
        ("My date of birth is twenty-eight April nineteen ninety-three.", {"reply": "none", "intent": "none", "topic": "none"}),
        ("three three one seven.", {"reply": "yes"}),
        ("Okay, what is this about?", {"reply": "ack", "topic": "what_about"}),
        ("I actually paid it in the app this morning.", {"topic": "already_paid"}),
    ],
    # gate 4, PUB-12: the refused loans were named in the same sentence and got the credit card's date
    "PUB-12": [
        ("Yes, this is Marcus Bell.", {"reply": "yes"}),
        ("Nineteen October nineteen eighty three.", {"reply": "none", "intent": "none", "topic": "none"}),
        ("Four four zero one.", {"reply": "yes"}),
        ("Four four one zero.", {"reply": "none", "intent": "none", "topic": "none"}),
        ("What is this about?", {"topic": "what_about"}),
        ("I will pay the credit card tomorrow, but I am not paying the personal loan or the car loan.",
         {"reply": "no", "intent": "propose", "pay_date": "tomorrow"}),
        ("No, I am not paying the personal loan.", {"reply": "no", "intent": "refuse_pay"}),
        ("No.", {"reply": "no", "intent": "refuse_pay"}),
        ("No, I won't.", {"reply": "no", "intent": "refuse_pay"}),
        ("Yes, I confirm.", {"reply": "yes"}),
    ],
    # gate 5 corrects, PUB-06: the turn was cut at the comma before the correction ('on Thursday,' ... 'I mean Friday')
    "PUB-06": [
        ("Yes, this is Priya Nair.", {"reply": "yes"}),
        ("It is the seventeenth of May nineteen eighty six.", {"reply": "none", "intent": "none", "topic": "none"}),
        ("one five zero three, sorry, I mean one five zero two.", {"reply": "yes"}),
        ("Okay, what is this about?", {"reply": "ack", "topic": "what_about"}),
        ("That is way too much for me to pay right now. I cannot do the full amount.", {"reply": "no", "intent": "too_much"}),
        ("I cannot pay that today. How much is the minimum?", {"reply": "no", "topic": "how_much"}),
        ("I can pay that on Thursday,", {"intent": "propose", "pay_date": "on Thursday"}),
        ("sorry, I mean Friday.", {"pay_date": "Friday"}),
        ("Yes, I confirm.", {"reply": "yes"}),
    ],
    # gate 5 talkative, PUB-07: long turns cut mid-sentence; fragments used up the only persuasion attempt
    "PUB-07": [
        ("Yes, this is Samuel Ortiz. I have been so busy at work today that I barely had time to grab a coffee.", {"reply": "yes"}),
        ("Work has been absolutely non-stop. My date of birth is the fifth of December nineteen seventy-five.", {"reply": "yes"}),
        ("The traffic was just terrible this morning. The last four digits are seven zero nine three.", {"reply": "yes"}),
        ("I am just swamped with all these meetings. I am calling to let you know that I cannot pay today.",
         {"intent": "refuse_pay", "pay_date": "today"}),
        ("My day has been so hectic with back-", {}),
        ("My day has been so hectic with", {}),
        ("back-to-back meetings. I cannot do it today, I can only pay the week after next.",
         {"reply": "no", "intent": "vague_time", "pay_date": "the week after next"}),
        ("I have been running from one meeting to", {}),
        ("another and I also have my cousin's wedding coming up on the thirtieth. I", {"pay_date": "on the thirtieth"}),
        ("can pay on Monday the 26th.", {"intent": "propose", "pay_date": "Monday the 26th"}),
        ("Yes, that works.", {"reply": "yes"}),
        ("Yes, I confirm.", {"reply": "yes"}),
    ],
    # B talkative, PUB-11: the security answer arrived after turns cut mid-sentence; re-asking 4 times closed the call
    "PUB-11": [
        ("Yes, this is Sofia Almeida. Traffic was just terrible getting home today.", {"reply": "yes"}),
        ("Work has been so busy lately. My date of birth is the third of June nineteen eighty-seven.", {"reply": "yes"}),
        ("I've been so busy planning things because my cousin", {}),
        ("I'm sorry, I was just saying that I'", {}),
        ("ve been distracted, my cousin's wedding is on the 30th. The last four digits are two two eight eight.", {}),
        ("Okay.", {"reply": "ack"}),
        ("Not today, but I can pay all three this Friday.", {"reply": "no", "intent": "propose", "pay_date": "this Friday"}),
        ("Yes, I confirm.", {"reply": "yes"}),
    ],
    # B pieces, PUB-13: 'both on October' ... 'Thirty.' must become 30 October for both (the loan clamped to its own
    # deadline); a cut turn right after the identity check must not delay the account
    "PUB-13": [
        ("Yes, this is Elena Rossi.", {"reply": "yes"}),
        ("8 January.", {}), ("Nineteen ninety-one.", {"reply": "yes"}),
        ("Six six.", {"reply": "none"}), ("Zero four.", {"reply": "yes"}),
        ("I can't pay today. I want to pay", {"intent": "too_much"}),
        ("No, I want to pay both on October.", {"reply": "no", "intent": "vague_time", "pay_date": "on October"}),
        ("Thirty.", {"intent": "propose", "pay_date": "Thirty"}),
        ("Yes, I confirm.", {"reply": "yes"}),
    ],
}


@pytest.mark.parametrize("cid", sorted(LIVE))
def test_livelike(cid):
    w, bank, pol = walk(cid, script=LIVE[cid])
    assert w.ended, "call did not end:\n" + LW.text_of(w)
    r = score_ledger(CASES[cid], bank.ledger)
    assert r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))
    fails = lessons.check(LW.events(w), bank.ledger, pol, code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, LW.text_of(w))
    assert not w.rejected


def test_correction_at_readback_refuses_some_products():
    """At the read-back the customer takes two products back: they go to the persuasion attempts (PUB-12 rules)."""
    script = LIVE["PUB-12"][:5] + [
        ("I can pay all of them tomorrow.", {"intent": "propose", "pay_date": "tomorrow"}),
        ("Actually only the credit card, I am not paying the loans.", {"reply": "no", "intent": "propose"}),
        ("No.", {"reply": "no", "intent": "refuse_pay"}),
        ("No.", {"reply": "no", "intent": "refuse_pay"}),
        ("No, I won't.", {"reply": "no", "intent": "refuse_pay"}),
        ("Yes, I confirm.", {"reply": "yes"}),
    ]
    w, bank, pol = walk("PUB-12", script=script)
    r = score_ledger(CASES["PUB-12"], bank.ledger)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))


# candidate 2, live focused run (simulation 5553f9dc), PUB-06: 'That full amount is too much' was extracted with
# pay_amount 'full amount'; it was taken as a proposal of the full amount, and 'too much' at the read-back had no
# floor offer, so 'the rest stays overdue' was never said (judge fail; the ledger itself was right)
LIVE_C2_PUB06 = [
    ("Yes, this is Priya Nair.", {"reply": "yes"}),
    ("Seventeenth of May nineteen eighty six.", {"reply": "none", "intent": "none", "topic": "none"}),
    ("One five zero two.", {"reply": "yes"}),
    ("Okay, why are you calling?", {"reply": "ack", "topic": "what_about"}),
    ("That full amount is too much for me right now.", {"reply": "no", "intent": "too_much", "pay_amount": "full amount"}),
    ("I can make a payment this Friday.", {"reply": "none", "intent": "propose", "topic": "none", "pay_date": "this Friday"}),
    ("Yes, I confirm.", {"reply": "yes"}),
]


def test_live_c2_full_amount_too_much_gets_the_floor():
    w, bank, pol = walk("PUB-06", script=LIVE_C2_PUB06)
    text = LW.text_of(w)
    r = score_ledger(CASES["PUB-06"], bank.ledger)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], text)
    assert "Which exact day" not in text and pol["lines"]["rest_overdue"] in text, text


def test_live_c2_too_much_at_the_read_back_offers_the_floor():
    script = LIVE_C2_PUB06[:4] + [
        ("I can make a payment this Friday.", {"reply": "none", "intent": "propose", "pay_date": "this Friday"}),
        ("That is too much money for me to pay all at once.", {"reply": "no", "intent": "too_much"}),
        ("Yes, I can do that.", {"reply": "yes"}),
        ("Yes, I confirm.", {"reply": "yes"})]
    w, bank, pol = walk("PUB-06", script=script)
    text = LW.text_of(w)
    assert pol["lines"]["rest_overdue"] in text, text
    assert [(p["amount"], p["date"]) for p in bank.ledger["promises"]] == [(637.5, "2026-10-16")], text


# candidate 2 v1, live in_words run (simulation 79b38400), PUB-06: the floor was offered for today, then again as
# attempt 1 on Friday; the judge failed 'minimum payment offered once'. Now the one floor offer carries Friday.
def test_live_c2_in_words_floor_named_once():
    script = LIVE_C2_PUB06[:4] + [
        ("That is too much for me to pay right now.", {"reply": "no", "intent": "too_much"}),
        ("Yes, I can pay six hundred and thirty-seven dollars and fifty cents this Friday the sixteenth of October.",
         {"reply": "yes", "pay_date": "this Friday the sixteenth of October",
          "pay_amount": "six hundred and thirty-seven dollars and fifty cents"}),
        ("Yes, I confirm.", {"reply": "yes"})]
    w, bank, pol = walk("PUB-06", script=script)
    text = LW.text_of(w)
    r = score_ledger(CASES["PUB-06"], bank.ledger)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], text)
    offers = [t for k, t, _ in LW.events(w) if k == "agent" and "637.50" in t and not t.startswith(("So that is", "Your promise"))]
    assert len(offers) == 1, text
