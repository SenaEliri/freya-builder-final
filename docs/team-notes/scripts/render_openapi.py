"""Render selected OpenAPI operations as compact Markdown. Usage: render_openapi.py spec.json out.md path1 path2 ..."""
import json, sys

def typ(s):
    if not isinstance(s, dict): return '?'
    t = s.get('type')
    if isinstance(t, list): t = '|'.join(map(str, t))
    if 'anyOf' in s or 'oneOf' in s:
        alts = s.get('anyOf') or s.get('oneOf')
        return ' | '.join(typ(a) for a in alts)
    if t == 'array':
        return 'array<' + typ(s.get('items', {})) + '>'
    if t is None and 'properties' in s: t = 'object'
    if t is None and 'enum' in s: t = 'enum'
    if t is None and 'const' in s: t = 'const'
    fmt = s.get('format')
    return (t or 'any') + (f'({fmt})' if fmt else '')

def walk(s, prefix, req, depth, out, maxdepth):
    if not isinstance(s, dict) or depth > maxdepth: return
    for key in ('anyOf', 'oneOf', 'allOf'):
        if key in s:
            for i, alt in enumerate(s[key]):
                if isinstance(alt, dict) and (alt.get('properties') or alt.get('items')):
                    walk(alt, prefix + (f' [{key}#{i}]' if key != 'allOf' else ''), set(alt.get('required', [])), depth, out, maxdepth)
    props = s.get('properties') or {}
    for name, p in props.items():
        if not isinstance(p, dict): continue
        path = f'{prefix}.{name}' if prefix else name
        bits = [f'`{path}`', typ(p)]
        if name in req: bits.append('**required**')
        if 'enum' in p: bits.append('enum=' + json.dumps(p['enum']))
        if 'const' in p: bits.append('const=' + json.dumps(p['const']))
        if 'default' in p: bits.append('default=' + json.dumps(p['default'])[:80])
        for k in ('minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems', 'pattern'):
            if k in p: bits.append(f'{k}={p[k]}')
        d = (p.get('description') or '').replace('\n', ' ').strip()
        if d: bits.append('— ' + d[:400])
        out.append('- ' + ' '.join(bits))
        if p.get('type') == 'object' or 'properties' in p or any(k in p for k in ('anyOf', 'oneOf', 'allOf')):
            walk(p, path, set(p.get('required', [])), depth + 1, out, maxdepth)
        if p.get('type') == 'array' and isinstance(p.get('items'), dict):
            walk(p['items'], path + '[]', set(p['items'].get('required', [])), depth + 1, out, maxdepth)

def result_schema(resp):
    try:
        sch = resp['content']['application/json']['schema']
    except Exception:
        return None
    try:
        return sch['properties']['data']['properties']['result']
    except Exception:
        return sch

def render(spec, path, method, op, maxdepth=5):
    out = [f'### `{method.upper()} /api/v2{path}` — {op.get("summary", "")}', '']
    if op.get('description'): out += [op['description'].strip(), '']
    params = op.get('parameters') or []
    if params:
        out.append('**Parameters**')
        for p in params:
            sch = p.get('schema', {})
            bits = [f'`{p.get("name")}`', f'({p.get("in")})', typ(sch)]
            if p.get('required'): bits.append('**required**')
            if 'enum' in sch: bits.append('enum=' + json.dumps(sch['enum']))
            if 'default' in sch: bits.append('default=' + json.dumps(sch['default']))
            for k in ('minimum', 'maximum'):
                if k in sch: bits.append(f'{k}={sch[k]}')
            d = (p.get('description') or sch.get('description') or '').replace('\n', ' ').strip()
            if d: bits.append('— ' + d[:300])
            out.append('- ' + ' '.join(bits))
        out.append('')
    rb = op.get('requestBody')
    if rb:
        for ctype, c in (rb.get('content') or {}).items():
            sch = c.get('schema', {})
            out.append(f'**Request body** ({ctype})')
            lines = []
            walk(sch, '', set(sch.get('required', [])), 0, lines, maxdepth)
            out += lines or ['- (no properties listed) ' + json.dumps(sch)[:300]]
            out.append('')
    for code, resp in (op.get('responses') or {}).items():
        if not str(code).startswith('2'):
            continue
        rs = result_schema(resp)
        out.append(f'**Response {code}** — {resp.get("description", "")} (fields of `data.result`)')
        if rs:
            lines = []
            if rs.get('type') == 'array' and isinstance(rs.get('items'), dict):
                lines.append('- result is ' + typ(rs))
                walk(rs['items'], '[]', set(rs['items'].get('required', [])), 0, lines, maxdepth)
            else:
                walk(rs, '', set(rs.get('required', [])), 0, lines, maxdepth)
            out += lines or ['- ' + json.dumps(rs)[:300]]
        out.append('')
    errs = [f'{c}: {r.get("description","")}' for c, r in (op.get('responses') or {}).items() if not str(c).startswith('2')]
    if errs: out += ['**Errors**: ' + '; '.join(errs), '']
    return '\n'.join(out)

if __name__ == '__main__':
    spec = json.load(open(sys.argv[1]))
    out = []
    for path in sys.argv[3:]:
        for m, op in (spec['paths'].get(path) or {}).items():
            if m in ('get', 'post', 'put', 'patch', 'delete'):
                out.append(render(spec, path, m, op))
    open(sys.argv[2], 'w').write('\n'.join(out))
    print('wrote', sys.argv[2], sum(len(x) for x in out))
