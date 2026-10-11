"""Emit the workflow for a case: one conversation step that holds the extracted instructions and the bank's services
as tools (the start-of-call service is its first tool call), and one closing step per way the call ends.

All case knowledge comes in through `spec` (extracted instructions, endings, wiring) and `contract` (parsed services).
"""
import json
import re

from builder.case import sources as S

PLATFORM_RULES = """HOW YOU WORK ON THIS PLATFORM
- Everything you write is spoken aloud to the caller. Plain sentences only: no lists, no markdown, no asterisks, no field names, no JSON.
- Each service in your instructions is a tool: the service `a.b.c` is the tool `a_b_c`. When an instruction says to use a service, CALL that tool; saying that you did is not enough.
- Call one tool at a time. After every tool result either speak to the caller or call the next tool. Never end a turn with nothing.
- Never call a service that changes or sends something before the caller has given the consent your instructions require for it. Call it once only.
- Every amount, date, name and digit you say must come from a tool result of this call. Copy values exactly. If a value did not come from a service, do not say it.
- You are not shown the tool results of earlier turns again. SERVICE RESULTS SO FAR in your current task is your memory of them: the latest answer of every service in this call. Take every value you say or send from there or from a tool result of this turn.
- Send identifiers to tools exactly as a service returned them, character for character, including any mask characters. Never send a value you cannot find in SERVICE RESULTS SO FAR or in what the caller just chose.
- A tool result that says the request failed, or has no success status, is a service failure unless your instructions name that result as a normal case.
- A tool result may hold "assistant_notes": facts worked out for you from the result (for example how each date relates to now). Use them; never read them out as they are.
- A service that changes or sends something is refused by the platform when the caller has not spoken since the last service result, or when the caller's last answer was not a clear yes. A tool error that starts with NOT ALLOWED YET is that refusal, not a service failure: do what it says, and do not tell the caller about it.
- Do not stop after giving information when your instructions name a next step (a service to call, a question, an offer): do that next step in the same turn. When an offer or question depends on a service lookup, call that service before you speak, then give the information and the offer in one message.
- A caller's message can reach you cut off in the middle. If a message is incomplete, or you are not sure what the caller wants, ask. Never end the call on an incomplete or unclear message, and never because the caller turned down one of several things you offered: ask what they would like instead.
- If an instruction depends on a fact that no service gives you, assume the ordinary case and let the service decide. Do not hold back an offer or a step because of such a fact.
- When a result note gives an amount as whole part and hundredths, say exactly those two numbers.
- To end the call, CALL the closing tool (its name starts with transition_to_) whose situation matches. The platform then says that tool's closing sentence itself: do not say that sentence yourself. Anything else you must say first goes in the same message as the tool call.
- Never end the call any other way, and never go on talking after a closing sentence."""

POST_HOOK = '''import datetime, re
try:
    if isinstance(result, dict):
        result.pop('header', None)
        body = result.get('data')
        now_raw = str(vars.get(NOW_VAR) or '')
        today = None
        try:
            today = datetime.date.fromisoformat(now_raw[:10])
        except Exception:
            today = None
        notes = dict()
        amounts = dict()
        def walk(o, path):
            if isinstance(o, dict):
                for k in o:
                    walk(o[k], (path + '.' + k) if path else k)
            elif isinstance(o, list):
                for i, x in enumerate(o):
                    walk(x, path + '[' + str(i) + ']')
            elif isinstance(o, float) and not isinstance(o, bool):
                try:
                    if abs(o - round(o)) > 0.0000001:
                        t = ('%.2f' % abs(o)).split('.')
                        amounts[path] = ('minus ' if o < 0 else '') + t[0] + '.' + t[1] + ' exactly: whole part ' + t[0] + ', then ' + str(int(t[1])) + ' hundredths (two decimal places)'
                except Exception:
                    pass
            elif isinstance(o, str) and today is not None:
                m = re.match(r'^(\\d{2})\\.(\\d{2})\\.(\\d{4})$', o)
                if m:
                    try:
                        d = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                        n = (d - today).days
                        notes[path] = o + (' is today' if n == 0 else (' is in %d day(s), not reached yet' % n if n > 0 else ' was %d day(s) ago, already passed' % (-n)))
                    except Exception:
                        pass
        if isinstance(body, dict):
            inner = body.get('result')
            if isinstance(inner, dict):
                inner.pop('details', None)
            walk(body, '')
            if notes or amounts:
                body['assistant_notes'] = dict(now=now_raw, dates=notes, amounts_with_decimals=amounts)
            try:
                lines = []
                def flat(o, path):
                    if isinstance(o, dict):
                        for k in o:
                            flat(o[k], (path + '.' + k) if path else k)
                    elif isinstance(o, list):
                        if not o:
                            lines.append(path + ' = (empty list)')
                        for i, x in enumerate(o):
                            flat(x, path + '[' + str(i + 1) + ']')
                    elif o is not None:
                        lines.append(path + ' = ' + str(o) + ((' (' + notes[path].split(' ', 1)[1] + ')') if path in notes else '') + ((' (' + amounts[path] + ')') if path in amounts else ''))
                for k in body:
                    if k not in ('assistant_notes', 'what_to_do_next', 'result'):
                        flat(body[k], k)
                sent = [str(k)[len(TOOL) + 6:] + '=' + str(vars.get(k)) for k in sorted(vars) if str(k).startswith(TOOL + '_args.')]
                mem = 'answered' + ((' for ' + ', '.join(sent)) if sent else '') + ':' + chr(10) + '  ' + (chr(10) + '  ').join(lines)
                vars['mem_' + TOOL] = mem[:3500].replace('{' + '{', '{ {').replace('}' + '}', '} }')
            except Exception:
                pass
            body['what_to_do_next'] = 'Before you speak: if what your instructions make you say after this (a question, an offer) depends on another service, call that service now and speak only after its result. Otherwise speak to the caller now and include the next question or offer your instructions name. Do not stay silent.'
except Exception:
    pass
'''

PRE_HOOK = '''turn = ''
try:
    turn = str(vars.get(NODE + '.total_turns') or '')
    last = str(vars.get('last_service_turn') or '')
except Exception:
    turn, last = '', ''
if GUARD and turn and last == turn:
    raise Exception('NOT ALLOWED YET. This is not a service failure. This service changes or sends something and the caller has not answered since the last service result. Now tell the caller exactly what will be done, with the values from the last result, and ask for a clear yes. Call this tool again only after the caller has clearly said yes.')
if GUARD and YES:
    said = ''
    try:
        conv = vars.get('system.conversation')
        if isinstance(conv, list):
            for m in conv:
                if isinstance(m, dict) and m.get('role') == 'user':
                    said = str(m.get('content') or '')
        import re
        said = ' ' + re.sub(r'[^\\w]+', ' ', said.lower().replace(chr(775), '')).strip() + ' '
    except Exception:
        said = ''
    if said.strip() and (any((' ' + h + ' ') in said for h in HEDGE) or not any((' ' + y + ' ') in said for y in YES)):
        raise Exception('NOT ALLOWED YET. This is not a service failure. The last thing the caller said was not a clear yes. Ask the same confirmation question once more, short and plain, and wait for the answer. Call this tool again only after the caller has clearly said yes.')
try:
    vars['last_service_turn'] = turn
except Exception:
    pass
try:
    if FROM_CALL:
        import json
        b = config.get('body')
        if isinstance(b, str):
            b = json.loads(b)
        def fill(o):
            if isinstance(o, dict):
                for k in list(o):
                    if isinstance(o[k], (dict, list)):
                        fill(o[k])
                    elif k in FROM_CALL and vars.get(FROM_CALL[k]) is not None:
                        o[k] = str(vars.get(FROM_CALL[k]))
            elif isinstance(o, list):
                for x in o:
                    fill(x)
        if isinstance(b, dict):
            fill(b)
            config['body'] = json.dumps(b)
except Exception:
    pass
'''

def _const(name, value):
    return "%s = %s\n" % (name, json.dumps(value))


def _clean(value):
    """Example placeholders such as "<caller's number>" are not values."""
    if isinstance(value, str) and re.match(r"^<.*>$", value.strip()):
        return ""
    return value


def _jtype(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def body_schema(example, field_sources, call_vars, service):
    """JSON-schema body for one service from its example request. Returns (schema, model_filled_field_names)."""
    filled, from_call = [], {}

    def build(node, in_data):
        props, required = {}, []
        for key, value in node.items():
            if isinstance(value, dict):
                props[key] = build(value, key == "data" or in_data)[0]
                continue
            src = field_sources.get(key) if in_data else None
            src = src if isinstance(src, dict) else {}
            kind = str(src.get("source") or ("conversation" if in_data else "constant"))
            if kind == "call_variable" and str(src.get("value")) in call_vars:
                props[key] = {"type": "string", "default": "{{%s}}" % src["value"]}
                from_call[key] = str(src["value"])
            elif kind == "constant":
                fixed = src.get("value") if src.get("value") not in (None, "") else _clean(value)
                props[key] = {"type": _jtype(fixed), "default": fixed}
            else:
                note = str(src.get("note") or "").strip()
                desc = ("%s. Copy the real value of this call from SERVICE RESULTS SO FAR or from what the caller chose; never a sample value."
                        % (note.rstrip(".") if note else "Value for %s" % key))
                props[key] = {"type": _jtype(value), "description": desc, "default": "{{%s}}" % key}
                required.append(key)
                filled.append(key)
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        return schema, required

    return build(example, False)[0], filled, from_call


def words(items):
    """Normalised words and phrases for the consent check: lower case, letters and digits only."""
    out = []
    for x in items if isinstance(items, list) else []:
        w = re.sub(r"[^\w]+", " ", str(x).lower().replace(chr(775), "")).strip()
        if w and w not in out:
            out.append(w)
    return out


def api_tool(contract, service, mock_url, field_sources, call_vars, now_var, timeout_ms, description=None, guard=False,
             node="assistant", consent=None):
    body, filled, from_call = body_schema(service["request_example"], field_sources, call_vars, service["name"])
    url = mock_url.rstrip("/") + "/" + contract["base_path"].strip("/") + "/" + service["name"]
    name = S.tool_name(service["name"])
    desc = description or ("The service `%s`. %s CALL it when your instructions say to use `%s`." % (service["name"], service["summary"], service["name"]))
    tool = {"type": "function", "config": {"timeoutMs": timeout_ms, "maxRetries": 0},
            "function": {"name": name, "handler": "__function__:api_call", "description": desc,
                         "parameters": {"type": "object", "properties": {
                             "url": {"type": "string", "default": url},
                             "method": {"type": "string", "default": contract["method"]},
                             "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"},
                                                                          "Accept": {"type": "string", "default": "application/json"}}},
                             "body": body}}},
            "pre_process_code": (_const("NODE", node) + "GUARD = %s\n" % bool(guard)
                                 + "YES = %r\nHEDGE = %r\n" % (words((consent or {}).get("clear_yes")) if guard else [],
                                                               words((consent or {}).get("not_clear")) if guard else [])
                                 + "FROM_CALL = dict(%s)\n" % ", ".join(
                "%s=%s" % (k, json.dumps(v)) for k, v in sorted(from_call.items())) + PRE_HOOK),
            "post_process_code": _const("NOW_VAR", now_var) + _const("TOOL", name) + POST_HOOK}
    return tool, filled


def end_node(key, function_name, sentence):
    params = {"message_mode": {"type": "string", "default": "custom" if sentence else "none"}}
    if sentence:
        params["spoken_message"] = {"type": "string", "default": sentence}
    return {"name": key, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": function_name, "handler": "__function__:end_call",
                                                          "parameters": {"type": "object", "properties": params}}}}


def snake(text, fallback="end"):
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s[:40] or fallback


def now_variable(call_variables):
    """The call variable that carries the moment of the call: the one whose example reads as an ISO date-time."""
    for v in call_variables:
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", str(v.get("example") or "")):
            return v["name"]
    for v in call_variables:
        if v["name"].lower() in ("now", "call_time", "current_time"):
            return v["name"]
    return "now"


def build(spec, contract, mock_url, slow_service_ms=30000):
    wire = spec.get("wiring") or {}
    call_variables = [v for v in (wire.get("call_variables") or []) if isinstance(v, dict) and re.match(r"^[A-Za-z_]\w*$", str(v.get("name") or ""))]
    call_vars = [v["name"] for v in call_variables]
    now_var = now_variable(call_variables)
    fields = wire.get("fields") if isinstance(wire.get("fields"), dict) else {}
    services = {s["name"]: s for s in contract["services"]}
    language = str(wire.get("language") or "the caller's language")

    # the start-of-call service: named only if the call variables and fixed values are all it needs
    start = services.get(str(wire.get("start_service") or ""))
    if start and body_schema(start["request_example"], fields.get(start["name"]) or {}, call_vars, start["name"])[1]:
        start = None

    flags = wire.get("services") if isinstance(wire.get("services"), dict) else {}
    tools, tool_lines, guarded = [], [], []
    for s in contract["services"]:
        flag = flags.get(s["name"]) if isinstance(flags.get(s["name"]), dict) else {}
        guard = flag.get("changes_something") in (True, "true", "True")
        tool, filled = api_tool(contract, s, mock_url, fields.get(s["name"]) or {}, call_vars, now_var, slow_service_ms, guard=guard,
                                consent=wire.get("consent") if isinstance(wire.get("consent"), dict) else None)
        tools.append(tool)
        if guard:
            guarded.append(s["name"])
        tool_lines.append("- `%s` -> tool %s%s%s" % (s["name"], tool["function"]["name"], (" (you fill: %s)" % ", ".join(filled)) if filled else "",
                                                     " [changes or sends something: needs the caller's consent first]" if guard else ""))

    nodes, end_transitions, seen = {}, [], {}
    for e in spec.get("endings") or []:
        dest = snake(e["destination"])
        seen[dest] = seen.get(dest, 0) + 1
        key = "end_%s_%d" % (dest, seen[dest])
        nodes[key] = end_node(key, dest, e["last_sentence"])
        said = ('The platform then says: "%s"' % e["last_sentence"]) if e["last_sentence"] else "No closing sentence is said for you."
        desc = "End of call, destination %s. CALL it when: %s. %s" % (e["destination"], e["when"] or "this ending applies", said)
        end_transitions.append({"target_node": key, "description": desc, "is_tool_call": True,
                                "condition": {"operator": "matches_intent", "description": desc}})

    sections = spec.get("sections") or {}
    titles = {"start": "THE CALL AND THE ITEM IT IS ABOUT", "reading": "GIVING THE INFORMATION", "actions": "OFFERS AND ACTIONS",
              "failures": "TRIES, FAILURES, TRANSFERS AND ENDINGS", "security": "SECURITY AND CONDUCT"}
    parts = ["You are the phone voice assistant described by the instructions below. You are in a live call. Speak %s with the caller, in short natural sentences." % language,
             PLATFORM_RULES]
    if sections.get("assume"):
        parts.append("WHAT NO SERVICE TELLS YOU (these lines override any condition below that needs such a fact)\n"
                     + "\n".join("- " + line for line in sections["assume"]))
    if sections.get("outline"):
        parts.append("THE NORMAL COURSE OF A CALL (details follow below)\n" + "\n".join(sections["outline"]))
    for key in ("start", "reading", "actions", "failures", "security"):
        if sections.get(key):
            parts.append(titles[key] + "\n" + "\n".join("- " + line for line in sections[key]))
    parts.append("YOUR TOOLS\n" + "\n".join(tool_lines))
    system_prompt = "\n\n".join(parts)

    var_lines = "\n".join("- %s (%s): {{%s}}" % (v["name"], str(v.get("meaning") or "")[:120], v["name"]) for v in call_variables)
    task = "CALL VARIABLES OF THIS CALL\n%s\n\n" % var_lines
    mem_lines = "\n".join("- `%s` (tool %s): {{mem_%s}}" % (x["name"], S.tool_name(x["name"]), S.tool_name(x["name"])) for x in contract["services"])
    task += "SERVICE RESULTS SO FAR IN THIS CALL (latest answer of each service)\n%s\n\n" % mem_lines
    if start:
        # The model makes this call itself: an engine-run call in front of the conversation took the whole chat turn
        # down (HTTP 502) when the service answered 404, which is an ordinary answer for some callers.
        task += ("START OF THIS CALL\nIf `%s` above still says it was not called: before you say anything, CALL the tool %s. "
                 "It needs no value from the caller. What it returns decides your first sentence.\n\n"
                 % (start["name"], S.tool_name(start["name"])))
    task += ("Follow your instructions from the first step that is still open. If the next step is a service call, CALL the tool now; "
             "otherwise speak to the caller. Use the moment of the call given above for every decision about dates, never today's real date.")

    nodes["assistant"] = {"name": "assistant", "node_type": "conversation", "task_message": task, "tools": tools,
                          "max_node_turns": 80, "max_turn_transition": next(iter([t["target_node"] for t in end_transitions]), "assistant"),
                          "transitions": end_transitions}
    # no test_variables: an example value in the workflow was seen to reach service calls in place of the call's own value
    wf = {"system_prompt": system_prompt, "global_nodes": {}, "nodes": nodes}
    examples = {v["name"]: str(v.get("example") or "") for v in call_variables if str(v.get("example") or "")}
    boot = "".join("vars[%s] = 'not called yet in this call'\n" % json.dumps("mem_" + S.tool_name(x["name"])) for x in contract["services"])
    nodes["boot"] = {"name": "boot", "node_type": "code", "passthrough": True, "passthrough_default_transition": "assistant",
                     "on_enter": {"type": "silent"}, "pre_actions": [_code(boot)],
                     "transitions": [{"target_node": "assistant", "description": "always", "condition": {"operator": "always"}}]}
    wf["initial_node"] = "boot"
    return wf, {"start_service": start["name"] if start else "", "tools": [t["function"]["name"] for t in tools],
                "endings": len(end_transitions), "consent_guard_on": guarded, "clear_yes": words((wire.get("consent") or {}).get("clear_yes") if isinstance(wire.get("consent"), dict) else []),
                "not_clear": words((wire.get("consent") or {}).get("not_clear") if isinstance(wire.get("consent"), dict) else []), "system_prompt_chars": len(system_prompt), "now_variable": now_var,
                "call_variables": call_vars, "example_variables": examples}


def _code(code):
    assert "{{" not in code and "}}" not in code, "code must not contain template braces"
    return {"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                             "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code},
                                                                                             "timeout_ms": {"type": "number", "default": 10000}}}}}


def lint(wf):
    errs = []
    nodes = wf["nodes"]
    if wf.get("initial_node") not in nodes:
        errs.append("initial node missing")
    for name, n in nodes.items():
        for t in n.get("transitions") or []:
            if t["target_node"] not in nodes:
                errs.append("%s: transition to unknown node %s" % (name, t["target_node"]))
        if n.get("passthrough") and (not n.get("transitions") or n["transitions"][-1]["condition"].get("operator") != "always"):
            errs.append("%s: passthrough node must end with an always transition" % name)
        if n["node_type"] == "conversation" and not n.get("tools"):
            errs.append("%s: no tools" % name)
    if not any(n["node_type"] == "end_call" for n in nodes.values()):
        errs.append("no end_call node")
    return errs
