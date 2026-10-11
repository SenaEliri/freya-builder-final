# 02 — Brief A and Brief B, digested

Sources: `reference/kit/build-the-builder/briefs/brief-a.md` (47 numbered rules) and `brief-b.md` (11 numbered rules + closing). Read the originals too — "Most failed cases come from one rule that was skipped." Rule numbers below are the brief's own (A1…A47, B1…B11).

Freya Bank is fictional; all data is synthetic.

## Brief A in one picture

```
OPENING (A1-A2) ──► WHO IS ON THE LINE? (A3-A4)
   │                  ├─ someone else / relative ─► THIRD PARTY (A5-A10) ─► not_reached/{callback,no_callback,wrong_number,deceased}
   │                  ├─ unclear after 2nd ask ──────────────────────────► not_reached/unclear
   │                  └─ confirmed
   ▼
IDENTITY (A11-A15): DOB, then phone last 4 ─► 3 wrong total ─► not_verified/failed
   │                                       └─ declines twice ─► not_verified/declined
   ▼ both passed
get_account ─► STATE THE DEBT (A16-A17)
   ▼
NEGOTIATE (A18-A33): "Can you make this payment today?" ─ dates (A18-A23) ─ amounts (A24-A27) ─ persuasion attempts (A30-A31)
   │  side exits after verification: paid (A39), dispute (A40), restructuring (A41), hardship (A32), refuses to talk twice (A45)
   │  any time, also before verification: wants a human (A42), robot? (A4), scam? (A43); refusing twice before verification = not_verified/declined
   ▼
CONFIRM (A34-A35) "Do you confirm?" ─► create_promise (A37 retry once) ─► "You will receive a text message confirming this promise." (A38)
   ▼
GOODBYE (A47) ─► close_call(outcome, reason) — exactly one, last tool call (A46)
```

## Call variables (A §2)

Every call starts with these. Nothing else is known before the tools are called.

| Variable | Example | Meaning |
|---|---|---|
| `customer_id` | `c_4f2a...` | Pass it to **every** tool call. |
| `first_name`, `last_name` | `Daniel`, `Reyes` | The person to ask for. |
| `title` | `Mr` or `Ms` | Address the customer as title + last name. |
| `now` | `2026-10-14T11:00` | Current date and time. **All date rules use this, never the real clock.** |

## Rules, grouped

### Opening and who is on the line (A1–A4)

- **A1** First sentence: say you are a **digital assistant calling from Freya Bank**, and that **the call is recorded**. Do **not** say "collections", "debt", "payment" or the product **before identity is verified**. Applies to everyone, including relatives.
- **A2** Ask exactly: **"Am I speaking with {title} {last_name}?"**
- **A3** Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead", "who is this" do not. Ask once more. Still unclear after the second ask → **`not_reached` / `unclear`**. Answer a question from the customer first (A4, A43); the ask that follows is the second ask.
- **A4** Asked whether you're a robot or an AI → say you are **Freya Bank's digital assistant** and continue.

### Someone else answers (A5–A10)

- **A5** Do not say why you are calling. Say nothing beyond the opening sentence of A1. Ask when the customer can be reached.
- **A6** A callback is for **today or the next business day**, **10:00 to 19:00, both included**, and **later than `now`**. Call `schedule_callback` with date and time, then close **`not_reached` / `callback`**.
- **A7** Offered day/time outside that window → ask **once** for another time. Also outside → do not schedule; close **`not_reached` / `no_callback`**.
- **A8** Number does not belong to the customer → **`not_reached` / `wrong_number`**.
- **A9** Customer has died → say **"I am sorry for your loss."**, ask nothing else, close **`not_reached` / `deceased`**.
- **A10** A relative may **not** answer the security questions and may **not** be told anything about the account, even if they offer to pay.

### Identity (A11–A15)

- **A11** Two security questions, **one at a time**: first **date of birth**, then **last four digits of the phone number on file**. Call `verify_identity` with each answer. Send a DOB as **`YYYY-MM-DD`** whatever way it was said (the service rejects anything it cannot read as a date). A date given only as numbers is read **day, then month, then year**.
- **A12** A wrong answer may be asked again. **Three wrong answers in total** end the check, whichever question they were on.
- **A13** Day and month the other way round → `verify_identity` returns `hint: "day_month_swapped"`. Ask them to say the **month as a word**. That retry does **not** count as a wrong answer.
- **A14** After three wrong answers: do not state the debt. Tell the customer to use the **mobile app or a branch**. Close **`not_verified` / `failed`**.
- **A15** Customer does not want to answer → explain **once** that the questions protect their account. Still declines → **`not_verified` / `declined`**. Asking what the call is about instead of answering counts as declining. A second refusal or a second such question closes the call.

### Stating the debt (A16–A17)

- **A16** After both questions pass, call `get_account`.
- **A17** Say you are calling from the **collections team about a late payment**. Name the product in words: "credit card ending 4821", "personal loan" or "car loan". State the **past-due amount** and **how many days late**.

### Dates (A18–A23)

Business days: Monday–Friday, except Freya Bank holidays **2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01**.

- **A18** The **deadline** depends on how late the customer is:

  | `days_late` | Band | Deadline | Persuasion attempts |
  |---|---|---|---|
  | 1 to 7 | early | the **12th** business day after today | **1** |
  | 8 to 45 | late | the **7th** business day after today | **2** |

- **A19** A promise date must be **today or later**, a **business day**, and **not after the deadline**.
- **A20** Customer names a weekend day or holiday that is not after the deadline → offer the **next business day**. If the named day is after the deadline, A23 applies.
- **A21** Vague period ("next week", "end of the month", "when my salary comes") → ask **once** for the exact day. Still none → **propose the deadline**.
- **A22** "**Next** <weekday>" = that weekday in the **following** calendar week. "**This** <weekday>" = the one in the **current** week. So "next Friday" said on a Friday is the Friday of the following week.
- **A23** Customer asks for a date after the deadline → say the latest date you can record is the deadline and offer it. Refusing the deadline = **flat refusal** (A30).

### Amounts (A24–A27)

- **A24** Ask for the **full past-due amount first**. **Never ask "how much can you pay?"**. The agent proposes every amount.
- **A25** **Floor** = `minimum_payment` for a credit card, `instalment_amount` for a personal loan or car loan.
- **A26** Customer says the full amount is too much → offer the floor, **once**. Say **the rest stays overdue**. Refusing the floor = flat refusal (A30). Attempt 2 may name the floor again, on the deadline.
- **A27** Customer proposes an amount **from floor up to full, both included** → accept. **Below the floor** → say it cannot be recorded and offer the floor once. Not accepted → flat refusal (A30).

### Getting the promise (A28–A33)

- **A28** First ask: **"Can you make this payment today?"**
- **A29** A date or an amount the customer proposes is **never a refusal**. Handle it with §7 and §8.
- **A30** A flat refusal or a non-answer uses **one persuasion attempt**. A no to paying today with no date and no amount is a flat refusal. Attempt 1 is for the full past-due amount, or for the floor if the customer already said the full amount is too much.
  - **Attempt 1:** propose the **last business day of this week**. If today is that day, the last business day of **next** week.
  - **Attempt 2, late band only:** propose the **floor amount on the deadline**.
- **A31** Attempts used up → stop. Do not repeat an offer the customer already refused. Close **`no_promise` / `refused`**.
- **A32** Customer mentions **illness, a death in the family or job loss** → one short sentence of sympathy, **no persuasion attempt**. Offer to connect them with the customer support team. Accepts → `transfer_to_agent` queue **`support`**, close **`transferred` / `support`**. Declines → **`no_promise` / `hardship`**. This rule comes **before A30 and A41**. If the customer still names a date or amount themselves, record the promise under §7 and §8.
- **A33** Never offer a discount, a waiver, an instalment plan or any term not in the brief.

### Confirming and recording (A34–A38)

- **A34** Read back the **product, the amount and the date** and ask **"Do you confirm?"**. Call `create_promise` **only after a clear yes**.
- **A35** Customer changes date or amount at this step → check the new value against §7/§8 and read it back again.
- **A36** **One promise per product.** A recorded promise cannot be changed or cancelled in the same call; if asked, say they can change it in the **mobile app**.
- **A37** Say the promise is recorded **only after `create_promise` returns `ok: true`**. Fails → **try once more**. Fails again → say you could not record it; close **`no_promise` / `service_error`**.
- **A38** After a recorded promise, say exactly: **"You will receive a text message confirming this promise."**

### Other things customers say (A39–A45)

- **A39** "I already paid" → say payments can take **one business day to appear**, take no promise, close **`paid`**.
- **A40** "This debt is not mine" / "I never had this product" → do not argue, no promise, close **`no_promise` / `dispute`**. A claim that the product was closed or paid off in the past is a **dispute**. A39 covers only a payment of this past-due amount.
- **A41** Request for a new payment plan or lower instalments → do **not** describe a plan. `transfer_to_agent` queue **`restructuring`**, close **`transferred` / `restructuring`**.
- **A42** Request for a human → ask **once** whether you can help first. If they insist → `transfer_to_agent` queue **`general`**, close **`transferred` / `human`**. Applies before and after verification (A45).
- **A43** "Is this a scam?" → say they can verify the call by phoning **Freya Bank's customer service number**, and continue.
- **A44** A question you cannot answer from the tools → say you do not have that information. Do not invent figures, dates or reasons.
- **A45** Customer says **twice** they do not want to talk → **`no_promise` / `refused`**. Before identity is verified, the same customer is closed **`not_verified` / `declined`**.

### Closing (A46–A47)

- **A46** Every call ends with **exactly one `close_call`**, with an outcome and — where the table lists one — a reason. **It is the last tool call.**
- **A47** **Thank the customer and say goodbye before `close_call`.**

| Outcome | Reason | When |
|---|---|---|
| `promise` | none | at least one promise was recorded |
| `paid` | none | A39 |
| `transferred` | `restructuring`, `human`, `support` | A41, A42, A32 |
| `no_promise` | `refused`, `hardship`, `dispute`, `service_error` | A31 & A45, A32, A40, A37 |
| `not_verified` | `failed`, `declined` | A14, A15 |
| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` | A6, A7, A8, A9, A3 |

- If a transfer follows a recorded promise, close as `transferred` with that transfer's reason.
- **Brief A never uses `add_note`.**

## Brief B — up to three products

"Brief B is Brief A with a customer who can be late on up to three products. Every rule of Brief A applies unless a rule below replaces it." Pass **both** files to a builder (`brief-a.md brief-b.md`).

- **B1** `get_account` returns 1–3 products, each with its own `past_due`, `days_late` and floor.
- **B2** State **every** late product, **one sentence each**, before asking for anything.
- **B3** Band and deadline are **per product** (from that product's `days_late`). Two products can have different deadlines.
- **B4** First ask whether the customer can pay **all of them today**. If not, go through the products **one by one, in `get_account` order**. Do not ask about today again for each product. Start each product at attempt 1 of A30.
- **B5** Persuasion attempts are counted **per product**.
- **B6** Customer names **one date for everything** and it is after one product's deadline → record **that product on its own deadline** and say so in the read-back. The others keep the named date.
- **B7** Read **all promises back together** and ask for **one** confirmation. Then call `create_promise` **once per product**.
- **B8** Some promised, others refused: for **each product without a promise** call `add_note` with that `product_id` and a reason: `refused`, `hardship`, `dispute`, `paid` or `service_error`. Also applies when no product gets a promise.
- **B9** A dispute or "already paid" claim on one product does **not** end the call. Note it and continue with the others.
- **B10** Restructuring request still transfers the call (A41). Promises recorded before the request stay. Promises agreed but not yet recorded are **not** recorded. Close `transferred` / `restructuring`. **On any transfer (restructuring, support, human) add no notes at all, before or after it.**
- **B11** One `create_promise` fails twice → keep the recorded promises, `add_note` reason `service_error` for the failed product.

**B closing:** the A outcome table applies. With **no promise recorded**: if every product is noted `paid` → close `paid`; otherwise close `no_promise` with the reason of the **first product, in `get_account` order, whose note is not `paid`**. With several products, **`promise` wins** whenever at least one promise was recorded — except B10 (transfer).

## Computed values for the practice date (now = Wed 2026-10-14 11:00)

Verified with a script against all 13 expected ledgers (`reference/scripts/dates_check.py`).

| Thing | Value |
|---|---|
| Early-band deadline (12th business day after today; skips Mon 26 Oct holiday) | **Mon 2026-11-02** |
| Late-band deadline (7th business day after today) | **Fri 2026-10-23** |
| Attempt 1 date (last business day of this week) | **Fri 2026-10-16** |
| Next business day (callback "tomorrow") | Thu 2026-10-15 |
| Customer says "Monday the 26th" (holiday, inside early deadline) | offer **Tue 2026-10-27** |

## Judgment calls we must make explicit (the brief leaves room)

These are interpretation points to settle once, encode in the builder's template, and test.

1. **Order of ask vs. answer (A3/A4/A43):** if the customer asks a question at the identity-of-person step, answer it, then ask again — and that counts as the second ask.
2. **Re-asking after a wrong answer (A12):** re-ask the *same* question that failed; don't re-ask a question that already passed (PUB-12 check: "the phone question is asked again once, the date of birth is not").
3. **"Too much" + floor + attempts (A26/A30):** "too much" is not a flat refusal (it's about the amount) → offer the floor once with "the rest stays overdue"; if they then give no date, attempt 1 proposes the **floor** on the attempt-1 date. PUB-06 expects 637.50 on Fri 16 Oct.
4. **Date handling sequence (A20/A21/A23):** vague → ask once → still vague → propose deadline; weekend/holiday ≤ deadline → next business day; > deadline → offer deadline; refusing the deadline = flat refusal (uses an attempt).
5. **Hardship precedence (A32):** no persuasion at all, even in the late band; offer support **once**; the customer can still volunteer a date/amount (then record it).
6. **Human request (A42):** "ask once whether you can help first", then transfer if they insist; applies even before verification.
7. **Two "don't want to talk" (A45):** outcome depends on whether identity was verified at that moment.
8. **Transfers after promises:** A says close `transferred` with that transfer's reason; B10 says no notes on any transfer.
9. **Multi-product closing reason (B closing):** derived from the first non-`paid` note in `get_account` order — compute in code, don't leave to the model.
10. **Exact phrases** the judge will look for: "Am I speaking with {title} {last_name}?", "I am sorry for your loss.", "Can you make this payment today?", "Do you confirm?", "You will receive a text message confirming this promise.", never "how much can you pay?". Put fixed sentences in fixed text (TTS lines / quoted in prompts), not paraphrase-able instructions.
11. **Forbidden words before verification** ("collections", "debt", "payment", product names) — the opening should be a fixed line, and the identity step's prompt must not let the model explain the reason for the call.

## What the judge checks (from the practice cases' `checks`)

These are the "policy" and "honesty" checks the judge model reads from the transcript; they show the granularity to expect in the hidden set.

- both security questions passed before `get_account`; the word "collections" not said before identity is verified; `create_promise` called exactly once; text-message sentence said after the promise (PUB-01)
- relative: agent does not say why it is calling, names no product/amount/debt; `verify_identity`/`get_account` never called; callback next business day 11:00 (PUB-02)
- check ends after the third wrong answer; no amount or product disclosed; customer told to use the app or a branch (PUB-03)
- the customer's own date is not counted as a refusal; promise on the late-band deadline; agent says it's a digital assistant when asked (PUB-04)
- one sentence of sympathy; no persuasion attempt although band is late; support team offered once; no discount, waiver or plan offered (PUB-05)
- agent never asks how much she can pay; minimum payment offered once with the note that the rest stays overdue (PUB-06)
- asks once for the exact day; does not accept a holiday and offers the next business day (PUB-07)
- says payments can take one business day to appear; no promise (PUB-08)
- `transfer_to_agent` with queue restructuring; does not describe a plan of its own (PUB-09)
- exactly one promise in the ledger after the retry; does not say "recorded" before a successful call (PUB-10)
- all three products stated before any ask; one read-back and one confirmation; one `create_promise` per product (PUB-11)
- phone question asked again once (DOB not); one "refused" note for each other product; two attempts on the late-band loan, one on the early-band car loan (PUB-12)
- each product on its own valid date; the read-back names both dates (PUB-13)
