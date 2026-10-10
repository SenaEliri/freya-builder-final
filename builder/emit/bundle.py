"""Bundle the runtime source + the policy into the code string of the decide node.

The policy travels as hex-encoded JSON so the code contains no braces from the policy, and the code
never contains two consecutive braces (the platform may template the code field).
"""
import json
import pathlib

RUNTIME = pathlib.Path(__file__).resolve().parent.parent / "runtime" / "agent_runtime.py"


def code(policy):
    src = RUNTIME.read_text(encoding="utf-8")
    payload = json.dumps(policy, ensure_ascii=True, separators=(",", ":")).encode("utf-8").hex()
    tail = ("\n\nPOLICY = json.loads(bytes.fromhex('%s').decode('utf-8'))\n"
            "try:\n    run(vars, POLICY)\nexcept Exception as _e:\n"
            "    vars['route'] = 'end_tech'\n    vars['rb_error'] = str(_e)[:200]\n") % payload
    out = src + tail
    if "{{" in out or "}}" in out:
        raise ValueError("decide code would contain double braces")
    return out


def runtime_hash():
    import hashlib
    return hashlib.sha256(RUNTIME.read_bytes()).hexdigest()[:12]
