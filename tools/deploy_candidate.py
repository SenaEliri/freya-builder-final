"""Build a test candidate from a saved policy and publish it to a NEW rb- slot, leaving every existing agent as it is.

    python3 tools/deploy_candidate.py submission/brief-a.policy.json tools/openapi.json --slot rb-c2-brief-a
    python3 tools/deploy_candidate.py submission/brief-a.policy.json tools/openapi.json --local-only   # no network

The policy is the one the official build extracted (builder/build.py), so a candidate differs from the agent built
before only by the builder code (runtime + emitter). Steps: validate the policy, emit, lint, the builder self-tests on
the local bank stub, then (unless --local-only) platform dry run, save + publish to the slot, chat smoke test and
export. Writes <out>/<name>.workflow.json and <out>/<name>.manifest.json (slot, workflow and agent ids, published
version, source commit, runtime hash, builder identity, export sha256). Needs env.sh sourced for the live part.
A slot that already exists in .freya-agents.json is refused unless --update is given (never the frozen candidate).
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.emit import bundle  # noqa: E402
from builder.emit import workflow as W  # noqa: E402
from builder.policy import openapi, schema  # noqa: E402
from qa import selftest  # noqa: E402

FROZEN = ("rb-brief-a", "rb-brief-a-brief-b")  # candidate 1, kept for QA (HANDOFF.md)


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def commit():
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "builder"], capture_output=True, text=True)
    return r.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("policy")
    ap.add_argument("openapi")
    ap.add_argument("--slot", help="new rb- slot to publish to")
    ap.add_argument("--out", default=str(ROOT / "submission" / "candidate-2"))
    ap.add_argument("--local-only", action="store_true", help="stop after the local checks (no network)")
    ap.add_argument("--update", action="store_true", help="allow updating an existing (non-frozen) slot")
    a = ap.parse_args(argv)
    ts = openapi.load(a.openapi)
    policy = json.load(open(a.policy))
    errs = schema.validate(policy, ts)
    if errs:
        sys.exit("policy invalid: %s" % errs[:5])
    wf = W.build(policy, ts)
    lint = [x for x in W.lint(wf) if not x.startswith("unreachable")]
    if lint:
        sys.exit("lint: %s" % lint)
    code_bytes = len(bundle.code(dict(policy, api=policy.get("api") or ts["api"])).encode())
    tests = list(selftest.run_all(policy, ts, wf))
    failed = [t["name"] for t in tests if not t["ok"]]
    for t in tests:
        print(("PASS" if t["ok"] else "FAIL"), "self-test:", t["name"], "" if t["ok"] else t)
    if failed:
        sys.exit("self-tests failed: %s" % failed)
    name = pathlib.Path(a.policy).name.replace(".policy.json", "")
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    man = {"policy": str(pathlib.Path(a.policy).resolve().relative_to(ROOT)), "policy_sha256": sha256(a.policy),
           "openapi_sha256": sha256(a.openapi), "source_commit": commit(), "runtime_hash": bundle.runtime_hash(),
           "nodes": len(wf["nodes"]), "decide_code_bytes": code_bytes, "self_tests": len(tests),
           "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if a.local_only:
        path = out / ("%s.workflow.local.json" % name)
        path.write_text(json.dumps({"workflow": wf}, indent=1))
        man.update(published=False, export=str(path.relative_to(ROOT)), export_sha256=sha256(path))
        (out / ("%s.manifest.local.json" % name)).write_text(json.dumps(man, indent=1))
        print(json.dumps(man, indent=1))
        return 0
    from builder import build as B
    from builder import platform as P
    if not a.slot or not a.slot.startswith("rb-") or a.slot in FROZEN:
        sys.exit("give a new --slot starting with rb- (not %s)" % ", ".join(FROZEN))
    state = json.loads(P.STATE_FILE.read_text()) if P.STATE_FILE.exists() else {}
    if a.slot in state and not a.update:
        sys.exit("slot %s exists (workflow %s); pass --update to publish a new version to it" % (a.slot, state[a.slot]["workflow_id"]))
    P.freya.validate_workflow(a.slot + " dry run", wf)
    saved = P.save(a.slot, wf)
    ok, info = B.chat_smoke(saved["workflow_id"], policy, None)
    path = out / ("%s.workflow.json" % name)
    P.freya.export_workflow(saved["workflow_id"], str(path))
    man.update(published=True, slot=a.slot, workflow_id=saved["workflow_id"], agent_id=saved["agent_id"],
               version=saved.get("version"), smoke_ok=ok, smoke=info, export=str(path.relative_to(ROOT)),
               export_sha256=sha256(path))
    (out / ("%s.manifest.json" % name)).write_text(json.dumps(man, indent=1))
    print(json.dumps(man, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
