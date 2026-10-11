"""Suite B: play the official example scenarios against the built phone agent (chat API, deployed mock) and check
the stored call: tool calls, their arguments and order, consent before side effects, what was said, how it ended.

    python3 -m qa.scenarios [workflow.json from the builder] [--only EX2]

A scripted caller is rigid, so the checks are invariants of the trace, not a turn-by-turn script. Nothing here
changes the agent. Results go to tests/reports/scenario-results.md and tests/reports/scenario-evidence.json.
"""
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import platform as P  # noqa: E402

ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
DIGITS = ["sıfır"] + ONES[1:]


def tr_words(n):
    n = int(n)
    if n == 0:
        return "sıfır"
    out = []
    for size, name in ((1000000, "milyon"), (1000, "bin"), (1, "")):
        part, n = divmod(n, size)
        if not part:
            continue
        h, r = divmod(part, 100)
        w = ([] if h == 0 else (["yüz"] if h == 1 else [ONES[h], "yüz"])) + [x for x in (TENS[r // 10], ONES[r % 10]) if x]
        if size == 1000 and part == 1:
            w = []
        out += w + ([name] if name else [])
    return " ".join(out)


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower().replace(chr(775), ""))).strip()


def _has(said, pattern):
    return re.search(r"(?<!\w)%s(?!\w)" % pattern, said) is not None


def assert_amount(said, a):
    """The amount as digits (12000, 12.000, 12 bin) or as Turkish words; decimals as ',20' or as a second number."""
    whole, cents = int(a), int(round((a - int(a)) * 100))
    digits = [str(whole), "{:,}".format(whole).replace(",", " ")]
    if whole >= 1000:
        digits.append(("%d bin %d" % divmod(whole, 1000)) if whole % 1000 else "%d bin" % (whole // 1000))
    wholes = [re.escape(d) for d in digits] + [re.escape(norm(tr_words(whole)))]
    if not cents:
        return any(_has(said, w) for w in wholes)
    tails = ["%02d" % cents, str(cents), re.escape(norm(tr_words(cents)))]
    return any(_has(said, w + r" (?:\w+ ){0,3}?" + t) for w in wholes for t in tails)


def assert_date(said, ddmmyyyy):
    d, m, _ = ddmmyyyy.split(".")
    month = norm(MONTHS[int(m) - 1])
    return any(_has(said, re.escape(x) + " " + month) for x in (str(int(d)), norm(tr_words(int(d)))))


def card_prefix_leaks(agent_texts, card):
    """Anything beyond the last four: the first six as digits or as spoken digits, or a run of five or more digits."""
    first6, text = card[:6], " ".join(agent_texts)
    leaks = []
    if first6 in re.sub(r"[\s.\-]", "", text):
        leaks.append("first six digits as digits")
    if norm(" ".join(DIGITS[int(c)] for c in first6)) in norm(text):
        leaks.append("first six digits spoken")
    spoken = norm(text).split()
    run = 0
    for w in spoken:
        run = run + 1 if w in DIGITS else 0
        if run >= 5:
            leaks.append("five or more digits spoken in a row")
            break
    if re.search(r"\d{5,}", text):
        leaks.append("digit run %s" % re.search(r"\d{5,}", text).group(0))
    return leaks


def timeline(call):
    """[{kind: user|agent|tool|node, ...}] in order; tool rows carry name, data (request data), ok, error."""
    rows, pending = [], None
    for e in P.events(call):
        ev = e.get("event") or {}
        if e.get("text") is not None and e.get("role") in ("user", "assistant"):
            rows.append({"kind": "user" if e["role"] == "user" else "agent", "text": e["text"]})
        elif ev.get("event") == "function_call_start" and ev.get("function") != "code_exec":
            body = (ev.get("args") or {}).get("body")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except Exception:
                    body = {}
            pending = {"kind": "tool", "name": ev.get("function"), "data": body.get("data") if isinstance(body, dict) else None,
                       "ok": None, "error": ""}
            rows.append(pending)
        elif ev.get("event") in ("function_call_complete", "function_call_complete_deferred") and pending is not None \
                and ev.get("function") == pending["name"]:
            pending["ok"] = True
        elif ev.get("event") == "function_call_error" and pending is not None:
            pending["ok"], pending["error"] = False, str(ev.get("error"))[-200:]
        elif ev.get("event") == "node_enter":
            rows.append({"kind": "node", "name": ev.get("node")})
    return rows


def _safe_timeline(cid):
    try:
        return timeline(P.get_call(cid))
    except Exception:
        return []


def play(workflow_id, sc):
    """Scripted caller. An utterance is a string, or a dict: say `say` up to `max` times until `repeat_until_tool`
    has run; with `when_agent_asks`, say `say` once the agent's last message contains that text, else `fallback_say`."""
    r = P.freya.api("POST", "/api/v2/chat/message", {"workflowId": workflow_id, "message": sc["utterances"][0],
                                                     "customerVariables": {"customerNumber": sc["customerNumber"], "now": sc["now"]}})
    cid, last, ended = r["callId"], r.get("response") or "", False
    for u in sc["utterances"][1:]:
        n, limit = 0, (1 if isinstance(u, str) else u.get("max", 3))
        while not ended and n < limit:
            say = u if isinstance(u, str) else u["say"]
            if not isinstance(u, str):
                if u.get("repeat_until_tool") and any(x["kind"] == "tool" and x["name"] == u["repeat_until_tool"] and x["ok"] for x in _safe_timeline(cid)):
                    break
                if u.get("when_agent_asks"):
                    if u["when_agent_asks"] in norm(last):
                        limit = n + 1
                    else:
                        say = u["fallback_say"]
            n += 1
            try:
                r = P.freya.api("POST", "/api/v2/chat/message", {"workflowId": workflow_id, "message": say, "callId": cid})
                last = r.get("response") or ""
            except Exception:  # the chat route answers 502 when the agent ends the call inside the turn
                ended = True
            if any(x["kind"] == "tool" and x["name"] == "end_call" for x in _safe_timeline(cid)):
                ended = True
    P.chat_end(cid)
    time.sleep(1)
    return P.get_call(cid)


def check(sc, call):
    x, tl, res = sc["expect"], timeline(call), []

    def add(name, ok, detail=""):
        res.append({"assertion": name, "ok": bool(ok), "detail": detail})

    tools = [r for r in tl if r["kind"] == "tool" and r["name"] != "end_call"]
    done = [r for r in tools if r["ok"]]
    agent = [r["text"] for r in tl if r["kind"] == "agent"]
    said = norm(" ".join(agent))
    names = [r["name"] for r in done]
    for t in x.get("required_tools", []):
        add("assertToolCalled(%s)" % t, t in names)
    for t in x.get("forbidden_tools", []):
        add("assertToolNotCalled(%s)" % t, t not in names)
    for a, b in x.get("order", []):
        add("assertCallOrdering(%s before %s)" % (a, b), a in names and b in names and names.index(a) < names.index(b))
    for t, want in (x.get("tool_args") or {}).items():
        got = next((r["data"] for r in done if r["name"] == t), None) or {}
        bad = {k: got.get(k) for k, v in want.items() if str(got.get(k)) != str(v)}
        add("assertToolCallArguments(%s)" % t, t in names and not bad, ("sent " + json.dumps(bad, ensure_ascii=False)) if bad else "")
    cust = [r for r in done if (r["data"] or {}).get("customerNo") is not None]
    add("assertNoOtherCustomerAccess", bool(cust) and all(str(r["data"]["customerNo"]) == sc["customerNumber"] for r in cust))
    if x.get("balance_cards") is not None:
        got = sorted(set(str((r["data"] or {}).get("cardNumber")) for r in done if r["name"] == "cards_balance"))
        add("cards.balance only for the expected card", got == sorted(x["balance_cards"]) or (not got and "cards_balance" not in x.get("required_tools", [])), str(got))
    if x.get("only_cards"):
        used = sorted(set(str(r["data"]["cardNumber"]) for r in done if (r["data"] or {}).get("cardNumber")))
        add("no service call for any other card", all(c in x["only_cards"] for c in used), str(used))
    se = x.get("side_effect")
    if se:
        idx = [i for i, r in enumerate(tl) if r["kind"] == "tool" and r["name"] == se["tool"] and r["ok"]]
        add("assertToolCallCount(%s == %d)" % (se["tool"], se["count"]), len(idx) == se["count"], "count %d" % len(idx))
        prev = [i for i, r in enumerate(tl) if r["kind"] == "tool" and r["name"] == se["needs_user_turn_after"] and r["ok"] and (not idx or i < idx[0])]
        between = tl[prev[-1]:idx[0]] if idx and prev else []
        add("assertNoSideEffectBeforeConfirmation(%s)" % se["tool"],
            any(r["kind"] == "agent" for r in between) and any(r["kind"] == "user" for r in between),
            "needs the agent to speak and the caller to answer between %s and %s" % (se["needs_user_turn_after"], se["tool"]))
        if se.get("not_after_user_text") and idx:
            users = [r["text"] for r in tl[:idx[0]] if r["kind"] == "user"]
            add("change not made on a hedged answer", norm(se["not_after_user_text"]) not in norm(users[-1]), "caller's last words before it: %r" % users[-1])
        refused = [r for r in tools if r["name"] == se["tool"] and not r["ok"] and "NOT ALLOWED YET" in r["error"]]
        if refused:
            add("(info) the consent guard refused %d early call(s)" % len(refused), True)
    first_bal = next((i for i, r in enumerate(tl) if r["kind"] == "tool" and r["name"] == "cards_balance"), None)
    if x.get("no_balance_before_user_turn"):
        before = sum(1 for r in tl[:first_bal] if r["kind"] == "user") if first_bal is not None else 0
        add("no balance read before the caller chose a card", first_bal is not None and before >= x["no_balance_before_user_turn"], "caller turns before the first balance: %d" % before)
    if x.get("min_user_turns_before_end"):
        end = next((i for i, r in enumerate(tl) if r["kind"] == "tool" and r["name"] == "end_call"), len(tl))
        add("call not ended on the repeated request", sum(1 for r in tl[:end] if r["kind"] == "user") >= x["min_user_turns_before_end"])
    if x.get("no_card_question"):
        add("no card selection question", "hangi kart" not in norm(agent[0] if agent else ""))
    for a in x.get("amounts", []):
        add("assertExactReturnedAmounts(%s)" % a, assert_amount(said, a))
    for d in x.get("dates", []):
        add("assertExpectedDateMentioned(%s)" % d, assert_date(said, d))
    if x.get("last4"):
        add("card named by its last four digits", x["last4"] in said.replace(" ", "") or norm(" ".join(DIGITS[int(c)] for c in x["last4"])) in said)
    for m in x.get("must_say", []):
        add("says %r" % m, norm(m) in said)
    scope = norm(agent[0]) if x.get("must_not_say_scope") == "first_agent_message" and agent else said
    for m in x.get("must_not_say", []):
        add("does not say %r (%s)" % (m, x.get("must_not_say_scope", "whole call")), norm(m) not in scope)
    if x.get("card"):
        leaks = card_prefix_leaks(agent, x["card"])
        add("assertNoCardPrefixDisclosure", not leaks, "; ".join(leaks))
    ends = [r for r in tl if r["kind"] == "node" and str(r["name"]).startswith("end_")]
    dest = re.sub(r"^end_|_\d+$", "", ends[-1]["name"]) if ends else ""
    if x.get("disposition"):
        add("assertCorrectHandoff(%s)" % x["disposition"], dest == x["disposition"], "ended in %r" % (dest or "no closing step"))
    else:
        add("(info) call ended in %r" % (dest or "no closing step"), True)
    return res, tl


def main(argv):
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    files = [a for a in argv if a.endswith(".json")]
    sub = json.loads((ROOT / "submission.json").read_text())
    wf_file = files[0] if files else str(ROOT / sub["workflow"])
    wid = json.loads(pathlib.Path(wf_file).read_text())["workflow_id"]
    spec = json.loads((ROOT / "tests" / "scenarios" / "official-examples.json").read_text())
    out = []
    for sc in spec["scenarios"]:
        if only and sc["id"] != only:
            continue
        o = {"id": sc["id"], "category": sc["category"], "title": sc["title"], "assertions": [], "timeline": []}
        try:
            call = play(wid, sc)
            o["assertions"], o["timeline"] = check(sc, call)
            o["call_id"] = call.get("id")
            o["status"] = "PASS" if all(r["ok"] for r in o["assertions"]) else "FAIL"
        except Exception as e:
            o["status"], o["error"] = "ERROR", "%s: %s" % (type(e).__name__, str(e)[:300])
        out.append(o)
        print(o["id"], o["status"], "| failed:", [a["assertion"] + (" [" + a["detail"] + "]" if a["detail"] else "") for a in o["assertions"] if not a["ok"]] or o.get("error", ""), flush=True)
    rep = ROOT / "tests" / "reports"
    rep.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M %z")
    name = pathlib.Path(wf_file).resolve()
    shown = str(name.relative_to(ROOT)) if str(name).startswith(str(ROOT)) else str(name)
    (rep / "scenario-evidence.json").write_text(json.dumps({"run_at": stamp, "workflow_file": shown, "workflow_id": wid, "results": out}, ensure_ascii=False, indent=1))
    lines = ["# Official example scenarios: results", "",
             "Run at %s against workflow `%s` (file `%s`), the agent exactly as the builder exported it, with the deployed mock." % (stamp, wid, shown),
             "A scripted caller talks to the agent over the chat API. Every assertion is checked on the stored call: tool calls,",
             "their arguments and order, and the transcript. Evidence: `tests/reports/scenario-evidence.json`.",
             "Definitions: `tests/scenarios/official-examples.json`.", "",
             "| Scenario | Category | Status | Assertions passed | Failed assertions |", "|---|---|---|---|---|"]
    for o in out:
        bad = [a["assertion"] + (" (" + a["detail"] + ")" if a["detail"] else "") for a in o["assertions"] if not a["ok"]]
        lines.append("| %s %s | %s | **%s** | %d/%d | %s |" % (o["id"], o["title"], o["category"], o["status"], sum(a["ok"] for a in o["assertions"]),
                                                              len(o["assertions"]), "; ".join(bad) or o.get("error", "") or "none"))
    lines += ["", "Passed: %d of %d." % (sum(o["status"] == "PASS" for o in out), len(out)), ""]
    for o in out:
        lines += ["## %s %s (%s)" % (o["id"], o["title"], o["status"]), ""]
        for r in o["timeline"]:
            if r["kind"] in ("user", "agent"):
                lines.append("- **%s:** %s" % ("Caller" if r["kind"] == "user" else "Agent", r["text"].replace("\n", " ")))
            elif r["kind"] == "tool":
                lines.append("  - `%s` %s %s" % (r["name"], json.dumps(r["data"], ensure_ascii=False) if r["data"] else "",
                                                 "ok" if r["ok"] else "REFUSED/FAILED: " + r["error"][-120:].replace("\n", " ")))
        lines.append("")
    (rep / "scenario-results.md").write_text("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
