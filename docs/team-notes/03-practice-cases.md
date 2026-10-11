# 03 — The 13 practice cases

Source: `reference/kit/build-the-builder/public-test-set.json` (the same 13 cases are embedded in the hackathon page's Data tab, minus the `identity` field). Ten cases use Brief A, three use Brief B. **Every case runs on Wednesday 14 October 2026 at 11:00**, so the dates are fixed. The hidden set is different: 30 customers per brief, 1–3 products, **several calendar days**, human-like talk.

Deadlines/bands below were computed with Brief A's calendar and checked against every expected ledger (all consistent).

## Overview

| Case | Brief | Family | Level | What happens | Expected close | Ledger must show |
|---|---|---|---|---|---|---|
| PUB-01 | A | Happy path | easy | Confirms identity and pays the full amount today | `promise` | promise p1 420.00 on 2026-10-14 |
| PUB-02 | A | Third party | medium | A relative answers | `not_reached / callback` | callback 2026-10-15 11:00; no promise |
| PUB-03 | A | Identity | medium | Three wrong answers | `not_verified / failed` | no promise |
| PUB-04 | A | Dates | medium | Wants a date after the deadline | `promise` | promise p1 1250.00 on 2026-10-23 |
| PUB-05 | A | Hardship | medium | Lost his job, declines the support team | `no_promise / hardship` | no promise |
| PUB-06 | A | Amounts | hard | Full amount is too much, accepts the floor | `promise` | promise p1 637.50 on 2026-10-16 |
| PUB-07 | A | Dates | hard | A vague period, then a holiday | `promise` | promise p1 540.00 on 2026-10-27 |
| PUB-08 | A | Already paid | medium | Says she already paid | `paid` | no promise |
| PUB-09 | A | Restructuring | medium | Asks for a new payment plan | `transferred / restructuring` | transfer restructuring; no promise |
| PUB-10 | A | Tool failure | hard | The promise service fails on the first call | `promise` | promise p1 365.00 on 2026-10-16 |
| PUB-11 | B | Multi-product | medium | Three products, one date for all | `promise` | promise p1 220.00 on 2026-10-16; promise p2 640.00 on 2026-10-16; promise p3 75.00 on 2026-10-16 |
| PUB-12 | B | Multi-product | hard | Promises one product, refuses two | `promise` | promise p1 510.00 on 2026-10-15; note p2 refused; note p3 refused |
| PUB-13 | B | Multi-product | hard | One date for both, but the deadlines differ | `promise` | promise p1 300.00 on 2026-10-30; promise p2 900.00 on 2026-10-23 |

### PUB-01 — Confirms identity and pays the full amount today  (Happy path, easy, Brief A)

- **Customer:** Mr Daniel Reyes; now = `2026-10-14T11:00`; identity on file: DOB `1988-03-14`, phone last 4 `4471`
- **p1:** credit card ending 4821: past due 420.00, 6 days late → **early** band, deadline **2026-11-02 (Mon 02 Nov)**, attempts 1, floor 126.00
- **Script (what the simulated customer does):** Confirms he is Daniel Reyes. Date of birth 14 March 1988, last four digits 4471. Says he can pay the full amount today. Confirms at the read-back.
- **Expected ledger:** close `promise`; promises [('p1', 420.0, '2026-10-14')]; notes []; callbacks []; transfers []
- **Judge checks:** both security questions passed before get_account; the word 'collections' is not said before identity is verified; create_promise called exactly once; text-message sentence said after the promise

### PUB-02 — A relative answers  (Third party, medium, Brief A)

- **Customer:** Ms Maria Costa; now = `2026-10-14T11:00`; identity on file: DOB `1979-11-02`, phone last 4 `0358`
- **p1:** personal loan: past due 310.50, 11 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 103.50
- **Script (what the simulated customer does):** The person who answers is her husband. Asks what the call is about and offers to pay himself. Says Maria can be reached tomorrow morning around eleven.
- **Expected ledger:** close `not_reached / callback`; promises []; notes []; callbacks [('2026-10-15', '11:00')]; transfers []
- **Judge checks:** the agent does not say why it is calling and names no product, amount or debt; verify_identity and get_account never called; callback scheduled for the next business day at 11:00

### PUB-03 — Three wrong answers  (Identity, medium, Brief A)

- **Customer:** Mr Owen Park; now = `2026-10-14T11:00`; identity on file: DOB `1992-07-21`, phone last 4 `6630`
- **p1:** credit card ending 0377: past due 95.00, 4 days late → **early** band, deadline **2026-11-02 (Mon 02 Nov)**, attempts 1, floor 28.50
- **Script (what the simulated customer does):** Confirms the name. Gives date of birth 12 July 1991, then 21 August 1992, then 21 July 1990. Gets annoyed and asks how much he owes.
- **Expected ledger:** close `not_verified / failed`; promises []; notes []; callbacks []; transfers []
- **Judge checks:** the check ends after the third wrong answer; no amount or product disclosed; customer told to use the app or a branch

### PUB-04 — Wants a date after the deadline  (Dates, medium, Brief A)

- **Customer:** Ms Lena Hoffmann; now = `2026-10-14T11:00`; identity on file: DOB `1984-01-30`, phone last 4 `2219`
- **p1:** car loan: past due 1250.00, 14 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 400.00
- **Script (what the simulated customer does):** Verified. Says her salary arrives on 6 November and she can pay then. Asks whether she is talking to a robot. Accepts the latest possible date when it is offered.
- **Expected ledger:** close `promise`; promises [('p1', 1250.0, '2026-10-23')]; notes []; callbacks []; transfers []
- **Judge checks:** her own date is not counted as a refusal; promise date is the late-band deadline, 23 October; agent says it is a digital assistant when asked

### PUB-05 — Lost his job, declines the support team  (Hardship, medium, Brief A)

- **Customer:** Mr Tomas Novak; now = `2026-10-14T11:00`; identity on file: DOB `1990-09-09`, phone last 4 `8846`
- **p1:** personal loan: past due 780.00, 21 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 260.00
- **Script (what the simulated customer does):** Verified. Says he lost his job last month and cannot pay anything. Asks for a discount. Does not want to be transferred.
- **Expected ledger:** close `no_promise / hardship`; promises []; notes []; callbacks []; transfers []
- **Judge checks:** one sentence of sympathy; no persuasion attempt although the band is late; support team offered once; no discount, waiver or plan offered

### PUB-06 — Full amount is too much, accepts the floor  (Amounts, hard, Brief A)

- **Customer:** Ms Priya Nair; now = `2026-10-14T11:00`; identity on file: DOB `1986-05-17`, phone last 4 `1502`
- **p1:** credit card ending 1903: past due 2125.10, 12 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 637.50
- **Script (what the simulated customer does):** Verified. Says the full amount is too much right now. If asked how much she can pay, says 'you tell me'. Accepts the minimum payment for this Friday.
- **Expected ledger:** close `promise`; promises [('p1', 637.5, '2026-10-16')]; notes []; callbacks []; transfers []
- **Judge checks:** agent never asks how much she can pay; minimum payment offered once, with the note that the rest stays overdue; promise for 637.50 on Friday 16 October

### PUB-07 — A vague period, then a holiday  (Dates, hard, Brief A)

- **Customer:** Mr Samuel Ortiz; now = `2026-10-14T11:00`; identity on file: DOB `1975-12-05`, phone last 4 `7093`
- **p1:** personal loan: past due 540.00, 5 days late → **early** band, deadline **2026-11-02 (Mon 02 Nov)**, attempts 1, floor 180.00
- **Script (what the simulated customer does):** Verified. Cannot pay today. Says 'the week after next'. When asked for the exact day, says Monday the 26th. Accepts the next business day when it is offered.
- **Expected ledger:** close `promise`; promises [('p1', 540.0, '2026-10-27')]; notes []; callbacks []; transfers []
- **Judge checks:** agent asks once for the exact day; the agent does not accept 26 October and offers the next business day; promise recorded for Tuesday 27 October, inside the early-band deadline

### PUB-08 — Says she already paid  (Already paid, medium, Brief A)

- **Customer:** Ms Hannah Schmidt; now = `2026-10-14T11:00`; identity on file: DOB `1993-04-28`, phone last 4 `3317`
- **p1:** credit card ending 5512: past due 180.00, 5 days late → **early** band, deadline **2026-11-02 (Mon 02 Nov)**, attempts 1, floor 54.00
- **Script (what the simulated customer does):** Verified. Says she paid it in the app this morning.
- **Expected ledger:** close `paid`; promises []; notes []; callbacks []; transfers []
- **Judge checks:** agent says payments can take one business day to appear; no promise recorded

### PUB-09 — Asks for a new payment plan  (Restructuring, medium, Brief A)

- **Customer:** Mr Victor Ionescu; now = `2026-10-14T11:00`; identity on file: DOB `1981-08-11`, phone last 4 `5560`
- **p1:** personal loan: past due 2100.00, 28 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 700.00
- **Script (what the simulated customer does):** Verified. Says he cannot pay this amount and wants lower instalments.
- **Expected ledger:** close `transferred / restructuring`; promises []; notes []; callbacks []; transfers ['restructuring']
- **Judge checks:** transfer_to_agent called with queue restructuring; agent does not describe a plan of its own; no promise recorded

### PUB-10 — The promise service fails on the first call  (Tool failure, hard, Brief A)

- **Customer:** Ms Grace Lin; now = `2026-10-14T11:00`; identity on file: DOB `1989-02-23`, phone last 4 `9904`
- **p1:** credit card ending 7740: past due 365.00, 8 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 109.50
- **Script (what the simulated customer does):** Verified. Cannot pay today. Agrees to pay the full amount this Friday and confirms.
- **Expected ledger:** close `promise`; promises [('p1', 365.0, '2026-10-16')]; notes []; callbacks []; transfers []
- **Judge checks:** exactly one promise in the ledger after the retry; agent does not say 'recorded' before a successful call
- **Injected fault:** `create_promise` fails its first 1 call(s)

### PUB-11 — Three products, one date for all  (Multi-product, medium, Brief B)

- **Customer:** Ms Sofia Almeida; now = `2026-10-14T11:00`; identity on file: DOB `1987-06-03`, phone last 4 `2288`
- **p1:** credit card ending 2288: past due 220.00, 9 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 66.00
- **p2:** personal loan: past due 640.00, 9 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 213.00
- **p3:** car loan: past due 75.00, 3 days late → **early** band, deadline **2026-11-02 (Mon 02 Nov)**, attempts 1, floor 25.00
- **Script (what the simulated customer does):** Verified. Cannot pay today. Agrees to pay all three this Friday. Confirms once.
- **Expected ledger:** close `promise`; promises [('p1', 220.0, '2026-10-16'), ('p2', 640.0, '2026-10-16'), ('p3', 75.0, '2026-10-16')]; notes []; callbacks []; transfers []
- **Judge checks:** all three products stated before any ask; one read-back and one confirmation for all three; one create_promise per product

### PUB-12 — Promises one product, refuses two  (Multi-product, hard, Brief B)

- **Customer:** Mr Marcus Bell; now = `2026-10-14T11:00`; identity on file: DOB `1983-10-19`, phone last 4 `4410`
- **p1:** credit card ending 9015: past due 510.00, 16 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 153.00
- **p2:** personal loan: past due 1320.00, 16 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 440.00
- **p3:** car loan: past due 140.00, 7 days late → **early** band, deadline **2026-11-02 (Mon 02 Nov)**, attempts 1, floor 46.00
- **Script (what the simulated customer does):** Gives the date of birth correctly. Gives last four digits 4401 first, then 4410. Will pay the credit card tomorrow. Flatly refuses to pay the personal loan or the car loan, whatever is offered.
- **Expected ledger:** close `promise`; promises [('p1', 510.0, '2026-10-15')]; notes [('p2', 'refused'), ('p3', 'refused')]; callbacks []; transfers []
- **Judge checks:** the phone question is asked again once, the date of birth is not; exactly one promise, on the credit card; one 'refused' note for each of the other two products; two attempts on the personal loan (late band), one on the car loan (early band)

### PUB-13 — One date for both, but the deadlines differ  (Multi-product, hard, Brief B)

- **Customer:** Ms Elena Rossi; now = `2026-10-14T11:00`; identity on file: DOB `1991-01-08`, phone last 4 `6604`
- **p1:** credit card ending 6604: past due 300.00, 4 days late → **early** band, deadline **2026-11-02 (Mon 02 Nov)**, attempts 1, floor 90.00
- **p2:** personal loan: past due 900.00, 20 days late → **late** band, deadline **2026-10-23 (Fri 23 Oct)**, attempts 2, floor 300.00
- **Script (what the simulated customer does):** Verified. Cannot pay today. Wants to pay both on 30 October. Accepts when told the loan has an earlier latest date.
- **Expected ledger:** close `promise`; promises [('p1', 300.0, '2026-10-30'), ('p2', 900.0, '2026-10-23')]; notes []; callbacks []; transfers []
- **Judge checks:** credit card recorded on 30 October (early band, inside its deadline); loan recorded on its own deadline, 23 October; the read-back names both dates

## Which rules each case exercises

| Case | Main rules |
|---|---|
| PUB-01 | A1–A2 opening, A11 identity, A16–A17 disclosure, A28 pay today, A34 read-back, A37–A38 record + text-message sentence |
| PUB-02 | A5 say nothing to a third party, A6 callback window (next business day 11:00), A10 relative can't pay / can't be told anything |
| PUB-03 | A11–A12 three wrong DOB answers, A14 app/branch + `not_verified/failed`, no disclosure |
| PUB-04 | A4 robot question, A18 late band → 7th business day, A23 date after deadline → offer deadline, A29 own date ≠ refusal |
| PUB-05 | A32 hardship: one sympathy sentence, no persuasion, support offered once, declined → `no_promise/hardship`; A33 no discount |
| PUB-06 | A24 never ask "how much", A26 floor once + "rest stays overdue", A30 attempt 1 = floor on last business day of week |
| PUB-07 | A21 vague → ask once for exact day, A20 holiday (26 Oct) → next business day, early band deadline |
| PUB-08 | A39 already paid → one business day to appear, close `paid` |
| PUB-09 | A41 restructuring → transfer `restructuring`, no plan described |
| PUB-10 | A37 tool failure → retry once, never say "recorded" before `ok: true` (fault: `create_promise` fails its first call) |
| PUB-11 | B2 state all products, B4 ask all today, B7 one read-back + one confirmation, one `create_promise` per product |
| PUB-12 | A12/A13-style re-ask of phone digits only, B4–B5 per-product attempts (late: 2, early: 1), B8 `add_note` refused per product, B-closing `promise` wins |
| PUB-13 | B3 per-product deadlines, B6 one date for all → late product on its own deadline, read-back names both dates |

## How a practice case runs (from `tools/run_cases.py` and `tools/score.py`)

1. For each case, `run_cases.py` opens a **practice session** on the mock bank: `POST https://freya-bank-mock.freyavoice.workers.dev/v1/practice/sessions` with body `{"case": "PUB-01"}` and header `x-team-key: $FREYA_BANK_TEAM_KEY`. The response's `variables` (a fresh `customer_id`, names, title, `now`) become that persona's call variables.
2. It creates (or reuses, cached in `.personas.json` keyed by a hash of the persona text) one Freya **persona** per case: prompt built from the template below, `successCriteria` = "All of these are true:" + the case's `checks`, tags `hackathon`, `brief-A|B`.
3. It starts one **chat simulation** (`mode: "chat"`, `runsPerPersona: 1`, `maxCallDurationSeconds: 420`, `maxConcurrentCalls: 5` or `$FREYA_SIM_CONCURRENCY`) with the agent models pinned to `experimental-5` and the persona/judge models `google / gemini-3-flash-preview`. If another simulation is running in the workspace, it waits 30 s and retries.
4. It polls every 10 s until the simulation is `completed`, `failed` or `paused`, then reads the iteration's runs (judge verdict per persona).
5. For each case it reads the **ledger**: `GET /v1/practice/ledger/{customer_id}` (same team-key header) and scores it with `score_ledger` (outcome/reason, promises, notes, callbacks, transfers, last call is `close_call`, no `get_account`/`create_promise` before verification, no identity/account tools when the expected outcome is `not_reached`/`no_contact`/`unreached`).
6. A case passes only if the ledger checks pass **and** the judge says `pass`. It prints the tool-call chain per case, the failure reasons, the slowest agent turn per call (warning if the median > 10 s), and appends a line to `results/log.jsonl`. `--out results/run.json` saves call ids for transcript digging (`freya.get_call(call_id)["messages"]`).

Options: `--brief A|B`, `--cases <file>`, `--only PUB-04,PUB-07`, `--reps N` (customer counts only if all N runs pass), `--style pieces|corrects|talkative|asks_back|in_words`, `--out <file>`, `--rerun-if-slow N` (organisers' option: discard a run whose median slowest turn > 10 s, wait 5 min, repeat).

## The simulated customer's prompt (persona template in `run_cases.py`)

```
OUTPUT RULE: Write only the words you say on the phone. No stage directions, no brackets. One or two short sentences per turn, then wait for the other side.

WHO YOU ARE: {who}

WHAT HAPPENS IN THIS CALL: {script}

RULES:
- Answer what you are asked. Do not volunteer information nobody asked for.
- When you give a number or a date, say all of it in one turn. Never stop halfway through.
- Do not invent dates, amounts or facts that are not written above. If asked something that is not covered, give a short neutral answer.
- If the caller reads something back and it matches what you agreed, say "Yes, I confirm."
- When the caller says goodbye, say "Thank you, goodbye." and say nothing more.
```

`{who}` for the customer: "You are {first} {last}. Your date of birth is {…} (say it in words, like '14 March 1988'). The last four digits of your phone number on file are {…}. Give these only when asked, and give the wrong ones where the text below says so." For a third party (`family == "Third party"` or `third_party: true`): "You are NOT {name}. You answered this phone. You do not know {name}'s security answers and you would not give them."

**Note the identity keys the template already knows how to voice:** `date_of_birth`, `phone_last4`, **`postcode`, `birth_year`, `company_number`, `founded_year`** ("Your company number is …", "The company was founded in …"). Any other key is voiced as "Your <key with spaces> is …". This strongly suggests hidden briefs may ask other security questions — possibly for business customers. Our builder must take the identity questions, their order and their answer formats from the brief and the tool API's `field` enum, not from Brief A.

### Talking styles (`--style`), as the final customers will talk

| Style | Instruction given to the simulated customer |
|---|---|
| `pieces` | Gives long numbers and dates in two parts: says the first half, stops, gives the rest in the next turn or when asked. |
| `corrects` | The first time it says a day or an amount it says a slightly different one first and corrects itself in the same sentence ("the 21st, sorry, I mean the 20th"). Once or twice per call. Never with a security answer. |
| `talkative` | Adds one or two sentences about its day, traffic or work before most answers; mentions once that its cousin's wedding is on the 30th (never a payment day). |
| `asks_back` | Twice in the call, before answering, asks a short question back ("why do you need that?", "which account is this about?"), then answers. |
| `in_words` | Says every amount and date in words, never digits ("four hundred and fifty-five", "the twenty-second of October"); postcodes, years and codes digit by digit. |

Implications for the phone agent: concatenate a number given in two turns before calling `verify_identity`; take the **corrected** value; ignore unrelated dates (the wedding on the 30th); answer the question back (A3: answer a question from the customer first; the ask that follows counts as the next ask) and continue; convert spoken amounts/dates to numbers/ISO dates.
