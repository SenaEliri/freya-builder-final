"""L14: verify platform semantics before relying on them. Builds workflow slot rb-probe and talks to it.

    python3 -m qa.probe_platform            # needs env.sh sourced

Checks, read from the call's event log (results/probe-*.json):
  1. extraction: does a string field copy the LAST customer message verbatim (utterance)?
  2. one code node per turn: decide sees extracted values, can clear them, sets route/say
  3. conversation node re-entered through decide speaks its TTS line again
  4. api_request (pre_actions) routes at once on <node>_response.data.*
  5. node-level response_mapping of a list (products) -> what does code see?
  6. passthrough conversation nodes chained in one turn: are both TTS lines emitted?
  7. end_call spoken_message with a variable + end_of_call close_call fed by variables
  8. how the mock stores reason "" for outcome promise (ledger)
  9. any non-English filler lines
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from builder import platform as P  # noqa: E402

BANK = "https://freya-bank-mock.freyavoice.workers.dev/v1"


def api_fn(name, path, body_props, required):
    props = {"url": {"type": "string", "default": BANK + path},
             "method": {"type": "string", "default": "POST"},
             "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
             "body": {"type": "object", "properties": body_props, "required": required}}
    return {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 0},
            "function": {"name": name, "handler": "__function__:api_call", "description": name,
                         "parameters": {"type": "object", "properties": props}}}


EXTRACT = [
    {"name": "utterance", "type": "string", "min_confidence": 0.05,
     "description": "The customer's LAST message, copied word for word. Do not use earlier messages."},
    {"name": "reply", "type": "string", "enum_values": ["yes", "no", "ack", "none"], "min_confidence": 0.2,
     "description": "yes/no if the LAST customer message answers a yes-no question; ack for okay/mm/fine; none otherwise."},
    {"name": "date_phrase", "type": "string", "min_confidence": 0.05,
     "description": "The date expression in the LAST customer message, copied verbatim (e.g. 'next Friday the 23rd'). Empty if none."},
]

DECIDE = r'''
import json
try:
    t = int(vars.get('probe_turn') or 0) + 1
    vars['probe_turn'] = str(t)
    seen = 'utt=[%s] reply=[%s] date=[%s]' % (vars.get('utterance'), vars.get('reply'), vars.get('date_phrase'))
    keys = sorted(k for k in vars.keys())
    vars['dbg_keys'] = ' '.join(keys)[:3000]
    vars['utterance'] = ''
    vars['reply'] = ''
    vars['date_phrase'] = ''
    if t == 1:
        vars['v_field'] = 'date_of_birth'
        vars['v_answer'] = '1988-03-14'
        vars['route'] = 'verify'
    elif t == 2:
        vars['v_field'] = 'phone_last4'
        vars['v_answer'] = '4471'
        vars['route'] = 'verify'
    elif t == 3:
        vars['route'] = 'chain'
    else:
        vars['final_outcome'] = 'promise'
        vars['final_reason'] = ''
        vars['route'] = 'end'
    vars['say'] = 'Turn %d. %s' % (t, seen)
except Exception as e:
    vars['say'] = 'decide error ' + str(e)[:100]
    vars['route'] = 'say'
'''

DUMP = r'''
try:
    pr = vars.get('products_raw')
    flat = [k for k in vars.keys() if 'account' in k or 'product' in k]
    vars['say'] = 'products_raw type=%s value=%s | keys=%s' % (type(pr).__name__, str(pr)[:400], ' '.join(sorted(flat))[:600])
except Exception as e:
    vars['say'] = 'dump error ' + str(e)[:100]
'''


def code_node(name, code, target):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": target,
            "on_enter": {"type": "silent"},
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                             "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code},
                                                                              "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": [{"target_node": target, "description": "always", "condition": {"operator": "always"}}]}


def tts_node(name, text, passthrough_to=None):
    n = {"name": name, "node_type": "conversation", "on_enter": {"type": "tts", "text": text},
         "task_message": "Do not say anything. No tool call is allowed in this turn.",
         "extraction_schema": EXTRACT, "max_node_turns": 60,
         "transitions": [{"target_node": "decide", "description": "always", "condition": {"operator": "always"}}]}
    if passthrough_to:
        n["passthrough"] = True
        n["passthrough_default_transition"] = passthrough_to
        n["transitions"] = [{"target_node": passthrough_to, "description": "always", "condition": {"operator": "always"}}]
    return n


def eq_true(var):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": "true"},
                                          {"variable": var, "operator": "equals", "operand": "True"}]}


def route(value, target):
    return {"target_node": target, "description": "route " + value,
            "condition": {"logic": "or", "conditions": [{"variable": "route", "operator": "equals", "operand": value}]}}


def workflow():
    decide = code_node("decide", DECIDE, "say")
    decide["transitions"] = [
        {"target_node": "err", "description": "decide failed",
         "condition": {"logic": "or", "conditions": [{"variable": "decide_response.status", "operator": "not_equals", "operand": "success"}]}},
        route("verify", "verify"), route("chain", "p1"), route("end", "end_node"),
        {"target_node": "say", "description": "always", "condition": {"operator": "always"}}]
    verify = {"name": "verify", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "say_bad",
              "on_enter": {"type": "silent"},
              "pre_actions": [api_fn("verify_identity", "/verify_identity",
                                     {"customer_id": {"type": "string", "default": "{{customer_id}}"},
                                      "field": {"type": "string", "default": "{{v_field}}"},
                                      "answer": {"type": "string", "default": "{{v_answer}}"}}, ["customer_id", "field", "answer"])],
              "transitions": [{"target_node": "account", "description": "all verified", "condition": eq_true("verify_response.data.all_verified")},
                              {"target_node": "say_ok", "description": "verified", "condition": eq_true("verify_response.data.verified")},
                              {"target_node": "say_bad", "description": "always", "condition": {"operator": "always"}}]}
    account = {"name": "account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "dump",
               "on_enter": {"type": "silent"},
               "pre_actions": [api_fn("get_account", "/get_account", {"customer_id": {"type": "string", "default": "{{customer_id}}"}}, ["customer_id"])],
               "response_mapping": [{"path": "data.products", "variable": "products_raw"}],
               "transitions": [{"target_node": "dump", "description": "always", "condition": {"operator": "always"}}]}
    end_node = {"name": "end_node", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                "transitions": [],
                "terminal": {"type": "function", "function": {"name": "probe_end", "handler": "__function__:end_call",
                             "parameters": {"type": "object", "properties": {
                                 "message_mode": {"type": "string", "default": "custom"},
                                 "spoken_message": {"type": "string", "default": "Probe goodbye. {{say}}"}}}}}}
    close = api_fn("close_call", "/close_call", {"customer_id": {"type": "string", "default": "{{customer_id}}"},
                                                  "outcome": {"type": "string", "default": "{{final_outcome}}"},
                                                  "reason": {"type": "string", "default": "{{final_reason}}"}}, ["customer_id", "outcome"])
    close["config"]["alwaysRunsAt"] = ["end_of_call"]
    return {
        "initial_node": "open",
        "system_prompt": "You are a test agent. Speak English only.",
        "nodes": {
            "open": dict(tts_node("open", "Hello, this is a probe. This call is recorded. Am I speaking with {{title}} {{last_name}}?"),
                         task_message="Say exactly this sentence and nothing else: Hello, this is a probe. This call is recorded. Am I speaking with {{title}} {{last_name}}?"),
            "decide": decide, "verify": verify, "account": account,
            "dump": code_node("dump", DUMP, "say"),
            "say_ok": tts_node("say_ok", "Verified one. wrong_left={{verify_response.data.wrong_answers_left}}"),
            "say_bad": tts_node("say_bad", "Not verified. ok={{verify_response.data.ok}} left={{verify_response.data.wrong_answers_left}}"),
            "p1": tts_node("p1", "Chain line one.", passthrough_to="p2"),
            "p2": tts_node("p2", "Chain line two.", passthrough_to="say"),
            "say": tts_node("say", "{{say}}"),
            "err": tts_node("err", "Code step failed."),
            "end_node": end_node,
        },
        "global_nodes": {},
        "tools": [close],
    }


def main():
    wf = workflow()
    v = P.freya.validate_workflow("rb-probe dry", wf)
    print("dry run ok")
    saved = P.save("rb-probe", wf)
    print("saved", {k: saved[k] for k in ("workflow_id", "version")})
    variables = P.practice_session("PUB-01")
    turns = ["Hello?", "Yes, speaking.", "Fine.", "Next Friday the 23rd works for me.", "Okay, goodbye."]
    call_id, transcript = None, []
    for msg in turns:
        t0 = time.time()
        r = P.chat(saved["workflow_id"], msg, variables=variables, call_id=call_id)
        call_id = r.get("callId") or call_id
        transcript.append({"user": msg, "agent": r.get("response"), "secs": round(time.time() - t0, 1),
                           "ended": r.get("endedByAgent"), "warning": r.get("warning")})
        print(json.dumps(transcript[-1], ensure_ascii=False))
        if r.get("endedByAgent"):
            break
    print("chat end:", P.chat_end(call_id))
    time.sleep(8)
    call = P.get_call(call_id)
    ev = P.events(call)
    led = P.ledger(variables["customer_id"])
    out = pathlib.Path(__file__).resolve().parent.parent / "results" / ("probe-%s.json" % time.strftime("%H%M%S"))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"saved": saved, "transcript": transcript, "events": ev, "ledger": led,
                               "endedReason": call.get("endedReason")}, indent=1, ensure_ascii=False))
    print("ledger:", json.dumps(led)[:800])
    print("endedReason:", call.get("endedReason"), "| events file:", out)


if __name__ == "__main__":
    main()
