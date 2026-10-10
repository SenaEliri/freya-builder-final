"""Which standard modules can a code node import, and does a compressed snippet run? (needed for L16, code size)

    python3 -m qa.probe_modules        # one chat on slot rb-probe-min; needs env.sh sourced
"""
import base64
import json
import pathlib
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from builder import platform as P  # noqa: E402

INNER = "vars['inner'] = 'decompressed-ok:' + str(sum(range(10)))\n"
BLOB = base64.b64encode(zlib.compress(INNER.encode(), 9)).decode()
CODE = ("res = []\n"
        "for m in ('zlib', 'base64', 'binascii', 'lzma', 'bz2', 'gzip', 'math', 'hashlib'):\n"
        "    try:\n"
        "        __import__(m)\n"
        "        res.append(m + ':ok')\n"
        "    except Exception as e:\n"
        "        res.append(m + ':no')\n"
        "try:\n"
        "    import zlib, base64\n"
        "    exec(zlib.decompress(base64.b64decode('%s')).decode(), {'vars': vars})\n"
        "except Exception as e:\n"
        "    vars['inner'] = 'exec failed: ' + str(e)[:80]\n"
        "vars['mods'] = ' '.join(res) + ' ' + str(vars.get('inner'))\n") % BLOB


def wf():
    return {"initial_node": "open", "system_prompt": "Test workflow. Say only what you are told.", "global_nodes": {},
            "nodes": {
                "open": {"name": "open", "node_type": "conversation", "on_enter": {"type": "tts", "text": "Ready."},
                         "task_message": "Say exactly: Ready.", "max_node_turns": 5,
                         "transitions": [{"target_node": "m", "description": "always", "condition": {"operator": "always"}}]},
                "m": {"name": "m", "node_type": "code", "passthrough": True, "passthrough_default_transition": "say",
                      "on_enter": {"type": "silent"},
                      "pre_actions": [{"type": "function", "function": {
                          "name": "code_exec", "handler": "__function__:code_exec",
                          "parameters": {"type": "object", "properties": {
                              "code": {"type": "string", "default": CODE},
                              "timeout_ms": {"type": "number", "default": 15000}}}}}],
                      "transitions": [{"target_node": "say", "description": "always", "condition": {"operator": "always"}}]},
                "say": {"name": "say", "node_type": "conversation", "on_enter": {"type": "tts", "text": "{{mods}}"},
                        "task_message": "Say exactly: {{mods}}", "max_node_turns": 5, "transitions": []}}}


def main():
    saved = P.save("rb-probe-min", wf())
    wid = saved["workflow_id"]
    r1 = P.freya.api("POST", "/api/v2/chat/message", {"workflowId": wid, "message": "Hello?", "customerVariables": {}})
    cid = r1.get("callId")
    r2 = P.freya.api("POST", "/api/v2/chat/message", {"workflowId": wid, "message": "go", "callId": cid})
    print("reply:", r2.get("response"))
    try:
        P.chat_end(cid)
    except Exception:
        pass
    call = P.get_call(cid)
    for e in P.events(call):
        ev = e.get("event") or {}
        if ev.get("function") == "code_exec" and ev.get("event") in ("function_call_complete", "function_call_error"):
            print(json.dumps(ev)[:400])


if __name__ == "__main__":
    main()
