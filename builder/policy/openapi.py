"""Read the bank's tool API file (OpenAPI 3) into a compact, deterministic tool spec.

Nothing here is brief-specific: names, URLs, fields and enums all come from the file.
"""
import json

TOOL_NAMES = ("verify_identity", "get_account", "create_promise", "add_note",
              "schedule_callback", "transfer_to_agent", "close_call")


def _schema(op):
    try:
        return op["requestBody"]["content"]["application/json"]["schema"]
    except (KeyError, TypeError):
        return {}


def _resp_schema(op):
    for code in ("200", 200):
        try:
            return op["responses"][code]["content"]["application/json"]["schema"]
        except (KeyError, TypeError):
            continue
    return {}


def _props(schema):
    out = {}
    for name, p in (schema.get("properties") or {}).items():
        if not isinstance(p, dict):
            continue
        item = {"type": p.get("type") or "string"}
        for k in ("enum", "description", "format"):
            if k in p:
                item[k] = p[k]
        if p.get("type") == "array" and isinstance(p.get("items"), dict):
            item["items"] = _props(p["items"])
        out[name] = item
    return out


def load(path):
    spec = json.load(open(path, encoding="utf-8"))
    servers = spec.get("servers") or []
    if not servers or not servers[0].get("url"):
        raise ValueError("tool API file has no servers[0].url")
    base = servers[0]["url"].rstrip("/")
    tools = {}
    for p, ops in (spec.get("paths") or {}).items():
        op = (ops or {}).get("post") or (ops or {}).get("get")
        if not op:
            continue
        name = p.strip("/").split("/")[-1]
        req = _schema(op)
        tools[name] = {
            "name": name,
            "url": base + p,
            "method": "POST" if "post" in ops else "GET",
            "summary": op.get("summary", ""),
            "fields": _props(req),
            "required": list(req.get("required") or []),
            "response": _props(_resp_schema(op)),
        }
    missing = [t for t in TOOL_NAMES if t not in tools]
    if missing:
        raise ValueError("tool API file lacks tools: %s" % ", ".join(missing))
    from builder.policy import roles
    api, problems = roles.resolve({"tools": tools})
    out = {"title": (spec.get("info") or {}).get("title", ""), "description": (spec.get("info") or {}).get("description", ""),
           "base_url": base, "tools": tools, "api": api, "api_problems": problems}
    out["enums"] = enums(out)
    return out


def _enum(tools, tool, field):
    f = tools.get(tool, {}).get("fields", {}).get(field) or {}
    return list(f.get("enum") or [])


def enums(spec):
    """Allowed values, read through the role mapping (field names may differ from the public tool API)."""
    t = spec["tools"]
    api = spec.get("api") or {}

    def req(tool, role):
        return (api.get(tool) or {}).get("req", {}).get(role, role)

    def resp(tool, role):
        return (api.get(tool) or {}).get("resp", {}).get(role, role)
    products = (t["get_account"]["response"].get(resp("get_account", "products")) or {}).get("items") or {}
    type_field = ((api.get("get_account") or {}).get("item") or {}).get("type", "type")
    return {
        "identity_fields": _enum(t, "verify_identity", req("verify_identity", "field")),
        "hints": list(((t["verify_identity"]["response"].get(resp("verify_identity", "hint")) or {}).get("enum")) or []),
        "product_types": list(((products.get(type_field) or {}).get("enum")) or []),
        "product_fields": sorted(products.keys()),
        "note_reasons": _enum(t, "add_note", req("add_note", "reason")),
        "queues": _enum(t, "transfer_to_agent", req("transfer_to_agent", "queue")),
        "outcomes": _enum(t, "close_call", req("close_call", "outcome")),
    }


def field_descriptions(spec):
    """Every field description in the file, for the policy extractor's context."""
    lines = []
    for name, tool in spec["tools"].items():
        lines.append("%s: %s" % (name, tool.get("summary", "")))
        for f, d in tool["fields"].items():
            extra = (" enum=%s" % d["enum"]) if d.get("enum") else ""
            lines.append("  request.%s (%s)%s %s" % (f, d.get("type"), extra, d.get("description", "")))
        for f, d in tool["response"].items():
            extra = (" enum=%s" % d["enum"]) if d.get("enum") else ""
            lines.append("  response.%s (%s)%s %s" % (f, d.get("type"), extra, d.get("description", "")))
            for sf, sd in (d.get("items") or {}).items():
                extra = (" enum=%s" % sd["enum"]) if sd.get("enum") else ""
                lines.append("    response.%s[].%s (%s)%s %s" % (f, sf, sd.get("type"), extra, sd.get("description", "")))
    return "\n".join(lines)
