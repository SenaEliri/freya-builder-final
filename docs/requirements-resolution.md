# Requirements resolution

Precedence used. API: service contract, then `test-customers.json` for exact answers, then `test-customers.md`.
Conversation: 9 Oct mail, then 8 Oct analysis, then 7 Oct session, then older material. Undated organiser files
(brief, example scenarios) are binding. The builder applies the same idea generically: sources are dated by file
name and later sources win; of two editions of one document only the newest is read.

Rules attributed to a "10 October follow-up" in my instructions are marked **unverified source**: that file is not
in the pack (see `source-inventory.md`). Where the same rule also stands in a source I have, that source is cited.

| Topic | Older instruction | Later / stronger instruction | Rule implemented | Confidence | Residual |
|---|---|---|---|---|---|
| Identity | Flow drawing shows a second check | Analysis 8 Oct section 2; kickoff mail: never built, IVR has identified the caller | No code, PIN or date of birth is asked | high | none |
| Statement-week limit | Older material: other limits | Analysis section 7: once per calendar year (Kerem, 7 Oct) | Once a year is the rule told to callers | high | No service tells whether the right is used (contract 5.3, open point 3). The agent offers the change and lets the service decide; it never claims to have checked |
| Upset caller | Recap item 5: two calming replies | Selin's correction in the same mail: three | Three calming replies, then agent; insults never returned | high | none |
| Silence | Earlier: main menu | Analysis 8.2, recap item 1 | Repeat shorter twice; third silence: "Sesinizi alamadığım için görüşmeyi sonlandırıyorum." and close | high | Not testable in chat simulation |
| Out of scope | Analysis 8.4: straight to main menu | 9 Oct mail item 2, which says the 8 Oct document is not yet updated on this | Ask "Size bu konuda yardımcı olamıyorum. Sizi ana menüye aktarmamı ister misiniz?"; yes: main menu; else resume | high | none |
| Currency names | Tables say "TL" | Analysis 4.9, recap item 6 | Full names in speech: Türk Lirası, Dolar, Euro, İngiliz Sterlini | high | The agent sometimes still says "TL" or "lira" (see open issues) |
| Another card | September draft: not present | Analysis 5.1 (also "10 Oct": unverified source) | Ask "Başka bir kartınızın borcunu öğrenmek ister misiniz?" before the offer, only with more than one eligible card | high | none |
| Joint statement | not present | Analysis section 7 step 5 | Say which other card is affected before the confirmation question | high | none |
| New card, no statement | not present | Analysis 4.10 (also "10 Oct": unverified source) | Say there is no debt; no invented date | medium | The agent presented the next due date as the due date in one test (open issues) |
| Statement cut day | not present | Analysis 4.10: cut is today at 00.00, then total debt (detail "use `totalDebt`" is from the unverified source) | Tell the caller the cut is today, give the total debt from the service | medium | No fixture has the cut on 12 Oct; not tested |
| Service timeout | none agreed | Contract section 4 and 7, analysis 8.3: open; answers over ten seconds can succeed | Tool timeout 30 s, no automatic retry | high | No bank-approved limit exists |
| Card number | Contract: masked in test | 9 Oct mail: production returns full numbers; never read more than the last four | Identify by last four only; card numbers sent to services exactly as returned | high | With masked test data, two cards with the same last four cannot be told apart by "last six" |
| Spouse's / other person's card | | Analysis 8.6: IVR login step. Example 5: main menu | No information, no action; the builder extracted both endings | medium | Sources disagree on the destination |
| E-mail address | | Analysis section 6, contract 5.7 | Only the registered address; the service does not check, so the agent must | high | none |
