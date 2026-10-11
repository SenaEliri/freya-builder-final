# 10 — Gotchas, all in one place

Collected from the kit docs, README, `freya.py` comments, the hackathon page and the briefs. Source in brackets: [README], [api], [wf] = workflow-format.md, [tc] = tools-and-code.md, [page], [brief], [code] = kit Python.

## Platform and API

- **Browser-like `User-Agent` or Cloudflare blocks you** with an HTML page `error code: 1010`. [api][README]
- **Update ≠ publish.** `PUT /workflow/{id}` saves an unpublished version; simulations and chats run the **published** one. `freya.save_workflow`/`update_workflow` publish. Check `agentVersionNumber` of a run when a change "does nothing". [api][README]
- **`PUT` replaces the whole definition** — omitted top-level keys are deleted (`test_variables`, the platform-filled `agent_config`). Send everything every time. [api]
- After the **first create**, `agent_config` holds the platform default model; per `freya.py`, a chat turn or real call can't start until the model is set to the event model — `update_workflow` fixes that, `create_workflow` alone doesn't. [code]
- **Leave `agent_config` out** of what you send; a simulation that stays "running" with no call means the workflow can't start a call. [README]
- **One simulation at a time per workspace**, one workspace per team; a second `run_cases.py` waits. 10 cases = 3–11 min. [page][README]
- **200 workflows per workspace** → update in place (`Workspace plan limit reached`). [page][README]
- Routes: `/workflow`, `/call` singular; `/personas`, `/simulations` plural; HTML 404 = wrong route; list routes need `workspaceId`. [api]
- Iteration runs come 30 per page by default (max 100) — page through. [api]
- Chat API: long turns can 504; a first `code` node may be skipped in chat (its values empty); a bare 500 = workflow can't start; `/chat/end` fires the end-of-call lifecycle (end-of-call tools run). [api][live spec]
- Dry-run validation **silently strips** fields that don't belong to a node type. Read back what was stored. [api]
- `run_cases.py` caches personas in `.personas.json`; `save_workflow` keeps slot → workflow ids in `.freya-agents.json` (per working directory). Two teammates sharing a slot name overwrite each other's agent. [code]
- API keys expire (default 90 days). **One Freya key per team.** [docs][page]

## Workflow JSON

- **No `null` values** (omit optional fields or use `""`). [wf]
- **`tools` only on `conversation` nodes; `pre_actions` only on `api_request`/`code` nodes** — the other is dropped without an error. [wf][tc]
- `response_mapping`: on the **tool** for `tools`, on the **node** for `pre_actions` (nested inside a pre_action it is ignored). Paths start with **`data.`**. [tc]
- **Booleans arrive as strings** (`"true"` / `"True"`) — test both or route on string flags. [wf][tc]
- **Passthrough nodes must end with an `always` transition** or they deadlock. [wf]
- Variable conditions: top-level group is always `"logic": "or"`; nest `and` inside. [wf]
- **No fallback when nothing matches** — the agent stays in the node and answers from the same prompt. [wf]
- Routing reads only transitions (+ `routing_prompt`); routing text inside `task_message` does nothing. Don't name other nodes in prompts. [wf]
- `matches_intent` re-testing the user's earlier intent can route away **before** the tool was called — branch on an extracted enum or a tool result instead. [tc]
- Extraction `min_confidence` defaults to **0.95** — set it on every variable (discarded values leave no trace). [wf]
- A custom `extraction_prompt` **replaces** the template and must include `{{extractor.speech}}`, `{{extractor.conversation.last-10}}`, `{{extractor.type_preamble}}`, `{{extractor.variables_list}}`. [wf]
- `type: "date"` extraction turns "next week" into a concrete date and anchors on its own "today" (likely the real clock, not our `now`). Do date logic in code from `now`. [wf]
- `context_variables` came back missing after an API save on 10 Oct — don't rely on it. [wf]
- `max_node_turns` defaults to **10** user turns; a whole-call node needs more, and set `max_turn_transition`. [wf]
- `end_call`: the farewell comes from the **terminal**, not `on_enter`; `message_mode: none` + silent entry hangs up immediately. `endedReason` = terminal `function.name`. [wf]
- An unresolved `{{var}}` in a fixed spoken line is **spoken aloud**; in a prompt the model sees the placeholder; in an engine-run call a lone placeholder field is dropped and a mixed one is sent literally. [wf]

## Tools, hooks, code

- **`default`, never `const`** (const never bakes; a const `url` fails "URL is required"). [tc]
- A model-filled field whose name matches a variable already set at node entry gets **baked** and hidden from the model. [tc]
- Plain tool descriptions ("Looks up an order") → the model talks instead of calling. Write "CALL it when …". [tc]
- The model can only call tools listed in the current node ("The function `<name>` is not currently available."). [tc]
- **Silent agent after a tool result** and **ignoring `verified: false`** were seen with the event's model → add `what_to_do_next` in a post-hook; prompt "after every tool result, speak or call the next tool". A turn with neither text nor tool call → error "The model returned no speakable content". [tc]
- Hooks run only on `api_call` tools; always `try/except`; post-hook sees the **envelope** (`result["data"]` is the API body); `result.pop("header", None)` saves context. [tc]
- Code snippets: **no `{{` or `}}`**, never raise, write string flags, keep fast; values only leave via `vars`. Only `json`, `re`, `datetime` are verified imports. [tc]
- Lifecycle tools: `each_turn` never fires; `end_of_call` gets no `response_mapping`; a malformed lifecycle tool is dropped at run time silently. [tc]
- `maxRetries` > 0 on a write can record twice if the API isn't idempotent (the mock's 500 says nothing was recorded). [tc][bank api]
- `unknown product_id` from the bank = the model invented an id; give ids in the tool result or fill them with code. [README]

## Hackathon rules that bite

- **30 minutes per brief including self-tests.** [page]
- After 17:00 UTC Sunday: bug fixes only — **no rule, value or name from a hidden brief** in code or prompts; a reviewer checks the commit. [page]
- The phone agent may call **only** the tool API; a call to any other service fails the case. [page]
- Don't change `AGENT_LLM`. [README]
- Submit exactly what `freya.export_workflow` wrote; organisers load it into their own workspace. [page]
- Traces must exist (no trace → not ranked) and must not contain API keys. [page]
- Mail to Outlook/Hotmail/some university addresses was filtered — watch spam for the hidden briefs. [page FAQ]
- Third tie-break is submission time — don't wait for the last minute. [page]

## Brief logic traps (Brief A/B)

- "Hello", "go ahead", "who is this" are **not** confirmations; answering the customer's question first, then asking again, counts as the second ask. [A3]
- Third party: nothing beyond the opening sentence; no `verify_identity`/`get_account` at all (ledger check for `not_reached`). [A5, score.py]
- `day_month_swapped` retry and unreadable dates don't count as wrong answers; three wrong in total ends the check. [A12–A13, bank api]
- A customer's own date or amount is **never** a refusal; "too much" is not a flat refusal. [A26, A29]
- "Next Friday" said on a Friday = the following week's Friday. [A22]
- Hardship: no persuasion even in the late band; support offered once. [A32]
- Human request: offer help once before transferring. [A42]
- Brief B: **no notes on any transfer**; notes for every product without a promise otherwise; closing reason from the first non-`paid` note in `get_account` order. [B8, B10, B closing]
- Say "recorded" only after `ok: true`; retry once; then `no_promise / service_error` (B: note `service_error` for that product). [A37, B11]
