"""Build a workflow from a policy fixture and save it to an rb- slot (development gates before Phase 0 lands).

    python3 -m qa.deploy_fixture rb-a tests/fixtures/policy-a.json [tools/openapi.json]
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import platform as P  # noqa: E402
from builder.emit import workflow as W  # noqa: E402
from builder.policy import openapi, schema  # noqa: E402


def main():
    slot, pol_path = sys.argv[1], sys.argv[2]
    api_path = sys.argv[3] if len(sys.argv) > 3 else str(ROOT / "tools" / "openapi.json")
    ts = openapi.load(api_path)
    pol = json.load(open(pol_path))
    errs = schema.validate(pol, ts)
    if errs:
        sys.exit("policy invalid: %s" % errs)
    wf = W.build(pol, ts)
    lint = W.lint(wf)
    if lint:
        sys.exit("lint: %s" % lint)
    P.freya.validate_workflow(slot + " dry", wf)
    saved = P.save(slot, wf)
    print(json.dumps({"slot": slot, "workflow_id": saved["workflow_id"], "agent_id": saved["agent_id"],
                      "version": saved.get("version"), "nodes": len(wf["nodes"])}))


if __name__ == "__main__":
    main()
