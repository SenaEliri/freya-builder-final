# Northgate Savings Bank — material for the collections caller

Northgate Savings Bank is fictional. All customers, debts and payments are synthetic. This file is a test
fixture written by the team to check that the builder reads raw bank material; it is not an event brief.

---

**From:** Priya Lindqvist, Head of Early Collections
**To:** Voice automation vendor
**Date:** 2 September 2026
**Subject:** What we need from the reminder calls

Hi team,

as discussed, the assistant phones customers who are a few days or weeks behind on a Northgate product. Most
have one product, some have two (a credit card and an overdraft). Please keep it short and polite. The very
first thing the caller hears must be that this is Northgate's automated assistant and that the call may be
recorded, then ask for the customer by title and surname: "Am I speaking with {title} {last_name}?"

Nothing about money, arrears, collections or the product may be said before the customer passed security.
If someone else picks up, we only want to know when to call back.

The policy team will send you the formal extract; Legal changed a few things last month (see their memo).

Thanks, Priya

---

## Policy extract CP-7 (2025 edition), section 4 "Reminder calls"

4.1 Security. Ask for the postcode of the registered address first, then the customer's year of birth, one
at a time, and check each with the bank's verification service. Two wrong answers in total end the check;
the customer is then told to visit northgate.example/help or call the number on the back of their card, and
the call is closed as not identified (failed). A customer who refuses to answer gets one explanation that the
questions keep their account safe; a second refusal closes the call as not identified (declined).

4.2 Someone else answers. Say nothing about the reason for the call. Ask when the customer is available. A
callback may be booked for today or the next working day between 09:00 and 17:00 (both included) and must be
later than the current time. If the time offered is outside the window, ask once more; otherwise close as no
contact (no callback). Wrong number and deceased customers are closed as no contact with the matching reason;
for a deceased customer say "Please accept our condolences." and nothing else.

4.3 Working days are Monday to Friday. Bank holidays 2026: 12 October, 26 October, 25 December, 28 December.

4.4 Promise window. The latest promise date depends on lateness:

| Days late | Group | Latest promise date | Extra offers |
|---|---|---|---|
| 1-10 | A | 10th working day after today | 1 |
| 11-60 | B | 5th working day after today | 2 |

A promise date must be a working day, not in the past and not after the latest promise date. A weekend or a
holiday inside the window moves to the next working day. "Next Tuesday" means the Tuesday of the following week.

4.5 Amounts. Always ask for the whole overdue amount first, payable today. Never ask the customer what they can
afford. If the whole amount is too much, offer the minimum once and say "The remaining balance stays overdue."
The minimum is the `minimum_due` of a credit card and the `monthly_minimum` of an overdraft.

4.6 Extra offers. A refusal uses one extra offer. Offer 1: the whole amount (or the minimum, if the customer
already said the whole amount is too much) on the last working day of the current week (next week if today is
that day). Offer 2 (group B only): the minimum on the latest promise date. After the offers stop and close as
no promise (refused).

4.7 Read the product, amount and date back and ask "Is that correct?". Record only after a clear yes. After a
recorded promise say "You will get a text message with the details." Retry a failed recording once; if it fails
again, say so and close as no promise (technical error).

4.8 Several products: name each one, ask once whether all can be paid today, then go product by product. Each
product without a promise gets a note with the matching reason code.

4.9 Customers who report serious illness, a death in the family or losing their job: one sentence of sympathy,
no extra offers, offer the general service team; accepted -> transfer (queue GENERAL, close as transferred,
hardship); declined -> no promise (hardship). Requests for a new instalment plan go to queue RESTR (transferred,
restructuring). A customer who insists on a person after one offer of help goes to queue GENERAL (transferred,
human). "I already paid" -> say payments can take two working days to show, close as paid. Disputes -> no
promise (dispute).

---

## Memo from Legal, 30 September 2026 — amendments to CP-7 section 4 (in force from 5 October 2026)

1. Group B: the latest promise date is now the **6th** working day after today (was the 5th).
2. Add 30 October 2026 as a bank holiday for the reminder calls.
3. Replace the sentence after a recorded promise by: "We will send you an SMS to confirm."
4. Hardship transfers no longer go to GENERAL. Use the new queue CARE (close as transferred, hardship).

---

## Code list for the close_call tool (from the core banking team)

| Code | Meaning |
|---|---|
| PTP | promise to pay recorded |
| PAID | customer says already paid |
| XFR | transferred to a person |
| NPTP | verified, no promise |
| NOID | not identified |
| NOCT | no contact with the customer |

Reason codes:

| Outcome | Reason code | Meaning |
|---|---|---|
| XFR | RESTR | restructuring request |
| XFR | HUMAN | asked for a person |
| XFR | HARD | hardship |
| NPTP | REF | refused / offers used up |
| NPTP | HARD | hardship, transfer declined |
| NPTP | DISP | dispute |
| NPTP | TECH | technical error |
| NOID | FAIL | wrong answers |
| NOID | DECL | declined security |
| NOCT | CB | callback booked |
| NOCT | NOCB | no callback possible |
| NOCT | WRONG | wrong number |
| NOCT | DEAD | deceased |
| NOCT | UNCL | unclear who answered |

PTP and PAID take no reason code. Note reasons use the same codes as NPTP (REF, HARD, DISP, TECH) plus PAID.
