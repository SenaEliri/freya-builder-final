"""Phase 0: brief(s) + tool API -> validated policy JSON, using Freya's model at build time.

Nothing here knows a particular brief. The questions describe what the runtime can do; the answers come
from the brief; every enumerated value is checked against the tool API file; errors are fed back for one
bounded retry per section; whatever stays invalid falls back to a safe default and is reported.
"""
import concurrent.futures
import copy
import json
import re

from builder import llm_freya
from builder.policy import schema

DEFAULT_LINES = {
    "opening": "Hello, this is {bank}'s digital assistant calling, and this call is recorded. Am I speaking with {title} {last_name}?",
    "person_question": "Am I speaking with {title} {last_name}?",
    "third_party_ask": "When would be a good time to reach {title} {last_name}?",
    "third_party_no_info": "I'm sorry, I can only speak with {title} {last_name} directly.",
    "callback_window": "I can only arrange a call {window}. Is there a time in that window that works?",
    "callback_done": "Thank you. We will call back on {when}.",
    "deceased": "I am sorry for your loss.",
    "wrong_number": "I'm sorry for the inconvenience.",
    "id_intro": "Before I continue, I need to ask you {n_questions} security questions.",
    "id_explain": "These questions protect your account.",
    "id_fail": "I'm sorry, I could not verify your identity.",
    "id_retry": "That does not match our records. Could you tell me {label} again?",
    "id_swapped": "Could you say the month as a word, please?",
    "id_unreadable": "Sorry, I didn't catch that. Could you tell me {label} again?",
    "id_more": "Could you give me the rest of {label}, please?",
    "verified": "Thank you, your identity is verified.",
    "disclosure_intro": "I am calling from {bank} about a late payment.",
    "disclosure_item": "Your {product} has {past_due} past due, {days_late} days late.",
    "first_ask_single": "Can you make this payment today?",
    "first_ask_multi": "Can you pay all of them today?",
    "offer": "Could you pay {amount} on {date}?",
    "floor_offer": "I can record a payment of {amount} instead.",
    "ask_exact_day": "Which exact day would that be?",
    "next_business_day_offer": "{asked} is not a business day. The next business day is {date}. Would that work?",
    "deadline_offer": "The latest date I can record is {date}. Can you pay by then?",
    "past_date": "That date has already passed. Which day from today on would work?",
    "date_conflict": "Just to be sure, did you mean {date}?",
    "readback": "So that is {items}.",
    "readback_item": "{amount} for your {product} on {date}",
    "readback_clamped": "{amount} for your {product} on {date}, the latest date I can record for it",
    "recorded": "Your promise of {amount} for your {product} on {date} is recorded.",
    "confirm_question": "Do you confirm?",
    "after_promise": "Thank you.",
    "rest_overdue": "The rest stays overdue.",
    "below_floor": "I'm sorry, I can't record an amount below {floor}.",
    "paid_reply": "Thank you for letting me know.",
    "scam_reply": "You can verify this call by phoning {bank}'s customer service number.",
    "robot_reply": "I am {bank}'s digital assistant.",
    "no_info": "I'm sorry, I don't have that information.",
    "change_in_app": "A recorded promise can't be changed in this call.",
    "record_failed": "I'm sorry, I could not record the promise for your {product} because of a technical problem.",
    "help_first": "Before I transfer you, is there anything I can help you with myself?",
    "sympathy": "I'm very sorry to hear that.",
    "support_offer": "Would you like me to connect you with our customer support team?",
    "transfer": "I will transfer you now.",
    "dispute_reply": "I understand, thank you for letting me know.",
    "anything_else": "Is there anything else I can help you with?",
    "repeat": "Sorry, could you repeat that, please?",
    "which_product": "Which product do you mean: {products}?",
    "goodbye": "Thank you for your time. Goodbye.",
    "tech_problem": "I'm sorry, we are having a technical problem, so I can't continue this call right now.",
}

SITUATIONS_TEXT = {
    "promise": "at least one payment promise was recorded",
    "paid": "the customer says they already paid (and, with several products, every product is paid)",
    "transfer_restructuring": "the call was transferred because the customer asked for a new payment plan / restructuring",
    "transfer_human": "the call was transferred because the customer insisted on a human",
    "transfer_support": "the call was transferred to support after hardship (illness, bereavement, job loss)",
    "refused": "verified customer, no promise: refused or persuasion attempts used up, or said twice they do not want to talk",
    "hardship": "verified customer, no promise: hardship and declined the support transfer",
    "dispute": "verified customer, no promise: disputes the debt",
    "service_error": "no promise because recording the promise failed twice (technical error)",
    "id_failed": "identity check failed (too many wrong answers)",
    "id_declined": "the customer declined to answer the identity questions",
    "callback": "someone else answered and a callback was scheduled",
    "no_callback": "someone else answered and no callback could be scheduled in the allowed window",
    "wrong_number": "the number does not belong to the customer",
    "deceased": "the customer has died",
    "unclear": "it stayed unclear who is on the line",
}

PREAMBLE = ("The CONTEXT is a bank's specification ('brief') for an automated phone agent that calls customers who are late "
            "on payments, plus the bank's tool API. The brief may be a clean specification or raw material (emails, policy "
            "extracts, amendments/memos and code lists). When several texts disagree, the LATER amendment overrides the "
            "earlier text; report the rules in force after all amendments. When the brief gives a code list, use the codes "
            "the tool API accepts. If the brief does not say something, use null. ")


def build_context(brief_texts, toolspec):
    from builder.policy import openapi
    parts = []
    for i, t in enumerate(brief_texts):
        role = "base brief" if i == 0 else "extension brief: its rules replace the base brief's where it says so"
        parts.append("=== BRIEF FILE %d (%s) ===\n%s" % (i + 1, role, t.strip()))
    parts.append("=== TOOL API (fields and allowed values) ===\n" + openapi.field_descriptions(toolspec))
    return "\n\n".join(parts)


def q_identity(en):
    return PREAMBLE + (
        "How does the agent check identity? Allowed field values from the tool API: %s. Return JSON: "
        '{"questions": [{"field": <allowed value>, "label": "<how to refer to it, e.g. your date of birth>", '
        '"ask": "<the question the agent asks for it>", "kind": "date|digits|year|text", "length": <digits count or null>, '
        '"date_order": "DMY|MDY|YMD for dates given only as numbers"}] in the order the brief requires, '
        '"max_wrong": <total wrong answers that end the check>, "swap_hint": <the tool API hint value meaning day and month '
        'were swapped, or null>, "swap_ask": "<what to ask then>", "fail_say": "<what the agent must tell the customer after '
        'the check failed, e.g. where to go instead>", "explain_once": "<the one explanation when the customer does not want to '
        'answer>", "decline_after": <number of refusals that close the call>}' % json.dumps(en["identity_fields"]))


def q_calendar():
    return PREAMBLE + (
        'Return JSON about dates: {"weekend": [weekday numbers that are NOT business days, Monday=0 ... Sunday=6], '
        '"holidays": ["YYYY-MM-DD", ...] (the bank holidays in force), "next_weekday": "following_week" if "next <weekday>" '
        'means that weekday in the following calendar week else "next_occurrence", "this_weekday": "current_week" or '
        '"next_occurrence", "numeric_order": "DMY|MDY" for dates given only as numbers}')


def q_bands():
    return PREAMBLE + (
        'Return JSON about payment deadlines and persuasion: {"first_ask": {"date_rule": "<rule>", "amount_rule": "<rule>"} '
        '(the FIRST payment request, made right after the account is described and before any refusal), '
        '"bands": [{"name": "<short name>", "min": <min days late, inclusive>, '
        '"max": <max days late, inclusive>, "deadline_kind": "business_days|calendar_days", "deadline_n": <N: the deadline is the '
        'N-th business or calendar day after today>, "attempts": <number of EXTRA offers (persuasion attempts) allowed in this band '
        'after the first request was refused; the first request itself is not counted>}], '
        '"attempts": [{"n": <1-based number of the extra offer>, "date_rule": "<rule>", "amount_rule": "<rule>", '
        '"bands": null or [band names the extra offer applies to]}] (ONLY the extra offers made after a refusal, in order; '
        'never include the first request)}. Date rules: today | tomorrow | end_of_week (last business day of this week, or of next '
        'week if today is that day) | deadline (the band\'s latest allowed date) | next_business_day. Amount rules: full | floor '
        '(the lowest acceptable amount) | full_or_floor (the full amount, or the floor if the customer already said the full amount '
        'is too much).')


def q_amounts(en):
    return PREAMBLE + (
        "Products the tool API knows: %s; product fields: %s. Return JSON: "
        '{"products": {"<product type>": {"phrase": "<how the agent names it, using {field} placeholders for product fields, '
        'e.g. credit card ending {card_last4}>", "floor_field": "<the product field that is the lowest acceptable amount>"}}, '
        '"currency_word": "<e.g. dollars>", "first_ask_single": "<the exact first question asking to pay one product>", '
        '"first_ask_multi": "<the first question when the customer has several products, or null>", "rest_overdue": "<sentence '
        'to say when offering the floor, or null>", "below_floor": "<what to say when the customer offers less than the floor, '
        'or null>", "never_ask_how_much": true|false}' % (json.dumps(en["product_types"]), json.dumps(en["product_fields"])))


def q_outcomes(en, ts):
    sit = "; ".join("%s = %s" % (k, v) for k, v in SITUATIONS_TEXT.items())
    reasons = ts["tools"]["close_call"]["fields"].get("reason", {}).get("description", "")
    return PREAMBLE + (
        "Every call ends with close_call(outcome, reason). Allowed outcome values: %s. Reason field: %s. Map each situation "
        "to the outcome and reason the brief requires (reason null when the brief lists none). Situations: %s. Return JSON: "
        '{"<situation>": ["<outcome>", "<reason or null>"], ...} with all situations.' % (json.dumps(en["outcomes"]), reasons, sit))


def q_third_party(en):
    return PREAMBLE + (
        'Return JSON about calls answered by someone else and callbacks: {"callback_days": [subset of "today", "tomorrow", '
        '"next_business_day"] ("next_business_day" when the brief says next business day or next working day; "tomorrow" only '
        'when it says tomorrow or the next calendar day), "callback_start": "HH:MM", "callback_end": "HH:MM", "after_now": true|false (must be later than '
        'now), "max_asks": <how many times to ask for a time in total before giving up>, "condolence": "<exact sentence when the '
        'customer has died, or null>", "wrong_number_say": "<what to say for a wrong number, or null>"}')


def q_interrupts(en):
    return PREAMBLE + (
        "Allowed transfer queues: %s. Return JSON: "
        '{"hardship": "<what counts as hardship>", "support_queue": "<queue or null>", "sympathy": "<sentence or null>", '
        '"support_offer": "<how to offer the transfer or null>", "dispute": "<what counts as a dispute>", '
        '"dispute_say": "<sentence or null>", "already_paid": "<what counts>", "paid_say": "<what to say>", '
        '"restructuring": "<what counts>", "restructuring_queue": "<queue or null>", "human": "<what counts>", '
        '"human_queue": "<queue or null>", "human_ask_first": true|false, "scam_say": "<what to say or null>", '
        '"robot_say": "<what to say or null>", "no_info_say": "<what to say when the tools cannot answer, or null>", '
        '"change_say": "<what to say when asked to change a recorded promise, or null>", "precedence": ["hardship", '
        '"dispute", "already_paid", "restructuring", "human"] reordered by the brief\'s precedence rules, '
        '"refuse_talk_times": <times the customer says they do not want to talk before the call closes>}' % json.dumps(en["queues"]))


LINE_SPEC = {
    "opening": "the first sentence(s) of the call, ending with the question that checks who is on the line",
    "person_question": "the question that checks who is on the line, alone",
    "third_party_ask": "said to SOMEONE ELSE who answered (not the customer): ask when {title} {last_name} can be reached; refer to the customer as {title} {last_name}, never as 'you'; say nothing about why we call",
    "third_party_no_info": "to someone else who asks why we call or offers to pay: reveal nothing",
    "id_intro": "lead-in before the first security question (nothing about why the bank calls)",
    "id_explain": "the one explanation when the customer does not want to answer the security questions",
    "id_fail": "after the identity check failed for good: say you could not verify their identity, then where they can go instead (if the brief says)",
    "id_swapped": "when the bank says day and month of the date seem swapped",
    "verified": "identity check passed",
    "disclosure_intro": "first sentence after identity: who is calling and why",
    "first_ask_single": "the first question asking the customer to pay one late product",
    "first_ask_multi": "the first question when the customer has several late products",
    "confirm_question": "the question after reading the promise back",
    "after_promise": "the sentence after a promise was recorded",
    "rest_overdue": "said when offering the lowest acceptable amount",
    "below_floor": "when the customer offers less than the lowest acceptable amount (use {floor} for the amount)",
    "paid_reply": "when the customer says they already paid",
    "dispute_reply": "when the customer disputes the debt",
    "scam_reply": "when the customer asks if this is a scam",
    "robot_reply": "when the customer asks if they talk to a robot or AI",
    "no_info": "when the customer asks something the agent cannot answer",
    "change_in_app": "when asked to change or cancel a promise that is already recorded: say it cannot be changed in this call and where it can be changed (if the brief says)",
    "sympathy": "one short sentence of sympathy after illness, bereavement or job loss",
    "support_offer": "a question offering to connect them to the support team the brief names",
    "help_first": "the first time the customer asks for a human: a question offering to help them yourself before transferring",
    "transfer": "just before transferring the call",
    "deceased": "when told the customer has died",
    "wrong_number": "when told it is a wrong number",
    "goodbye": "thank the customer and say goodbye",
}


def q_lines():
    keys = "; ".join("%s = %s" % (k, v) for k, v in LINE_SPEC.items())
    return PREAMBLE + (
        "For each key below, write the EXACT words the agent says aloud to the customer. Rules: first person (I/we), "
        "address the customer as 'you', complete sentences that start with a capital letter and end with . or ?. Copy "
        "sentences the brief quotes word for word. If the brief only describes what to say, write the sentence that does "
        "exactly that (brief: 'say that payments can take one business day to appear' -> 'Payments can take one business "
        "day to appear.'). Never write instructions, descriptions or text starting with 'that', 'say', 'tell', 'offer', "
        "'ask' or 'explain'. Keep {title} and {last_name} as placeholders for the customer's title and last name. Use null "
        "when the brief says nothing about a key. Keys: " + keys +
        '. Also add "forbidden_before_identity": [words the agent must never say before identity is verified]. '
        "Return one JSON object with these keys.")


def q_sentences():
    return q_lines()


def q_multi(en):
    return PREAMBLE + (
        "Allowed note reasons: %s. Return JSON: "
        '{"multi_enabled": true|false (customers can be late on several products), "ask_all_today": true|false, '
        '"per_product_attempts": true|false, "clamp_to_deadline": true|false (one date for everything that is after one '
        'product\'s deadline is recorded on that product\'s own deadline), "single_readback": true|false, '
        '"notes_enabled": true|false (the agent must call add_note for products without a promise), "note_reasons": '
        '{"refused": "<value>", "hardship": "<value>", "dispute": "<value>", "paid": "<value>", "service_error": "<value>"}, '
        '"notes_on_transfer": true|false, "closing_reason": "first_non_paid_note" or "<other rule>"}' % json.dumps(en["note_reasons"]))


SECTIONS = ("identity", "calendar", "bands", "amounts", "outcomes", "third_party", "interrupts", "sentences", "multi")


def questions(toolspec):
    en = toolspec["enums"]
    return {"identity": q_identity(en), "calendar": q_calendar(), "bands": q_bands(), "amounts": q_amounts(en),
            "outcomes": q_outcomes(en, toolspec), "third_party": q_third_party(en), "interrupts": q_interrupts(en),
            "sentences": q_sentences(), "multi": q_multi(en)}


# ---------------------------------------------------------------- deterministic helpers

def bank_name(texts):
    for t in texts:
        m = re.search(r"\b([A-Z][\w&'.-]+(?: [A-Z][\w&'.-]+){0,3} (?:Bank|Credit Union|Savings|Finance|Lending))\b", t)
        if m:
            return m.group(1)
    return "the bank"


def iso_dates(text):
    return sorted(set(re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", text)))


BAD_START = re.compile(r"^(?:that\b|(?i:say|tell|offer|ask|explain|mention|one short|a short|inform|state|the agent|agent)\b)")


def line_problem(key, v):
    if v is None:
        return None
    if not isinstance(v, str) or not v.strip():
        return "%s is empty" % key
    t = v.strip()
    if BAD_START.match(t):
        return "%s is an instruction or description, not the words spoken: %r" % (key, t[:80])
    if re.search(r"\bthe customer\b(?!\s+(?:support|service|services|care|team|helpline|line|centre|center|desk))|\bthey (?:can|should|must)\b", t, re.I):
        return "%s talks about the customer instead of to them: %r" % (key, t[:80])
    if not t[0].isupper() and not t.startswith("{"):
        return "%s must start with a capital letter: %r" % (key, t[:80])
    if t[-1] not in ".?!":
        return "%s must end with . or ? : %r" % (key, t[:80])
    if "{{" in t or "}}" in t:
        return "%s contains double braces" % key
    if key in NEEDS_NAME and "{last_name}" not in t:
        return "%s must name the customer with {title} {last_name}: %r" % (key, t[:80])
    return None


NEEDS_NAME = ("opening", "person_question", "third_party_ask")


def section_errors(name, ans, toolspec):
    """Cheap per-section checks so a bad answer can be re-asked with the reasons."""
    en = toolspec["enums"]
    e = []
    if not isinstance(ans, dict):
        return ["the answer was not a JSON object"]
    if name == "identity":
        qs = ans.get("questions") or []
        if not qs:
            e.append("questions is empty")
        for q in qs:
            if q.get("field") not in en["identity_fields"]:
                e.append("field %r is not one of %s" % (q.get("field"), en["identity_fields"]))
            if q.get("kind") not in schema.ID_KINDS:
                e.append("kind %r is not one of %s" % (q.get("kind"), list(schema.ID_KINDS)))
        if not isinstance(ans.get("max_wrong"), int):
            e.append("max_wrong must be an integer")
    elif name == "calendar":
        for h in ans.get("holidays") or []:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(h)):
                e.append("holiday %r is not YYYY-MM-DD" % h)
        if not isinstance(ans.get("weekend"), list):
            e.append("weekend must be a list of weekday numbers")
    elif name == "bands":
        if not ans.get("bands"):
            e.append("bands is empty")
        for b in ans.get("bands") or []:
            if b.get("deadline_kind") not in ("business_days", "calendar_days"):
                e.append("deadline_kind %r invalid" % b.get("deadline_kind"))
            for k in ("min", "max", "deadline_n", "attempts"):
                if not isinstance(b.get(k), int):
                    e.append("band %s.%s must be an integer" % (b.get("name"), k))
        for a in ans.get("attempts") or []:
            if a.get("date_rule") not in schema.DATE_RULES:
                e.append("attempt date_rule %r invalid" % a.get("date_rule"))
            if a.get("amount_rule") not in schema.AMOUNT_RULES:
                e.append("attempt amount_rule %r invalid" % a.get("amount_rule"))
    elif name == "amounts":
        for t in en["product_types"]:
            p = (ans.get("products") or {}).get(t)
            if not p:
                e.append("no entry for product type %r" % t)
            elif p.get("floor_field") not in en["product_fields"]:
                e.append("floor_field %r of %s is not a product field %s" % (p.get("floor_field"), t, en["product_fields"]))
    elif name == "outcomes":
        for s in schema.SITUATIONS:
            v = ans.get(s)
            if not (isinstance(v, list) and len(v) == 2):
                e.append("situation %s missing or not [outcome, reason]" % s)
            elif v[0] not in en["outcomes"]:
                e.append("situation %s outcome %r is not one of %s" % (s, v[0], en["outcomes"]))
    elif name == "interrupts":
        for k in ("support_queue", "restructuring_queue", "human_queue"):
            if ans.get(k) is not None and ans.get(k) not in en["queues"]:
                e.append("%s %r is not one of %s" % (k, ans.get(k), en["queues"]))
    elif name == "sentences":
        for k in LINE_SPEC:
            pr = line_problem(k, ans.get(k))
            if pr:
                e.append(pr)
        forb = [w.lower() for w in (ans.get("forbidden_before_identity") or []) if isinstance(w, str)]
        for k in ("opening", "person_question", "id_intro", "third_party_ask", "third_party_no_info", "id_explain"):
            v = (ans.get(k) or "").lower()
            for w in forb:
                if w and re.search(r"\b" + re.escape(w) + r"\b", v):
                    e.append("%s says the forbidden word %r before identity is verified" % (k, w))
    elif name == "multi":
        if ans.get("notes_enabled"):
            for k, v in (ans.get("note_reasons") or {}).items():
                if v not in en["note_reasons"]:
                    e.append("note reason %s=%r is not one of %s" % (k, v, en["note_reasons"]))
    return e


def ask_section(name, question, context, toolspec, trace, retries=1):
    ans, raw = llm_freya.ask(context, question, "policy section %s" % name, trace=trace)
    errs = section_errors(name, ans, toolspec)
    tries = 0
    while errs and tries < retries:
        tries += 1
        q2 = question + "\nYour previous answer had these problems, fix them: " + "; ".join(errs[:8]) + \
            "\nPrevious answer: " + (raw or "")[:1500]
        ans, raw = llm_freya.ask(context, q2, "policy section %s (retry %d)" % (name, tries), trace=trace)
        errs = section_errors(name, ans, toolspec)
    return name, ans if isinstance(ans, dict) else {}, errs


def extract(brief_texts, toolspec, trace=None, parallel=4):
    context = build_context(brief_texts, toolspec)
    qs = questions(toolspec)
    answers, problems = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = [ex.submit(ask_section, n, qs[n], context, toolspec, trace) for n in SECTIONS]
        for f in concurrent.futures.as_completed(futs):
            n, ans, errs = f.result()
            answers[n] = ans
            if errs:
                problems[n] = errs
    policy = assemble(answers, brief_texts, toolspec, problems)
    errs = schema.validate(policy, toolspec)
    return policy, {"section_problems": problems, "policy_errors": errs, "answers": answers}


def _s(v):
    return v.strip() if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none") else None


def normalize_attempts(raw, first_ask, bands, problems):
    """Keep only the extra offers made after a refusal, numbered 1..n in order.

    An entry identical to the first request is not an extra offer (models sometimes list the first request as
    attempt 1); it is dropped and the band counts are capped at the number of offers that apply to each band."""
    items = [dict(a) for a in raw or [] if isinstance(a, dict) and a.get("date_rule") in schema.DATE_RULES
             and a.get("amount_rule") in schema.AMOUNT_RULES]
    for a in items:
        try:
            a["n"] = int(a.get("n") or 0)
        except Exception:
            a["n"] = 0
        if a.get("bands") is not None and not isinstance(a.get("bands"), list):
            a["bands"] = None
    names = [b["name"] for b in bands]

    def canon(n):
        n0 = str(n).strip().lower()
        for b in names:
            if n0 == b.lower() or n0.endswith(" " + b.lower()) or b.lower().endswith(" " + n0):
                return b
        return str(n)
    for a in items:
        if a.get("bands"):
            a["bands"] = [canon(n) for n in a["bands"]]
            if sorted(set(a["bands"])) == sorted(names):
                a["bands"] = None
    items.sort(key=lambda a: a["n"])
    kept = []
    for a in items:
        if a["date_rule"] == first_ask["date_rule"] and a["amount_rule"] == first_ask["amount_rule"]:
            problems.setdefault("attempts", []).append("dropped an extra offer identical to the first request: %s/%s"
                                                       % (a["date_rule"], a["amount_rule"]))
            continue
        kept.append({"n": len(kept) + 1, "date_rule": a["date_rule"], "amount_rule": a["amount_rule"],
                     "bands": a.get("bands")})
    for b in bands:
        applies = len([a for a in kept if not a.get("bands") or b["name"] in a["bands"]])
        if b["attempts"] > applies:
            problems.setdefault("attempts", []).append("band %s: %d extra offers capped to the %d defined"
                                                       % (b["name"], b["attempts"], applies))
            b["attempts"] = applies
    return kept


def assemble(A, brief_texts, toolspec, problems):
    en = toolspec["enums"]
    bank = bank_name(brief_texts)
    lines = dict(DEFAULT_LINES)
    sent = A.get("sentences") or {}
    forb = [w.lower() for w in (sent.get("forbidden_before_identity") or []) if isinstance(w, str) and w.strip()]
    for k in LINE_SPEC:
        v = _s(sent.get(k))
        if v and not line_problem(k, v):
            if k in ("opening", "person_question", "id_intro", "third_party_ask", "third_party_no_info", "id_explain") and \
                    any(re.search(r"\b" + re.escape(w) + r"\b", v.lower()) for w in forb):
                continue
            lines[k] = v
    idn = A.get("identity") or {}
    qs = []
    for q in idn.get("questions") or []:
        if q.get("field") in en["identity_fields"] and q.get("kind") in schema.ID_KINDS:
            item = {"field": q["field"], "label": _s(q.get("label")) or q["field"].replace("_", " "),
                    "ask": _s(q.get("ask")) or "What is your %s?" % q["field"].replace("_", " "), "kind": q["kind"]}
            if q["kind"] == "digits":
                item["length"] = int(q.get("length") or 4)
            if q["kind"] == "date":
                item["date_order"] = q.get("date_order") if q.get("date_order") in ("DMY", "MDY", "YMD") else "DMY"
            qs.append(item)
    if not qs:  # fall back to the tool API's own field order
        for f in en["identity_fields"]:
            qs.append({"field": f, "label": "your " + f.replace("_", " "), "ask": "What is your %s?" % f.replace("_", " "), "kind": "text"})
    lines["id_intro"] = lines["id_intro"].replace("{n_questions}", {1: "one", 2: "two", 3: "three"}.get(len(qs), str(len(qs))))
    cal = A.get("calendar") or {}
    holidays = [h for h in (cal.get("holidays") or []) if re.match(r"^\d{4}-\d{2}-\d{2}$", str(h))]
    weekend = [d for d in (cal.get("weekend") or [5, 6]) if isinstance(d, int) and 0 <= d <= 6] or [5, 6]
    bands_ans = A.get("bands") or {}
    bands = [b for b in bands_ans.get("bands") or [] if all(isinstance(b.get(k), int) for k in ("min", "max", "deadline_n", "attempts"))
             and b.get("deadline_kind") in ("business_days", "calendar_days")]
    for b in bands:
        b["name"] = str(b.get("name") or "band%d" % b["min"])
    fa = bands_ans.get("first_ask") if isinstance(bands_ans.get("first_ask"), dict) else {}
    first_ask = {"date_rule": fa.get("date_rule") if fa.get("date_rule") in schema.DATE_RULES else "today",
                 "amount_rule": fa.get("amount_rule") if fa.get("amount_rule") in ("full", "floor") else "full"}
    attempts = normalize_attempts(bands_ans.get("attempts"), first_ask, bands, problems)
    am = A.get("amounts") or {}
    products = {}
    for t in en["product_types"]:
        p = (am.get("products") or {}).get(t) or {}
        ff = p.get("floor_field") if p.get("floor_field") in en["product_fields"] else None
        phrase = _s(p.get("phrase")) or t.replace("_", " ")
        phrase = re.sub(r"\{(\w+)\}", lambda m: m.group(0) if m.group(1) in en["product_fields"] else "", phrase).strip()
        products[t] = {"phrase": phrase, "floor_field": ff}
    oc = A.get("outcomes") or {}
    outcomes = {}
    for s in schema.SITUATIONS:
        v = oc.get(s)
        if isinstance(v, list) and len(v) == 2 and v[0] in en["outcomes"]:
            outcomes[s] = [v[0], _s(v[1]) if isinstance(v[1], str) else None]
    tp = A.get("third_party") or {}
    cb_days = [d for d in (tp.get("callback_days") or ["today", "next_business_day"]) if d in ("today", "tomorrow", "next_business_day")]
    cb = {"days": cb_days or ["today", "next_business_day"],
          "start": tp.get("callback_start") if re.match(r"^\d{2}:\d{2}$", str(tp.get("callback_start"))) else "09:00",
          "end": tp.get("callback_end") if re.match(r"^\d{2}:\d{2}$", str(tp.get("callback_end"))) else "17:00",
          "after_now": tp.get("after_now") is not False, "max_asks": int(tp.get("max_asks") or 2)}
    window = " or ".join({"today": "today", "tomorrow": "tomorrow", "next_business_day": "on the next business day"}[d] for d in cb["days"])
    lines["callback_window"] = lines["callback_window"].replace("{window}", "%s, between %s and %s" % (window, cb["start"], cb["end"]))
    it = A.get("interrupts") or {}
    queues = {"restructuring": it.get("restructuring_queue") if it.get("restructuring_queue") in en["queues"] else None,
              "human": it.get("human_queue") if it.get("human_queue") in en["queues"] else None,
              "support": it.get("support_queue") if it.get("support_queue") in en["queues"] else None}
    prec = [p for p in (it.get("precedence") or []) if p in ("hardship", "dispute", "already_paid", "restructuring", "human")]
    for p in ("hardship", "dispute", "already_paid", "restructuring", "human"):
        if p not in prec:
            prec.append(p)
    interrupts = {"hardship": _s(it.get("hardship")), "dispute": _s(it.get("dispute")), "already_paid": _s(it.get("already_paid")),
                  "restructuring": _s(it.get("restructuring")), "human": _s(it.get("human")), "precedence": prec}
    mu = A.get("multi") or {}
    notes_on = bool(mu.get("notes_enabled"))
    nr = dict((k, v) for k, v in (mu.get("note_reasons") or {}).items() if v in en["note_reasons"]) if notes_on else {}
    for line_k in list(lines):
        lines[line_k] = lines[line_k].replace("{bank}", bank)
    policy = {
        "version": 1, "bank": bank, "address": "{title} {last_name}", "lines": lines,
        "person": {"max_asks": 2},
        "identity": {"questions": qs, "max_wrong": int(idn.get("max_wrong") or 3),
                     "swap_hint": idn.get("swap_hint") if idn.get("swap_hint") in (en["hints"] or []) else None,
                     "explain_once": True, "decline_after": int(idn.get("decline_after") or 2)},
        "calendar": {"weekend": weekend, "holidays": holidays},
        "bands": bands, "products": products, "first_ask": first_ask, "attempts": attempts,
        "amounts": {"never_ask_how_much": am.get("never_ask_how_much") is not False},
        "dates": {"next_weekday": cal.get("next_weekday") if cal.get("next_weekday") in ("following_week", "next_occurrence") else "following_week",
                  "this_weekday": cal.get("this_weekday") if cal.get("this_weekday") in ("current_week", "next_occurrence") else "current_week",
                  "numeric_order": cal.get("numeric_order") if cal.get("numeric_order") in ("DMY", "MDY") else "DMY"},
        "callback": cb, "outcomes": outcomes, "queues": queues,
        "notes": {"enabled": notes_on, "reasons": nr, "on_transfer": bool(mu.get("notes_on_transfer"))},
        "multi": {"enabled": bool(mu.get("multi_enabled")), "ask_all_today": mu.get("ask_all_today") is not False,
                  "clamp_to_deadline": mu.get("clamp_to_deadline") is not False},
        "interrupts": interrupts,
        "currency_word": _s(am.get("currency_word")) or "dollars",
        "forbidden_before_identity": forb[:20],
        "rules_text": [],
    }
    return policy
