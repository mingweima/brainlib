"""Minimal YAML front matter reader for Markdown notes. Standard library only.

Supports the subset people actually write in note headers:

    key: value              strings, numbers, true/false, null (dates stay strings)
    key: [a, b, "c d"]      flow lists
    key: {by: x, at: y}     flow mappings
    key:                    block list of scalars or mappings
      - item
      - {id: s1, resource: "x"}
    key:                    one-level nested mapping
      sub: value
    key: |                  literal block (also >)
      text

Unknown keys are kept as they are. Parsing never raises: problems come back as a list of
error strings, so one odd header never stops a scan of the whole library.
"""

import json
import re

_KEY_RE = re.compile(r"^([^\s:#\-][^:]*?)\s*:(?:\s+(.*)|\s*)$")


def split(text):
    """Return (front_matter_text_or_None, body, errors)."""
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text, []
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            fm = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            return fm, body, []
    return None, text, ["front matter starts with --- but never closes"]


def read(text):
    """Return (data, body, errors, has_front_matter)."""
    fm, body, errors = split(text)
    if fm is None:
        return {}, body, errors, False
    data, perrors = parse(fm)
    return data, body, errors + perrors, True


def _strip_comment(s):
    out = []
    quote = None
    prev = " "
    for ch in s:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and prev in " \t":
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _split_top(s, sep=","):
    parts, buf, depth, quote = [], [], 0, None
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def _split_pair(s):
    """Split 'key: value' at the first colon followed by a space (or at a trailing colon)."""
    m = re.match(r"^\s*([^:]+?)\s*:(?:\s+(.*)|\s*)$", s)
    if not m:
        return None, None
    return m.group(1).strip().strip("\"'"), (m.group(2) or "").strip()


def parse_scalar(s):
    s = s.strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return json.loads(s)
        except ValueError:
            return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(p) for p in _split_top(inner) if p != ""]
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        out = {}
        if inner:
            for part in _split_top(inner):
                if not part:
                    continue
                k, v = _split_pair(part)
                if k is None:
                    out[part] = None
                else:
                    out[k] = parse_scalar(v)
        return out
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if re.match(r"^-?\d+$", s) and len(s) < 16:
        return int(s)
    if re.match(r"^-?\d+\.\d+$", s):
        try:
            return float(s)
        except ValueError:
            return s
    return s


def _indent(line):
    return len(line) - len(line.lstrip(" \t"))


def parse(fm_text):
    """Parse front matter text into a dict. Returns (data, errors)."""
    data, errors = {}, []
    lines = fm_text.split("\n")
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i].rstrip("\r")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if _indent(raw) > 0:
            errors.append("line %d: unexpected indentation" % (i + 1))
            i += 1
            continue
        m = _KEY_RE.match(raw)
        if not m:
            errors.append("line %d: not a 'key: value' line" % (i + 1))
            i += 1
            continue
        key = m.group(1).strip().strip("\"'")
        value = _strip_comment(m.group(2) or "").strip()
        if key in data:
            errors.append("line %d: duplicate key '%s' (last one wins)" % (i + 1, key))
        i += 1
        if value in ("|", "|-", "|+", ">", ">-", ">+"):
            block = []
            while i < n and (not lines[i].strip() or _indent(lines[i]) > 0):
                block.append(lines[i].strip())
                i += 1
            while block and not block[-1]:
                block.pop()
            data[key] = (" " if value.startswith(">") else "\n").join(block)
            continue
        if value != "":
            data[key] = parse_scalar(value)
            continue
        # Empty value: maybe a nested block follows.
        j = i
        while j < n and not lines[j].strip():
            j += 1
        if j >= n or _indent(lines[j]) == 0:
            data[key] = None
            continue
        if lines[j].strip().startswith("- ") or lines[j].strip() == "-":
            items, i = _parse_block_list(lines, j)
            data[key] = items
        else:
            mapping, i = _parse_block_map(lines, j, errors)
            data[key] = mapping
    return data, errors


def _parse_block_list(lines, i):
    items = []
    n = len(lines)
    base = _indent(lines[i])
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        ind = _indent(line)
        if ind < base or (ind == base and not line.strip().startswith("-")) or ind == 0:
            break
        text = line.strip()
        if ind == base and text.startswith("-"):
            item_text = _strip_comment(text[1:].strip())
            i += 1
            k, v = _split_pair(item_text) if item_text and item_text[0] not in "[{\"'" else (None, None)
            if k is not None and not re.match(r"^https?$", k):
                item = {k: parse_scalar(v)}
                while i < n and lines[i].strip() and _indent(lines[i]) > base and not lines[i].strip().startswith("- "):
                    k2, v2 = _split_pair(_strip_comment(lines[i].strip()))
                    if k2 is not None:
                        item[k2] = parse_scalar(v2)
                    i += 1
                items.append(item)
            else:
                items.append(parse_scalar(item_text))
        else:
            i += 1
    return items, i


def _parse_block_map(lines, i, errors):
    mapping = {}
    n = len(lines)
    base = _indent(lines[i])
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _indent(line) < base or _indent(line) == 0:
            break
        k, v = _split_pair(_strip_comment(line.strip()))
        if k is None:
            errors.append("line %d: not a 'key: value' line inside a nested block" % (i + 1))
        else:
            mapping[k] = parse_scalar(v)
        i += 1
    return mapping, i


def _needs_quotes(s):
    if s == "" or s.strip() != s:
        return True
    if re.search(r":\s|\s#|^[\[\]{}&*!|>'\"%@`,?-]", s):
        return True
    if s in ("true", "false", "null", "~") or re.match(r"^-?\d+(\.\d+)?$", s):
        return True
    return False


def dump_scalar(v):
    if v is None:
        return ""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(dump_scalar(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join("%s: %s" % (k, dump_scalar(x)) for k, x in v.items()) + "}"
    s = str(v)
    return json.dumps(s, ensure_ascii=False) if _needs_quotes(s) else s


def dump(data):
    """Render a dict as front matter (without the --- fences)."""
    out = []
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
            out.append("%s:" % key)
            for item in value:
                out.append("  - " + dump_scalar(item))
        else:
            rendered = dump_scalar(value)
            out.append(("%s: %s" % (key, rendered)).rstrip())
    return "\n".join(out)


def render(data, body):
    """Return a full note text with front matter and body."""
    return "---\n%s\n---\n%s" % (dump(data), body if body.startswith("\n") else "\n" + body)
