# Mock API test results (Suite A)

Run on 11 October 2026, about 22:09 Istanbul. The Worker was not changed for this run.

| Run | Command (from `mock/`) | Result |
|---|---|---|
| Handler tests | `npx vitest run` | 682 passed, 0 failed |
| Fixtures in the handler tests | part of the above | 617/617: status, deep equality and key order |
| Public Worker replay | `node scripts/replay.mjs https://freya-bank-mock.yasarkaancan.workers.dev` | 634 passed, 0 failed |
| Fixtures on the public Worker | part of the replay | 617/617 exact (200: 609, 404: 2, 500: 6) |
| Delayed fixture on the public Worker | part of the replay | HTTP 200, body exact, 12,085 ms |
| Negative and extra checks on the public Worker | part of the replay | 17/17 |

The 17 checks: unknown customer and unknown card per service (contract 404 or 400), a customer without a
`statement.pdf.send` entry, the card's current week for `decide` and `change`, an empty card number, malformed JSON,
the `cards.balance` masking form used as input, numeric `customerNo`, string week, template-variable preview,
405 on GET, `/health`, CORS preflight.

The handler tests also cover every required field of every service (missing, empty, blank, null), all eight
predefined errors with their fixed guids, cards that share the last four digits, missing `debtGBP`, empty and
instruction-like product names, wrong methods and unknown paths.

## Output

```
Tests  682 passed (682)
   Start at  22:08:52
   Duration  453ms (transform 98ms, setup 0ms, collect 114ms, tests 84ms, environment 0ms, prepare 56ms)

Replaying 617 fixtures against https://freya-bank-mock.yasarkaancan.workers.dev
fixtures (non-delayed): 616/616 exact | statuses {"200":608,"404":2,"500":6} | latency ms p50=102 max=1124
DELAYED cards.balance 94907600 540000******7211: status 200, body exact, took 12085 ms (configured 12 s)
negative / extra checks: all passed

TOTAL: 634 passed, 0 failed
Sun Oct 11 22:09:17 +03 2026
```
