# 07 — Freya REST API for a builder

Sources: the kit's `docs/api.md` (every call there was taken from a client run against the platform, unless marked "not confirmed"), `freya.py`, and the live OpenAPI spec the docs site renders (`https://staging-app.freyavoice.ai/api/openapi.json`, OpenAPI 3.1, 96 paths — saved at `reference/freya-docs/openapi/live-openapi.json`; readable renderings of the relevant endpoints are in `reference/api-rendered/`).

**Workflow creation/update and the workflow JSON are not in the public docs** — only in the kit. Everything in "Part B" below is from the live spec and was not exercised by the kit's client.

## Basics

| Item | Value |
|---|---|
| Base URL (event) | `https://staging-app.freyavoice.ai` (paths below are under `/api/v2`). The docs' spec lists production `https://app.freyavoice.ai/api/v2` — **use staging for the event**. |
| Auth | `Authorization: Bearer <key>`; keys start with `fak_`. Every key expires (default 90 days). |
| Content type | `Content-Type: application/json` |
| **User-Agent** | **Required and must look like a browser**, e.g. `Mozilla/5.0 (my-builder)`. Without it Cloudflare answers an HTML page with `error code: 1010`. Many HTTP libraries' default agents are rejected. |
| Envelope | `{"success": true, "data": {"message": "...", "result": {...}}}` — payload is `data.result`. Errors: `success: false`, `result: null`. |
| Wrong route | an **HTML 404**. Workflow and call routes are **singular** (`/workflow`, `/call`); persona and simulation routes are **plural**. |
| List routes | need the workspace id as a query parameter — the live spec names it **`workspaceId`** (the kit said "not confirmed"; `freya.py` already uses `workspaceId`). |

The reference client reads wrapper keys (`workflow`, `simulation`, `iterations`, `workspaces`) and falls back to the bare payload if a key is missing — do the same.

## Part A — calls the kit confirmed

### Workflows

| Call | Body / params | Result |
|---|---|---|
| `POST /api/v2/workflow` | `{"name": "...", "workflow": {…complete workflow…}}` | `result.workflow.id`, `result.workflow.agentId` (pass `agentId` to simulations). The platform creates the agent together with the workflow. |
| `POST /api/v2/workflow?dryRun=true` | same as create | runs write validation, stores nothing. Result fields undocumented; treat any HTTP error as failure and print the body. **Validation silently drops fields that don't belong to a node type** (e.g. `pre_actions` on a conversation node) — read back what was stored if unsure. |
| `PUT /api/v2/workflow/{workflowId}` | `{"workflow": {…}}` | **Replaces the whole definition.** A top-level key you leave out is deleted (incl. `test_variables` and the platform-filled `agent_config`). **Saves a new version and does NOT publish it.** |
| `GET /api/v2/versions/workflow/{workflowId}?workspaceId=…` | | `result.versions[]`: `id`, `versionNumber`, `isPublished` |
| `POST /api/v2/versions/workflow/{workflowId}/publish` | `{"versionId": "<newest>"}` | publishes; simulations and calls run the **published** version |
| `GET /api/v2/workflow/{workflowId}?workspaceId=…` | | `result.workflow` (`id`, `agentId`, `updatedAt`, `workflow` = the definition, `nodePositions`, …) — used by `freya.export_workflow` |
| `GET /api/v2/workspaces` | | `result.workspaces[].id` |

A simulation run reports the version it used as `agentVersionNumber` — check it when a change seems to have no effect.

### Personas

`POST /api/v2/personas` with `{"personas": [{"name", "prompt", "successCriteria", "tags": []}]}` → `result.personas` in request order, each with `id`. A persona plays the caller; `successCriteria` is what the judge model checks after the call.

### Simulations

`POST /api/v2/simulations`:

```json
{ "agentId": "AGENT_ID", "name": "practice run 1", "mode": "chat",
  "selectedPersonaIds": ["PERSONA_ID"],
  "customerVariablesMap": {"PERSONA_ID": {"customer_id": "c_123", "first_name": "Dana"}},
  "maxConcurrentCalls": 5, "runsPerPersona": 1, "maxCallDurationSeconds": 420,
  "assistantLlmOverride":  {"provider": "experimental-5", "model": "experimental-5"},
  "routingLlmOverride":    {"provider": "experimental-5", "model": "experimental-5"},
  "extractionLlmOverride": {"provider": "experimental-5", "model": "experimental-5"},
  "personaLlmOverride":    {"provider": "google", "model": "gemini-3-flash-preview"},
  "analysisLlmOverride":   {"provider": "google", "model": "gemini-3-flash-preview"} }
```

- Pass **all three agent overrides** on every simulation (a missing one falls back to the agent's default model).
- `result.simulation.id`. Poll `GET /api/v2/simulations/{id}` every 10 s until `result.simulation.status` ∈ {`completed`, `failed`, `paused`}.
- **One simulation at a time per workspace**: a second create fails with an error containing "concurrent simulations" (`freya.run_simulation` waits 30 s and retries).
- `GET /api/v2/simulations/{id}/iterations` → `result.iterations` (take the first entry's `id` right after a run).
- `GET /api/v2/simulations/{id}/iterations/{iterationId}?limit=100&offset=0` → `iteration`, `runs`, `runsTotal`. Default page 30 runs, max 100 — page until short (`freya.get_iteration` does it). Run fields: `id`, `callId`, `personaId`, `personaName`, `outcome` (e.g. `pass`/`fail`; `queued`/`running` while in progress), `reason` (judge's explanation), `turnCount`, `startedAt`, `endedAt`.

### Calls (transcripts)

`GET /api/v2/call/{callId}` → `result.call`: `messages` (event list), `transcript` (one string), `endedReason` (for an `end_call` node: the terminal's `function.name`; `customer-ended-call` when the simulated customer hung up), `duration`, `successCriteriaResult` (`success`, `reason`).

Each message: `role`, `message`, `nodeId`, `messageId`, `secondsFromStart`. `role` = `assistant` (agent said), `user` (caller said), `system` (JSON string of one engine event):

| `event` | Content |
|---|---|
| `node_enter` | `node`, `from_node`, `reason` |
| `function_call_start` | `function`, `args` (for `api_call`: full request `url`, `method`, `headers`, `body`) |
| `function_call_complete` | `function`, `result` |
| `route_evaluated` | `matched`, `from_node`, `target`, `reason`, `branches` (every condition's result: variable, operand, result), `variable_table` (all variables at that moment) — **fastest way to learn why a transition did or didn't fire** |
| `error` | `message`, `details` |

User/assistant messages in the trial call also carried a `workflowSnapshot` (`currentNode`, `previousNode`, `nodeTurnCount`, `totalTurnCount`, `transitionHistory`, `enteredNodes`, `variableTable` — each entry `value`, `confidence`, `source`, `source_node`). To check whether a variable arrived, read `variable_table`/`variableTable` — seeing its name in a prompt proves nothing.

### Chat: talk to a workflow turn by turn (seconds, no simulation queue)

```bash
curl -s -X POST "$FREYA_API_URL/api/v2/chat/message" \
  -H "Authorization: Bearer $FREYA_API_KEY" -H "Content-Type: application/json" -H "User-Agent: $UA" \
  -d '{"workflowId": "'$WORKFLOW_ID'", "message": "Hello?", "customerVariables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}'
```

`result.response` (what the agent said) and `result.callId`. Next turn: same body with `callId`. End: `POST /api/v2/chat/end` with `{"callId": "..."}`. Runs against the **published** workflow.

Seen in tests, not guaranteed: a long turn can return **504**; when the first step is a code step the chat route **may skip it** (values it computes are empty); a bare **500** means the workflow cannot start a call at all (also: a simulation stuck at "running" with no call → try one chat turn; leave `agent_config` out of what you send).

### Minimal loop (kit)

1. Build the workflow JSON → 2. `POST /workflow?dryRun=true`, fix rejections → 3. `POST /workflow`, keep `agentId` → 4. `POST /personas` once → 5. `POST /simulations` → 6. poll → 7. iterations → runs → 8. for failed runs, `GET /call/{callId}` and read the events.

## Part B — more endpoints in the live spec (not verified by the kit)

Use sparingly ("do not probe or load-test the platform"). All under `/api/v2`, Bearer auth.

### Chat extras

- `POST /chat/message` also accepts **`versionId`** (target a specific version), **`fromMessageId`** (branch from an earlier assistant turn of the same call — test several customer replies from one point without replaying the whole conversation), and `agentId` instead of `workflowId`. Response adds `messageId`, `warning`, `endedByAgent`. Errors: 404 call not found, 409 no resume anchor, 422 customerVariables too large, 502 no response from agent service, 504 timeout. `message` 1–10000 chars.
- `POST /chat/fork` `{parentCallId, fromMessageId, versionId|agentId|workflowId}` → a new dormant call copying messages up to the anchor; drive it with `/chat/message`.
- `POST /chat/end` `{callId}` → `ended`, `endedReason`, `alreadyEnded` (idempotent). **It fires the end-of-call lifecycle** (webhook, post-conversation analysis, **end-of-call tools**) — so an `end_of_call` `close_call` tool would hit the bank when you end a chat.

### Versions (`entityType` ∈ {`agent`, `workflow`})

- `GET /versions/{entityType}/{entityId}?workspaceId=…&entityId=…` — history (`versionNumber`, `isPublished`, `publishedAt`, `configDiffSummary`, `openBranches`).
- `POST /versions/{entityType}/{entityId}` `{entityId, workspaceId, configSnapshot, parentVersionId?, description?}` — "the snapshot is validated against that entity's config schema and applied to the working copy, so an invalid snapshot is rejected with **422**."
- `GET /versions/{entityType}/{entityId}/{versionId}` (full `configSnapshot`, `configDiff`), `PUT` (metadata), `GET …/graph` (commits incl. per-version `checks`: unit and sim pass/fail counts).
- The publish route the kit uses (`POST /versions/workflow/{id}/publish`) is not in the spec but is confirmed by the kit.
- Branches (`/branches`, commit, rebase = merge, discard, activity) also exist — not needed.

### Personas

- `GET /personas?workspaceId=…` (prompt/successCriteria truncated to 280 chars unless `include=prompt,successCriteria`), `GET/PUT/DELETE /personas/{personaId}` (delete → 409 while simulations use it; `force=true`).
- Persona fields: `name`, `prompt` (≤100k chars), `successCriteria`, `systemPrompt`, `evaluationPrompt`, `tags`, `agentIds`. Up to 200 personas per create call.
- `POST /personas/preview` `{agentId, prompt, count (1–50, default 3)}` → AI-generated `{name, prompt, successCriteria, tags}` suggestions.

### Simulations

- Create also takes `description`, `tags`, `assertions` (ids), `maxRetries` (0–10), **`agentVersionId`**, **`start: false`** (create a draft; `POST /simulations/{id}/start` dispatches it). Ranges: `maxConcurrentCalls` 1–1000, `maxCallDurationSeconds` 60–3600 (default 240), `runsPerPersona` 1–50, `mode` `voice|chat` (default `voice`!). Persona/analysis overrides accept `reasoningEffort` (`none`…`xhigh`).
- `GET /simulations?workspaceId=…&status=draft|running|paused|completed`, `GET/PUT/DELETE /simulations/{id}` (`include=` for full persona text), `POST /simulations/{id}/rerun` (new iteration).
- `GET /simulations/{id}/iterations` (newest first; per iteration `status`, `passedRuns`, `failedRuns`, `inconclusiveRuns`, `errorRuns`, `passRate`, `agentVersionNumber`, `agentLlm`, `params`).
- `GET /simulations/version-checks` / `version-persona-runs` `?workspaceId&entityVersionId` — results per version.

### Unit tests (behavioural tests on one turn — potentially a fast self-test path)

- `POST /unit-tests` `{workspaceId, entityType: "workflow", entityId, name, expectation (judge text), assertions[], input: {schemaVersion: 1, callType: "web"|"voice", messages: [{role, message}…], customerVariables}, judgeContext, tags}`.
- Assertion types: `routing` (`signal`: `node_entered` | `route_target`, `target`, `negate`), `extraction` (`name`, `match`: exists/equals/contains/regex/absent, `value`, `minConfidence`), `tool_call` (`tool`, `args`, `argsMatch`: subset/exact, `negate`).
- `POST /unit-tests/run-all` `{workspaceId, entityType, entityId, entityVersionId?, unitTestIds?, onlyFailed?, mockToolResults?, judgeLlmOverride?, assistantLlmOverride?, repeat (1–20)}` → `202` with `runIds`. **`mockToolResults`** (free-form object) suggests tool results can be mocked — useful for hidden briefs where no practice customers exist. Untested.
- `GET /unit-tests/runs/{runId}` → `outcome` (`queued`/`running`/`pass`/`fail`/`error`), `verdictReason`, `agentResponse`, `assertionResults`, `latencyMs`, `judgeModel`.
- Also: list (`?workspaceId&entityType&entityId`), get, `PATCH`, archive (`DELETE`), `/unit-tests/{id}/runs`, `/unit-tests/overview`, `/unit-tests/version-runs`.

### Misc

- `GET /workflow?workspaceId=…` (list; `latestVersionNumber`, `agentId`), `GET /workflow/templates?workspaceId=…`.
- `GET /agents/defaults?workspaceId=…` — the default agent config (what `agent_config` holds): `llmConfig` (`provider`, `model`, `systemPrompt`, `temperature` default 0.7, `maxTokens` default 1000, `firstMessage`, `firstMessageMode`, `tools`…), `ttsConfig`, `sttConfig`, `callTimeoutSettings`, `guardrailsConfig`, `piiRedactionConfig`, `routingLlmConfig`, `extractionLlmConfig`, `postConversationAnalysis`, `testVariables`… Agent tool schema also lists `config.maxPerNTurns`, `config.preSpeech`, `function.transition_to`, extraction `required`/`overridable` — unverified for workflows.
- `GET /api-keys/check` → `valid`, `workspaceId`, `name`, `isActive`, `expiresAt`, `rateLimit {requestsPerMinute, requestsPerDay}` — a cheap way to verify the key and see its rate limit.
- `GET /workspaces/{workspaceId}/credits` → `creditsLeft`, `billingUnit`, …
- `GET /call/{callId}` in the spec also has `turnLatencyStats` (p50…p99), `assertionResults`, `problems`, `entityVersionNumber`.
