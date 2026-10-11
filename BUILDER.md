# Our builder (branch `rebuild/core`)

One command turns a bank brief and its tool API file into a tested phone agent on Freya:

```bash
source env.sh                                   # FREYA_API_KEY, FREYA_BANK_TEAM_KEY (never committed)
python3 builder/build.py <brief.md> <openapi.json>
python3 builder/build.py <base brief.md> <extension brief.md> <openapi.json>   # e.g. Brief A + Brief B
```

About 50–95 seconds, no manual step. It writes:

| Output | What it is |
|---|---|
| `traces/<UTC start>-<slot>.txt` | the trace to submit: start/end, every model call (model + purpose, failures too), what was created on Freya, every self-test |
| `submission/<brief>.workflow.json` | the exported phone agent (`freya.export_workflow`) to submit |
| `submission/<brief>.policy.json`, `.answers.json` | what the model read from the brief (for review) |

The workflow goes to slot `rb-<brief file name>` (created once, then updated in place and published).

## How it works

1. **Tool API** (`builder/policy/openapi.py`, `roles.py`): reads the OpenAPI file and maps its field names to roles
   (the finals may rename fields: `products` → `facilities`, `date` → `pay_date`, one `callback_at` date-time…).
2. **Policy extraction with Freya's model** (`builder/policy/extract.py`, `builder/llm_freya.py`): nine questions in
   parallel through the chat API on helper workflow `rb-llm`, each answer checked and re-asked with its errors;
   deterministic repairs (missing outcome mappings, band gaps, first request listed as an extra offer…); one
   repair round if the policy still fails validation. Bounded: 14 minutes for the model part, 30 for the build.
3. **Workflow** (`builder/emit/workflow.py`): one `decide` code step per customer turn (`builder/runtime/agent_runtime.py`,
   stdlib only, zlib-compressed into the node: the platform caps code + variables at 131,072 bytes), engine-run
   tool calls, write chains that end without a customer turn, fixed endings with close_call retried once.
4. **Self-tests** (`qa/selftest.py`): local walks of customers made up from the extracted policy against a bank stub
   that speaks the brief's own tool API (happy path, wrong number, identity failure, already paid, refusals).
5. **Platform**: dry run, save + publish, two-turn chat smoke test (opening + first decide step), export.

At call time the agent calls only the bank's tool API. Freya's model is used only by the platform's extractor.

## Final day (Sunday 11 Oct, briefs at 17:00 UTC / 20:00 Istanbul, deadline 20:00 UTC / 23:00 Istanbul)

1. `git pull` / use this folder as is; `source env.sh`; `python3 -m qa.identity` (note the hash).
2. Put each final brief and its tool API file in `briefs/final/` (do not edit them).
3. `python3 builder/build.py briefs/final/<brief>.md briefs/final/<api>.json` — once per final brief.
4. Check the trace ends with `status: OK` and all `TEST … PASS`. If it crashed on a table the parser did not expect,
   fixing that crash is allowed; adding anything from the final brief (rules, values, names) is not.
5. Submit `submission/<brief>.workflow.json`, the trace, and the code (this repo at that commit).

Optional live check (one simulation at a time; the QA operator runs the official evaluation): there are no
practice customers for the finals, so the builder's self-tests and chat smoke are the checks we have.

## Checks

```bash
/root/.local/bin/pytest -q tests          # 168 offline tests (parsers, dates, styles, failures, renamed APIs, extraction)
python3 -m qa.extract_run out.json <api.json> <brief.md>...      # extraction only
python3 tools/run_cases.py <agent_id> --brief A [--style talkative] --out results/x.json
python3 -m qa.check_run results/x.json submission/<brief>.policy.json   # lesson checks on live calls
```

## State on 11 Oct, 07:00 UTC

- Builder-produced agents on the live public cases: **Brief A 10/10**, **Brief B 3/3** (single runs; median slowest
  turn 1–3 s); speech styles pieces / corrects / asks_back / in_words / talkative pass on two cases each.
- Extraction matches hand-written facts for Brief A, A+B, and two raw-material fixtures of different shapes
  (`tests/fixtures/messy-brief.md`, `tests/fixtures/raw2-brief.md`).

## Lessons found live (all covered by tests)

- L16: code + variables per code step must stay under 131,072 bytes (98 KB code broke on three products).
- Enum variables reject `""` from code: reset them to `none` or stale values survive the next turn.
- Judges read "never say *recorded* before a successful create_promise" literally: openings say "we are recording".
- Voice turns get cut at pauses (`I can pay on Thursday,` … `sorry, I mean Friday`): the agent waits for the rest.
- Numbers: "twenty-eight April" is a day, not 2008; "dollars and fifty" is cents; "cannot pay anything" is no offer.
