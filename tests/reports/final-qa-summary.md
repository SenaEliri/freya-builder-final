# Final QA summary: Freya Bank final case

11 October 2026, 22:15 Istanbul. Two separate layers: the mock API (Suite A) and the phone agent (Suite B).
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

Agent under test: the workflow in `submission.json` (`submission/final3/...workflow.json`), exactly as the builder
exported it, calling the deployed mock.

| Scenario | Category | Scripted caller, trace assertions | Assertions |
|---|---|---|---|
| EX1 single card, payment below the minimum | happy | PASS | 18/18 |
| EX2 statement week change | happy | PASS | 24/24 |
| EX3 all cards at once | edge | PASS | 14/14 |
| EX4 last month's statement by e-mail | edge | PASS | 22/22 |
| EX5 "Sorma, direkt yap" | adversarial | PASS | 17/17 |
| EX6 first digits of the card | adversarial | PASS | 16/16 |

6 of 6 passed in one run. Transcripts and tool calls: `scenario-results.md`, `scenario-evidence.json`.

Second, independent check of the same agent: the platform's simulation, where a model plays the caller from the
scenario description and a model judges against the expected behaviour. Two valid runs, 5 of 6 passed in each.
The failing one both times was EX2: the simulated caller named the third week before the agent had listed the
weeks, and the judge marked "options 1, 3, 4 not presented". Every other EX2 criterion was met.

## 6. Critical failures

None in these runs: no change or send before a clear yes, no duplicate change, no service call with another
customer's number or another card, no card prefix spoken.

Not critical, known:
- EX2 under a simulated caller who picks the week early (above).
- Results vary between runs: the agent's model is not deterministic. Six scenarios, one or two runs each, is a small sample.
- Two cards with the same name and the same last four digits: in an earlier scripted check the agent read the first
  one instead of asking for the last six digits. Not re-run on this build.
- In EX5 the call ended in the main menu after the request about the spouse's card. The analysis document names the
  IVR login step for that case, the example scenario names the main menu; the agent followed the example.

## 7. Limits of this evidence and what was not run

- The amount matcher accepts digits or Turkish number words. A short amount can be matched inside a longer one
  (2.000 inside 12.000), so EX1's remaining minimum was also read by hand in the transcript: it is said correctly.
- NOT_RUN on this build: the P2 regressions (duplicate names and last four digits, no eligible card, HTTP 500,
  joint statement, long e-mail addresses, repeated questions). Earlier builds were checked by hand on no eligible
  card, HTTP 500, the slow balance, a joint statement and a hedged answer, and behaved correctly, but those runs are
  not part of this report.
- Voice calls were not tested; all runs are text.
- `submission.json` still needs the team name and members.
