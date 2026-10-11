# Sentiment comparison: v5 baseline vs experimental c3.1 (chat API, platform post-call analysis)

**Submission baseline is unchanged: v5** (tag `baseline-v5-validated`, `docs/VALIDATION.md`). This is one chat per
version per scenario with a scripted customer. It is a conversation-quality probe, not a validation, and it does not
promote c3.1 (see `docs/CONVERSATION_QUALITY.md` section 5).

**Status: limited, supplementary diagnostic.** These are chat-API calls with a scripted customer and no judge. Their
bank-ledger checks and sentiment labels are **not official simulation passes**: official scoring reads the bank
records, then a judge checks policy and honesty, three runs per customer, and sentiment is not part of it (kit README).
Evidence on the review's concerns (calls and workflows re-read, nothing new run; details in `docs/HIDDEN_BRIEFS_READINESS.md` on `main`):

| Concern | Finding | Kind |
|---|---|---|
| Chat skips a first code step | Does not apply: the workflows start at a conversation node (`open`, no pre-actions). In all ten calls 6–8 `code_exec` steps completed `success`, with 0 errors, and the bank tools ran | documented limitation (kit `docs/api.md`); observed not to occur |
| Chat uses another model than simulations | Dialogue: the published `llmConfig` = `experimental-5`, the required model. Routing: every transition is `exact`, so no model is involved. Extraction: the chat API takes no override, the config field is `null`, and the call record names no model, so **unverified** | partly observed, partly unverified |
| Scripted driver breaks on new wording | Answered coherently in all ten calls: every line answers the agent's question, and the "Okay." fallback was never used. It is a keyword script that knew both versions' wording in advance, so it cannot surface unexpected wording | observed; limitation by design |
| Sentiment vs scoring | Separate: sentiment is not in the official scoring | documented |

## Result in one table

| Scenario (public case) | c3.1 change it exercises | v5 sentiment | c3.1 sentiment | Bank check v5 / c3.1 | What differs in the transcript |
|---|---|---|---|---|---|
| S1 hardship + discount question (PUB-05) | 3: answer the discount question | **−1** (conf. 1) | **−0.5** (conf. 0.9) | pass / pass | v5 ignores "Can I get a discount?"; c3.1 says it cannot offer one |
| S2 "cannot pay today because my salary…" (PUB-04) | 4: because-clause parser | 0.5 (0.9) | 0.5 (1) | pass / pass | v5 asks "Which exact day would that be?" after the day was given; c3.1 goes straight to the deadline (one exchange fewer) |
| S3 event date before the date of birth (PUB-01) | 2: date-of-birth parser | 1 (1) | 1 (1) | pass / pass | none: identical; v5 also read this date of birth correctly |
| S4 month without a day, two products (PUB-13) | 5: month-only clarification | 0.5 (1) | 0.5 (1) | pass / pass | "Which exact day would that be?" vs "I have October. Which day in October do you mean?" |
| S5 control: shared day, three products (PUB-11) | none | 1 (1) | 1 (1) | pass / pass | none: identical |

- **Sentiment measured for 10 of 10 calls; unavailable for 0.** An unavailable value would have been reported as
  "unavailable", never as a pass or a failure. Every value is the platform's own tag
  (`{"tag": "sentiment", "source": "system"}`), read back from the call. None was assigned here. Values seen: −1, −0.5,
  0.5, 1 (the earlier smoke tests showed 0 = neutral). Re-read at 16:35 UTC: unchanged.
- **Bank: 10/10 ledgers pass** (a diagnostic check, not an official pass) the kit's scorer (`tools/score.py`: outcome and reason, each promise's product, amount
  and date, notes, callbacks, transfers, `close_call` last, no account tool before verification). Re-read from the
  practice bank after the run: identical to what the run recorded. Every tool call returned ok.
- **Sentiment differs only in S1.** In S2 and S4 it is the same although c3.1's wording is shorter or more focused.
  The analyser did not register the redundant v5 question in S2.

## The two negative calls (S1, PUB-05)

| | v5 | c3.1 |
|---|---|---|
| Call | `ff501c42-98aa-4ebe-8666-51c1f1a8d34d` | `d235dcfa-4ee4-4db7-b7e4-2efe0f491ec4` |
| Agent / workflow / version | `8cd8c4c7` / `eb8c91b8` / 5 (`rb-c2-brief-a`) | `25183cdb` / `7fd77242` / 2 (`rb-c3-brief-a`) |
| Time (UTC; UTC+3 in brackets) | 16:18:34–16:18:57 (19:18) | 16:19:33–16:20:04 (19:19–19:20) |
| Sentiment | −1, confidence 1 | −0.5, confidence 0.9 |
| Bank | `no_promise` / `hardship`; no promise, note, callback or transfer; tools `verify_identity` ×2, `get_account`, `close_call` | same |

In a UTC+3 hourly view all ten comparison calls fall in the 19:00 bucket, and these two are the only negative ones.
The analytics bucket itself was not queried, so it is not proven that it holds no other negative call (suite
simulation calls are never sentiment-tagged, `docs/CONVERSATION_QUALITY.md` section 1).

Both calls are identical up to the last agent line:

| Customer | v5 | c3.1 |
|---|---|---|
| Okay, what is this about? | I am calling from the collections team about a late payment. Your personal loan has 780 dollars past due, 21 days late. Can you make this payment today? | same |
| **I lost my job last month and I cannot pay anything.** | I am sorry to hear that. Would you like me to connect you with the customer support team? | same |
| **No, I do not want to be transferred. Can I get a discount?** | Thank you and goodbye. | I'm not able to offer a discount. Thank you and goodbye. |

The platform's summaries:

- v5: "When he declined a transfer to customer support and asked for a discount, the assistant **abruptly ended the
  call**."
- c3.1: "He declined an offer to be transferred to customer support and asked for a discount, which the assistant
  could not provide, leading to the end of the call."

**Cause.**
- **Both calls are negative because of what the customer says.** The scripted PUB-05 customer has lost his job,
  cannot pay anything, refuses the support team and asks for a discount he cannot get.
- **The agent did what the brief requires** in both calls. Both gave one sentence of sympathy, made no persuasion
  attempt, offered support once, offered no discount, and closed `no_promise/hardship`. The case's checks and the bank
  record pass for both.
- **The extra −0.5 for v5 is best explained by the unanswered question.** v5 answered "Can I get a discount?" with
  only a goodbye, and the analyser's summary calls that ending abrupt. c3.1 answers the question (change 3) and is
  tagged −0.5. This rests on one call per version and on the summary's wording. The platform gives no other reason,
  and its run-to-run variation is unknown.
- **The "customer" is the tool's fixed script, not a person.** The tag is the analyser's reading of a hardship
  conversation, not a measured customer reaction.

The 0.5 calls (S2, S4, both versions) are positive, not negative. In both, the customer's own date was not recorded
as said: S2 moved from 6 November to the 23 October deadline, and in S4 the loan moved from 30 to 23 October. Each
summary mentions the counter-offer. That this is why they score 0.5 rather than 1 is an inference.

## Transcripts that differ (from the call logs)

Identity steps, opening and closing lines are identical between the versions in every scenario. Full transcripts of
all ten calls: `qa/chat-compare/call-records.json`.

**S2 (PUB-04, car loan 1,250 dollars, 14 days late)**

| Customer | v5 | c3.1 |
|---|---|---|
| I cannot pay today because my salary arrives on the sixth of November and I can pay then. | Which exact day would that be? | The latest date I can record is Friday 23 October. Can you pay by then? |
| The sixth of November. *(v5 only)* | The latest date I can record is Friday 23 October. Can you pay by then? | — |
| Yes, that works. | So that is 1,250 dollars for your car loan on Friday 23 October. Do you confirm? | same |
| Yes, I confirm. | Your promise of 1,250 dollars for your car loan on Friday 23 October is recorded. You will receive a text message confirming this promise. Thank you and goodbye. | same |

**S4 (PUB-13, card 300 dollars, 4 days late; personal loan 900 dollars, 20 days late)**

| Customer | v5 | c3.1 |
|---|---|---|
| Not today. I want to pay both of them in October. | Which exact day would that be? | I have October. Which day in October do you mean? |
| The thirtieth. | So that is 300 dollars for your credit card ending 6604 on Friday 30 October and 900 dollars for your personal loan on Friday 23 October, the latest date I can record for it. Do you confirm? | same |
| Yes, I confirm. | Two "Your promise … is recorded." lines, then the text-message sentence and goodbye | same |

**S3 and S5:** word-for-word identical between the versions. In S3 the customer says "My cousin's wedding is coming
up on the thirtieth, so I am a bit distracted. My date of birth is the fourteenth of March nineteen eighty-eight." Both
versions verify on the first answer. So this run did not reproduce the v5 misreading seen earlier (with "nine
September nineteen ninety"), and change 2 is still not differentiated live.

## How it was run

| | |
|---|---|
| Tool | `tools/chat_compare.py` (commit `6cb0d02`), one run, 11 Oct 2026 16:18–16:29 UTC; calls alternate v5, c3.1 per scenario |
| v5 | A: `rb-c2-brief-a` v5, agent `8cd8c4c7-81b9-4517-b3b0-90a14d6d6358`; B: `rb-c2-brief-a-brief-b` v4, agent `02348dd0-989b-4359-bdbe-7c925c22477f` |
| c3.1 | A: `rb-c3-brief-a` v2, agent `25183cdb-43aa-4c5e-b427-a0680b1ca71e`; B: `rb-c3-brief-a-brief-b` v2, agent `d07c16c4-e607-4356-b53a-aaffc9c87523` |
| Versions | confirmed from each call record (`entityVersionNumber`) |
| Customer | deterministic responder with fixed lines per scenario, so both versions hear the same words; a fresh practice customer of the named case per chat (practice clock 14 Oct 2026, 11:00) |
| Channel | chat API (`webCall`), each closed with `/chat/end`, which runs the post-call analysis; every call ended `assistant-ended-call` (19–35 s) |
| Analysis | each call record was updated with its tags 10–14 s after the chat ended. `waited_s: 600` in `run.json` is the configured upper limit; all ten tags were present at the first poll |

**Gateway timeouts.** In each chat one turn got HTTP 504 from `POST /api/v2/chat/message`. The tool never resends a
turn: it waited 20 s and read the agent's reply from the call log. That turn was the final one, which closes the
call. A 504 on any earlier turn would have left a gap of at least 20 s before the next customer line. The call logs
show none: customer lines are 2–14 s apart, and the calls last 19–35 s. In S2–S5
the tool kept only that turn's last line (the goodbye), so `run.json` omits the "Your promise … is recorded." lines.
The call logs have them, and `call-records.json` holds the complete transcripts. Every customer line was delivered
exactly once. The platform's analysis reads its own complete call log, so the omission does not affect the sentiment.

## What this shows and what it does not

- **Shows:** c3.1 changed the conversation only where intended: changes 3, 4 and 5 appeared in live chats (4 and 5
  for the first time live). Its bank records are identical to v5's in all five scenarios. The platform sentiment was
  the same in four scenarios and less negative in the hardship scenario.
- **Does not show:**
  - a reliable sentiment difference: one call each, a model-based analyser, a scripted customer;
  - anything about change 1 (no verification-service failure occurred);
  - anything about change 2 (S3 did not differentiate);
  - anything about the 13-case suites, the speech styles or the hidden briefs.
- **Recommendation unchanged:** submit v5. Promoting c3.1 still needs three frozen runs of the full A and B suites
  (`docs/CONVERSATION_QUALITY.md` section 5).

## Files

- `qa/chat-compare/run.json`: the tool's output. The practice-bank customer handles (`customer_id`) are removed;
  nothing else is changed.
- `qa/chat-compare/call-records.json`: a read-only re-read of the ten calls (16:35 UTC). It holds agent, workflow,
  version, times, the sentiment tag, the summary, the complete transcript and the re-scored bank ledger. Phone
  numbers, recording URLs, cost and engine events are left out. Names, dates of birth and phone digits in the
  transcripts are the fictional public practice cases (`public-test-set.json`).
