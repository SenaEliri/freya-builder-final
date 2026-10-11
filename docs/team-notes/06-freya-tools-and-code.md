# 06 — Freya tools, API calls, hooks and code nodes: cheat sheet

Source: `reference/kit/build-the-builder/docs/tools-and-code.md`. "Verified in a working builder" = a 6-node workflow with code nodes, `api_call` tools, post-hooks and transitions on tool results, whose agent passed its practice cases. "Seen in a trial call" = from that builder's simulation event log.

## Tool function shape (same everywhere)

```json
{
  "type": "function",
  "config": { "timeoutMs": 10000, "maxRetries": 2 },
  "function": {
    "name": "lookup_order",
    "handler": "__function__:api_call",
    "description": "Look up one order. CALL it when the caller asks about a specific order.",
    "parameters": { "type": "object", "properties": {
      "url": { "type": "string", "default": "https://api.example.com/v1/orders/lookup" },
      "method": { "type": "string", "default": "POST" },
      "headers": { "type": "object", "properties": { "Content-Type": { "type": "string", "default": "application/json" } } },
      "body": { "type": "object", "properties": {
        "customer_id":  { "type": "string", "default": "{{customer_id}}" },
        "order_number": { "type": "string", "description": "Order number, digits only", "default": "{{order_number}}" } },
        "required": ["order_number"] } } }
  },
  "response_mapping": [ { "path": "data.status", "variable": "order_status" } ],
  "pre_process_code": "",
  "post_process_code": ""
}
```

| Field | Meaning |
|---|---|
| `function.name` | the model calls it by this name; result variables are named after it |
| `function.handler` | `__function__:api_call` (HTTP), `__function__:code_exec` (Python sandbox), `__function__:end_call` (hang up) |
| `function.description` | read by the dialogue model (for tools in `tools`); ignored in `pre_actions` |
| `config.timeoutMs` / `config.maxRetries` | per-attempt timeout / tool-level retries of a failed call (defaults not documented) |
| `config.interruptible: false` | background tool (result arrives a turn or more later) |
| `config.alwaysRunsAt` | lifecycle tool (`start_of_call`, `end_of_call`; `each_turn` is accepted but never fires) |
| `response_mapping` | tool level for tools in `tools` |
| `pre_process_code` / `post_process_code` | Python hooks (api_call only) |

`api_call` parameters: `url`, `method`, `headers` (each header a property with a `default`), `body` (each field a leaf under `body.properties`), optional `connect_retries`.

## How a parameter gets its value — the `default` rule

| Declaration | Who supplies the value | Model sees it? |
|---|---|---|
| `default` = literal, or `{{var}}` that **has a value at node entry** | the workflow (**baked**) | no |
| `default` = `{{var}}` with **no value at node entry** | the model | yes (named after the variable, with `type`/`description`/`enum`) |
| no `default` | the model | yes |
| `const` | nobody — **`const` does not bake** (only constrains model output) | — |

- Use `default` for URL, method, auth headers. **Never `const`** (an `api_call` with `const` url fails "URL is required").
- Baking happens **when the node is entered**.
- The working builder: `customer_id` default `{{customer_id}}` (baked from the call variable); every other field `default: "{{<field name>}}"` with no such variable → model fills it.
- The model's arguments are stored as `<tool>_args.<field>` (not under the bare field name).
- **Trap:** a model-filled field must not share its name with a variable already set at node entry — it would be baked and hidden from the model.

Body-field rules: one leaf per field under `body.properties.<field>` with its own `default`, `type`, `description`, `enum`; required fields in `body.required`. Don't put field specs at the top of `parameters.properties` next to a `body.default` template (the model sees only "Template variable: name"; enum/description lost; the dashboard editor shows an empty form and saving there deletes the tool). `code_exec` tools are different: their parameters are true top-level arguments.

| Field kind | Variable unset | Variable `""` |
|---|---|---|
| normal field in an engine-run call (`pre_actions`, lifecycle) | field dropped, no error | sent empty |
| `code` of `code_exec` | literal `{{var}}` stays in the Python → crash | |

Constrain model-filled values: `enum` on the leaf **and** list the values in the description; or a number index into a list (a hook maps it); or name the exact source and say "copy unchanged".

## `pre_actions` vs `tools`

| | `pre_actions` (`api_request`/`code` nodes) | `tools` (`conversation` nodes) |
|---|---|---|
| Who calls | the engine, on node entry, before any model turn | the dialogue model, when it decides |
| Can be skipped | no | yes (if description/prompt don't push it) |
| `response_mapping` lives | on the **node** (nested inside the pre_action it is ignored!) | on the **tool** |
| `description` | ignored | the only text the model reads about the tool |
| History | tool call + result pair added | same |

The platform silently removes `tools` from non-conversation nodes and `pre_actions` from conversation nodes (create succeeds, stored array is empty). Fixed call before a conversation → passthrough `api_request` node. Don't build long chains of passthrough nodes for optional actions — one conversation node with several tools.

### Tool descriptions decide whether the model calls the tool

- Write a trigger instruction: "CALL it every time the caller gives an order number." A plain "Looks up an order" lets the model answer in words and never call it (most common failure in nodes with many tools).
- If two tools could match, say which not to use.
- In `task_message`, put tool rules before long reference text; "when a rule says to use a tool, call the tool".
- The working builder tells the model: **one tool per message**, and **speak after every tool result**. A model turn with no text and no tool call produced the error event "The model returned no speakable content".
- A tool is available only in nodes that list it; otherwise the result is "The function `<name>` is not currently available."

## Results, `response_mapping` and automatic variables

An `api_call` result is an envelope:

```json
{ "status": "success", "data": { "ok": true, "verified": true, "attempts_left": 3 },
  "message": "Successfully executed POST request", "status_code": 200, "header": { "Content-Type": "application/json" } }
```

`data` = the API's JSON body. The engine writes every result into variables automatically (flattened with dots), e.g. for a tool `check_answer`:

| Variable | Value |
|---|---|
| `check_answer_args.<field>` | each argument the model sent |
| `check_answer_response.status` | `success` |
| `check_answer_response.data.ok` / `.data.verified` | `true` (**a string**) |
| `check_answer_response.data.attempts_left` | `3` |
| `check_answer_response.message` / `.status_code` / `.header.<Name>` | … |
| `check_answer_status_code` | `200` |
| `check_answer_success_count` | successful calls so far |

Each call of the same tool overwrites the previous `_args`/`_response` values.

Mapping paths: **start with `data.`** (`data.ok`, `data.products`) — verified on tool-level and node-level mappings; a path without `data.` is not confirmed (an early trial left variables unset). The flattened key itself works as a transition variable. Booleans arrive as strings (lower-case seen) — test `"true"` and `"True"`. A mapped list/object's form inside `vars` is not confirmed — read it defensively (list, JSON string, or flattened keys).

### Routing on tool results

Routing re-runs after a tool result, so a transition on a result variable fires **in the same turn** (seen in a trial call). Patterns:

- "a closing tool sets a variable, a transition on that variable leads to an `end_call` node" — verified in a working builder.
- To leave a node that carries out an action, **don't re-test the user's earlier intent with `matches_intent`** (the router looks at the latest message and can route away before the tool was called). Extract a follow-up enum with a default such as `stay` and branch with `equals`.
- On passthrough nodes, end with `always` so a failed/empty response doesn't deadlock.

### Success / failure counters (no mapping needed)

| Placement | Variables |
|---|---|
| `pre_actions` node | `<nodeId>_success_count`, `<nodeId>_failure_count` |
| `api_call` tool in `tools` | `<toolName>_success_count`, `<toolName>_failure_count` |

E.g. `{ "variable": "create_promise_failure_count", "operator": "greater_than", "operand": 1 }`.

`suppress_tool_results: true` (node) → the model sees only `{status: "success"}`; variables still mapped, routing still sees them.

Background tools (`config.interruptible: false`): result arrives later; gate transitions with `is_set`.

### Retries and timeouts

| Setting | Where | Default | What |
|---|---|---|---|
| `timeoutMs` | `config` | not documented | per-attempt time limit |
| `maxRetries` | `config` | not documented | tool-level retries after a failed response |
| `connect_retries` | baked parameter next to `url`/`method`: `{"type":"number","default":0}` | 2 | only connection-establishment failures (safe for POST); not HTTP errors/timeouts; cap 5; back-off 150 ms × attempt; 30 s total budget |
| `timeout_ms` | `code_exec` parameter | 30000 | snippet time limit |

The working builder: `maxRetries: 0` on writes, `2` on its read-only `pre_actions` call ("a retried write can record the same thing twice if the API is not idempotent").

## Pre/post Python hooks (on `api_call` tools)

| Hook | Names available | Use |
|---|---|---|
| `pre_process_code` | `vars` (mutable dict that fills the request's `{{var}}`s), `config` (the substituted request: `url`, `method`, `headers`, `body`) | clean a value, rewrite the request |
| `post_process_code` | `result` (mutable tool result = the **envelope**; the API body is `result["data"]`) | reshape/shorten/extend the result |

- Post-hook runs **before** `response_mapping` and extraction see the result. Mapping paths still start with `data.`.
- A key the hook adds inside `result["data"]` reaches the dialogue model. **The working builder adds `what_to_do_next` there and its prompt tells the model to obey it.**
- `result.pop("header", None)` on every tool saves context.
- Hooks are honoured only on `api_call` (and integration/knowledge-search) handlers; removed from others on save.
- Pre-hook: setting `config['body']` to a string sends it raw (set `Content-Type` yourself).
- Wrap every hook in `try/except Exception: pass`; check types with `isinstance`. Platform behaviour on a raising hook is undocumented.
- Seen 10 Oct: **a post-hook can read call variables and write new variables, and a later pre-hook reads them.** Not confirmed: whether changing `result` also changes the flattened `<tool>_response.*` variables.

Example post-hook (from the kit):

```python
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            d['what_to_do_next'] = 'Ask the next question.' if d.get('verified') else 'Ask the same question again.'
except Exception:
    pass
```

## Code nodes and `code_exec`

```json
{ "name": "compute_delivery", "node_type": "code", "passthrough": true, "passthrough_default_transition": "tell_delivery",
  "on_enter": { "type": "silent" },
  "pre_actions": [ { "type": "function", "function": { "name": "code_exec", "handler": "__function__:code_exec",
    "parameters": { "type": "object", "properties": {
      "code": { "type": "string", "default": "import datetime\ntry:\n    ...\n    vars['delivery_state'] = 'known'\nexcept Exception:\n    vars['delivery_state'] = 'unknown'\n" },
      "timeout_ms": { "type": "number", "default": 10000 } } } } } ],
  "transitions": [ { "target_node": "tell_delivery", "description": "always", "condition": { "operator": "always" } } ] }
```

- Snippet gets a dict **`vars`** (current workflow variables). Read `vars.get("name")` (unset = absent); write `vars["name"] = value` → becomes a workflow variable.
- Verified: call variables are in `vars` (`vars.get("now")`); an earlier `api_request` result is reachable (under the mapped name or flattened keys — read both); a string written in a code node resolves as `{{date_facts}}` in later prompts (multi-line OK); `json`, `re`, `datetime` import fine; the same snippet can run in two code nodes and sees variables added in between.
- Result of a `code_exec`: `{ "status": "success", "data": null, "message": "Code executed successfully", "status_code": 200 }` — output only reaches the workflow via `vars`. Automatic keys are named after the **node** (`setup_success_count`, `setup_response.status`, …).

Snippet rules:

- **No `{{` or `}}` anywhere in the code** (sources disagree on templating; a nested dict literal ends in `}}`). Read everything from `vars`.
- **Never let a snippet raise**: `try/except`, fallback values for every variable a later prompt/condition reads.
- Write **string flags** for routing (`known`/`unknown`), not booleans.
- Keep snippets fast (they block the conversation). Do **arithmetic, date calculation and counting in code** and give the model finished facts as text (verified: a code node computes a block of date facts placed in prompts).
- Treat a code node like an API node: `passthrough: true`, `passthrough_default_transition`, last `always`.
- Sandbox: time = `timeout_ms`; modules beyond `json`/`re`/`datetime` undocumented; network/file/memory undocumented.
- `code_exec` can also be a **tool** in a conversation node (model calls it; `code` resolves `{{var}}` at call time). Not verified by the working builder.

## Lifecycle tools

Top-level `tools` entries with non-empty `config.alwaysRunsAt`; never shown to the model.

| Value | When |
|---|---|
| `start_of_call` | during setup, before the first turn (`response_mapping` applied) |
| `end_of_call` | after the call has ended (`response_mapping` **not** applied) |
| `each_turn` | accepted, never fires |

- A workflow-level tool without `alwaysRunsAt` never runs.
- In a node's `tools`, a lifecycle tool runs `start_of_call` only on the `initial_node` and `end_of_call` only on the node where the call ended.
- **If a `{{var}}` parameter is still unresolved, one model call fills the parameters; if everything resolves, the handler runs directly.**
- End-of-call order: call analysis → `end_of_call` tools → success-criteria judging. Available: `{{call.analysis.summary}}`, `{{call.analysis.structured_data_str}}`, `{{call.call_end_reason}}`, `{{call.call_end_reason_category}}`, `{{call.call_tags}}`, `{{call.duration}}`.
- A malformed lifecycle tool is dropped at run time without error → validate with a dry run.

`examples/base-agent.json` uses this for `close_call`: an `end_of_call` lifecycle tool with model-filled `outcome`/`reason` (enum + descriptions) and a `pre_process_code` that pops `reason` when outcome is `promise`/`paid`.

## Tool results and the next turn (observed with the hackathon's agent model)

Two failure modes seen in practice runs:

1. **The agent says nothing after the tool call** → the simulated customer waits and hangs up (more often when the result is bare data like `{"ok": true, "verified": true}`).
2. **The agent ignores a negative result** (reads `"verified": false` and moves on as if it passed).

Fix that worked (verified): a **post-hook that adds one plain instruction line** to the result (`what_to_do_next`: what the answer means and what to say or call next). Also say in the step's prompt: after every tool result, speak to the customer or call the next tool; never end a turn with nothing.

## Checklist (from the kit)

- Fixed values use `default`, never `const`.
- Each `api_call` body field is a leaf under `body.properties` with its own `default`, `description`, `enum`.
- `tools` only on `conversation` nodes; `pre_actions` only on `api_request`/`code` nodes.
- `response_mapping` on the tool for `tools`, on the node for `pre_actions`; paths start with `data.`.
- Booleans tested as `"true"` and `"True"`, or replaced by string fields.
- Every passthrough node ends with an `always` transition.
- Code reads/writes through `vars`, never raises, contains no `{{` or `}}`.
- Tool descriptions say **when** to call the tool.
