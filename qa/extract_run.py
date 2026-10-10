"""Run Phase 0 extraction for a brief set and save the policy + answers (gate tool).

    python3 -m qa.extract_run out.json tools/openapi.json briefs/brief-a.md [briefs/brief-b.md]
"""
import json
import sys
import time

sys.path.insert(0, ".")
from builder.policy import extract, openapi  # noqa: E402
from builder.trace import Trace  # noqa: E402

out, api = sys.argv[1], sys.argv[2]
briefs = [open(b).read() for b in sys.argv[3:]]
tr = Trace(None, echo=True)
t0 = time.time()
pol, rep = extract.extract(briefs, openapi.load(api), trace=tr)
json.dump(pol, open(out, "w"), indent=1)
json.dump(rep, open(out.replace(".json", ".report.json"), "w"), indent=1)
print("seconds:", round(time.time() - t0, 1), "| section problems:", rep["section_problems"], "| policy errors:", rep["policy_errors"])
