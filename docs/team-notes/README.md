> Copy of the team's working-folder index (`hack/README.md`, 11 Oct 2026). Paths in it are relative to that folder: `notes/` is this directory, `reference/scripts/` is `scripts/` here. `reference/` (a copy of the public Freya docs, the hackathon page capture and the kit zip) was not copied; the kit itself is the first commit of this repository.

# Build the Builder (Freya × YC, 10–11 Oct 2026) — team notes

Everything learned from the hackathon page, the **v3 starter kit** and **docs.freyavoice.ai**, organised for a team of two. Collected Sat 10 Oct 2026, ~19:00 UTC (22:00 Istanbul). If the organisers email a kit v4, re-check `notes/08-kit-walkthrough.md` against its changelog.

## Our builder (rebuild, branch `rebuild/core`)

`build-the-builder/` is our git repo (synced from the cloud session). Start with `build-the-builder/BUILDER.md`: one command `python3 builder/build.py <brief.md> <openapi.json>` builds, self-tests, publishes and exports a phone agent with a trace in ~1 minute. `source ../env.sh` first. Builder-produced agents: Brief A 10/10, Brief B 3/3 on the live practice cases (11 Oct). `_to_delete/` only holds sync leftovers.

## The task in one paragraph

We write a **builder**: one command that takes a bank's **brief** (one Markdown file) and the bank's **tool API** (an OpenAPI file) and creates a **phone agent** — a Freya workflow — with no manual edits, in ≤ 30 minutes. Freya runs that agent in **text** conversations with simulated customers who are late on payments. **Score = hidden cases passed / 60.** A case passes only if (1) the bank's ledger is exactly right, (2) the conversation followed the brief, and (3) the agent never lied (e.g. said "recorded" when the tool call failed) — in **all 3 runs**. The two hidden briefs change identity questions, limits, deadlines, outcome table, calendar, and tool fields/values; one of them is raw bank material (mail + policy extract + a memo that changes it + a code list).

## Clock

| | UTC | Istanbul |
|---|---|---|
| Started | Sat 10 Oct 10:00 | Sat 13:00 |
| **Hidden briefs emailed** (2 briefs + their tool API files) | **Sun 11 Oct 17:00** | **Sun 20:00** |
| **Deadline** — submission form by email | **Sun 20:00** | **Sun 23:00** |

## What's in this folder

| Path | Contents |
|---|---|
| `notes/01-hackathon-rules-and-scoring.md` | task, timeline, scoring (3 checks), final benchmark, submission + trace + verification, limits, rules, prizes, full FAQ |
| `notes/02-briefs-digest.md` | Brief A (47 rules) and Brief B (11 rules) grouped into a call flow, outcome table, computed dates, judgment calls, what the judge checks |
| `notes/03-practice-cases.md` | the 13 practice customers with deadlines, expected ledgers, checks; how `run_cases.py` runs a case; the simulated customer's prompt; talking styles |
| `notes/04-bank-tool-api.md` | the 7 bank tools, ledger + scorer logic, practice endpoints, faults, how to wire a bank tool into Freya |
| `notes/05-freya-workflow-format.md` | workflow JSON cheat sheet: nodes, prompts, variables, transitions, extraction, end-call, limits |
| `notes/06-freya-tools-and-code.md` | `api_call` tools, `default` baking, `response_mapping`, automatic variables, hooks, code nodes, lifecycle tools, `what_to_do_next` |
| `notes/07-freya-rest-api.md` | REST calls a builder needs (kit-confirmed) + extra endpoints from the live spec (chat branching, versions, personas, simulations, unit tests) |
| `notes/08-kit-walkthrough.md` | every kit file, `freya.py` functions, the example builder + skill, base agent anatomy, troubleshooting, hints about hidden briefs |
| `notes/09-strategy-and-plan.md` | **our recommendations**: builder architecture, spec schema sketch, workflow shape, testing loops, 2-person split, timeline, submission checklist, risks |
| `notes/10-gotchas.md` | every pitfall from all sources in one list |
| `notes/11-freya-docs-overview.md` | what docs.freyavoice.ai covers and which parts matter |
| `reference/kit/` | `build-the-builder-v3.zip` + extracted `build-the-builder/` (note hidden `.claude/`) — copy it to start working |
| `reference/hackathon-page/` | raw HTML + full text capture of the hackathon page |
| `reference/freya-docs/` | all 188 docs pages as Markdown (`pages/`), `llms.txt`, `llms-full.txt`, `urls.txt`, OpenAPI files (`openapi/live-openapi.json` is the complete one) |
| `reference/api-rendered/` | readable Markdown of the relevant live-spec endpoints |
| `reference/scripts/` | `date_rules.py` (tested business-day helpers), `dates_check.py` (verifies all 13 expected dates), `render_openapi.py` |

## Top things not to forget

1. **No partial credit; 3/3 runs per case.** Ties: promised amount on passed cases → shorter build time (from traces) → earlier submission.
2. **One command**: `python3 builder/build.py {brief_path} {tool_api_path}`; ≤ 30 min per brief **including self-tests**; no manual edits; export with `freya.export_workflow` — **what you export is what is scored**.
3. **After 17:00 UTC Sunday: crash fixes only.** No rule, value or name from a hidden brief in code or prompts (a reviewer checks the commit). Top-10 builders are rerun; a clearly lower rerun score removes the entry.
4. **Trace per hidden brief** (no trace → not ranked): start/end time, every model call (model + one-line purpose), workflow id, agent id, #steps, #tools, self-tests + results. **Strip API keys.**
5. The phone agent runs on `experimental-5` (`AGENT_LLM` in `freya.py`) — don't change it. It may call **only** the bank tool API; code nodes and hooks are fine.
6. **Read everything from the brief + tool API file**: identity questions (hint: the kit's simulator already knows `postcode`, `birth_year`, `company_number`, `founded_year`), bands/deadlines, holidays, outcome names (hint: the scorer knows `no_contact`, `unreached`), tool URLs/fields/enums.
7. Final customers: **1–3 products, several calendar days** (`now` varies), talk like people (numbers in two parts, self-corrections, small talk, questions back, words for numbers/dates).
8. **Compute dates, deadlines, floors, attempt counts and the closing outcome in code**, not in the model's head. The bank API enforces nothing.
9. After every tool result the model may go silent or ignore a negative result → **post-hook `what_to_do_next`**, and "always speak or call the next tool".
10. Required exact sentences (Brief A): "Am I speaking with {title} {last_name}?", "Can you make this payment today?", "Do you confirm?", "You will receive a text message confirming this promise.", "I am sorry for your loss." Never "how much can you pay?". No "collections"/"debt"/"payment"/product words before identity is verified. Say "recorded" only after `ok: true`.
11. Exactly **one `close_call`, last tool call**, goodbye before it.
12. **Update ≠ publish** (`save_workflow` publishes); `PUT` replaces the whole workflow; send no `agent_config`; browser-like `User-Agent` or you get Cloudflare `error 1010`.
13. Workflow JSON traps: no nulls; `tools` only on conversation nodes, `pre_actions` only on api/code nodes (silently stripped); mapping paths start with `data.`; booleans arrive as `"true"`/`"True"`; passthrough nodes end with `always`; code has no `{{`/`}}` and never raises; `default` not `const`.
14. **One simulation at a time per workspace** and one workspace + **one Freya key per team** → coordinate; use the chat API (`/api/v2/chat/message`) for fast tests in parallel.
15. The hidden briefs arrive by **email** — mail to Outlook/Hotmail/some university addresses was filtered: check spam at 20:00 Istanbul.

## Ten-minute start (from the kit)

```bash
cp -R reference/kit/build-the-builder ~/somewhere/build-the-builder && cd ~/somewhere/build-the-builder
cp env.example env.sh   # FREYA_API_KEY=fak_…, FREYA_API_URL=https://staging-app.freyavoice.ai, FREYA_BANK_TEAM_KEY=<16+ chars, fixed>
source env.sh
python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"
python3 tools/run_cases.py <agent_id> --brief A          # 10 cases, 3–11 min (the base agent passed 2 of all 13 in the organisers' run)
pip install claude-agent-sdk
python3 examples/agent_builder.py briefs/brief-a.md                     # example builder (got 10/10 on A in one run)
python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md   # Brief B builds on A
```

Dashboard test calls: the workspace's practice customer answers DOB **14 March 1988**, last four **4471**; it resets after 5 idle minutes.

## Sources

- Hackathon page: https://www.freyavoice.ai/hackathon
- Kit v3: https://www.freyavoice.ai/hackathon/build-the-builder-v3.zip
- Freya docs: https://docs.freyavoice.ai (index: https://docs.freyavoice.ai/llms.txt)
- Live API spec: https://staging-app.freyavoice.ai/api/openapi.json
- Dashboard (event): https://staging-app.freyavoice.ai — workspace settings: https://staging-app.freyavoice.ai/workspace/settings
- Registration: https://events.ycombinator.com/AI-FDE-Build-the-Builder26
