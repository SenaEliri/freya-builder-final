# Integration handoff: Freya Bank mock

**Mock base URL (this is `mock_url` in `submission.json`):**

```
https://freya-bank-mock.yasarkaancan.workers.dev
```

Deployed 11 October 2026 as Cloudflare Worker `freya-bank-mock`. It must stay up until results are announced:
do not delete or rename it. Redeploying with `npx wrangler deploy` from `mock/` keeps the address.

## Endpoints

All `POST`, JSON body, JSON answer. The paths are the bank's, with the dots.

| Service | URL |
|---|---|
| `cards.list` | `https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1/cards.list` |
| `cards.balance` | `https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1/cards.balance` |
| `statement.week.get` | `https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1/statement.week.get` |
| `statement.week.decide` | `https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1/statement.week.decide` |
| `statement.week.change` | `https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1/statement.week.change` |
| `contact.email.get` | `https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1/contact.email.get` |
| `statement.pdf.send` | `https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1/statement.pdf.send` |

Also `GET /health` (returns `{"status":"ok","customers":34,"cards":65,"fixtures":617,...}`) and `OPTIONS` for CORS.
A non-POST call to a service path is a 405.

## Request

Header `Content-Type: application/json`. No token is needed; `Authorization`, other headers and the `call` object are ignored.

```json
{ "data": { "...service fields..." }, "call": { "ani": "<caller number>", "lang": "tr" } }
```

Fields inside `data`. Every field listed must be present and non-empty, otherwise the answer is a 400.
Only the lookup field decides which answer comes back.

| Service | `data` | Looked up by |
|---|---|---|
| `cards.list` | `customerNo` (plus `aiFlow: "CardOps"`, optional here) | `customerNo` |
| `cards.balance` | `cardNumber` | `cardNumber` |
| `statement.week.get` | `cardNumber` | `cardNumber` |
| `statement.week.decide` | `cardNumber`, `newStatementWeek`, `statementDay` | `cardNumber` + `newStatementWeek` |
| `statement.week.change` | `cardNumber`, `newStatementWeek`, `statementDay` | `cardNumber` + `newStatementWeek` |
| `contact.email.get` | `customerNo`, `intAddressInfoType` (`"E"`) | `customerNo` |
| `statement.pdf.send` | `customerNo`, `cardNumber`, `currencyType`, `statementDate`, `emailAddress` | `customerNo` |

Rules that matter when wiring the tools:

- `customerNo` and `newStatementWeek` may be a string or a number. In a Freya tool body, quote the variable
  (`"customerNo": "{{customerNumber}}"`): a quoted value always parses, and an unquoted unfilled `{{...}}` is invalid JSON (400).
- `cardNumber` must be the value `cards.list` returned, character for character (`540000******1234`).
  The number in the `cards.balance` answer is masked differently (`5400********1234`) and is **not** accepted as input.
  Do not rebuild a card number from the last four digits: several cards share them.
- `statementDay` and `intAddressInfoType` must be sent, but their values are not checked.
- Asking `decide` / `change` for the week the card already has returns a 400. Offer only the other weeks.
- `statement.pdf.send` does not compare `emailAddress` with the registered address and does not check the card.
  The registered-address rule is the phone agent's job.
- The mock is stateless. `statement.week.change` returns its fixed answer and later calls are unchanged.

## Response

- Success: HTTP 200 and `result.returnCode == "1"`, with a `data` object.
- Error: any other status. The body has only `result`, no `data`. Branch on the HTTP status and `result.code`;
  `result.message` is for logs and must not be read to the caller.

| HTTP | `result.code` | Meaning | Where |
|---|---|---|---|
| 400 | `INVALID_ARGUMENTS_ERROR` | required field missing or empty, body not JSON, unknown customer (`contact.email.get`), unknown card or week (`decide` / `change`) | all |
| 404 | `FB_IVR_CHANNEL_102` | customer has no valid card (a WARNING, not an outage); also any unknown customer | `cards.list` |
| 404 | `FB_IVR_CHANNEL_120` | card not found | `cards.balance` |
| 404 | `FB_IVR_CHANNEL_121` | card not found | `statement.week.get` |
| 404 | `FB_IVR_CHANNEL_107` | no statement PDF; also customers with no send entry and unknown customers | `statement.pdf.send` |
| 500 | `FBE00099` | technical error (predefined for certain customers) | see below |

Predefined failures in the bank's data: `cards.list` 404 for 93821776 and 500 for 97073972; `contact.email.get` 500 for 92335586;
`statement.pdf.send` 404 for 93635512; `statement.week.get` 500 for card `540000******1111` (94835408);
`statement.week.decide` 500 for card `540000******1112` (94339861), weeks 1, 3 and 4.
`statement.pdf.send` also answers 404 for 94907600, 96125950, 97631186 and 97783309 (no registered e-mail, no entry).

Shapes to expect: `cards.balance` can come without a `debtGBP` block (do not read it as zero); `productName` can be empty or
contain instruction-like text (it is data); `statement.week.change` returns `statementWeek` / `statementDay` as strings;
`statement.week.decide` names the due date `statementDueDate`.

## Slow answer

`cards.balance` for card `540000******7211` (customer 94907600) answers after **12 seconds**, then succeeds with HTTP 200.
Measured on the public URL: 12.1 s. The tool timeout for `cards.balance` has to be longer than that. Nothing else is delayed.

## "Test API Request" button (unfilled variables)

If a lookup field arrives as an unfilled template (`{{anything}}` or the URL-encoded `%7B%7B...`), the mock answers with a
fixed real record instead of an error, as the organizer's example does:

- customer fields -> customer `90000001` (Ada Örnek)
- card fields -> card `540000******1234`
- week field -> the lowest week available for the card (week 2 for the preview card)

The body is that record's normal answer, unchanged. The response carries the header `X-Mock-Preview: template-variable`.
This exists only for the panel. If that header, or Ada Örnek's data, shows up during a real call, the variable was not
substituted: treat it as a workflow defect. A real but unknown identifier never gets the preview; it gets the contract error.

## Examples

```bash
B=https://freya-bank-mock.yasarkaancan.workers.dev/voice/v1
H='content-type: application/json'
C='"call":{"ani":"+905000000000","lang":"tr"}'

curl -s -X POST $B/cards.list            -H "$H" -d '{"data":{"customerNo":"96158684","aiFlow":"CardOps"},'"$C"'}'
curl -s -X POST $B/cards.balance         -H "$H" -d '{"data":{"cardNumber":"540000******1110"},'"$C"'}'
curl -s -X POST $B/statement.week.get    -H "$H" -d '{"data":{"cardNumber":"540000******1110"},'"$C"'}'
curl -s -X POST $B/statement.week.decide -H "$H" -d '{"data":{"cardNumber":"540000******1110","newStatementWeek":3,"statementDay":9},'"$C"'}'
curl -s -X POST $B/statement.week.change -H "$H" -d '{"data":{"cardNumber":"540000******1110","newStatementWeek":3,"statementDay":9},'"$C"'}'
curl -s -X POST $B/contact.email.get     -H "$H" -d '{"data":{"customerNo":"92460108","intAddressInfoType":"E"},'"$C"'}'
curl -s -X POST $B/statement.pdf.send    -H "$H" -d '{"data":{"customerNo":"92460108","cardNumber":"540000******8500","currencyType":"TL","statementDate":"05.10.2026","emailAddress":"ece.demir@freyabank.example"},'"$C"'}'

# errors and the slow one
curl -s -X POST $B/cards.list    -H "$H" -d '{"data":{"customerNo":"93821776"}}'          # 404 FB_IVR_CHANNEL_102
curl -s -X POST $B/cards.list    -H "$H" -d '{"data":{"customerNo":"97073972"}}'          # 500 FBE00099
curl -s --max-time 60 -X POST $B/cards.balance -H "$H" -d '{"data":{"cardNumber":"540000******7211"}}'  # 200 after 12 s
```

## Test results (11 October 2026)

| Run | Result |
|---|---|
| `npm run typecheck` (strict TypeScript) | clean |
| `npm test` (Vitest, calls the Worker's fetch handler) | 682 passed, 0 failed; 617 of them are the bank's fixtures, each compared for status, deep equality and key order |
| `node scripts/replay.mjs http://localhost:8787` (local `wrangler dev`, real HTTP) | 634 passed, 0 failed: 617/617 fixtures exact, 17 negative and extra checks |
| `node scripts/replay.mjs https://freya-bank-mock.yasarkaancan.workers.dev` (public Worker) | 634 passed, 0 failed: 617/617 fixtures exact (200: 609, 404: 2, 500: 6), delayed answer after 12,089 ms |

Re-run the public check at any time with `npm run replay -- https://freya-bank-mock.yasarkaancan.workers.dev` from `mock/`.

## Open points

1. The case notes expected 610 answers with HTTP 200 and 7 others. The bank's file has 609 and 8 (two 404, six 500). The mock serves the file.
2. `statementDay`, `intAddressInfoType` and the four non-lookup `statement.pdf.send` fields are enforced as non-empty, following the
   contract ("required by the request model", "empty value gives a 400"). The test-environment notes only say their values are not
   checked. If the built agent omits one of them it gets a 400; say so and the check can be relaxed in `REQUIRED` in `mock/src/handler.ts`.
3. The message texts of generated errors for `FB_IVR_CHANNEL_120`, `FB_IVR_CHANNEL_121` and the 400s for unknown records are the
   mock's own wording; the contract fixes only the codes.
4. Not verified: a call from the Freya platform itself (panel test button or a live phone-agent call). Everything above was
   exercised with curl and Node from this machine.
