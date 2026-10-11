# Live validation of candidate 2 (Freya staging, 11 Oct 2026)

Real Freya extraction and execution, the hosted practice bank, the organisers' judge. Runner:
`tools/run_cases_retry.py` (the kit's `tools/run_cases.py`, unmodified, plus GET retries, a wait for a running
simulation, and the practice sessions saved before polling). One simulation at a time in the workspace. Every failure
below was classified from the call's own event log (`tools/summarize_runs.py --evidence`, read by hand as well), never
from the score alone. Raw outputs (simulation, iteration, call and practice-customer ids): `qa/live-results/`.

## The tested candidate (frozen)

| | Brief A | Brief A + B |
|---|---|---|
| Slot | `rb-c2-brief-a` | `rb-c2-brief-a-brief-b` |
| Workflow / agent | `eb8c91b8-ef17-4e43-ad6b-831096b299dd` / `8cd8c4c7-81b9-4517-b3b0-90a14d6d6358` | `310fbf87-6c7c-4aef-bef3-fbc5709842e3` / `02348dd0-989b-4359-bdbe-7c925c22477f` |
| Published version | 5 | 4 |
| Source commit / runtime | `9279ea0` / `a6ca24d742b1` | `9279ea0` / `a6ca24d742b1` |
| Export (sha256) | `submission/candidate-2/brief-a.workflow.json` (`a6583c8c…09d1`) | `submission/candidate-2/brief-a-brief-b.workflow.json` (`17fad486…6184`) |
| Policy | `submission/brief-a.policy.json` (the one candidate 1 was built from) | `submission/brief-a-brief-b.policy.json` |

"v5" below means this runtime (A agent version 5, B agent version 4). Nothing was edited or published between the
suite runs. The frozen candidate-1 agents (`rb-brief-a` v3, `rb-brief-a-brief-b` v5) were never written to (checked
after the runs: still versions 1-3 / 1-5, published 3 / 5).

## Frozen suites, three runs each (all public cases, plain customers)

| Case | Passed | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| PUB-01 | 3/3 | pass | pass | pass |
| PUB-02 | 2/3 | infra | pass | pass |
| PUB-03 | 2/3 | infra | pass | pass |
| PUB-04 | 3/3 | pass | pass | pass |
| PUB-05 | 3/3 | pass | pass | pass |
| PUB-06 | 3/3 | pass | pass | pass |
| PUB-07 | 2/3 | pass | pass | unclear (probably latency) |
| PUB-08 | 3/3 | pass | pass | pass |
| PUB-09 | 3/3 | pass | pass | pass |
| PUB-10 | 3/3 | pass | pass | pass |
| PUB-11 | 3/3 | pass | pass | pass |
| PUB-12 | 3/3 | pass | pass | pass |
| PUB-13 | 3/3 | pass | pass | pass |

- Simulations: A `e182971c` (8/10), `708ce9df` (10/10), `e8047f6d` (9/10); B `54ba20ea` (3/3), `285f1eca` (3/3), `b09cb4af` (3/3).
- **Strict metric (a case counts only if all three runs pass): 10 of 13** (A 7/10, B 3/3). 36 of 39 calls passed.
- Every passing run passed both the bank-ledger check (outcome and reason, promise amounts and dates per product, notes
  per product, callbacks, transfers, `close_call` last) and the judge's conversation checks (attempt limits, floor
  offered once, read-back and confirmation, required sentences).
- PUB-02 run 1, PUB-03 run 1 — **infrastructure (proven)**: the customer answered the opening at ~1.5 s, the platform
  never left the `open` node (no routing, no code step, no error), the simulated customer hung up at 62 s.
- PUB-07 run 3 — **unclear, probably infrastructure**: every customer turn took 17-22 s to process (normal 1-2 s); the
  simulated customer hung up silently 2 s after the agent's fourth line (the disclosure and the brief's required first
  ask), with no tool error and nothing wrong in the conversation so far. The log cannot prove why the simulator hung up.
  PUB-07 passed in the other two suite runs and in all six focused v5 styles where it was reached.

## Focused runs on v5 (affected cases, every speech style)

| Style | A (PUB-04/05/06/07/10) | B (PUB-11/12/13) |
|---|---|---|
| plain | 3/5 — PUB-05, PUB-06 infra (never left `open`, hang-up at 62 s) | 3/3 |
| in_words | 5/5 | 3/3 |
| pieces | 5/5 | 3/3 |
| corrects | 5/5 | 3/3 |
| talkative | 2/5 — PUB-04 infra (platform 420 s call cap: 382 s of it waiting on agent replies); PUB-06, PUB-10 infra (bank tool calls answered with Cloudflare HTML error pages, so `get_account` / `close_call` failed; the agent gave the honest technical ending and never claimed a record) | 2/3 — PUB-11: the simulated customer never gave the phone digits in ~15 turns of small talk; the agent re-asked within its bound and closed `not_verified/declined` (simulator loop; no agent defect found) |
| asks_back | 1/5 — PUB-04/05/07/10 infra (never left `open`, hang-up at 62 s) | 3/3 |

Simulations (A: plain `987c6d26`, in_words `595fb674`, pieces `a3b82f49`, corrects `4e6ed79b`, talkative `3353180f`,
asks_back `120ccf90`; B: pieces `3586c086`, talkative `8e9e178b`, asks_back `d8dbd8e2`, plain `759dded0`, in_words
`13304de1`, corrects `27357b9c`). **No agent failure on v5 in the focused runs.**

## Earlier versions — evidence for the fixes, not validation of v5

Each version changed the runtime, so none of these results validates the final candidate; they show what was found live
and fixed (details and transcripts as tests: HANDOFF.md, `tests/test_walk_livelike.py` `test_live_c2_*`).

| Version | Runs | Result | Agent defects found → fixed in |
|---|---|---|---|
| v1 | A plain; A in_words (`5553f9dc`, `79b38400`) | 4/5; 3 pass, 1 fail, 1 no verdict | "full amount is too much" read as a proposal; floor named twice → v2 |
| v2 | A × 6 styles; B × 6 styles (12 simulations) | A 30/30; B 13/18 | "all three of them" = $3; "all day" small talk refused every product; too_much misread; re-ask after an ask-back → v3; one sandbox failure (infra) → retry node in v3 |
| v3 | A plain `3d4d2982`, A in_words `9efc2d7d`, B pieces `d82d478f` | 5/5; 2/5; bank 2/3 | floor offered again after "what is the minimum?" → v4; cut "on 30…" + "October" lost the day → v5 |
| v4 | (A only, not run before v5) | — | — |

## Timing (platform timestamps, `tools/sim_timing.py`)

| Run | Queue s | Calls s | Judge s | Polling s | Reply median/max s | Extraction median/max s | Decide step median/max s |
|---|---|---|---|---|---|---|---|
| suite A r1 | 1.5 | 229 | 0.6 | 9.8 | 10.4 / 33.2 | 7.6 / 32.3 | 0.9 / 7.6 |
| suite A r2 | 0.3 | 176 | 3.6 | 8.6 | 10.1 / 24.2 | 7.8 / 20.2 | 0.7 / 9.0 |
| suite A r3 | 0.2 | 166 | 0.8 | 11.6 | 2.7 / 38.3 | 0.9 / 37.6 | 0.5 / 3.1 |
| suite B r1 | 1.8 | 260 | 0.8 | 8.4 | 2.6 / 51.0 | 1.7 / 50.8 | 0.4 / 2.6 |
| suite B r2 | 1.9 | 96 | 3.5 | 3.1 | 2.1 / 38.2 | 1.0 / 38.0 | 0.6 / 2.1 |
| suite B r3 | 1.1 | 178 | 3.7 | 5.7 | 11.9 / 20.9 | 9.2 / 20.0 | 0.6 / 4.2 |
| v3 A plain (the 880 s run) | 526 | 171 | 172 | 12 | 9.7 / 43.3 | 8.8 / 43.0 | 0.4 / 3.5 |

The agent's own work per turn (the decide code step) stays under a second at the median; the waiting customers hear
is the platform's extraction model. Queue and judge time are the platform's; polling is ours (10 s interval).

## Infrastructure during the day (all outside the agent)

- Practice bank unreachable from this network 09:07-09:12 UTC (TCP timeouts to its Cloudflare edge; other hosts fine).
- Freya API: 504 on every route ~09:40-10:08 UTC; intermittent 504s on simulation detail routes ~10:40-12:05 UTC; the
  workflow dry-run and the chat route timing out at 60 s around 12:20 UTC.
- One simulation (`d82d478f`, B pieces on v3) stayed "running" for two hours with two calls stuck in the judge's
  analysis; it blocked the workspace (one simulation at a time) and was set to `paused` (my own test run, nothing
  deleted); its calls were scored from the bank ledgers (customer ids read from the call logs).
- One sandbox failure of a decide step ("did not return a parseable result") in 351 steps; the judge's analysis
  missing on 5 calls whose bank records passed; bank tool calls answered with Cloudflare HTML error pages in one run.
