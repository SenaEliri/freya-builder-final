# Hand-off to QA — frozen candidate 1 (11 Oct 2026, 07:35 UTC)

| | |
|---|---|
| Branch / commit | `rebuild/core` @ `d798445` (builder code identical to `f806122`, which built the agents) |
| `python3 -m qa.identity` | `builder b528d245355bc1cd`, `runtime bac97a98b178` (also in each build trace's START line) |
| Brief A agent | slot `rb-brief-a` · workflow `bc5fe0d0-0d34-4e9a-bcb2-62dab24d3cc7` · agent `edf86627-20cc-41ce-be0d-51115a31061e` · **published version 3** |
| Brief A+B agent | slot `rb-brief-a-brief-b` · workflow `e382d2c5-7a09-42a0-96d8-0d1d60579e08` · agent `2b88bb81-311c-4e81-8858-37c60ea2ded3` · **published version 5** |
| Built by | the official command, model extraction included: `traces/20261011T071113Z-rb-brief-a.txt`, `traces/20261011T071328Z-rb-brief-a-brief-b.txt` |
| Exported files | `submission/brief-a.workflow.json`, `submission/brief-a-brief-b.workflow.json` |

Nothing will be published to these two slots while QA tests. Development continues on other `rb-` slots only.

## What was run on exactly these versions (single runs, not a claim)

- `rb-brief-a` v3: Brief A, style pieces: 10/10, lesson checks clean.
- `rb-brief-a-brief-b` v5: Brief B, styles asks_back and in_words: 3/3 each, lesson checks clean.
- Earlier versions of the same builder (same slots): Brief A plain 10/10, Brief B plain 3/3, B talkative / corrects /
  pieces 3/3 after the fixes now included.

## Suggested QA order (from the rebuild plan)

```bash
source env.sh
python3 tools/run_cases.py edf86627-20cc-41ce-be0d-51115a31061e --brief A --only PUB-03,PUB-04,PUB-07 --out results/qa1.json
python3 tools/run_cases.py edf86627-20cc-41ce-be0d-51115a31061e --brief A --only PUB-09,PUB-01,PUB-02,PUB-05,PUB-06,PUB-08,PUB-10 --out results/qa2.json
python3 tools/run_cases.py edf86627-20cc-41ce-be0d-51115a31061e --brief A --reps 3 --out results/qa-a3.json
python3 tools/run_cases.py 2b88bb81-311c-4e81-8858-37c60ea2ded3 --brief B --reps 3 --out results/qa-b3.json
python3 -m qa.check_run results/qa-a3.json submission/brief-a.policy.json      # lesson checks on the calls
```

Styles worth a repetition each: `--style pieces`, `corrects`, `talkative`, `asks_back`, `in_words`.

## Known limits

- Platform latency under load: the platform's extraction step sometimes takes 15–30 s (code steps 0.3–1 s).
  run_cases.py flags runs whose median slowest turn is above 10 s; organisers repeat those.
- A verified customer who asks to be called back later has no callback flow (neither public brief has one).
