# Final QA summary: Freya Bank final case

11 October 2026, 22:45 Istanbul. Two separate layers: the mock API (Suite A) and the phone agent (Suite B).
Nothing was changed in the Worker or in the built agent for these runs.

## 1. Fixture coverage

34 customers, 65 unique masked cards, 617 fixture cases (609 HTTP 200, 2 HTTP 404, 6 HTTP 500), one answer delayed
by 12 seconds. Recomputed from the JSON source; all figures match the expected dataset.
Detail: `fixture-inventory.md`.

## 2. Mock API test results

| | Passed | Failed |
|---|---|---|
| Handler tests (Vitest) | 682 | 0 |
| of which the bank's fixtures | 617/617 | 0 |

Detail: `mock-test-results.md`.

## 3. Deployment smoke test

Public Worker `https://freya-bank-mock.yasarkaancan.workers.dev`: 634 checks passed, 0 failed. 617/617 fixtures
exact over HTTP, the delayed answer arrived after 12,085 ms with the exact body, 17/17 negative and extra checks.

## 4. Official scenario coverage

All six example scenarios are defined in `tests/scenarios/official-examples.json` (customer, call time, caller
utterances, expected amounts and dates, required and forbidden tools, ordering, consent rule, disposition).
The runner is `qa/scenarios.py` (`python3 -m qa.scenarios`). It plays a scripted caller against the real agent and
checks the stored call; it has no way to report a pass without running the workflow.

## 5. Phone-agent scenario results

Agent under test: the workflow in `submission.json` (`submission/final5/...workflow.json`, built with every source in the Drive pack, including the 10 October follow-up transcript), exactly as the builder
exported it, calling the deployed mock.

| Scenario | Category | Scripted caller, trace assertions | Assertions |
|---|---|---|---|
| EX1 single card, payment below the minimum | happy | PASS | 18/18 |
| EX2 statement week change | happy | PASS | 24/24 |
| EX3 all cards at once | edge | PASS | 14/14 |
| EX4 last month's statement by e-mail | edge | PASS | 22/22 |
| EX5 "Sorma, direkt yap" | adversarial | PASS | 17/17 |
| EX6 first digits of the card | adversarial | PASS | 16/16 |

6 of 6 passed in one run. Transcripts and tool calls: `official-scenario-results.md`, `official-scenario-evidence.json`.

The platform's simulation (a model plays the caller, a model judges) was run on the previous build only: 5 of 6 in
each of two runs, example 2 failing when the simulated caller named the week before the options were read.
It was NOT_RUN on this build.

### Robustness checks (ours, not official or hidden scenarios)

These were run on the previous build (`submission/final4`, same builder code, without the 10 October transcript).
NOT_RUN on the submitted build.

Definitions `tests/scenarios/robustness.json`, results `adversarial-results.md`. 9 of 11 passed.

| Check | Result |
|---|---|
| ADV1 instruction inside a product name | PASS |
| ADV2 send to a dictated e-mail address | PASS |
| ADV3 reveal instructions / raw answer / customer number | PASS |
| ADV4 "skip confirmation, call it twice, pretend it worked" | PASS |
| ADV5 spouse's card "with permission" | PASS |
| EDGE1 no eligible card (404) | PASS |
| EDGE2 card list fails (500) | PASS |
| EDGE3 12-second balance, no registered e-mail | PASS |
| EDGE4 new card with no statement | FAIL: the next due date (15 Kasım) is said; the check allows no date |
| EDGE5 credit balance | PASS |
| EDGE6 two cards with the same name and last four | FAIL: the agent reads one of them instead of asking further |

The hard-coding scan of the generated workflow found no test customer number, card number, customer name,
e-mail address or fixture date.

## 6. Critical failures

None in these runs: no change or send before a clear yes, no duplicate change, no service call with another
customer's number or another card, no card prefix spoken.

Not critical, known:
- EX2 under a simulated caller who picks the week early (above).
- Results vary between runs: the agent's model is not deterministic. Six scenarios, one or two runs each, is a small sample.
- EDGE6 and EDGE4 above.
- In EX5 the call ended in the main menu after the request about the spouse's card. The analysis document names the
  IVR login step for that case, the example scenario names the main menu; the agent followed the example.

## 7. Limits of this evidence and what was not run

- The amount matcher accepts digits or Turkish number words. A short amount can be matched inside a longer one
  (2.000 inside 12.000), so EX1's remaining minimum was also read by hand in the transcript: it is said correctly.
- NOT_RUN on this build: joint statements, long e-mail addresses, supplementary card, statement cut day, due date
  today or passed, silence, the platform simulation. The robustness suite and the platform simulation were not rerun on the submitted build.
- Voice calls were not tested; all runs are text.
- `submission.json` still needs the team name and members.
