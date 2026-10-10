"""Gate 2: dates. A table over three 'now' values (a Wednesday, a Friday, a year end) plus walks of the date
cases moved to those days. Expected values are worked out by hand from Brief A's rules (business days Mon-Fri,
holidays 26 Oct, 11 Nov, 26 Nov, 25 Dec 2026 and 1 Jan 2027; early band deadline = 12th business day, late = 7th)."""
import copy
import datetime
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "builder" / "runtime"))
import agent_runtime as R  # noqa: E402
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402
from tests.test_walk_public import CASES, POL, WF, verified_prefix  # noqa: E402
from tools.score import score_ledger  # noqa: E402

D = datetime.date
WED, FRI, YEND = D(2026, 10, 14), D(2026, 10, 16), D(2026, 12, 30)
CAL = POL["A"]["calendar"]
CFG = POL["A"]["dates"]

PARSE = [
    (WED, "today", "2026-10-14"), (WED, "tomorrow", "2026-10-15"), (WED, "Friday", "2026-10-16"),
    (WED, "this Friday", "2026-10-16"), (WED, "next Friday", "2026-10-23"), (WED, "Friday next week", "2026-10-23"),
    (WED, "Monday the 26th", "2026-10-26"), (WED, "the 23rd", "2026-10-23"), (WED, "on the 6th of November", "2026-11-06"),
    (WED, "the twenty-third of October", "2026-10-23"), (WED, "the 23rd, sorry, the 22nd", "2026-10-22"),
    (WED, "16/10", "2026-10-16"), (WED, "Not today, but I can pay the minimum on Friday.", "2026-10-16"),
    (WED, "Today is not possible, tomorrow then", "2026-10-15"), (WED, "in two days", "2026-10-16"),
    (FRI, "Friday", "2026-10-16"), (FRI, "next Friday", "2026-10-23"), (FRI, "Monday", "2026-10-19"),
    (FRI, "next Monday", "2026-10-19"), (FRI, "the day after tomorrow", "2026-10-18"),
    (YEND, "tomorrow", "2026-12-31"), (YEND, "the 5th of January", "2027-01-05"), (YEND, "next Monday", "2027-01-04"),
    (YEND, "the 2nd", "2027-01-02"), (YEND, "this Friday", "2027-01-01"), (YEND, "January the fourth", "2027-01-04"),
]


@pytest.mark.parametrize("today,text,want", PARSE)
def test_parse_ok(today, text, want):
    r = R.parse_pay_date(text, today, CAL, CFG)
    assert r == {"status": "ok", "date": want}, (text, r)


@pytest.mark.parametrize("today,text,status", [
    (WED, "the week after next", "vague"), (WED, "I can't pay today. Maybe the week after next.", "vague"),
    (WED, "end of the month", "vague"), (WED, "when my salary comes", "vague"), (WED, "end of the week", "vague"),
    (WED, "not today", "none"), (YEND, "on the 6th of November", "past"), (YEND, "Monday the 26th", "conflict"),
    (WED, "Friday the 17th", "conflict"),
])
def test_parse_status(today, text, status):
    assert R.parse_pay_date(text, today, CAL, CFG)["status"] == status


@pytest.mark.parametrize("today,early,late,eow,nbd", [
    (WED, "2026-11-02", "2026-10-23", "2026-10-16", "2026-10-15"),
    (FRI, "2026-11-04", "2026-10-28", "2026-10-23", "2026-10-19"),
    (YEND, "2027-01-18", "2027-01-11", "2026-12-31", "2026-12-31"),
])
def test_deadlines_and_rules(today, early, late, eow, nbd):
    bands = dict((b["name"], b) for b in POL["A"]["bands"])
    got_early = R.add_business(today, bands["early"]["deadline_n"], CAL)
    got_late = R.add_business(today, bands["late"]["deadline_n"], CAL)
    assert (str(got_early), str(got_late)) == (early, late)
    assert str(R.date_for_rule("end_of_week", today, got_early, CAL)) == eow
    assert str(R.date_for_rule("next_business_day", today, got_early, CAL)) == nbd


def moved(cid, now, script, promises):
    c = copy.deepcopy(CASES[cid])
    c["variables"]["now"] = now
    c["expected"]["promises"] = promises
    return c, script


SYNTH = {
    # Friday: 'end of week' offer moves to next Friday (attempt 1, full amount)
    "fri-PUB-10": moved("PUB-10", "2026-10-16T11:00", verified_prefix("PUB-10") + [
        ("No, not today.", {"reply": "no"}), ("Yes, I can do that.", {"reply": "yes"}), ("Yes, I confirm.", {"reply": "yes"})],
        [{"product_id": "p1", "amount": 365.0, "date": "2026-10-23"}]),
    # year end: Saturday 2 January -> next business day Monday 4 January offered and accepted
    "yend-PUB-07": moved("PUB-07", "2026-12-30T11:00", verified_prefix("PUB-07") + [
        ("I can't pay today. Maybe the 2nd of January.", {"reply": "no", "intent": "propose", "pay_date": "the 2nd of January"}),
        ("Yes, that works.", {"reply": "yes"}), ("Yes, I confirm.", {"reply": "yes"})],
        [{"product_id": "p1", "amount": 540.0, "date": "2027-01-04"}]),
    # year end, late band (14 days): a date after the deadline -> latest date (11 January) offered and accepted
    "yend-PUB-04": moved("PUB-04", "2026-12-30T11:00", verified_prefix("PUB-04") + [
        ("My salary arrives on 20 January, I can pay then.", {"intent": "propose", "pay_date": "on 20 January"}),
        ("Okay, the 11th is fine.", {"reply": "yes", "pay_date": "the 11th"}), ("Yes, I confirm.", {"reply": "yes"})],
        [{"product_id": "p1", "amount": 1250.0, "date": "2027-01-11"}]),
    # year end: holiday 1 January named -> next business day (4 January)
    "yend-PUB-10": moved("PUB-10", "2026-12-30T11:00", verified_prefix("PUB-10") + [
        ("Not today. On the first of January.", {"reply": "no", "intent": "propose", "pay_date": "on the first of January"}),
        ("Yes.", {"reply": "yes"}), ("Yes, I confirm.", {"reply": "yes"})],
        [{"product_id": "p1", "amount": 365.0, "date": "2027-01-04"}]),
    # Friday, too much: minimum on 'Friday' means today (a Friday)
    "fri-PUB-06": moved("PUB-06", "2026-10-16T11:00", verified_prefix("PUB-06") + [
        ("The full amount is too much right now.", {"intent": "too_much", "reply": "no"}),
        ("I can pay the minimum next Tuesday.", {"intent": "propose", "pay_date": "next Tuesday", "pay_amount": "the minimum"}),
        ("Yes, I confirm.", {"reply": "yes"})],
        [{"product_id": "p1", "amount": 637.5, "date": "2026-10-20"}]),
}


@pytest.mark.parametrize("name", sorted(SYNTH))
def test_moved_date_cases(name):
    (case, script) = SYNTH[name]
    pol = POL["A"]
    bank = LW.Bank(case)
    w = LW.Walk(WF["A"], dict(case["variables"], customer_id="c_" + name), bank)
    w.start()
    for txt, ex in script:
        if w.ended:
            break
        w.customer(txt, ex)
    assert w.ended, LW.text_of(w)
    r = score_ledger(case, bank.ledger)
    assert r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))
    fails = lessons.check(LW.events(w), bank.ledger, pol, code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, LW.text_of(w))
