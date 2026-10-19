"""Classify: turn pending inbox items into proposals. Never edits notes directly.

Backends
- rules (default, no AI needed): match each item to the existing note whose title,
  read_when, tags, description and path share the most words with it; items that match
  nothing go to the fallback note (inbox-unsorted.md by default).
- command: send a JSON request to any program you choose (a local model, a script) and
  read JSON back. Invalid answers are retried once, then the rules backend takes over.
"""

import json
import re
import subprocess

from . import inbox, onboard, privacy, proposals, provenance
from .scan import _content_tokens, _tokens, load_index
from .util import BrainError, new_id, now_iso, today_str, write_json

THRESHOLD = 3.0
WEIGHTS = (("title", 3.0), ("read_when", 3.0), ("tags", 2.0), ("description", 1.0), ("path", 1.0))


def _fields(note):
    return {
        "title": _tokens(note.get("title")),
        "read_when": _tokens(" ".join(note.get("read_when") or [])),
        "tags": _tokens(" ".join(note.get("tags") or [])),
        "description": _tokens(note.get("description")),
        "path": _tokens(note.get("path", "").replace("/", " ").replace("-", " ").replace("_", " ")),
    }


def _usable_suggestion(lib, target, writable):
    """An agent's suggested target counts if it is a readable note, or a new note the policy allows."""
    if target in writable:
        return True
    if (lib.root / target).exists():
        return False
    try:
        proposals.target_info(lib, target)
    except BrainError:
        return False
    return True


def best_target(candidates, text):
    q = _content_tokens(text, fallback=False)
    best, best_score, best_words = None, 0.0, []
    for note, fields in candidates:
        score = 0.0
        words = set()
        for name, w in WEIGHTS:
            common = q & fields[name]
            score += w * len(common)
            words |= common
        if note["tier"] == "L0":
            score -= 1.0
        if score > best_score:
            best, best_score, best_words = note, score, sorted(words)
    if best_score >= THRESHOLD:
        return best["path"], best_score, best_words[:5]
    return None, best_score, []


def format_line(item):
    date = (item.get("said_at") or item.get("captured_at") or now_iso())[:10]
    src = (item.get("source") or {}).get("ref")
    mark = provenance.marker(item["provenance"], date=date, source=src)
    text = re.sub(r"\s+", " ", item["text"]).strip()
    return "- %s %s" % (mark, text)


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _command_assignments(lib, cmd, items, notes):
    request = {
        "schema": "brainlib/classify-request@0.1",
        "instructions": (
            "For each item choose the single best existing note path from `notes`, or null if none fits. "
            "Reply with JSON only: {\"assignments\": [{\"item\": <id>, \"target\": <path or null>}]}."
        ),
        "items": [{"id": i["id"], "text": i["text"], "provenance": i["provenance"]} for i in items],
        "notes": [
            {k: n.get(k) for k in ("path", "title", "description", "read_when", "tags")} for n in notes
        ],
    }
    valid_paths = {n["path"] for n in notes}
    for _attempt in range(2):
        try:
            res = subprocess.run(
                cmd,
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            data = json.loads(res.stdout)
            out = {}
            for a in data.get("assignments") or []:
                t = a.get("target")
                if a.get("item") and (t is None or t in valid_paths):
                    out[a["item"]] = t
            if out:
                return out
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    return None


def run(lib, actor="agent/unknown", limit=200, dry_run=False):
    settings = onboard.settings(lib)
    proposals.require_not_read_only(settings)
    items = [i for i in inbox.all_items(lib) if i["status"] == "pending" and i.get("text")]
    held = [i for i in items if not onboard.allows_provenance(settings, i["provenance"])]
    items = [i for i in items if onboard.allows_provenance(settings, i["provenance"])][:limit]
    summary = {"items": len(items), "held_by_record_policy": len(held), "proposals": [], "duplicates": 0, "auto_applied": 0}
    if not items:
        return summary

    index = load_index(lib)
    notes = [
        n
        for n in index["notes"]
        if n["authority"] == "canonical"
        and not n.get("stream")
        and not n.get("not_utf8")
        and privacy.is_readable_by_agents(n["sensitivity"])
    ]
    candidates = [(n, _fields(n)) for n in notes]
    fallback = lib.config.get("fallback_note") or "inbox-unsorted.md"

    assigned = None
    backend = (lib.config.get("classifier") or {}).get("backend", "rules")
    if backend == "command":
        cmd = (lib.config.get("classifier") or {}).get("command")
        if cmd:
            assigned = _command_assignments(lib, cmd, items, notes)
    if assigned is None:
        backend = "rules"

    writable = {
        n["path"]
        for n in index["notes"]
        if n["authority"] != "archived" and not n.get("not_utf8") and privacy.is_readable_by_agents(n["sensitivity"])
    }
    groups = {}
    for it in items:
        target, score, words = None, 0.0, []
        sug = (it.get("suggest") or {}).get("target")
        if sug and _usable_suggestion(lib, sug, writable):
            target, words = sug, ["suggested by the agent"]
        elif assigned is not None and it["id"] in assigned:
            target = assigned[it["id"]]
        else:
            target, score, words = best_target(candidates, it["text"])
        target = target or fallback
        body = ""
        full = lib.root / target
        if full.is_file():
            body = full.read_text(encoding="utf-8", errors="replace")
        if _norm(it["text"]) and _norm(it["text"]) in _norm(body):
            summary["duplicates"] += 1
            if not dry_run:
                inbox.set_status(lib, it["id"], "duplicate")
            continue
        g = groups.setdefault(target, {"items": [], "words": set()})
        g["items"].append(it)
        g["words"].update(w for w in words if w != "suggested by the agent")

    batch = new_id("B")
    for target, g in groups.items():
        content = "\n".join(format_line(i) for i in g["items"])
        n = len(g["items"])
        if target == fallback:
            reason = "%d inbox item(s) did not clearly fit any note, so they are parked here for the user to sort." % n
        else:
            reason = "%d inbox item(s) seem to belong in this note" % n
            if g["words"]:
                reason += " (shared words: %s)" % ", ".join(sorted(g["words"])[:5])
            reason += "."
        if dry_run:
            summary["proposals"].append({"target": target, "items": n, "reason": reason, "content": content})
            continue
        try:
            p = proposals.create(
                lib,
                "append",
                target,
                content,
                reason,
                actor=actor,
                evidence=[{"item": i["id"], "provenance": i["provenance"]} for i in g["items"]],
            )
        except BrainError as e:
            summary.setdefault("errors", []).append({"target": target, "error": e.message})
            continue
        for i in g["items"]:
            inbox.set_status(lib, i["id"], "proposed", ref=p["id"])
        summary["proposals"].append({"id": p["id"], "target": target, "items": n, "approval": p["approval"]})

    if not dry_run:
        write_json(
            lib.state("batches", "%s.json" % batch),
            {"batch": batch, "at": now_iso(), "backend": backend, "summary": summary, "contains_content": False},
        )
        if any(p.get("approval") == "auto" for p in summary["proposals"]):
            done, failed = proposals.apply_auto(lib, actor=actor)
            summary["auto_applied"] = len(done)
            if failed:
                summary.setdefault("errors", []).extend(failed)
    summary["backend"] = backend
    return summary
