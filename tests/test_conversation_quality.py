"""Conversation-quality changes on the experimental candidate (branch experiment/conversation-quality).

Each test is a v5 live transcript (real extraction values) with the old wording in the docstring. The changes are
wording and reading only: verification, attempt limits, calendar rules, outcomes, tool order and the confirmation /
write guards are untouched (the full suite still covers them).
"""
import copy
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "builder" / "runtime"))
import agent_runtime as R  # noqa: E402
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402
from tests.test_walk_public import CASES, WF, walk  # noqa: E402
from tools.score import score_ledger  # noqa: E402


def agent_lines(w):
    return [t for r, t, _ in w.transcript if r == "agent"]


def test_failed_identity_check_is_not_blamed_on_the_customer():
    """focusA-talkative PUB-05 (simulation 3353180f): verify_identity failed (bank HTML error) and the agent said
    'Sorry, I didn't catch that. Could you tell me your date of birth again?' four times."""
    case = copy.deepcopy(CASES["PUB-05"])
    bank = LW.Bank(case, faults=[{"tool": "verify_identity", "fail_first_n": 1}])
    w = LW.Walk(WF["A"], dict(case["variables"], customer_id="c_tech"), bank)
    w.start()
    for t, e in [("Yes, this is Tomas Novak.", {"reply": "yes"}), ("Nine September nineteen ninety.", {})]:
        w.customer(t, e)
    last = agent_lines(w)[-1]
    assert "didn't catch" not in last and "could not check that just now" in last, LW.text_of(w)
    assert bank.wrong == 0  # a technical failure is never a wrong answer (unchanged)
    w.customer("Nine September nineteen ninety.", {})
    assert [c["result"].get("verified") for c in bank.ledger["calls"] if c["tool"] == "verify_identity"][-1] is True


def test_an_events_date_is_not_the_date_of_birth():
    """Same call: 'my cousin's wedding coming up on the thirtieth. My date of birth is nine September nineteen ninety'
    was read as 30 September 1990 and counted as a wrong answer ('That does not match our records')."""
    said = ("I'm getting a bit tired of repeating myself, but I suppose things are just busy everywhere, like my "
            "cousin's wedding coming up on the thirtieth. My date of birth is nine September nineteen ninety.")
    assert R.dob_complete(R.parse_dob(R.dob_text(said))) == "1990-09-09"
    assert R.dob_complete(R.parse_dob(R.dob_text("My cousin's wedding is on the thirtieth. Nine September 1990."))) == "1990-09-09"
    assert R.dob_complete(R.parse_dob(R.dob_text("The fourteenth of March, nineteen eighty-eight."))) == "1988-03-14"


def test_question_while_declining_support_is_answered_before_goodbye():
    """suite A r1 + r2 PUB-05: 'No, I do not want to be transferred. Can I get a discount?' -> 'Thank you and
    goodbye.' (the question was dropped). Now it is answered (no discount is offered, A33), then the same closing."""
    script = [("Yes, this is Tomas Novak.", {"reply": "yes"}), ("Nine September nineteen ninety.", {}),
              ("Eight eight four six.", {"reply": "yes"}), ("Okay.", {"reply": "ack"}),
              ("I lost my job last month and I cannot pay anything.", {"reply": "none", "intent": "refuse_pay", "topic": "hardship"}),
              ("No, I do not want to be transferred. Can I get a discount?", {"reply": "no", "intent": "decline", "topic": "discount"})]
    w, bank, pol = walk("PUB-05", script=script)
    r = score_ledger(CASES["PUB-05"], bank.ledger)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))
    assert "I'm not able to offer a discount." in agent_lines(w)[-1], LW.text_of(w)
    assert not lessons.check(LW.events(w), bank.ledger, pol, code_steps=w.code_steps_per_turn)


def test_a_negated_today_does_not_cancel_the_salary_date_after_because():
    """focusA-in_words PUB-04 (simulation 595fb674): 'I cannot pay today because my salary arrives on the sixth of
    November and I can pay then. Am I talking to a robot?' -> 'I am Freya Bank's digital assistant. Which exact day
    would that be?' (the date had been said). Now the date is handled at once (after the deadline -> the deadline)."""
    script = [("Yes, speaking.", {"reply": "yes"}), ("30 January 1984.", {}), ("2219", {}), ("Okay.", {"reply": "ack"}),
              ("I cannot pay today because my salary arrives on the sixth of November and I can pay then. Am I talking to a robot?",
               {"reply": "no", "intent": "vague_time", "topic": "robot", "pay_date": "the sixth of November"}),
              ("Yes, the twenty-third works.", {"reply": "yes", "pay_date": "the twenty-third"}),
              ("Yes, I confirm.", {"reply": "yes"})]
    w, bank, pol = walk("PUB-04", script=script)
    lines = agent_lines(w)
    assert not any("Which exact day" in t for t in lines), LW.text_of(w)
    assert any(t.startswith("I am Freya Bank's digital assistant. The latest date I can record is Friday 23 October") for t in lines), LW.text_of(w)
    assert score_ledger(CASES["PUB-04"], bank.ledger)["pass"], LW.text_of(w)


def test_month_without_a_day_is_built_on():
    """v3 B pieces PUB-13 (simulation d82d478f): 'October for both of them.' -> 'Which exact day would that be?'."""
    script = [("Yes, this is Elena Rossi.", {"reply": "yes"}), ("8 January 1991.", {}), ("6604", {}), ("Okay.", {"reply": "ack"}),
              ("Not today. I want to pay both of them in October.", {"reply": "no", "intent": "vague_time", "pay_date": "in October"}),
              ("The thirtieth.", {"pay_date": "The thirtieth"}), ("Yes, I confirm.", {"reply": "yes"})]
    w, bank, pol = walk("PUB-13", script=script)
    assert "I have October. Which day in October do you mean?" in agent_lines(w), LW.text_of(w)
    r = score_ledger(CASES["PUB-13"], bank.ledger)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))
