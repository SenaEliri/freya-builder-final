# Open issues

## From the bank's side (unresolved in the sources)
1. No flag for "statement-week right already used this year" (contract open point 3, analysis open point 1).
2. No agreed client timeout or retry policy (contract open point 1).
3. Card-number masking in production `cards.list` (contract open point 2; the 9 Oct mail says full numbers).
4. Foreign-currency total on the no-debt reading; the line for foreign debt moved into Turkish Lira (analysis open points 3, 4).
5. Destination for a caller asking about someone else's card: IVR login (analysis) or main menu (example 5).

## Missing input
6. `2026-10-10-follow-up-session-transcript.txt` is named in my instructions but is not in the pack. Not read, not used.
7. `statement-debt-call-flow.pdf` was not read by me or by the builder (text files only).

## Known behaviour of the built agent (see `tests/reports/`)
8. The agent's model is not deterministic and each build re-extracts its instructions; results vary between runs and builds.
9. Under a simulated caller who names the week before the options are read, the judge marked "options not presented" (example 2).
10. The agent sometimes says "TL" or "lira" where the rule asks for "Türk Lirası", and once said "lira" for a Euro amount.
11. Voice behaviour (silence, interruptions) cannot be exercised in chat runs.

## Mock
12. Required-field strictness: `statementDay`, `intAddressInfoType` and the non-lookup `statement.pdf.send` fields must be present and non-empty (contract wording). Relax in `mock/src/handler.ts` `REQUIRED` if needed.
13. Message texts of generated `FB_IVR_CHANNEL_120`/`121` and unknown-record 400 errors are the mock's wording; the contract fixes only the codes.
