"""Per-turn "decide" step of the phone agent. Runs inside ONE Freya code node per customer turn.

Contract with the workflow (see builder/emit/workflow.py):
  inputs  (extraction, this turn): utterance, reply, intent, topic, pay_date, pay_amount
  inputs  (bank results, engine-run api_request nodes): verify_*, account_*, wp*/wn*/xfer*/cb* response vars
  state   : vars['rb_state'] (JSON string, owned by this code only)
  outputs : say, route, farewell, final_outcome, final_reason, v_field, v_answer, say_v_*,
            wp{k}_*, wn{k}_*, say_wp{k}_ok/_fail, say_after_fail, xfer_queue, cb_date, cb_time

Rules this file enforces (rebuild LESSONS):
  L1  only write-result lines (precomputed here, spoken after the write succeeded) mention recording
  L2  repeated lines are detected; caps lead to an honest ending; nothing waits for a reply after goodbye
  L3  extracted values are consumed once and cleared; a value not found in this turn's utterance is ignored
  L4  dates are resolved here against `now` (never the real clock); missing/past/ambiguous -> ask
  L5  the read-back is rendered from ONE snapshot; writes use exactly that snapshot; a yes counts only
      right after the read-back
  L6  required sentences are fixed lines from the policy
  L7  partial identity answers are assembled across turns; a technical failure is never a wrong answer
  L8  every turn checks interrupts (hardship, dispute, paid, restructuring, human, questions) first
Stdlib only (json, re, datetime). The source must never contain two consecutive braces.
"""
import datetime
import json
import re

RUNTIME_VERSION = "rb-1"
MAX_TURNS = 45
NULL_REASON = ""

# ---------------------------------------------------------------- text and numbers

UNITS = {"zero": 0, "oh": 0, "o": 0, "nil": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90}
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
       "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
       "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
       "twentieth": 20, "thirtieth": 30}
MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
          "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
          "sep": 9, "sept": 9, "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5,
            "sat": 5, "sunday": 6, "sun": 6}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def norm(s):
    s = (s or "").lower().replace("’", "'").replace("-", " ")
    s = re.sub(r"[^a-z0-9.,:/' $]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s):
    """Lower-case word and number tokens; '23rd' -> '23rd', '1,250.50' -> '1250.50'."""
    s = norm(s)
    s = re.sub(r"(\d),(\d{3})", r"\1\2", s)
    return re.findall(r"\d+(?:\.\d+)?(?:st|nd|rd|th)?|[a-z]+(?:'[a-z]+)?", s)


def _cls(w):
    if w in UNITS:
        v = UNITS[w]
        return ("unit" if v < 10 else "teen"), v
    if w in TENS:
        return "tens", TENS[w]
    if w in ORD:
        return "ord", ORD[w]
    return None, None


def word_number(toks, i):
    """Parse one cardinal/ordinal number written in words starting at toks[i].
    Returns (value, next_index, is_ordinal) or None.

    A small grammar, so that adjacent numbers stay apart: 'twenty eight nineteen ninety three' is 28 then 1993's
    words, not one sum. 'four hundred and fifty five' = 455, 'two thousand and one' = 2001, 'thirty first' = 31."""
    total, cur, j, last = 0, 0, i, None
    while j < len(toks):
        w = toks[j]
        c, v = _cls(w)
        if w == "a" and j + 1 < len(toks) and toks[j + 1] in ("hundred", "thousand") and last is None:
            cur, last, j = 1, "unit", j + 1
            continue
        if c == "unit":
            if last not in (None, "tens", "hundred", "thousand", "and"):
                break
            if w in ("o", "oh", "nil") and last is not None:
                break
            cur += v
            last = "unit"
        elif c == "teen":
            if last not in (None, "hundred", "thousand", "and"):
                break
            cur += v
            last = "teen"
        elif c == "tens":
            if last not in (None, "hundred", "thousand", "and"):
                break
            cur += v
            last = "tens"
        elif c == "ord":
            if v >= 20 and last not in (None, "hundred", "thousand", "and"):
                break
            if v < 20 and last not in (None, "tens", "hundred", "thousand", "and"):
                break
            return total + cur + v, j + 1, True
        elif w == "hundred" and last in ("unit", "teen"):
            cur = max(cur, 1) * 100
            last = "hundred"
        elif w == "thousand" and last in ("unit", "teen", "tens", "hundred"):
            total += max(cur, 1) * 1000
            cur = 0
            last = "thousand"
        elif w == "and" and last in ("hundred", "thousand") and j + 1 < len(toks) and _cls(toks[j + 1])[0] is not None:
            last = "and"
        else:
            break
        j += 1
    if last is None or last == "and":
        return None
    return total + cur, j, False


def year_words(toks, i):
    """'nineteen eighty eight' -> 1988, 'two thousand and one' -> 2001, 'twenty twenty six' -> 2026,
    'nineteen oh five' -> 1905. 'twenty eight' is the number 28, not a year."""
    if i >= len(toks):
        return None
    t = toks[i]
    if re.match(r"^\d{4}$", t):
        return int(t), i + 1
    digs, j = [], i  # digit by digit: 'one nine eight eight', '1 9 8 8'
    while j < len(toks) and len(digs) < 4:
        w = toks[j]
        if re.match(r"^\d$", w):
            digs.append(w)
        elif w in UNITS and UNITS[w] < 10:
            digs.append(str(UNITS[w]))
        else:
            break
        j += 1
    if len(digs) == 4 and 1900 <= int("".join(digs)) <= 2100:
        return int("".join(digs)), j
    if t in ("nineteen", "twenty") and i + 1 < len(toks):
        hi = UNITS.get(t) or TENS.get(t)
        nxt = toks[i + 1]
        if nxt in ("oh", "o", "zero") and i + 2 < len(toks):
            c, v = _cls(toks[i + 2])
            if c == "unit" and v > 0:
                return hi * 100 + v, i + 3
            return None
        if nxt in ("hundred",):
            r = word_number(toks, i + 2) if i + 2 < len(toks) else None
            if r and not r[2] and r[0] < 100:
                return hi * 100 + r[0], r[1]
            return hi * 100, i + 2
        c, _ = _cls(nxt)
        if c in ("teen", "tens"):
            r = word_number(toks, i + 1)
            if r and not r[2] and 10 <= r[0] < 100:
                return hi * 100 + r[0], r[1]
        return None
    r = word_number(toks, i)
    if r and not r[2] and 1900 <= r[0] <= 2100:
        return r[0], r[1]
    return None


CUR_WORDS = ("dollars", "dollar", "euros", "euro", "pounds", "pound", "lira", "usd", "eur", "bucks")
CENT_WORDS = ("cents", "cent", "pence", "penny")
AMOUNT_WORDS = set(UNITS) | set(TENS) | set(CUR_WORDS) | set(CENT_WORDS) | {"hundred", "thousand", "and", "point", "a"}
CORRECTION = re.compile(r"\b(sorry|i mean|actually|no wait|rather|correction|make it)\b")


def amount_text(text):
    """Normalised amount words: '637,50' (decimal comma before exactly two digits) reads as 637.50."""
    return re.sub(r"(\d),(\d{2})(?!\d)", r"\1.\2", norm(text))


def _num_groups(toks):
    """Numbers in a token list, in order: dict(c=cents, i, j, dec=has cents, big=has hundreds)."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        m = re.match(r"^(\d+)(?:\.(\d+))?$", t)
        if m:
            c = int(m.group(1)) * 100 + (int((m.group(2) + "0")[:2]) if m.group(2) else 0)
            out.append({"c": c, "i": i, "j": i + 1, "dec": bool(m.group(2)), "big": int(m.group(1)) >= 100})
            i += 1
            continue
        r = word_number(toks, i)
        if r and not r[2]:
            g = {"c": r[0] * 100, "i": i, "j": r[1], "dec": False, "big": r[0] >= 100}
            if r[1] < len(toks) and toks[r[1]] == "point":  # 'six hundred point five'
                digits, k = "", r[1] + 1
                while k < len(toks) and (toks[k] in UNITS and UNITS[toks[k]] < 10 or re.match(r"^\d$", toks[k])):
                    digits += toks[k] if toks[k].isdigit() else str(UNITS[toks[k]])
                    k += 1
                if digits:
                    g.update(c=r[0] * 100 + int((digits + "0")[:2]), j=k, dec=True)
            out.append(g)
            i = g["j"]
            continue
        i += 1
    return out


def parse_amount(text):
    """Spoken amount -> dict(status, c, alts). Integer cents, never floats.

    status: ok (one clear reading), interp (one reading, said in an unusual way: the read-back shows it),
    ambiguous (alts holds the readings, e.g. 'twelve fifty' = 1250.00 or 12.50), incomplete (ends in 'and' /
    'point' / 'dollars and'), none. The LAST amount counts (corrections: '200, sorry, 250')."""
    t = amount_text(text)
    m = list(CORRECTION.finditer(t))
    if m and re.search(r"\d|" + "|".join(list(UNITS) + list(TENS)), t[m[-1].end():]):
        t = t[m[-1].end():]
    toks = tokens(t)
    if not toks:
        return {"status": "none"}
    gs = _num_groups(toks)
    if not gs:
        return {"status": "none"}
    tail = toks[gs[-1]["j"]:]
    if tail in (["and"], ["point"]) or tail[-2:] in ([w, "and"] for w in CUR_WORDS):
        return {"status": "incomplete", "c": gs[-1]["c"]}
    found, k = [], 0
    while k < len(gs):
        g = gs[k]
        res = {"status": "ok", "c": g["c"]}
        nx = gs[k + 1] if k + 1 < len(gs) else None
        if nx and not g["dec"] and not nx["dec"] and g["c"] % 100 == 0 and nx["c"] < 10000:
            between = toks[g["j"]:nx["i"]]
            after = toks[nx["j"]] if nx["j"] < len(toks) else ""
            cents_after = after in CENT_WORDS
            if after in MONTHS or after == "of":
                pass  # '100 dollars 30 October': a day, not cents
            elif (len(between) in (1, 2) and between[0] in CUR_WORDS and between[1:] in ([], ["and"])) or \
                    (between == ["and"] and cents_after) or (not between and cents_after):
                res = {"status": "ok", "c": g["c"] + nx["c"] // 100}  # '637 dollars and 50 (cents)'
                k += 1
            elif not between and nx["c"] >= 1000 and k + 2 < len(gs) and gs[k + 2]["i"] == nx["j"] and \
                    gs[k + 2]["c"] < 10000 and g["c"] < 1000 and not gs[k + 2]["dec"]:
                # 'six thirty-seven fifty' -> 637.50
                res = {"status": "interp", "c": g["c"] * 100 + nx["c"] + gs[k + 2]["c"] // 100}
                k += 2
            elif not between and nx["c"] >= 1000:
                if g["big"]:  # 'six hundred thirty-seven fifty' -> 637.50
                    res = {"status": "interp", "c": g["c"] + nx["c"] // 100}
                else:  # 'twelve fifty' -> 1250.00 or 12.50
                    res = {"status": "ambiguous", "c": g["c"] * 100 + nx["c"], "alts": [g["c"] * 100 + nx["c"], g["c"] + nx["c"] // 100]}
                k += 1
        found.append(res)
        k += 1
    out = found[-1]
    if out["c"] <= 0 and out["status"] == "ok":
        return {"status": "none"}  # 'zero' is not an offer
    if re.search(r"(\d),(\d{2})(?!\d)", norm(text)) and out["status"] == "ok":
        out["status"] = "interp"
    return out


def money_value(text):
    """Amount in digits or words -> float, or None (the first reading of an ambiguous amount)."""
    r = parse_amount(text)
    if r["status"] in ("none", "incomplete"):
        return None
    return r["c"] / 100.0


def cents(x):
    return int(round(float(x) * 100))


def amount_span(utt, phrase):
    """The whole amount around the extracted words in the customer's message. The extractor may copy only part of
    it ('six hundred and thirty-seven dollars' of '... dollars and fifty'), or a merged cut turn may hold the rest."""
    ut, pt = tokens(amount_text(utt)), tokens(amount_text(phrase))
    if not pt or not any(re.match(r"^\d", w) or w in UNITS or w in TENS for w in pt):
        return phrase
    pos = None
    for i in range(len(ut) - len(pt), -1, -1):
        if ut[i:i + len(pt)] == pt:
            pos = i
            break
    if pos is None:
        return phrase

    def amountish(w):
        return w in AMOUNT_WORDS or bool(re.match(r"^\d+(\.\d+)?$", w))
    i, j = pos, pos + len(pt)
    while j < len(ut) and amountish(ut[j]) and ut[j] != "a":
        j += 1
    while i > 0 and amountish(ut[i - 1]) and (ut[i - 1] != "a" or ut[i] in ("hundred", "thousand")):
        i -= 1
    while i < j and (ut[i] == "and" or ut[i] == "a" and (i + 1 >= j or ut[i + 1] not in ("hundred", "thousand"))):
        i += 1
    return " ".join(ut[i:j])


AMOUNT_REFS = (("floor", re.compile(r"\b(minimum|lowest|least|smallest|floor|instalment|installment)\b")),
               ("full", re.compile(r"\b(full|whole|entire|total|everything|all of it|the lot|past due|overdue|all)\b")),
               ("that", re.compile(r"^(that|it|this|that amount|this amount|the same|same amount|same|that much|"
                                   r"this much|what you said|the amount you said)$")))


def digit_string(text):
    """All digit runs spoken in the text, as a list of strings (each run = consecutive digits/words)."""
    toks = tokens(text)
    runs, cur = [], ""
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"^\d+$", t):
            cur += t
            i += 1
            continue
        if t in ("double", "triple") and i + 1 < len(toks) and toks[i + 1] in UNITS and UNITS[toks[i + 1]] < 10:
            cur += str(UNITS[toks[i + 1]]) * (2 if t == "double" else 3)
            i += 2
            continue
        if t in UNITS:
            cur += str(UNITS[t])
            i += 1
            continue
        if t in TENS:
            v = TENS[t]
            if i + 1 < len(toks) and toks[i + 1] in UNITS and 0 < UNITS[toks[i + 1]] < 10:
                v += UNITS[toks[i + 1]]
                i += 1
            cur += str(v)
            i += 1
            continue
        if cur:
            runs.append(cur)
            cur = ""
        i += 1
    if cur:
        runs.append(cur)
    return runs


def pick_digits(text, length):
    """Digits answer of a given length. Returns (value, partial) where partial is the digits so far."""
    t = norm(text)
    t = re.sub(r"\b(last|final)\s+(four|4|three|3|five|5|six|6|two|2)\s+(digits?|numbers?)\b", " ", t)
    t = re.sub(r"\b(four|4|three|3|five|5|six|6)\s+digits?\b", " ", t)
    runs = digit_string(t)
    if not runs:
        return None, ""
    for r in reversed(runs):
        if length and len(r) == length:
            return r, ""
    joined = "".join(runs)
    if length and len(joined) == length:
        return joined, ""
    if length and len(runs[-1]) > length:
        return runs[-1][-length:], ""
    if not length:
        return runs[-1], ""
    return None, joined


# ---------------------------------------------------------------- dates

def d_iso(d):
    return d.isoformat()


def d_from(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def is_business(d, cal):
    return d.weekday() not in cal.get("weekend", [5, 6]) and d_iso(d) not in cal.get("holidays", [])


def add_business(d, n, cal):
    k = 0
    while k < n:
        d += datetime.timedelta(days=1)
        if is_business(d, cal):
            k += 1
    return d


def next_business_on_or_after(d, cal):
    for _ in range(40):
        if is_business(d, cal):
            return d
        d += datetime.timedelta(days=1)
    return d


def last_business_of_week(d, cal):
    monday = d - datetime.timedelta(days=d.weekday())
    for i in range(6, -1, -1):
        x = monday + datetime.timedelta(days=i)
        if is_business(x, cal):
            return x
    return None


def date_for_rule(rule, today, deadline, cal):
    if rule == "today":
        return today
    if rule == "tomorrow":
        return today + datetime.timedelta(days=1)
    if rule == "next_business_day":
        return add_business(today, 1, cal)
    if rule == "deadline":
        return deadline
    if rule == "end_of_week":
        x = last_business_of_week(today, cal)
        if x is None or x <= today:
            x = last_business_of_week(today + datetime.timedelta(days=7), cal)
        return x
    m = re.match(r"^(business|calendar)_day_(\d{1,2})$", str(rule or ""))
    if m:
        n = int(m.group(2))
        if m.group(1) == "business":
            return add_business(today, n, cal)
        return next_business_on_or_after(today + datetime.timedelta(days=n), cal)
    return deadline


def spoken_date(d, today=None):
    s = "%s %d %s" % (DAY_NAMES[d.weekday()], d.day, MONTH_NAMES[d.month - 1])
    if today is not None and d.year != today.year:
        s += " %d" % d.year
    return s


VAGUE = re.compile(r"\b(next week|this week|the week after|week after next|end of (the |this |next )?month|"
                   r"beginning of (the |next )?month|start of (the |next )?month|next month|later this month|"
                   r"in a (few|couple of) (days|weeks)|in (two|2|three|3) weeks|soon|sometime|some time|"
                   r"when (my|i get my|i get) (salary|pay|paycheck|wages|money)|payday|pay day|when i get paid|"
                   r"when i can|later|after the weekend|over the weekend|at some point|in a week|"
                   r"(end|beginning|start|middle) of (the |this |next )?week|this weekend|the weekend|early next week|"
                   r"later this week|in (a|one|1) weeks?|in (a|one|1) months?|in (two|2|three|3) (days|months))\b")
NEG_DAY = re.compile(r"\b(not|n't|cannot|can't|cant|unable to|won't|wont|no way)\b[^.?!,;]{0,25}\b(today|tomorrow|tonight|now)\b|"
                     r"\b(today|tomorrow|tonight)\b[^.?!,;]{0,12}\b(is not|isn't|won't|doesn't|does not|is impossible|"
                     r"is too soon|no)\b")


BARE_FILLER = {"the", "on", "of", "day", "its", "it", "s", "um", "uh", "er", "yes", "okay", "ok", "so", "maybe"}


def parse_pay_date(text, today, cal, dates_cfg, month_hint=None):
    """Resolve a spoken payment date against `today`.
    Returns dict(status=ok|vague|none|past|ask, date=iso, asked=words, conflict=iso, month=n for 'in October').
    month_hint: the month named in the previous answer ('on October' ... 'Thirty.' -> 30 October)."""
    t = norm(text)
    if not t:
        return {"status": "none"}
    toks = tokens(t)
    core = [w for w in toks if w not in BARE_FILLER]
    if core and len(core) <= 2 and not any(w in MONTHS or w in WEEKDAYS for w in core):
        r = word_number(core, 0)
        m0 = re.match(r"^(\d{1,2})(st|nd|rd|th)?$", core[0])
        val = int(m0.group(1)) if m0 else (r[0] if r and r[1] == len(core) else None)
        if val is not None and 1 <= val <= 31 and (len(core) == 1 or r):
            # a bare day number answering 'which exact day?'
            d = _month_day(today, val, month_hint, None) if month_hint else _next_day_number(today, val)
            if d is None:
                return {"status": "ask"}
            return {"status": "ok", "date": d_iso(d)} if d >= today else {"status": "past", "date": d_iso(d)}
    cands = []
    # explicit corrections: keep only what follows the last correction marker
    m = list(re.finditer(r"\b(sorry|i mean|actually|no wait|rather|correction)\b", t))
    if m:
        tail = t[m[-1].end():]
        if re.search(r"\d|" + "|".join(list(MONTHS) + list(WEEKDAYS) + list(ORD) + ["today", "tomorrow"]), tail):
            t = tail
            toks = tokens(t)
    neg = NEG_DAY.search(t.replace("’", "'"))
    negated = set()
    if neg:
        for w in ("today", "tomorrow", "tonight", "now"):
            if w in neg.group(0):
                negated.add(w)
    if re.search(r"\b(today|tonight|this (morning|afternoon|evening)|right now|now)\b", t) and \
            not (negated & {"today", "tonight", "now"}):
        cands.append(("ok", today))
    if re.search(r"\bday after tomorrow\b", t):
        cands.append(("ok", today + datetime.timedelta(days=2)))
    elif re.search(r"\btomorrow\b", t) and "tomorrow" not in negated:
        cands.append(("ok", today + datetime.timedelta(days=1)))
    m = re.search(r"\bin (\w+) days?\b", t)
    if m:
        r = word_number([m.group(1)], 0)
        n = int(m.group(1)) if m.group(1).isdigit() else (r[0] if r else None)
        if n is not None:
            cands.append(("ok", today + datetime.timedelta(days=n)))
    # ISO and numeric dates
    for mm in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        try:
            cands.append(("ok", datetime.date(int(mm.group(1)), int(mm.group(2)), int(mm.group(3)))))
        except ValueError:
            pass
    for mm in re.finditer(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t):
        a, b = int(mm.group(1)), int(mm.group(2))
        day, mon = (b, a) if dates_cfg.get("numeric_order") == "MDY" else (a, b)
        y = mm.group(3)
        yr = int(y) + (2000 if y and len(y) == 2 else 0) if y else None
        d = _month_day(today, day, mon, yr)
        if d:
            cands.append(("ok", d))
    # day number (+ month) (+ weekday)
    day_num, mon, wd, year = None, None, None, None
    i = 0
    while i < len(toks):
        w = toks[i]
        m2 = re.match(r"^(\d{1,2})(st|nd|rd|th)?$", w)
        if w in MONTHS and w not in ("may",) or (w == "may" and (i + 1 < len(toks) and re.match(r"^\d", toks[i + 1]) or i > 0 and re.match(r"^\d", toks[i - 1]))):
            mon = MONTHS[w]
        elif w in WEEKDAYS:
            wd = WEEKDAYS[w]
        elif m2 and (m2.group(2) or (i > 0 and toks[i - 1] in ("the", "on")) or
                     (i + 1 < len(toks) and (toks[i + 1] in MONTHS or toks[i + 1] == "of")) or
                     (i > 0 and toks[i - 1] in MONTHS)):
            v = int(m2.group(1))
            if 1 <= v <= 31:
                day_num = v
        elif re.match(r"^\d{4}$", w) and 2020 <= int(w) <= 2100:
            year = int(w)
        else:
            r = word_number(toks, i)
            if r and r[2] and 1 <= r[0] <= 31:
                day_num = r[0]
                i = r[1]
                continue
            if r and not r[2] and 1 <= r[0] <= 31 and r[1] < len(toks) and toks[r[1]] in MONTHS:
                day_num = r[0]
                i = r[1]
                continue
            if r and not r[2] and 1 <= r[0] <= 31 and i > 0 and toks[i - 1] in MONTHS:
                day_num = r[0]
                i = r[1]
                continue
        i += 1
    if day_num is not None:
        if mon is None and month_hint:
            mon = month_hint
        if mon is not None:
            d = _month_day(today, day_num, mon, year)
        else:
            d = _next_day_number(today, day_num)
        if d is None:
            return {"status": "ask"}
        if wd is not None and d.weekday() != wd:
            return {"status": "conflict", "date": d_iso(d), "weekday": DAY_NAMES[wd]}
        cands.append(("ok", d))
    elif wd is not None:
        monday = today - datetime.timedelta(days=today.weekday())
        if re.search(r"\bnext\b", t) and dates_cfg.get("next_weekday", "following_week") == "following_week":
            d = monday + datetime.timedelta(days=7 + wd)
        elif re.search(r"\bthis\b", t) and dates_cfg.get("this_weekday", "current_week") == "current_week":
            d = monday + datetime.timedelta(days=wd)
        else:
            d = today + datetime.timedelta(days=(wd - today.weekday()) % 7)
        cands.append(("ok", d))
    elif mon is not None:
        return {"status": "vague", "month": mon}
    if not cands:
        if VAGUE.search(t):
            return {"status": "vague"}
        return {"status": "none"}
    d = cands[-1][1]
    if d < today:
        return {"status": "past", "date": d_iso(d)}
    return {"status": "ok", "date": d_iso(d)}


def _month_day(today, day, mon, year=None):
    try:
        if year:
            return datetime.date(year, mon, day)
        d = datetime.date(today.year, mon, day)
    except ValueError:
        return None
    if d < today and (today - d).days > 60:
        try:
            d = datetime.date(today.year + 1, mon, day)
        except ValueError:
            return None
    return d


def _next_day_number(today, day):
    y, m = today.year, today.month
    for _ in range(3):
        try:
            d = datetime.date(y, m, day)
            if d >= today:
                return d
        except ValueError:
            pass
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return None


def _numberish(w):
    return bool(re.match(r"^\d", w or "")) or _cls(w or "")[0] is not None


def parse_dob(text, order="DMY"):
    """Date of birth parts from speech -> dict(y, m, d) with None for parts not given.

    Handles '14 March 1988', 'the fourteenth of March, nineteen eighty-eight', 'twenty-eight April nineteen
    ninety-three', 'March 14th 88', '14/03/1988', '1988-03-14' and day/month given as two small numbers."""
    t = norm(text)
    out = {"y": None, "m": None, "d": None}
    mm = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if mm:
        return {"y": int(mm.group(1)), "m": int(mm.group(2)), "d": int(mm.group(3))}
    mm = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b", t)
    if mm:
        a, b, y = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
        if y < 100:
            y += 1900 if y > 30 else 2000
        d, m = (b, a) if order == "MDY" else (a, b)
        if m > 12 and d <= 12:
            d, m = m, d
        return {"y": y, "m": m, "d": d}
    toks = tokens(t)
    small, two_digit = [], []
    i = 0
    while i < len(toks):
        w = toks[i]
        if w in MONTHS and (w != "may" or _numberish(toks[i - 1] if i else "") or
                            _numberish(toks[i + 1] if i + 1 < len(toks) else "") or
                            (i + 1 < len(toks) and toks[i + 1] in ("the",)) or (i > 0 and toks[i - 1] in ("of", "in")) or
                            not [x for x in toks if x not in BARE_FILLER and x != "may"]):
            out["m"] = MONTHS[w]
            i += 1
            continue
        yr = year_words(toks, i)
        if yr and 1900 <= yr[0] <= 2030:
            out["y"] = yr[0]
            i = yr[1]
            continue
        m2 = re.match(r"^(\d{1,2})(st|nd|rd|th)?$", w)
        if m2:
            v = int(m2.group(1))
            if m2.group(2) or 1 <= v <= 31:
                small.append((v, bool(m2.group(2))))
            elif v >= 32:
                two_digit.append(v)
            i += 1
            continue
        r = word_number(toks, i)
        if r:
            v = r[0]
            if 1 <= v <= 31:
                small.append((v, r[2]))
            elif 32 <= v <= 99 and not r[2]:
                two_digit.append(v)
            i = r[1]
            continue
        i += 1
    if small:
        ords = [v for v, o in small if o]
        if out["m"] is not None:
            out["d"] = (ords or [v for v, _ in small])[-1] if len(small) > 1 and ords else small[0][0]
            if len(small) > 1 and out["y"] is None and not ords and small[-1][0] >= 0:
                two_digit.append(small[-1][0])
        elif len(small) >= 2:
            a, b = small[0][0], small[1][0]
            d, m = (b, a) if order == "MDY" else (a, b)
            if m > 12 and d <= 12:
                d, m = m, d
            if 1 <= m <= 12:
                out["d"], out["m"] = d, m
            if len(small) >= 3 and out["y"] is None:
                two_digit.append(small[2][0])
        else:
            out["d"] = small[0][0]
    if out["y"] is None and two_digit:
        v = two_digit[-1]
        out["y"] = 1900 + v if v >= 30 else 2000 + v
    return out


LEAD_IN = re.compile(r"^(?:(?:yes|yeah|sure|okay|ok|um|uh|well|so|right)[, ]+)*(?:(?:it'?s|it is|that'?s|that is|"
                     r"(?:my|our|the) [a-z ]{1,40}? (?:is|are))\s+)?", re.I)


CODE_STOP = set("it is my me at on in to so ok oh uh um of or an as be by do go he we us no hi am".split())


def parse_code(text, upper=True, keep_spaces=False):
    """An alphanumeric code (postcode, company number) from speech: 'S W one A, one A A' -> 'SW1A1AA',
    'SW1A 1AA' -> 'SW1A1AA', 'three four zero zero zero' -> '34000'. The longest run of letters/digits wins; the
    last one on a tie (corrections)."""
    toks = re.findall(r"[a-z0-9]+", re.sub(r"'[a-z]+\b", "", norm(text)))
    runs, cur = [], []
    i = 0
    while i < len(toks):
        t = toks[i]
        piece = None
        if t in ("double", "triple") and i + 1 < len(toks):
            nx = toks[i + 1]
            unit = str(UNITS[nx]) if nx in UNITS and UNITS[nx] < 10 else (nx if re.match(r"^[a-z0-9]$", nx) else None)
            if unit is not None:
                piece = unit * (2 if t == "double" else 3)
                i += 1
        elif re.match(r"^[0-9]+$", t) or (re.search(r"\d", t) and re.search(r"[a-z]", t) and len(t) <= 8):
            piece = t
        elif t in UNITS and UNITS[t] < 10:
            piece = str(UNITS[t])
        elif t in TENS:
            v = TENS[t]
            if i + 1 < len(toks) and toks[i + 1] in UNITS and 0 < UNITS[toks[i + 1]] < 10:
                v += UNITS[toks[i + 1]]
                i += 1
            piece = str(v)
        elif t in UNITS:
            piece = str(UNITS[t])
        elif len(t) <= 2 and t.isalpha() and (len(t) == 1 or t not in CODE_STOP):
            piece = t
        if piece is not None:
            cur.append(piece)
        elif cur:
            runs.append(cur)
            cur = []
        i += 1
    if cur:
        runs.append(cur)
    runs = [r for r in runs if re.search(r"\d", "".join(r)) or len("".join(r)) >= 4]
    if not runs:
        return None
    best = None
    for r in runs:
        if best is None or len("".join(r)) >= len("".join(best)):
            best = r
    compact = "".join(best)
    if len(compact) < 2:
        return None
    code = compact
    if keep_spaces:
        up = compact.upper()
        m = re.match(r"^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})$", up) or re.match(r"^([A-Z]\d[A-Z])(\d[A-Z]\d)$", up)
        if m:  # postcode shapes with a fixed inner space (outward + inward part)
            code = m.group(1) + " " + m.group(2)
            code = code if upper else code.lower()
        else:  # keep the groups as said: multi-character pieces stay apart, spelled characters join up
            groups, cur = [], ""
            for piece in best:
                if len(piece) == 1:
                    cur += piece
                else:
                    if cur:
                        groups.append(cur)
                        cur = ""
                    groups.append(piece)
            if cur:
                groups.append(cur)
            code = " ".join(groups)
    return code.upper() if upper else code


def clean_text_answer(text):
    t = (text or "").strip()
    t = LEAD_IN.sub("", t).strip()
    return t.strip(" .!?,") or None


def dob_complete(parts, fmt="YYYY-MM-DD"):
    try:
        d = datetime.date(int(parts["y"]), int(parts["m"]), int(parts["d"]))
    except Exception:
        return None
    return format_date(d, fmt)


def format_date(d, fmt="YYYY-MM-DD"):
    f = fmt or "YYYY-MM-DD"
    return f.replace("YYYY", "%04d" % d.year).replace("MM", "%02d" % d.month).replace("DD", "%02d" % d.day)


def parse_year(text):
    toks = tokens(text)
    for i in range(len(toks)):
        r = year_words(toks, i)
        if r and 1800 <= r[0] <= 2100:
            return str(r[0])
    return None


def parse_time(text, cfg_start="10:00", cfg_end="19:00"):
    """Spoken time -> 'HH:MM' or None. Hour without am/pm is placed inside the callback window if possible."""
    t = norm(text)
    if re.search(r"\b(noon|midday|lunchtime)\b", t):
        return "12:00"
    pm = re.search(r"\b(pm|p m|afternoon|evening|tonight)\b", t) is not None
    am = re.search(r"\b(am|a m|morning)\b", t) is not None
    h, mi = None, 0
    mm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t)
    toks = tokens(t)
    if re.search(r"\bhalf past\b", t) or re.search(r"\bquarter (past|to)\b", t):
        m3 = re.search(r"\b(half past|quarter past|quarter to)\s+(\w+)", t)
        if m3:
            r = word_number([m3.group(2)], 0)
            hv = int(m3.group(2)) if m3.group(2).isdigit() else (r[0] if r else None)
            if hv is not None:
                h = hv
                mi = 30 if m3.group(1) == "half past" else (15 if m3.group(1) == "quarter past" else 45)
                if m3.group(1) == "quarter to":
                    h -= 1
    if h is None:
        # the first number that is clearly a time ('12:00', '3 pm', 'at 11', '4 o'clock'), not a day ('13 October')
        for mm in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t):
            before = t[:mm.start()]
            if mm.group(2) or mm.group(3) or re.search(r"\b(at|around|about|after|by|from|before)\s*$", before) \
                    or re.match(r"\s*o ?clock\b", t[mm.end():]):
                h = int(mm.group(1))
                mi = int(mm.group(2) or 0)
                if mm.group(3) == "pm":
                    pm = True
                if mm.group(3) == "am":
                    am = True
                break
    if h is None:
        for i, w in enumerate(toks):
            if w in ("at", "around", "about", "after", "by", "from") and i + 1 < len(toks):
                r = word_number(toks, i + 1)
                if r and not r[2] and 1 <= r[0] <= 23:
                    h = r[0]
                    if r[1] < len(toks) and toks[r[1]] in TENS or (r[1] < len(toks) and re.match(r"^\d{2}$", toks[r[1]])):
                        r2 = word_number(toks, r[1])
                        if r2 and r2[0] < 60:
                            mi = r2[0]
                    break
    if h is None:
        r = None
        for i, w in enumerate(toks):
            if w in UNITS or w in TENS:
                r = word_number(toks, i)
                if r and 1 <= r[0] <= 12 and (r[1] < len(toks) and toks[r[1]] in ("o", "oclock", "am", "pm")):
                    h = r[0]
                    break
    if h is None:
        return None
    if pm and h < 12:
        h += 12
    elif not am and not pm:
        s_h = int(cfg_start[:2])
        e_h = int(cfg_end[:2])
        if h < 12 and not (s_h <= h <= e_h) and s_h <= h + 12 <= e_h:
            h += 12
    if am and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return "%02d:%02d" % (h, mi)


# ---------------------------------------------------------------- formatting

def fill(tpl, mp):
    """Fill {placeholders}; one that has no value is dropped (never spoken as a brace word)."""
    def rep(m):
        k = m.group(1)
        return str(mp[k]) if k in mp and mp[k] is not None else ""
    out = re.sub(r"\{(\w+)\}", rep, tpl or "")
    out = re.sub(r"\s+([,.?!])", r"\1", re.sub(r"\s{2,}", " ", out))
    return out.strip()


def money(x, word="dollars"):
    x = round(float(x) + 1e-9, 2)
    if abs(x - round(x)) < 0.005:
        s = "{:,}".format(int(round(x)))
    else:
        s = "{:,.2f}".format(x)
    return s + " " + word


def join_and(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# ---------------------------------------------------------------- state helpers

def get_state(V):
    raw = V.get("rb_state")
    if isinstance(raw, dict):
        return raw
    try:
        st = json.loads(raw) if raw else None
    except Exception:
        st = None
    if not isinstance(st, dict) or st.get("rv") != RUNTIME_VERSION:
        st = {"rv": RUNTIME_VERSION, "phase": "person", "turn": 0, "person_asks": 1, "refusals": 0,
              "id": {"q": 0, "wrong": 0, "buf": {}, "explained": False, "declines": 0, "tech": 0, "seen": 0},
              "products": [], "cur": 0, "snapshot": None, "last_say": "", "repeats": 0, "clarify": 0,
              "help_offered": False, "support_offered": False, "events": [], "acct_seen": False,
              "cb_asks": 0, "multi_stage": None, "recorded": [], "failed": [], "notes": [],
              "outcome": "unclear", "transfer_after_promise": None, "pending": None, "hardship": False}
    return st


def S(V, key):
    v = V.get(key)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip()


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def contains_phrase(utt, phrase):
    u, p = norm(utt), norm(phrase)
    if not p:
        return False
    if not u or p in u:
        return True
    pt = [w for w in p.split() if len(w) > 2]
    if not pt:
        return p in u
    hit = sum(1 for w in pt if w in u.split() or w in u)
    return hit >= max(1, int(0.6 * len(pt) + 0.5))


YES_RE = re.compile(r"^\s*(yes|yeah|yep|yup|ya|sure|correct|right|exactly|absolutely|of course|okay yes|"
                    r"that'?s (right|correct|me|fine|ok)|that is (right|correct)|i confirm|confirmed|i do|"
                    r"speaking|it is|this is (he|she|him|her|me)|go ahead and record|sounds good|fine by me|"
                    r"works for me|that works|deal)\b")
NO_RE = re.compile(r"^\s*(no|nope|nah|not (today|really|now|possible)|i can'?t|i cannot|i won'?t|never|"
                   r"i don'?t (think so|want)|that'?s not|it'?s not)\b")
ACK_RE = re.compile(r"^\s*(ok|okay|alright|all right|mm+|hmm+|uh huh|i see|got it|fine|right then|one moment|hold on|wait)\b[\s.!,]*$")


EVENT_WORDS = re.compile(r"\b(wedding|birthday|party|anniversary|funeral|holiday|holidays|vacation|trip|concert|match|"
                         r"exam|appointment|christening|graduation|ceremony|festival|flight|surgery|operation)\b")
PAY_WORDS = re.compile(r"\b(pay|paying|payment|transfer|send|settle|cover|clear)\b")


CLAUSES = re.compile(r"[.;!?,]|\bbut\b|\band\b|\bhowever\b|\bthough\b")


def not_about_paying(utt, phrase):
    """True when the date phrase sits in a clause about another event ('my cousin's wedding is on the 30th'),
    also when that clause shares a sentence with paying ('I can't pay today, my cousin's wedding is on the 30th')."""
    u = norm(utt)
    ph = norm(phrase)
    if not ph or ph not in u:
        return False
    for clause in CLAUSES.split(u):
        if ph in clause:
            return bool(EVENT_WORDS.search(clause)) and not PAY_WORDS.search(clause)
    return False


NEG_WORDS = re.compile(r"\b(not|no|never|cannot|can't|cant|won't|wont|unable|don't|dont|isn't|impossible|no way)\b|n't\b")
NEG_AFTER = re.compile(r"^\s*(is not|isn't|won't|wont|doesn't|does not|is impossible|is too soon|is not possible|"
                       r"won't work|doesn't work|no)\b")
INCOME = re.compile(r"\b(salary|paycheck|pay check|wages|payday|pay day|get paid|income|pension|benefits)\b")
ANAPHORA = re.compile(r"\b(then|that day|that date|on that day|by then|at that point)\b")
PAY_CUE = re.compile(r"\b(pay|paying|payment|transfer|send|settle|afford|manage)\b")
PAY_INTENT = re.compile(r"\b(i|we)('ll|'d| will| would| can| could| shall| am able to| are able to| want to| wanna|"
                        r" plan to| intend to| am going to|'m going to| would like to|'d like to| might)\s+(\w+\s+)?"
                        r"(pay|transfer|send|settle|manage|do it|do that|make it|make the payment)\b|"
                        r"\bcan (i|we) pay\b|\b(pay|paying)\b[^.;]{0,40}\b(then|that day)\b")
TOO_MUCH = re.compile(r"\b(too much|too high|too expensive|too big|can't afford|cannot afford|can not afford|unaffordable|"
                      r"more than i (can|have))\b")
SUPERSEDED = re.compile(r"\b(instead of|rather than)\s+(on\s+)?(the\s+)?[a-z0-9]+(\s+of\s+[a-z]+)?")


def negated_in(utt, phrase):
    """True when the customer's message negates this phrase: 'I cannot pay today', 'not today', 'today won't work'.
    'I can't pay until Friday' names Friday (until / till / before turn the negation into a limit)."""
    u, ph = norm(utt).replace("’", "'"), norm(phrase)
    if not ph or ph not in u:
        return False
    if re.match(r"^(until|till|before|after|from)\b", ph):
        return False
    k = u.rfind(ph)
    start = max(u.rfind(x, 0, k) for x in (",", ".", ";", "!", "?", " but ", " however "))
    before = u[start + 1:k]
    if re.search(r"\b(until|till|before|from|after)\s*$", before):
        return False
    return bool(NEG_WORDS.search(before)) or bool(NEG_AFTER.match(u[k + len(ph):]))


def month_hint(st):
    h = st.get("month_hint")
    if isinstance(h, dict) and st.get("turn", 0) - h.get("turn", 0) <= 3:
        return h.get("m")
    return None


def utterance_date(utt, today, cal, cfg, hint):
    """A payment day stated in the message when the extracted words are missing, negated or only point back
    ('then'): a clause that pays, or names an income day that a paying clause points back to. Clauses about another
    event and negated clauses never count."""
    u = SUPERSEDED.sub(" ", norm(utt).replace("’", "'"))
    linked = bool(ANAPHORA.search(u) and PAY_CUE.search(u))
    best = None
    for c in CLAUSES.split(u):
        c = c.strip()
        if not c or (EVENT_WORDS.search(c) and not PAY_CUE.search(c)):
            continue
        if NEG_DAY.search(c) or (NEG_WORDS.search(c) and not re.search(r"\b(until|till|before)\b", c)):
            continue
        if not (PAY_INTENT.search(c) or (linked and INCOME.search(c))):
            continue  # only a clause that says the customer will pay ('too much for me to pay right now' is not one)
        r = parse_pay_date(c, today, cal, cfg, hint)
        if r.get("status") in ("ok", "past", "conflict"):
            best = r
    return best


def read_date(st, inp, P, today):
    """The payment day of this turn, read in context: the extracted words unless the message negates them, else a
    payment day the message itself links to paying; 'instead of <day>' drops the superseded day."""
    utt, ph = inp.get("utterance") or "", inp.get("pay_date") or ""
    cal, cfg, hint = P["calendar"], P.get("dates") or {}, month_hint(st)
    dres = {"status": "none"}
    if ph and not (utt and negated_in(utt, ph)):
        clean = SUPERSEDED.sub(" ", norm(ph))
        dres = parse_pay_date(clean if clean.strip() else ph, today, cal, cfg, hint)
    if dres.get("status") == "none" and utt:
        dres = utterance_date(utt, today, cal, cfg, hint) or dres
    if dres.get("month"):
        st["month_hint"] = {"m": dres["month"], "turn": st.get("turn", 0)}  # 'on October' ... 'Thirty.'
    elif dres.get("status") == "ok":
        st["month_hint"] = None
    return dres


def read_amount(st, inp):
    """What the customer said about the amount, before a product is chosen: parse_amount() of the whole amount in the
    message, or a reference (ref: floor | full | that). A negated amount ('I can't pay the minimum') is none."""
    ph, utt = inp.get("pay_amount") or "", inp.get("utterance") or ""
    if not ph:
        return {"status": "none"}
    if utt and negated_in(utt, ph):
        return {"status": "none", "negated": True}
    u, n = norm(utt), norm(ph)
    clause = next((c for c in CLAUSES.split(u) if n and n in c), u) if n in u else u
    if TOO_MUCH.search(clause) or (inp.get("intent") == "too_much" and not PAY_INTENT.search(clause)):
        return {"status": "none", "too_much": True}  # 'that full amount is too much': a complaint, not an offer
    span = amount_span(utt, ph) if utt else ph
    r = parse_amount(span)
    if r["status"] == "none":
        n = norm(span)
        for ref, rx in AMOUNT_REFS:
            if rx.search(n):
                return {"status": "ref", "ref": ref}
    return r


def amount_for(st, p, ar):
    """Resolve the amount for product p against the account facts. Returns dict(status=none|ok|ambiguous, c, best).
    A reading that equals a known amount wins; one reading inside floor..past due wins (the read-back shows it);
    a whole-dollar amount just under a known amount with cents ('six hundred thirty-seven' for 637.50) is checked
    with the customer, never rejected as below the floor."""
    s = ar.get("status")
    if s in ("none", None):
        return {"status": "none", "best": None}
    floor, full = cents(p["floor"]), cents(p["past_due"])
    known = [floor, full]
    if (p.get("offer") or {}).get("amount") is not None:
        known.append(cents(p["offer"]["amount"]))
    said = st.get("said") or {}
    if said.get("amt") is not None:
        known.append(cents(said["amt"]))
    if s == "ref":
        ref = ar["ref"]
        if ref == "floor":
            return {"status": "ok", "c": floor}
        if ref == "full":
            return {"status": "ok", "c": full}
        if said.get("amt") is not None and st.get("turn", 0) - said.get("turn", 0) <= 1 and \
                (not said.get("pid") or said["pid"] == p["id"]):
            return {"status": "ok", "c": cents(said["amt"])}
        if (p.get("offer") or {}).get("amount") is not None:
            return {"status": "ok", "c": cents(p["offer"]["amount"])}
        return {"status": "none", "best": None}
    def near(c):  # a known amount with cents whose dollars were said: the cents may be missing
        ks = [k for k in known if k % 100 and k // 100 == c // 100 and k > c and k >= floor]
        return ks[0] if ks and c % 100 == 0 else None
    if s == "incomplete":  # '... dollars and' with nothing after it
        return {"status": "ambiguous", "best": near(ar["c"]) or ar["c"]}
    alts = ar.get("alts") or [ar["c"]]
    hit = [a for a in alts if a in known]
    if len(set(hit)) == 1:
        return {"status": "ok", "c": hit[0]}
    inr = [a for a in alts if floor <= a <= full]
    if s == "ambiguous":
        if len(inr) == 1:
            return {"status": "ok", "c": inr[0]}
        best = min(alts, key=lambda a: min(abs(a - k) for k in known))
        return {"status": "ambiguous", "best": near(best) or best}
    c = ar["c"]
    if c < floor and near(c):
        return {"status": "ambiguous", "best": near(c)}
    return {"status": "ok", "c": c}


def read_inputs(V):
    inp = {k: S(V, k) for k in ("utterance", "reply", "intent", "topic", "pay_date", "pay_amount")}
    utt = inp["utterance"]
    for k in ("pay_date", "pay_amount"):
        if inp[k] and utt and not contains_phrase(utt, inp[k]):
            inp[k] = ""  # stale: not in this turn's message (L3)
    if inp["pay_date"] and utt and not_about_paying(utt, inp["pay_date"]):
        inp["pay_date"] = ""  # a date of another event, not a payment day (talkative customers)
    for k in ("reply", "intent", "topic"):
        inp[k] = norm(inp[k]).replace(" ", "_")
        if inp[k] in ("", "none", "null", "n_a"):
            inp[k] = ""
    nu = norm(utt)
    if not inp["reply"] and nu:
        if YES_RE.match(nu):
            inp["reply"] = "yes"
        elif NO_RE.match(nu):
            inp["reply"] = "no"
        elif ACK_RE.match(nu):
            inp["reply"] = "ack"
    # clear this turn's inputs: the extractor may omit a variable next turn and the old value would stay. Enum
    # variables only accept their own values (the platform rejects ""), so they are reset to "none".
    for k in ("utterance", "pay_date", "pay_amount"):
        V[k] = ""
    for k in ("reply", "intent", "topic"):
        V[k] = "none"
    return inp


# ---------------------------------------------------------------- the decision

class Out(object):
    def __init__(self):
        self.say = []
        self.route = "say"
        self.ending = None
        self.extra = {}


RUNTIME_LINES = {"go_on": "Please go on.", "floor_info": "The lowest amount I can record for your {product} is {amount}.",
                 "amount_check": "Just to be sure, did you mean {amount}?",
                 "ask_change": "What would you like to change, the amount or the date?",
                 "wait_ok": "Of course, take your time."}


def L(P, key, mp=None, **kw):
    base = dict(mp or {})
    base.update(kw)
    return fill(P["lines"].get(key) or RUNTIME_LINES.get(key, ""), base)


def person_map(V, P):
    mp = {}
    for k in P.get("call_variables") or []:
        if re.match(r"^[a-z][a-z0-9_]*$", str(k)) and k not in ("customer_id", "now"):
            mp[k] = S(V, k)
    mp.update({"title": S(V, "title"), "last_name": S(V, "last_name"), "first_name": S(V, "first_name"),
               "bank": P.get("bank", "")})
    return mp


def san(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "other"


def end_route(outcome, reason):
    return "end_" + san(outcome) + ("_r" if reason else "")


def set_outcome(V, P, situation):
    """Provisional or final outcome. final_route names the ending branch: with a reason field or without."""
    o = (P.get("outcomes") or {}).get(situation) or ["", None]
    V["final_outcome"] = o[0] or ""
    V["final_reason"] = o[1] if o[1] else NULL_REASON
    V["final_route"] = end_route(o[0], o[1])
    return o


def end_call(st, out, V, P, situation, pre_lines):
    o = set_outcome(V, P, situation)
    st["outcome"] = situation
    st["phase"] = "ended"
    words = [x for x in pre_lines if x] + [P["lines"]["goodbye"]]
    V["farewell"] = " ".join(words)
    out.route = V["final_route"]
    out.ending = situation


def product_view(p, P, today):
    return {"product": p["phrase"], "past_due": money(p["past_due"], P.get("currency_word", "dollars")),
            "days_late": str(p["days_late"])}


def load_products(V, P, today):
    raw = V.get("account_products")
    lst = None
    if isinstance(raw, list):
        lst = raw
    elif isinstance(raw, str) and raw.strip():
        for cand in (raw, raw.replace("'", '"').replace("True", "true").replace("False", "false").replace("None", "null")):
            try:
                lst = json.loads(cand)
                break
            except Exception:
                continue
    if lst is None:
        idx = {}
        pkey = re.escape(api_resp(P, "get_account", "products"))
        for k in list(V.keys()):
            m = re.match(r"^account_r?_?response\.data\." + pkey + r"\.(\d+)\.(\w+)$", str(k))
            if m:
                idx.setdefault(int(m.group(1)), {})[m.group(2)] = V[k]
        if idx:
            lst = [idx[i] for i in sorted(idx)]
    if not isinstance(lst, list):
        return None
    prods = []
    for i, it in enumerate(lst):
        if not isinstance(it, dict):
            continue
        typ = str(it.get(api_item(P, "type")) or "")
        spec = (P.get("products") or {}).get(typ) or {}
        floor_field = spec.get("floor_field")
        try:
            past_due = float(it.get(api_item(P, "past_due")))
            days_late = int(float(it.get(api_item(P, "days_late"))))
        except Exception:
            continue
        floor = None
        try:
            floor = float(it.get(floor_field)) if floor_field and it.get(floor_field) not in (None, "") else None
        except Exception:
            floor = None
        band = None
        for b in P.get("bands") or []:
            if b["min"] <= days_late <= b["max"]:
                band = b
        if band is None:
            band = sorted(P.get("bands") or [{}], key=lambda b: -b.get("max", 0))[0]
        if band.get("deadline_kind") == "calendar_days":
            dl = today + datetime.timedelta(days=int(band.get("deadline_n", 0)))
        else:
            dl = add_business(today, int(band.get("deadline_n", 0)), P["calendar"])
        mp = dict((k, v) for k, v in it.items() if isinstance(v, (str, int, float)))
        phrase = fill(spec.get("phrase") or typ.replace("_", " "), mp)
        prods.append({"id": str(it.get(api_item(P, "product_id")) or ("p%d" % (i + 1))), "type": typ, "phrase": phrase,
                      "past_due": past_due, "floor": floor if floor is not None else past_due,
                      "days_late": days_late, "band": band.get("name", ""), "deadline": d_iso(dl),
                      "attempts_total": int(band.get("attempts", 1)), "attempts_used": 0,
                      "status": "open", "too_much": False, "floor_offered": False, "exact_asked": False,
                      "refused": [], "offer": None, "agreed": None, "below_floor_offered": False})
    return prods


def api_resp(P, tool, role):
    return (((P.get("api") or {}).get(tool) or {}).get("resp") or {}).get(role, role)


def api_item(P, role):
    return (((P.get("api") or {}).get("get_account") or {}).get("item") or {}).get(role, role)


def now_string(V, P=None):
    """The call's current date-time variable: 'now' in the public briefs, else a call variable named like it."""
    names = ["now"] + [n for n in ((P or {}).get("call_variables") or [])
                       if re.search(r"now|today|date|time", str(n)) and n != "now"]
    for k in names:
        v = S(V, k)
        if d_from(v):
            return v
    return ""


def today_of(V, P=None):
    d = d_from(now_string(V, P))
    return d or datetime.date.today()


INCOMPLETE = re.compile(r"(,|;|:|\.\.\.|\u2026|-|\u2014)\s*$|\b(and|but|or|so|because|actually|sorry|i mean|could we|"
                        r"can we|could i|can i|maybe|um|uh|er|erm|like|well|then|the|on|at|to|for|of|with|is|it's)\s*$",
                        re.I)
TALK_PHASES = ("negotiate", "confirm", "support_offer", "human_offer")


def is_cut(inp):
    """A turn that ends mid-sentence: a trailing comma/dash/connector, or four or more words without . ? !"""
    u = (inp.get("utterance") or "").strip()
    if not u or re.search(r"\b(goodbye|bye)\b", norm(u)):
        return False
    if INCOMPLETE.search(u):
        return True
    if not re.search(r"[.?!][\"')\]]*$", u) and len(u.split()) >= 4:
        return True
    return False


def should_wait(st, inp, P, V=None):
    """Wait for the rest of a cut turn, in any phase, unless the fragment already holds what this step needs."""
    if st.get("waits", 0) >= 2 or not is_cut(inp):
        return False
    if st.get("phase") == "identity" and V is not None:
        absorb_verify(st, V, P)  # the last answer may have completed the check: then the account comes first
    ph = st.get("phase")
    if ph in TALK_PHASES:
        return True
    if ph == "identity":
        idq = P["identity"]["questions"]
        q = idq[min(st["id"].get("q", 0), len(idq) - 1)]
        val, _buf, _got = id_kind_parse(q, inp["utterance"], st["id"].get("buf"))
        return not val and inp["intent"] not in ("refuse_talk", "wants_human") and inp["topic"] not in ("human",)
    if ph == "person":
        return inp["reply"] not in ("yes", "no") and inp["intent"] in ("", "none")
    if ph == "third_party":
        return not re.search(r"\d|tomorrow|today|morning|afternoon|evening|noon|o'clock", norm(inp["utterance"]))
    return False


def merge_fragment(st, inp):
    """A customer turn cut at a pause ('I can pay that on Thursday,') is completed by the next one before deciding:
    the next turn's values win, the fragment fills what the next turn lacks."""
    fr = st.pop("fragment", None)
    if not fr:
        return inp
    out = dict(inp)
    out["utterance"] = (fr.get("utterance", "") + " " + inp["utterance"]).strip()
    for k in ("pay_date", "pay_amount", "reply", "intent", "topic"):
        if not inp.get(k) and fr.get(k):
            out[k] = fr[k]
    return out


def run(V, P):
    st = get_state(V)
    st["turn"] = st.get("turn", 0) + 1
    out = Out()
    inp = read_inputs(V)
    today = today_of(V, P)
    V["say"] = ""
    if st.get("fragment"):
        inp = merge_fragment(st, inp)
    if should_wait(st, inp, P, V):
        # the customer was cut off mid-sentence (a pause ended their turn): wait for the rest before deciding
        st["waits"] = st.get("waits", 0) + 1
        st["fragment"] = dict(inp)
        n = st.get("go_on_n", 0)
        st["go_on_n"] = n + 1
        out.say.append([L(P, "go_on", person_map(V, P)), "Sorry, go ahead.", "I'm listening."][n % 3])
        finish(st, out, V, P)
        return st
    st["waits"] = 0
    try:
        step(st, inp, V, P, out, today)
    except Exception as e:  # never raise: honest technical ending
        st.setdefault("events", []).append("error:" + str(e)[:120])
        out = Out()
        end_call(st, out, V, P, fallback_situation(st), [P["lines"]["tech_problem"]])
    finish(st, out, V, P)
    return st


def fallback_situation(st):
    """How to close if the next decide step fails (end_tech routes by final_route): not verified -> unclear,
    verified -> service_error."""
    if st.get("phase") in ("person", "third_party", "identity"):
        return "unclear"
    return "service_error"


def limit_exit(st, V, P):
    """The turn cap or a loop of identical lines ends the call (L2). It is not the customer's refusal: before the
    account the call closes as unclear, after it every product without a promise is a service problem."""
    out = Out()
    st.setdefault("events", []).append("limit_exit")
    if st.get("phase") in ("person", "third_party", "identity", "verified_wait") or not st.get("products"):
        end_call(st, out, V, P, fallback_situation(st), [])
        return out
    for p in st["products"]:
        if p["status"] in ("open", "agreed"):
            p["status"] = "failed"
    close_without_promise(st, out, V, P, person_map(V, P), today_of(V, P))
    return out


def finish(st, out, V, P):
    text = " ".join(x for x in out.say if x).strip()
    looping = out.route in ("say", "confirm") and text and text == st.get("last_say") and st.get("repeats", 0) >= 2
    if st.get("phase") != "ended" and (st.get("turn", 0) >= MAX_TURNS or looping):
        out, text = limit_exit(st, V, P), ""
    if out.route == "say" or out.route == "confirm":
        if text and text == st.get("last_say"):
            st["repeats"] = st.get("repeats", 0) + 1
        else:
            st["repeats"] = 0
        st["last_say"] = text
        if st["repeats"] >= 2:
            text = " ".join([P["lines"]["repeat"], text])
        if not text:
            text = P["lines"]["repeat"]
    if out.route not in ("say", "confirm") and text:
        # lines decided this turn must still be heard when the turn ends in a tool chain or an ending
        if out.route == "verify":
            for k in ("say_v_next", "say_v_wrong", "say_v_swapped", "say_v_unreadable", "say_v_done", "say_v_tech"):
                if out.extra.get(k):
                    out.extra[k] = text + " " + out.extra[k]
        else:
            for k in ("farewell", "farewell_af"):
                fw = S(V, k)
                if (k == "farewell" or fw) and text not in fw:
                    V[k] = (text + " " + fw).strip()
    V["say"] = text
    V["route"] = out.route
    for k, v in out.extra.items():
        V[k] = v
    if out.route in ("say", "confirm") and st.get("phase") != "ended":
        set_outcome(V, P, fallback_situation(st))  # only used if a later decide step fails (end_tech)
    elif not V.get("final_outcome") or not V.get("final_route"):
        set_outcome(V, P, st.get("outcome") or "unclear")
    st["events"] = (st.get("events") or [])[-12:]
    V["rb_state"] = json.dumps(st, separators=(",", ":"))
    V["rb_phase"] = st.get("phase", "")


def step(st, inp, V, P, out, today):
    ph = st["phase"]
    pm = person_map(V, P)
    topic, reply, intent = inp["topic"], inp["reply"], inp["intent"]
    if ph == "person":
        return step_person(st, inp, V, P, out, pm)
    if ph == "third_party":
        return step_third_party(st, inp, V, P, out, pm, today)
    if ph == "identity":
        return step_identity(st, inp, V, P, out, pm)
    if ph == "verified_wait":
        return step_after_verify(st, inp, V, P, out, pm, today)
    if ph in ("negotiate", "confirm", "support_offer", "human_offer", "after_fail"):
        return step_negotiate(st, inp, V, P, out, pm, today)
    if ph == "ended":
        end_call(st, out, V, P, st.get("outcome") or "unclear", [])
        return
    end_call(st, out, V, P, "unclear", [])


# ---- person check (A1-A10)

def answer_question(topic, P, pm, verified):
    if topic == "robot":
        return L(P, "robot_reply", pm)
    if topic == "scam":
        return L(P, "scam_reply", pm)
    if topic in ("who_is_calling",):
        return L(P, "robot_reply", pm)
    if topic == "discount":
        return L(P, "no_discount", pm) or L(P, "no_info", pm)
    return L(P, "no_info", pm)


def step_person(st, inp, V, P, out, pm):
    topic, reply, intent = inp["topic"], inp["reply"], inp["intent"]
    st["outcome"] = "unclear"
    if intent == "deceased":
        return end_call(st, out, V, P, "deceased", [L(P, "deceased", pm)])
    if intent == "wrong_number":
        return end_call(st, out, V, P, "wrong_number", [L(P, "wrong_number", pm)])
    if intent == "someone_else":
        st["phase"] = "third_party"
        st["outcome"] = "no_callback"
        out.say.append(L(P, "third_party_ask", pm))
        return
    if topic == "human" or intent == "wants_human":
        return handle_human(st, inp, V, P, out, pm, verified=False)
    if intent in ("refuse_talk", "goodbye") and reply != "yes":
        st["refusals"] = st.get("refusals", 0) + 1
        if st["refusals"] >= int((P.get("identity") or {}).get("decline_after", 2) or 2):
            return end_call(st, out, V, P, "id_declined", [])
        out.say.append(L(P, "id_explain", pm))
        out.say.append(L(P, "person_question", pm))
        st["person_asks"] = st.get("person_asks", 1) + 1
        return
    if reply == "yes" and topic not in ("robot", "scam", "who_is_calling", "what_about", "other_question"):
        return start_identity(st, out, V, P, pm)
    # not a confirmation: answer a question first, then ask again (A3/A4/A43)
    if topic in ("robot", "scam", "who_is_calling", "what_about", "other_question"):
        if topic == "what_about":
            out.say.append(L(P, "third_party_no_info", pm))
        else:
            out.say.append(answer_question(topic, P, pm, False))
    st["person_asks"] = st.get("person_asks", 1) + 1
    if st["person_asks"] > int((P.get("person") or {}).get("max_asks", 2)):
        return end_call(st, out, V, P, "unclear", [])
    out.say.append(L(P, "person_question", pm))


def start_identity(st, out, V, P, pm):
    st["phase"] = "identity"
    st["outcome"] = "id_declined"
    st["id"]["q"] = 0
    q = P["identity"]["questions"][0]
    out.say.append(L(P, "id_intro", pm))
    out.say.append(q["ask"])


def step_third_party(st, inp, V, P, out, pm, today):
    topic, reply, intent = inp["topic"], inp["reply"], inp["intent"]
    utt = inp["utterance"]
    if intent == "deceased":
        return end_call(st, out, V, P, "deceased", [L(P, "deceased", pm)])
    if intent == "wrong_number":
        return end_call(st, out, V, P, "wrong_number", [L(P, "wrong_number", pm)])
    if intent == "goodbye" and not utt:
        return end_call(st, out, V, P, "no_callback", [])
    cb = P.get("callback") or {}
    when = parse_callback(utt + " " + inp["pay_date"], today, V, P)
    if when.get("status") == "ok":
        st["outcome"] = "callback"
        set_outcome(V, P, "callback")
        st["phase"] = "ended"
        out.extra["cb_date"] = when["date"]
        out.extra["cb_time"] = when["time"]
        d = d_from(when["date"])
        V["farewell"] = " ".join([L(P, "callback_done", pm, when=spoken_date(d, today) + " at " + when["time"]), P["lines"]["goodbye"]])
        out.route = "callback"
        return
    if when.get("status") == "outside" or (when.get("status") == "none" and (reply == "no" or intent in ("refuse_talk",))):
        st["cb_asks"] = st.get("cb_asks", 0) + 1
        if st["cb_asks"] >= int(cb.get("max_asks", 2)):
            return end_call(st, out, V, P, "no_callback", [])
        out.say.append(L(P, "callback_window", pm))
        return
    if topic in ("what_about", "other_question", "offers_to_pay") or intent in ("propose", "too_much"):
        out.say.append(L(P, "third_party_no_info", pm))
        out.say.append(L(P, "third_party_ask", pm))
        st["cb_asks"] = st.get("cb_asks", 0)
        return
    if topic in ("robot", "scam"):
        out.say.append(answer_question(topic, P, pm, False))
        out.say.append(L(P, "third_party_ask", pm))
        return
    if bump(st, "tp") > 2:
        return end_call(st, out, V, P, "no_callback", [])
    out.say.append(L(P, "third_party_ask", pm))


def parse_callback(text, today, V, P):
    cb = P.get("callback") or {}
    t = norm(text)
    if not t:
        return {"status": "none"}
    tm = parse_time(t, cb.get("start", "10:00"), cb.get("end", "19:00"))
    dres = parse_pay_date(t, today, P["calendar"], P.get("dates") or {})
    day = None
    if dres.get("status") == "ok":
        day = d_from(dres["date"])
    if tm is None and day is None:
        return {"status": "none"}
    now_s = now_string(V, P)
    now_t = now_s[11:16] if len(now_s) >= 16 else "00:00"
    if tm is None:
        return {"status": "outside" if day and not allowed_cb_day(day, today, P) else "none"}
    if day is None:
        day = today if tm > now_t else None
        if day is None:
            nb = add_business(today, 1, P["calendar"])
            day = nb
    ok_day = allowed_cb_day(day, today, P)
    ok_time = cb.get("start", "10:00") <= tm <= cb.get("end", "19:00")
    if day == today and cb.get("after_now", True) and tm <= now_t:
        ok_time = False
    if ok_day and ok_time:
        return {"status": "ok", "date": d_iso(day), "time": tm}
    return {"status": "outside"}


def allowed_cb_day(day, today, P):
    days = (P.get("callback") or {}).get("days") or ["today", "next_business_day"]
    ok = []
    if "today" in days:
        ok.append(today)
    if "next_business_day" in days:
        ok.append(add_business(today, 1, P["calendar"]))
    if "tomorrow" in days:
        ok.append(today + datetime.timedelta(days=1))
    return day in ok


def handle_human(st, inp, V, P, out, pm, verified):
    if not st.get("help_offered"):
        st["help_offered"] = True
        st["resume_phase"] = st.get("phase")
        st["phase"] = "human_offer" if verified else st.get("phase")
        st["human_pending"] = True
        out.say.append(L(P, "help_first", pm))
        return
    return do_transfer(st, out, V, P, pm, "human")


def do_transfer(st, out, V, P, pm, kind):
    q = (P.get("queues") or {}).get(kind)
    situation = "transfer_" + kind
    if st.get("recorded") and kind:
        pass  # promise recorded earlier: transferred with this transfer's reason (A46 note)
    set_outcome(V, P, situation)
    st["outcome"] = situation
    st["phase"] = "ended"
    out.extra["xfer_queue"] = q or ""
    V["farewell"] = " ".join([L(P, "transfer", pm), P["lines"]["goodbye"]])
    out.route = "transfer"


# ---- identity (A11-A15)

def id_kind_parse(q, text, buf):
    kind = q.get("kind")
    if kind == "date":
        parts = parse_dob(text, q.get("date_order", "DMY"))
        merged = dict(buf or {})
        for k in ("y", "m", "d"):
            if parts.get(k) is not None:
                merged[k] = parts[k]
        val = dob_complete(merged, q.get("format") or "YYYY-MM-DD")
        return val, (None if val else merged), any(parts.get(k) is not None for k in ("y", "m", "d"))
    if kind == "digits":
        n = int(q.get("length") or 0)
        prev = (buf or {}).get("digits", "")
        val, partial = pick_digits(text, n)
        if val:
            return val, None, True
        if partial:
            comb = prev + partial
            if n and len(comb) == n:
                return comb, None, True
            if n and len(comb) > n:
                return comb[-n:], None, True
            return None, {"digits": comb}, True
        return None, buf, False
    if kind == "year":
        y = parse_year(text)
        return (y, None, True) if y else (None, buf, False)
    if kind == "code":
        v = parse_code(text, q.get("upper", True) is not False, bool(q.get("keep_spaces")))
        return (v, None, True) if v else (None, buf, False)
    v = clean_text_answer(text)
    return (v, None, True) if v else (None, buf, False)


def step_identity(st, inp, V, P, out, pm):
    idq = P["identity"]["questions"]
    ids = st["id"]
    topic, reply, intent = inp["topic"], inp["reply"], inp["intent"]
    utt = inp["utterance"]
    # results of the verify call made at the end of the previous turn
    absorb_verify(st, V, P)
    if st["phase"] != "identity":
        return step(st, inp, V, P, out, today_of(V, P))
    q = idq[min(ids["q"], len(idq) - 1)]
    if topic == "human" or intent == "wants_human":
        return handle_human(st, inp, V, P, out, pm, verified=False)
    if topic in ("robot", "scam"):
        out.say.append(answer_question(topic, P, pm, False))
        out.say.append(q["ask"])
        return
    val, buf, got = id_kind_parse(q, utt, ids.get("buf"))
    declining = intent in ("refuse_talk", "refuse_answer") or topic in ("what_about", "why_needed") and not got
    if declining and not got:
        if topic == "why_needed" and not ids.get("explained"):
            ids["explained"] = True
            out.say.append(L(P, "id_explain", pm))
            out.say.append(q["ask"])
            return
        ids["declines"] = ids.get("declines", 0) + 1
        limit = max(1, int((P.get("identity") or {}).get("decline_after", 2) or 2))
        if ids["declines"] >= limit or ids.get("explained") and ids["declines"] >= limit - 1 and topic != "why_needed":
            return end_call(st, out, V, P, "id_declined", [])
        ids["explained"] = True
        out.say.append(L(P, "id_explain", pm))
        out.say.append(q["ask"])
        return
    if val:
        ids["buf"] = {}
        ids["more"] = 0
        # an answer ends a refusal episode: 'still declines' means refusing again without answering in between
        ids["declines"] = 0
        ids["explained"] = False
        ids["pending_field"] = q["field"]
        out.extra["v_field"] = q["field"]
        out.extra["v_answer"] = val
        precompute_verify(st, out, V, P, pm, q)
        out.route = "verify"
        return
    if got and buf:
        ids["more"] = ids.get("more", 0) + 1
        if ids["more"] <= 2:
            ids["buf"] = buf
            out.say.append(L(P, "id_more", pm, label=q.get("label", "")))
            return
        # still incomplete after asking for the rest twice: start this answer again
        ids["buf"] = {}
        ids["more"] = 0
        out.say.append(q["ask"])
        return
    n = bump(st, "id%d" % ids["q"])
    if n > 4:
        return end_call(st, out, V, P, "id_declined", [])
    # never the same words three times in a row: alternate the question with a 'didn't catch that' variant
    out.say.append(q["ask"] if n % 2 else L(P, "id_unreadable", pm, label=q.get("label", "")))


def precompute_verify(st, out, V, P, pm, q):
    idq = P["identity"]["questions"]
    ids = st["id"]
    nxt = idq[ids["q"] + 1] if ids["q"] + 1 < len(idq) else None
    out.extra["say_v_next"] = nxt["ask"] if nxt else L(P, "verified", pm)
    out.extra["say_v_wrong"] = L(P, "id_retry", pm, label=q.get("label", ""))
    out.extra["say_v_swapped"] = L(P, "id_swapped", pm, label=q.get("label", ""))
    out.extra["say_v_unreadable"] = L(P, "id_unreadable", pm, label=q.get("label", ""))
    out.extra["say_v_done"] = L(P, "verified", pm)
    out.extra["say_v_tech"] = L(P, "id_unreadable", pm, label=q.get("label", ""))
    max_wrong = int(P["identity"].get("max_wrong", 3))
    if ids.get("wrong", 0) + 1 >= max_wrong:
        # if this answer is wrong the bank ends the check: the end node needs these already set
        set_outcome(V, P, "id_failed")
        V["farewell"] = " ".join([L(P, "id_fail", pm), P["lines"]["goodbye"]])
    else:
        set_outcome(V, P, "unclear")  # placeholder: only used if a later decide step fails


def absorb_verify(st, V, P):
    ids = st["id"]
    cnt = int(float(S(V, "verify_success_count") or 0)) + int(float(S(V, "verify_failure_count") or 0))
    if cnt <= ids.get("seen", 0):
        return
    ids["seen"] = cnt
    status = S(V, "verify_response.status")
    if status and status != "success":
        ids["tech"] = ids.get("tech", 0) + 1
        st["events"].append("verify_tech")
        return
    vk = lambda role: "verify_response.data." + api_resp(P, "verify_identity", role)  # noqa: E731
    if truthy(S(V, vk("all_verified"))):
        st["phase"] = "verified_wait"
        st["outcome"] = "refused"
        return
    if truthy(S(V, vk("verified"))):
        ids["q"] = ids.get("q", 0) + 1
        return
    left = S(V, vk("wrong_answers_left"))
    hint = S(V, vk("hint"))
    okv = S(V, vk("ok"))
    if hint:
        return
    if okv and not truthy(okv) and not left:
        return
    try:
        left_i = int(float(left))
        ids["wrong"] = int(P["identity"].get("max_wrong", 3)) - left_i
        if left_i <= 0:
            st["phase"] = "ended"
            st["outcome"] = "id_failed"
    except Exception:
        pass


# ---- after verification: account, disclosure (A16-A17)

def step_after_verify(st, inp, V, P, out, pm, today):
    prods = load_products(V, P, today)
    if not prods:  # get_account failed twice (account + account_r): honest technical ending
        st["acct_tries"] = st.get("acct_tries", 0) + 1
        return end_call(st, out, V, P, "service_error", [P["lines"]["tech_problem"]])
    st["products"] = prods
    st["phase"] = "negotiate"
    st["outcome"] = "refused"
    multi = len(prods) > 1
    out.say.append(L(P, "disclosure_intro", pm))
    for p in prods:
        out.say.append(L(P, "disclosure_item", pm, **product_view(p, P, today)))
    topic = inp["topic"]
    if topic == "hardship":
        return start_hardship(st, out, V, P, pm)
    if topic in ("dispute", "already_paid", "restructuring", "human") and not multi:
        return handle_interrupt(st, inp, V, P, out, pm, today, topic)
    if topic in ("robot", "scam", "other_question", "how_much", "discount"):
        out.say.insert(0, answer_question(topic, P, pm, True))
    if multi:
        st["multi_stage"] = "all_today"
    for p in prods:
        p["offer"] = first_offer(p, P, today)
    out.say.append(first_ask_text(st, P, pm, today))
    st["cur"] = 0


def first_ask_rule(P):
    fa = P.get("first_ask") or {}
    return fa.get("date_rule") or "today", fa.get("amount_rule") or "full"


def first_offer(p, P, today):
    """The first payment request for product p (kind 'today' marks the first request whatever its date rule)."""
    date_rule, amount_rule = first_ask_rule(P)
    dl = d_from(p["deadline"])
    d = date_for_rule(date_rule, today, dl, P["calendar"]) if date_rule != "today" else today
    if d > dl:
        d = dl
    amt = p["floor"] if amount_rule == "floor" else p["past_due"]
    return {"amount": amt, "date": d_iso(d), "kind": "today"}


def first_ask_text(st, P, pm, today):
    prods = [p for p in st["products"] if p["status"] == "open"] or st["products"]
    multi = len(st["products"]) > 1
    if first_ask_rule(P) == ("today", "full"):
        return L(P, "first_ask_multi" if multi and st.get("multi_stage") == "all_today" else "first_ask_single", pm)
    if multi and st.get("multi_stage") == "all_today":
        return " ".join(offer_text(P, pm, p, p["offer"]["amount"], p["offer"]["date"], today, True, True) for p in prods)
    p = cur_product(st) or prods[0]
    off = p.get("offer") or first_offer(p, P, today)
    return offer_text(P, pm, p, off["amount"], off["date"], today, multi, multi)


# ---- negotiation (A18-A38, B1-B11)

def open_products(st):
    return [p for p in st["products"] if p["status"] == "open"]


def cur_product(st):
    ops = open_products(st)
    if not ops:
        return None
    for p in ops:
        if st["products"].index(p) >= st.get("cur", 0):
            return p
    return ops[0]


def start_hardship(st, out, V, P, pm):
    st["hardship"] = True
    st["phase"] = "support_offer"
    st["outcome"] = "hardship"
    out.say.append(L(P, "sympathy", pm))
    if not st.get("support_offered"):
        st["support_offered"] = True
        out.say.append(L(P, "support_offer", pm))
    return


def handle_interrupt(st, inp, V, P, out, pm, today, topic):
    multi = len(st["products"]) > 1
    if topic == "hardship":
        return start_hardship(st, out, V, P, pm)
    if topic == "restructuring":
        return do_transfer(st, out, V, P, pm, "restructuring")
    if topic == "human":
        return handle_human(st, inp, V, P, out, pm, verified=True)
    if topic in ("dispute", "already_paid"):
        if not multi:
            if topic == "dispute":
                return end_call(st, out, V, P, "dispute", [L(P, "dispute_reply", pm)])
            return end_call(st, out, V, P, "paid", [L(P, "paid_reply", pm)])
        targets = scope_products(st, inp, P)
        if not targets:
            p = cur_product(st)
            targets = [p] if p else []
        for p in targets:
            p["status"] = "dispute" if topic == "dispute" else "paid"
        out.say.append(L(P, "dispute_reply" if topic == "dispute" else "paid_reply", pm))
        return next_product_or_close(st, out, V, P, pm, today)
    return None


CLAUSE_NEG = re.compile(r"\b(not|no|never|won't|wont|will not|can't|cant|cannot|refuse|refusing|don't|dont|do not|"
                        r"nothing|neither|nor)\b|n't\b")
CLAUSE_SPLIT = re.compile(r"(\bbut\b|\bexcept(?: for)?\b|\bapart from\b|\bother than\b|\bhowever\b|\bwhile\b|"
                          r"\bwhereas\b|[.;!?,])")
OTHERS = re.compile(r"\b(the )?(others|other ones|other two|other three|other one|rest|remaining ones|everything else|"
                    r"other (products|loans|accounts|debts|cards))\b")


def scope_split(st, inp, P):
    """Split a multi-product statement into the products it pays (pos) and the ones it refuses (neg).

    'I will pay the credit card tomorrow, but I am not paying the personal loan or the car loan' -> pos [card],
    neg [loans]. A clause after 'except' / 'apart from' is a refusal. 'the others' / 'the rest' covers the products
    not named elsewhere. A clause that only negates a day ('not today') refuses no product."""
    t = norm(inp["utterance"]).replace("’", "'")
    live = [p for p in st["products"] if p["status"] in ("open", "agreed")]
    parts = CLAUSE_SPLIT.split(t)
    pos, neg, others_pos, others_neg, carry = [], [], False, False, []
    marker = ""
    for part in parts:
        if part is None:
            continue
        if CLAUSE_SPLIT.fullmatch(part.strip() or "#"):
            marker = part.strip()
            continue
        c = part.strip()
        if not c:
            continue
        hits = [p for p in scope_products(st, {"utterance": c, "pay_date": ""}, P) if p in live]
        excepted = marker.startswith(("except", "apart", "other than"))
        day_only = bool(NEG_DAY.search(c)) and not re.search(r"\b(pay|paying)\b[^.]{0,30}\b(not|never|won't|refuse)\b", c)
        negative = excepted or (bool(CLAUSE_NEG.search(c)) and not day_only)
        if OTHERS.search(c):
            if negative:
                others_neg = True
            else:
                others_pos = True
        if not hits and carry and not negative and not day_only:
            hits = carry
        if day_only:
            carry = hits
            continue
        carry = hits
        (neg if negative else pos).extend(h for h in hits if h not in (neg if negative else pos))
    pos = [p for p in pos if p not in neg]
    if others_pos:
        pos += [p for p in live if p not in neg and p not in pos]
    if others_neg:
        neg += [p for p in live if p not in pos and p not in neg]
    return pos, neg


def scope_products(st, inp, P):
    """Which products a customer statement covers (multi-product)."""
    t = norm(inp["utterance"] + " " + inp["pay_date"])
    prods = st["products"]
    if re.search(r"\b(all|both|everything|all of them|every one|each of them|the three|all three|the two)\b", t):
        return [p for p in prods if p["status"] in ("open", "agreed")]
    hits, matched = [], {}
    for p in prods:
        words = [w for w in norm(p["phrase"]).split() if len(w) > 2 and w not in ("ending", "your", "the")]
        typ_words = [w for w in norm(p["type"].replace("_", " ")).split() if len(w) > 2]
        m = set(w for w in set(words + typ_words) if re.search(r"\b" + re.escape(w) + r"s?\b", t))
        if m:
            hits.append(p)
            matched[p["id"]] = m
    if len(hits) > 1:
        # 'loan' matches several loans: a product named only by a shared word ('loan') yields to one named by its own
        # word too ('car loan'); 'the card and the car loan' keeps the card (no other product says 'card')
        shared = set(w for p in hits for w in matched[p["id"]] if sum(1 for q in hits if w in matched[q["id"]]) > 1)
        named = [p for p in hits if matched[p["id"]] - shared]
        hits = [p for p in hits if matched[p["id"]] - shared or
                not any(set(matched[p["id"]]) & matched[q["id"]] for q in named if q is not p)]
    return hits


def offer_text(P, pm, p, amount, date, today, multi, with_product):
    s = L(P, "offer", pm, amount=money(amount, P.get("currency_word", "dollars")), date=spoken_date(d_from(date), today))
    if multi and with_product:
        s = "For your %s: %s" % (p["phrase"], s[0].lower() + s[1:] if s else s)
    return s


def attempt_offer(p, P, today, n):
    """The offer of persuasion attempt n (1-based) for product p, or None if the band has no attempt n."""
    if n > p["attempts_total"]:
        return None
    rules = [a for a in (P.get("attempts") or []) if a.get("n") == n]
    if not rules:
        return None
    a = rules[0]
    if a.get("bands") and p["band"] not in a["bands"]:
        return None
    dl = d_from(p["deadline"])
    d = date_for_rule(a.get("date_rule"), today, dl, P["calendar"])
    if d > dl:
        d = dl
    rule = a.get("amount_rule")
    if rule == "floor":
        amt = p["floor"]
    elif rule == "full_or_floor":
        amt = p["floor"] if p["too_much"] else p["past_due"]
    elif rule == "current" and p.get("offer"):
        amt = p["offer"]["amount"]
    else:
        amt = p["past_due"]
    return {"amount": amt, "date": d_iso(d), "kind": "attempt%d" % n}


def refused_before(p, offer):
    for r in p.get("refused") or []:
        if abs(r["amount"] - offer["amount"]) < 0.005 and r["date"] == offer["date"]:
            return True
    return False


def next_attempt(st, out, V, P, pm, today, p):
    """The customer refused (or did not answer). Use the next persuasion attempt or settle as refused."""
    multi = len(st["products"]) > 1
    if p.get("offer") and p["offer"].get("date"):
        p["refused"].append({"amount": p["offer"]["amount"], "date": p["offer"]["date"]})
    if st.get("hardship"):
        # A32: after illness, a death or job loss no persuasion attempt; support is offered once
        p["offer"] = None
        if not st.get("support_offered"):
            return offer_support(st, out, P, pm)
        p["status"] = "hardship"
        return next_product_or_close(st, out, V, P, pm, today)
    while True:
        n = p["attempts_used"] + 1
        off = attempt_offer(p, P, today, n)
        if off is None:
            p["status"] = "refused"
            p["offer"] = None
            return next_product_or_close(st, out, V, P, pm, today)
        p["attempts_used"] = n
        if refused_before(p, off):
            continue  # A31: an offer the customer already refused is not repeated
        p["offer"] = off
        out.say.append(offer_text(P, pm, p, off["amount"], off["date"], today, multi, True))
        if off["amount"] < p["past_due"] - 0.005 and off["amount"] <= p["floor"] + 0.005 and not p.get("rest_said"):
            p["rest_said"] = True
            out.say.append(L(P, "rest_overdue", pm))
        return


def next_product_or_close(st, out, V, P, pm, today):
    ops = open_products(st)
    if ops:
        p = ops[0]
        st["cur"] = st["products"].index(p)
        if p.get("offer") is None or p["offer"].get("kind") == "today":
            p["offer"] = None
            return next_attempt(st, out, V, P, pm, today, p)
        return ask_pending(st, out, P, pm, today, p)
    return readback_or_close(st, out, V, P, pm, today)


def readback_or_close(st, out, V, P, pm, today):
    agreed = [p for p in st["products"] if p["status"] == "agreed"]
    if agreed:
        items = []
        for p in agreed:
            a = p["agreed"]
            key = "readback_clamped" if a.get("clamped") else "readback_item"
            items.append(L(P, key, pm, amount=money(a["amount"], P.get("currency_word", "dollars")), product=p["phrase"],
                           date=spoken_date(d_from(a["date"]), today)))
        st["snapshot"] = [{"pid": p["id"], "amount": p["agreed"]["amount"], "date": p["agreed"]["date"]} for p in agreed]
        st["phase"] = "confirm"
        st.setdefault("cl", {}).pop("confirm", None)
        out.say.append(L(P, "readback", pm, items=join_and(items)))
        partial = [p for p in agreed if p["agreed"]["amount"] < p["past_due"] - 0.005 and not p.get("rest_said")]
        if partial:
            for p in partial:
                p["rest_said"] = True
            out.say.append(L(P, "rest_overdue", pm))
        out.say.append(L(P, "confirm_question", pm))
        out.route = "say"
        return
    return close_without_promise(st, out, V, P, pm, today)


def note_reason_for(p, P):
    reasons = (P.get("notes") or {}).get("reasons") or {}
    key = {"refused": "refused", "hardship": "hardship", "dispute": "dispute", "paid": "paid", "failed": "service_error"}.get(p["status"], "refused")
    return reasons.get(key, key)


def situation_for_status(status):
    return {"refused": "refused", "hardship": "hardship", "dispute": "dispute", "paid": "paid",
            "failed": "service_error", "open": "refused"}.get(status, "refused")


def close_without_promise(st, out, V, P, pm, today, pre=None):
    prods = st["products"]
    for p in prods:
        if p["status"] in ("agreed", "open"):
            p["status"] = "hardship" if st.get("hardship") else "refused"
            p["agreed"] = None
    notes_on = (P.get("notes") or {}).get("enabled")
    if len(prods) <= 1 or not notes_on:
        p = prods[0] if prods else {"status": "refused"}
        sit = situation_for_status(p["status"])
        return end_call(st, out, V, P, sit, pre or [])
    # B closing: all paid -> paid; else first non-paid note's reason
    if all(p["status"] == "paid" for p in prods):
        sit = "paid"
    else:
        first = [p for p in prods if p["status"] != "paid"][0]
        sit = situation_for_status(first["status"])
    set_notes(st, out, V, P, [p for p in prods if p["status"] not in ("agreed", "recorded")])
    for k in range(1, 4):
        out.extra["wp%d_on" % k] = "no"
    set_outcome(V, P, sit)
    st["outcome"] = sit
    st["phase"] = "ended"
    V["farewell"] = " ".join([x for x in (pre or []) if x] + [P["lines"]["goodbye"]])
    out.route = "write_n1" if out.extra.get("wn1_on") == "yes" else V["final_route"]


def set_notes(st, out, V, P, prods):
    for k in range(1, 4):
        out.extra["wn%d_on" % k] = "no"
    k = 0
    for p in prods:
        if k >= 3:
            break
        k += 1
        out.extra["wn%d_on" % k] = "yes"
        out.extra["wn%d_pid" % k] = p["id"]
        out.extra["wn%d_reason" % k] = note_reason_for(p, P)


def accept(p, amount, date, clamped=False):
    p["status"] = "agreed"
    p["agreed"] = {"amount": round(float(amount), 2), "date": date, "clamped": clamped}
    p["offer"] = None


def cw(P):
    return P.get("currency_word", "dollars")


def bump(st, key):
    """Bounded no-progress counters, one per question (identity question, product, read-back): a non-answer in one
    phase never uses up another phase's patience."""
    cl = st.setdefault("cl", {})
    cl[key] = cl.get(key, 0) + 1
    return cl[key]


def date_alternative(p, dres, P, today):
    """The day the calendar rules make of a parsed day for product p, without speaking: the day itself, the next
    business day, or the deadline. None when there is no usable day."""
    if dres.get("status") != "ok":
        return None
    d, dl = d_from(dres["date"]), d_from(p["deadline"])
    if d is None or d < today:
        return None
    if d > dl:
        return d_iso(dl)
    if not is_business(d, P["calendar"]):
        return d_iso(min(next_business_on_or_after(d, P["calendar"]), dl))
    return d_iso(d)


def validate_date(p, dres, P, pm, today, out, multi, allow_clamp):
    """Apply the calendar rules to a parsed date for product p. Returns (date_iso, clamped) or (None, None) after
    speaking the counter-question. An alternative day offered here remembers the day it replaces."""
    dl = d_from(p["deadline"])
    st_ = dres.get("status")
    amt = (p.get("offer") or {}).get("amount", p["past_due"])
    if st_ == "ok":
        d = d_from(dres["date"])
        if d > dl:
            if allow_clamp:
                return d_iso(dl), True
            p["offer"] = {"amount": amt, "date": d_iso(dl), "kind": "deadline", "replaces": dres["date"]}
            out.say.append(L(P, "deadline_offer", pm, date=spoken_date(dl, today)))
            return None, None
        if not is_business(d, P["calendar"]):
            nb = next_business_on_or_after(d, P["calendar"])
            if nb > dl:
                nb = dl
            p["offer"] = {"amount": amt, "date": d_iso(nb), "kind": "next_business", "replaces": dres["date"]}
            out.say.append(L(P, "next_business_day_offer", pm, asked=spoken_date(d, today), date=spoken_date(nb, today)))
            return None, None
        return d_iso(d), False
    if st_ == "past":
        out.say.append(L(P, "past_date", pm))
        return None, None
    if st_ == "conflict":
        d = d_from(dres["date"])
        p["offer"] = {"amount": amt, "date": d_iso(d), "kind": "confirm_date"}
        out.say.append(L(P, "date_conflict", pm, date=spoken_date(d, today)))
        return None, None
    if st_ == "vague":
        if not p["exact_asked"]:
            p["exact_asked"] = True
            out.say.append(L(P, "ask_exact_day", pm))
            return None, None
        p["offer"] = {"amount": amt, "date": d_iso(dl), "kind": "deadline"}
        out.say.append(offer_text(P, pm, p, p["offer"]["amount"], p["offer"]["date"], today, multi, multi))
        return None, None
    out.say.append(L(P, "ask_exact_day", pm))
    return None, None


def validate_amount(p, c, P, pm, today, out, date=None):
    """c: the customer's amount in cents, already unambiguous. Returns the accepted amount, None after offering the
    floor (A27, once; on the customer's own day when they gave one), or -1 when the floor was already offered."""
    if c > cents(p["past_due"]):
        return p["past_due"]
    if c < cents(p["floor"]):
        if not p.get("below_floor_offered"):
            p["below_floor_offered"] = True
            p["floor_offered"] = True
            line = L(P, "below_floor", pm, floor=money(p["floor"], cw(P)))
            out.say.append(line)
            p["offer"] = {"amount": p["floor"], "date": date, "kind": "floor"}
            if not line.rstrip().endswith("?"):
                if date:
                    out.say.append(offer_text(P, pm, p, p["floor"], date, today, False, False))
                else:
                    out.say.append(L(P, "floor_offer", pm, amount=money(p["floor"], cw(P))))
                    out.say.append(L(P, "ask_exact_day", pm))
            return None
        return -1
    return c / 100.0


INFO_TOPICS = ("robot", "scam", "other_question", "discount", "how_much", "why_needed", "what_about", "change_promise")
MIN_Q = re.compile(r"\b(minimum|lowest|least|smallest)\b")
OWE_Q = re.compile(r"\b(how much|owe|past due|balance|the amount)\b")
REPEAT_Q = re.compile(r"\b(repeat|say that again|come again|pardon|what did you say|didn't (catch|hear)|one more time|"
                      r"say again)\b")
HOLD = re.compile(r"^\s*(hold on|one (moment|second|sec|minute)|just a (moment|second|sec|minute)|"
                  r"give me a (moment|second|sec|minute)|let me (check|think|see|look)|wait a)\b")
HESITATE = re.compile(r"\b(don't know|dont know|not sure|no idea|maybe|i guess|we'll see|hard to say|depends|perhaps)\b")


def own_offer(inp):
    """The customer named a day or an amount of their own this turn ('I cannot pay anything' is not one)."""
    return inp["ar"].get("status") not in ("none", None) or inp["dres"].get("status") in ("ok", "past", "conflict")


def answer_info(st, inp, out, P, pm, today):
    """Answer an information question from the account facts. Counters and offers stay as they are."""
    topic, u = inp["topic"], norm(inp["utterance"])
    if topic == "change_promise":
        out.say.append(L(P, "change_in_app", pm))
        return
    if topic == "how_much" or (topic in ("other_question", "discount") and (MIN_Q.search(u) or OWE_Q.search(u))
                               and "?" in inp["utterance"]):
        prods = st["products"]
        targets = [p for p in scope_products(st, inp, P) if p in prods] or [cur_product(st) or prods[0]]
        for p in targets:
            if MIN_Q.search(u) and p.get("floor") is not None:
                out.say.append(L(P, "floor_info", pm, product=p["phrase"], amount=money(p["floor"], cw(P))))
                st["said"] = {"amt": p["floor"], "pid": p["id"], "turn": st.get("turn", 0)}
            else:
                out.say.append(L(P, "disclosure_item", pm, **product_view(p, P, today)))
                st["said"] = {"amt": p["past_due"], "pid": p["id"], "turn": st.get("turn", 0)}
        return
    if REPEAT_Q.search(u):
        return  # the pending question follows, said again
    out.say.append(answer_question(topic, P, pm, True))


def offer_support(st, out, P, pm):
    st["phase"] = "support_offer"
    st["outcome"] = "hardship"
    st["support_offered"] = True
    out.say.append(L(P, "support_offer", pm))


def step_negotiate(st, inp, V, P, out, pm, today):
    topic, reply, intent = inp["topic"], inp["reply"], inp["intent"]
    prods = st["products"]
    multi = len(prods) > 1
    ph = st["phase"]
    asked_before = st.pop("asked", None)  # what the agent's previous turn ended with (info answer, hold)
    if ph == "after_fail":
        absorb_writes(st, V)
        return finish_after_fail(st, out, V, P, pm, today)
    inp["dres"] = read_date(st, inp, P, today)
    inp["ar"] = read_amount(st, inp)
    # interrupts first (L8), by the brief's precedence
    prec = (P.get("interrupts") or {}).get("precedence") or ["hardship", "dispute", "already_paid", "restructuring", "human"]
    if topic in prec and not (ph == "support_offer" and topic == "hardship") and not (ph == "human_offer" and topic == "human"):
        if topic == "hardship" and own_offer(inp) and ph in ("negotiate", "confirm"):
            # A32: one sentence of sympathy and no persuasion; a day or an amount the customer names is still handled
            st["hardship"] = True
            out.say.append(L(P, "sympathy", pm))
            st["phase"] = ph = "negotiate"
        else:
            handle_interrupt(st, inp, V, P, out, pm, today, topic)
            if out.route != "say" or out.say:
                return
    if ph == "support_offer":
        if own_offer(inp):
            st["phase"] = ph = "negotiate"
        elif reply == "yes" or intent == "accept_transfer":
            return do_transfer(st, out, V, P, pm, "support")
        elif reply == "no" or intent in ("refuse_talk", "goodbye", "decline", "refuse_pay"):
            for p in prods:
                if p["status"] == "open":
                    p["status"] = "hardship"
            if any(p["status"] == "agreed" for p in prods):
                return readback_or_close(st, out, V, P, pm, today)
            return close_without_promise(st, out, V, P, pm, today)
        else:
            if topic in INFO_TOPICS:
                answer_info(st, inp, out, P, pm, today)
            out.say.append(L(P, "support_offer", pm))
            return
    if ph == "human_offer":
        if topic == "human" or intent == "wants_human" or reply == "yes" and st.get("human_pending"):
            if reply == "no" and not topic:
                pass
            else:
                return do_transfer(st, out, V, P, pm, "human")
        st["phase"] = st.get("resume_phase") if st.get("resume_phase") in ("negotiate", "confirm") else "negotiate"
        st["human_pending"] = False
        ph = st["phase"]
    if topic in INFO_TOPICS:
        answer_info(st, inp, out, P, pm, today)
        if not (own_offer(inp) or reply in ("yes", "no") or intent in ("propose", "too_much", "vague_time", "refuse_pay")):
            st["asked"] = "info"
            return repeat_pending(st, out, V, P, pm, today)
    if intent in ("refuse_talk", "goodbye") and not own_offer(inp) and reply != "yes":
        st["refusals"] = st.get("refusals", 0) + 1
        if st["refusals"] >= int((P.get("interrupts") or {}).get("refuse_talk_times", 2) or 2) or intent == "goodbye":
            for p in prods:
                if p["status"] == "open":
                    p["status"] = "hardship" if st.get("hardship") else "refused"
            if any(p["status"] == "agreed" for p in prods) and ph != "confirm":
                return readback_or_close(st, out, V, P, pm, today)
            return close_without_promise(st, out, V, P, pm, today)
    if ph == "confirm":
        return step_confirm(st, inp, V, P, out, pm, today)
    return step_offer(st, inp, V, P, out, pm, today, asked_before)


def repeat_pending(st, out, V, P, pm, today):
    """Say the pending question again (a clarification or a requested repetition: no counter moves)."""
    if st["phase"] == "confirm":
        return readback_or_close(st, out, V, P, pm, today)
    if st.get("multi_stage") == "all_date" and st.get("group_q"):
        out.say.append(st["group_q"])
        return
    p = cur_product(st)
    if not p:
        return readback_or_close(st, out, V, P, pm, today)
    off = p.get("offer")
    if st.get("multi_stage") == "all_today" or (off and off.get("kind") == "today"):
        out.say.append(first_ask_text(st, P, pm, today))
    elif off:
        ask_pending(st, out, P, pm, today, p)
    else:
        p["offer"] = first_offer(p, P, today)
        out.say.append(first_ask_text(st, P, pm, today))


def step_offer(st, inp, V, P, out, pm, today, asked_before=None):
    topic, reply, intent = inp["topic"], inp["reply"], inp["intent"]
    prods = st["products"]
    multi = len(prods) > 1
    stage = st.get("multi_stage")
    ar, dres = inp["ar"], inp["dres"]
    if intent == "vague_time" and dres.get("status") == "none":
        dres = {"status": "vague"}
    proposes = ar.get("status") not in ("none", None) or dres.get("status") != "none" or intent in ("propose", "vague_time")
    if multi and stage == "all_date":
        # the exact day was asked for a group of products at once: a day without a narrower scope covers that group
        st["multi_stage"] = None
        scope = [p for p in prods if p["id"] in (st.get("scope") or []) and p["status"] == "open"] or open_products(st)
        if reply == "yes" and dres.get("status") == "none" and st.get("scope_date"):
            dres, proposes = {"status": "ok", "date": st["scope_date"]}, True
        if ar.get("status") in ("none", None) and st.get("scope_ar"):
            ar = st["scope_ar"]
        st["scope_date"], st["group_q"], st["scope_ar"] = None, None, None
        targets, refused_now = scope_split(st, inp, P)
        if proposes and not refused_now:
            use = [p for p in targets if p["status"] == "open"] or scope
            if len(use) > 1:
                return apply_group(st, inp, V, P, out, pm, today, ar, dres, use)
            if use:
                return single_proposal(st, inp, V, P, out, pm, today, use[0], ar, dres)
    if multi and stage == "all_today":
        targets, refused_now = scope_split(st, inp, P)
        if reply == "yes" and not proposes:
            # yes to paying today: all products, or the ones named ('yes for the card, not the loans'); the others
            # go through the persuasion steps (B4)
            yes_to = [p for p in (targets or open_products(st)) if p["status"] == "open" and p not in refused_now]
            for p in open_products(st):
                if p in yes_to:
                    off = p.get("offer") or first_offer(p, P, today)
                    accept(p, off["amount"], off["date"])
                else:
                    p["offer"] = None
            st["multi_stage"] = None
            return next_product_or_close(st, out, V, P, pm, today)
        st["multi_stage"] = None
        live = open_products(st)
        if proposes and not refused_now and (not targets or len(targets) == len(live)):
            # one statement for everything (B6): each product validated, late ones on their own deadline
            return apply_group(st, inp, V, P, out, pm, today, ar, dres, live)
        if intent == "too_much":
            for p in prods:
                p["too_much"] = True
        for p in prods:
            if p["status"] == "open" and p not in targets:
                p["offer"] = None  # no to all today: each product starts at attempt 1 (B4)
        if proposes and targets:
            if len(targets) > 1:
                return apply_group(st, inp, V, P, out, pm, today, ar, dres, targets)
            return single_proposal(st, inp, V, P, out, pm, today, targets[0], ar, dres)
        return next_product_or_close(st, out, V, P, pm, today)
    p = cur_product(st)
    if p is None:
        return readback_or_close(st, out, V, P, pm, today)
    off = p.get("offer") or {}
    if off.get("replaces") and reply in ("yes", "ack") and dres.get("status") == "ok" and dres["date"] == off["replaces"] \
            and ar.get("status") in ("none", None):
        dres, proposes = {"status": "none"}, False  # 'yes, instead of the 30th': the alternative is accepted
    if off.get("kind") == "confirm_amount":
        if reply in ("yes",) and ar.get("status") in ("none", None):
            p["offer"] = off.get("prev")
            od = off.get("dres") or {"status": "none"}
            return single_proposal(st, dict(inp, reply="none"), V, P, out, pm, today, p,
                                   {"status": "ok", "c": cents(off["amount"])}, dres if dres.get("status") != "none" else od)
        if reply == "no" and not proposes:
            p["offer"] = off.get("prev")
            return repeat_pending(st, out, V, P, pm, today)
    if multi:
        targets, _neg = scope_split(st, inp, P)
        if proposes and targets and p not in targets:
            for q in targets:
                apply_proposal(st, q, inp, V, P, out, pm, today, ar, dres, multi)
                if q["status"] == "refused":
                    q["status"], q["offer"] = "open", None
            if any(q["status"] == "open" and q.get("offer") and q["offer"].get("kind") != "today" for q in targets):
                return
            if p["status"] == "open":
                if not p.get("offer"):
                    return next_attempt(st, out, V, P, pm, today, p)
                return repeat_pending(st, out, V, P, pm, today)
            return next_product_or_close(st, out, V, P, pm, today)
        if proposes and targets and len(targets) > 1:
            return apply_group(st, inp, V, P, out, pm, today, ar, dres, targets)
    if proposes:
        return single_proposal(st, inp, V, P, out, pm, today, p, ar, dres)
    if intent == "too_much":
        return offer_floor(st, out, V, P, pm, today, p)
    acked_info = reply == "ack" and asked_before in ("info", "hold")
    if reply == "yes" or (reply == "ack" and off and off.get("kind") != "today" and not acked_info):
        if off:
            if not off.get("date"):
                # an amount without a day: a yes is no day (never today by default); ask once more, then the deadline
                if not p.get("day_reasked"):
                    p["day_reasked"] = True
                    p["exact_asked"] = True
                    out.say.append(L(P, "ask_exact_day", pm))
                    return
            elif off.get("kind") == "confirm_date":
                dd, cl = validate_date(p, {"status": "ok", "date": off["date"]}, P, pm, today, out, multi, False)
                if dd is None:
                    return
                accept(p, off["amount"], dd, cl)
                return next_product_or_close(st, out, V, P, pm, today)
            else:
                accept(p, off["amount"], off["date"])
                return next_product_or_close(st, out, V, P, pm, today)
    if acked_info:
        return repeat_pending(st, out, V, P, pm, today)  # 'okay' to an explanation answers nothing
    if reply == "no" or intent in ("refuse", "refuse_pay"):
        return next_attempt(st, out, V, P, pm, today, p)
    if reply == "ack":
        out.say.append(L(P, "repeat", pm))
        return repeat_pending(st, out, V, P, pm, today)
    # after asking for the exact day, still no day: propose the deadline (A21) before counting a non-answer
    if p.get("exact_asked") and not p.get("deadline_proposed") and off.get("kind") != "deadline":
        p["deadline_proposed"] = True
        dl = d_from(p["deadline"])
        p["offer"] = {"amount": off.get("amount", p["past_due"]), "date": d_iso(dl), "kind": "deadline"}
        out.say.append(offer_text(P, pm, p, p["offer"]["amount"], p["offer"]["date"], today, multi, multi))
        return
    u = norm(inp["utterance"])
    idx = st["products"].index(p)
    if u and HOLD.match(u) and bump(st, "hold%d" % idx) <= 2:
        st["asked"] = "hold"
        out.say.append(L(P, "wait_ok", pm))
        return
    if u and not HESITATE.search(u) and bump(st, "talk%d:%s" % (idx, off.get("kind", ""))) <= 1:
        return repeat_pending(st, out, V, P, pm, today)  # unrelated talk: ask once more before counting it
    # a non-answer uses one persuasion attempt (A30) unless nothing was understood at all
    if inp["utterance"]:
        return next_attempt(st, out, V, P, pm, today, p)
    if bump(st, "n%d" % idx) > 2:
        return next_attempt(st, out, V, P, pm, today, p)
    out.say.append(L(P, "repeat", pm))
    return repeat_pending(st, out, V, P, pm, today)


def offer_floor(st, out, V, P, pm, today, p):
    """'The full amount is too much' (A26): offer the floor once, on the pending day, and say the rest stays overdue.
    Said again after the floor was offered, it is a refusal of the floor (the next persuasion attempt)."""
    multi = len(st["products"]) > 1
    p["too_much"] = True
    if p["floor_offered"] or p["floor"] >= p["past_due"] - 0.005:
        return next_attempt(st, out, V, P, pm, today, p)
    p["floor_offered"] = True
    off = p.get("offer") or {}
    date = off.get("date")
    if off.get("kind") == "today" or (multi and date == d_iso(today)):
        # 'too much' answers the question about today: the one floor offer (A26) carries attempt 1's day (A30), so
        # the floor is named once; refusing it moves on to attempt 2 (refused offers are never repeated, A31)
        a1 = attempt_offer(p, P, today, 1)
        date = a1["date"] if a1 else date
    p["offer"] = {"amount": p["floor"], "date": date, "kind": "floor"}
    out.say.append(L(P, "floor_offer", pm, amount=money(p["floor"], cw(P))))
    out.say.append(L(P, "rest_overdue", pm))
    p["rest_said"] = True
    if not date:
        out.say.append(L(P, "ask_exact_day", pm))
    elif date == d_iso(today):
        out.say.append(L(P, "first_ask_single", pm) if not multi else offer_text(P, pm, p, p["floor"], date, today, multi, False))
    else:
        out.say.append(offer_text(P, pm, p, p["floor"], date, today, multi, False))


def single_proposal(st, inp, V, P, out, pm, today, p, ar, dres):
    """A proposal for one product, then the next step: the next product or the read-back, the next persuasion
    attempt (floor refused), or the counter-question already spoken."""
    apply_proposal(st, p, inp, V, P, out, pm, today, ar, dres, len(st["products"]) > 1)
    if p["status"] == "agreed":
        return next_product_or_close(st, out, V, P, pm, today)
    if p["status"] == "refused":
        p["status"] = "open"
        return next_attempt(st, out, V, P, pm, today, p)
    if not out.say:
        return repeat_pending(st, out, V, P, pm, today)


def apply_proposal(st, p, inp, V, P, out, pm, today, ar, dres, multi):
    """A date and/or amount the customer proposed for product p (never a refusal, A29). The day the customer did
    not mention stays what the pending question said, the amount likewise (A35)."""
    off = p.get("offer") or {}
    if dres.get("status") == "none":
        if off.get("date") and off.get("kind") != "today":
            dres = {"status": "ok", "date": off["date"]}
        elif off.get("kind") == "today" and inp.get("reply") == "yes":
            dres = {"status": "ok", "date": off.get("date") or d_iso(today)}  # 'yes, 700' answers 'today?'
    alt_day = date_alternative(p, dres, P, today)
    am = amount_for(st, p, ar)
    if am["status"] == "ambiguous":
        # an uncertain amount is checked with the customer, never rejected as below the floor (C)
        p["offer"] = {"amount": am["best"] / 100.0, "date": alt_day or off.get("date"), "kind": "confirm_amount",
                      "prev": dict((k, v) for k, v in off.items() if k not in ("prev", "dres")) or None, "dres": dres}
        out.say.append(L(P, "amount_check", pm, amount=money(am["best"] / 100.0, cw(P))))
        return
    if am["status"] == "ok":
        a = validate_amount(p, am["c"], P, pm, today, out, alt_day or off.get("date"))
        if a is None:
            return
        if a == -1:
            p["status"] = "refused"
            return
    else:
        a = off.get("amount", p["past_due"])
        if p["too_much"] and p["floor_offered"]:
            a = off.get("amount", p["floor"])
    if dres.get("status") == "none":
        p["offer"] = {"amount": a, "date": None, "kind": "amount_only"}
        p["exact_asked"] = True
        out.say.append(L(P, "ask_exact_day", pm))
        return
    d, clamped = validate_date(p, dres, P, pm, today, out, multi, False)
    if d is None:
        if p.get("offer"):
            p["offer"]["amount"] = a
        return
    accept(p, a, d, clamped)


def apply_group(st, inp, V, P, out, pm, today, ar, dres, targets):
    """One day (and maybe amount) for several products (B6). Each product is checked on its own: its own floor and
    full amount, its own deadline (a day after it is recorded on the deadline and the read-back says so). A question
    about the day is asked once for the whole group and remembered with the group (scope), never replaced by a
    generic persuasion offer."""
    targets = [p for p in targets if p["status"] == "open"]
    if len(targets) <= 1:
        if targets:
            return single_proposal(st, inp, V, P, out, pm, today, targets[0], ar, dres)
        return next_product_or_close(st, out, V, P, pm, today)
    s = dres.get("status")

    def ask_group(text, scope_date=None):
        st["multi_stage"] = "all_date"
        st["scope"] = [p["id"] for p in targets]
        if ar.get("status") not in ("none", None):
            st["scope_ar"] = ar
        st["scope_date"] = scope_date
        st["group_q"] = text
        for p in targets:
            p["exact_asked"] = True
        out.say.append(text)

    if s == "none" and ar.get("status") in ("none", None):
        return next_product_or_close(st, out, V, P, pm, today)
    own_days = [(p.get("offer") or {}).get("date") for p in targets
                if (p.get("offer") or {}).get("kind") not in (None, "today", "amount_only")]
    if s == "none" and len(own_days) == len(targets) and all(own_days):
        return settle_group(st, out, V, P, pm, today, ar, targets, None)
    if s in ("vague", "none", "ask"):
        if not st.get("all_exact_asked") or s == "ask":
            st["all_exact_asked"] = True
            return ask_group(L(P, "ask_exact_day", pm))
        dl = min(d_from(p["deadline"]) for p in targets)
        return ask_group(L(P, "deadline_offer", pm, date=spoken_date(dl, today)), d_iso(dl))
    if s == "past":
        return ask_group(L(P, "past_date", pm))
    if s == "conflict":
        return ask_group(L(P, "date_conflict", pm, date=spoken_date(d_from(dres["date"]), today)), dres["date"])
    d = d_from(dres["date"])
    if not is_business(d, P["calendar"]):
        nb = next_business_on_or_after(d, P["calendar"])
        return ask_group(L(P, "next_business_day_offer", pm, asked=spoken_date(d, today), date=spoken_date(nb, today)),
                         d_iso(nb))
    return settle_group(st, out, V, P, pm, today, ar, targets, d)


def settle_group(st, out, V, P, pm, today, ar, targets, d):
    """Accept the group's products on day d (None: each product's own pending day), each one checked against its
    own deadline, floor and full amount. A product that needs a question keeps it pending; the first is asked."""
    for p in targets:
        off = p.get("offer") or {}
        day0 = d or d_from(off.get("date"))
        dl = d_from(p["deadline"])
        day, clamped = (d_iso(dl), True) if day0 > dl else (d_iso(day0), False)
        am = amount_for(st, p, ar)
        if am["status"] == "none":
            a = off.get("amount", p["past_due"]) if off.get("kind") not in ("today", None) else p["past_due"]
            accept(p, a, day, clamped)
            continue
        if am["status"] == "ambiguous":
            p["offer"] = {"amount": am["best"] / 100.0, "date": day, "kind": "confirm_amount", "prev": None,
                          "dres": {"status": "ok", "date": day}}
            continue
        c = am["c"]
        if c < cents(p["floor"]):
            # below this product's floor: offer the floor once on the same day (A27); refused before -> attempts
            p["offer"] = None if p.get("below_floor_offered") else {"amount": p["floor"], "date": day, "kind": "floor",
                                                                     "below": True}
            p["below_floor_offered"] = p["floor_offered"] = True
            continue
        accept(p, min(c, cents(p["past_due"])) / 100.0, day, clamped)
    for p in targets:
        if p["status"] == "open" and p.get("offer"):
            st["cur"] = st["products"].index(p)
            if p["offer"].get("below"):
                out.say.append(L(P, "below_floor", pm, floor=money(p["floor"], cw(P))))
                if not out.say[-1].rstrip().endswith("?"):
                    out.say.append(offer_text(P, pm, p, p["offer"]["amount"], p["offer"]["date"], today, True, True))
                return
            return ask_pending(st, out, P, pm, today, p)
    return next_product_or_close(st, out, V, P, pm, today)


def snapshot_matches(st, inp, P, today):
    """A yes that repeats the read-back's own day or amount is still a yes to that read-back."""
    snap = st.get("snapshot") or []
    if not snap:
        return False
    dres, ar = inp["dres"], inp["ar"]
    byid = dict((p["id"], p) for p in st["products"])
    if dres.get("status") not in ("none", None) and not (dres.get("status") == "ok" and all(s["date"] == dres["date"] for s in snap)):
        return False
    if ar.get("status") not in ("none", None):
        for s in snap:
            am = amount_for(st, byid[s["pid"]], ar)
            if am["status"] != "ok" or am["c"] != cents(s["amount"]):
                return False
    return True


def step_confirm(st, inp, V, P, out, pm, today):
    reply, intent = inp["reply"], inp["intent"]
    bare_ack = bool(ACK_RE.match(norm(inp["utterance"]))) if inp["utterance"] else False
    has_values = inp["dres"].get("status") != "none" or inp["ar"].get("status") not in ("none", None)
    if reply == "yes" and not bare_ack and intent not in ("too_much",) and (not has_values or snapshot_matches(st, inp, P, today)):
        return start_writes(st, out, V, P, pm, today)
    pos, neg = scope_split(st, inp, P) if len(st["products"]) > 1 else ([], [])
    if has_values or intent in ("propose", "too_much", "vague_time") or neg:
        # a change at the read-back: re-validate and read back again (A35). Products the customer now refuses go
        # back to the persuasion attempts.
        agreed = [p for p in st["products"] if p["status"] == "agreed"]
        for p in neg:
            if p["status"] in ("agreed", "open"):
                p["status"] = "open"
                p["agreed"] = None
                p["offer"] = None
        targets = [p for p in pos if p not in neg] or ([] if neg else agreed[:1] if len(agreed) == 1 else agreed)
        if not (has_values or intent in ("propose", "too_much", "vague_time")):
            targets = []
        for p in targets:
            prev = p.get("agreed") or {}
            p["status"] = "open"
            p["offer"] = {"amount": prev.get("amount", p["past_due"]), "date": prev.get("date"), "kind": "change"}
        st["phase"] = "negotiate"
        st["change_asked"] = False
        if targets and intent == "too_much" and not has_values:
            st["cur"] = st["products"].index(targets[0])
            return offer_floor(st, out, V, P, pm, today, targets[0])
        if len(targets) > 1:
            return apply_group(st, inp, V, P, out, pm, today, inp["ar"], inp["dres"], targets)
        if targets:
            return single_proposal(st, inp, V, P, out, pm, today, targets[0], inp["ar"], inp["dres"])
        return next_product_or_close(st, out, V, P, pm, today)
    if reply == "no" and not st.get("change_asked"):
        # 'no' to the read-back: ask what to change; the agreed values stay the pending offers (A35)
        st["phase"] = "negotiate"
        st["change_asked"] = True
        for p in st["products"]:
            if p["status"] == "agreed":
                p["status"] = "open"
                p["offer"] = {"amount": p["agreed"]["amount"], "date": p["agreed"]["date"], "kind": "change"}
                p["agreed"] = None
        out.say.append(L(P, "ask_change", pm))
        return
    if reply == "no":
        # a second plain no: the customer does not want this promise (a flat refusal of the offer, A30)
        st["phase"] = "negotiate"
        for p in st["products"]:
            if p["status"] == "agreed":
                p["status"] = "open"
                p["offer"] = {"amount": p["agreed"]["amount"], "date": p["agreed"]["date"], "kind": "change"}
                p["agreed"] = None
        p = cur_product(st)
        return next_attempt(st, out, V, P, pm, today, p) if p else readback_or_close(st, out, V, P, pm, today)
    if bump(st, "confirm") > 3:
        for p in st["products"]:
            if p["status"] in ("agreed", "open"):
                p["status"] = "refused"
        return close_without_promise(st, out, V, P, pm, today)
    out.say.append(L(P, "readback", pm, items=readback_items(st, P, pm, today)))
    out.say.append(L(P, "confirm_question", pm))


def readback_items(st, P, pm, today):
    items = []
    for p in st["products"]:
        if p["status"] == "agreed":
            a = p["agreed"]
            key = "readback_clamped" if a.get("clamped") else "readback_item"
            items.append(L(P, key, pm, amount=money(a["amount"], cw(P)), product=p["phrase"],
                           date=spoken_date(d_from(a["date"]), today)))
    return join_and(items)


def ask_pending(st, out, P, pm, today, p):
    """Say product p's pending question: an amount check, the exact day for an amount without one, or the offer."""
    multi = len(st["products"]) > 1
    off = p["offer"]
    if off.get("kind") == "confirm_amount":
        line = L(P, "amount_check", pm, amount=money(off["amount"], cw(P)))
    elif not off.get("date"):
        line = L(P, "ask_exact_day", pm)
    else:
        return out.say.append(offer_text(P, pm, p, off["amount"], off["date"], today, multi, multi))
    out.say.append("For your %s: %s" % (p["phrase"], line[:1].lower() + line[1:]) if multi else line)


def start_writes(st, out, V, P, pm, today):
    """The customer confirmed the read-back: write exactly the snapshot (L5)."""
    snap = st.get("snapshot") or []
    byid = dict((p["id"], p) for p in st["products"])
    for k in range(1, 4):
        out.extra["wp%d_on" % k] = "no"
        out.extra["say_wp%d_ok" % k] = ""
        out.extra["say_wp%d_fail" % k] = ""
    for k, s in enumerate(snap[:3], 1):
        p = byid.get(s["pid"])
        out.extra["wp%d_on" % k] = "yes"
        out.extra["wp%d_pid" % k] = s["pid"]
        out.extra["wp%d_amount" % k] = float(s["amount"])
        out.extra["wp%d_date" % k] = s["date"]
        view = {"amount": money(s["amount"], P.get("currency_word", "dollars")), "product": p["phrase"] if p else s["pid"],
                "date": spoken_date(d_from(s["date"]), today)}
        out.extra["say_wp%d_ok" % k] = L(P, "recorded", pm, **view)
        out.extra["say_wp%d_fail" % k] = L(P, "record_failed", pm, **view)
    others = [p for p in st["products"] if p["status"] not in ("agreed",)]
    notes_multi = bool((P.get("notes") or {}).get("enabled")) and len(st["products"]) > 1
    if notes_multi:
        set_notes(st, out, V, P, others)
    else:
        for k in range(1, 4):
            out.extra["wn%d_on" % k] = "no"
    # a product whose write fails twice gets a service_error note in the chain itself (B11)
    out.extra["wf_on"] = "yes" if notes_multi else "no"
    out.extra["wf_reason"] = note_reason_for({"status": "failed"}, P) if notes_multi else ""
    st["writes_started"] = True
    # the chain ends on its own: any write ok -> the promise ending with 'farewell'; every write failed -> the
    # ending precomputed here (final_route/final_reason) with 'farewell_af'. No customer turn is needed.
    af = af_situation(st, P)
    set_outcome(V, P, af)
    st["outcome"] = "promise"
    V["farewell"] = " ".join([L(P, "after_promise", pm), P["lines"]["goodbye"]])
    V["farewell_af"] = P["lines"]["goodbye"]
    st["phase"] = "ended"
    out.route = "write_p1"


def af_situation(st, P):
    """The closing situation if every create_promise of this chain fails twice (Brief B closing rule)."""
    prods = st["products"]
    if not ((P.get("notes") or {}).get("enabled") and len(prods) > 1):
        return "service_error"
    for p in prods:
        if p["status"] in ("agreed", "recorded", "failed"):
            return "service_error"
        if p["status"] != "paid":
            return situation_for_status(p["status"])
    return "paid"


def absorb_writes(st, V):
    rec, fail = [], []
    for k in range(1, 4):
        if S(V, "wp%d_on" % k) != "yes":
            continue
        pid = S(V, "wp%d_pid" % k)
        ok1 = truthy(S(V, "wp%d_response.data.ok" % k))
        ok2 = truthy(S(V, "wp%dr_response.data.ok" % k))
        (rec if (ok1 or ok2) else fail).append(pid)
    st["recorded"], st["failed"] = rec, fail


def finish_after_fail(st, out, V, P, pm, today):
    """Reached only when at least one write failed twice: recorded ones stay; failed ones are noted (B11)."""
    rec, fail = st.get("recorded") or [], st.get("failed") or []
    for p in st["products"]:
        if p["id"] in rec:
            p["status"] = "recorded"
        elif p["id"] in fail:
            p["status"] = "failed"
    notes_on = (P.get("notes") or {}).get("enabled")
    if rec:
        sit = "promise"
    else:
        sit = "service_error"
    if notes_on and len(st["products"]) > 1:
        set_notes(st, out, V, P, [p for p in st["products"] if p["id"] in fail])
    else:
        for k in range(1, 4):
            out.extra["wn%d_on" % k] = "no"
    set_outcome(V, P, sit)
    st["outcome"] = sit
    st["phase"] = "ended"
    pre = [L(P, "after_promise", pm)] if rec else []
    V["farewell"] = " ".join(pre + [P["lines"]["goodbye"]])
    out.route = "write_n1" if out.extra.get("wn1_on") == "yes" else V["final_route"]
