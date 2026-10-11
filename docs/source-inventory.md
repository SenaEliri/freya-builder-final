# Source inventory: Freya Bank final case

Pack location used: `~/Downloads/Build the Builder - Final Case/` (same top-level contents as the shared Drive folder).
"Read by" says who actually read the file: **me** (the engineer on this work, in full unless noted) and **builder**
(every text file goes through the builder's extraction with Freya's model; see the build trace).

| File | Date | Author | Subject | Weight | Read by |
|---|---|---|---|---|---|
| `BRIEF.md` | undated | organisers | Task, scoring, submission format, deadline 11 Oct 23:00 Istanbul | binding for the competition | me, builder |
| `README.md` | undated | organisers | Pack overview, the two call variables | binding | me, builder |
| `example-scenarios.md` | undated | organisers | Six example calls with expected behaviour | binding for expected behaviour | me, builder |
| `statement-debt-call-flow.pdf` | undated | bank | Call-flow drawing | background; its second-factor box was never built (kickoff mail, analysis section 2) | **not read**: the builder takes text files only and I did not open it |
| `sources/documents/2026-10-01-service-contract.md` | 1 Oct 2026 | Mert Koç | Seven services, envelopes, errors, test-environment rules | authority for the API | me, builder |
| `sources/documents/2026-09-10-ivr-prompt-sheet.md` | 10 Sep 2026 | Burcu Tan | Today's IVR prompts; "don't read them as how it should be" | background | me: header only; builder |
| `sources/documents/2025-08-14-cards-faq.md` | 14 Aug 2025 | bank website | Public FAQ | background | me: searched only; builder |
| `sources/emails/attachments/2026-09-02-statement-debt-analysis.md` | 2 Sep 2026 | Selin Aydın | First analysis draft | replaced by the 8 Oct edition | me: header only; builder skips it (older edition of the same document) |
| `sources/emails/attachments/2026-10-08-statement-debt-analysis.md` | 8 Oct 2026 | Selin Aydın | Full analysis after the 7 Oct session | main authority for the conversation, except where the 9 Oct mail corrects it | me, builder |
| `sources/emails/2026-09-24-kickoff-questions.txt` | 24 Sep 2026 | Deniz Arı, bank replies | Kickoff questions (identity, timeouts, e-mail) | early decisions | me: searched only; builder |
| `sources/emails/2026-10-09-decisions-recap.txt` | 9 Oct 2026 | Deniz Arı, Selin Aydın | Decisions from 7 Oct with Selin's corrections | latest written authority | me, builder |
| `sources/meetings/2026-10-07-analysis-session-transcript.txt` | 7 Oct 2026 | meeting | Analysis session | decisions, later written up | me: searched only; builder |
| `test-environment/test-customers.md` | 1 Oct 2026 | Mert Koç | Lookup rules, data quirks, customer table | authority for fixture lookup | me, builder |
| `test-environment/test-customers.json` | 1 Oct 2026 | Mert Koç | 617 exact answers | authority for mock answers | me (by script), mock |
| `cloudflare-mock/README.md`, `example/worker.js`, `wrangler.toml`, `example-response.json` | undated | organisers | Worker pattern, template-variable preview | guidance for the mock | me |

## Referenced but absent

- `sources/meetings/2026-10-10-follow-up-session-transcript.txt`: named in the instructions I was given on 11 Oct, but
  it is not in the local pack and no file with "2026-10-10" or "follow-up" in its name shows in the Drive folder
  listing I could see. I did not read it and nothing here cites it. If it exists, drop it into `sources/meetings/`
  and rerun the builder: it reads every dated text file and later dates win.

## Gaps in my own reading

I did not read the PDF, and I read four sources only by search or header (marked above). The builder's model read
all text sources; what it took from each is in the build's `*.spec.json` under `rules`.
