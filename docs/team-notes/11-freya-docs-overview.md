# 11 — What docs.freyavoice.ai contains (and what matters for us)

Crawled Sat 10 Oct 2026: all 188 pages listed in `https://docs.freyavoice.ai/llms.txt` (Mintlify site), saved as Markdown in `reference/freya-docs/pages/` (same paths as the URLs), plus `llms.txt`, `llms-full.txt` (all pages concatenated) and the OpenAPI files in `reference/freya-docs/openapi/`:

| File | What |
|---|---|
| `live-openapi.json` | `https://staging-app.freyavoice.ai/api/openapi.json` — OpenAPI 3.1, **96 paths**, the spec every API page on the docs site renders. Most complete. |
| `docs-openapi.json` | `https://docs.freyavoice.ai/api-reference/openapi.json` — an older OpenAPI 3.0 copy (58 paths; no chat, personas, simulations, versions, unit tests) |
| `model-apis-openapi.json` | STT/TTS model APIs |

Readable renderings of the endpoints that matter to a builder: `reference/api-rendered/*.md` (generated from `live-openapi.json` with `reference/scripts/render_openapi.py`).

## Big picture

Freya is a voice-AI platform: you build **agents** (one LLM config with prompt, tools, voice) or **workflows** (node graphs with per-node prompts, tools, routing — what we build), connect them to **phone numbers** (SIP/Twilio), run **campaigns** (outbound lists), and inspect **calls**, analytics, simulations and unit tests. For this hackathon only a thin slice matters: workflows, chat, personas, simulations, calls, versions (and maybe unit tests). Telephony/voice/campaign/knowledge-base pages are background.

**The docs do not document workflow creation or the workflow JSON** (only list/get/templates). The kit's `docs/workflow-format.md`, `docs/tools-and-code.md` and `docs/api.md` are the reference for that.

## Relevance map

| Section | Pages | Relevance | Takeaways |
|---|---|---|---|
| Introduction / Getting Started (workspace, agent, workflow, AI Studio, phone numbers, inbound/outbound) | 10 | low | UI walkthroughs. Workspace settings at `/workspace/settings`; members are Admin or Member; AI Studio = an in-dashboard prompt-editing assistant; simulations recommended before going live. |
| Learning path: Core Concepts, Architecture, Best Practices | 4 | low–medium | Generic: agents = prompt + model + voice + functions + context; workflows = nodes, conditional connections, variables; best practices: specific prompts with examples and boundaries, plan for failures, test all paths in simulation, version configs. |
| Fundamentals: Workspaces, Agents, Workflows, Phone Numbers, Integrations | 5 | low | Conceptual. Workflow patterns: simple routing, conditional routing, multi-agent hand-off, human escalation, function integration. SIP endpoints: `sip.us1.freyavoice.ai:5080`, `sip.eu1…:5080`, `sip.tr.freyavoice.ai:5060`. |
| Features: Knowledgebase (beta, hybrid search over articles/snippets), Analytics (calls tab, structured-data widgets), Campaigns (draft → scheduled → active → completed/partially completed; schedule, retries, webhook; prompt `{{variables}}` become customer columns) | 3 | none for scoring | Not used by the phone agent (it may only call the bank tool API). |
| Telephony: overview, inbound, outbound, call routing, voice configuration | 5 | none | Voice only. |
| Embed SDK + client reference | 2 | none | Browser WebRTC/chat widget; backend mints a token via `POST /api/token/embed` (permission `calls:web-token`). |
| API reference: Authentication + Introduction | 2 | medium | Bearer token from Settings → API Keys; the Call API is "still experimental and the definitions may change without immediate notice". |
| API reference endpoints | ~150 | **high for: chat, personas, simulations (+iterations), calls, workflows, versions, unit tests, api-keys/check** | See `07-freya-rest-api.md` (Part B) and `reference/api-rendered/`. |
| Webhooks (call outcome, end-of-call report) | 2 | none | Campaign/production integrations. |
| Model API reference (STT `stt.freyavoice.ai`, TTS `tts.freyavoice.ai`, OpenAI-compatible) | 5 | none | Conversations in this event are text. |

## API surface (live spec, by tag)

Campaigns (7) · Calls (list/initiate/bulk update/delete, details, tags, insights, recording, raw ZIP export/import, inbound web) · Agents (list/create/delete/defaults/get/update) · **Workflows (list, get, templates)** · Feedbacks (+ statuses, assignees, comments, references, open-for-agent) · Branches (list/create/get/update/commit/rebase/discard/activity) · API keys (list/create/update/delete/**check**) · OAuth connections · Analytics (+ widgets, credits, structured data) · Phone numbers · Phone aliases · Alerts (destinations, rules, events) · Suppression list · Workspaces (+ members, roles, invitations, logs, credits) · Export · Integrations · Reviews · Favorites · Audio (transcriptions, speech) · **Personas** (list/create/preview/get/update/delete) · **Simulations** (tags/list/create/get/update/delete/iterations/version-checks/version-persona-runs/start/rerun) · **Unit tests** (version-runs/overview/list/create/get/update/archive/run-all/run/runs) · Webhooks · Custom (TTS abbreviations) · **Chat** (message/fork/end) · Insights + agent insights · **Versions** (list/create/get/update/graph) · Permissions · Workspace roles.

Not in the spec but confirmed by the kit: `POST /workflow` (+ `?dryRun=true`), `PUT /workflow/{id}`, `POST /versions/workflow/{id}/publish`, `GET /simulations/{id}/iterations/{iterationId}`.

## API-key permissions (from the create-key schema)

Keys can be scoped, e.g. `agents:read|write|delete|sync|test`, `workflows:read|write|delete|sync|test`, `calls:read|write|…|chat-message|…`, `campaign:*`, `feedbacks:*`, `reviews:*`, … Our event key must at least cover workflows, simulations/personas and calls/chat — if a call returns 403 "insufficient permissions", check the key's permissions in the dashboard.
