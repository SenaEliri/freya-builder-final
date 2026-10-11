"""Regressions for the defects fixed after candidate 1 (see HANDOFF.md, "Fixes after candidate 1").

Each test walks the generated workflow locally (qa/localwalk.py: the real decide code, the bank stub) with scripted
extraction values, including the imperfect ones the live extractor produced (a negated 'today', a span without the
cents, a wedding date). Products, amounts and dates are made up here on purpose: nothing comes from a practice case.
now = Tuesday 3 November 2026: late band deadline Friday 13 November, early band Friday 20 November, attempt 1
(last business day of the week) Friday 6 November; 11 November is a bank holiday in the fixture calendar.
"""
import copy
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "builder" / "runtime"))
import agent_runtime as R  # noqa: E402
from builder.emit import bundle  # noqa: E402
from builder.emit import workflow as W  # noqa: E402
from builder.policy import openapi  # noqa: E402
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402

TS = openapi.load(str(ROOT / "tools" / "openapi.json"))
POL = {"A": json.load(open(ROOT / "tests" / "fixtures" / "policy-a.json")),
       "B": json.load(open(ROOT / "tests" / "fixtures" / "policy-ab.json"))}
WF = dict((k, W.build(p, TS)) for k, p in POL.items())
NOW = "2026-11-03T10:00"
ID = {"date_of_birth": "1979-05-04", "phone_last4": "3308"}
YES = {"reply": "yes"}
NO = {"reply": "no", "intent": "refuse_pay"}
VERIFIED = [("Yes, speaking.", YES), ("4 May 1979.", {}), ("3308", {}), ("Okay.", {"reply": "ack"})]
CARD = {"type": "credit_card", "card_last4": "5512", "past_due": 1374.50, "days_late": 10, "minimum_payment": 412.35}
LOAN = {"type": "personal_loan", "past_due": 860.0, "days_late": 3, "instalment_amount": 215.0}
CAR = {"type": "car_loan", "past_due": 2240.0, "days_late": 20, "instalment_amount": 560.0}


class Bank(LW.Bank):
    """The stub bank, optionally failing create_promise (HTTP 500) for chosen product ids."""

    def __init__(self, case, fail_pids=()):
        LW.Bank.__init__(self, case, faults=[])
        self.fail_pids = set(fail_pids)

    def call(self, tool, body):
        if tool == "create_promise" and body.get("product_id") in self.fail_pids:
            self.ledger["calls"].append({"tool": tool, "args": body, "result": {"http": 500}})
            return 500, None
        return LW.Bank.call(self, tool, body)


def call(brief, products, script, prefix=True, fail_pids=()):
    bank = Bank({"identity": ID, "products": copy.deepcopy(products)}, fail_pids)
    w = LW.Walk(WF[brief], {"first_name": "Ana", "last_name": "Lind", "title": "Ms", "now": NOW, "customer_id": "c_reg"}, bank)
    w.start()
    for txt, ex in (VERIFIED if prefix else []) + script:
        if w.ended:
            break
        w.customer(txt, ex)
    return w, bank


def agent(w):
    return [t for r, t, _ in w.transcript if r == "agent"]


def text(w):
    return LW.text_of(w)


def promises(bank):
    return sorted((p["product_id"], round(p["amount"], 2), p["date"]) for p in bank.ledger["promises"])


def notes(bank):
    return sorted((n["product_id"], n["reason"]) for n in bank.ledger["notes"])


def state(w):
    return json.loads(w.V["rb_state"])


def assert_clean_end(w, bank, brief):
    """Ended, exactly one successful close_call as the last tool call, lesson checks clean."""
    assert w.ended, text(w)
    fails = lessons.check(LW.events(w), bank.ledger, POL[brief], code_steps=w.code_steps_per_turn,
                          max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, text(w))
    assert not w.rejected
    with pytest.raises(RuntimeError):
        w.customer("Hello? Are you still there?", {})  # nothing returns to the negotiation after the goodbye


# ---------------------------------------------------------------- A: inability, refusal, counterproposals

def test_cannot_pay_today_is_a_refusal_not_a_promise_for_today():
    """'I cannot pay today' with the extractor's pay_date 'today': attempt 1, never a read-back for today."""
    w, bank = call("A", [CARD], [
        ("I cannot pay today.", {"reply": "no", "intent": "refuse_pay", "pay_date": "today"}),
        ("No.", NO), ("No.", NO)])
    lines = agent(w)
    assert "Could you pay 1,374.50 dollars on Friday 6 November?" in lines, text(w)
    assert not any("Tuesday 3 November" in t for t in lines), text(w)
    assert promises(bank) == [] and (bank.ledger["outcome"], bank.ledger["reason"]) == ("no_promise", "refused")
    assert_clean_end(w, bank, "A")


def test_cannot_pay_today_but_names_another_day():
    """A counterproposal is not a refusal: the other day in the same message is used (the extractor copied 'today')."""
    w, bank = call("A", [LOAN], [
        ("I cannot pay today, but I can pay on the 12th.", {"reply": "no", "intent": "propose", "pay_date": "today"}),
        ("Yes, I confirm.", YES)])
    assert promises(bank) == [("p1", 860.0, "2026-11-12")], text(w)
    assert_clean_end(w, bank, "A")


def test_cannot_afford_amount_gets_the_floor_once_then_attempt_2():
    """A26: the floor is offered once (on attempt 1's day, A30: the full amount was too much) with 'the rest stays
    overdue'; refusing it uses attempt 1, so only attempt 2 (late band) names the floor again, on the deadline."""
    w, bank = call("A", [CARD], [
        ("I cannot afford that amount.", {"intent": "too_much", "reply": "no"}),
        ("No.", NO), ("No.", NO), ("No.", NO)])
    lines = agent(w)
    assert ("I can record a payment of 412.35 dollars instead. The rest stays overdue. "
            "Could you pay 412.35 dollars on Friday 6 November?") in lines, text(w)
    assert "Could you pay 412.35 dollars on Friday 13 November?" in lines, text(w)
    assert sum("412.35" in t for t in lines) == 2, text(w)
    assert (bank.ledger["outcome"], bank.ledger["reason"]) == ("no_promise", "refused")
    assert_clean_end(w, bank, "A")


def test_cannot_pay_anything_or_commit_closes_refused_after_the_attempts():
    w, bank = call("A", [CARD], [
        ("I cannot pay anything and I cannot commit to a date.", {"reply": "no", "intent": "refuse_pay", "pay_amount": "anything"}),
        ("No.", NO), ("No.", NO)])
    assert promises(bank) == [] and (bank.ledger["outcome"], bank.ledger["reason"]) == ("no_promise", "refused")
    assert sum(1 for t in agent(w) if t.startswith("Could you pay")) == 2, text(w)  # the late band's two attempts
    assert_clean_end(w, bank, "A")


def test_salary_day_for_both_products():
    """'My salary arrives on the 12th; can I pay both then?' (pay_date 'then') is a shared counterproposal."""
    w, bank = call("B", [CARD, LOAN], [
        ("Not today. My salary arrives on the 12th; can I pay both then?", {"reply": "no", "intent": "propose", "pay_date": "then"}),
        ("Yes, I confirm.", YES)])
    assert promises(bank) == [("p1", 1374.5, "2026-11-12"), ("p2", 860.0, "2026-11-12")], text(w)
    assert_clean_end(w, bank, "B")


def test_hardship_with_own_day_and_amount_records_without_persuasion():
    w, bank = call("A", [CARD], [
        ("I lost my job, but my new salary comes on the 12th and I can pay the minimum then.",
         {"topic": "hardship", "intent": "propose", "pay_date": "on the 12th", "pay_amount": "the minimum"}),
        ("Yes, I confirm.", YES)])
    lines = agent(w)
    assert any(POL["A"]["lines"]["sympathy"] in t for t in lines), text(w)
    assert not any("Could you pay" in t for t in lines), text(w)
    assert promises(bank) == [("p1", 412.35, "2026-11-12")]
    assert_clean_end(w, bank, "A")


def test_hardship_then_refusal_offers_support_never_persuasion():
    w, bank = call("A", [CARD], [
        ("I was in hospital for a month. I could pay the minimum on the 12th.",
         {"topic": "hardship", "intent": "propose", "pay_date": "on the 12th", "pay_amount": "the minimum"}),
        ("No.", {"reply": "no"}),
        ("No, I really can't do it.", {"reply": "no", "intent": "refuse_pay"}),
        ("No, thank you.", {"reply": "no", "intent": "decline"})])
    lines = agent(w)
    assert not any("Could you pay" in t for t in lines), text(w)
    assert any(POL["A"]["lines"]["support_offer"] in t for t in lines), text(w)
    assert (bank.ledger["outcome"], bank.ledger["reason"]) == ("no_promise", "hardship")
    assert_clean_end(w, bank, "A")


# ---------------------------------------------------------------- B: dates and fragmented answers

def test_fragmented_month_then_day_keeps_the_named_products():
    """'the card and the car loan in November' ... 'Twentieth.': the card is past its deadline (recorded on it, said in
    the read-back), the car loan keeps the 20th, the loan nobody named gets its own attempts."""
    car_early = dict(CAR, days_late=2)
    loan_late = dict(LOAN, days_late=15)
    w, bank = call("B", [CARD, loan_late, car_early], [
        ("Not today. I want to pay the card and the car loan in November.", {"reply": "no", "intent": "vague_time", "pay_date": "in November"}),
        ("Twentieth.", {"intent": "propose", "pay_date": "Twentieth"}),
        ("No.", NO), ("No.", NO),
        ("Yes, I confirm.", YES)])
    lines = agent(w)
    assert lines.count("Which exact day would that be?") == 1, text(w)
    readback = [t for t in lines if t.startswith("So that is")][-1]
    assert "on Friday 13 November, the latest date I can record for it" in readback, readback
    assert promises(bank) == [("p1", 1374.5, "2026-11-13"), ("p3", 2240.0, "2026-11-20")], text(w)
    assert notes(bank) == [("p2", "refused")]
    assert bank.ledger["outcome"] == "promise"
    assert_clean_end(w, bank, "B")


def test_unrelated_event_date_is_not_a_promise():
    """The extractor copied the wedding date out of a comma-joined sentence: it is not a payment day."""
    w, bank = call("A", [CARD], [
        ("I can't pay today, it's a busy month, my cousin's wedding is on the 12th.", {"reply": "no", "pay_date": "on the 12th"}),
        ("No.", NO), ("No.", NO)])
    assert not any("12 November" in t for t in agent(w)), text(w)
    assert "Could you pay 1,374.50 dollars on Friday 6 November?" in agent(w)
    assert_clean_end(w, bank, "A")


def test_explicit_day_number_wins_over_a_wrong_weekday():
    w, bank = call("A", [CARD], [
        ("I can pay on Thursday the 6th.", {"intent": "propose", "pay_date": "Thursday the 6th"}),
        ("Yes.", YES), ("Yes, I confirm.", YES)])
    assert "Just to be sure, did you mean Friday 6 November?" in agent(w), text(w)
    assert promises(bank) == [("p1", 1374.5, "2026-11-06")]
    assert_clean_end(w, bank, "A")


def test_accepted_alternative_replaces_the_old_day():
    for said in [("Yes, the 13th instead of the 20th.", {"reply": "yes", "pay_date": "the 13th instead of the 20th"}),
                 ("Yes, okay, instead of the 20th.", {"reply": "yes", "pay_date": "the 20th"})]:
        w, bank = call("A", [CARD], [
            ("I can pay on the 20th.", {"intent": "propose", "pay_date": "on the 20th"}), said, ("Yes, I confirm.", YES)])
        lines = agent(w)
        assert lines.count("The latest date I can record is Friday 13 November. Can you pay by then?") == 1, text(w)
        assert promises(bank) == [("p1", 1374.5, "2026-11-13")], text(w)
        assert_clean_end(w, bank, "A")


def test_weekend_day_alternative_accepted_with_that_works():
    w, bank = call("A", [CARD], [
        ("I can pay on Saturday.", {"intent": "propose", "pay_date": "on Saturday"}),
        ("Okay, that works.", YES), ("Yes, I confirm.", YES)])
    assert promises(bank) == [("p1", 1374.5, "2026-11-09")], text(w)
    assert_clean_end(w, bank, "A")


# ---------------------------------------------------------------- C: amounts

@pytest.mark.parametrize("said,extracted", [
    ("I can pay 412.35 on Friday.", "412.35"),
    ("I can pay four hundred and twelve dollars and thirty-five cents on Friday.", "four hundred and twelve dollars and thirty-five cents"),
    ("Four hundred and twelve dollars and thirty-five, on Friday.", "Four hundred and twelve dollars"),  # span without the cents
    ("I can do four hundred twelve thirty-five on Friday.", "four hundred twelve thirty-five"),
    ("I can pay the minimum on Friday.", "the minimum"),
])
def test_exact_floor_in_digits_and_words(said, extracted):
    w, bank = call("A", [CARD], [
        (said, {"intent": "propose", "pay_amount": extracted, "pay_date": "on Friday"}), ("Yes, I confirm.", YES)])
    assert not any("can't record" in t for t in agent(w)), text(w)
    assert promises(bank) == [("p1", 412.35, "2026-11-06")], text(w)
    assert_clean_end(w, bank, "A")


def test_cents_in_a_cut_turn():
    """'... dollars and' (pause) 'thirty-five.': the second turn's extraction alone says 35."""
    w, bank = call("A", [CARD], [
        ("The full amount is too much.", {"intent": "too_much", "reply": "no"}),
        ("On Friday I can pay four hundred and twelve dollars and", {"intent": "propose", "pay_amount": "four hundred and twelve dollars", "pay_date": "On Friday"}),
        ("thirty-five.", {"pay_amount": "thirty-five"}),
        ("Yes, I confirm.", YES)])
    assert not any("can't record" in t for t in agent(w)), text(w)
    assert promises(bank) == [("p1", 412.35, "2026-11-06")], text(w)
    assert_clean_end(w, bank, "A")


def test_whole_dollars_just_under_the_floor_are_checked_not_rejected():
    w, bank = call("A", [CARD], [
        ("Four hundred and twelve dollars on Friday.", {"intent": "propose", "pay_amount": "Four hundred and twelve dollars", "pay_date": "on Friday"}),
        ("Yes.", YES), ("Yes, I confirm.", YES)])
    lines = agent(w)
    assert "Just to be sure, did you mean 412.35 dollars?" in lines, text(w)
    assert not any("can't record" in t for t in lines), text(w)
    assert promises(bank) == [("p1", 412.35, "2026-11-06")], text(w)  # the day said with the amount is kept
    assert_clean_end(w, bank, "A")


def test_that_after_the_minimum_was_stated():
    w, bank = call("A", [CARD], [
        ("What is the minimum payment?", {"topic": "how_much"}),
        ("Okay, I'll pay that on Friday.", {"reply": "yes", "intent": "propose", "pay_date": "on Friday", "pay_amount": "that"}),
        ("Yes, I confirm.", YES)])
    assert promises(bank) == [("p1", 412.35, "2026-11-06")], text(w)
    assert_clean_end(w, bank, "A")


def test_really_below_the_floor_keeps_the_day_and_the_product():
    """Below the floor: say so, offer the floor once on the customer's own day; refusing it is a flat refusal that
    uses an attempt, and the product stays in the conversation (it used to be dropped)."""
    w, bank = call("A", [CARD], [
        ("I can pay 150 dollars on Friday.", {"intent": "propose", "pay_amount": "150 dollars", "pay_date": "on Friday"}),
        ("No, only 150.", {"reply": "no", "pay_amount": "150"}),
        ("No.", NO),
        ("Okay, yes, I can do that.", YES), ("Yes, I confirm.", YES)])
    assert ("I'm sorry, I can't record an amount below 412.35 dollars. "
            "Could you pay 412.35 dollars on Friday 6 November?") in agent(w), text(w)
    assert promises(bank) == [("p1", 412.35, "2026-11-13")], text(w)
    assert_clean_end(w, bank, "A")


def test_ambiguous_amount_without_a_usable_reading_is_asked():
    w, bank = call("A", [dict(CARD, past_due=95.0, minimum_payment=28.5)], [
        ("I can pay twelve fifty on Friday.", {"intent": "propose", "pay_amount": "twelve fifty", "pay_date": "on Friday"})])
    assert agent(w)[-1] == "Just to be sure, did you mean 12.50 dollars?", text(w)
    assert not w.ended


# ---------------------------------------------------------------- D: information questions and repeated offers

def test_minimum_question_answers_without_a_new_attempt():
    w, bank = call("A", [CARD], [
        ("No, not today.", NO),
        ("What is the minimum payment?", {"topic": "how_much"})])
    st = state(w)
    assert st["products"][0]["attempts_used"] == 1, st
    assert agent(w)[-1] == "The lowest amount I can record for your credit card ending 5512 is 412.35 dollars.", text(w)
    w.customer("Okay.", {"reply": "ack"})  # acknowledges the explanation: not a yes to the offer
    assert not any(t.startswith("So that is") for t in agent(w)), text(w)
    assert agent(w)[-1] == "Could you pay 1,374.50 dollars on Friday 6 November?", text(w)  # the pending question
    assert state(w)["products"][0]["attempts_used"] == 1
    w.customer("No.", NO)
    assert agent(w)[-1].startswith("Could you pay 412.35 dollars on Friday 13 November?"), text(w)


# ---------------------------------------------------------------- E: several products

def test_three_products_mixed_outcomes_and_one_failed_write():
    w, bank = call("B", [CARD, LOAN, CAR], [
        ("No, not today.", NO),
        ("For the card I can pay the minimum on Friday.", {"intent": "propose", "pay_amount": "the minimum", "pay_date": "on Friday"}),
        ("The personal loan is not mine, I never had it.", {"topic": "dispute"}),
        ("Yes, the car loan on Friday too.", {"reply": "yes", "intent": "propose", "pay_date": "on Friday"}),
        ("Yes, I confirm.", YES)], fail_pids=["p3"])
    assert promises(bank) == [("p1", 412.35, "2026-11-06")], text(w)
    assert notes(bank) == [("p2", "dispute"), ("p3", "service_error")], text(w)
    assert bank.ledger["outcome"] == "promise"
    lines = agent(w)
    assert sum("could not record" in t for t in lines) == 1 and sum(" is recorded" in t for t in lines) == 1, text(w)
    assert_clean_end(w, bank, "B")


def test_shared_day_valid_for_one_product_past_the_other_deadline():
    w, bank = call("B", [CARD, LOAN], [
        ("Not today, but I can pay both on the 20th.", {"reply": "no", "intent": "propose", "pay_date": "on the 20th"}),
        ("Yes, I confirm.", YES)])
    readback = [t for t in agent(w) if t.startswith("So that is")][-1]
    assert "1,374.50 dollars for your credit card ending 5512 on Friday 13 November, the latest date" in readback, readback
    assert "860 dollars for your personal loan on Friday 20 November" in readback
    assert promises(bank) == [("p1", 1374.5, "2026-11-13"), ("p2", 860.0, "2026-11-20")]
    assert_clean_end(w, bank, "B")


def test_shared_weekend_day_is_offered_as_the_next_business_day_once():
    w, bank = call("B", [CARD, LOAN], [
        ("Not today, but both on Saturday.", {"reply": "no", "intent": "propose", "pay_date": "on Saturday"}),
        ("Yes, that works.", YES), ("Yes, I confirm.", YES)])
    assert sum("is not a business day" in t for t in agent(w)) == 1, text(w)
    assert promises(bank) == [("p1", 1374.5, "2026-11-09"), ("p2", 860.0, "2026-11-09")], text(w)
    assert_clean_end(w, bank, "B")


def test_scoped_yes_to_today():
    w, bank = call("B", [CARD, LOAN], [
        ("Yes for the card, but not the loan.", {"reply": "yes"}),
        ("No.", NO), ("Yes, I confirm.", YES)])
    assert promises(bank) == [("p1", 1374.5, "2026-11-03")], text(w)
    assert notes(bank) == [("p2", "refused")]
    assert_clean_end(w, bank, "B")


# ---------------------------------------------------------------- F: confirmation, writes, closure

def test_okay_at_the_read_back_is_not_a_confirmation():
    w, bank = call("A", [CARD], [
        ("I can pay on Friday.", {"intent": "propose", "pay_date": "on Friday"}),
        ("Okay.", {"reply": "yes"})])  # even when the extractor calls it a yes
    assert bank.ledger["promises"] == [] and not w.ended, text(w)
    w.customer("Yes, I confirm.", YES)
    assert promises(bank) == [("p1", 1374.5, "2026-11-06")]
    assert_clean_end(w, bank, "A")


def test_amount_without_a_day_is_never_today():
    w, bank = call("A", [CARD], [
        ("I can pay 500 dollars.", {"intent": "propose", "pay_amount": "500 dollars"}),
        ("Okay.", {"reply": "ack"}), ("Yes.", YES), ("Yes.", YES), ("Yes, I confirm.", YES)])
    assert agent(w).count("Which exact day would that be?") == 2, text(w)
    assert promises(bank) == [("p1", 500.0, "2026-11-13")], text(w)  # the deadline, proposed and accepted
    assert_clean_end(w, bank, "A")


def test_change_at_the_read_back_keeps_the_other_value():
    w, bank = call("A", [CARD], [
        ("I can pay 700 on Friday.", {"intent": "propose", "pay_date": "on Friday", "pay_amount": "700"}),
        ("Actually, make it Thursday.", {"intent": "propose", "pay_date": "Thursday"}),
        ("Make it 800 dollars.", {"intent": "propose", "pay_amount": "800 dollars"}),
        ("Yes, I confirm.", YES)])
    assert promises(bank) == [("p1", 800.0, "2026-11-05")], text(w)
    assert_clean_end(w, bank, "A")


def test_plain_no_at_the_read_back_asks_what_to_change():
    w, bank = call("A", [CARD], [
        ("I can pay on Friday.", {"intent": "propose", "pay_date": "on Friday"}),
        ("No.", {"reply": "no"})])
    assert agent(w)[-1] == "What would you like to change, the amount or the date?", text(w)
    w.customer("The minimum.", {"intent": "propose", "pay_amount": "The minimum"})
    w.customer("Yes, I confirm.", YES)
    assert promises(bank) == [("p1", 412.35, "2026-11-06")], text(w)
    assert_clean_end(w, bank, "A")


def test_successful_write_ends_the_call_once():
    w, bank = call("A", [CARD], [("Yes, I can pay it all today.", YES), ("Yes, I confirm.", YES)])
    calls = [c["tool"] for c in bank.ledger["calls"]]
    assert calls.count("close_call") == 1 and calls[-1] == "close_call" and calls.count("create_promise") == 1
    assert promises(bank) == [("p1", 1374.5, "2026-11-03")]
    assert_clean_end(w, bank, "A")


def test_goodbye_at_the_read_back_notes_every_product():
    w, bank = call("B", [CARD, LOAN], [
        ("Not today, but both on Friday.", {"reply": "no", "intent": "propose", "pay_date": "on Friday"}),
        ("Actually I have to go, bye.", {"intent": "goodbye"})])
    assert promises(bank) == [] and notes(bank) == [("p1", "refused"), ("p2", "refused")], text(w)
    assert (bank.ledger["outcome"], bank.ledger["reason"]) == ("no_promise", "refused")
    assert_clean_end(w, bank, "B")


def test_turn_cap_is_not_a_refusal():
    w, bank = call("B", [CARD, LOAN], [("Sorry, can you say that again?", {"topic": "other_question"})] * 60)
    assert w.ended, text(w)
    assert (bank.ledger["outcome"], bank.ledger["reason"]) == ("no_promise", "service_error"), text(w)
    assert notes(bank) == [("p1", "service_error"), ("p2", "service_error")]
    assert [c["tool"] for c in bank.ledger["calls"]].count("close_call") == 1


def test_one_unclear_answer_at_the_read_back_after_a_slow_identity_check():
    """Non-answers during identity used to share one counter with the read-back: one 'hang on' then closed the call."""
    w, bank = call("A", [CARD], [("Yes, speaking.", YES)] + [("Hmm.", {"reply": "none"})] * 4 + [
        ("4 May 1979.", {}), ("3308", {}), ("Okay.", {"reply": "ack"}),
        ("I can pay on Friday.", {"intent": "propose", "pay_date": "on Friday"}),
        ("Hmm, hang on, let me check my calendar.", {"reply": "none"}),
        ("Yes, I confirm.", YES)], prefix=False)
    assert promises(bank) == [("p1", 1374.5, "2026-11-06")], text(w)
    assert_clean_end(w, bank, "A")


# ---------------------------------------------------------------- G: incomplete identity answers

def test_date_of_birth_in_fragments_with_may():
    w, bank = call("A", [CARD], [
        ("Yes, speaking.", YES), ("It's the fourth of", {}), ("May.", {}), ("Nineteen seventy-nine.", {}),
        ("3308", {}), ("Okay.", {"reply": "ack"}), ("Yes, I can pay it all today.", YES), ("Yes, I confirm.", YES)], prefix=False)
    verifies = [c for c in bank.ledger["calls"] if c["tool"] == "verify_identity"]
    assert [c["args"]["answer"] for c in verifies] == ["1979-05-04", "3308"], text(w)
    assert all(c["result"].get("verified") for c in verifies)
    assert promises(bank) == [("p1", 1374.5, "2026-11-03")]
    assert_clean_end(w, bank, "A")


def test_non_answers_are_not_wrong_answers_and_stay_bounded():
    w, bank = call("A", [CARD], [("Yes, speaking.", YES)] + [("Um.", {"reply": "none"})] * 6, prefix=False)
    assert not any(c["tool"] == "verify_identity" for c in bank.ledger["calls"]), text(w)
    assert w.ended and (bank.ledger["outcome"], bank.ledger["reason"]) == ("not_verified", "declined"), text(w)


# ---------------------------------------------------------------- H: payload

def test_long_three_product_call_stays_far_under_the_code_step_limit():
    sizes = []
    orig = LW.Walk.run_code

    def measured(self, n):
        code = n["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        sizes.append(len(code.encode("utf-8")) + len(json.dumps(self.V).encode("utf-8")))
        return orig(self, n)
    talk = (" I have been so busy with work and the kids, and the traffic this morning was absolutely terrible, "
            "honestly I barely had time for a coffee")
    script = [("Yes, speaking." + talk + ".", YES), ("4 May 1979." + talk + ".", {}), ("3308." + talk + ".", {}),
              ("Okay." + talk + ".", {"reply": "ack"})] + [("Hmm, let me think about it" + talk + ", what was I saying", {})] * 60
    LW.Walk.run_code = measured
    try:
        w, bank = call("B", [CARD, LOAN, CAR], script, prefix=False)
    finally:
        LW.Walk.run_code = orig
    assert w.ended and sizes
    assert max(sizes) < bundle.LIMIT // 2, max(sizes)
    assert len(bundle.code(POL["B"]).encode("utf-8")) < bundle.CODE_BUDGET


# ---------------------------------------------------------------- parsers

@pytest.mark.parametrize("text,status,c", [
    ("six hundred and thirty-seven dollars and fifty", "ok", 63750),
    ("637 dollars 50", "ok", 63750),
    ("637 and 50 cents", "ok", 63750),
    ("six hundred thirty-seven fifty", "interp", 63750),
    ("six thirty-seven fifty", "interp", 63750),
    ("637,50", "interp", 63750),
    ("1,250.50", "ok", 125050),
    ("twelve fifty", "ambiguous", 125000),
    ("six hundred and thirty-seven dollars and", "incomplete", 63700),
    ("I can pay 200, sorry, 250", "ok", 25000),
    ("a hundred", "ok", 10000),
    ("zero", "none", None),
    ("the minimum", "none", None),
])
def test_parse_amount(text, status, c):
    r = R.parse_amount(text)
    assert r["status"] == status and r.get("c") == c, r


def test_amount_span_finds_the_whole_amount():
    assert R.amount_span("Six hundred and thirty-seven dollars and fifty, on Friday.", "six hundred and thirty-seven dollars") == \
        "six hundred and thirty seven dollars and fifty"
    assert R.amount_span("I can pay a hundred on Monday", "a hundred") == "a hundred"


@pytest.mark.parametrize("utt,phrase,neg", [
    ("I cannot pay today.", "today", True),
    ("Not today, but on Friday.", "on Friday", False),
    ("Not today, but on Friday.", "today", True),
    ("Today won't work for me.", "today", True),
    ("I can't pay until Friday.", "until Friday", False),
    ("I can pay on Friday, not today.", "on Friday", False),
])
def test_negated_in(utt, phrase, neg):
    assert R.negated_in(utt, phrase) is neg


def test_scope_keeps_a_card_named_next_to_a_loan():
    st = {"products": [{"id": "p1", "phrase": "credit card ending 5512", "type": "credit_card", "status": "open"},
                       {"id": "p2", "phrase": "personal loan", "type": "personal_loan", "status": "open"},
                       {"id": "p3", "phrase": "car loan", "type": "car_loan", "status": "open"}]}
    got = R.scope_products(st, {"utterance": "the card and the car loan", "pay_date": ""}, {})
    assert [p["id"] for p in got] == ["p1", "p3"]
    got = R.scope_products(st, {"utterance": "the loan", "pay_date": ""}, {})
    assert [p["id"] for p in got] == ["p2", "p3"]


def test_shared_proposal_amount_is_checked_per_product():
    """'the minimum for both on Friday': each product's own floor (the amount used to be ignored for groups)."""
    w, bank = call("B", [CARD, LOAN], [
        ("Not today, but I can pay the minimum for both on Friday.",
         {"reply": "no", "intent": "propose", "pay_amount": "the minimum", "pay_date": "on Friday"}),
        ("Yes, I confirm.", YES)])
    assert promises(bank) == [("p1", 412.35, "2026-11-06"), ("p2", 215.0, "2026-11-06")], text(w)
    assert_clean_end(w, bank, "B")


@pytest.mark.parametrize("phrase", ["all three of them", "both of them", "all 3 accounts", "two of them", "the three loans"])
def test_product_counts_are_not_amounts(phrase):
    ar = R.read_amount({"turn": 1}, {"pay_amount": phrase, "utterance": "I can pay %s on Friday." % phrase, "intent": "propose"})
    assert ar["status"] == "none", ar


def test_decide_step_is_retried_once_before_the_technical_ending():
    nodes = WF["A"]["nodes"]
    first = nodes["decide"]["transitions"][0]
    assert first["target_node"] == "decide_r" and nodes["decide_r"]["transitions"][0]["target_node"] == "end_tech"
    code = lambda n: n["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]  # noqa: E731
    assert code(nodes["decide"]) == code(nodes["decide_r"])
    assert [t["target_node"] for t in nodes["decide"]["transitions"][1:]] == \
        [t["target_node"] for t in nodes["decide_r"]["transitions"][1:]]


def test_a_sandbox_failure_of_the_decide_step_recovers():
    """The platform's sandbox once returned no parseable result: nothing was applied. The retry node runs the same
    step on the same input and the call goes on as if nothing happened."""
    orig = LW.Walk.run_code
    failed = []

    def flaky(self, n):
        if n["name"] == "decide" and len(self.code_steps_per_turn) == 3 and not failed:  # the 4th customer turn
            failed.append(1)
            self.V["decide_response.status"] = "error"
            return
        if n["name"] == "decide":
            self.V["decide_response.status"] = "success"
        return orig(self, n)
    LW.Walk.run_code = flaky
    try:
        w, bank = call("A", [CARD], [("I can pay it all on Friday.", {"intent": "propose", "pay_date": "on Friday"}),
                                     ("Yes, I confirm.", YES)])
    finally:
        LW.Walk.run_code = orig
    assert failed and promises(bank) == [("p1", 1374.5, "2026-11-06")], text(w)
    assert "technical problem" not in text(w)
