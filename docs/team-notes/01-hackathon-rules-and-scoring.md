# 01 — The hackathon: task, timeline, scoring, submission, rules

Source: https://www.freyavoice.ai/hackathon (all tabs: Overview, Data, Evaluation, Submit, Leaderboard, Rules, FAQ) and the kit's `README.md` (v3).
Raw copies: `reference/hackathon-page/` and `reference/kit/build-the-builder/README.md`.

## What it is

**Build the Builder** — Freya × Y Combinator. "Build an AI agent that builds other agents on Freya."
Online, October 10–11, 2026. Solo or teams of two. Domain: **debt collection**. Conversations: **text** (not audio).
Registration: https://events.ycombinator.com/AI-FDE-Build-the-Builder26. The Freya account and the support channel arrive by email at the start.

The story: a bank phones customers who are late on a payment. The call must check who is on the line, say what is owed and record when they will pay. On Freya, software makes that call. Someone has to read the bank's specification and build the caller to follow it ("never mention the debt before the identity check, never accept a promise on a holiday, say nothing to a relative"). Today a person does this by hand, and one bank takes days. **Question of the hackathon: can a program do that work instead?**

Example from the page (what the bank's system keeps is the last line):

```
Phone agent: Your credit card has 420 dollars past due. Can you pay today?
Customer:    Not today. I can do it on Friday.
Phone agent: 420 dollars on Friday the sixteenth. Do you confirm?
Customer:    Yes.
create_promise 420.00 2026-10-16      <- recorded in the bank's system
```

### Three words

| Term | Meaning |
|---|---|
| **Phone agent** | The software that talks to the customer. It lives on Freya as a **workflow**: steps (nodes), prompts and tools. |
| **Brief** | The bank's specification for these calls: who to ask for, how to check identity, which payment dates are allowed, how to close the call. |
| **Builder** | The program **we** write. It reads a brief and creates the phone agent. Nobody edits the phone agent by hand. |

"You write the builder. We score the phone agent it creates." One case = one simulated customer. The kit calls a step of a phone agent a **node**.

Pipeline diagram on the page: **Brief** (policies, tool API docs, practice customers) → **Your builder** (reads the brief, creates the phone agent, tests and improves it — *the part you write*) → **Phone agent** (a workflow on Freya, conditional routes, tool calls) → **Their benchmark** (simulated customers talk to the phone agent, they read the bank's records, score = cases passed / cases run). "A new brief goes in, a different phone agent comes out, no edits by hand."

## Timeline

Istanbul is UTC+3.

| Milestone | UTC | Istanbul |
|---|---|---|
| Start: kit and keys | Sat 10 Oct, 10:00 | Sat 13:00 |
| Build against the 13 practice cases | Sat 10:00 → Sun 17:00 | Sat 13:00 → Sun 20:00 |
| **Hidden briefs open** — two briefs, each with its own tool API file, sent by email to every team | **Sun 11 Oct, 17:00** | **Sun 20:00** |
| **Close: submit** (form sent to the address in the kit email) | **Sun 20:00** | **Sun 23:00** |
| Results | after review | |

"The three hours in orange are for running the builder and fixing bugs, not for tuning it to the new briefs." (the orange band on the timeline = Sun 17:00–20:00 UTC)

### How the weekend goes (from the page)

1. Download the kit (Data tab): two briefs, the bank's tool API, 13 practice customers, the Freya workflow reference and a small working builder.
2. Run the sample builder. It creates a phone agent on Freya in your workspace.
3. Test that phone agent. Simulated customers talk to it in text. You see which ones it handled correctly and why the others failed.
4. Write your own builder; repeat 2 and 3 as often as you like.
5. **Sunday: briefs you have not seen.** Same kind of call, different rules: other identity questions, other limits and deadlines, another outcome table, another calendar. **The seven tool names stay the same. Their fields and allowed values can change.**
6. Run your builder once on each new brief and submit the phone agents it created, your code and the builder's trace.
7. They test those phone agents on customers nobody has seen. The share handled correctly is the score.

## Scoring

**Score = cases passed / 60.** No partial credit.

A case passes only when **all three checks** pass:

| Check | Question | Read from | Example |
|---|---|---|---|
| **Outcome** | Is the ledger in the right state? | The bank's records (the mock bank's ledger), not what the agent said | Promise on the right product, date and amount, recorded once. Also every note, callback and transfer, and the close outcome/reason. |
| **Policy** | Did it stay inside the brief? | Transcript, by a judge model, against the checks listed for that case | No debt read before the identity check, no date past the limit. |
| **Honesty** | Did it tell the customer the truth? | Transcript, by a judge model | Never says "recorded" when the tool call failed. |

- "The bank's API does not enforce the brief. It records a promise on a holiday or below the minimum without complaint. Keeping the rules is the phone agent's job."
- "A correct refusal counts. When the customer disputes the debt, the passing outcome is a recorded dispute and no promise. A phone agent that pushes for a promise anyway fails."
- "The same phone agent can pass a customer in one run and fail it in the next. Treat one green run as a hint, not as proof."

### The final benchmark

| Item | Value |
|---|---|
| Hidden briefs | **2**. One is a clean specification. The other is **raw bank material: a mail, a policy extract, a memo that changes it, a code list.** Each is one Markdown file with its own tool API file next to it. |
| Customers per brief | **30**, with **one to three products**, on **several calendar days** |
| How customers talk | Like people: a number said in two parts ("463..." then "51"), corrections, talk about other things, a question back, amounts and dates in words |
| Repetitions | **3 per case. The case passes only when all 3 runs pass.** |
| Score | cases passed / 60 |
| 1st tie-break | Total promised amount recorded on the cases that passed |
| 2nd tie-break | Shorter total build time, read from the builder's traces |
| 3rd tie-break | Earlier submission time |

"A phone agent that is right most of the time is not right." (README)

### Practice scoring (kit)

```
$ python3 tools/run_cases.py <agent_id> --brief A

PASS PUB-01 easy   Happy path   | verify > verify > get_account > promise > close_call
FAIL PUB-04 medium Dates        | verify > verify > get_account > promise > close_call
       - promises [('p1', 1250.0, '2026-10-27')], expected [('p1', 1250.0, '2026-10-23')]
...
5 / 10 passed
```

`verify` = `verify_identity`, `promise` = `create_promise` in the printout. A ten-case run takes **3 to 11 minutes**. **One simulation runs at a time per workspace, and a team has one workspace.** Use `--reps 3` (a customer counts only when every run passes, as in the final). Practise human-like talk with `--style pieces|corrects|talkative|asks_back|in_words`.

## What counts (rules of the game)

- **Only the phone agents are scored.** Rank comes from their score. The builders of the top entries are rerun to verify. Build time is the 2nd tie-break.
- **A customer counts as handled** when the bank's records are right afterwards and the conversation followed the brief.
- **The builder must work alone.** One command, a brief as input, a phone agent as output. No manual edits after it runs.
- **The final briefs are hidden** so that a builder tuned to the two public briefs does not win. It has to read a brief it has never seen. "So build something that reads a brief, not something that knows this one. Whatever your builder can take from the brief, it should take from the brief." (README)
- **After the hidden briefs open** you may fix a bug in your builder. You may **not** write anything from a hidden brief into it: **no rule, no value, no name**. Fixing a crash on a table your parser did not expect is allowed. Adding the new brief's holiday dates or outcome names to your code or prompts is not. A reviewer checks the commit for that.
- **Calls are in English.** The phone agent gets the date and time of the call as a variable, **`now`**. Every date rule uses it.
- **Every phone agent runs on the same Freya model** (`AGENT_LLM` in `freya.py`: provider/model `experimental-5`, "Freya's model on the event's own GPU box"). Do not change it. The builder may use any model or coding agent (you pay for your builder's model calls).

### Formal rules (Rules tab)

- Enter solo or as a team of two.
- You submit a **builder**. A hand-built phone agent on its own is not a valid entry.
- The phone agents for the hidden briefs must come out of the submitted commit with no manual edits.
- Submit **one builder trace per hidden brief**. An entry without traces is not ranked.
- The phone agent may call **only the tool API from the kit**. A call to any other service fails the case. (Code steps and hooks inside the workflow are allowed and expected.)
- **Do not probe or load-test the platform. One Freya key per team.**
- You may fix your builder after the hidden briefs open. Nothing from a hidden brief may be written into it.
- All data is synthetic. Do not bring real customer data.

### Limits

| Limit | Value |
|---|---|
| Builder run time | **30 minutes per brief**, including any test the builder runs on its own phone agent |
| Workflows per workspace | **200**. Update one in place instead of creating a new one per run (`Workspace plan limit reached` otherwise). |
| Models the builder may use | Any. You pay for your builder's own model calls. |
| Model the phone agent runs on | The Freya model set in `freya.py`. Same for every team. Do not change it. |
| Practice simulations | **1 running at a time per workspace** (a second `run_cases.py` waits for the first) |

## Submission ("Two phone agents, one commit and the builder's trace")

1. Sun 17:00 UTC: two hidden briefs arrive by email, each with its own tool API file.
2. Run the builder on each brief and **keep everything it prints**. You may run it more than once. Submit **one phone agent per brief**, with the trace of the run that made it. Do not edit a phone agent after the run.
3. Export each phone agent with `freya.export_workflow(workflow_id, "<brief>.workflow.json")` and **commit the files**. They load them into their own workspace, so **what you export is what they score**.
4. Before **20:00 UTC**, send the form to the address in the kit email.

Example run command from the page:

```bash
python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log
```

Form (JSON):

```json
{
  "team": "your-team-name",
  "repo": "https://github.com/you/your-builder",
  "commit": "9f2c1ab",
  "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
  "workflows": {
    "hidden-1": "submission/hidden-1.workflow.json",
    "hidden-2": "submission/hidden-2.workflow.json"
  },
  "traces": {
    "hidden-1": "traces/hidden-1.log",
    "hidden-2": "traces/hidden-2.log"
  }
}
```

### The builder's trace

A trace = the record of one builder run: what it read, what it decided, what it created. One per hidden brief, committed to the repo. Plain text is fine; no required format. **Remove API keys before you commit.**

| Must be in the trace | Why |
|---|---|
| Start and end time of the run | Build time breaks ties |
| Every model call the builder made: which model, and what it was asked for in one line | Shows how the builder works, not only what it produced |
| What it created on Freya: workflow id, agent id, number of steps and tools | Ties the submitted phone agent to this run |
| Any test it ran on its own phone agent, with the result | "A builder that checks its own work is the point of the exercise." |

Optional: if you built the builder with a coding agent (Claude Code, Codex), you may share those session logs. The top three teams talk their approach through with Freya; a log is the easiest way to show it.

### How they verify

- They test the phone agents you submitted (score comes from your exported workflows, not from their rebuild).
- For the **top ten** teams they also clone the repo at that commit, run the builder themselves on the same briefs and compare with your trace. Model output varies, so they don't expect an identical workflow — they look at its structure and its score.
- Every trace is read by a **reviewer agent** that checks it against the submitted code and the phone agent it claims to have created.
- **If their run scores clearly below yours, the entry is removed.** (This catches hand-edited phone agents.)

## Prizes

| Place | Prize |
|---|---|
| First | YC interview |
| Second | AirPods |
| Top three | Final interview with Freya |
| Prize pool | $3,000 in Freya credits |

Leaderboard columns: Rank, Team, Score, Passed, Promised amount, Submitted. Empty until the hidden benchmark has run and the top entries are verified.

## FAQ (verbatim answers, condensed)

| Question | Answer |
|---|---|
| I did not get the login mail. | Look in spam first. **Mail to Outlook, Hotmail and some university addresses was filtered.** If not there, reply to them and they resend. (Same risk for Sunday's hidden-brief email — watch spam.) |
| Where is the kit? | Data tab, "Download the kit". Unzip it and read `README.md` first. |
| Where do I get a Freya API key? | Sign in with the account they mailed you (https://staging-app.freyavoice.ai), open **API keys** in the dashboard and create one. Put it in `env.sh` as `FREYA_API_KEY`. |
| My teammate has no account, or we have two workspaces. | **Work in one workspace.** Its owner invites the teammate from Workspace settings (https://staging-app.freyavoice.ai/workspace/settings). If the teammate has no account at all, reply to them with the address. |
| A test call in the dashboard never passes identity. | The workspace has one practice customer for dashboard test calls. Answer as that customer: **date of birth 14 March 1988, last four digits 4471**. After a call has closed, the same customer starts fresh once it has been idle for **5 minutes**. `run_cases.py` opens a fresh customer for every case, so it is not affected. |
| How many workflows can a workspace hold? | 200. Still, update your workflow in place. |
| Can my builder open practice customers of its own? | **No.** The practice bank serves the 13 cases PUB-01 to PUB-13 only. To check a phone agent on a brief with no cases, talk to it with `POST /api/v2/chat/message` (see `docs/api.md`). |
| Do the hidden briefs come with practice cases? | **No.** Each comes with its tool API file only. |
| Is the raw-material brief one file? | Yes. Each hidden brief is one Markdown file, with its own tool API file next to it. `{brief_path}` is that one file. |
| May I use code I wrote before the event? | Yes. Nothing from the hidden briefs may be in your builder, and the phone agents must come out of your builder with no hand edits. |
| Is the score taken from the phone agent we submit, or from your rebuild? | From the phone agents you export and submit. They rebuild only the top entries, to check that the submitted phone agent really came out of your builder. |
| My score dropped and I changed nothing. | The simulated customers and your phone agent are language models, so runs differ. A run also suffers when the model is busy: `run_cases.py` prints the slowest agent turn per call. Run again, and use `--reps 3` before you trust a number. |
| Something else? | Reply to the login mail. It reaches them. |

## Starting info from the organisers' email (as given to us)

- Hackathon page: https://www.freyavoice.ai/hackathon
- Starter kit v3: https://www.freyavoice.ai/hackathon/build-the-builder-v3.zip (version in file name and at the top of README.md; they email new versions)
- Freya API key: sign in at https://staging-app.freyavoice.ai, create a key in the workspace under API keys, put it in `env.sh` as `FREYA_API_KEY`.
- Bank tool API: described in `tools/openapi.json`. Pick your own **team key** (any secret of 16+ characters) and use the same one every time (`FREYA_BANK_TEAM_KEY`).
- Starter workflow: the workspace already has **"Freya Bank Collections Base"**. Its test variables hold a practice customer, so you can start a chat right away. It is the same agent as `examples/base-agent.json`.
- Docs: https://docs.freyavoice.ai
