"""The policy: everything brief-specific the runtime needs, as data. Validated against the tool API file.

A policy is produced at build time (policy/extract.py) from ONE brief file (or a base brief plus an
extension) and the brief's own OpenAPI file. The runtime (runtime/agent_runtime.py) never contains
brief-specific values; it reads them from the policy embedded in the workflow.
"""
import datetime
import re

# Situations the runtime can end a call in. The policy maps each one to the brief's outcome/reason.
SITUATIONS = (
    "promise", "paid", "transfer_restructuring", "transfer_human", "transfer_support",
    "refused", "hardship", "dispute", "service_error",
    "id_failed", "id_declined",
    "callback", "no_callback", "wrong_number", "deceased", "unclear",
)

# Lines the agent speaks verbatim. Required sentences from the brief must be copied exactly.
LINE_KEYS = (
    "opening",            # first sentence(s) of the call; must contain the person question at the end
    "person_question",    # the person check alone, used when asking again
    "third_party_ask",    # ask when the customer can be reached (says nothing about the reason)
    "third_party_no_info",  # what to say to a third party who asks why/offers to pay (reveals nothing)
    "callback_window",    # one sentence describing the allowed callback window, used to ask for another time
    "callback_done",      # confirm a booked callback (no reason given)
    "deceased",           # the brief's condolence sentence
    "wrong_number",       # apology for a wrong number
    "id_intro",           # lead-in before the first security question
    "id_explain",         # the one explanation that the questions protect the account
    "id_fail",            # guidance after too many wrong answers (e.g. app or branch)
    "id_retry",           # a wrong answer: ask again
    "id_swapped",         # the bank hinted day/month swapped: ask for the month as a word
    "id_unreadable",      # the answer could not be read: ask again
    "verified",           # identity passed
    "disclosure_intro",   # who is calling and why, after identity (e.g. collections team, late payment)
    "first_ask_single",   # first ask for one product
    "first_ask_multi",    # first ask for several products
    "confirm_question",   # the question after the read-back
    "after_promise",      # sentence required after a recorded promise
    "rest_overdue",       # said with a floor offer
    "below_floor",        # amount below the floor cannot be recorded
    "paid_reply",         # reply to "I already paid"
    "scam_reply",         # reply to "is this a scam?"
    "robot_reply",        # reply to "are you a robot?"
    "no_info",            # a question the tools cannot answer
    "change_in_app",      # a recorded promise cannot be changed in this call
    "record_failed",      # a write failed twice
    "help_first",         # asked for a human: offer help once first
    "sympathy",           # one short sentence of sympathy (hardship)
    "support_offer",      # offer to connect to the support team (hardship)
    "transfer",           # said before a transfer
    "dispute_reply",      # acknowledge a dispute without arguing
    "goodbye",            # thank the customer and say goodbye
    "tech_problem",       # honest technical-problem ending
)

DATE_RULES = ("today", "tomorrow", "end_of_week", "deadline", "next_business_day")
AMOUNT_RULES = ("full", "floor", "full_or_floor", "current")
ID_KINDS = ("date", "digits", "year", "text")


def _is_date(s):
    try:
        datetime.date.fromisoformat(s)
        return True
    except Exception:
        return False


def validate(policy, toolspec):
    """Return a list of human-readable errors (empty = valid)."""
    e = []
    en = toolspec["enums"]
    req = ("bank", "lines", "address", "identity", "calendar", "bands", "products", "attempts",
           "callback", "outcomes", "queues", "notes", "multi", "interrupts", "person")
    for k in req:
        if k not in policy:
            e.append("missing key: %s" % k)
    if e:
        return e
    lines = policy["lines"]
    for k in LINE_KEYS:
        if not isinstance(lines.get(k), str) or not lines.get(k).strip():
            e.append("lines.%s is missing or empty" % k)
    for k, v in lines.items():
        if isinstance(v, str) and ("{{" in v or "}}" in v):
            e.append("lines.%s contains double braces" % k)
    # identity
    qs = policy["identity"].get("questions") or []
    if not qs:
        e.append("identity.questions is empty")
    for i, q in enumerate(qs):
        if q.get("field") not in en["identity_fields"]:
            e.append("identity.questions[%d].field %r not in tool API enum %s" % (i, q.get("field"), en["identity_fields"]))
        if q.get("kind") not in ID_KINDS:
            e.append("identity.questions[%d].kind %r not in %s" % (i, q.get("kind"), ID_KINDS))
        if not (q.get("ask") or "").strip():
            e.append("identity.questions[%d].ask is empty" % i)
        if q.get("kind") == "digits" and not isinstance(q.get("length"), int):
            e.append("identity.questions[%d].length must be an integer for digits" % i)
    mw = policy["identity"].get("max_wrong")
    if not isinstance(mw, int) or mw < 1:
        e.append("identity.max_wrong must be a positive integer")
    sh = policy["identity"].get("swap_hint")
    if sh and en["hints"] and sh not in en["hints"]:
        e.append("identity.swap_hint %r not in tool API hints %s" % (sh, en["hints"]))
    # calendar
    cal = policy["calendar"]
    if not all(isinstance(d, int) and 0 <= d <= 6 for d in cal.get("weekend", [])):
        e.append("calendar.weekend must be weekday numbers 0-6 (Monday=0)")
    for h in cal.get("holidays", []):
        if not _is_date(h):
            e.append("calendar.holidays has a non-ISO date %r" % h)
    # bands
    bands = policy["bands"]
    if not bands:
        e.append("bands is empty")
    for i, b in enumerate(bands):
        for k in ("name", "min", "max", "deadline_kind", "deadline_n", "attempts"):
            if k not in b:
                e.append("bands[%d].%s missing" % (i, k))
        if b.get("deadline_kind") not in ("business_days", "calendar_days"):
            e.append("bands[%d].deadline_kind must be business_days or calendar_days" % i)
    ranges = sorted((b.get("min", 0), b.get("max", 0)) for b in bands if isinstance(b.get("min"), int))
    for (a1, b1), (a2, b2) in zip(ranges, ranges[1:]):
        if a2 != b1 + 1:
            e.append("bands do not form contiguous days_late ranges: %s" % ranges)
            break
    # products
    for t, p in policy["products"].items():
        if en["product_types"] and t not in en["product_types"]:
            e.append("products.%s not in tool API product types %s" % (t, en["product_types"]))
        if p.get("floor_field") and en["product_fields"] and p["floor_field"] not in en["product_fields"]:
            e.append("products.%s.floor_field %r not a product field %s" % (t, p.get("floor_field"), en["product_fields"]))
        for ph in re.findall(r"\{(\w+)\}", p.get("phrase", "")):
            if en["product_fields"] and ph not in en["product_fields"]:
                e.append("products.%s.phrase uses unknown field {%s}" % (t, ph))
    for t in en["product_types"]:
        if t not in policy["products"]:
            e.append("tool API product type %r has no products entry" % t)
    # attempts
    for i, a in enumerate(policy["attempts"]):
        if a.get("date_rule") not in DATE_RULES:
            e.append("attempts[%d].date_rule %r not in %s" % (i, a.get("date_rule"), DATE_RULES))
        if a.get("amount_rule") not in AMOUNT_RULES:
            e.append("attempts[%d].amount_rule %r not in %s" % (i, a.get("amount_rule"), AMOUNT_RULES))
        for bn in a.get("bands") or []:
            if bn not in [b.get("name") for b in bands]:
                e.append("attempts[%d].bands names unknown band %r" % (i, bn))
    # callback
    cb = policy["callback"]
    for k in ("start", "end"):
        if not re.match(r"^\d{2}:\d{2}$", str(cb.get(k, ""))):
            e.append("callback.%s must be HH:MM" % k)
    # outcomes
    outs = policy["outcomes"]
    for s in SITUATIONS:
        if s not in outs:
            e.append("outcomes.%s missing" % s)
            continue
        o = outs[s]
        if not (isinstance(o, list) and len(o) == 2):
            e.append("outcomes.%s must be [outcome, reason-or-null]" % s)
            continue
        if en["outcomes"] and o[0] not in en["outcomes"]:
            e.append("outcomes.%s outcome %r not in tool API enum %s" % (s, o[0], en["outcomes"]))
    # queues
    for k in ("restructuring", "human", "support"):
        q = policy["queues"].get(k)
        if q is not None and en["queues"] and q not in en["queues"]:
            e.append("queues.%s %r not in tool API enum %s" % (k, q, en["queues"]))
    # notes
    if policy["notes"].get("enabled"):
        for k, v in (policy["notes"].get("reasons") or {}).items():
            if en["note_reasons"] and v not in en["note_reasons"]:
                e.append("notes.reasons.%s %r not in tool API enum %s" % (k, v, en["note_reasons"]))
    return e
