"""Gate 5: the kit's speech styles (pieces, corrects, asks_back, in_words, talkative) on local walks.

Customer lines follow tools/run_cases.py STYLES; extraction values are what a correct extractor returns (and, for
talkative, a wrong one that picks the wedding date). Expected ledgers are the public cases' own.
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

YES = {"reply": "yes"}
STYLED = {
    "pieces-PUB-01": ("PUB-01", [
        ("Yes, speaking.", YES),
        ("Fourteenth of March,", {}), ("nineteen eighty-eight.", {}),
        ("Forty-four", {}), ("seventy-one.", {}),
        ("Okay.", {"reply": "ack"}),
        ("Yes, I can pay the full amount today.", YES), ("Yes, I confirm.", YES)]),
    "pieces-PUB-13": ("PUB-13", [
        ("Yes, speaking.", YES), ("The eighth of January", {}), ("nineteen ninety-one.", {}),
        ("Sixty-six", {}), ("oh four.", {}), ("Okay.", {"reply": "ack"}),
        ("Not today. I'd like to pay both on 30 October.", {"reply": "no", "intent": "propose", "pay_date": "on 30 October"}),
        ("Okay, yes, I confirm.", YES)]),
    "corrects-PUB-06": ("PUB-06", [
        ("Yes, speaking.", YES), ("The 17th of May 1986.", {}), ("1502", {}), ("Okay.", {"reply": "ack"}),
        ("The full amount is too much right now.", {"intent": "too_much", "reply": "no"}),
        ("Not today, but I can pay the minimum on Thursday, sorry, I mean Friday.",
         {"intent": "propose", "pay_date": "on Thursday, sorry, I mean Friday", "pay_amount": "the minimum"}),
        ("Yes, I confirm.", YES)]),
    "corrects-PUB-04": ("PUB-04", [
        ("Yes, speaking.", YES), ("30 January 1984.", {}), ("2219", {}), ("Okay.", {"reply": "ack"}),
        ("My salary arrives on the 7th of November, sorry, the 6th of November, I can pay then.",
         {"intent": "propose", "pay_date": "on the 7th of November, sorry, the 6th of November"}),
        ("Wait, am I talking to a robot?", {"topic": "robot"}),
        ("Okay, the 23rd is fine.", {"reply": "yes", "pay_date": "the 23rd"}), ("Yes, I confirm.", YES)]),
    "asks_back-PUB-01": ("PUB-01", [
        ("Yes, speaking.", YES),
        ("Why do you need that?", {"topic": "why_needed"}), ("Fourteenth of March, nineteen eighty-eight.", {}),
        ("Which account is this about?", {"topic": "what_about"}), ("4471", {}),
        ("Okay.", {"reply": "ack"}),
        ("Yes, I can pay the full amount today.", YES), ("Yes, I confirm.", YES)]),
    "asks_back-PUB-10": ("PUB-10", [
        ("Yes, speaking.", YES), ("Which account is this about?", {"topic": "what_about"}), ("23 February 1989.", {}),
        ("Why do you need that?", {"topic": "why_needed"}), ("9904", {}), ("Okay.", {"reply": "ack"}),
        ("No, not today.", {"reply": "no"}), ("Yes, I can do that.", YES), ("Yes, I confirm.", YES)]),
    "in_words-PUB-06": ("PUB-06", [
        ("Yes, speaking.", YES), ("The seventeenth of May, one nine eight six.", {}), ("one five zero two.", {}),
        ("Okay.", {"reply": "ack"}),
        ("The full amount is too much right now.", {"intent": "too_much", "reply": "no"}),
        ("Not today, but I can pay six hundred and thirty-seven dollars and fifty cents on Friday the sixteenth of October.",
         {"intent": "propose", "pay_date": "on Friday the sixteenth of October",
          "pay_amount": "six hundred and thirty-seven dollars and fifty cents"}),
        ("Yes, I confirm.", YES)]),
    "in_words-PUB-11": ("PUB-11", [
        ("Yes, speaking.", YES), ("The third of June, nineteen eighty-seven.", {}), ("two two eight eight.", {}),
        ("Okay.", {"reply": "ack"}),
        ("Not today, but I can pay all three on the sixteenth of October.",
         {"reply": "no", "intent": "propose", "pay_date": "on the sixteenth of October"}),
        ("Yes, I confirm.", YES)]),
    "talkative-PUB-07": ("PUB-07", [
        ("Oh hello, yes, speaking. Sorry, I'm just back from work, it was a long day.", YES),
        ("Let me think. December 5th, 1975.", {}), ("It's 7093.", {}),
        ("Okay, go on. The traffic was terrible today.", {"reply": "ack"}),
        ("I can't pay today, it's a busy month, my cousin's wedding is on the 30th. Maybe the week after next.",
         {"intent": "vague_time", "reply": "no", "pay_date": "on the 30th"}),
        ("Monday the 26th.", {"pay_date": "Monday the 26th", "intent": "propose"}),
        ("Yes, that works.", YES), ("Yes, I confirm.", YES)]),
    "talkative-PUB-10": ("PUB-10", [
        ("Yes, that's me. Busy day at work, you know how it is.", YES), ("23 February 1989.", {}), ("9904", {}),
        ("Okay. My cousin's wedding is on the 30th, so money is tight.", {"reply": "ack", "pay_date": "on the 30th"}),
        ("No, not today.", {"reply": "no"}), ("Yes, I can do that.", YES), ("Yes, I confirm.", YES)]),
}


@pytest.mark.parametrize("name", sorted(STYLED))
def test_style(name):
    cid, script = STYLED[name]
    w, bank, pol = walk(cid, script=script)
    text = LW.text_of(w)
    assert w.ended, "call did not end:\n" + text
    r = score_ledger(CASES[cid], bank.ledger)
    assert r["pass"], "%s\n%s" % (r["failed"], text)
    fails = lessons.check(LW.events(w), bank.ledger, pol, code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, text)
