"""Read a case folder: the text sources (dated where the file name says so) and the service contract in them.

Nothing here knows a particular bank or case. The contract parser looks for a markdown document that defines
services under headings of the form "### 5.1 `service.name`", each with a JSON request example, and a base
address in a code block.
"""
import json
import pathlib
import re
import urllib.parse

TEXT_SUFFIXES = (".md", ".txt")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[-_ ]?(.*)$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
SERVICE_HEAD_RE = re.compile(r"^(?:[\d.]+\s+)?`([A-Za-z][\w.\-]*)`$")


def read_sources(folder):
    """All text files, oldest first, undated last. Of dated files with the same name only the newest is kept."""
    folder = pathlib.Path(folder)
    docs, skipped = [], []
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        if f.suffix.lower() not in TEXT_SUFFIXES:
            skipped.append({"file": str(f.relative_to(folder)), "why": "not a text file"})
            continue
        m = DATE_RE.match(f.stem)
        docs.append({"path": str(f.relative_to(folder)), "date": m.group(1) if m else "", "stem": (m.group(2) if m else f.stem).lower(),
                     "text": f.read_text(encoding="utf-8", errors="replace")})
    newest = {}
    for d in docs:
        if d["date"] and d["date"] > newest.get(d["stem"], ""):
            newest[d["stem"]] = d["date"]
    kept = []
    for d in docs:
        if d["date"] and d["date"] < newest[d["stem"]]:
            skipped.append({"file": d["path"], "why": "an edition of the same document dated %s replaces it" % newest[d["stem"]]})
        else:
            kept.append(d)
    kept.sort(key=lambda d: (d["date"] == "", d["date"], d["path"]))
    return kept, skipped


def split_sections(text):
    """[(level, title, body)] by markdown heading."""
    out, cur = [], [0, "", []]
    fence = False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        m = None if fence else HEAD_RE.match(line)
        if m:
            out.append((cur[0], cur[1], "\n".join(cur[2])))
            cur = [len(m.group(1)), m.group(2), []]
        else:
            cur[2].append(line)
    out.append((cur[0], cur[1], "\n".join(cur[2])))
    return out


def _json_blocks(body):
    return re.findall(r"```(?:json)?\s*\n(.*?)```", body, re.S)


def _request_example(body):
    """The first JSON object in a code block that follows a line starting with 'Request'."""
    m = re.search(r"^\s*Request\b.*?$", body, re.M | re.I)
    for block in _json_blocks(body[m.end():] if m else body):
        try:
            v = json.loads(block)
        except Exception:
            continue
        if isinstance(v, dict):
            return v
    return None


def find_contract(docs):
    """The service contract among the sources, or None. Returns {path, base_path, method, services: [...]}."""
    best = None
    for d in docs:
        services = []
        for level, title, body in split_sections(d["text"]):
            m = SERVICE_HEAD_RE.match(title)
            if not m:
                continue
            example = _request_example(body)
            if example is None:
                continue
            prose = re.sub(r"```.*?```", "", body, flags=re.S)
            services.append({"name": m.group(1), "request_example": example, "notes": re.sub(r"\n{3,}", "\n\n", prose).strip()})
        if services and (best is None or len(services) > len(best["services"])):
            base = ""
            for block in re.findall(r"```\w*\s*\n(.*?)```", d["text"], re.S):
                if re.match(r"^https?://\S+$", block.strip()):
                    base = block.strip()
                    break
            method = "POST"
            for mth in ("POST", "GET", "PUT"):
                if re.search(r"\bevery service is `?%s`?" % mth, d["text"], re.I):
                    method = mth
                    break
            summaries = {}
            for row in re.findall(r"^\|[^|\n]*\|\s*`([A-Za-z][\w.\-]*)`\s*\|([^|\n]*)\|([^|\n]*)\|\s*$", d["text"], re.M):
                summaries.setdefault(row[0], "Called with: %s. Gives back: %s." % (row[1].strip(), row[2].strip()))
            for s in services:
                s["summary"] = summaries.get(s["name"], "")
            best = {"path": d["path"], "base_url": base, "base_path": urllib.parse.urlparse(base).path if base else "/",
                    "method": method, "services": services}
    return best


def tool_name(service):
    return re.sub(r"[^A-Za-z0-9]+", "_", service).strip("_")


def chunk(text, n):
    """Split at paragraph borders into parts of at most n characters."""
    out, cur = [], ""
    for para in re.split(r"(?<=\n)\n+", text):
        while len(para) > n:
            if cur.strip():
                out.append(cur)
                cur = ""
            cut = para.rfind("\n", 0, n)
            cut = cut if cut > n // 2 else n
            out.append(para[:cut])
            para = para[cut:]
        if len(cur) + len(para) + 1 > n and cur.strip():
            out.append(cur)
            cur = ""
        cur += para + "\n"
    if cur.strip():
        out.append(cur)
    return out
