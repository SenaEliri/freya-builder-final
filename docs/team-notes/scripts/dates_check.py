"""Check Brief A date rules against the practice cases' expected dates.

Usage (from the hack folder): python3 reference/scripts/dates_check.py reference/kit/build-the-builder/public-test-set.json
"""
import datetime as dt, json, sys
HOL = {dt.date(2026,10,26), dt.date(2026,11,11), dt.date(2026,11,26), dt.date(2026,12,25), dt.date(2027,1,1)}
def is_bd(d): return d.weekday() < 5 and d not in HOL
def nth_bd_after(d, n):
    k = 0
    while k < n:
        d += dt.timedelta(days=1)
        if is_bd(d): k += 1
    return d
def next_bd_on_or_after(d):
    while not is_bd(d): d += dt.timedelta(days=1)
    return d
def last_bd_of_week(d):
    friday = d + dt.timedelta(days=4 - d.weekday())
    x = friday
    while not is_bd(x): x -= dt.timedelta(days=1)
    return x
def deadline(today, days_late):
    return nth_bd_after(today, 12 if days_late <= 7 else 7)
today = dt.date(2026, 10, 14)
print('today', today, today.strftime('%A'))
print('early deadline (12th bd)', deadline(today, 5), deadline(today, 5).strftime('%a'))
print('late  deadline (7th bd) ', deadline(today, 8), deadline(today, 8).strftime('%a'))
lb = last_bd_of_week(today); print('attempt-1 date (last bd this week)', lb, lb.strftime('%a'))
print('next bd after 2026-10-26 holiday', next_bd_on_or_after(dt.date(2026,10,26)))
print('next business day after today (callback)', nth_bd_after(today, 1))
cases = json.load(open(sys.argv[1]))
for c in cases:
    for i, p in enumerate(c['products']):
        print(c['id'], f"p{i+1}", p['type'], 'days_late', p['days_late'], 'band', 'early' if p['days_late'] <= 7 else 'late', 'deadline', deadline(today, p['days_late']), 'floor', p.get('minimum_payment', p.get('instalment_amount')))
    for pr in c['expected']['promises']:
        d = dt.date.fromisoformat(pr['date']); idx = int(pr['product_id'][1:]) - 1
        dl = deadline(today, c['products'][idx]['days_late'])
        print('   promise', pr, 'business day' if is_bd(d) else 'NOT BUSINESS DAY', '<= deadline' if d <= dl else 'AFTER DEADLINE')
