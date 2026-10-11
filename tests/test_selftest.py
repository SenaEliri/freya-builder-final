"""The builder's own self-tests (qa/selftest.py) pass on every fixture policy and tool API."""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.emit import workflow as W  # noqa: E402
from builder.policy import openapi  # noqa: E402
from qa import selftest  # noqa: E402

PAIRS = [("policy-a.json", "tools/openapi.json"), ("policy-ab.json", "tools/openapi.json"),
         ("policy-messy.json", "tests/fixtures/messy-openapi.json"), ("policy-a.json", "tests/fixtures/renamed-openapi.json"),
         ("policy-ab.json", "tests/fixtures/renamed-openapi.json")]


@pytest.mark.parametrize("pol,api", PAIRS)
def test_selftests_pass(pol, api):
    p = json.loads((ROOT / "tests" / "fixtures" / pol).read_text())
    p.pop("api", None)
    ts = openapi.load(str(ROOT / api))
    wf = W.build(p, ts)
    bad = [r for r in selftest.run_all(p, ts, wf) if not r["ok"]]
    assert not bad, json.dumps(bad, indent=1)
