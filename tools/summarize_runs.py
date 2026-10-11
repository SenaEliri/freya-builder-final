"""Per-case consistency across live runs (tools/run_cases.py --out files), as a Markdown table.

    python3 tools/summarize_runs.py results/c2/suiteA-r1.json results/c2/suiteA-r2.json results/c2/suiteA-r3.json

A run of a case is classed as infrastructure when the evidence says the agent never got a fair turn: no call was
created, the call has no tool calls and no judge verdict, the simulation did not complete, or the slowest agent turn
was over 30 s (the platform's model, not the decide code), or the judge never produced a verdict while the bank
records passed. Everything else that fails is an agent failure.
"""
import json
import re
import sys


def classify(row, sim_status):
    if row["pass"]:
        return "pass"
    why = " ".join(row.get("failed") or [])
    if sim_status not in (None, "completed") or not row.get("call_id"):
        return "infra"
    judge_only = all(f.startswith("conversation:") for f in row.get("failed") or [])
    if judge_only and re.search(r"analysis never arrived|no verdict|timed out|internal error", why, re.I):
        return "infra"  # the bank records passed and the judge produced no verdict
    if not row.get("tools") and "no verdict" in why:
        return "infra"
    if (row.get("slowest_turn_s") or 0) > 30:
        return "infra?"
    return "agent"


def main(paths):
    runs = [json.load(open(p)) for p in paths]
    cases = []
    for r in runs:
        for row in r.get("rows") or []:
            if row["id"] not in cases:
                cases.append(row["id"])
    print("| case | passed | " + " | ".join("run %d" % (i + 1) for i in range(len(runs))) + " |")
    print("|---|---|" + "---|" * len(runs))
    details = []
    for cid in cases:
        cells, n = [], 0
        for i, r in enumerate(runs):
            row = next((x for x in r.get("rows") or [] if x["id"] == cid), None)
            if row is None:
                cells.append("-")
                continue
            c = classify(row, r.get("status"))
            n += row["pass"]
            cells.append(c)
            if not row["pass"]:
                details.append("- %s run %d (%s, call %s): %s" % (cid, i + 1, c, row.get("call_id"),
                                                                  "; ".join(f[:220] for f in row.get("failed") or [])))
        print("| %s | %d/%d | %s |" % (cid, n, sum(1 for c in cells if c != "-"), " | ".join(cells)))
    print()
    for i, r in enumerate(runs):
        print("- run %d: simulation %s, iteration %s, %s/%s passed, %ss" % (
            i + 1, r.get("simulation_id"), r.get("iteration_id"), r.get("passed"), r.get("total"), r.get("seconds")))
    if details:
        print("\nFailures:")
        print("\n".join(details))


if __name__ == "__main__":
    main(sys.argv[1:])
