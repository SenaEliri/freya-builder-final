"""Phase 0 regressions without the model: recorded answers -> assemble -> same behaviour facts as the golden policies.

The answers files are real model outputs for the public briefs and the team's messy fixture (saved from gate runs).
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.policy import extract, openapi, schema  # noqa: E402
from qa import policy_diff  # noqa: E402

FX = ROOT / "tests" / "fixtures"
SETS = {
    "a": (["briefs/brief-a.md"], "tools/openapi.json", "policy-a.json"),
    "ab": (["briefs/brief-a.md", "briefs/brief-b.md"], "tools/openapi.json", "policy-ab.json"),
    "messy": (["tests/fixtures/messy-brief.md"], "tests/fixtures/messy-openapi.json", "policy-messy.json"),
}


@pytest.mark.parametrize("name", sorted(SETS))
def test_recorded_answers_match_golden(name):
    briefs, api, gold = SETS[name]
    ts = openapi.load(str(ROOT / api))
    answers = json.loads((FX / ("answers-%s.json" % name)).read_text())
    texts = [(ROOT / b).read_text() for b in briefs]
    problems = {}
    pol = extract.assemble(answers, texts, ts, problems)
    assert schema.validate(pol, ts) == []
    assert policy_diff.diff(pol, json.loads((FX / gold).read_text())) == []
    for k, v in pol["lines"].items():
        assert "{{" not in v and "}}" not in v, k


def test_first_request_listed_as_attempt_is_dropped():
    bands = [{"name": "A", "min": 1, "max": 10, "deadline_kind": "business_days", "deadline_n": 10, "attempts": 1},
             {"name": "B", "min": 11, "max": 60, "deadline_kind": "business_days", "deadline_n": 6, "attempts": 3}]
    raw = [{"n": 1, "date_rule": "today", "amount_rule": "full", "bands": None},
           {"n": 2, "date_rule": "end_of_week", "amount_rule": "full_or_floor", "bands": None},
           {"n": 3, "date_rule": "deadline", "amount_rule": "floor", "bands": ["group B"]}]
    problems = {}
    got = extract.normalize_attempts(raw, {"date_rule": "today", "amount_rule": "full"}, bands, problems)
    assert got == [{"n": 1, "date_rule": "end_of_week", "amount_rule": "full_or_floor", "bands": None},
                   {"n": 2, "date_rule": "deadline", "amount_rule": "floor", "bands": ["B"]}]
    assert bands[1]["attempts"] == 2 and bands[0]["attempts"] == 1
    assert problems["attempts"]


@pytest.mark.parametrize("key,text,ok", [
    ("below_floor", "That amount cannot be recorded. Can you pay {floor}?", True),
    ("support_offer", "Would you like me to connect you with the customer support team?", True),
    ("paid_reply", "that payments can take one business day to appear.", False),
    ("goodbye", "Say goodbye to the customer.", False),
    ("third_party_ask", "When are you available?", False),
    ("third_party_ask", "When can {title} {last_name} be reached?", True),
    ("goodbye", "The customer can call us back.", False),
    ("goodbye", "Thank you for your time. Goodbye", False),
])
def test_line_checks(key, text, ok):
    assert (extract.line_problem(key, text) is None) == ok
