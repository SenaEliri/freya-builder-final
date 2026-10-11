"""One command: bank brief(s) + the bank's tool API file -> a tested phone agent on Freya, exported, with a trace.

    python3 builder/build.py <brief.md> <openapi.json>
    python3 builder/build.py <base brief.md> <extension brief.md> ... <openapi.json> [--slot rb-x] [--out submission]

Steps (each one in the trace, traces/<UTC start>-<slot>.txt):
  1. read the tool API file; map its field names to roles (builder/policy/roles.py)
  2. policy extraction with Freya's model through the chat API (builder/policy/extract.py), bounded in time
  3. validate the policy against the tool API; emit the workflow; lint it
  4. self-tests on a local bank stub, with customers made up from the policy itself (no practice cases)
  5. platform dry run, save to the rb- slot (created once, then updated in place and published)
  6. chat smoke test on the published workflow (opening + first decide step), then export
At call time the phone agent calls only the bank's tool API (hard rule 4). Needs env.sh sourced.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from builder import platform as P  # noqa: E402
from builder.emit import bundle  # noqa: E402
from builder.emit import workflow as W  # noqa: E402
from builder.policy import extract, openapi, schema  # noqa: E402
from builder.trace import Trace  # noqa: E402

BUDGET_S = 30 * 60          # hard rule 7: one build at most 30 minutes
EXTRACT_BUDGET_S = 14 * 60  # the model part gets at most this much
SMOKE_MIN_LEFT_S = 4 * 60   # skip the live smoke test when less than this is left


class BuildError(Exception):
    pass


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "brief"


def git_commit():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


def identity_hash():
    """Hash of the builder code that produced the agent (same as `python3 -m qa.identity`)."""
    h = hashlib.sha256()
    for f in sorted((ROOT / "builder").rglob("*.py")):
        h.update(str(f.relative_to(ROOT)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()[:16]


def rel(path):
    try:
        return str(pathlib.Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="brief file(s) then the tool API file (.json)")
    ap.add_argument("--slot", help="workflow slot (must start with rb-)")
    ap.add_argument("--out", default=str(ROOT / "submission"))
    ap.add_argument("--no-smoke", action="store_true", help="skip the live chat smoke test")
    ap.add_argument("--mock-url", default=os.environ.get("FREYA_MOCK_URL"),
                    help="case folder builds: the address of your own mock of the bank's services")
    a = ap.parse_args(argv)
    if len(a.paths) == 1 and pathlib.Path(a.paths[0]).is_dir():
        return main_case(a, ap)
    briefs = [p for p in a.paths if not p.lower().endswith(".json")]
    apis = [p for p in a.paths if p.lower().endswith(".json")]
    if not briefs or len(apis) != 1:
        ap.error("give one or more brief files and exactly one tool API .json file")
    t0 = time.time()
    stems = [pathlib.Path(b).stem for b in briefs]
    name = slug("-".join(stems))
    slot = a.slot or ("rb-" + name)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (ROOT / "traces").mkdir(exist_ok=True)
    trace = Trace(ROOT / "traces" / ("%s-%s.txt" % (stamp, slot)), echo=True)
    trace.start(briefs=[{"file": b, "sha256": sha(b)} for b in briefs], tool_api={"file": apis[0], "sha256": sha(apis[0])},
                slot=slot, commit=git_commit(), builder_identity=identity_hash(), runtime=bundle.runtime_hash(),
                budget_s=BUDGET_S)
    status, result = "FAILED", {}
    try:
        result = build(briefs, apis[0], slot, name, pathlib.Path(a.out), trace, t0, smoke=not a.no_smoke)
        status = "OK" if result.get("self_tests_failed", 0) == 0 else "OK_WITH_TEST_FAILURES"
    except BuildError as e:
        trace.note("build stopped: %s" % e)
    except Exception as e:  # never die silently: the trace says what happened
        trace.note("build crashed: %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        trace.end(status=status, seconds=round(time.time() - t0, 1), **{k: v for k, v in result.items() if k != "policy"})
    return 0 if status.startswith("OK") else 1


def main_case(a, ap):
    """A case folder (sources, service contract, no tool API file): see builder/case/build_case.py."""
    from builder.case import build_case
    if not a.mock_url:
        ap.error("a case folder build needs --mock-url (or FREYA_MOCK_URL)")
    folder = pathlib.Path(a.paths[0]).resolve()
    t0 = time.time()
    name = slug(folder.name)[:40]
    slot = a.slot or ("rb-" + name)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (ROOT / "traces").mkdir(exist_ok=True)
    trace = Trace(ROOT / "traces" / ("%s-%s.txt" % (stamp, slot)), echo=True)
    files = sorted(f for f in folder.rglob("*") if f.is_file() and not f.name.startswith("."))
    trace.start(case_folder=str(folder), files=[{"file": str(f.relative_to(folder)), "sha256": sha(f)} for f in files],
                mock_url=a.mock_url, slot=slot, commit=git_commit(), builder_identity=identity_hash(), budget_s=BUDGET_S)
    status, result = "FAILED", {}
    try:
        result = build_case.build(folder, a.mock_url, slot, name, pathlib.Path(a.out), trace, t0, smoke=not a.no_smoke,
                                  rel=rel, sha=sha)
        status = "OK" if result.get("self_tests_failed", 0) == 0 else "OK_WITH_TEST_FAILURES"
    except build_case.CaseError as e:
        trace.note("build stopped: %s" % e)
    except Exception as e:  # never die silently: the trace says what happened
        trace.note("build crashed: %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        trace.end(status=status, seconds=round(time.time() - t0, 1), **result)
    return 0 if status.startswith("OK") else 1


def left(t0):
    return BUDGET_S - (time.time() - t0)


def build(briefs, api_path, slot, name, out_dir, trace, t0, smoke=True):
    # 1. tool API
    ts = openapi.load(api_path)
    trace.note("tool API read", base_url=ts["base_url"], tools=sorted(ts["tools"]), enums=ts["enums"],
               field_roles={t: {k: v for k, v in m.items() if k != "combined_datetime"} for t, m in ts["api"].items()})
    if ts["api_problems"]:
        raise BuildError("tool API fields could not be mapped: %s" % "; ".join(ts["api_problems"]))
    texts = [pathlib.Path(b).read_text(encoding="utf-8") for b in briefs]
    # 2. policy extraction (Freya's model, bounded)
    deadline = t0 + min(EXTRACT_BUDGET_S, BUDGET_S - 8 * 60)
    policy, report = extract.extract(texts, ts, trace=trace, parallel=4, deadline=deadline)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ("%s.policy.json" % name)).write_text(json.dumps(policy, indent=1, ensure_ascii=False))
    (out_dir / ("%s.answers.json" % name)).write_text(json.dumps(report["answers"], indent=1, ensure_ascii=False))
    trace.note("policy extracted", seconds=round(time.time() - t0, 1), section_problems=report["section_problems"],
               file=rel(out_dir / ("%s.policy.json" % name)))
    # 3. validate, emit, lint
    errs = schema.validate(policy, ts)
    trace.test("policy validates against the tool API", not errs, errors=errs[:20])
    if errs and time.time() < deadline + 4 * 60:
        policy, report = extract.repair(texts, ts, report, errs, trace=trace, deadline=deadline + 4 * 60)
        (out_dir / ("%s.policy.json" % name)).write_text(json.dumps(policy, indent=1, ensure_ascii=False))
        errs = schema.validate(policy, ts)
        trace.test("policy validates after one repair round", not errs, errors=errs[:20], sections=report.get("repaired"))
    if errs:
        raise BuildError("policy invalid: %s" % "; ".join(errs[:5]))
    wf = W.build(policy, ts)
    code_bytes = len(bundle.code(dict(policy, api=policy.get("api") or ts["api"])).encode())
    lint = W.lint(wf)
    fatal = [x for x in lint if not x.startswith("unreachable")]  # an unreachable node is harmless
    trace.test("workflow lint", not fatal, problems=lint[:20], nodes=len(wf["nodes"]), decide_code_bytes=code_bytes)
    if fatal:
        raise BuildError("lint: %s" % "; ".join(fatal[:5]))
    # 4. self-tests on the local stub, customers made up from the policy
    from qa import selftest
    failed = 0
    for res in selftest.run_all(policy, ts, wf):
        trace.test("local walk: " + res["name"], res["ok"], **{k: v for k, v in res.items() if k not in ("name", "ok")})
        failed += 0 if res["ok"] else 1
    # 5. platform dry run, save, publish
    P.freya.validate_workflow(slot + " dry run", wf)
    trace.test("platform dry run (POST /api/v2/workflow?dryRun=true)", True)
    saved = P.save(slot, wf)
    trace.created("workflow saved and published", slot=slot, workflow_id=saved["workflow_id"], agent_id=saved["agent_id"],
                  version=saved.get("version"))
    # 6. chat smoke test, export
    if smoke and left(t0) > SMOKE_MIN_LEFT_S:
        ok, info = chat_smoke(saved["workflow_id"], policy, trace)
        trace.test("chat smoke on the published workflow", ok, **info)
        failed += 0 if ok else 1
    else:
        trace.note("chat smoke skipped", seconds_left=round(left(t0)))
    path = out_dir / ("%s.workflow.json" % name)
    P.freya.export_workflow(saved["workflow_id"], str(path))
    trace.created("exported workflow file", path=rel(path), sha256=sha(path))
    return {"workflow_id": saved["workflow_id"], "agent_id": saved["agent_id"], "version": saved.get("version"),
            "export": rel(path), "self_tests_failed": failed}


def smoke_variables(policy):
    v = {"title": "Mr", "first_name": "Alex", "last_name": "Morgan", "customer_id": "c_selftest_smoke",
         "now": "%sT11:00" % datetime.date.today().isoformat()}
    for n in policy.get("call_variables") or []:
        v.setdefault(n, "Test")
    return v


def chat_smoke(workflow_id, policy, trace):
    """Two chat turns: the opening, then the first decide step (it must run and ask the person question or the
    first security question). No bank customer is touched. The chat route is never retried blindly."""
    info = {}
    t = time.time()
    try:
        r1 = P.freya.api("POST", "/api/v2/chat/message", {"workflowId": workflow_id, "message": "Hello?",
                                                          "customerVariables": smoke_variables(policy)})
    except Exception as e:
        return False, {"error": "first turn: %s" % str(e)[:200]}
    call_id = r1.get("callId")
    info["opening"] = (r1.get("response") or "")[:200]
    info["first_turn_s"] = round(time.time() - t, 1)
    t = time.time()
    try:
        r2 = P.freya.api("POST", "/api/v2/chat/message", {"workflowId": workflow_id, "message": "Yes, speaking.",
                                                          "callId": call_id})
        info["second_reply"] = (r2.get("response") or "")[:200]
    except Exception as e:
        info["second_error"] = str(e)[:200]
    info["second_turn_s"] = round(time.time() - t, 1)
    P.chat_end(call_id)
    code_ok, code_err = None, None
    try:
        for e in P.events(P.get_call(call_id)):
            ev = e.get("event") or {}
            if ev.get("function") == "code_exec" and ev.get("event") == "function_call_complete":
                code_ok = (ev.get("result") or {}).get("status") == "success" if code_ok is not False else False
            if ev.get("function") == "code_exec" and ev.get("event") == "function_call_error":
                code_ok, code_err = False, str(ev.get("error"))[:200]
    except Exception as e:
        info["call_log_error"] = str(e)[:120]
    info.update(call_id=call_id, decide_step_ok=code_ok, decide_error=code_err)
    ok = bool(info.get("opening")) and bool(info.get("second_reply")) and code_ok is True
    return ok, info


if __name__ == "__main__":
    sys.exit(main())
