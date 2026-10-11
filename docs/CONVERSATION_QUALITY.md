# Conversation quality review (experimental candidates c3 / c3.1)

**Recommended baseline for submission: v5** — tag `baseline-v5-validated` (`969ecad`), runtime commit `9279ea0`,
agents `rb-c2-brief-a` v5 / `rb-c2-brief-a-brief-b` v4, exports `submission/candidate-2/`, validation
`docs/VALIDATION.md`. Nothing below changes it. **c3 is experimental** (branch `experiment/conversation-quality`, new
slots `rb-c3-brief-a` / `rb-c3-brief-a-brief-b`); v5's passing results do not validate c3. The current experimental
build is **c3.1** (commit `1d9e0b6`, runtime `b04f7c198ec9`): c3 (`08fc779`) plus tighter parser rules after the
counterexample check in section 3b; results for c3 do not validate c3.1 either.

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

## 3. Changes (c3 `08fc779`, tightened in c3.1 `1d9e0b6`)

Three are **wording** changes (1, 3, 5: what the agent says on a path it already took). Two are **behavioural parser
changes** (2, 4: they change which value the agent reads from the customer's words, and so which path it takes).

| # | Before | After | Why |
|---|---|---|---|
| 1 | "Sorry, I didn't catch that. Could you tell me your date of birth again?" (after a failed verify call) | "Sorry, I could not check that just now. Could you tell me your date of birth again, please?" | the service failed, not the customer; the retry itself is unchanged and still never counts as a wrong answer |
| 2 (parser) | wedding's "thirtieth" taken as the birth day -> wrong answer | clauses about another event are dropped before the date of birth is read; a clause about the customer's own birth ("my birthday is", "born", "date of birth") is always kept | a correct answer must not use up one of three attempts |
| 3 | "Thank you and goodbye." | "I'm not able to offer a discount. Thank you and goodbye." | answer the immediate question; A33 (no discount is offered) is kept |
| 4 (parser) | "...Which exact day would that be?" | "...The latest date I can record is Friday 23 October. Can you pay by then?" | the date was said; "because"/"since" now end a negated part, but only when what follows links the day to income or paying |
| 5 | "Which exact day would that be?" | "I have October. Which day in October do you mean?" | one focused clarification that uses what the customer already said |

### 3b. Counterexamples for the two parser changes

`tests/test_conversation_quality.py` (through `read_inputs` -> `read_date`, and the date-of-birth reader); "proposal"
means the agent takes the day as the customer's own payment day (it still needs the read-back and a clear yes).

| Customer says (extracted day) | Should be | Baseline v5 | c3 | c3.1 |
|---|---|---|---|---|
| I cannot pay today because my salary arrives on the sixth of November and I can pay then. | proposal | no | yes | yes |
| I cannot pay today since my salary arrives on the 30th. | proposal | no | yes | yes |
| I can't pay today, but since my salary comes on the 20th I can pay then. | proposal | yes | yes | yes |
| Since I get paid on the 20th, I can pay on the 20th. | proposal | yes | yes | yes |
| I cannot pay **since the bank is closed** on the 30th. | not a proposal | correct | **wrong** | correct |
| I can't pay **because the 30th is when my rent is due**. | not a proposal | correct | **wrong** | correct |
| I can't pay on Friday because my rent is due then. | not a proposal | correct | correct | correct |
| Because of the holiday I can't pay on Monday. | not a proposal | correct | correct | correct |
| I can't pay because I'm on holiday until the 30th. | not a proposal | **wrong** | correct | correct |
| I won't be able to pay **since I'm travelling** on the 20th. | not a proposal | correct | **wrong** | correct |
| I cannot pay today because my cousin's wedding is on the 30th. | not a proposal | correct | correct | correct |
| DOB: My birthday is the 3rd of June **and I was born in 1987**. | 1987-06-03 | correct | **wrong** (no date) | correct |
| DOB: ...cousin's wedding ... on the thirtieth. My date of birth is nine September nineteen ninety. | 1990-09-09 | **wrong** (30th) | correct | correct |
| DOB: The 17th of May 1986, my sister's birthday party was on the 30th. | 1986-05-17 | **wrong** (30th) | **wrong** | correct |
| 4 more date-of-birth answers (own birthday, born on a holiday, wedding first, plain) | as said | correct | correct | correct |
| **Total (18)** | | 13/18 | 13/18 | **18/18** |

c3 fixed four baseline errors but introduced four regressions; c3.1 removes them. These are the cases checked, not
proof for every phrasing.

Unchanged: verification and its limits, attempt limits, calendar rules, outcome mappings, tool order, the
confirmation/write guards, every line the brief requires. No turn or model call was added. New sentences are runtime
defaults (`id_tech`, `no_discount`, `ask_day_in_month`) that a policy line with the same key overrides.

## 4. Validation

- Offline (c3.1): 297 tests pass; `tests/test_conversation_quality.py` holds the 5 v5 transcripts (all 5 fail on the
  baseline) and the 18 counterexamples of section 3b; the public, speech-style and live-derived scripts on the
  extracted policies 33/33; builder self-tests 10/10 per brief.

### c3 (`08fc779`) — superseded by c3.1; kept for the record

- Live (Freya staging, c3 agents `25183cdb-43aa-4c5e-b427-a0680b1ca71e` (A) / `d07c16c4-e607-4356-b53a-aaffc9c87523`
  (B), commit `08fc779`, exports `submission/candidate-3/`; one simulation at a time; raw outputs `qa/live-results/c3/`):

| Run (simulation) | Result | Failures (from each call's log) |
|---|---|---|
| A plain, PUB-04/05/06/07/10 (`3e50e5b6`) | 5/5 | — |
| A in_words (`dc68d656`) | 4/5 | PUB-10 infrastructure: the first `create_promise` got no answer within the workflow's 12 s tool timeout (unchanged since candidate 1); the agent retried once (A37), the retry met the case's scripted failure, the agent said it could not record and closed `service_error`; the bank's ledger shows the delayed first request arriving after `close_call` |
| A talkative (`75f0d84a`) | 4/5 | PUB-06 test harness: the platform retried the run (`attempts: 1`) on the same practice customer after a first attempt had already verified it and read the account; the bank answers a repeated verification without `all_verified`, so the retried conversation could not finish identity |
| B plain (`60006137`) | **inconclusive** (0/3 ran) | infrastructure: all three never left the opening node; customer hung up at 62 s |
| B pieces (`09e3b769`) | **inconclusive** (0/3 ran) | infrastructure: same; the chat API also answered 504 for the A and B c3 workflows at 15:20-15:22 UTC |

Why the B stalls are infrastructure, not a c3 opening defect (raw call events): in a normal call the first event after
the customer's first reply is `variable_extracted` on the `open` node (~0.6 s), then `route_evaluated open -> decide`
(transition `always`), then the decide code step. In every stalled call (c3 B `2a35bf8d`, and the validated v5 suite
call `996fbc9e`) there is **no event at all** after the reply: the platform's extraction on the opening node never
returned, so the opening transition was never evaluated and no c3 code ran. The c3/c3.1 opening is byte-identical to
v5's (initial node, `open` node with its transition, extraction schema, spoken opening and task message, system prompt,
agent config); the only workflow difference anywhere is the decide code, which these calls never reached.

- c3 live: A 13/15 (2 infrastructure / harness), B inconclusive. The discount answer appeared in all three A runs.

### c3.1 (`1d9e0b6`, runtime `b04f7c198ec9`; agents `rb-c3-brief-a` v2, `rb-c3-brief-a-brief-b` v2; exports `submission/candidate-3/`)

| Run (simulation) | Result |
|---|---|
| A plain, PUB-04/05/06/07/10 (`1c077687`) | 5/5 |
| B plain, PUB-11/12/13 (`6f4a75f7`) — the retry of the inconclusive B check | 3/3 |
| B pieces, PUB-11/12/13 (`10de0437`) | 3/3 |

- **11/11 calls passed** (bank records and the judge's conversation checks); raw outputs `qa/live-results/c3.1/`.
- In these simulations only change 3 occurred (PUB-05 "Can I get a discount since I can't pay anything right now?"
  -> "I'm not able to offer a discount. Thank you and goodbye.", passed). Changes 1, 2, 4 and 5 did not occur in them
  (no service failure, no event mentioned during identity, no "because my salary..." sentence, no month-only answer).
- **Later chat checks** (`docs/SENTIMENT_COMPARISON.md`, branch `experiment/conversation-quality`): one chat per
  version per scenario through the chat API, scripted customer, no judge, extraction model of chat calls unverified.
  These are supplementary diagnostics, not official simulation passes. Changes **3, 4 and 5** occurred, with bank
  records identical to v5's. **Change 2 did not differentiate** the candidates (v5 also read that date of birth
  correctly). **Change 1 remained unexercised.**
- Single runs of 8 of the 13 public cases, plain and pieces only. The baseline has three frozen runs of all 13 cases
  plus every speech style; c3.1 has neither.

## 5. Recommendation

**c3.1 does not yet have sufficient evidence to replace the baseline. Submit the validated baseline v5** (tag
`baseline-v5-validated`, `submission/candidate-2/`). c3.1 passed every targeted live check (11/11) and all offline
checks, but it has single runs on 8 of 13 cases, two of its five changes are behavioural parser changes, change 1
was never exercised, change 2 did not differentiate the candidates live, and changes 4 and 5 were seen only in single
supplementary chat checks, not in official simulations. Before c3.1 could replace v5 it needs the same evidence v5 has — three frozen runs
of the full A and B suites (and ideally the speech styles):

```bash
# three times each, nothing published in between (c3.1 = rb-c3-brief-a v2 / rb-c3-brief-a-brief-b v2)
python3 tools/run_cases_retry.py 25183cdb-43aa-4c5e-b427-a0680b1ca71e --brief A --out results/c31-suiteA-r1.json
python3 tools/run_cases_retry.py d07c16c4-e607-4356-b53a-aaffc9c87523 --brief B --out results/c31-suiteB-r1.json
```
