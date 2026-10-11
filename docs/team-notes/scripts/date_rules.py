"""Brief-A-style date rules as plain functions (stdlib only: datetime).

Everything is parameterised (holidays, weekend, bands) so a builder can fill the values from a spec
instead of hard-coding Brief A. Contains no double-brace sequences, so the functions can be pasted into a Freya code node (code must not contain them).
Run this file to self-test it on dates taken from the practice cases (dates_check.py checks all 13 expected ledgers).
"""
import datetime as dt

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def is_business_day(d, holidays, weekend=(5, 6)):
    return d.weekday() not in weekend and d.isoformat() not in holidays


def nth_business_day_after(today, n, holidays, weekend=(5, 6)):
    d, k = today, 0
    while k < n:
        d += dt.timedelta(days=1)
        if is_business_day(d, holidays, weekend):
            k += 1
    return d


def next_business_day_on_or_after(d, holidays, weekend=(5, 6)):
    while not is_business_day(d, holidays, weekend):
        d += dt.timedelta(days=1)
    return d


def last_business_day_of_week(d, holidays, weekend=(5, 6)):
    """Last business day of the Monday-Sunday week containing d (None if the week has none)."""
    monday = d - dt.timedelta(days=d.weekday())
    for i in range(6, -1, -1):
        x = monday + dt.timedelta(days=i)
        if is_business_day(x, holidays, weekend):
            return x
    return None


def attempt1_date(today, holidays, weekend=(5, 6)):
    """Brief A rule 30: last business day of this week; if today is that day, last business day of next week."""
    x = last_business_day_of_week(today, holidays, weekend)
    if x is None or x <= today:
        x = last_business_day_of_week(today + dt.timedelta(days=7), holidays, weekend)
    return x


def resolve_weekday(today, weekday_name, mode):
    """Brief A rule 22: 'this <weekday>' = in the current Monday-Sunday week; 'next <weekday>' = in the following week."""
    target = WEEKDAYS.index(weekday_name.lower())
    monday = today - dt.timedelta(days=today.weekday())
    if mode == "next":
        monday += dt.timedelta(days=7)
    return monday + dt.timedelta(days=target)


def deadline_for(today, days_late, bands, holidays, weekend=(5, 6)):
    """bands: list of dicts like {"min": 1, "max": 7, "nth_business_day": 12, "attempts": 1, "name": "early"}."""
    for b in bands:
        if b["min"] <= days_late <= b["max"]:
            return nth_business_day_after(today, b["nth_business_day"], holidays, weekend), b
    return None, None


def check_promise_date(today, wanted, deadline, holidays, weekend=(5, 6)):
    """Returns (verdict, date_to_offer). verdict: ok | before_today | not_business_day | after_deadline."""
    if wanted < today:
        return "before_today", None
    if wanted > deadline:
        return "after_deadline", deadline
    if not is_business_day(wanted, holidays, weekend):
        nxt = next_business_day_on_or_after(wanted, holidays, weekend)
        return "not_business_day", (nxt if nxt <= deadline else deadline)
    return "ok", wanted


if __name__ == "__main__":
    HOL = {"2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"}
    BANDS = [{"name": "early", "min": 1, "max": 7, "nth_business_day": 12, "attempts": 1},
             {"name": "late", "min": 8, "max": 45, "nth_business_day": 7, "attempts": 2}]
    t = dt.date(2026, 10, 14)
    assert deadline_for(t, 5, BANDS, HOL)[0] == dt.date(2026, 11, 2)
    assert deadline_for(t, 14, BANDS, HOL)[0] == dt.date(2026, 10, 23)
    assert attempt1_date(t, HOL) == dt.date(2026, 10, 16)
    assert attempt1_date(dt.date(2026, 10, 16), HOL) == dt.date(2026, 10, 23)        # today is Friday
    assert resolve_weekday(dt.date(2026, 10, 16), "friday", "next") == dt.date(2026, 10, 23)
    assert resolve_weekday(t, "friday", "this") == dt.date(2026, 10, 16)
    assert check_promise_date(t, dt.date(2026, 10, 26), dt.date(2026, 11, 2), HOL) == ("not_business_day", dt.date(2026, 10, 27))
    assert check_promise_date(t, dt.date(2026, 11, 6), dt.date(2026, 10, 23), HOL) == ("after_deadline", dt.date(2026, 10, 23))
    assert nth_business_day_after(t, 1, HOL) == dt.date(2026, 10, 15)
    print("all date-rule checks pass")
