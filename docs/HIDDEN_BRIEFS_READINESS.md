# Hidden-brief readiness (11 Oct 2026, checked 16:45–16:55 UTC)

**Build from `main`.** The builder and runtime code are byte-identical to tag `baseline-v5-validated` (`969ecad`):
`git diff baseline-v5-validated main` touches only `HANDOFF.md` and `docs/`. The identity check printed
`builder f0e251d303472942 | runtime a6ca24d742b1`; `a6ca24d742b1` is the validated v5 runtime. c3.1 stays on
`experiment/conversation-quality` and is not merged or cherry-picked. Nothing was published while preparing this; no
call or simulation was started.

## 1. Model and configuration: what is documented, observed, unverified

| Question | Answer | Kind of evidence |
|---|---|---|
| Required phone-agent model | `freya.AGENT_LLM` = `{"provider": "experimental-5", "model": "experimental-5"}` (kit `freya.py`; README: "Do not change it"). It can only be changed through `FREYA_AGENT_PROVIDER` / `FREYA_AGENT_MODEL`, which are set neither in `env.sh` nor in the shell | documented (kit) + checked |
| How the model reaches the agent | `freya.update_workflow` (called by `builder/platform.save`) writes `AGENT_LLM` into `agent_config.llmConfig` before publishing | documented (kit code) |
| Published agents | v5 `rb-c2-brief-a` v5 / `rb-c2-brief-a-brief-b` v4 and c3.1 `rb-c3-*` v2: `llmConfig` = experimental-5/experimental-5. `routingLlmConfig`, `extractionLlmConfig` and `postConversationAnalysis.analysisModel` are `null`. The v5 exports in `submission/candidate-2/` carry the same `agent_config` | observed (`GET /api/v2/workflow`, export files) |
| Simulation overrides | `freya.run_simulation` (kit, unmodified; `tools/run_cases_retry.py` only wraps it) sends assistant/routing/extraction = `AGENT_LLM`, persona/analysis = `gemini-3-flash-preview`. These are exactly the kit's documented values (`docs/api.md`, "Create a simulation") | documented + code. The platform's simulation record does not echo the overrides (`settings` has only duration, concurrency, retries and runs), so they cannot be confirmed from the record |
| Routing model | every transition in the v5 workflows is `mode: exact` (95 `always`, 128 variable-equality groups). No model decides a route | observed (export files) |
| Model used by chat-API calls | Dialogue: the published `llmConfig` (experimental-5); the kit notes that a chat turn cannot start when that model is wrong, and all chats started. Extraction (8 nodes use the platform extractor): the chat API takes no override, the config field is `null`, and the call record names no model, so **it is not known which model extracted in chat calls** | dialogue: documented + observed; extraction: **unverified** |
| Chat API skipping a first code step | The kit documents it as "seen in tests, not guaranteed" (`docs/api.md`). Our workflows start at `open`, a conversation node with no pre-actions; the first code step (`decide`) follows an `always` transition after the customer's first reply. In all 10 chat-comparison calls, 6–8 `code_exec` steps per call completed `success`, 0 errors. Bank tools ran: 4–7 `api_call`s per call, plus `end_call` | documented limitation; does not apply to these workflows (observed) |
| Sentiment vs scoring | README "How you are scored": bank records, then policy and honesty read by a judge, three runs per customer. Sentiment is not part of it | documented |

**Consequence for the chat comparison** (`docs/SENTIMENT_COMPARISON.md` on the experiment branch): status **limited,
supplementary diagnostic**.
- No first code step was skipped.
- The customer driver answered coherently in all ten calls: each line answers the agent's question, and the "Okay."
  fallback was never used. It is a keyword script tuned to wording known in advance, though.
- The extraction model of chat calls is unverified, and no judge ran.
- Its bank-ledger checks and sentiment labels are not official simulation passes.

## 2. Build path for the hidden briefs

Checked:
- **Credentials:** `~/Downloads/hack/env.sh` exports `FREYA_API_KEY`, `FREYA_API_URL`, `FREYA_WORKSPACE_ID` and
  `FREYA_BANK_TEAM_KEY`. Read-only API calls work.
- **Workspace:** 20 of 200 workflows are used, and no simulation is running.
- **Helper:** the extraction workflow `rb-llm` exists.
- **Python:** 3.12.7.
- **Time limits:** the builder bounds itself (`builder/build.py`): 30 min per build, 14 min for model extraction,
  and the chat smoke test is skipped when less than 4 min are left.
- **Traceability:** the trace (`traces/<UTC start>-<slot>.txt`) records:
  - the start and end;
  - each input's sha256, the commit, the builder identity and the runtime hash;
  - every model call (model + purpose);
  - every self-test;
  - the workflow id, agent id and published version;
  - the export path and its sha256.

**Two collision risks, avoided with options `build.py` already has:**
- **Slot:** the default slot is `rb-<brief file name>`. A final brief named `brief-a.md` would overwrite the frozen
  candidate-1 slot `rb-brief-a`, and two briefs with the same file name would share one slot. Pass `--slot`.
- **Output folder:** the default output is `submission/`, which holds the earlier exports. Pass `--out`.
- Keep each brief and its own tool API file in their own folder, because both API files may have the same name.

**Commands** (`<x>` = a short name per brief, e.g. `final-1`, `final-2`):

```bash
cd ~/Downloads/hack/freya-builder-final
git switch main && git pull --ff-only && git status --short        # must print nothing
source ~/Downloads/hack/env.sh
python3 -m qa.identity                                             # builder f0e251d303472942 | runtime a6ca24d742b1
mkdir -p briefs/final/<x>                                          # copy the supplied files in, unmodified
python3 builder/build.py briefs/final/<x>/<brief file(s)> briefs/final/<x>/<its api>.json \
    --slot rb-<x> --out submission/final/<x>
```

- **One build at a time.** `builder/platform.save` rewrites `.freya-agents.json`, so two parallel builds can lose a
  slot entry. A build only uses chat calls, no simulation.
- **Raw bank material in several files:** pass every brief file, then the one tool API `.json` last. If a brief part is
  itself a `.json` file, or is not UTF-8 text (PDF, Word), `build.py` stops. Report it at once; any change must be a
  generic builder fix (README, "The final").
- **Outputs:**
  - `submission/final/<x>/<name>.workflow.json`: the export to submit;
  - `submission/final/<x>/<name>.policy.json` and `<name>.answers.json`;
  - `traces/<UTC start>-rb-<x>.txt`;
  - the `rb-<x>` entry in `.freya-agents.json`, which is git-ignored.
- **A second run** with the same `--out` replaces that folder's files (the trace keeps a new name). Use
  `--out submission/final/<x>-run2` to keep both.

## 3. After each build, before submitting

1. **Status:** the trace's `END` line shows `"status": "OK"` and every `TEST` line ends `PASS` (policy validation,
   lint, self-tests, dry run, chat smoke).
   `OK_WITH_TEST_FAILURES` or `FAILED` is reported at once with the trace lines.
2. **The export matches the build:** the export's sha256 equals the trace's, and the trace's commit is the one checked
   out.
3. **Defaults:** read `policy.json` against the brief. The builder fills these with built-in defaults when the
   extraction gives nothing, without a trace warning:
   - the weekend (Saturday and Sunday);
   - identity: 3 wrong answers, decline after 2, answer length 4;
   - the callback window (today or next business day, 09:00–17:00, asked at most 2 times);
   - times the customer may refuse to talk before the call closes (2);
   - date-reading conventions (DMY, "next Friday" = following week);
   - the currency word ("dollars").

   Holidays default to none, and outcome, reason, queue and product values come from the brief's own tool API.

   If the brief says something else, report it as an extraction conflict. A fix must go through the builder and be
   regenerated; the generated agent is never edited by hand, and no value from the brief goes into code.
4. **Bank behaviour:** writes, confirmation order, per-product outcomes and closure are checked by the self-tests
   against a stub that speaks the brief's own tool API, plus the trace's chat smoke. There are no practice customers for
   the hidden briefs, so no scored validation is possible here. Do not use the public practice cases or their dates as
   stand-ins. Any simulation must go through `freya.run_simulation` (the official overrides), one at a time; a
   `run_cases_retry.py` restart waits for the running one instead of starting another.
5. **Preserve:** commit `submission/final/<x>/`, the trace and `briefs/final/<x>/` on `main` right away and push. No
   sentiment step.

## 4. Known non-blockers

- The extraction model of chat calls is unverified (section 1). It affects only the supplementary chat comparison,
  not the build or the official evaluation, which sets its own overrides.
- `submission/brief-a*.workflow.json` are still candidate-1 exports; the v5 exports for the public briefs are in
  `submission/candidate-2/` (a team decision, unchanged).
