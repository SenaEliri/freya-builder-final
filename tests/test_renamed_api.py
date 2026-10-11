"""The finals keep the seven tool names but may rename fields. tests/fixtures/renamed-openapi.json renames almost
every request and response field of the public tool API (field -> question, products -> accounts, past_due ->
amount_due, date -> promise_date, outcome -> result, queue -> team, ...). The same public scripts must still
produce the right bank records through the role mapping (builder/policy/roles.py)."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.emit import workflow as W  # noqa: E402
from builder.policy import openapi  # noqa: E402
from qa import lessons  # noqa: E402
from qa import localwalk as LW  # noqa: E402
from tests.test_walk_public import CASES, POL, SCRIPTS  # noqa: E402
from tools.score import score_ledger  # noqa: E402

TS = openapi.load(str(ROOT / "tests" / "fixtures" / "renamed-openapi.json"))
WF = dict((k, W.build(dict(p, api=None), TS)) for k, p in POL.items())


def test_roles_resolved():
    assert TS["api_problems"] == []
    assert TS["api"]["verify_identity"]["req"]["field"] == "question"
    assert TS["api"]["get_account"]["item"]["past_due"] == "amount_due"
    assert TS["enums"]["identity_fields"] == ["date_of_birth", "phone_last4"]


def test_bodies_use_renamed_fields():
    wf = WF["A"]
    body = wf["nodes"]["wp1c"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert set(body) == {"customer_id", "account_id", "promise_amount", "promise_date"}
    vb = wf["nodes"]["verify"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert set(vb) == {"customer_id", "question", "value"}


@pytest.mark.parametrize("cid", sorted(SCRIPTS))
def test_public_scripts_on_renamed_api(cid):
    case = CASES[cid]
    bank = LW.Bank(case, api=TS["api"])
    w = LW.Walk(WF[case["brief"]], dict(case["variables"], customer_id="c_" + cid), bank)
    w.start()
    for txt, ex in SCRIPTS[cid]:
        if w.ended:
            break
        w.customer(txt, ex)
    r = score_ledger(case, bank.ledger)
    assert w.ended and r["pass"], "%s\n%s" % (r["failed"], LW.text_of(w))
    fails = lessons.check(LW.events(w), bank.ledger, POL[case["brief"]], code_steps=w.code_steps_per_turn,
                          max_node_entries=w.nodes_entered)
    assert not fails, "%s\n%s" % (fails, LW.text_of(w))
