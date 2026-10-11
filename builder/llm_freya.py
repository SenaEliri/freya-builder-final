"""Build-time model = Freya's model, reached through the documented chat API on a helper workflow.

The helper is a one-node workflow in slot `rb-llm`. Each `ask()` opens a fresh chat call, sends the
context in parts (the chat route takes at most 10,000 characters per message) and then the question.
Every wait is bounded; a 504 from the chat route is not retried blindly (the turn may have run): the
call's event log is polled for the assistant's reply instead. Every call is recorded in the trace.
"""
import json
import re
import time

from builder import platform as P

SLOT = "rb-llm"
MAX_MSG = 9000

SYSTEM = ("You are a precise information-extraction engine used by a software build step. You are NOT on a phone call. "
          "Read every message carefully. When a message says CONTEXT, reply with exactly: OK. When a message asks a "
          "QUESTION, reply with one JSON object and nothing else: no prose, no markdown fences. Use only facts from the "
          "context; never invent values. Write in English.")


def helper_workflow():
    return {"initial_node": "llm", "system_prompt": SYSTEM, "global_nodes": {},
            "nodes": {"llm": {"name": "llm", "node_type": "conversation",
                              "task_message": "Follow the latest message exactly. CONTEXT -> reply OK. QUESTION -> reply with one JSON object only.",
                              "max_node_turns": 80, "transitions": [],
                              "truncation_strategy": "keep_all"}}}


_helper = {}
_lock = __import__("threading").Lock()


def ensure_helper(trace=None):
    with _lock:
        return _ensure_helper(trace)


def _ensure_helper(trace=None):
    if _helper.get("id"):
        return _helper["id"]
    saved = P.save(SLOT, helper_workflow())
    wid = saved["workflow_id"]
    # longer answers and steadier output for extraction (helper only; the phone agent is untouched)
    try:
        w = P.get_workflow(wid)["workflow"]
        ac = w.get("agent_config") or {}
        llm = ac.get("llmConfig") or {}
        if llm.get("maxTokens") != 4000 or llm.get("temperature") != 0:
            llm["maxTokens"] = 4000
            llm["temperature"] = 0
            ac["llmConfig"] = llm
            P.freya.api("PUT", "/api/v2/workflow/%s" % wid, {"workflow": dict(w, agent_config=ac)})
            vs = P.freya.api("GET", "/api/v2/versions/workflow/%s" % wid, workspaceId=P.freya.workspace_id())["versions"]
            newest = max(vs, key=lambda v: v["versionNumber"])
            if not newest.get("isPublished"):
                P.freya.api("POST", "/api/v2/versions/workflow/%s/publish" % wid, {"versionId": newest["id"]})
    except Exception as e:  # the helper still works with defaults
        if trace:
            trace.note("helper agent_config tuning skipped: %s" % str(e)[:120])
    _helper["id"] = wid
    if trace:
        trace.created("helper workflow", slot=SLOT, workflow_id=wid)
    return wid


def _post(body, timeout_s):
    t0 = time.time()
    try:
        r = P.freya.api("POST", "/api/v2/chat/message", body)
        return r, time.time() - t0, None
    except Exception as e:  # HTTP errors and socket timeouts alike: the caller decides, nothing escapes
        return None, time.time() - t0, str(e)[:200]


def _poll_reply(call_id, after_text, deadline):
    """After a 504: find the assistant message that follows our last user message in the call log."""
    while time.time() < deadline:
        time.sleep(4)
        try:
            call = P.get_call(call_id)
        except Exception:
            continue
        msgs = [m for m in call.get("messages") or [] if m.get("role") in ("user", "assistant")]
        idx = None
        for i, m in enumerate(msgs):
            if m.get("role") == "user" and (m.get("message") or "").strip() == after_text.strip():
                idx = i
        if idx is not None:
            for m in msgs[idx + 1:]:
                if m.get("role") == "assistant" and (m.get("message") or "").strip():
                    return m["message"]
    return None


def chunks(text, n=MAX_MSG):
    out, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) + 1 > n and cur:
            out.append(cur)
            cur = ""
        while len(para) > n:
            out.append(para[:n])
            para = para[n:]
        cur += para + "\n"
    if cur.strip():
        out.append(cur)
    return out


def ask(context, question, purpose, trace=None, timeout_s=240, per_turn_s=120):
    """One extraction question over a context. Returns (parsed_json or None, raw_text)."""
    wid = ensure_helper(trace)
    t_start = time.time()
    deadline = t_start + timeout_s
    call_id = None
    parts = chunks(context)
    msgs = ["CONTEXT part %d of %d:\n%s" % (i + 1, len(parts), p) for i, p in enumerate(parts)]
    msgs.append("QUESTION:\n" + question)
    raw = None
    err = None
    for m in msgs:
        if time.time() > deadline:
            err = "overall timeout"
            break
        body = {"workflowId": wid, "message": m[:10000]}
        if call_id:
            body["callId"] = call_id
        else:
            body["customerVariables"] = {}
        r, secs, e = _post(body, per_turn_s)
        if r is not None:
            call_id = r.get("callId") or call_id
            raw = r.get("response") or ""
            continue
        if call_id and "504" in (e or ""):
            raw = _poll_reply(call_id, m[:10000], min(deadline, time.time() + per_turn_s))
            if raw is not None:
                continue
        err = e or "no reply"
        break
    if call_id:
        try:
            P.chat_end(call_id)
        except Exception:
            pass
    parsed = parse_json(raw) if raw and not err else None
    if trace:
        trace.model_call(model="freya:experimental-5 (chat helper %s)" % SLOT, purpose=purpose,
                         seconds=round(time.time() - t_start, 1), ok=parsed is not None,
                         error=err or (None if parsed is not None else "reply was not JSON: %r" % (raw or "")[:80]))
    return parsed, raw


def parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None
