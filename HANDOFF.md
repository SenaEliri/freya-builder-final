# Hand-off — candidate 2: runtime fixes on top of candidate 1 (11 Oct 2026)

## Source

| | |
|---|---|
| Download used | `~/Downloads/hack/build-the-builder` — git repo, branch `rebuild/core` @ `0f70e8d` (byte-identical to the newest snapshot `hack/_to_delete/btb-handoff1.tar.gz`). Older snapshots (`95869c9`, `d798445`, kit-only `~/Downloads/build-the-builder`) were not used. The download itself was not modified; work happened in a separate clone. |
| What it contains | **Both** the full builder source (`builder/`, `qa/`, `tests/`, `tools/`) **and** the exported Freya workflows (`submission/*.workflow.json`). The exports are reproducible: `builder/emit/workflow.py` on `submission/<brief>.policy.json` gives exactly the exported workflow plus platform-filled defaults (checked node by node). |
| History | The teammate's 16 commits are kept as they are; this work adds commits on top (no force-push, nothing rewritten). |
| Not copied | `env.sh` (credentials), `.freya-agents.json` / `.personas.json` (local platform state, git-ignored), `results/` (raw run logs, git-ignored; summaries are below), the copy of the public Freya docs, the hackathon page capture and the kit zip (the kit is the first commit). Team notes are in `docs/team-notes/`. |

## Design (unchanged)

The bank API gives the account facts and the write results; the brief (extracted into `submission/<brief>.policy.json`)
gives the rules; Freya's runtime model only extracts `reply/intent/topic/pay_date/pay_amount` from the customer's turn;
one deterministic decide step (`builder/runtime/agent_runtime.py`) validates values, counts attempts, reads back,
confirms and drives the writes. No model call was added; the fixes are in how the decide step reads the extracted
values in context (the active question, the pending offer, the per-product state, the whole message).

## Defects confirmed on candidate 1 and fixed

Each was reproduced first (local walk with the real decide code, or a live transcript), then fixed in
`builder/runtime/agent_runtime.py` (two wording changes in `builder/emit/workflow.py`), then covered by a test in
`tests/test_regressions.py` or `tests/test_walk_livelike.py`. 47 of the 59 regression tests fail on candidate 1;
the other 12 guard behaviour that already worked (B6 deadline clamping, write retries, weekend alternative, ...).

| | Defect (reproduced) | Fix |
|---|---|---|
| A | `I cannot pay today.` with the extractor's `pay_date: today` was read back as a promise for today | a day the message negates is not a payment day; a bare no to today is a flat refusal (attempt 1) |
| A | `I cannot pay today, but I can pay on the 12th` (extractor copied `today`) was recorded for today | the payment day the message itself links to paying is used |
| A | `My salary arrives on the 12th; can I pay both then?` (`pay_date: then`) was ignored, generic attempt offered | `then` resolves to the income day named in the same message; both products get it |
| A | hardship and the customer's own day/amount in one turn: the proposal was dropped | one sympathy sentence, the proposal is handled, no persuasion; a later refusal gets the support offer, then `no_promise/hardship` |
| B | an amount without a day: `Which exact day?` → `Okay.` recorded the promise **for today** | a missing day is asked again, then the deadline is proposed (A21); never today by default |
| B | `the card and the car loan in October` → `Thirty.`: the card was lost (scope matcher) and a generic attempt-1 offer was mixed in | the group keeps its scope across turns and is checked per product (card on its own deadline, said in the read-back) |
| B | a cousin's wedding date in a comma-joined sentence was taken as the payment day | event clauses are split at commas too |
| B | `Yes, the 13th instead of the 20th` / a yes repeating the superseded day re-checked the old day | the accepted alternative replaces it |
| C | **637.50 trace**: the extractor's span `six hundred and thirty-seven dollars` (cents missing) → 637 → below the 637.50 floor → "can't record", floor re-offered **on today** instead of the customer's Friday. Same for a cut turn (`...dollars and` + `fifty.` → 50) and `six hundred thirty-seven fifty` → 50 | amounts in integer cents with explicit statuses (ok / interpreted / ambiguous / incomplete); the whole amount is read around the extracted words in the (merged) message; a whole-dollar amount just under a known amount with cents is checked (`did you mean 637.50?`), never rejected; the floor counter-offer keeps the customer's day |
| C | `the minimum` → the **full amount** was read back and written; `that` after the minimum was stated → full amount | references resolve from the account facts: minimum/instalment → that product's floor, full → past due, that/it → the amount just stated or offered |
| C | refusing the floor after a below-floor proposal dropped the product (status stuck at refused) | it goes to the next persuasion attempt |
| D | `Okay.` after the minimum was explained accepted the pending full-amount offer | an acknowledgement of an explanation re-poses the question; counters do not move |
| D | floor named twice (live judge, logic from candidate 1): floor for today, then attempt 1 = floor on Friday | the one floor offer after "too much" at the today question carries attempt 1's day; a refusal moves to attempt 2 (A26) |
| E | `Yes for the card, not the loan` sent the card to attempt 1; amounts in shared proposals were ignored; a shared weekend day was moved silently | scoped yes accepts those products; amounts checked per product; the next business day is offered once for the group |
| F | a bare `Okay.` at the read-back (extractor said yes) wrote the promise | not a confirmation; the read-back is asked again |
| F | plain `No` at the read-back → `Which exact day would that be?`; `too much` at the read-back → the same read-back again | asks what to change / offers the floor with "the rest stays overdue" |
| F | goodbye at the read-back (B): agreed products got no note | noted `refused` (B8) |
| F | turn cap / repeat loop closed as `no_promise/refused` | closes as `service_error` (notes per product), never as the customer's refusal |
| G | identity non-answers shared one counter with the read-back: one `hang on` at the read-back then closed the call as refused | per-question counters |
| G | `It's the fourth of` / `May.` lost the month (`may` needed a number next to it) | `of May`, `in May`, a bare `May.` are the month |

Found live on candidate 2 (real extraction, real judge) and fixed in the next version:

| Version | Live evidence | Fix |
|---|---|---|
| v1 → v2 | PUB-06: `That full amount is too much` came back with `pay_amount: full amount` and was read as a proposal of the full amount (my reference resolution) | an amount inside a "too much" statement is a complaint, never a proposal; "too much" at the read-back gets the floor offer |
| v1 → v2 | PUB-06 in_words: floor offered for today, then again as attempt 1 on Friday; judge: "minimum offered twice" (same logic in candidate 1) | the one floor offer after "too much" carries attempt 1's day (A26: offer the floor once; only attempt 2 names it again) |
| v2 → v3 | PUB-11 pieces: `pay_amount: all three of them` was read as **3 dollars** (my per-product amount check) | product counts are scope, never amounts; a group day without an amount is each product's past due |
| v2 → v3 | PUB-12 talkative: small talk "calls **all day** and **haven't** had a moment" made a bare "all" name every product in a negative clause → all refused (bug present in candidate 1) | time idioms are not scope; a generic all/both names products only in a clause about paying or the products |
| v2 → v3 | PUB-13 talkative: "I can't pay that today" came back as `too_much` → floor attempt, then the group day kept the floor amount | a `too_much` with a negated day and no amount words is a refusal of today |
| v2 → v3 | PUB-12 asks_back: after "Why do you need that?" the security question was asked again; judge: "date of birth asked again" | a question back is answered without asking the security question again |
| v2 → v3 | PUB-12 pieces: the platform sandbox returned "did not return a parseable result" for one decide step (1 of 351 live steps; the same input replays to valid JSON locally) → honest technical ending | infrastructure; the workflow now runs a failed decide step once more (`decide_r`, same input, nothing was applied) |
| v3 → v4 | PUB-06 in_words: "How much is the minimum?" after the floor offer was answered and the floor offer made again; judge: "offered twice" (requirement D) | an amount question is answered from the account facts and the pending offer is not made again |

Checked and **not** changed (already correct on candidate 1): B6 clamping with the read-back note, create_promise
retry + `service_error` note, exactly one `close_call` as the last tool call, `recorded` only after `ok: true`,
weekend/holiday alternative (single product), explicit day number kept over a wrong weekday (asks), per-product
attempt counters, close-on-goodbye without returning to the negotiation.

**H — payload.** This candidate already zlib-compresses the runtime into the decide node (L16), so the
132,575-byte failure of the older uncompressed build does not occur. Measured: decide code ~36 KB after these fixes
(was ~30 KB); the worst case over a 60-turn three-product talkative call is ~42 KB of code + variables (limit
131,072); `rb_state` stays under 2 KB (events capped at 12, counters bounded). A test keeps it under half the limit.
**Workflow warnings:** the platform validator (`POST /api/v2/workflow?dryRun=true`) answers `valid: true` with no
warnings for both briefs; the stored workflow records carry no warning fields (only canvas layout); the builder lint
is clean. Nothing was merged for the canvas.

## Tests (offline)

```bash
python3 -m pytest -q tests        # 272 passed (170 from candidate 1 + 102 new)
```

- The public, speech-style and live-derived scripts also pass on the model-extracted policies
  (`submission/*.policy.json`, the lines the live agents speak): 32/32.
- Calendar matrix (`tests/test_generalization.py`): 8 `now` days (Fridays, holidays, year end, 2027) agree with the
  team's independently written date rules (`docs/team-notes/scripts/date_rules.py`) for attempt dates, deadlines and
  weekend/holiday alternatives; the self-tests and the core fixes also pass on the messy and raw2 brief shapes
  (renamed tool API, postcode/year/company-number identity, calendar-day deadlines).
- Live transcripts that failed are replayed as tests (`tests/test_walk_livelike.py`, `test_live_c2_*`).
- Builder self-tests (customers made up from the policy): 10/10 per brief.
- A randomized sweep (1,500 local calls, 1–3 products, mixed turns) found no exception and no rejected write.

## Live tests (Freya staging, real extraction and execution)

**Status at this commit (checkpoint, 11 Oct ~13:15 UTC): live validation in progress.** The candidate to freeze is **v5** (commit `9279ea0`, runtime `a6ca24d742b1`; A agent version 5, B agent version 4). v5 focused so far: B all six speech styles 17/18 (the one failure: the simulated talkative customer never gave the phone digits in ~15 turns), A in_words 5/5; the remaining A styles and the frozen 3x suites follow. Results of v1-v4 below do not validate v5 (each version changed the runtime); they are the evidence for the fixes. Every run below was
made with `tools/run_cases_retry.py` (the kit's runner, unmodified, plus GET retries), one simulation at a time in the
workspace; each failure was read in the call's own event log, not inferred.

Candidates (new slots; the frozen candidate-1 agents `rb-brief-a` v3 / `rb-brief-a-brief-b` v5 were never written to;
every publish is in `submission/candidate-2/deploys.jsonl`):

| Slot | Workflow | Agent | Versions published (commit) |
|---|---|---|---|
| `rb-c2-brief-a` | `eb8c91b8-ef17-4e43-ad6b-831096b299dd` | `8cd8c4c7-81b9-4517-b3b0-90a14d6d6358` | v1 `f453fba`, v2 `6e2bb85`, v3 `b11d5fc`, v4 `bdd6382` |
| `rb-c2-brief-a-brief-b` | `310fbf87-6c7c-4aef-bef3-fbc5709842e3` | `02348dd0-989b-4359-bdbe-7c925c22477f` | v1 `f453fba`, v2 `6e2bb85`, v3 `b11d5fc` |

Focused runs (affected cases A: PUB-04/05/06/07/10, B: PUB-11/12/13; plain and every speech style). Results files with
simulation, iteration and call ids are in `qa/live-results/`.

| Agent version | Runs | Result | Failures and evidence |
|---|---|---|---|
| v1 | A plain | 4/5 | PUB-06 agent ("full amount" read as a proposal) → v2 |
| v1 | A in_words (sim `79b38400`, poller lost to 504s; verdicts recovered) | 3 pass, 1 fail, 1 no verdict | PUB-06 agent (floor named twice) → v2; PUB-07 judge "analysis never arrived" (infrastructure) |
| v2 | A × 6 styles (sims `cb5fd15f` `920b0197` `b749999d` `03f4ef23` `9b8cf5b1` `11b604b7`) | **30/30** | — |
| v2 | B × 6 styles (sims `1e16f724` `a66ef1e1` `ffbdbd21` `28fe438d` `9398b0f7` `7c481ff1`) | 13/18 | pieces PUB-11 agent ($3) → v3; pieces PUB-12 **infrastructure** (sandbox "no parseable result"); talkative PUB-12 agent ("all day") → v3; talkative PUB-13 agent (too_much misread) → v3; asks_back PUB-12 judge conversation check (re-ask after an ask-back; its "3 attempts" claim contradicts the transcript) → v3 |
| v3 | A plain (sim `3d4d2982`) | **5/5** | — (880 s, see timing) |
| v3 | A in_words (sim `9efc2d7d`) | 2/5 | PUB-04, PUB-10 **infrastructure** (bank records passed; judge "analysis never arrived (300s)"); PUB-06 agent (floor offered again after "what is the minimum?") → v4 |
| v3 | B pieces (sim `d82d478f`) | pending | platform kept it "running" > 1 h with its detail route answering 504 |

Timing (`tools/sim_timing.py`, platform timestamps): the 880 s run was 526 s queued before the platform started any
call, 171 s of calls, 172 s judge analysis, 12 s polling; inside the calls the decide step took 0.4 s median (3.5 s max)
while the platform's extraction took 8.8 s median (43 s max) per turn, against 1.2 s in a normal run. No logic was
changed for latency.

Infrastructure seen (all on the platform side): practice bank unreachable from this network 09:07-09:12 UTC (TCP
timeouts to its Cloudflare edge, other hosts fine); Freya API 504 on every route ~09:40-10:08 UTC; partial 504s on
simulation detail routes from ~10:40 UTC; one sandbox parse failure in 351 decide steps; judge verdicts missing
("analysis never arrived") on 3 calls whose bank records passed.

## Remaining limitations

- **Live coverage is the 13 public practice cases** (plus speech styles). The hidden briefs and their customers
  cannot be tested before they arrive; behaviour on them rests on the offline tests and the builder self-tests.
- The fixes read the extractor's values in context, so they still depend on the extractor noticing a day or an
  amount at all; an utterance-level fallback only takes a day from a clause that says the customer will pay.
- A plain number for several products (`300 for both`) is read as each product's amount and shown in the read-back
  for confirmation; a total split across products is not inferred.
- After a below-floor proposal and a refusal of the floor, attempt 1 is the full amount (literal A30) unless the
  customer said the full amount was too much.
- A verified customer who asks to be called back still has no callback flow (neither public brief has one).
- `submission/messy-brief.*` and `submission/raw2-brief.*` are development exports from an older runtime.
- Platform latency varies (agent turns of 15–30 s were seen); the organisers' runner discards slow runs.

## Build, export and test

```bash
cp .env.example env.sh && $EDITOR env.sh && source env.sh          # never commit env.sh
python3 -m pytest -q tests                                       # offline, no credentials needed
python3 builder/build.py briefs/brief-a.md tools/openapi.json     # the official one-command build (extracts the policy
                                                                 # with Freya's model, self-tests, publishes rb-brief-a, exports)
# a candidate from an already extracted policy, published to a NEW slot (refuses the frozen candidate-1 slots):
python3 tools/deploy_candidate.py submission/brief-a.policy.json tools/openapi.json --slot rb-c2-brief-a [--update]
python3 tools/deploy_candidate.py submission/brief-a.policy.json tools/openapi.json --local-only   # no network
# live cases (one simulation at a time per workspace; waits for a running one; retries transient GET errors):
python3 tools/run_cases_retry.py <agent_id> --brief A [--only PUB-06] [--style in_words] --out results/x.json
python3 tools/summarize_runs.py results/r1.json results/r2.json results/r3.json   # per-case consistency
```

Exports of candidate 2 (what was tested live) are in `submission/candidate-2/` with a manifest each (slot, workflow
and agent ids, published version, source commit, runtime hash, export sha256). `submission/brief-a*.workflow.json`
are still the candidate-1 exports of the frozen agents below; replace them only by publishing (the export is what
is scored).

---

## Candidate 1 hand-off (unchanged, as written by the teammate)

### Hand-off to QA — frozen candidate 1 (11 Oct 2026, 07:35 UTC)

| | |
|---|---|
| Branch / commit | `rebuild/core` @ `d798445` (builder code identical to `f806122`, which built the agents) |
| `python3 -m qa.identity` | `builder b528d245355bc1cd`, `runtime bac97a98b178` (also in each build trace's START line) |
| Brief A agent | slot `rb-brief-a` · workflow `bc5fe0d0-0d34-4e9a-bcb2-62dab24d3cc7` · agent `edf86627-20cc-41ce-be0d-51115a31061e` · **published version 3** |
| Brief A+B agent | slot `rb-brief-a-brief-b` · workflow `e382d2c5-7a09-42a0-96d8-0d1d60579e08` · agent `2b88bb81-311c-4e81-8858-37c60ea2ded3` · **published version 5** |
| Built by | the official command, model extraction included: `traces/20261011T071113Z-rb-brief-a.txt`, `traces/20261011T071328Z-rb-brief-a-brief-b.txt` |
| Exported files | `submission/brief-a.workflow.json`, `submission/brief-a-brief-b.workflow.json` |

Nothing will be published to these two slots while QA tests. Development continues on other `rb-` slots only.

#### What was run on exactly these versions (single runs, not a claim)

- `rb-brief-a` v3: Brief A, style pieces: 10/10, lesson checks clean.
- `rb-brief-a-brief-b` v5: Brief B, styles asks_back and in_words: 3/3 each, lesson checks clean.
- Earlier versions of the same builder (same slots): Brief A plain 10/10, Brief B plain 3/3, B talkative / corrects /
  pieces 3/3 after the fixes now included.

#### Suggested QA order (from the rebuild plan)

```bash
source env.sh
python3 tools/run_cases.py edf86627-20cc-41ce-be0d-51115a31061e --brief A --only PUB-03,PUB-04,PUB-07 --out results/qa1.json
python3 tools/run_cases.py edf86627-20cc-41ce-be0d-51115a31061e --brief A --only PUB-09,PUB-01,PUB-02,PUB-05,PUB-06,PUB-08,PUB-10 --out results/qa2.json
python3 tools/run_cases.py edf86627-20cc-41ce-be0d-51115a31061e --brief A --reps 3 --out results/qa-a3.json
python3 tools/run_cases.py 2b88bb81-311c-4e81-8858-37c60ea2ded3 --brief B --reps 3 --out results/qa-b3.json
python3 -m qa.check_run results/qa-a3.json submission/brief-a.policy.json      # lesson checks on the calls
```

Styles worth a repetition each: `--style pieces`, `corrects`, `talkative`, `asks_back`, `in_words`.

#### Known limits

- Platform latency under load: the platform's extraction step sometimes takes 15–30 s (code steps 0.3–1 s).
  run_cases.py flags runs whose median slowest turn is above 10 s; organisers repeat those.
- A verified customer who asks to be called back later has no callback flow (neither public brief has one).
