"""Local walk: execute a generated workflow offline against a stub of the mock bank.

It mimics the documented engine semantics (kit docs) closely enough to test routing, the decide code
and the ledger before spending a live simulation:
  - conversation nodes speak on_enter TTS (with {{var}} substitution) and wait for the customer
  - extraction values per customer turn are scripted (the test gives them), like Freya's extractor would
  - code nodes exec the bundled decide code with a `vars` dict
  - api_request nodes call the bank stub; results are flattened into <node>_response.* (booleans as
    lower-case strings) plus counters and node-level response_mapping
  - passthrough nodes route at once; end_call speaks spoken_message and fires end_of_call close_call
"""
import copy
import datetime
import json
import re

# ---------------------------------------------------------------- bank stub


class Bank(object):
    def __init__(self, case, faults=None):
        self.case = case
        self.ident = dict(case.get("identity") or {})
        self.products = []
        for i, p in enumerate(case.get("products") or []):
            q = dict(p)
            q["product_id"] = "p%d" % (i + 1)
            self.products.append(q)
        self.faults = dict((f["tool"], f["fail_first_n"]) for f in (faults if faults is not None else case.get("faults") or []))
        self.calls_by_tool = {}
        self.ledger = {"outcome": None, "reason": None, "promises": [], "notes": [], "callbacks": [], "transfers": [], "calls": []}
        self.wrong = 0
        self.passed = set()
        self.closed = False

    def call(self, tool, body):
        n = self.calls_by_tool.get(tool, 0) + 1
        self.calls_by_tool[tool] = n
        if tool in self.faults and n <= self.faults[tool]:
            self.ledger["calls"].append({"tool": tool, "args": body, "result": {"http": 500}})
            return 500, None
        if self.closed:
            r = {"ok": False, "error": "call already closed"}
        else:
            r = getattr(self, "t_" + tool)(body)
        self.ledger["calls"].append({"tool": tool, "args": body, "result": r})
        return 200, r

    def t_verify_identity(self, b):
        if self.wrong >= 3:
            return {"ok": False, "error": "identity check ended"}
        field, ans = b.get("field"), str(b.get("answer") or "")
        true = str(self.ident.get(field) or "")
        if field == "date_of_birth":
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", ans):
                return {"ok": False, "error": "answer is not a date"}
            y, m, d = ans.split("-")
            if ans != true and "%s-%s-%s" % (y, d, m) == true:
                return {"ok": True, "verified": False, "hint": "day_month_swapped", "wrong_answers_left": 3 - self.wrong,
                        "all_verified": False}
        if ans == true:
            self.passed.add(field)
            return {"ok": True, "verified": True, "wrong_answers_left": 3 - self.wrong,
                    "all_verified": len(self.passed) >= len(self.ident)}
        self.wrong += 1
        return {"ok": True, "verified": False, "wrong_answers_left": 3 - self.wrong, "all_verified": False}

    def verified(self):
        return len(self.passed) >= len(self.ident)

    def t_get_account(self, b):
        if not self.verified():
            return {"ok": False, "error": "identity not verified"}
        return {"ok": True, "products": copy.deepcopy(self.products)}

    def t_create_promise(self, b):
        if not self.verified():
            return {"ok": False, "error": "identity not verified"}
        pid = b.get("product_id")
        if pid not in [p["product_id"] for p in self.products]:
            return {"ok": False, "error": "unknown product_id"}
        if any(p["product_id"] == pid for p in self.ledger["promises"]):
            return {"ok": False, "error": "promise already recorded for this product"}
        self.ledger["promises"].append({"product_id": pid, "amount": float(b.get("amount")), "date": b.get("date")})
        return {"ok": True, "promise_id": "pr_%d" % len(self.ledger["promises"])}

    def t_add_note(self, b):
        self.ledger["notes"].append({"product_id": b.get("product_id"), "reason": b.get("reason")})
        return {"ok": True}

    def t_schedule_callback(self, b):
        self.ledger["callbacks"].append({"date": b.get("date"), "time": b.get("time")})
        return {"ok": True}

    def t_transfer_to_agent(self, b):
        self.ledger["transfers"].append({"queue": b.get("queue")})
        return {"ok": True}

    def t_close_call(self, b):
        self.ledger["outcome"] = b.get("outcome")
        self.ledger["reason"] = b.get("reason") or None
        self.closed = True
        return {"ok": True}


# ---------------------------------------------------------------- engine


def sub(text, V, drop_single=False):
    if not isinstance(text, str):
        return text
    m = re.match(r"^\{\{(\w[\w.]*)\}\}$", text)
    if m:
        k = m.group(1)
        if k in V and V[k] not in (None,):
            return V[k]
        return None if drop_single else text
    return re.sub(r"\{\{(\w[\w.]*)\}\}", lambda mm: str(V.get(mm.group(1), mm.group(0))), text)


def flat(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat(prefix + "." + k, v, out)
    elif isinstance(obj, list):
        out[prefix] = obj
        for i, v in enumerate(obj):
            flat(prefix + "." + str(i), v, out)
    elif isinstance(obj, bool):
        out[prefix] = "true" if obj else "false"
    else:
        out[prefix] = obj


def cond_true(c, V):
    if "logic" in c:
        rs = [cond_true(x, V) for x in c.get("conditions") or []]
        return any(rs) if c["logic"] == "or" else all(rs)
    op = c.get("operator")
    if op == "always":
        return True
    val = V.get(c.get("variable"))
    if op == "is_set":
        return val not in (None, "")
    if op == "is_not_set":
        return val in (None, "")
    if val is None:
        return op == "not_equals"
    sv, so = str(val), str(c.get("operand"))
    if isinstance(val, bool):
        sv = "True" if val else "False"
    if op == "equals":
        return sv == so
    if op == "not_equals":
        return sv != so
    if op == "contains":
        return so.lower() in sv.lower()
    try:
        if op == "greater_than":
            return float(val) > float(c.get("operand"))
        if op == "less_than":
            return float(val) < float(c.get("operand"))
    except Exception:
        return False
    if op == "matches_intent":
        return False
    return False


class Walk(object):
    def __init__(self, wf, variables, bank, max_steps=400):
        self.wf, self.bank = wf, bank
        self.V = dict(variables)
        self.transcript = []  # (role, text, node)
        self.node = wf["initial_node"]
        self.ended = False
        self.code_steps_per_turn = []
        self.max_steps = max_steps
        self.nodes_entered = {}

    def say(self, text, node):
        if text:
            self.transcript.append(("agent", text, node))

    def start(self):
        n = self.wf["nodes"][self.node]
        self.say(sub(n["on_enter"].get("text", ""), self.V), self.node)

    def customer(self, text, extraction):
        """One customer turn: extraction in the current node, then route until a node waits or the call ends."""
        if self.ended:
            raise RuntimeError("call already ended")
        self.transcript.append(("customer", text, self.node))
        n = self.wf["nodes"][self.node]
        names = [e["name"] for e in n.get("extraction_schema") or []]
        for k, v in (extraction or {}).items():
            if k in names and v not in (None, ""):
                self.V[k] = v
        if "utterance" in names and "utterance" not in (extraction or {}):
            self.V["utterance"] = text
        code_steps = 0
        target = self.route(n)
        steps = 0
        while True:
            steps += 1
            if steps > self.max_steps:
                raise RuntimeError("routing loop")
            self.node = target
            self.nodes_entered[target] = self.nodes_entered.get(target, 0) + 1
            n = self.wf["nodes"][target]
            nt = n["node_type"]
            if nt == "code":
                code_steps += 1
                self.run_code(n)
                target = self.route(n)
                continue
            if nt == "api_request":
                self.run_api(n)
                target = self.route(n)
                continue
            if nt == "end_call":
                props = n["terminal"]["function"]["parameters"]["properties"]
                self.say(sub(props.get("spoken_message", {}).get("default", ""), self.V), target)
                self.end(target)
                break
            # conversation
            self.say(sub(n["on_enter"].get("text", ""), self.V), target)
            if n.get("passthrough"):
                target = self.route(n)
                continue
            break
        self.code_steps_per_turn.append(code_steps)

    def route(self, n):
        for t in n.get("transitions") or []:
            if cond_true(t["condition"], self.V):
                return t["target_node"]
        raise RuntimeError("no transition matched in %s" % n["name"])

    def run_code(self, n):
        code = n["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        g = {"vars": self.V, "__name__": "freya_code"}
        try:
            exec(compile(code, "<decide>", "exec"), g)
            status = "success"
        except Exception as e:
            status = "error"
            self.V["rb_error"] = repr(e)
        self.V["%s_response.status" % n["name"]] = status
        k = "%s_success_count" % n["name"] if status == "success" else "%s_failure_count" % n["name"]
        self.V[k] = int(self.V.get(k, 0)) + 1

    def build_body(self, fn):
        props = fn["function"]["parameters"]["properties"]["body"]["properties"]
        body = {}
        for f, spec in props.items():
            v = sub(spec.get("default"), self.V, drop_single=True)
            if v is None:
                continue
            if spec.get("type") == "number":
                try:
                    v = float(v)
                except Exception:
                    pass
            body[f] = v
        return body

    def run_api(self, n):
        fn = n["pre_actions"][0]
        tool = fn["function"]["name"]
        body = self.build_body(fn)
        code, res = self.bank.call(tool, body)
        name = n["name"]
        okflag = "ok" if (code == 200 and isinstance(res, dict) and res.get("ok")) else "fail"
        self.transcript.append(("tool", "%s:%s:%s" % (tool, okflag, body.get("product_id", "")), name))
        for k in [k for k in self.V if k.startswith(name + "_response.")]:
            del self.V[k]
        if code != 200:
            self.V[name + "_response.status"] = "error"
            self.V[name + "_response.status_code"] = code
            self.V[name + "_failure_count"] = int(self.V.get(name + "_failure_count", 0)) + 1
            return
        env = {"status": "success", "data": res, "message": "ok", "status_code": 200}
        out = {}
        flat(name + "_response", env, out)
        self.V.update(out)
        self.V[name + "_success_count"] = int(self.V.get(name + "_success_count", 0)) + 1
        for m in n.get("response_mapping") or []:
            cur = env
            for part in m["path"].split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is not None:
                self.V[m["variable"]] = ("true" if cur else "false") if isinstance(cur, bool) else cur

    def end(self, node):
        self.ended = True
        self.ended_node = node
        for t in self.wf.get("tools") or []:
            if "end_of_call" in ((t.get("config") or {}).get("alwaysRunsAt") or []):
                body = self.build_body(t)
                self.bank.call(t["function"]["name"], body)


def events(w):
    return list(w.transcript)


def agent_lines(w):
    return [t for r, t, _ in w.transcript if r == "agent"]


def text_of(w):
    return "\n".join("%s: %s" % (r.upper(), t) for r, t, _ in w.transcript)
