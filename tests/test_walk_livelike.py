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
