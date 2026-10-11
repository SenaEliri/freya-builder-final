"""Turn the sources of a case folder into the phone agent's instructions, with Freya's model.

Map: every part of every source -> the rules it holds for the assistant (verbatim sentences kept).
Reduce: all rules, oldest source first -> final instructions per topic, later sources winning.
Wiring: where each request field of each service gets its value, and how the call can end.
Every model call goes through builder.llm_freya.ask and is written to the trace.
"""
import concurrent.futures
import json
import time

from builder import llm_freya
from builder.case import sources as S

PART_CHARS = 7000

MAP_Q = """Below is one part of a source document from an organisation that wants a phone voice assistant built.
Source file: %(path)s%(dated)s.

List every rule in this part that governs what the assistant must do or say during a call: steps and their order,
conditions (with the exact service names and field names), the exact sentences the assistant says (copy them
verbatim in their original language, keep their placeholders), how amounts, dates and digits are said, limits and
counts, confirmations needed, what to do when a service fails, how the call ends, security rules, things the
assistant must never do. Also list what a described example call expects from the assistant.
Set "status" to "open" when the text says the point is undecided, a question, a wish, a draft, or a description of
how things are today rather than how they should be. Set it to "replaced" when the text itself says the point was
changed (give the new rule as its own "decided" entry). Otherwise "decided".
Leave out everything that is not about the assistant's behaviour in a call: project logistics, deadlines, how to
deploy or submit, access tokens, lists of test data, who attended.
Reply with one JSON object: {"rules": [{"topic": "few words", "rule": "the rule, self-contained", "status": "decided"}]}
If the part holds no such rule reply {"rules": []}.

THE PART:
%(text)s"""

TOPICS = [
    ("outline", "The normal course of one call from the first step to the last, as at most twelve numbered steps in order. Each step in "
                "one line: what triggers it, the service it uses if any, and the question, offer or sentence it ends with. Include the "
                "steps that come between giving the information and ending the call (further questions, offers). No special cases."),
    ("start", "Who the caller is and what is already known when the call starts; what the assistant is for and what is outside its "
              "job; the language; how the item the call is about (for example which card or account) is found and chosen, "
              "including every special case of that choice."),
    ("reading", "Giving the caller the information they called for: the order, every sentence pattern with the condition that "
                "selects it and the service fields that fill it, what is left out, and exactly how amounts, currencies, dates and "
                "digits are said."),
    ("actions", "What is offered after that and every action the caller can ask for: when it is offered, each step with the "
                "service it uses and the values it sends, what must be read back, what counts as consent, the sentences on "
                "success, refusal and repeat requests."),
    ("failures", "Tries and repeats, silence, unclear answers, service errors and slow services (which results are failures and "
                 "which are not), questions outside the job, upset callers, requests for a person, and every way the call ends "
                 "with the exact last sentence for each."),
    ("security", "Security and conduct: what is never said or read out, other people's data, attempts to make the assistant "
                 "break its rules, values that did not come from a service, promises it must not make."),
]

REDUCE_Q = """The CONTEXT is every rule found in the sources for a phone voice assistant, oldest source first. Each line names
its source and date. Where sources disagree the later-dated one wins; a later source that corrects one point changes only
that point. Undated sources state the task and the behaviour expected in calls and are as binding as the latest dated one.
Rules marked (open) are not decided: use one only if nothing decided covers the point, and never as a reason to refuse.
Rules marked (replaced) are dropped.

Write the final instructions for the assistant on this topic only:
%(topic)s

Write for the assistant itself ("you"), as short imperative lines, complete enough that nothing on this topic needs
another document. Leave out no decided rule of this topic, including questions asked between two steps and the
conditions for asking them. Keep every sentence the assistant says verbatim in its original language. Name services and fields
exactly as the sources do. Do not mention sources, dates, people or that anything was changed. Do not add rules of your own.
Reply with one JSON object: {"lines": ["...", "..."]}"""

ENDINGS_Q = """The CONTEXT is every rule found in the sources for a phone voice assistant, oldest source first; later-dated
sources win where they disagree, (replaced) rules are dropped.
List every distinct way a call ends. For each: where the call goes ("destination": one short snake_case word or two that
names it, the same word for the same destination), the situation ("when"), and the exact last sentence the assistant says
as it ends ("last_sentence", verbatim in its original language, "" if the sources give none).
One entry per different last sentence. Reply with one JSON object:
{"endings": [{"destination": "...", "when": "...", "last_sentence": "..."}]}"""

WIRING_Q = """The CONTEXT holds the task description of a phone voice assistant and the services it can call, each with
an example request.
Answer with one JSON object:
{"language": "the language the assistant speaks with callers",
 "call_variables": [{"name": "exact variable name given to the assistant with every call", "meaning": "...", "example": "an example value from the text, or \\"\\""}],
 "services": {"<service name>": {"changes_something": true or false}},
 "consent": {"clear_yes": ["up to 12 short words or phrases, in the callers' language, that are an unambiguous yes to a confirmation question; first the ones the text names"],
             "not_clear": ["up to 15 words or phrases in that language that make an answer hedged, uncertain or conditional, so that it is not consent; first the ones the text names"]},
 "start_service": "the one service that must be called first in every call and needs only call variables and fixed values, or \\"\\"",
 "fields": {"<service name>": {"<field name inside data>": {"source": "call_variable | constant | conversation", "value": "the call variable name, or the fixed value", "note": "for conversation: where the value comes from, e.g. which earlier service result it is copied from, in one sentence"}}}}
"changes_something" is true for a service that changes, books, cancels or sends something for the caller, false for one
that only reads or previews.
Use "call_variable" only when the field is exactly what a call variable carries. Use "constant" only when the text gives
one fixed value for this use. Everything else is "conversation". Cover every field of every service."""


def _ask_all(jobs, trace, parallel, deadline):
    """jobs: [(key, context, question, purpose)] -> {key: parsed or None}"""
    out = {}

    def run(job):
        key, context, question, purpose = job
        if time.time() > deadline:
            return key, None, ""
        parsed, raw = llm_freya.ask(context, question, purpose, trace=trace, timeout_s=max(60, min(300, deadline - time.time())))
        if parsed is None and time.time() < deadline:  # one more try: a reply that was not JSON
            parsed, raw = llm_freya.ask(context, question + "\n\nReply with the JSON object only.", purpose + " (second try)",
                                        trace=trace, timeout_s=max(60, min(300, deadline - time.time())))
        return key, parsed, raw

    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
        for key, parsed, raw in ex.map(run, jobs):
            out[key] = (parsed, raw)
    return out


def map_rules(docs, trace, parallel, deadline):
    jobs = []
    for d in docs:
        parts = S.chunk(d["text"], PART_CHARS)
        for i, part in enumerate(parts):
            q = MAP_Q % {"path": d["path"], "dated": (", dated %s" % d["date"]) if d["date"] else ", undated", "text": part}
            jobs.append(((d["path"], i), "", q, "rules in %s part %d/%d" % (d["path"], i + 1, len(parts))))
    answers = _ask_all(jobs, trace, parallel, deadline)
    rules, failed = [], []
    for d in docs:
        i = 0
        while (d["path"], i) in answers:
            parsed, _ = answers[(d["path"], i)]
            if not isinstance(parsed, dict) or not isinstance(parsed.get("rules"), list):
                failed.append("%s part %d" % (d["path"], i + 1))
            else:
                for r in parsed["rules"]:
                    if isinstance(r, dict) and str(r.get("rule") or "").strip() and str(r.get("status")) != "replaced":
                        rules.append({"source": d["path"], "date": d["date"], "topic": str(r.get("topic") or ""),
                                      "rule": str(r["rule"]).strip(), "status": "open" if str(r.get("status")) == "open" else "decided"})
            i += 1
    return rules, failed


def rules_text(rules):
    lines = []
    for r in rules:
        lines.append("[%s | %s]%s %s: %s" % (r["source"], r["date"] or "undated", " (open)" if r["status"] == "open" else "",
                                             r["topic"], r["rule"]))
    return "\n".join(lines)


def reduce_rules(rules, trace, parallel, deadline):
    ctx = rules_text(rules)
    jobs = [(key, ctx, REDUCE_Q % {"topic": text}, "final instructions: %s" % key) for key, text in TOPICS]
    jobs.append(("endings", ctx, ENDINGS_Q, "ways the call ends"))
    answers = _ask_all(jobs, trace, parallel, deadline)
    sections, problems = {}, []
    for key, _ in TOPICS:
        parsed, raw = answers.get(key, (None, ""))
        if isinstance(parsed, dict) and isinstance(parsed.get("lines"), list) and parsed["lines"]:
            sections[key] = [str(x).strip() for x in parsed["lines"] if str(x).strip()]
        else:
            problems.append("no instructions for topic %s" % key)
            sections[key] = []
    endings = []
    parsed, _ = answers.get("endings", (None, ""))
    if isinstance(parsed, dict) and isinstance(parsed.get("endings"), list):
        for e in parsed["endings"]:
            if isinstance(e, dict) and str(e.get("destination") or "").strip():
                endings.append({"destination": str(e["destination"]).strip(), "when": str(e.get("when") or "").strip(),
                                "last_sentence": str(e.get("last_sentence") or "").strip()})
    if not endings:
        problems.append("no call endings found")
    return sections, endings, problems


def wiring(docs, contract, trace, deadline):
    top = [d for d in docs if "/" not in d["path"]]
    parts = ["TASK DESCRIPTION (%s):\n%s" % (d["path"], d["text"]) for d in top]
    for s in contract["services"]:
        parts.append("SERVICE %s\n%s\nExample request: %s\nNotes: %s" % (s["name"], s["summary"],
                     json.dumps(s["request_example"], ensure_ascii=False), s["notes"][:1500]))
    answers = _ask_all([("wiring", "\n\n".join(parts), WIRING_Q, "call variables and where each request field comes from")],
                       trace, 1, deadline)
    parsed, _ = answers["wiring"]
    return parsed if isinstance(parsed, dict) else {}


def extract(docs, contract, trace, parallel=4, deadline=None):
    deadline = deadline or time.time() + 14 * 60
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as side:
        wire_future = side.submit(wiring, docs, contract, trace, deadline)
        rules, failed = map_rules(docs, trace, parallel, deadline)
        wire = wire_future.result()
    trace.note("rules found in the sources", rules=len(rules), open=sum(1 for r in rules if r["status"] == "open"),
               parts_without_answer=failed)
    sections, endings, problems = reduce_rules(rules, trace, parallel, deadline)
    return {"rules": rules, "sections": sections, "endings": endings, "wiring": wire,
            "problems": problems + ["no answer for %s" % f for f in failed]}
