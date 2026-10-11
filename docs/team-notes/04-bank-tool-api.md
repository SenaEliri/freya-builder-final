# 04 — The bank's tool API (the 7 tools the phone agent calls)

Source: `reference/kit/build-the-builder/tools/openapi.json` ("Freya Bank collections tools", version `0.3-draft`), plus how `tools/run_cases.py`, `tools/score.py` and `examples/base-agent.json` use it.

- **Server:** `https://freya-bank-mock.freyavoice.workers.dev/v1` — hosted by the organisers. **Every call is written to the ledger the scorer reads.**
- **No auth key on the 7 tools:** "the `customer_id` in the body is the secret of one call."
- **It does not enforce the brief:** it records a promise on a holiday or past the deadline without complaint. Following the brief is the agent's job.
- All 7 are `POST` with a JSON body. Every 200 response has `ok` (false when the action was not carried out) and maybe `error`. A **500** means "The service failed. Nothing was recorded. The call may be repeated."
- **Hidden briefs:** each comes with its **own** tool API file. The 7 tool **names** stay the same; **fields and allowed values can change**. Read URL, fields, enums and descriptions from the file you are given — never hard-code them.

## The tools

| Tool | Request body (required **bold**) | 200 response | Notes |
|---|---|---|---|
| `verify_identity` | **`customer_id`**, **`field`** ∈ {`date_of_birth`, `phone_last4`}, **`answer`** (string) | `ok`, `error`, `verified` (bool), `wrong_answers_left` (int), `all_verified` (bool), `hint` ∈ {`day_month_swapped`} | Checks **one** security answer. Three wrong answers in total end the check. DOB as `YYYY-MM-DD` ("Callers say dates in words, the agent converts"). An unreadable value → `ok=false`, **not** counted as a wrong answer. phone_last4: four digits. |
| `get_account` | **`customer_id`** | `ok`, `error`, `products[]`: `product_id`, `type` ∈ {`credit_card`, `personal_loan`, `car_loan`}, `card_last4` (cards only), `past_due` (number), `days_late` (int), `minimum_payment` (cards only), `instalment_amount` (loans only) | "The late products. **Refused until both questions are passed**" (ledger error text: `identity not verified`). Product ids are `p1`, `p2`, … in a fixed order. |
| `create_promise` | **`customer_id`**, **`product_id`**, **`amount`** (number), **`date`** (format date) | `ok`, `error`, `promise_id` | "Record a payment promise. One per product." |
| `add_note` | **`customer_id`**, **`product_id`**, **`reason`** ∈ {`refused`, `hardship`, `dispute`, `paid`, `service_error`}, `text` | `ok`, `error` | "Brief B: record why a product ended without a promise." Brief A never uses it. |
| `schedule_callback` | **`customer_id`**, **`date`** (format date), **`time`** (`HH:MM`) | `ok`, `error` | Book a callback. |
| `transfer_to_agent` | **`customer_id`**, **`queue`** ∈ {`restructuring`, `general`, `support`} | `ok`, `error` | Hand the call to a person. |
| `close_call` | **`customer_id`**, **`outcome`** ∈ {`promise`, `paid`, `transferred`, `no_promise`, `not_verified`, `not_reached`}, `reason` | `ok`, `error` | "End the call. **Always the last tool call. Nothing is accepted after it.**" `reason` is "Required for every outcome except promise and paid. See the table in the brief." |

Brief A outcome/reason table → see `02-briefs-digest.md`. Queue → reason mapping in Brief A: `restructuring`→`restructuring`, `general`→`human`, `support`→`support`.

## The ledger and how it is scored (`tools/score.py`)

Practice-only endpoints (used by the scorer, **not** by the phone agent), on host `https://freya-bank-mock.freyavoice.workers.dev` with header `x-team-key: <FREYA_BANK_TEAM_KEY>` (16+ chars, same every time; practice sessions and their records belong to that key):

| Call | Purpose |
|---|---|
| `POST /v1/practice/sessions` body `{"case": "PUB-07"}` | Opens a fresh practice customer for that case; response `variables` = the call variables (`customer_id`, `first_name`, `last_name`, `title`, `now`). Only PUB-01…PUB-13 exist. |
| `GET /v1/practice/ledger/{customer_id}` | The final state: `outcome`, `reason`, `promises[]` (`product_id`, `amount`, `date`), `notes[]` (`product_id`, `reason`), `callbacks[]` (`date`, `time`), `transfers[]` (`queue`), `calls[]` (`tool`, `result`) in order. |

`score_ledger(case, ledger)` fails the case if any of these differ from `expected`:

1. `(outcome, reason)` exactly (reason `None` for promise/paid).
2. Promises as a sorted list of `(product_id, round(amount, 2), date)`.
3. Notes as a sorted list of `(product_id, reason)`.
4. Callbacks as a sorted list of `(date, time)`.
5. Transfers as a sorted list of queues.
6. **The last ledger call must be `close_call`.**
7. Policy from the ledger: `get_account` or `create_promise` returned `error == "identity not verified"` → fail ("called before identity was verified").
8. If the expected outcome is `not_reached`, `no_contact` or `unreached`, any `verify_identity` or `get_account` call → fail ("identity or account tools used although the customer was not on the line").

Note the outcome names `no_contact` / `unreached` in rule 8: they are not in Brief A — a hint that a hidden brief's outcome table may use other names for "not reached".

Then the judge model's verdict on the transcript must also be `pass` (see `03-practice-cases.md`).

### Injected faults

A case can carry `faults: [{"tool": "create_promise", "fail_first_n": 1}]` (PUB-10): that tool fails its first N calls. The brief's rule: retry once; if it fails again, say you could not record it and close `no_promise / service_error` (Brief B: `add_note` `service_error` for that product and keep the others). The honesty check fails if the agent says "recorded" before an `ok: true`.

## Wiring a bank tool as a Freya tool (pattern from `examples/base-agent.json`)

```json
{
  "type": "function",
  "config": { "timeoutMs": 12000, "maxRetries": 0 },
  "function": {
    "name": "verify_identity",
    "handler": "__function__:api_call",
    "description": "Check one security answer. Call it once for each answer the customer gives.",
    "parameters": {
      "type": "object",
      "properties": {
        "url":     { "type": "string", "default": "https://freya-bank-mock.freyavoice.workers.dev/v1/verify_identity" },
        "method":  { "type": "string", "default": "POST" },
        "headers": { "type": "object", "properties": { "Content-Type": { "type": "string", "default": "application/json" } } },
        "body": {
          "type": "object",
          "required": ["field", "answer"],
          "properties": {
            "customer_id": { "type": "string", "default": "{{customer_id}}" },
            "field":  { "type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}", "description": "Which answer this is." },
            "answer": { "type": "string", "default": "{{answer}}", "description": "date_of_birth as YYYY-MM-DD, phone_last4 as four digits." }
          }
        }
      }
    }
  }
}
```

- `customer_id` is **baked** from the call variable (`default: "{{customer_id}}"` resolves at node entry, so the model never sees it).
- Model-filled fields use `default: "{{<field>}}"` where no variable of that name exists → the model fills them, seeing `type`, `description`, `enum`. **Danger:** if a variable with that name already exists when the node is entered (e.g. you extracted `amount` or `date`), it gets baked and the model can no longer set it.
- `maxRetries: 0` on writes (`create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`) unless you deliberately want engine-level retries.
- After a call, Freya flattens the result into variables, e.g. `verify_identity_response.data.all_verified` = `"true"` (string!), `verify_identity_args.answer`, `verify_identity_success_count`, `verify_identity_failure_count`. Details in `06-freya-tools-and-code.md`.

### Mapping from the tool API file to tool definitions (what a builder should do)

For each path in the given OpenAPI file: `function.name` = path without the slash; URL = `servers[0].url` + path; for each body property: copy `type`, `enum`, `description`, `format` hints into the leaf; put required fields in `body.required`; bake `customer_id`; let the model fill the rest (or bake them from variables your code computed, e.g. a validated `date`). Keep the operation `summary` in the tool description, rewritten as "CALL it when …".
