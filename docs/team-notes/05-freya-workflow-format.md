# 05 — Freya workflow JSON: cheat sheet

Source: `reference/kit/build-the-builder/docs/workflow-format.md` (written for a program to read; "verified in a working builder" = a 6-node builder whose agent passed its practice cases). The public docs site does **not** document the workflow JSON — the kit is the reference. This page condenses it; the full text with all examples is in the kit.

## Mental model

A workflow = a conversation graph. Each **node** is one step with its own prompt. **Transitions** move between nodes, on what the user said (model-judged) or on variable values (code-judged). Creating a workflow via API also creates an **agent**; simulations run against the agent id.

**Three separate model calls per user turn** (they do not share a prompt):

| # | Call | Sees | Produces |
|---|---|---|---|
| 1 | Extraction | recent messages + current node's `extraction_schema` | variable values |
| 2 | Routing | recent messages + transition descriptions (**not** the dialogue prompt) | which transition, or none |
| 3 | Dialogue | `system_prompt` + `role_message` + `## Current Task` + `task_message`, full history, node `tools` | reply or tool call |

Consequences: routing instructions inside `task_message` do nothing; the dialogue model can call only the current node's `tools`; variable conditions need no model call.

## Top-level keys

| Key | Req | Meaning |
|---|---|---|
| `initial_node` | yes | node key where every call starts (a passthrough `code` node works as initial node — verified) |
| `nodes` | yes | map node key → node |
| `system_prompt` | | global rules, part of the dialogue prompt in every node |
| `global_nodes` | | interrupt handlers that can fire from any node |
| `test_variables` | | default call variables (call-supplied values win) |
| `context_variables` | | state block for the dialogue model — **⚠ a workflow saved over the API on 10 Oct came back without this key, no error. Don't rely on it; put values in prompts with `{{var}}`** |
| `tools` | | workflow-level **lifecycle** tools (`config.alwaysRunsAt`) |
| `agent_config` | | model/voice/timeouts — **omit it** when creating (platform fills defaults; `freya.update_workflow` then sets `llmConfig` to the event model) |
| `nodePositions` | | editor layout; omit |

REST body is `{"name": "...", "workflow": {…this object…}}`. **No `null` values** per the doc ("schema is strict… a null fails validation") — omit optional fields or use `""`. (Note: `examples/base-agent.json`, an export, contains `null` for `max_turn_transition` and `passthrough_default_transition`, so some fields are nullable; omitting is safest.)

## Node types

| `node_type` | Purpose | Speaks | Carries |
|---|---|---|---|
| `conversation` | dialogue step | yes | `task_message`, `tools`, `extraction_schema`, `transitions` |
| `api_request` | HTTP call on entry | usually not | `pre_actions`, node-level `response_mapping`, `transitions` |
| `code` | Python on entry | usually not | `pre_actions` with a `code_exec` function, `transitions` |
| `end_call` | hangs up | optional farewell | `terminal` |

Others exist (`transfer_call`, `integration`, `knowledge_base`, `reschedule_call`, `invoke_agent`, `exit`) — not needed here.

**Silent stripping:** `tools` survive only on `conversation` nodes; `pre_actions` only on `api_request`/`code` (and other action) nodes. A node can't have both → put a must-run call in its own passthrough `api_request` node in front.

## Node fields

| Field | Default | Meaning |
|---|---|---|
| `name` | | same as the key, `snake_case` |
| `node_type` | | see above |
| `task_message` | | instruction for the dialogue model in this node |
| `role_message` | | extra persona text; rarely needed |
| `on_enter` | `{"type":"llm"}` | entry behaviour (below) |
| `on_enter_first_entry_only` | `false` | run entry behaviour only on first visit (better than "don't greet twice" prompts) |
| `transitions` | | outgoing, **in priority order** |
| `routing_prompt` | | replaces the default intent-matching instruction for this node's routing call |
| `loop_condition` | | intent description for staying in the node (checked before transitions) |
| `loop_prompt` | | replaces `task_message` from the 2nd turn in the node (model sees one or the other) |
| `extraction_schema` | | variables to extract from user speech |
| `tools` | | tools the dialogue model may call (`conversation` only) |
| `pre_actions` | | calls the engine runs on entry (`api_request`/`code` only) |
| `response_mapping` | | node level, for `pre_actions` results |
| `passthrough` | `false` | route right after entry without waiting for the user |
| `passthrough_default_transition` | | target for a passthrough node |
| `max_node_turns` | `10` | cap on **user** turns in the node — no "unlimited" value |
| `max_turn_transition` | | target when the cap is hit (without it the cap changes nothing) |
| `terminal` | | end-call function (`end_call` only) |
| `disable_inactivity_monitor` | `false` | switch off silence check-ins |
| `suppress_tool_results` | `false` | model sees only `{status: "success"}`; variables still mapped |
| `truncation_strategy` | `keep_all` | `keep_recent` / `summarize` (dialogue model only) |
| `truncation_window_size` | `10` | messages kept by `keep_recent`/`summarize` |
| `reasoning_override` | `auto` | `enabled`/`disabled` forces model reasoning for this node (if the model supports it) |

Also seen in the exported `base-agent.json`: `position`, `assertions: []`, `interruptible`, `return_to_previous_on_interrupt`, and `"mode": "exact"` inside conditions. Voice-only: per-node `idle_config`, speech settings.

## Prompts

System message = `system_prompt` (workflow) + `role_message` (node) + `## Current Task` + `task_message` (or `loop_prompt` after the first turn).

Rules for `task_message`: instructions, not a script; this node's job only; **never describe routing or name other nodes** (the model narrates steps that haven't happened); name the node's tools and say when to call them; in a node without tools, say that no tool call is allowed this turn (in both `task_message` and `loop_prompt`).

### `on_enter`

| Value | Behaviour |
|---|---|
| `{"type":"llm"}` | model writes the first line from `task_message` (optional `prompt` overrides the entry instruction) |
| `{"type":"tts","text":"..."}` | **fixed line, no model call**, `{{var}}` works — best for exact sentences |
| `{"type":"silent"}` | says nothing; waits, or routes at once if passthrough |
| `{"type":"audio","asset_id":"..."}` | recorded asset (not needed) |

History across nodes: user/assistant messages are kept; the system message is replaced by the new node's prompts; a loop prompt is removed. Variables persist all call.

## Variables

One call-wide table; no scoping; never cleared on transitions; later writes overwrite. Sources: call variables, `test_variables`, extraction, call results (`response_mapping` + automatic `<tool>_response.*` keys), code (`vars[...]`), system.

`{{var}}` works in prompts, `on_enter.text`, transition descriptions, URLs, headers, bodies. `{{amount:json}}` = JSON-encoded (for bodies).

- Dates substituted into prompts are **formatted for speech**.
- Unresolved in a prompt → literal `{{name}}` (model sees it). In a fixed spoken line → **spoken aloud**.
- Unresolved in an engine-run call field: exactly one placeholder (`"{{x}}"`) → field **dropped**; mixed text (`"Status: {{x}}"`) → sent with literal `{{x}}`.

Call variables are readable as `{{customer_id}}` in prompts/tool params and `vars.get("customer_id")` in code (verified).

### System variables

| Variable | Example / meaning |
|---|---|
| `{{system.iso_utc_now}}` | real clock UTC timestamp — **don't use; use the `now` call variable** |
| `{{system.todays_date_en_cst}}`, `_en_est`, `todays_date_tr`, `todays_date_tr.iso_8601` | real-clock dates |
| `{{system.conversation}}` | transcript so far; `{{system.conversation.last-N}}` with N ∈ {1,5,10,20} — useful in transition descriptions / `routing_prompt` |
| `{{call.direction}}` | `inbound`/`outbound`/`web`/`simulation` (chat simulation showed `web`) |
| `{{call.duration}}`, `{{call.call_id}}` | seconds since start, platform call id |
| `{{<node>.current_turns}}`, `{{<node>.total_turns}}` | user turns in a node (since last entry / whole call) |

There is no `{{current_date}}`.

## Transitions

`{ "target_node", "description", "condition", "is_tool_call" }`. `target_node` may be the node itself; `__previous__` allowed in global nodes.

| Operator | Needs | True when (deterministic, no model call) |
|---|---|---|
| `equals` / `not_equals` | `variable`, `operand` | `str(value) == str(operand)` |
| `greater_than` / `less_than` | `variable`, `operand` | float comparison (use for counters) |
| `contains` | `variable`, `operand` | substring, case-insensitive |
| `is_set` / `is_not_set` | `variable` | has / has no value |
| `always` | — | always |
| `matches_intent` | `description` | **routing model** judges the user's last message (all intent conditions of one evaluation in one model call) |

Shapes:

```json
{ "target_node": "next", "description": "always", "condition": { "operator": "always" } }
{ "target_node": "complaint", "description": "...", "condition": { "operator": "matches_intent", "description": "The user is unhappy" } }
{ "target_node": "found", "description": "...", "condition": { "logic": "or", "conditions": [
    { "variable": "status", "operator": "equals", "operand": "shipped" },
    { "logic": "and", "conditions": [ { "variable": "a", "operator": "is_set" }, { "variable": "b", "operator": "is_set" } ] } ] } }
```

Variable checks go in a group whose **top level is always `"logic": "or"`**; nest an `and` group for AND. Never put `and` at the top.

**Never route on a boolean**: `equals` compares strings and booleans arrive as `"true"` or `"True"`. Test both, or route on string flags your code writes (`verified`, `rejected`).

### Order of evaluation (after each user message, first match wins)

1. `loop_condition` of the current node → stay, use `loop_prompt`
2. node's `transitions` in list order (deterministic ones are evaluated first; if one matches, no routing-model call)
3. global nodes
4. nothing matched → **stay** in the node, answer from the same `task_message` (no fallback!)

- Several transitions with the same `target_node` are merged into one (OR); if one is unconditional, the merged one is unconditional.
- **Routing also runs after a tool result** — a transition on a variable set by the tool's `response_mapping` fires in the same turn (verified).
- Self-transition with `always` as the last item keeps the user in the node (preferred over `loop_condition`).
- `loop_condition` must be specific (doc example: "The user has not yet given both a full name and an email address"); "The user has not finished" matches everything and the agent never leaves.

### Tool-call transitions

`"is_tool_call": true` → the dialogue model sees a tool `transition_to_<node>` and moves by calling it (router doesn't evaluate it per turn). Use when the agent should decide to move (it can acknowledge and move in the same message; the target's `on_enter` asks the next question). Global nodes accept the flag too.

### Passthrough nodes

`"passthrough": true` routes right after entry actions. Set `passthrough_default_transition`, end `transitions` with `always` (else **deadlock**), `on_enter` silent or a short fixed line. `api_request` and `code` nodes are normally passthrough.

### Global nodes

Interrupt handlers checked only after the current node's transitions found no match. Extra fields: `condition`, `description`, `excluded_nodes`, `is_tool_call`. `__previous__` returns to the interrupted node. List terminal nodes and sensitive nodes (identity check) in `excluded_nodes`. For a plain redirect use a passthrough node with a fixed TTS line.

## Extraction schema

```json
{ "name": "wanted_day", "type": "date", "description": "Day the caller wants", "min_confidence": 0.7 }
```

| Field | Meaning |
|---|---|
| `type` | `string`, `integer`, `float`, `boolean`, `date`, `datetime`, `name`, `phone_number` |
| `enum_values` | allowed values (any type); old `enum` type → `string` |
| `extraction_prompt` | **replaces the whole built-in template** — must include `{{extractor.speech}}`, `{{extractor.conversation.last-10}}`, `{{extractor.type_preamble}}`, `{{extractor.variables_list}}` or it silently extracts nothing |
| `validation_pattern` | regex the value must match |
| `min_confidence` | 0–1, **default 0.95 (strict!)** — set it on every variable (discarded values leave no trace) |
| `max_retries` | retries after failed validation |

- Confidence comes from token probabilities, not self-report.
- **Declare dates as `type: "date"`** (gets today's date + relative-date rules; a `string` date gets no anchor and the model guesses the year). But the built-in date rules turn vague "next week" into a concrete date — if you need vague dates rejected, a custom prompt must override that. ⚠ The extractor's "today" is presumably the real clock, not our `now` variable — compute dates in code from `now` instead.
- Extracted variables are available to the same node's transitions in the same turn.
- **Fork on an extracted enum + `equals`** — more reliable than competing `matches_intent` transitions. Use extraction for user speech, `response_mapping` for API results.
- Extraction-prompt date placeholders (`{{date.today}}`, `{{date.next_mon}}`, `{{date.fnm_mon}}`, `{{date.weeks2}}`, …) only work inside extraction prompts.

## End-call nodes

```json
{ "name": "goodbye", "node_type": "end_call", "on_enter": { "type": "silent" }, "disable_inactivity_monitor": true, "transitions": [],
  "terminal": { "type": "function", "function": { "name": "closing_end", "handler": "__function__:end_call",
    "parameters": { "type": "object", "properties": {
      "message_mode": { "type": "string", "default": "custom" },
      "spoken_message": { "type": "string", "default": "Thank you for calling. Goodbye." } } } } } }
```

- `message_mode`: `custom` (say `spoken_message`), `llm` (model writes farewell from `llm_prompt`), `none` (hang up silently).
- **The farewell comes from the terminal, not `on_enter`.** `message_mode: none` + silent `on_enter` ends the call immediately (verified) — say goodbye in the previous conversation node.
- The call's `endedReason` = the terminal's `function.name` → name it after the outcome; use several end nodes.
- `interruptible` + `trigger_timeout` + `trigger_pattern_both` (farewell phrases separated by `|` that don't cancel the close) — the window is wall-clock; chat simulations can't measure it.
- `examples/base-agent.json` instead puts an `end_call`-handler **tool** in conversation nodes with `trigger_pattern: "Have a good day|have a good day"` (+ `interruptible: true`, `trigger_timeout: 3`, `trigger_pattern_both`): saying "Have a good day." ends the call by itself. `trigger_pattern` is not described in the kit docs.

## Limits

| Limit | Default | Notes |
|---|---|---|
| `max_node_turns` | 10 | only user messages count. A node that handles a whole call can need dozens; the working builder used 60–80 |
| `max_turn_transition` | none | without it the cap changes nothing |
| `truncation_strategy` | `keep_all` | dialogue model only |
| extraction `min_confidence` | 0.95 | |
| code `timeout_ms` | 30000 | |
| call length (simulation) | `maxCallDurationSeconds` | run_cases uses 420 s |

## Design rules (from the doc)

- `snake_case` keys that describe the step; dialogue in `task_message`, routing in `transitions`, data capture in `extraction_schema`.
- Every path must reach an `end_call` node. Deterministic conditions before `matches_intent`. Every passthrough ends with `always`. Back-transitions are fine.
- Split a step into its own node when it has strict rules of its own or forms a clear state; keep related optional actions together in one conversation node with several tools.

The kit's complete example (clinic booking: `collect` → `find_slots` (passthrough `api_request`) → `offer` (tool + routing on mapped variable) → two `end_call` nodes) is at the end of `docs/workflow-format.md`.
