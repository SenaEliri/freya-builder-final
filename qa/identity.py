"""Identity of the frozen builder: commit + hash of the builder code (the same hash the trace records).

    python3 -m qa.identity
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.build import git_commit, identity_hash  # noqa: E402
from builder.emit import bundle  # noqa: E402

if __name__ == "__main__":
    print("commit %s | builder %s | runtime %s" % (git_commit(), identity_hash(), bundle.runtime_hash()))
