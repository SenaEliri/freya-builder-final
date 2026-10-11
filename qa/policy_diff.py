"""Compare an extracted policy with a golden one on the fields that decide behaviour (Phase 0 gate)."""
import json
import sys


def facts(p):
    f = {}
    f["identity.fields"] = [q["field"] for q in p["identity"]["questions"]]
    f["identity.kinds"] = [q["kind"] for q in p["identity"]["questions"]]
    f["identity.lengths"] = [q.get("length") for q in p["identity"]["questions"]]
    f["identity.max_wrong"] = p["identity"]["max_wrong"]
    f["identity.swap_hint"] = p["identity"].get("swap_hint")
    f["calendar.weekend"] = sorted(p["calendar"]["weekend"])
    f["calendar.holidays"] = sorted(p["calendar"]["holidays"])
    f["bands"] = sorted((b["min"], b["max"], b["deadline_kind"], b["deadline_n"], b["attempts"]) for b in p["bands"])
    names = sorted(b["name"] for b in p["bands"])
    rng = dict((b["name"], "%d-%d" % (b["min"], b["max"])) for b in p["bands"])

    def bands_of(a):
        bs = sorted(a.get("bands") or [])
        # compared by days-late range, so the band names the model picked do not matter
        return None if (not bs or bs == names) else tuple(sorted(rng.get(b, b) for b in bs))
    f["first_ask"] = (p.get("first_ask") or {"date_rule": "today", "amount_rule": "full"}) and \
        ((p.get("first_ask") or {}).get("date_rule", "today"), (p.get("first_ask") or {}).get("amount_rule", "full"))
    f["attempts"] = sorted((a["n"], a["date_rule"], a["amount_rule"], bands_of(a)) for a in p["attempts"])
    f["products.floor"] = dict((t, v.get("floor_field")) for t, v in p["products"].items())
    f["products.types"] = sorted(p["products"])
    f["outcomes"] = dict((k, tuple(v)) for k, v in p["outcomes"].items())
    f["queues"] = p["queues"]
    cbd = sorted(p["callback"]["days"])
    f["callback"] = (cbd, p["callback"]["start"], p["callback"]["end"],
                     p["callback"].get("after_now") if "today" in cbd else None)
    f["notes.enabled"] = p["notes"]["enabled"]
    f["notes.reasons"] = p["notes"].get("reasons") if p["notes"]["enabled"] else {}
    f["multi.enabled"] = p["multi"]["enabled"]
    f["dates"] = (p.get("dates") or {}).get("next_weekday"), (p.get("dates") or {}).get("this_weekday")
    f["precedence.first"] = (p.get("interrupts") or {}).get("precedence", [None])[0]
    return f


def diff(got, gold):
    a, b = facts(got), facts(gold)
    return [(k, a.get(k), b.get(k)) for k in b if a.get(k) != b.get(k)]


def required_phrases(policy, phrases):
    text = " ".join(policy["lines"].values())
    return [p for p in phrases if p not in text]


if __name__ == "__main__":
    got, gold = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
    for k, a, b in diff(got, gold):
        print("DIFF", k, "\n   got: ", a, "\n   want:", b)
