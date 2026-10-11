"""Calendar and generalization checks for the candidate-2 runtime.

1. Calendar matrix: local calls at many `now` days (Fridays, days before the brief's holidays, year end and the 2027
   rollover), both bands. The recorded dates are compared with docs/team-notes/scripts/date_rules.py, the team's
   separately written implementation of the same rules (an oracle the runtime does not share code with).
2. Other brief shapes: the builder self-tests and the core fixes on the messy and raw2 fixtures (renamed tool API,
   other identity questions, other bands, calendar-day deadlines, other call variables).
"""
import datetime
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.emit import workflow as W  # noqa: E402
from builder.policy import openapi  # noqa: E402
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402
from qa import selftest  # noqa: E402

_spec = importlib.util.spec_from_file_location("date_rules", ROOT / "docs" / "team-notes" / "scripts" / "date_rules.py")
ORACLE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ORACLE)

TS = openapi.load(str(ROOT / "tools" / "openapi.json"))
POL_A = json.load(open(ROOT / "tests" / "fixtures" / "policy-a.json"))
WF_A = W.build(POL_A, TS)
HOL = set(POL_A["calendar"]["holidays"])
ID = {"date_of_birth": "1979-05-04", "phone_last4": "3308"}
PRE = [("Yes, speaking.", {"reply": "yes"}), ("4 May 1979.", {}), ("3308", {}), ("Okay.", {"reply": "ack"})]
YES, NO = {"reply": "yes"}, {"reply": "no", "intent": "refuse_pay"}
LATE = {"type": "credit_card", "card_last4": "7741", "past_due": 980.0, "days_late": 10, "minimum_payment": 294.0}
EARLY = {"type": "personal_loan", "past_due": 455.0, "days_late": 3, "instalment_amount": 151.67}
NOWS = ["2026-10-14", "2026-10-16", "2026-10-23", "2026-11-10", "2026-11-25", "2026-12-24", "2026-12-30", "2027-01-04"]


def said(d):
    """A day as a customer says it ('the 2nd of December'); the extractor copies spoken words, never ISO dates."""
    suf = "th" if 10 <= d.day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return "the %d%s of %s" % (d.day, suf, d.strftime("%B"))


def walk_a(now, product, script):
    bank = LW.Bank({"identity": ID, "products": [dict(product)]})
    w = LW.Walk(WF_A, {"first_name": "Lea", "last_name": "Moss", "title": "Ms", "now": now + "T11:00", "customer_id": "c_cal"}, bank)
    w.start()
    for t, e in PRE + script:
        if w.ended:
            break
        w.customer(t, e)
    return w, bank


def oracle(now):
    t = datetime.date.fromisoformat(now)
    return {"a1": ORACLE.attempt1_date(t, HOL), "late": ORACLE.nth_business_day_after(t, 7, HOL),
            "early": ORACLE.nth_business_day_after(t, 12, HOL), "today": t}


@pytest.mark.parametrize("now", NOWS)
def test_attempt_dates_match_the_oracle(now):
    o = oracle(now)
    w, bank = walk_a(now, LATE, [("No, not today.", NO)])
    off = json.loads(w.V["rb_state"])["products"][0]["offer"]
    assert (off["amount"], off["date"]) == (980.0, o["a1"].isoformat()), LW.text_of(w)
    for t, e in [("No.", NO), ("Yes.", YES), ("Yes, I confirm.", YES)]:
        w.customer(t, e)
    assert [(p["amount"], p["date"]) for p in bank.ledger["promises"]] == [(294.0, o["late"].isoformat())], LW.text_of(w)
    assert not lessons.check(LW.events(w), bank.ledger, POL_A, code_steps=w.code_steps_per_turn)


@pytest.mark.parametrize("now", NOWS)
def test_day_after_the_deadline_gets_the_deadline(now):
    o = oracle(now)
    far = said(o["early"] + datetime.timedelta(days=30))
    w, bank = walk_a(now, EARLY, [("I can pay on %s." % far, {"intent": "propose", "pay_date": "on " + far}),
                                  ("Yes.", YES), ("Yes, I confirm.", YES)])
    assert [(p["amount"], p["date"]) for p in bank.ledger["promises"]] == [(455.0, o["early"].isoformat())], LW.text_of(w)


@pytest.mark.parametrize("now", NOWS)
def test_weekend_or_holiday_day_gets_the_oracles_alternative(now):
    o = oracle(now)
    day = o["today"] + datetime.timedelta(days=1)
    while ORACLE.is_business_day(day, HOL):
        day += datetime.timedelta(days=1)  # the next weekend day or holiday
    verdict, alt = ORACLE.check_promise_date(o["today"], day, o["early"], HOL)
    w, bank = walk_a(now, EARLY, [("I can pay on %s." % said(day), {"intent": "propose", "pay_date": "on " + said(day)}),
                                  ("Yes, that works.", YES), ("Yes, I confirm.", YES)])
    assert verdict in ("not_business_day", "after_deadline")
    assert [p["date"] for p in bank.ledger["promises"]] == [alt.isoformat()], LW.text_of(w)


# ---------------------------------------------------------------- other brief shapes

SHAPES = {
    "messy": (ROOT / "tests" / "fixtures" / "policy-messy.json", ROOT / "tests" / "fixtures" / "messy-openapi.json"),
    "raw2": (ROOT / "submission" / "raw2-brief.policy.json", ROOT / "tests" / "fixtures" / "raw2-openapi.json"),
}


def shape(name):
    pp, ap = SHAPES[name]
    ts = openapi.load(str(ap))
    pol = json.load(open(pp))
    if not pol.get("api"):
        pol["api"] = ts["api"]
    return pol, ts, W.build(pol, ts)


def walk_shape(pol, ts, wf, case, script):
    bank = LW.Bank(case, api=ts.get("api"), reasons=selftest.reasons_table(pol))
    bank.max_wrong = int(pol["identity"].get("max_wrong") or 3)
    w = LW.Walk(wf, dict(case["variables"], customer_id="c_shape"), bank)
    w.start()
    for t, e in script:
        if w.ended:
            break
        w.customer(t, e)
    return w, bank


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_builder_self_tests_pass_on_other_shapes(name):
    pol, ts, wf = shape(name)
    bad = [r for r in selftest.run_all(pol, ts, wf) if not r["ok"]]
    assert not bad, bad


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_core_fixes_on_other_shapes(name):
    pol, ts, wf = shape(name)
    late = len(pol["bands"]) - 1
    case, right, _ = selftest.make_case(pol, n_products=1, band_index=late)
    pre = selftest.verified_prefix(pol, right)
    today = datetime.date.fromisoformat(case["variables"]["now"][:10])
    nxt_d = ORACLE.nth_business_day_after(today, 1, set(pol["calendar"].get("holidays") or []),
                                          tuple(pol["calendar"].get("weekend") or (5, 6)))
    nxt = nxt_d.isoformat()
    floor_field = pol["products"][case["products"][0]["type"]]["floor_field"]
    floor = case["products"][0][floor_field]
    # a negated today is not a promise for today
    w, bank = walk_shape(pol, ts, wf, case, pre + [("I cannot pay today.", {"reply": "no", "intent": "refuse_pay", "pay_date": "today"})])
    assert not any(t.startswith(pol["lines"]["readback"].split("{")[0]) for r, t, _ in w.transcript if r == "agent"), LW.text_of(w)
    # 'the minimum' is this product's floor, on the customer's day
    case2, right2, _ = selftest.make_case(pol, n_products=1, band_index=late)
    w, bank = walk_shape(pol, ts, wf, case2, pre + [
        ("I can pay the minimum on %s." % said(nxt_d), {"intent": "propose", "pay_amount": "the minimum",
                                                       "pay_date": "on " + said(nxt_d)}),
        ("Yes, I confirm.", YES)])
    assert [(p["amount"], p["date"]) for p in bank.ledger["promises"]] == [(floor, nxt)], LW.text_of(w)
    # 'that full amount is too much' gets the floor offer with 'the rest stays overdue', never a full-amount read-back
    case3, _, _ = selftest.make_case(pol, n_products=1, band_index=late)
    w, bank = walk_shape(pol, ts, wf, case3, pre + [
        ("That full amount is too much for me.", {"reply": "no", "intent": "too_much", "pay_amount": "full amount"})])
    last = [t for r, t, _ in w.transcript if r == "agent"][-1]
    assert pol["lines"]["rest_overdue"] in last and "%g" % floor in last.replace(",", ""), LW.text_of(w)
