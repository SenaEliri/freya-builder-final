"""Bundle the runtime source + the policy into the code string of the decide node.

Size matters (L16): the platform refuses a code_exec whose code plus variables exceed 131072 bytes ("over the
131072-byte limit a sandboxed process can receive", seen live 10 Oct with a 98 KB bundle in a three-product call).
So the runtime is minified (AST round trip without docstrings and comments, one space per indent level) and the
policy travels as compact JSON text. The code never contains two consecutive braces (the platform may template
the code field).
"""
import ast
import base64
import hashlib
import json
import pathlib
import zlib

RUNTIME = pathlib.Path(__file__).resolve().parent.parent / "runtime" / "agent_runtime.py"
LIMIT = 131072          # code + variables, bytes
CODE_BUDGET = 60000     # leave the rest for the call's variables (about 115 bytes per variable)


def _no_double_braces(text):
    while "}}" in text:
        text = text.replace("}}", "} }")
    while "{{" in text:
        text = text.replace("{{", "{ {")
    return text


def minify(src):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    out = ast.unparse(tree)
    lines = []
    for line in out.split("\n"):
        stripped = line.lstrip(" ")
        if not stripped:
            continue
        lines.append(" " * ((len(line) - len(stripped)) // 4) + stripped)
    return _no_double_braces("\n".join(lines))


def code(policy, compressed=True):
    """The decide node's code: the minified runtime + policy, zlib-compressed and base64-encoded, run with exec.

    zlib, base64 and exec of a decompressed snippet that writes vars were verified in a code node on 10 Oct
    (qa/probe_modules.py). About 26 KB instead of 98 KB."""
    src = RUNTIME.read_text(encoding="utf-8")
    pj = json.dumps(policy, ensure_ascii=True, separators=(",", ":"))
    if compressed:
        inner = minify(src) + "\nPOLICY = json.loads(%s)\nrun(vars, POLICY)\n" % repr(pj)
        blob = base64.b64encode(zlib.compress(inner.encode("utf-8"), 9)).decode("ascii")
        out = ("import zlib, base64\n"
               "try:\n"
               " exec(zlib.decompress(base64.b64decode('%s')).decode('utf-8'), {'vars': vars, '__name__': 'rb_decide'})\n"
               "except Exception as _e:\n"
               " vars['route'] = 'end_tech'\n"
               " vars['rb_error'] = str(_e)[:200]\n") % blob
    else:
        tail = ("\nPOLICY = json.loads(%s)\n"
                "try:\n run(vars, POLICY)\nexcept Exception as _e:\n"
                " vars['route'] = 'end_tech'\n vars['rb_error'] = str(_e)[:200]\n") % repr(_no_double_braces(pj))
        out = minify(src) + "\n" + tail
    if "{{" in out or "}}" in out:
        raise ValueError("decide code would contain double braces")
    if len(out.encode("utf-8")) > CODE_BUDGET:
        raise ValueError("decide code is %d bytes, over the %d budget (platform limit %d incl. variables)"
                         % (len(out.encode("utf-8")), CODE_BUDGET, LIMIT))
    return out


def runtime_hash():
    return hashlib.sha256(RUNTIME.read_bytes()).hexdigest()[:12]
