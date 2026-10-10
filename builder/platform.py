"""Thin, bounded wrappers around the kit's freya.py and the practice bank.

Everything here uses documented operations only (kit docs/api.md + docs.freyavoice.ai):
workflow create/update/publish, chat message/end, call details, practice sessions and ledgers.
Every network call has a timeout. Nothing here prints secrets.
"""
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya  # noqa: E402  (kit client, unmodified)

if os.environ.get("FREYA_WORKSPACE_ID"):
    freya._ws = os.environ["FREYA_WORKSPACE_ID"]  # skip the extra /workspaces lookup the kit client makes

BANK_HOST = os.environ.get("FREYA_BANK_HOST", "https://freya-bank-mock.freyavoice.workers.dev")
STATE_FILE = ROOT / ".freya-agents.json"
PROTECTED_PREFIXES = ("rb-",)  # this rebuild only ever writes slots with these prefixes


def _check_slot(slot):
    if not slot.startswith(PROTECTED_PREFIXES):
        raise ValueError("refusing to write slot %r: rebuild slots must start with %s" % (slot, PROTECTED_PREFIXES))


def save(slot, workflow, state_file=STATE_FILE):
    """Create the slot's workflow once, update it afterwards; always leave the newest version published.

    The kit's create path does not set the event model in agent_config, which blocks chat turns, so a
    freshly created workflow is updated once right away (update_workflow fixes the model and publishes).
    Returns {workflow_id, agent_id, version}.
    """
    _check_slot(slot)
    f = pathlib.Path(state_file)
    state = json.loads(f.read_text()) if f.exists() else {}
    if slot not in state:
        state[slot] = freya.create_workflow("%s %s" % (slot, time.strftime("%m%d-%H%M%S")), workflow)
        f.write_text(json.dumps(state, indent=1))
    state[slot]["version"] = freya.update_workflow(state[slot]["workflow_id"], workflow)
    f.write_text(json.dumps(state, indent=1))
    return state[slot]


def get_workflow(workflow_id):
    return freya.api("GET", "/api/v2/workflow/%s" % workflow_id, workspaceId=freya.workspace_id())["workflow"]


def chat(workflow_id, message, variables=None, call_id=None, retries=1, timeout_s=90):
    """One chat turn. Returns the API result dict (response, callId, messageId, ...)."""
    body = {"workflowId": workflow_id, "message": message}
    if call_id:
        body["callId"] = call_id
    if variables is not None and not call_id:
        body["customerVariables"] = variables
    last = None
    for attempt in range(retries + 1):
        try:
            return freya.api("POST", "/api/v2/chat/message", body)
        except RuntimeError as e:  # 504 on long turns etc.
            last = e
            time.sleep(2)
    raise last


def chat_end(call_id):
    try:
        return freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
    except RuntimeError as e:
        return {"error": str(e)[:300]}


def get_call(call_id):
    return freya.api("GET", "/api/v2/call/%s" % call_id, workspaceId=freya.workspace_id())["call"]


def events(call):
    """Decode a call's messages into a flat list of dicts: role, text or event payload, node, t."""
    out = []
    for m in call.get("messages") or []:
        row = {"role": m.get("role"), "node": m.get("nodeId"), "t": m.get("secondsFromStart")}
        if m.get("role") == "system":
            try:
                row["event"] = json.loads(m.get("message") or "{}")
            except Exception:
                row["event"] = {"raw": m.get("message")}
        else:
            row["text"] = m.get("message")
        out.append(row)
    return out


def _bank(path, body=None, timeout_s=20):
    h = {"user-agent": "freya-bank-scorer/0.1", "content-type": "application/json",
         "x-team-key": os.environ["FREYA_BANK_TEAM_KEY"]}
    req = urllib.request.Request(BANK_HOST + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=h, method="POST" if body is not None else "GET")
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout_s))
    except urllib.error.HTTPError as e:
        return json.load(e)


def practice_session(case_id):
    """Open a fresh practice customer for one of PUB-01..PUB-13; returns its call variables."""
    return _bank("/v1/practice/sessions", {"case": case_id})["variables"]


def ledger(customer_id):
    return _bank("/v1/practice/ledger/" + customer_id)
