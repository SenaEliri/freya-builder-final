"""Gate 4: multi-product write-failure matrix on the local bank stub (Brief A + B rules).

create_promise fails for its first n calls (HTTP 500), across products in get_account order. Brief rules used:
retry a failed write once; a product whose write fails twice gets an add_note with reason service_error; promises
already recorded stay; with at least one recorded promise the outcome is promise; with none, no_promise with the
reason of the first non-paid note. 'recorded' is said only for writes that succeeded.
"""
import copy
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402
from tests.test_walk_public import CASES, POL, SCRIPTS, WF  # noqa: E402

P11 = [{"product_id": "p1", "amount": 220.0, "date": "2026-10-16"}, {"product_id": "p2", "amount": 640.0, "date": "2026-10-16"},
       {"product_id": "p3", "amount": 75.0, "date": "2026-10-16"}]

MATRIX = [
    # n failures, recorded product ids, noted service_error ids, outcome, reason
    (0, ["p1", "p2", "p3"], [], "promise", None),
    (1, ["p1", "p2", "p3"], [], "promise", None),
    (2, ["p2", "p3"], ["p1"], "promise", None),
    (3, ["p2", "p3"], ["p1"], "promise", None),
    (4, ["p3"], ["p1", "p2"], "promise", None),
    (6, [], ["p1", "p2", "p3"], "no_promise", "service_error"),
]


@pytest.mark.parametrize("n,rec,noted,outcome,reason", MATRIX)
def test_write_failures_pub11(n, rec, noted, outcome, reason):
    case = copy.deepcopy(CASES["PUB-11"])
    bank = LW.Bank(case, faults=[{"tool": "create_promise", "fail_first_n": n}] if n else [])
    w = LW.Walk(WF["B"], dict(case["variables"], customer_id="c_m%d" % n), bank)
    w.start()
    for txt, ex in SCRIPTS["PUB-11"]:
        if w.ended:
            break
        w.customer(txt, ex)
    led = bank.ledger
    text = LW.text_of(w)
    assert w.ended, text
    assert sorted(p["product_id"] for p in led["promises"]) == rec, text
    assert sorted(x["product_id"] for x in led["notes"] if x["reason"] == "service_error") == noted, text
    assert (led["outcome"], led["reason"]) == (outcome, reason), text
    for p in led["promises"]:
        assert p in P11
    fails = lessons.check(LW.events(w), led, POL["B"], code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, text)
    assert not w.rejected
    # honesty: one 'could not record' sentence per failed product, one 'recorded' sentence per recorded product
    agent = [t for k, t, _ in LW.events(w) if k == "agent"]
    said_fail = sum(t.count("could not record") for t in agent)
    assert said_fail == len(noted), text


@pytest.mark.parametrize("tool", ["add_note", "close_call", "get_account", "transfer_to_agent", "schedule_callback"])
def test_other_tool_fails_once(tool):
    """Every other tool failing once (HTTP 500) is retried and the case still ends correctly."""
    cid = {"add_note": "PUB-12", "close_call": "PUB-01", "get_account": "PUB-01", "transfer_to_agent": "PUB-09",
           "schedule_callback": "PUB-02"}[tool]
    case = copy.deepcopy(CASES[cid])
    bank = LW.Bank(case, faults=[{"tool": tool, "fail_first_n": 1}])
    pol = POL[case["brief"]]
    w = LW.Walk(WF[case["brief"]], dict(case["variables"], customer_id="c_f_" + tool), bank)
    w.start()
    for txt, ex in SCRIPTS[cid]:
        if w.ended:
            break
        w.customer(txt, ex)
    from tools.score import score_ledger
    r = score_ledger(case, bank.ledger)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))
    fails = lessons.check(LW.events(w), bank.ledger, pol, code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, LW.text_of(w))


def test_single_product_write_fails_twice():
    """Brief A: create_promise fails twice -> say it could not be recorded, close no_promise / service_error."""
    case = copy.deepcopy(CASES["PUB-10"])
    case["expected"].update({"outcome": "no_promise", "reason": "service_error", "promises": []})
    bank = LW.Bank(case, faults=[{"tool": "create_promise", "fail_first_n": 2}])
    w = LW.Walk(WF["A"], dict(case["variables"], customer_id="c_sf2"), bank)
    w.start()
    for txt, ex in SCRIPTS["PUB-10"]:
        if w.ended:
            break
        w.customer(txt, ex)
    from tools.score import score_ledger
    r = score_ledger(case, bank.ledger)
    text = LW.text_of(w)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], text)
    agent = " ".join(t for k, t, _ in LW.events(w) if k == "agent")
    assert "could not record" in agent and " is recorded" not in agent, text
    assert POL["A"]["lines"]["after_promise"] not in agent, text
    fails = lessons.check(LW.events(w), bank.ledger, POL["A"], code_steps=w.code_steps_per_turn, max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, text)


@pytest.mark.parametrize("tool,cid,outcome", [
    ("transfer_to_agent", "PUB-09", ("no_promise", "service_error")),
    ("schedule_callback", "PUB-02", ("not_reached", "no_callback")),
    ("get_account", "PUB-01", ("no_promise", "service_error")),
])
def test_tool_fails_twice(tool, cid, outcome):
    """A tool that fails twice ends the call honestly with a technical-problem sentence and a fitting outcome."""
    case = copy.deepcopy(CASES[cid])
    case["expected"].update({"outcome": outcome[0], "reason": outcome[1], "promises": [], "transfers": [], "callbacks": []})
    bank = LW.Bank(case, faults=[{"tool": tool, "fail_first_n": 2}])
    w = LW.Walk(WF[case["brief"]], dict(case["variables"], customer_id="c_f2_" + tool), bank)
    w.start()
    for txt, ex in SCRIPTS[cid]:
        if w.ended:
            break
        w.customer(txt, ex)
    from tools.score import score_ledger
    r = score_ledger(case, bank.ledger)
    text = LW.text_of(w)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], text)
    assert POL[case["brief"]]["lines"]["tech_problem"] in text, text
