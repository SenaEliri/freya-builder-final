# 09 — Strategy and plan for a team of two (our recommendations)

Everything above this file is what the sources say. **This file is opinion**: a proposed approach derived from those facts. Challenge it.

## What actually wins

1. **Reliability over cleverness.** A case counts only if all 3 runs pass, and the phone agent runs on a fixed, possibly modest model (`experimental-5`). Anything computable (dates, deadlines, floors, attempt counts, which outcome/reason, product order) should be computed in **code** (code nodes, hooks) and handed to the model as finished facts. The kit says it twice: "Prefer rules in routes and code over rules in prompts."
2. **Generalisation.** The hidden briefs change identity questions, limits, deadlines, outcome table, calendar, tool fields and enum values — and one brief is messy raw material (mail + policy extract + a memo that changes it + a code list). The builder must **read**, not remember. Nothing about Freya Bank may be hard-coded (and after 17:00 UTC nothing from the hidden briefs may be added).
3. **Honesty and exact phrases are cheap points.** Fixed TTS lines for required sentences; post-hooks that tell the model the truth after every tool call.
4. **Tie-breaks:** promised amount on passed cases (always go for the full amount first — the brief requires it anyway), then build time (keep the hidden-brief build short), then submission time.

## Proposed builder architecture: "compile, don't improvise"

```
python3 builder/build.py <brief.md> [<more briefs>] <tools.openapi.json>

 1. trace: start time, inputs (paths + sha256), builder version (git commit)
 2. SPEC  — LLM reads brief(s) + tool API → spec.json (strict JSON schema, below)
            raw material: merge sources, later memo overrides earlier policy, map code lists to enum values
            second LLM pass: rule-by-rule coverage check against the brief text; fix gaps
 3. CHECK — validate spec in code: enums ⊆ tool-API enums, dates parse, bands cover 1..max, every outcome in table reachable
 4. EMIT  — our Python templates turn spec → workflow JSON (deterministic):
            tools from the OpenAPI file (URL, fields, enums, descriptions) • code node for date facts from `now`
            post-hooks with `what_to_do_next` • node prompts from templates + quoted exact phrases + per-node rule lists
            outcome/reason bookkeeping + invariants in code
 5. SAVE  — lint (no nulls, passthrough → always, no {{ }} in code, all paths reach end_call) → dry run → save_workflow(slot) (create → update → publish)
 6. TEST  — time-boxed self-tests (see "Testing"); log every test + result in the trace
 7. EXPORT — freya.export_workflow → submission/<slot>.workflow.json ; trace: end time, workflow id, agent id, #nodes, #tools
```

Why this split: the LLM is good at reading messy text; templates are good at producing the same correct structure every time. Rules that don't fit any spec slot go into a `free_text_rules` list that the emitter injects into the relevant node prompts, so nothing in the brief is silently dropped.

**Alternative (faster to start):** extend the kit's agentic example builder (Claude Agent SDK + skill), which already built a 10/10-in-one-run agent for Brief A. Use it tonight as a **baseline and a reference design** (save the workflow it produces), then move the fragile parts into deterministic code. Watch its time: three fix loops × 3–11 min of simulation can exceed 30 min, and it can't run `run_cases.py` on hidden briefs.

### Spec sketch (starting point, extend as needed)

```json
{
  "bank": "Freya Bank",
  "call_variables": {"customer_id": "...", "first_name": "...", "last_name": "...", "title": "...", "now": "YYYY-MM-DDTHH:MM"},
  "address_as": "{title} {last_name}",
  "opening": {"first_sentence_must_include": ["digital assistant calling from Freya Bank", "call is recorded"],
              "person_check_question": "Am I speaking with {title} {last_name}?",
              "confirmations": ["yes", "that's me", "speaking", "<own name>"], "max_asks": 2,
              "forbidden_before_verification": ["collections", "debt", "payment", "<product words>"]},
  "third_party": {"disclose_nothing": true,
                  "callback": {"days": ["today", "next_business_day"], "from": "10:00", "to": "19:00", "inclusive": true, "must_be_after_now": true, "reask_once": true},
                  "outcomes": {"callback": ["not_reached", "callback"], "no_callback": ["not_reached", "no_callback"],
                               "wrong_number": ["not_reached", "wrong_number"], "deceased": ["not_reached", "deceased"], "unclear": ["not_reached", "unclear"]},
                  "deceased_line": "I am sorry for your loss."},
  "identity": {"questions": [{"field": "date_of_birth", "ask": "date of birth", "send_as": "YYYY-MM-DD", "numeric_order": "DMY"},
                             {"field": "phone_last4", "ask": "last four digits of the phone number on file", "send_as": "4 digits"}],
               "one_at_a_time": true, "max_wrong_total": 3,
               "hints": {"day_month_swapped": "ask for the month as a word; retry not counted"},
               "on_failed": {"say": "use the mobile app or a branch", "close": ["not_verified", "failed"]},
               "on_decline": {"explain_once": "the questions protect their account", "close": ["not_verified", "declined"]}},
  "disclosure": {"say": "calling from the collections team about a late payment",
                 "product_words": {"credit_card": "credit card ending {card_last4}", "personal_loan": "personal loan", "car_loan": "car loan"},
                 "state": ["past_due", "days_late"]},
  "calendar": {"weekend": [5, 6], "holidays": ["2026-10-26", "..."]},
  "bands": [{"name": "early", "min": 1, "max": 7, "deadline": {"nth_business_day_after_today": 12}, "attempts": 1},
            {"name": "late", "min": 8, "max": 45, "deadline": {"nth_business_day_after_today": 7}, "attempts": 2}],
  "floor_field": {"credit_card": "minimum_payment", "personal_loan": "instalment_amount", "car_loan": "instalment_amount"},
  "negotiation": {"first_ask": "Can you make this payment today?", "never_ask": ["how much can you pay?"],
                  "attempts": [{"n": 1, "amount": "full (floor if customer said full is too much)", "date": "last business day of this week (next week if today is it)"},
                               {"n": 2, "bands": ["late"], "amount": "floor", "date": "deadline"}],
                  "vague_date": "ask once for exact day, else propose deadline",
                  "weekend_or_holiday": "offer next business day", "after_deadline": "say latest recordable date is the deadline and offer it",
                  "floor_offer": "once, say the rest stays overdue", "forbidden_terms": ["discount", "waiver", "instalment plan"]},
  "confirm": {"read_back": ["product", "amount", "date"], "question": "Do you confirm?", "after_recorded": "You will receive a text message confirming this promise."},
  "tool_failure": {"retry_once": true, "close": ["no_promise", "service_error"]},
  "intents": [
    {"name": "already_paid", "say": "payments can take one business day to appear", "close": ["paid", null]},
    {"name": "dispute", "close": ["no_promise", "dispute"]},
    {"name": "restructuring", "transfer_queue": "restructuring", "close": ["transferred", "restructuring"]},
    {"name": "human", "ask_once_first": true, "transfer_queue": "general", "close": ["transferred", "human"]},
    {"name": "hardship", "sympathy": "one sentence", "offer_transfer_queue": "support", "accepted": ["transferred", "support"], "declined": ["no_promise", "hardship"]},
    {"name": "scam", "say": "verify by phoning Freya Bank's customer service number", "continue": true},
    {"name": "robot", "say": "I am Freya Bank's digital assistant", "continue": true},
    {"name": "refuses_to_talk_twice", "verified": ["no_promise", "refused"], "unverified": ["not_verified", "declined"]}],
  "multi_product": {"state_all_first": true, "ask_all_today_once": true, "order": "get_account",
                    "attempts_per_product": true, "single_date_after_deadline": "use that product's deadline and say so",
                    "single_readback_and_confirmation": true,
                    "notes": {"tool": "add_note", "for": "each product without a promise", "reasons": ["refused", "hardship", "dispute", "paid", "service_error"]},
                    "no_notes_on_transfer": true, "closing_reason": "first non-paid note in get_account order"},
  "outcome_table": [["promise", null], ["paid", null], ["transferred", "restructuring|human|support"], ["no_promise", "refused|hardship|dispute|service_error"],
                    ["not_verified", "failed|declined"], ["not_reached", "callback|no_callback|wrong_number|deceased|unclear"]],
  "free_text_rules": [{"node": "negotiate", "rule": "..."}]
}
```

### A workflow shape to start from (sketch)

| Node | Type | Job |
|---|---|---|
| `setup` | code, passthrough, initial | compute date facts from `now` + spec calendar (today's weekday, a 3–4 week table with business-day flags, band deadlines, attempt-1 date, callback window) → `{{date_facts}}`; init counters/flags as strings. (Chat API may skip a first code node — keep a fallback.) |
| `opening` | conversation | TTS opening line with the required content + person-check question; extract an enum (`confirmed`/`someone_else`/`unclear`/`wrong_number`/`deceased`/`asks_question`/`refuses`/`wants_human`); branch with `equals` |
| `third_party` | conversation | disclose nothing; get a callback time; `schedule_callback`; window rules computed in code |
| `identity` | conversation | one question at a time; `verify_identity`; post-hook `what_to_do_next` from `verified` / `wrong_answers_left` / `hint`; leave on `all_verified` |
| `load_account` | api_request (or tool + code) | `get_account`; code computes per-product band, deadline, floor, attempts, spoken name → `{{account_facts}}` |
| `negotiate` | conversation | state all products, first ask, dates/amounts/attempts with the facts, side intents, read-back + confirmation, `create_promise` (post-hook: honest status + retry instruction), `add_note`, `transfer_to_agent` |
| `wrap_up` | conversation | required closing sentences, thank + goodbye, then `close_call` |
| `end_*` | end_call | `message_mode: none`, one per outcome family (gives readable `endedReason`) |

Global interrupt candidates (passthrough, fixed TTS, back to `__previous__`): "are you a robot?", "is this a scam?". Exclude end nodes. Be careful with A3's "the ask that follows is the second ask".

### `close_call` — three designs to compare

1. **Lifecycle `end_of_call` tool with model-filled outcome/reason** (base agent): always the last call, but a model guesses the outcome after the call.
2. **Explicit tool in `wrap_up`**, enum-constrained, then a transition on its result to an `end_call` node. Add a `pre_process_code` that enforces invariants from `vars` (e.g. a recorded promise and no transfer → `promise` with no reason; a transfer → `transferred` + the queue's reason; drop `reason` for `promise`/`paid`; multi-product reason = first non-`paid` note).
3. **Track the outcome in variables** as events happen (hooks write `final_outcome`/`final_reason`), and bake them into an `end_of_call` lifecycle `close_call` via `{{final_outcome}}` — if everything resolves, no model call is made.

Whatever we pick: exactly one `close_call`, nothing after it, goodbye before it.

## Testing (fast loop first, official loop second)

| Loop | How | Speed | Notes |
|---|---|---|---|
| Lint + dry run | our checks + `POST /workflow?dryRun=true` | seconds | catches stripped fields, nulls, missing `always` |
| **Chat harness** (build this early) | open a practice session (`POST /v1/practice/sessions {"case": "PUB-07"}` with `x-team-key`) → drive `POST /api/v2/chat/message` with a local LLM playing the case script (reuse `run_cases.py`'s persona text + styles) → `POST /api/v2/chat/end` → read the ledger and score with `score.py`'s `score_ledger` + our own LLM judge on the case `checks` | ~1–2 min per case, **no workspace queue** | both of us can test in parallel; `fromMessageId` lets us branch a conversation at a hard point and replay variants |
| Official | `python3 tools/run_cases.py <agent_id> --brief A --reps 3`, then each `--style` | 3–11 min per run, **one per workspace** | the ground truth; one of us owns the queue |
| Generalisation | write 2–3 **variant briefs of our own** (other identity fields, holidays, bands, outcome names, a raw-material version with a memo override and a code list) and inspect spec + workflow; chat-test what the mock allows | minutes | our own invented content is fine; don't overfit to A/B |
| Date code | `reference/scripts/date_rules.py` style tests over many `now` values (Fridays, before holidays, month/year end) | seconds | the final uses several calendar days |

Inside the 30-minute hidden-brief run, the builder can only self-test without practice customers: lint + dry run + a few chat conversations (tools will reject unknown customers — check the agent handles that honestly) + an LLM review of transcripts against the spec. Log all of it in the trace. The live spec's unit-test API with `mockToolResults` might allow realistic tool results without customers — worth one quick experiment, but don't depend on it.

## Splitting the work (2 people)

| | Person 1 — "compiler" | Person 2 — "agent + harness" |
|---|---|---|
| Owns | spec schema, extraction prompts (incl. raw material), spec validation, CLI, trace, export, submission script, variant briefs | workflow templates, tool generation from OpenAPI, code nodes and hooks, chat harness, `run_cases` queue, failure triage |
| Shared rules | one workspace, **one Freya key (rule)**, one team key; separate `save_workflow` slot names per person (e.g. `p1-A`, `p2-A`) and separate checkouts so `.freya-agents.json` doesn't collide; only one simulation at a time → agree who runs `run_cases.py` | |

## Timeline (Istanbul time; hidden briefs Sun 20:00, deadline Sun 23:00)

| When | Goal |
|---|---|
| Sat evening | env.sh; check key (`GET /api-keys/check`); baseline: base agent on A (≈2/10); run the example builder on A, keep its workflow JSON as a reference; agree on spec schema + node design |
| Overnight / Sun morning | end-to-end v1 of our builder (crude is fine) that passes most of A, with trace + export working |
| Sun until ~15:00 | Brief B (multi-product) support; reliability (`--reps 3`, all styles); generalisation (variant briefs, raw material); speed (measure the whole run, stay well under 30 min) |
| Sun ~15:00–19:30 | **feature freeze**; full dry runs exactly as on submission (`… 2>&1 \| tee traces/…`), export, commit, push; fill the form JSON; make sure the repo is reachable by the organisers; README with run instructions and env vars |
| Sun 20:00 | hidden briefs (check spam if a mail account is Outlook/Hotmail/university). Run the builder on both; only crash fixes, nothing from the briefs in the code; pick the best run per brief; export; commit; push |
| Sun ≤ 22:30 | send the form (hard deadline 23:00) |

## Submission checklist

- [ ] `python3 builder/build.py {brief_path} {tool_api_path}` works from a fresh clone with only env vars set; `requirements.txt`; README lists env vars (`FREYA_API_KEY`, `FREYA_API_URL`, `FREYA_BANK_TEAM_KEY`, the builder's model key).
- [ ] Builder handles multiple briefs and a raw-material brief; never crashes on an unexpected table (fallback paths).
- [ ] `submission/hidden-1.workflow.json`, `submission/hidden-2.workflow.json` from `freya.export_workflow`, untouched.
- [ ] `traces/hidden-1.log`, `traces/hidden-2.log`: start/end time, every model call (model + one-line purpose), workflow id, agent id, #steps, #tools, tests + results. **No API keys** (grep for `fak_` and the team key).
- [ ] Commit hash recorded; repo URL accessible; form JSON sent before 20:00 UTC.
- [ ] No hidden-brief rule, value or name anywhere in the commit's code/prompts.
- [ ] `AGENT_LLM` untouched; the phone agent calls only the tool API URL from the given file.

## Risk list

| Risk | Mitigation |
|---|---|
| Agent silent after a tool result → customer hangs up | `what_to_do_next` post-hooks; prompt: always speak or call the next tool |
| Model narrates instead of calling a tool | "CALL it when …" descriptions; one tool per message; tool rules first in the prompt |
| Wrong date arithmetic | all date facts from code; never rely on the extractor's notion of "today" (it may be the real clock, not `now`) |
| Forbidden words before verification | fixed TTS opening; identity prompt forbids explaining the call; nothing about the account in context before verification |
| Lies about recording | post-hook on `create_promise` states plainly whether it was recorded and what to do next |
| Raw-material brief misread | two-pass extraction + coverage check + spec logged in trace; free-text rules channel |
| Model busy → slow turns | short prompts, fixed lines where possible, fewer nodes on the hot path; rerun before trusting a score |
| Build > 30 min | time-box each phase; no simulations for hidden briefs; measure on A/B |
| Top-10 rerun scores lower than our submission | determinism in the builder (structured outputs, low temperature, retries on invalid JSON) so a rerun produces an equivalent agent |
