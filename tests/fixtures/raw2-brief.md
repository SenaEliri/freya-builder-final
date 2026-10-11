# Kestrel Business Finance — material for the arrears reminder line

Kestrel Business Finance is fictional. All companies, people, debts and payments are synthetic. This file is a team test
fixture for the builder (raw bank material, second shape); it is not an event brief.

---

**Ticket CX-4471 (export from the service desk)**

> **Opened by:** Ruth Okafor, Business Arrears
> **Summary:** Spec for the automated reminder caller (business customers)
>
> We call small companies that are behind on a facility with us. Most have one facility; some have two (a term loan and
> a revolving credit line). Each call comes with `customer_id`, `company_name`, `contact_name` and `now` (date and time of
> the call, e.g. 2026-11-03T10:15). That's all we know before the tools are used.
>
> Opening, word for word please: "Good morning, this is Kestrel Business Finance's automated assistant, and we may record
> this call. May I speak with {contact_name} of {company_name}?"
>
> Our people get very nervous about disclosure: no amounts, no facility names, not the words "arrears" or "overdue"
> until security is complete. Same if a colleague or receptionist answers: just find out when {contact_name} is
> back.

**Comment — Tomasz (Security):** Security is two checks, in this order: the company registration number (8 digits),
then the year the company was founded. Use the verification service for each. Two wrong answers in total and we stop:
tell them to call the number on their latest statement, close as ID failed (detail WRONG). If they won't do security,
explain once that it protects the company's account; a second refusal closes the call (ID failed, detail REFUSED).

**Comment — Ruth:** Callbacks: only the next business day, 08:30 to 16:00 (inclusive). Never today. If they offer
something outside that, ask once more, then give up (no contact, detail NO_CALLBACK). Wrong number → no contact,
detail WRONG_NUMBER. If they tell us the contact has died: "Please accept my condolences." and close (no contact,
detail DECEASED).

---

### Arrears handling note AH-12 (v3)

Business days: Monday to Friday. Office closures: 2026-11-11, 2026-12-24, 2026-12-25, 2026-12-31.

Stages by days overdue:

- Stage 1 — 1 to 14 days overdue: latest promise date = 15 calendar days after today. One extra offer.
- Stage 2 — 15 to 90 days overdue: latest promise date = 5th business day after today. Two extra offers.

A promise date must be a business day, today or later, and not after the latest promise date; a weekend or closure day
inside the window moves to the next business day. "Next Monday" means Monday of the following week; "this Monday" means
the current week.

Opening ask: the full overdue amount, today. Don't ask what they can afford. If the full amount is too much, offer the
minimum once (term loan: the instalment; revolving credit: the minimum repayment) and say "Any remaining balance stays
overdue."

Extra offers (each refusal uses one):
1. the full amount, or the minimum if they already said the full amount is too much, on the last business day of this
   week (next week if today is that day);
2. Stage 2 only: the minimum on the latest promise date.
When the offers are used up, stop and close as no promise (detail REFUSED).

Read the facility, amount and date back and ask "Can you confirm that?" before recording. After a recorded promise say:
"You will receive written confirmation by email." If recording fails twice, say so and close as no promise (detail
SYSTEM).

Two facilities: name both, ask once if both can be paid today, then go facility by facility. Every facility without a
promise gets a note.

Hardship (illness, a bereavement, the business closing down): one sentence of sympathy, no extra offers, offer the
customer service desk; yes → transfer to SERVICE (transferred, detail HARDSHIP); no → no promise (detail HARDSHIP).
Wants a new repayment plan → transfer to WORKOUT (transferred, detail PLAN). Insists on a person after one offer of
help → CREDIT_CONTROL (transferred, detail PERSON). "Already paid" → say payments take up to two business days to show
and close as already paid. Disputes the debt → no promise (detail DISPUTE).

---

**Memo, 2 November 2026 — Head of Arrears: changes to AH-12, effective immediately**

(a) The office will be OPEN on 2026-12-24; remove it from the closures.
(b) Stage 1 latest promise date becomes 20 calendar days after today.
(c) The read-back question is now "Is that right?".

---

**Code list (core systems)**

`result`: PROMISE_TO_PAY · ALREADY_PAID · TRANSFERRED · NO_PROMISE · ID_FAILED · NO_CONTACT

`detail` per result:

| result | detail values |
|---|---|
| TRANSFERRED | PLAN, PERSON, HARDSHIP |
| NO_PROMISE | REFUSED, HARDSHIP, DISPUTE, SYSTEM |
| ID_FAILED | WRONG, REFUSED |
| NO_CONTACT | CALLBACK, NO_CALLBACK, WRONG_NUMBER, DECEASED, UNCLEAR |

PROMISE_TO_PAY and ALREADY_PAID carry no detail. Notes (`note`): NP-REF refused, NP-HARD hardship, NP-DISP dispute,
NP-TECH system failure, PAID already paid. A callback that was booked closes as NO_CONTACT / CALLBACK; if it stays
unclear who answered, NO_CONTACT / UNCLEAR.
