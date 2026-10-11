# Conversation quality review (experimental candidate c3)

**Recommended baseline for submission: v5** — tag `baseline-v5-validated` (`969ecad`), runtime commit `9279ea0`,
agents `rb-c2-brief-a` v5 / `rb-c2-brief-a-brief-b` v4, exports `submission/candidate-2/`, validation
`docs/VALIDATION.md`. Nothing below changes it. **c3 is experimental** (branch `experiment/conversation-quality`, new
slots `rb-c3-brief-a` / `rb-c3-brief-a-brief-b`); v5's passing results do not validate c3.

## 1. The grey "No sentiment" category: missing analysis, not dissatisfaction

| Agent (11 Oct, analytics API, `sentimentDistribution`) | Calls | With a sentiment | Without (grey) |
|---|---|---|---|
| candidate 2 A `8cd8c4c7` | 115 | 5 (all neutral) | 110 |
| candidate 2 B `02348dd0` | 54 | 5 (all neutral) | 49 |
| whole workspace | 972 | 278 | 694 |

- Sentiment is a system **call tag** (`{"tag": "sentiment", "value": 0}` = neutral) written by the post-call analysis.
- All 39 frozen-suite calls are `simulationCall`s with **no sentiment tag**; their `analysis` holds only the judge's
  `successEvaluation` (no summary either). The 5 tagged calls per agent are exactly the chat smoke tests (`webCall`,
  closed through `/chat/end`, which runs the post-call analysis), each tagged neutral with a summary.
- So the grey bucket is "never analysed for sentiment", not "pending" (the calls are hours old; web calls were tagged
  within minutes) and not a customer reaction. Whether the platform skips sentiment for simulations on purpose is
  unknown; the mechanism above is verified from the data.

## 2. Transcript review (87 v5 calls: 39 frozen-suite + 48 focused)

Scanned for every friction type in the request, then read the calls. Material problems found (each seen live):

| # | Where | What happened |
|---|---|---|
| 1 | focusA-talkative PUB-05, sim `3353180f` | `verify_identity` failed (bank answered with HTML error pages) four times; each time the agent said "Sorry, **I didn't catch that**. Could you tell me your date of birth again?" The customer had said it correctly: "I'm getting a bit tired of repeating myself", "It's really frustrating when technology doesn't work". |
| 2 | same call | "...like my cousin's wedding coming up on **the thirtieth**. My date of birth is nine September nineteen ninety." was read as 30 September 1990 and **counted as a wrong answer** ("That does not match our records"). |
| 3 | suite A r1 and r2 PUB-05, sims `e182971c`, `708ce9df` | "No, I do not want to be transferred. **Can I get a discount?**" -> "Thank you and goodbye." The question was dropped. |
| 4 | focusA-in_words PUB-04, sim `595fb674` | "I cannot pay today **because** my salary arrives on the sixth of November and I can pay then. Am I talking to a robot?" -> "I am Freya Bank's digital assistant. **Which exact day would that be?**" — the negation of "today" was applied to the November date; the customer had to say it again. |
| 5 | B pieces PUB-13, sim `d82d478f` (same code path in v5) | "October for both of them." -> "Which exact day would that be?" — generic, not building on the month already given. |

Checked and **not** changed: product transitions ("For your personal loan: could you pay ...?" names the product);
the third party asking what the call is about (Brief A rule 5: say nothing beyond the opening, ask when reachable);
the wait prompts after cut turns; hardship wording (one sentence of sympathy, support offered once); offers after
information answers (fixed in v4, none repeated in v5); no agent message over 330 characters.

## 3. Changes (c3, commit `08fc779`; wording and reading only)

| # | Before | After | Why |
|---|---|---|---|
| 1 | "Sorry, I didn't catch that. Could you tell me your date of birth again?" (after a failed verify call) | "Sorry, I could not check that just now. Could you tell me your date of birth again, please?" | the service failed, not the customer; the retry itself is unchanged and still never counts as a wrong answer |
| 2 | wedding's "thirtieth" taken as the birth day -> wrong answer | the part after "my date of birth is" is read; clauses about another event are ignored | a correct answer must not use up one of three attempts |
| 3 | "Thank you and goodbye." | "I'm not able to offer a discount. Thank you and goodbye." | answer the immediate question; A33 (no discount is offered) is kept |
| 4 | "...Which exact day would that be?" | "...The latest date I can record is Friday 23 October. Can you pay by then?" | the date was said; "because"/"since" now end the clause a negation applies to |
| 5 | "Which exact day would that be?" | "I have October. Which day in October do you mean?" | one focused clarification that uses what the customer already said |

Unchanged: verification and its limits, attempt limits, calendar rules, outcome mappings, tool order, the
confirmation/write guards, every line the brief requires. No turn or model call was added. New sentences are runtime
defaults (`id_tech`, `no_discount`, `ask_day_in_month`) that a policy line with the same key overrides.

## 4. Validation

- Offline: 279 tests pass (5 new in `tests/test_conversation_quality.py`, each a v5 live transcript; all 5 fail on the
  baseline); the public, speech-style and live-derived scripts on the extracted policies 33/33; builder self-tests
  10/10 per brief.

- Live (Freya staging, c3 agents `25183cdb-43aa-4c5e-b427-a0680b1ca71e` (A) / `d07c16c4-e607-4356-b53a-aaffc9c87523`
  (B), commit `08fc779`, exports `submission/candidate-3/`; one simulation at a time; raw outputs `qa/live-results/c3/`):

| Run (simulation) | Result | Failures (from each call's log) |
|---|---|---|
| A plain, PUB-04/05/06/07/10 (`3e50e5b6`) | 5/5 | — |
| A in_words (`dc68d656`) | 4/5 | PUB-10 infrastructure: the first `create_promise` got no answer within the workflow's 12 s tool timeout (unchanged since candidate 1); the agent retried once (A37), the retry met the case's scripted failure, the agent said it could not record and closed `service_error`; the bank's ledger shows the delayed first request arriving after `close_call` |
| A talkative (`75f0d84a`) | 4/5 | PUB-06 test harness: the platform retried the run (`attempts: 1`) on the same practice customer after a first attempt had already verified it and read the account; the bank answers a repeated verification without `all_verified`, so the retried conversation could not finish identity |
| B plain (`60006137`) | 0/3 | infrastructure: all three never left the opening node; customer hung up at 62 s |
| B pieces (`09e3b769`) | 0/3 | infrastructure: same; the chat API also answered 504 for the A and B c3 workflows at 15:20-15:22 UTC |

- The changed wording seen live: "I'm not able to offer a discount. Thank you and goodbye." (PUB-05 in all three A runs,
  each passed). Not reached live (no service failure, no month-only answer happened): changes 1 and 5 are covered by
  the local tests only. "Sorry, I didn't catch that." now appears only after real non-answers (A talkative PUB-06).
- **No regression found; Brief B is not verified live for c3** (6 of 6 B calls voided by the platform).

## 5. Recommendation

**Submit the validated baseline v5** (tag `baseline-v5-validated`, `submission/candidate-2/`). c3 is a sound, small
improvement with offline coverage and partial live evidence on Brief A, but Brief B could not be checked live and v5's
results do not carry over to it. If the team wants c3, it needs one clean live pass of the A and B suites first:

```bash
python3 tools/run_cases_retry.py 25183cdb-43aa-4c5e-b427-a0680b1ca71e --brief A --out results/c3-suiteA.json
python3 tools/run_cases_retry.py d07c16c4-e607-4356-b53a-aaffc9c87523 --brief B --out results/c3-suiteB.json
```
