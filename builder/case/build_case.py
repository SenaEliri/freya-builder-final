"""One command for a case folder: sources + service contract -> a phone agent on Freya whose tools call your mock.

    python3 builder/build.py <case_folder> --mock-url https://<your-mock>.workers.dev [--slot rb-x] [--out submission/final]

Steps (each one in the trace):
  1. read the text sources (dated by file name; of two editions of one document the newest is used)
  2. find the service contract in them and parse each service's request example
  3. Freya's model: rules per source part, then final instructions per topic (later sources win), the ways the
     call ends, and where each request field gets its value
  4. emit the workflow (one conversation step with the services as tools, one closing step per ending); lint
  5. check the mock answers on every service path; platform dry run; save and publish
  6. chat smoke test on the published workflow; export
"""
import json
import pathlib
import time
import urllib.error
import urllib.request

from builder import platform as P
from builder.case import emit, extract
from builder.case import sources as S

EXTRACT_BUDGET_S = 16 * 60


class CaseError(Exception):
    pass


def probe_mock(contract, mock_url):
    """Every service path must exist on the mock: an empty request has to come back as JSON with a result envelope
    or a client error, never a transport failure or an HTML page."""
    out = {}
    for s in contract["services"]:
        url = mock_url.rstrip("/") + "/" + contract["base_path"].strip("/") + "/" + s["name"]
        req = urllib.request.Request(url, data=b"{}", method=contract["method"],
                                     headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (build-the-builder)"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                code, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read()
        except Exception as e:
            out[s["name"]] = "unreachable: %s" % str(e)[:80]
            continue
        try:
            json.loads(body)
            out[s["name"]] = "ok (HTTP %d, JSON)" % code if code != 404 or b"result" in body else "HTTP 404"
        except Exception:
            out[s["name"]] = "HTTP %d, not JSON" % code
    return out


def has_none(o):
    if o is None:
        return True
    if isinstance(o, dict):
        return any(has_none(v) for v in o.values())
    if isinstance(o, list):
        return any(has_none(v) for v in o)
    return False


def chat_smoke(workflow_id, wf, summary, trace):
    """Open one chat call with the example call variables: the start service must have run and the agent must speak."""
    info = {}
    t = time.time()
    try:
        r1 = P.freya.api("POST", "/api/v2/chat/message", {"workflowId": workflow_id, "message": "Alo?",
                                                          "customerVariables": summary.get("example_variables") or {}})
    except Exception as e:
        return False, {"error": "first turn: %s" % str(e)[:200]}
    call_id = r1.get("callId")
    info.update(call_id=call_id, first_reply=(r1.get("response") or "")[:300], first_turn_s=round(time.time() - t, 1))
    P.chat_end(call_id)
    calls, errors = [], []
    try:
        for e in P.events(P.get_call(call_id)):
            ev = e.get("event") or {}
            if ev.get("event") == "function_call_start":
                calls.append(str((ev.get("args") or {}).get("url") or ev.get("function"))[-40:])
            if ev.get("event") == "function_call_error":
                errors.append(str(ev.get("error"))[:160])
    except Exception as e:
        info["call_log_error"] = str(e)[:120]
    info.update(service_calls=calls, service_errors=errors)
    ok = bool(info["first_reply"]) and (not summary["start_service"] or any(summary["start_service"] in c for c in calls))
    return ok, info


def build(folder, mock_url, slot, name, out_dir, trace, t0, smoke=True, rel=str, sha=None):
    folder = pathlib.Path(folder)
    # 1. sources
    docs, skipped = S.read_sources(folder)
    if not docs:
        raise CaseError("no text sources in %s" % folder)
    trace.note("sources read", files=[{"file": d["path"], "dated": d["date"] or None, "chars": len(d["text"])} for d in docs], not_used=skipped)
    # 2. service contract
    contract = S.find_contract(docs)
    if not contract:
        raise CaseError("no service contract found in the sources (headings with a service name and a JSON request example)")
    trace.note("service contract parsed", file=contract["path"], base_address=contract["base_url"], method=contract["method"],
               services=[{"name": s["name"], "request_example": s["request_example"]} for s in contract["services"]])
    mock = probe_mock(contract, mock_url)
    bad = {k: v for k, v in mock.items() if not v.startswith("ok")}
    trace.test("mock answers on every service path", not bad, mock_url=mock_url, services=mock)
    if bad:
        raise CaseError("mock does not serve: %s" % ", ".join(sorted(bad)))
    # 3. instructions from the sources (Freya's model, bounded)
    spec = extract.extract(docs, contract, trace=trace, parallel=4, deadline=t0 + EXTRACT_BUDGET_S)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ("%s.spec.json" % name)).write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    empty = [k for k, v in spec["sections"].items() if not v and k != "outline"]
    trace.test("instructions extracted for every topic", not empty and bool(spec["endings"]), problems=spec["problems"][:20],
               lines={k: len(v) for k, v in spec["sections"].items()}, endings=len(spec["endings"]), file=rel(out_dir / ("%s.spec.json" % name)))
    if len(empty) > 2 or not spec["endings"]:
        raise CaseError("extraction incomplete: %s" % "; ".join(spec["problems"][:5]))
    # 4. workflow
    wf, summary = emit.build(spec, contract, mock_url)
    problems = emit.lint(wf) + (["null value in workflow"] if has_none(wf) else [])
    trace.test("workflow lint", not problems, problems=problems[:20], nodes=len(wf["nodes"]), **summary)
    if problems:
        raise CaseError("lint: %s" % "; ".join(problems[:5]))
    # 5. platform
    P.freya.validate_workflow(slot + " dry run", wf)
    trace.test("platform dry run (POST /api/v2/workflow?dryRun=true)", True)
    saved = P.save(slot, wf)
    trace.created("workflow saved and published", slot=slot, workflow_id=saved["workflow_id"], agent_id=saved["agent_id"],
                  version=saved.get("version"))
    failed = 0
    # 6. smoke, export
    if smoke:
        ok, info = chat_smoke(saved["workflow_id"], wf, summary, trace)
        trace.test("chat smoke on the published workflow", ok, **info)
        failed += 0 if ok else 1
    path = out_dir / ("%s.workflow.json" % name)
    P.freya.export_workflow(saved["workflow_id"], str(path))
    trace.created("exported workflow file", path=rel(path), sha256=sha(path) if sha else None)
    return {"workflow_id": saved["workflow_id"], "agent_id": saved["agent_id"], "version": saved.get("version"),
            "export": rel(path), "self_tests_failed": failed}
