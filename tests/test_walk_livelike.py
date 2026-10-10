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
