# 08 — Starter kit v3, file by file

Kit: `reference/kit/build-the-builder-v3.zip`, extracted in `reference/kit/build-the-builder/` (note the hidden `.claude/` folder). `VERSION` = `3` (10 Oct 2026). Changelog: v3 — the example builder waits for its own test run (up to 20 min per command) instead of stopping before results arrive; **on Brief A it built an agent that passed 10 of the 10 practice customers in one run.** v2 — `examples/base-agent.json` and `examples/agent_builder.py` + skill replaced `examples/minimal_builder.py`. v1 — first release. Organisers email new versions.

| Path | Size | What it is |
|---|---|---|
| `README.md` | 9.6 KB | rules, ten-minute start, troubleshooting |
| `briefs/brief-a.md` | 10 KB | Freya Bank, one product, 47 rules → `02-briefs-digest.md` |
| `briefs/brief-b.md` | 2.4 KB | up to three products, builds on A |
| `tools/openapi.json` | 10.5 KB | the bank's 7 tools → `04-bank-tool-api.md` |
| `public-test-set.json` | 16 KB | 13 practice customers → `03-practice-cases.md` |
| `docs/workflow-format.md` | 42 KB | workflow JSON → `05-freya-workflow-format.md` |
| `docs/tools-and-code.md` | 31 KB | tools, hooks, code → `06-freya-tools-and-code.md` |
| `docs/api.md` | 14.5 KB | REST calls → `07-freya-rest-api.md` |
| `freya.py` | 7.3 KB | Freya client, standard library only |
| `tools/run_cases.py` | 10.5 KB | runs practice cases, prints pass/fail |
| `tools/score.py` | 3 KB | ledger scorer |
| `examples/base-agent.json` | 11.6 KB | example phone agent (2 steps, 4 tools) |
| `examples/agent_builder.py` | 2.9 KB | example builder (Claude Agent SDK) |
| `.claude/skills/build-phone-agent/SKILL.md` | 2 KB | the example builder's one skill |
| `env.example` | 0.3 KB | env vars to set |

## Ten-minute start (README)

```bash
cp env.example env.sh        # Freya API key + a team key you make up
source env.sh

# 1. Put the example agent on Freya and test it. Prints {"workflow_id": ..., "agent_id": ...}
python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"
python3 tools/run_cases.py <agent_id> --brief A            # ten practice customers, 3 to 11 minutes

# 2. Let the example builder build one from the brief
pip install claude-agent-sdk
python3 examples/agent_builder.py briefs/brief-a.md
python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md   # Brief B builds on A: pass both
```

Python 3.10+. `env.sh`:

```bash
export FREYA_API_KEY=fak_your_key_here                 # workspace → API keys
export FREYA_API_URL=https://staging-app.freyavoice.ai
export FREYA_BANK_TEAM_KEY=pick-any-secret-of-16-or-more-characters   # same one every time
```

Optional env vars read by the code: `FREYA_WORKSPACE_ID` (skip the workspace lookup), `FREYA_SIM_CONCURRENCY` (default 5), `FREYA_BANK_HOST` (scorer host), `BUILDER_MODEL` (example builder, default `claude-opus-5-5`), `ANTHROPIC_API_KEY` (or a Claude login), and organiser-only `FREYA_AGENT_PROVIDER` / `FREYA_AGENT_MODEL` (**don't touch**).

## `freya.py` — the client

| Function | What it does |
|---|---|
| `api(method, path, body=None, **params)` | urllib request with Bearer key, JSON, browser-like UA `Mozilla/5.0 (build-the-builder)`, 120 s timeout; returns `data.result`; raises `RuntimeError("METHOD path -> code: body[:1500]")` on HTTP errors |
| `workspace_id()` | `FREYA_WORKSPACE_ID` or the first of `GET /api/v2/workspaces` (cached) |
| `create_workflow(name, workflow)` | `POST /api/v2/workflow` → `{workflow_id, agent_id}` |
| `save_workflow(slot, workflow, state_file=".freya-agents.json")` | first time for a slot: create (name `"<slot> MMDD-HHMMSS"`); afterwards: `update_workflow` on the same id. **Use this in the builder.** State lives in `.freya-agents.json` in the current directory. |
| `validate_workflow(name, workflow)` | dry run (`?dryRun=true`) |
| `update_workflow(workflow_id, workflow)` | `PUT` → `GET` the stored workflow → if `agent_config.llmConfig` provider/model ≠ `AGENT_LLM`, set it and `PUT` again → list versions → **publish the newest** if unpublished → return its `versionNumber` |
| `export_workflow(workflow_id, path)` | writes `{"workflow_id", "agent_id", "updated_at", "workflow"}` — **the file you submit** |
| `create_personas(personas)` | `POST /api/v2/personas` |
| `get_iteration(sim_id, it_id)` | iteration + all runs (pages of 100) |
| `get_call(call_id)` | `result.call` (messages = transcript incl. tool calls) |
| `run_simulation(agent_id, name, variables_by_persona, max_seconds=420, concurrency=5)` | create a chat simulation with the pinned models (waits 30 s and retries while another simulation runs), poll every 10 s, return `(sim_id, iteration_id, status)` |

Constants: `AGENT_LLM = {"provider": "experimental-5", "model": "experimental-5"}` ("Freya's model on the event's own GPU box. Do not change it."), `SIM_LLM = {"provider": "google", "model": "gemini-3-flash-preview"}` (plays the customer and judges).

⚠ Comment inside `update_workflow`: "The platform fills in a default `agent_config`. If its model is not the event's model, a simulation still runs (it overrides the model), but **a chat turn or a real call cannot start**." `save_workflow`'s **create** path does not do this fix-up — so after the very first create, run one update (or call `update_workflow`) before relying on the chat API.

## `tools/run_cases.py` and `tools/score.py`

Covered in detail in `03-practice-cases.md` (flow, persona template, styles, options) and `04-bank-tool-api.md` (ledger checks). Key facts: uses `FREYA_API_KEY` + `FREYA_BANK_TEAM_KEY`; caches personas in `.personas.json` (recreated when the text changes); writes `results/log.jsonl` (one line per run: time, agent, brief, passed/total, seconds, failed ids) and optionally `--out results/run.json` (call ids per case); prints the slowest agent turn per call.

## `examples/agent_builder.py` — the example builder

- Claude Agent SDK `query()` with `ClaudeAgentOptions(cwd=KIT, model=$BUILDER_MODEL or "claude-opus-5-5", skills=["build-phone-agent"], setting_sources=["project"], allowed_tools=["Read","Write","Edit","Glob","Grep","Bash"], permission_mode="dontAsk", max_turns=150, env={BASH_DEFAULT_TIMEOUT_MS: 900000, BASH_MAX_TIMEOUT_MS: 1200000, CLAUDE_CODE_DISABLE_BACKGROUND_TASKS: 1})` — long foreground Bash so the 3–11 min test is awaited ("the builder stops when Claude ends its turn, so a test left in the background is never read").
- Prompt: "Use the build-phone-agent skill to build a phone agent for: <brief paths>".
- Trace: `traces/<YYYYmmdd-HHMMSS>.jsonl` — first line `{start, briefs, model}`, then every SDK message as JSON; prints text and tool calls; ends with turns, seconds, cost.
- Limits to keep in mind: its test step only works for the public briefs (`run_cases.py --brief A|B`); up to 3 fix loops × up to 11 min each can blow the **30-minute** budget; the trace has no explicit end-time line or one-line-per-model-call summary (the required trace items are in `01-…md`).

### `SKILL.md` (build-phone-agent)

Steps: read the brief(s), then `tools/openapi.json`; read `docs/workflow-format.md` and `docs/tools-and-code.md`; read `examples/base-agent.json` as a pattern; write `out/<slot>.workflow.json` (one step per stage, identity first; **move to the next step on a tool result, not on what the customer says**; take every tool field and allowed value from the openapi file; leave `agent_config` out); save with `freya.save_workflow(<slot>, …)`; test with `run_cases.py <agent_id> --brief A|B` in the foreground; read FAIL lines, fix, re-save, re-test — at most three times; finish with workflow_id, agent_id and passes. Rules: never edit on the platform by hand; when a tool call fails the agent must say so; "Prefer rules in routes and code over rules in prompts."

## `examples/base-agent.json` — anatomy of the starter phone agent

The same workflow is pre-installed in the workspace as **"Freya Bank Collections Base"**. Passed **2 of 13** in one run. "A place to start, not a good score."

- `initial_node: "identity"`, `system_prompt: ""`, `global_nodes: {}`, `test_variables`: Daniel Reyes / Mr / `now` 2026-10-14T11:00 (the workspace copy also holds a practice customer for dashboard chats).
- **`identity`** (conversation): `on_enter` TTS "Hello, this is the digital assistant of Freya Bank. Am I speaking with {{title}} {{last_name}}?"; tools `verify_identity` (model fills `field` enum + `answer`; `customer_id` baked) and an `end_call`-handler tool (`message_mode: none`, `interruptible: true`, `trigger_pattern: "Have a good day|have a good day"`, `trigger_timeout: 3`, `trigger_pattern_both: "goodbye|bye|have a good day|you too|thank you|thanks|take care"`; description: "You normally do NOT call this: the phrase 'Have a good day.' ends the call by itself"). Transition to `collection` when `verify_identity_response.data.all_verified` equals `true` or `True`. `max_node_turns: 80`.
- **`collection`** (conversation): TTS "Thank you, that's verified. I'm calling about your Freya Bank account, do you have a minute?"; tools `get_account`, `create_promise` (model fills `product_id`, `amount`, `date`), the same `end_call` tool; prompt ends "Now: {{now}}."; no transitions (the call ends via the trigger phrase).
- **Workflow-level `tools`:** `close_call` as an **`end_of_call` lifecycle tool**: `outcome` (enum of only 4: `promise`, `no_promise`, `not_verified`, `not_reached`) and `reason` are model-filled from the conversation after the call; `pre_process_code` drops `reason` when the outcome is `promise`/`paid`.
- Why it scores low (our reading): the opening never says the call is recorded (A1); no third-party, callback, transfer, note handling; only 4 outcomes; no date/amount logic or persuasion rules; no read-back discipline; no tool-failure handling; no `what_to_do_next` hooks.

## README troubleshooting (verbatim list, condensed)

| Symptom | Cause / fix |
|---|---|
| `error code: 1010` in an HTML page | no browser-like `User-Agent` (`freya.py` sets one) |
| `Workspace plan limit reached` | too many workflows — update one in place |
| Score doesn't move after a change | the update wasn't **published** (`freya.save_workflow` publishes; plain `PUT` doesn't) |
| A customer fails and you don't see why | `freya.get_call(call_id)["messages"]` (full transcript with tool calls); `run_cases.py --out results/run.json` saves call ids |
| Calls end `customer-ended-call` too early | agent silent too long; check the printed slowest turn; if the same agent is fast next run, the model was busy |
| Want to see what the agent says without a simulation | `POST /api/v2/chat/message` (one turn at a time) |
| Bank says `unknown product_id` | the model invented an id — product ids come from `get_account` (`p1`, `p2`…); give them to the model in the tool result or fill them with code |
| Simulation stays "running", no call starts | the workflow can't start a call; try one chat turn; leave `agent_config` out of what you send |
| Agent says nothing after a tool call, customer hangs up | see "Tool results and the next turn" (`what_to_do_next` post-hook) |

## Hints about the hidden briefs that are already in the public kit

Not hidden-brief content — just what the public files reveal about the space of variation (fair game for generalisation):

1. `run_cases.py` can voice identity answers for **`postcode`, `birth_year`, `company_number`, `founded_year`** besides `date_of_birth`/`phone_last4` → other security questions, possibly **business customers**.
2. `score.py` treats **`no_contact`** and **`unreached`** like `not_reached` → other outcome names.
3. Case records support `third_party: true`, a per-case `style`, and `faults` on any tool.
4. The page's example of a number said in two parts — "463..." then "51" — fits a company number / postcode-style answer.
5. The final runs "on several calendar days" → `now` varies; holidays and deadlines must be computed from `now` and the brief's calendar.
6. "Other limits and deadlines, another outcome table, another calendar", tool **fields and allowed values can change** (e.g. `verify_identity.field` enum, `close_call.outcome` enum, `add_note.reason`, `transfer_to_agent.queue`, product types and floor fields).
