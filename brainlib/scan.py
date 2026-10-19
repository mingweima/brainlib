"""Scan the library: build the index, the agent reading guide (llms.txt) and reports.

Scanning never modifies notes. Missing metadata is inferred and marked as inferred.
Private notes are counted but never listed in any output.
"""

import os
import re
import urllib.parse
from datetime import timedelta
from pathlib import Path

from . import __version__, frontmatter, privacy
from .config import AUTHORITIES, AUTHORITY_ALIASES, TIERS
from .util import now_iso, parse_date, read_json, today, write_json, atomic_write

NOTE_SUFFIXES = (".md", ".markdown")
_MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_WIKI_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_DATE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}")
_STREAM_DIRS = {"journal", "journals", "daily", "diary", "log", "logs", "dailies"}


def looks_like_stream(rel, zone):
    """Journal-like notes: anything in a `stream: true` zone, or a date-named file in a journal folder."""
    parent = Path(rel).parent.name.lower()
    return bool(zone.get("stream")) or (bool(_DATE_NAME.match(Path(rel).name)) and parent in _STREAM_DIRS)


def iter_notes(lib):
    """Yield note paths (posix, relative to the library root), sorted, skipping ignored ones."""
    root = lib.root
    out = []
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and not lib.is_ignored(rel_dir + d + "/")
        )
        for fn in filenames:
            if not fn.lower().endswith(NOTE_SUFFIXES) or fn.startswith("."):
                continue
            rel = rel_dir + fn
            full = Path(dirpath) / fn
            if full.is_symlink():
                try:
                    full.resolve().relative_to(root)
                except ValueError:
                    continue
            if lib.is_ignored(rel):
                continue
            out.append(rel)
    return sorted(out)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return [p.strip() for p in str(value).split(",") if p.strip()]


def _first_heading(body):
    for line in body.splitlines():
        m = re.match(r"^#\s+(.+?)\s*#*\s*$", line)
        if m:
            return m.group(1).strip()
    return None


def _first_paragraph(body, limit=160):
    para = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            if para:
                break
            continue
        if s.startswith(("#", "---", "```", "|", "<!--")) or re.match(r"^[-*_]{3,}$", s):
            if para:
                break
            continue
        s = re.sub(r"^[>\-*+]\s+|^\d+\.\s+", "", s)
        para.append(s)
    text = " ".join(para)
    text = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]", "", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text or None


def _normalize_verified(value):
    if not value:
        return None
    items = value if isinstance(value, list) else [value]
    best = None
    for item in items:
        if isinstance(item, dict):
            at = parse_date(item.get("at"))
            rec = {"by": item.get("by"), "at": at.isoformat() if at else None}
        else:
            at = parse_date(item)
            rec = {"by": None, "at": at.isoformat() if at else None}
        if rec["at"] and (best is None or rec["at"] > best["at"]):
            best = rec
    return best


def _extract_links(body):
    md = []
    for m in _MD_LINK.finditer(body):
        target = m.group(1).strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
            continue
        target = urllib.parse.unquote(target.split("#", 1)[0])
        if target:
            md.append(target)
    wiki = [m.group(1).strip() for m in _WIKI_LINK.finditer(body)]
    return md, wiki


def build_entry(lib, rel, text, mtime):
    fm, body, errors, has_fm = frontmatter.read(text)
    zone = lib.zone_for(rel)
    inferred = []
    t = today()

    title = fm.get("title") or _first_heading(body)
    if not title:
        title = Path(rel).stem.replace("-", " ").replace("_", " ").strip()
        inferred.append("title")
    elif not fm.get("title"):
        inferred.append("title")

    description = fm.get("description")
    if not description:
        description = _first_paragraph(body)
        inferred.append("description")

    stream = looks_like_stream(rel, zone)

    authority = str(fm.get("authority") or zone.get("authority") or "canonical").strip()
    authority = AUTHORITY_ALIASES.get(authority, authority).lower()
    if not fm.get("authority"):
        inferred.append("authority")

    updated = parse_date(fm.get("updated"))
    if updated is None and isinstance(fm.get("generated"), dict):
        updated = parse_date(fm["generated"].get("at"))
    if updated is None:
        named = parse_date(Path(rel).name[:10]) if stream and _DATE_NAME.match(Path(rel).name) else None
        updated = named or parse_date(_mtime_date(mtime))
        inferred.append("updated")

    tier = fm.get("tier") or zone.get("tier")
    if not tier:
        inferred.append("tier")
        if authority == "archived":
            tier = "L3"
        elif stream and updated and (t - updated).days > int(lib.config.get("stream_days") or 14):
            tier = "L3"
        elif Path(rel).name.lower() in ("readme.md", "index.md") and "/" not in rel:
            tier = "L1"
        else:
            tier = "L2"
    tier = str(tier).upper().strip()

    note_type = fm.get("type")
    if not note_type:
        note_type = "Journal" if stream else "Note"
        inferred.append("type")

    sensitivity = privacy.resolve_sensitivity(fm, zone)

    stale_after = parse_date(fm.get("stale_after"))
    if stale_after is None:
        ttl = fm.get("ttl")
        if ttl is None:
            ttl = (lib.config.get("ttl_days") or {}).get(tier, 0)
        try:
            ttl = int(ttl)
        except (TypeError, ValueError):
            ttl = 0
        if ttl > 0 and updated:
            stale_after = updated + timedelta(days=ttl)
    verified = _normalize_verified(fm.get("verified"))
    stale = bool(stale_after and t > stale_after and authority == "canonical" and not stream)

    md_links, wiki_links = _extract_links(body)
    return {
        "path": rel,
        "title": str(title),
        "type": str(note_type),
        "description": str(description) if description else None,
        "read_when": _as_list(fm.get("read_when")),
        "tags": _as_list(fm.get("tags")),
        "tier": tier,
        "authority": authority,
        "owner": fm.get("owner"),
        "updated": updated.isoformat() if updated else None,
        "verified": verified,
        "stale_after": stale_after.isoformat() if stale_after else None,
        "stale": stale,
        "stream": stream,
        "sensitivity": sensitivity,
        "has_front_matter": has_fm,
        "inferred": inferred,
        "bytes": len(text.encode("utf-8")),
        "lines": text.count("\n") + 1,
        "_md_links": md_links,
        "_wiki_links": wiki_links,
        "_fm_errors": errors,
        "_fm": fm,
    }


def _mtime_date(mtime):
    from datetime import datetime

    return datetime.fromtimestamp(mtime).date().isoformat()


def _resolve_links(entries):
    by_path = {e["path"] for e in entries}
    by_stem = {}
    for e in entries:
        stem = Path(e["path"]).with_suffix("").as_posix().lower()
        by_stem.setdefault(Path(stem).name, []).append(e["path"])
        by_stem.setdefault(stem, []).append(e["path"])
    broken = []
    for e in entries:
        links = []
        base = Path(e["path"]).parent
        for target in e["_md_links"]:
            norm = os.path.normpath((base / target).as_posix()).replace("\\", "/")
            if norm.startswith("../") or norm == "..":
                broken.append({"from": e["path"], "target": target})
                continue
            if norm in by_path or (norm + ".md") in by_path:
                links.append(norm if norm in by_path else norm + ".md")
            elif not norm.lower().endswith(NOTE_SUFFIXES) and Path(norm).suffix:
                continue  # attachments such as images are not checked in v0.1
            else:
                broken.append({"from": e["path"], "target": target})
        for target in e["_wiki_links"]:
            key = target.lower().replace("\\", "/")
            key = key[:-3] if key.endswith(".md") else key
            hit = by_stem.get(key)
            if hit:
                links.append(hit[0])
            else:
                broken.append({"from": e["path"], "target": "[[%s]]" % target})
        e["links"] = sorted(set(links))
    return broken


def scan_library(lib, write=True):
    """Scan every note. Returns the full scan result (including private entries in memory only)."""
    entries = []
    for rel in iter_notes(lib):
        full = lib.root / rel
        try:
            raw = full.read_bytes()
            mtime = full.stat().st_mtime
        except OSError:
            continue
        try:
            text, not_utf8 = raw.decode("utf-8"), False
        except UnicodeDecodeError:
            text, not_utf8 = raw.decode("utf-8", "replace"), True
        e = build_entry(lib, rel, text, mtime)
        if not_utf8:
            e["not_utf8"] = True
        e["_secret_hits"] = [h.as_dict() for h in privacy.scan_text(text, kinds=("secret",))]
        entries.append(e)
    broken = _resolve_links(entries)
    reports = _reports(lib, entries, broken)
    result = {
        "generated_at": now_iso(),
        "brainlib_version": __version__,
        "library": lib.name,
        "entries": entries,
        "reports": reports,
    }
    if write:
        write_outputs(lib, result)
    return result


def _reports(lib, entries, broken):
    t = today()
    public = [e for e in entries if privacy.is_readable_by_agents(e["sensitivity"])]
    private_paths = {e["path"] for e in entries if not privacy.is_readable_by_agents(e["sensitivity"])}
    reports = {
        "broken_links": [b for b in broken if b["from"] not in private_paths],
        "stale": [e["path"] for e in public if e["stale"]],
        "missing_meta": [
            e["path"]
            for e in public
            if e["tier"] in ("L0", "L1") and ("description" in e["inferred"] or not e["read_when"])
        ],
        "future_dates": [
            e["path"] for e in public if e["updated"] and parse_date(e["updated"]) > t + timedelta(days=1)
        ],
        "not_utf8": [e["path"] for e in public if e.get("not_utf8")],
        "invalid_values": [],
        "frontmatter_errors": [],
        "conflicts": [],
        "secrets_in_library": [],
        # Counts only: even the names of private notes stay out of agent-facing outputs.
        "private_plaintext": sum(1 for e in entries if e["sensitivity"] == "private"),
        "secret_level_files": sum(1 for e in entries if e["sensitivity"] == "secret"),
    }
    for e in entries:
        hidden = e["path"] in private_paths
        where = "(a private note)" if hidden else e["path"]
        if e["tier"] not in TIERS:
            reports["invalid_values"].append({"path": where, "field": "tier", "value": e["tier"]})
        if e["authority"] not in AUTHORITIES:
            reports["invalid_values"].append({"path": where, "field": "authority", "value": e["authority"]})
        raw_s = (e["_fm"] or {}).get("sensitivity")
        if raw_s and str(raw_s).lower() not in ("public", "internal", "private", "secret"):
            reports["invalid_values"].append({"path": where, "field": "sensitivity", "value": raw_s})
        for err in e["_fm_errors"]:
            reports["frontmatter_errors"].append({"path": where, "error": err})
        for h in e["_secret_hits"]:
            reports["secrets_in_library"].append(
                {"path": where, "line": None if hidden else h["line"], "rule": h["rule"]}
            )
    seen = {}
    for e in public:
        if e["authority"] != "canonical":
            continue
        key = (str(Path(e["path"]).parent), e["title"].strip().lower())
        seen.setdefault(key, []).append(e["path"])
    for (_d, title), paths in seen.items():
        if len(paths) > 1:
            reports["conflicts"].append({"title": title, "paths": sorted(paths)})
    return reports


def public_entry(e):
    return {k: v for k, v in e.items() if not k.startswith("_")}


def write_outputs(lib, result):
    entries = result["entries"]
    visible = [public_entry(e) for e in entries if privacy.is_readable_by_agents(e["sensitivity"])]
    hidden = len(entries) - len(visible)
    index = {
        "schema": "brainlib/index@0.1",
        "generated_at": result["generated_at"],
        "brainlib_version": result["brainlib_version"],
        "library": result["library"],
        "count": len(visible),
        "private_hidden": hidden,
        "notes": visible,
    }
    write_json(lib.out("index.json"), index)
    reports = dict(result["reports"])
    reports["schema"] = "brainlib/reports@0.1"
    reports["generated_at"] = result["generated_at"]
    reports["contains_content"] = False
    write_json(lib.out("reports.json"), reports)
    atomic_write(lib.out("llms.txt"), render_guide(lib, visible, hidden, result["generated_at"]), private=True)
    newest = 0.0
    for e in entries:
        try:
            newest = max(newest, (lib.root / e["path"]).stat().st_mtime)
        except OSError:
            pass
    write_json(lib.out("scan-meta.json"), {"generated_at": result["generated_at"], "newest_mtime": newest, "notes": len(entries)})


def render_guide(lib, visible, hidden, generated_at):
    lines = [
        "# %s: reading guide for AI agents" % lib.name,
        "",
        "Generated by brainlib %s at %s. This is a derived file; do not edit it. Run `brainlib scan` to rebuild." % (__version__, generated_at),
        "This guide is curated, not complete. If something is not listed here, it may still be in the library: use `brainlib find \"<topic>\"`.",
    ]
    if hidden:
        lines.append("%d private note(s) are hidden from every agent-facing list." % hidden)
    lines.append("")

    def fmt(e):
        s = "- [%s](%s)" % (e["title"], e["path"])
        if e.get("description"):
            s += ": %s" % e["description"]
        if e.get("read_when"):
            s += " (read when: %s)" % "; ".join(e["read_when"])
        return s

    canon = [e for e in visible if e["authority"] == "canonical"]
    core = [e for e in canon if e["tier"] == "L0"]
    entry = [e for e in canon if e["tier"] == "L1"]
    if core:
        lines.append("## Core pages (L0): read these before acting for the user")
        lines.extend(fmt(e) for e in core)
        lines.append("")
    if entry:
        lines.append("## Entry pages (L1)")
        lines.extend(fmt(e) for e in entry)
        lines.append("")
    if not core:
        lines.append("No core pages (L0) are marked yet. Ask the user which few notes matter most, then propose adding `tier: L0` to them.")
        lines.append("")
        recent = sorted(
            (e for e in canon if e["tier"] in ("L1", "L2")), key=lambda e: e.get("updated") or "", reverse=True
        )[:30]
        if recent:
            lines.append("## Recently updated notes")
            lines.extend(fmt(e) for e in recent)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_index(lib, refresh_if_stale=True):
    """Return the index dict, rescanning when it is missing or older than the newest note."""
    index = read_json(lib.out("index.json"))
    if index is None or (refresh_if_stale and is_stale(lib)):
        scan_library(lib, write=True)
        index = read_json(lib.out("index.json"))
    return index


def is_stale(lib):
    meta = read_json(lib.out("scan-meta.json"))
    if not meta:
        return True
    newest = 0.0
    count = 0
    for rel in iter_notes(lib):
        count += 1
        try:
            newest = max(newest, (lib.root / rel).stat().st_mtime)
        except OSError:
            pass
    return newest > float(meta.get("newest_mtime") or 0) + 0.001 or count != meta.get("notes")


# --- search -----------------------------------------------------------------

def _tokens(text):
    text = (text or "").lower()
    words = set(re.findall(r"[a-z0-9][a-z0-9_-]{1,}", text))
    cjk = re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+", text)
    for run in cjk:
        if len(run) == 1:
            words.add(run)
        for i in range(len(run) - 1):
            words.add(run[i:i + 2])
    return words


# Words that say nothing about the topic, including how people ask an agent to remember
# something. Matching on them sends "I only drink tea in the morning" to whichever note
# happens to contain "in".
STOPWORDS = frozenset(
    (
        "about after again all also am an and any are as at be been before being both but by can could did do does "
        "doing for from had has have having he her here hers him his how if in into is it its just me more most my "
        "no nor not now of off on once only or other our out over own please same she should so some such than that "
        "the their them then there these they this those through to too under until up us very was we were what "
        "when where which while who whom why will with would you your remember"
    ).split()
    + "这个 那个 这些 那些 什么 怎么 一下 一个 我们 你们 他们 的时 时候 之前 之后 不是 就是 还是 可以 没有 已经 "
    "因为 所以 如果 但是 然后 帮我 记一 记住 记得 我的 你的 一些 有点".split()
)


def _content_tokens(text, fallback=True):
    """Topic words only. With fallback, a text made only of stopwords keeps all its words."""
    words = _tokens(text)
    return (words - STOPWORDS) or (words if fallback else set())


def find(lib, query, limit=10):
    """Rank visible notes for a task or topic. Never returns private notes."""
    index = load_index(lib)
    q = _content_tokens(query)
    if not q:
        return []
    results = []
    for e in index["notes"]:
        score = 0.0
        score += 3 * len(q & _tokens(" ".join(e.get("read_when") or [])))
        score += 2 * len(q & _tokens(e.get("title")))
        score += 2 * len(q & _tokens(" ".join(e.get("tags") or [])))
        score += 1.5 * len(q & _tokens(e.get("description")))
        score += 1 * len(q & _tokens(e.get("path")))
        if score <= 0:
            continue
        if e["tier"] == "L0":
            score += 1
        if e["authority"] == "archived":
            score -= 1
        results.append((score, e))
    if len(results) < limit:
        seen = {e["path"] for _, e in results}
        for e in index["notes"]:
            if e["path"] in seen:
                continue
            try:
                body = (lib.root / e["path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits = len(q & _tokens(body))
            if hits:
                results.append((0.5 * hits, e))
    results.sort(key=lambda x: (-x[0], x[1]["path"]))
    return [dict(e, score=round(s, 2)) for s, e in results[:limit]]


def find_noted(lib, query, limit=5):
    """Inbox items that match the query but are not in any note yet (newest first among equals)."""
    from . import inbox

    q = _content_tokens(query)
    if not q:
        return []
    hits = []
    for it in inbox.not_filed_for_agents(lib):
        n = len(q & _tokens(it["text"]))
        if n:
            hits.append((n, it))
    hits.sort(key=lambda x: -x[0])
    return [
        {"id": it["id"], "line": inbox.describe(it), "provenance": it["provenance"], "status": it["status"]}
        for _n, it in hits[:limit]
    ]
