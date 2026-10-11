"""Map the tool API's actual field names to the roles the phone agent needs (hard rule 2: from the inputs).

The final briefs keep the seven tool names, but "the fields and the allowed values can change". So the request
bodies, the response keys the workflow routes on and the product fields the decide step reads are all looked up
here, deterministically, from the OpenAPI file: exact names first, then synonyms, then type/format/enum hints,
then the single remaining field. Anything still unresolved is reported (the builder fails loudly rather than
guessing a field the bank will reject).
"""
import re

SPEC = {
    "verify_identity": {"req": ["customer_id", "field", "answer"],
                        "resp": ["ok", "verified", "wrong_answers_left", "all_verified", "hint"]},
    "get_account": {"req": ["customer_id"], "resp": ["ok", "products"],
                    "item": ["product_id", "type", "past_due", "days_late"]},
    "create_promise": {"req": ["customer_id", "product_id", "amount", "date"], "resp": ["ok"]},
    "add_note": {"req": ["customer_id", "product_id", "reason"], "resp": ["ok"]},
    "close_call": {"req": ["customer_id", "outcome", "reason"], "resp": ["ok"]},
    "transfer_to_agent": {"req": ["customer_id", "queue"], "resp": ["ok"]},
    "schedule_callback": {"req": ["customer_id", "date", "time"], "resp": ["ok"]},
}
OPTIONAL = {("close_call", "req", "reason"), ("verify_identity", "resp", "hint"), ("verify_identity", "resp", "all_verified"),
            ("verify_identity", "resp", "wrong_answers_left"), ("schedule_callback", "req", "time")}

SYN = {
    "customer_id": ["customer_id", "customerid", "customer", "client_id", "clientid", "account_holder_id", "cid"],
    "field": ["field", "question", "check", "identity_field", "question_id", "factor", "item", "kind", "type"],
    "answer": ["answer", "value", "response", "given", "input", "reply"],
    "product_id": ["product_id", "productid", "product", "account_id", "accountid", "id"],
    "amount": ["amount", "promise_amount", "payment_amount", "promised_amount", "sum", "value"],
    "date": ["date", "promise_date", "payment_date", "pay_date", "pay_on", "due_date", "callback_date", "day", "on"],
    "time": ["time", "callback_time", "hour", "at_time", "at"],
    "reason": ["reason", "reason_code", "sub_outcome", "suboutcome", "detail", "code"],
    "outcome": ["outcome", "result", "disposition", "status", "outcome_code", "code"],
    "queue": ["queue", "team", "destination", "target", "department", "line", "to"],
    "ok": ["ok", "success", "succeeded", "accepted"],
    "verified": ["verified", "correct", "matched", "match", "passed", "valid"],
    "wrong_answers_left": ["wrong_answers_left", "attempts_left", "tries_left", "remaining_attempts", "remaining", "left"],
    "all_verified": ["all_verified", "identity_verified", "fully_verified", "complete", "completed", "done"],
    "hint": ["hint", "advice", "note"],
    "products": ["products", "accounts", "items", "debts", "facilities", "loans"],
    "type": ["type", "product_type", "kind", "category"],
    "past_due": ["past_due", "past_due_amount", "amount_due", "overdue_amount", "amount_overdue", "arrears", "overdue",
                 "due", "balance_due", "due_amount"],
    "days_late": ["days_late", "days_past_due", "dpd", "days_overdue", "days_in_arrears", "late_days", "days_due"],
}
TOKENS = {"customer_id": ["customer", "client"], "product_id": ["product", "account"], "amount": ["amount"],
          "date": ["date", "day"], "time": ["time", "hour"], "reason": ["reason"], "outcome": ["outcome", "result"],
          "queue": ["queue", "team"], "past_due": ["due", "overdue", "arrear"], "days_late": ["days", "dpd"],
          "type": ["type", "kind"], "field": ["field", "question"], "answer": ["answer", "value"],
          "wrong_answers_left": ["left", "remaining"], "all_verified": ["all", "complete"], "verified": ["verified"],
          "hint": ["hint"], "ok": ["ok", "success"], "products": ["products", "accounts"]}


def _type_ok(role, f):
    t = (f or {}).get("type") or "string"
    desc = ((f or {}).get("description") or "").lower()
    fmt = (f or {}).get("format") or ""
    if role in ("amount", "past_due"):
        return t in ("number", "integer")
    if role in ("days_late", "wrong_answers_left"):
        return t in ("integer", "number")
    if role in ("ok", "verified", "all_verified"):
        return t == "boolean"
    if role == "products":
        return t == "array"
    if role == "date":
        return t == "string" and (fmt == "date" or "date" in desc or "yyyy" in desc or True)
    if role == "time":
        return t == "string"
    return t in ("string", "integer", "number")


def _pick(role, fields, taken):
    names = [n for n in fields if n not in taken]
    low = dict((n.lower(), n) for n in names)
    for s in SYN.get(role, [role]):
        if s in low and _type_ok(role, fields[low[s]]):
            return low[s]
    for n in names:
        nl = n.lower()
        if any(tok in re.split(r"[_\W]+", nl) or tok in nl for tok in TOKENS.get(role, [])) and _type_ok(role, fields[n]):
            return n
    return None


def _map(roles, fields, tool, side):
    out, taken, missing = {}, set(), []
    for role in roles:
        n = _pick(role, fields, taken)
        if n:
            out[role] = n
            taken.add(n)
    left = [r for r in roles if r not in out]
    rest = [n for n in fields if n not in taken]
    if len(left) == 1 and len(rest) == 1 and _type_ok(left[0], fields[rest[0]]):
        out[left[0]] = rest[0]
        left = []
    for r in left:
        if (tool, side, r) not in OPTIONAL:
            missing.append("%s %s: no field for %s (fields: %s)" % (tool, side, r, ", ".join(sorted(fields))))
    return out, missing


def resolve(toolspec):
    """-> (api, problems). api[tool] = {"req": {role: name}, "resp": {role: name}, "item": {role: name}}"""
    api, problems = {}, []
    for tool, spec in SPEC.items():
        t = toolspec["tools"].get(tool) or {}
        req, m1 = _map(spec["req"], t.get("fields") or {}, tool, "req")
        resp, m2 = _map(spec["resp"], t.get("response") or {}, tool, "resp")
        entry = {"req": req, "resp": resp}
        problems += m1 + m2
        if "item" in spec:
            items = ((t.get("response") or {}).get(resp.get("products") or "products") or {}).get("items") or {}
            item, m3 = _map(spec["item"], items, tool, "item")
            entry["item"] = item
            problems += m3
        if tool == "schedule_callback" and "time" not in req and "date" in req:
            entry["combined_datetime"] = True  # one field for date and time
        api[tool] = entry
    return api, problems
