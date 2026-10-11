"""Policy + tool spec -> Freya workflow JSON. Deterministic: same inputs, same workflow.

Graph (one code step per customer turn, L11):
  open --(customer)--> decide --route--> say | verify chain | write chains | transfer | callback | end_*
  every waiting conversation node: same extraction schema (L8), single transition -> decide
  bank calls are engine-run api_request nodes (pre_actions route at once, L14); their outcomes pick
  result lines that decide precomputed, so no second code step is needed in the same turn.
  close_call is an end_of_call lifecycle tool fed by final_outcome/final_reason, with no hook (L6, L11).
"""
import json
import re

from builder.emit import bundle

EXTRACT_MIN_CONF = 0.05


def san(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "other"


def tpl(s):
    """Policy lines use {title}; Freya fixed lines need {{title}}."""
    return re.sub(r"\{(\w+)\}", lambda m: "{{" + m.group(1) + "}}", s)


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def when(var, op, operand, target, desc=None):
    c = {"variable": var, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return {"target_node": target, "description": desc or ("%s %s %s" % (var, op, operand)),
            "condition": {"logic": "or", "conditions": [c]}}


def when_true(var, target, desc=None):
    return {"target_node": target, "description": desc or (var + " is true"),
            "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": "true"},
                                                        {"variable": var, "operator": "equals", "operand": "True"}]}}


def extraction_schema(policy):
    it = policy.get("interrupts") or {}
    topics = [
        ("robot", "asks whether they are talking to a robot, a machine or an AI"),
        ("scam", "asks whether this call is a scam or fraud, or doubts the call is really from the bank"),
        ("who_is_calling", "asks who is calling"),
        ("what_about", "asks what the call is about or why the bank is calling, instead of answering"),
        ("why_needed", "asks why the agent needs the information it just asked for"),
        ("hardship", it.get("hardship") or "mentions illness, a death in the family or losing their job"),
        ("dispute", it.get("dispute") or "says the debt is not theirs or they never had this product"),
        ("already_paid", it.get("already_paid") or "says they already paid this amount"),
        ("restructuring", it.get("restructuring") or "asks for a new payment plan or lower instalments"),
        ("human", it.get("human") or "asks to speak to a human or a person"),
        ("discount", "asks for a discount, a waiver or to pay less in total (this is NOT a request for a new payment plan)"),
        ("how_much", "asks how much they owe or asks for the amount again"),
        ("change_promise", "asks to change or cancel a promise that was already recorded"),
        ("other_question", "asks any other question"),
    ]
    topic_desc = ("What the customer's LAST message is about, if it is one of these; otherwise none. "
                  "Pick the FIRST that applies in this order: " +
                  "; ".join("%s = %s" % (k, v) for k, v in topics) +
                  ". Not hardship: being busy, traffic, a wedding or other small talk. Not restructuring: asking for a discount.")
    intents = [
        ("someone_else", "the speaker is not the customer (a relative, a colleague, someone else who answered)"),
        ("wrong_number", "the number does not belong to the customer or they do not know the customer"),
        ("deceased", "says the customer has died"),
        ("propose", "proposes or names their own payment day and/or amount"),
        ("too_much", "says the full amount is too much or they cannot pay all of it"),
        ("vague_time", "gives only a vague time for paying, like next week, end of the month, when my salary comes"),
        ("refuse_talk", "refuses to answer the questions or says they do not want to talk"),
        ("refuse_pay", "flatly refuses to pay, with no day and no amount"),
        ("accept_transfer", "agrees to be transferred or connected to someone"),
        ("decline", "declines an offer to be transferred or connected"),
        ("wants_human", "insists on speaking to a human"),
        ("goodbye", "says goodbye or wants to end the call now"),
    ]
    intent_desc = ("The main intent of the customer's LAST message, if one of these applies; otherwise none: " +
                   "; ".join("%s = %s" % (k, v) for k, v in intents) + ".")
    return [
        {"name": "utterance", "type": "string", "min_confidence": EXTRACT_MIN_CONF,
         "description": "The customer's LAST message copied exactly, word for word, with numbers and dates as they were said. Use only the last message."},
        {"name": "reply", "type": "string", "enum_values": ["yes", "no", "ack", "none"], "min_confidence": 0.2,
         "description": ("How the customer's LAST message answers the agent's LAST question: yes = agrees, confirms or "
                         "says it is them (yes, correct, that's me, speaking, I confirm); no = says no or declines; "
                         "ack = only acknowledges without answering (okay, mm, alright, one moment); none = anything else.")},
        {"name": "intent", "type": "string", "enum_values": [k for k, _ in intents] + ["none"], "min_confidence": 0.2,
         "description": intent_desc},
        {"name": "topic", "type": "string", "enum_values": [k for k, _ in topics] + ["none"], "min_confidence": 0.2,
         "description": topic_desc},
        {"name": "pay_date", "type": "string", "min_confidence": EXTRACT_MIN_CONF,
         "description": ("Only the words of the customer's LAST message that say WHEN they will pay (for example "
                         "'on Friday', 'next Monday the 26th', 'tomorrow', 'when my salary comes'), copied exactly. "
                         "Empty if the last message names no payment day. Ignore dates that are not about paying "
                         "(birthdays, weddings, other events).")},
        {"name": "pay_amount", "type": "string", "min_confidence": EXTRACT_MIN_CONF,
         "description": ("Only the words of the customer's LAST message that say HOW MUCH they will pay (for example "
                         "'200 dollars', 'the minimum', 'four hundred and fifty'), copied exactly. Empty if none.")},
    ]


def system_prompt(policy):
    return ("You are %s's digital assistant on a phone call. Speak English only, in every message, including "
            "short fillers; never use any other language. Say only the exact sentence you are given for this step. "
            "Never say that anything is recorded, saved or booked unless the sentence you are given says so." % policy.get("bank", "the bank"))


def conv(name, line_var=None, text=None, extraction=None, to="decide", passthrough=False, task=None):
    t = text if text is not None else "{{%s}}" % line_var
    n = {"name": name, "node_type": "conversation", "on_enter": {"type": "tts", "text": t},
         "task_message": task or ("Say exactly this and nothing else: " + t + " No tool call is allowed in this turn."),
         "max_node_turns": 60, "transitions": [always(to)]}
    if extraction is not None:
        n["extraction_schema"] = extraction
    if passthrough:
        n["passthrough"] = True
        n["passthrough_default_transition"] = to
        n["disable_inactivity_monitor"] = True
    return n


def api_node(name, tool, body_defaults, transitions, response_mapping=None, default_to=None):
    props = {"url": {"type": "string", "default": tool["url"]},
             "method": {"type": "string", "default": tool.get("method", "POST")},
             "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
             "body": {"type": "object", "properties": {}, "required": [f for f in tool.get("required", []) if f in body_defaults]}}
    for f, val in body_defaults.items():
        spec = tool["fields"].get(f, {"type": "string"})
        leaf = {"type": spec.get("type", "string"), "default": val}
        if spec.get("description"):
            leaf["description"] = spec["description"][:300]
        props["body"]["properties"][f] = leaf
    n = {"name": name, "node_type": "api_request", "passthrough": True,
         "passthrough_default_transition": default_to or transitions[-1]["target_node"],
         "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
         "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 0},
                          "function": {"name": tool["name"], "handler": "__function__:api_call",
                                       "description": tool.get("summary", tool["name"]),
                                       "parameters": {"type": "object", "properties": props}}}],
         "transitions": transitions}
    if response_mapping:
        n["response_mapping"] = response_mapping
    return n


def end_node(name):
    """Hang up silently: the farewell was already spoken by the bye_ node, close_call was the last tool."""
    return {"name": name, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "transitions": [],
            "terminal": {"type": "function", "function": {"name": name, "handler": "__function__:end_call",
                         "parameters": {"type": "object", "properties": {
                             "message_mode": {"type": "string", "default": "none"}}}}}}


def router(name, transitions):
    """A silent passthrough step that only routes (no model call, no code)."""
    return {"name": name, "node_type": "conversation", "passthrough": True, "on_enter": {"type": "silent"},
            "task_message": "Say nothing. No tool call is allowed in this turn.", "disable_inactivity_monitor": True,
            "passthrough_default_transition": transitions[-1]["target_node"], "transitions": transitions}


def literal_ending(nodes, name, policy, situation, text, close, A=None):
    """A fixed ending for a failure path: speak `text`, close_call with the situation's literal outcome and reason
    (retried once), hang up. Needs no code step and no route variable."""
    o, r = policy["outcomes"].get(situation) or policy["outcomes"]["unclear"]
    body = A.body("close_call", cid=1, outcome=o, **({"reason": r} if r else {}))
    nodes[name] = conv(name, text=text, passthrough=True, to=name + "_close")
    nodes[name + "_close"] = api_node(name + "_close", close, body,
                                      [when_true(A.ok(name + "_close", "close_call"), name + "_end"), always(name + "_close_r")])
    nodes[name + "_close_r"] = api_node(name + "_close_r", close, body, [always(name + "_end")])
    nodes[name + "_end"] = end_node(name + "_end")


def end_route(outcome, reason):
    return "end_" + san(outcome) + ("_r" if reason else "")


OPTIONAL_REQ = {("close_call", "reason"), ("schedule_callback", "time")}


class Api(object):
    """Field names of the bank's tool API by role (builder/policy/roles.py)."""

    def __init__(self, policy, toolspec):
        self.map = policy.get("api") or toolspec.get("api") or {}
        names = [n for n in policy.get("call_variables") or [] if re.search(r"(customer|client).*id|^id$", n)]
        self.cid = "{{%s}}" % (names[0] if names else "customer_id")

    def rq(self, tool, role):
        m = (self.map.get(tool) or {}).get("req")
        if m is None:
            return role
        if role in m:
            return m[role]
        return None if (tool, role) in OPTIONAL_REQ else role

    def rs(self, tool, role):
        return ((self.map.get(tool) or {}).get("resp") or {}).get(role, role)

    def body(self, tool, **roles):
        out = {}
        for role, val in roles.items():
            name = self.rq(tool, "customer_id" if role == "cid" else role)
            if name is None:
                continue
            out[name] = self.cid if role == "cid" else val
        if tool == "schedule_callback" and (self.map.get(tool) or {}).get("combined_datetime"):
            out = {self.rq(tool, "customer_id"): self.cid, self.rq(tool, "date"): "{{cb_date}}T{{cb_time}}"}
        return out

    def ok(self, node, tool):
        return "%s_response.data.%s" % (node, self.rs(tool, "ok"))


def build(policy, toolspec):
    T = toolspec["tools"]
    if not policy.get("api") and toolspec.get("api"):
        policy = dict(policy, api=toolspec["api"])  # the decide step reads tool responses through the same mapping
    A = Api(policy, toolspec)
    ex = extraction_schema(policy)
    variants = {}
    for sit, (o, r) in sorted(policy["outcomes"].items()):
        variants[end_route(o, r)] = (o, bool(r))
    by_final = [when("final_route", "equals", rn, "bye" + rn[3:]) for rn in variants] + [always("bye_default")]
    close_by_final = [when("final_route", "equals", rn, "close" + rn[3:]) for rn in variants] + [always("close_default")]
    nodes = {}
    lines = policy["lines"]
    close = T["close_call"]
    opening = tpl(lines["opening"])
    nodes["open"] = conv("open", text=opening, extraction=ex,
                         task="Say exactly this and nothing else: " + opening + " No tool call is allowed in this turn.")
    # decide: the one code step per customer turn
    route_tr = [when("decide_response.status", "not_equals", "success", "end_tech", "decide failed: honest technical ending"),
                when("route", "equals", "verify", "verify"),
                when("route", "equals", "transfer", "xfer"),
                when("route", "equals", "callback", "cb"),
                when("route", "equals", "write_p1", "wp1c"),
                when("route", "equals", "write_n1", "wn1c"),
                when("route", "equals", "end_tech", "end_tech")]
    for rname in variants:
        route_tr.append(when("route", "equals", rname, "bye" + rname[3:]))
    route_tr.append(always("say"))
    code = bundle.code(policy)
    nodes["decide"] = {"name": "decide", "node_type": "code", "passthrough": True, "passthrough_default_transition": "say",
                       "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                       "pre_actions": [{"type": "function", "function": {
                           "name": "code_exec", "handler": "__function__:code_exec",
                           "parameters": {"type": "object", "properties": {
                               "code": {"type": "string", "default": code},
                               "timeout_ms": {"type": "number", "default": 15000}}}}}],
                       "transitions": route_tr}
    nodes["say"] = conv("say", "say", extraction=ex)
    # identity check: engine-run call, result picks a precomputed line
    swap = (policy.get("identity") or {}).get("swap_hint")
    vd = lambda role: "verify_response.data." + A.rs("verify_identity", role)  # noqa: E731
    vt = [when("verify_response.status", "not_equals", "success", "v_tech", "the bank call failed"),
          when_true(vd("all_verified"), "v_done", "all questions passed"),
          when_true(vd("verified"), "v_next", "this answer passed")]
    if swap:
        vt.append(when(vd("hint"), "equals", swap, "v_swapped", "bank hints day and month swapped"))
    vt += [{"target_node": "v_unreadable", "description": "answer not readable",
            "condition": {"logic": "or", "conditions": [{"variable": vd("ok"), "operator": "equals", "operand": "false"},
                                                        {"variable": vd("ok"), "operator": "equals", "operand": "False"}]}},
           when(vd("wrong_answers_left"), "less_than", 1, "v_failed", "no wrong answers left: identity failed"),
           always("v_wrong")]
    nodes["verify"] = api_node("verify", T["verify_identity"],
                               A.body("verify_identity", cid=1, field="{{v_field}}", answer="{{v_answer}}"), vt)
    for nm in ("v_next", "v_wrong", "v_unreadable", "v_tech") + (("v_swapped",) if swap else ()):
        nodes[nm] = conv(nm, "say_" + nm, extraction=ex)
    nodes["v_done"] = conv("v_done", "say_v_done", extraction=ex, to="account")
    pmap = [{"path": "data." + A.rs("get_account", "products"), "variable": "account_products"}]
    nodes["account"] = api_node("account", T["get_account"], A.body("get_account", cid=1),
                                [when("account_response.status", "equals", "success", "decide"), always("account_r")],
                                response_mapping=pmap)
    nodes["account_r"] = api_node("account_r", T["get_account"], A.body("get_account", cid=1), [always("decide")],
                                  response_mapping=pmap)
    # write chains: c = clean (no failure yet), d = dirty (a write failed twice). Both end at w_end, which needs no
    # customer turn: any create_promise ok -> the promise ending; promises tried but none ok -> the precomputed
    # all-failed ending (farewell_af, final_route/final_reason); notes only -> final_route.
    promise_bye = "bye" + end_route(*policy["outcomes"]["promise"])[3:]
    ok_conds = []
    for k in (1, 2, 3):
        for nm in ("wp%dc" % k, "wp%dcr" % k) + (("wp%dd" % k, "wp%ddr" % k) if k > 1 else ()):
            for val in ("true", "True"):
                ok_conds.append({"variable": A.ok(nm, "create_promise"), "operator": "equals", "operand": val})

    def after_promise(k, v):
        nxt = []
        if k < 3:
            nxt.append(when("wp%d_on" % (k + 1), "equals", "yes", "wp%d%s" % (k + 1, v)))
        nxt.append(when("wn1_on", "equals", "yes", "wn1%s" % v))
        return nxt + [always("w_end")]

    def after_note(k, v):
        nxt = []
        if k < 3:
            nxt.append(when("wn%d_on" % (k + 1), "equals", "yes", "wn%d%s" % (k + 1, v)))
        return nxt + [always("w_end")]

    def silent_router(name, transitions):
        nx = conv(name, text="", passthrough=True)
        nx["on_enter"] = {"type": "silent"}
        nx["task_message"] = "Say nothing. No tool call is allowed in this turn."
        nx["transitions"] = transitions
        nx["passthrough_default_transition"] = transitions[-1]["target_node"]
        return nx

    for v in ("c", "d"):
        for k in (1, 2, 3):
            nbody = A.body("add_note", cid=1, product_id="{{wn%d_pid}}" % k, reason="{{wn%d_reason}}" % k)
            nodes["wn%d%s" % (k, v)] = api_node("wn%d%s" % (k, v), T["add_note"], nbody,
                                                [when_true(A.ok("wn%d%s" % (k, v), "add_note"), "wn%d%s_next" % (k, v)),
                                                 always("wn%d%sr" % (k, v))])
            nodes["wn%d%sr" % (k, v)] = api_node("wn%d%sr" % (k, v), T["add_note"], nbody, [always("wn%d%s_next" % (k, v))])
            nodes["wn%d%s_next" % (k, v)] = silent_router("wn%d%s_next" % (k, v), after_note(k, v))
            if v == "d" and k == 1:
                continue  # the dirty chain starts after product 1 failed
            body = A.body("create_promise", cid=1, product_id="{{wp%d_pid}}" % k, amount="{{wp%d_amount}}" % k,
                          date="{{wp%d_date}}" % k)
            nodes["wp%d%s" % (k, v)] = api_node("wp%d%s" % (k, v), T["create_promise"], body,
                                                [when_true(A.ok("wp%d%s" % (k, v), "create_promise"), "wp%d%s_ok" % (k, v)),
                                                 always("wp%d%sr" % (k, v))])
            nodes["wp%d%sr" % (k, v)] = api_node("wp%d%sr" % (k, v), T["create_promise"], body,
                                                 [when_true(A.ok("wp%d%sr" % (k, v), "create_promise"), "wp%d%s_ok" % (k, v)),
                                                  always("wp%d_fail" % k)])
            ok = conv("wp%d%s_ok" % (k, v), "say_wp%d_ok" % k, passthrough=True, to="__set_below__")
            ok["transitions"] = after_promise(k, v)
            ok["passthrough_default_transition"] = ok["transitions"][-1]["target_node"]
            nodes["wp%d%s_ok" % (k, v)] = ok
    for k in (1, 2, 3):
        f = conv("wp%d_fail" % k, "say_wp%d_fail" % k, passthrough=True)
        f["transitions"] = [when("wf_on", "equals", "yes", "wf%d" % k)] + after_promise(k, "d")
        f["passthrough_default_transition"] = f["transitions"][-1]["target_node"]
        nodes["wp%d_fail" % k] = f
        fbody = A.body("add_note", cid=1, product_id="{{wp%d_pid}}" % k, reason="{{wf_reason}}")
        nodes["wf%d" % k] = api_node("wf%d" % k, T["add_note"], fbody,
                                     [when_true(A.ok("wf%d" % k, "add_note"), "wf%d_next" % k), always("wf%dr" % k)])
        nodes["wf%dr" % k] = api_node("wf%dr" % k, T["add_note"], fbody, [always("wf%d_next" % k)])
        nodes["wf%d_next" % k] = silent_router("wf%d_next" % k, after_promise(k, "d"))
    nodes["w_end"] = silent_router("w_end", [{"target_node": promise_bye, "description": "a create_promise succeeded",
                                              "condition": {"logic": "or", "conditions": ok_conds}},
                                             when("wp1_on", "equals", "yes", "af_bye", "every create_promise failed twice")]
                                   + by_final)
    af = conv("af_bye", "farewell_af", passthrough=True, to="close_default")
    af["transitions"] = close_by_final
    af["passthrough_default_transition"] = "close_default"
    nodes["af_bye"] = af
    # transfer and callback
    xbody = A.body("transfer_to_agent", cid=1, queue="{{xfer_queue}}")
    nodes["xfer"] = api_node("xfer", T["transfer_to_agent"], xbody,
                             [when_true(A.ok("xfer", "transfer_to_agent"), "xfer_done"), always("xfer_r")])
    nodes["xfer_r"] = api_node("xfer_r", T["transfer_to_agent"], xbody,
                               [when_true(A.ok("xfer_r", "transfer_to_agent"), "xfer_done"), always("xfer_fail")])
    literal_ending(nodes, "xfer_fail", policy, "service_error", lines["tech_problem"] + " " + lines["goodbye"], close, A)
    nodes["xfer_done"] = router("xfer_done", by_final)
    cbody = A.body("schedule_callback", cid=1, date="{{cb_date}}", time="{{cb_time}}")
    nodes["cb"] = api_node("cb", T["schedule_callback"], cbody,
                           [when_true(A.ok("cb", "schedule_callback"), "cb_done"), always("cb_r")])
    nodes["cb_r"] = api_node("cb_r", T["schedule_callback"], cbody,
                             [when_true(A.ok("cb_r", "schedule_callback"), "cb_done"), always("cb_fail")])
    literal_ending(nodes, "cb_fail", policy, "no_callback", lines["tech_problem"] + " " + lines["goodbye"], close, A)
    nodes["cb_done"] = router("cb_done", by_final)
    nodes["v_failed"] = router("v_failed", by_final)
    # endings (L2, L6): fixed farewell first (never waits), then close_call as an engine-run call, then hang up.
    # close_call must omit `reason` for outcomes without one: the mock rejects reason "" (verified 10 Oct).
    close = T["close_call"]
    for rn, (o, has_r) in variants.items():
        nodes["bye" + rn[3:]] = conv("bye" + rn[3:], "farewell", passthrough=True, to="close" + rn[3:])
        body = A.body("close_call", cid=1, outcome=o, **({"reason": "{{final_reason}}"} if has_r else {}))
        # close_call is retried once when it fails (HTTP 500: nothing was recorded, the call may be repeated)
        nodes["close" + rn[3:]] = api_node("close" + rn[3:], close, body,
                                           [when_true(A.ok("close" + rn[3:], "close_call"), rn), always("close%s_r" % rn[3:])])
        nodes["close%s_r" % rn[3:]] = api_node("close%s_r" % rn[3:], close, body, [always(rn)])
        nodes[rn] = end_node(rn)
    uo, ur = policy["outcomes"]["unclear"]
    dbody = A.body("close_call", cid=1, outcome=uo, **({"reason": ur} if ur else {}))
    nodes["bye_default"] = conv("bye_default", "farewell", passthrough=True, to="close_default")
    nodes["close_default"] = api_node("close_default", close, dbody,
                                      [when_true(A.ok("close_default", "close_call"), "end_default"), always("close_default_r")])
    nodes["close_default_r"] = api_node("close_default_r", close, dbody, [always("end_default")])
    nodes["end_default"] = end_node("end_default")
    nodes["end_tech"] = conv("end_tech", text=lines["tech_problem"] + " " + lines["goodbye"], passthrough=True, to="close_default")
    nodes["end_tech"]["transitions"] = close_by_final
    nodes["end_tech"]["passthrough_default_transition"] = "close_default"
    wf = {"initial_node": "open", "system_prompt": system_prompt(policy), "nodes": nodes, "global_nodes": {}}
    for n in nodes.values():
        if n.get("passthrough_default_transition") == "__set_below__":
            n["passthrough_default_transition"] = n["transitions"][-1]["target_node"]
    return wf


def lint(wf):
    """Structural checks that the platform does not report (L14/L15)."""
    errs = []
    nodes = wf["nodes"]
    for name, n in nodes.items():
        if n.get("name") != name:
            errs.append("%s: name differs from key" % name)
        nt = n.get("node_type")
        if nt != "conversation" and n.get("tools"):
            errs.append("%s: tools on a %s node would be stripped" % (name, nt))
        if nt == "conversation" and n.get("pre_actions"):
            errs.append("%s: pre_actions on a conversation node would be stripped" % name)
        for t in n.get("transitions") or []:
            if t["target_node"] not in nodes and t["target_node"] != "__previous__":
                errs.append("%s: transition to unknown node %s" % (name, t["target_node"]))
        if n.get("passthrough"):
            tr = n.get("transitions") or []
            if not tr or tr[-1]["condition"].get("operator") != "always":
                errs.append("%s: passthrough node must end with an always transition" % name)
        if nt == "conversation" and not n.get("passthrough"):
            tr = n.get("transitions") or []
            if not tr:
                errs.append("%s: waiting conversation node without exit" % name)
        if nt == "end_call" and n.get("transitions"):
            errs.append("%s: end node with transitions" % name)
    s = json.dumps(wf)
    if ": null" in s:
        errs.append("workflow contains null values")
    code = nodes["decide"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    if "{{" in code or "}}" in code:
        errs.append("decide code contains double braces")
    # reachability from the initial node
    seen, todo = set(), [wf["initial_node"]]
    while todo:
        x = todo.pop()
        if x in seen or x not in nodes:
            continue
        seen.add(x)
        todo += [t["target_node"] for t in nodes[x].get("transitions") or []]
    unreachable = sorted(set(nodes) - seen)
    if unreachable:
        errs.append("unreachable nodes: %s" % ", ".join(unreachable))
    return errs
