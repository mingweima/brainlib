"""Classify: turn pending inbox items into proposals. Never edits notes directly.

Where an item goes
- The note the agent suggested (--target), if the policy allows it.
- Otherwise by category: "about me" goes to me.md, "decisions" to decisions.md (made on
  first use), "journal" and minor items only to the day's journal, and a folder name to
  the best note in that folder.
- Otherwise the rules backend matches the item to the regular note whose title,
  read_when, tags, description and path share the most words with it (entry pages,
  journals and archives are left out); items that match nothing go to the fallback note
  (inbox-unsorted.md by default).

Every item gets its own proposal, so the user can take some and leave others. Every item
is also written into the journal of the day it was said, in time order, one proposal per
day (turn this off with "daily_log": false). An item a note already holds leaves the note
alone and is only logged, as said again. An item with `replaces` becomes a replace-line
proposal that keeps a short trace of the old wording; one that merely looks like an older
line only gets a hint, because looking alike is not the same as changing one's mind.

Backends
- rules (default, no AI needed): as above.
- command: send a JSON request to any program you choose (a local model, a script) and
  read JSON back. Invalid answers are retried once, then the rules backend takes over.
"""

import json
import re
import subprocess
from pathlib import Path

from . import i18n, inbox, onboard, privacy, proposals, records
from .scan import _content_tokens, _tokens, load_index
from .util import BrainError, new_id, now_iso, read_json, write_json

THRESHOLD = 3.0
WEIGHTS = (("title", 3.0), ("read_when", 3.0), ("tags", 2.0), ("description", 1.0), ("path", 1.0))
DECISIONS_PAGE = {
    "zh": {
        "title": "决定",
        "description": "用户定下的事，一件一行，带说话时间；同一件事以最新的说法为准。",
        "read_when": ["要照用户定过的事办", "不确定用户以前怎么定的"],
    },
    "en": {
        "title": "Decisions",
        "description": "What the user decided, one line each with when it was said; the newest one counts.",
        "read_when": ["acting on something the user decided", "unsure what the user decided before"],
    },
}


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


def best_target(candidates, text, threshold=THRESHOLD):
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
    if best is not None and best_score >= threshold:
        return best["path"], best_score, best_words[:5]
    return None, best_score, []


def format_line(item, lang=None):
    """The line an inbox item becomes in a note, with its source label first."""
    return records.format_line(item, lang or i18n.DEFAULT_LANG)


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


def _read(lib, rel):
    full = lib.root / rel
    if not full.is_file():
        return ""
    return full.read_text(encoding="utf-8", errors="replace")


def _by_category(lib, it, tags, candidates):
    """A target from the item's category (or its low importance), or None to keep looking."""
    key = records.category_key(it.get("category"))
    if key == "me" and (lib.root / "me.md").is_file():
        return "me.md"
    if key == "decisions":
        return "decisions.md"
    if key == "journal" or (not it.get("category") and tags["importance"] == "low"):
        return records.journal_target(lib, tags["when"])
    if it.get("category") and not key:
        label = it["category"].strip().lower().rstrip("/")
        inside = [(n, f) for n, f in candidates if n["path"].lower().startswith(label + "/")]
        target, _score, _words = best_target(inside, it["text"], threshold=0.5)
        if target:
            return target
        for n, _f in candidates:
            if (n.get("title") or "").strip().lower() == label or Path(n["path"]).stem.lower() == label:
                return n["path"]
    return None


def _note_lines(text):
    """(line number, raw line, record or None) for every line that could hold a statement."""
    out = []
    in_header = False
    for n, line in enumerate(text.splitlines(), start=1):
        raw = line.rstrip("\r")
        if n == 1 and raw.strip() == "---":
            in_header = True
            continue
        if in_header:
            if raw.strip() in ("---", "..."):
                in_header = False
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        out.append((n, raw, records.parse_line(raw)))
    return out


def _said_already(text, item_text):
    """Line number where a note already says this, or None."""
    want = records.squash(item_text)
    if not want:
        return None
    for n, raw, rec in _note_lines(text):
        if rec:
            if records.squash(rec["text"]) == want:
                return n
        elif len(want) >= 4 and want in records.squash(raw):
            return n
    return None


def _find_replaced(lib, words, target, readable):
    """The line an item says it replaces: in its target first, then in any other regular note."""
    want = records.squash(words)
    if not want:
        return None
    order = [target] + sorted(p for p in readable if p != target)
    for path in order:
        if records.in_journal(lib, path):
            continue
        hits = []
        for n, raw, rec in _note_lines(_read(lib, path)):
            text = rec["text"] if rec else re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", raw).strip()
            if want in records.squash(text):
                hits.append((records.time_key(rec["when"]) if rec else "", n, raw, rec, text))
        if hits:
            _key, n, raw, rec, text = max(hits)
            return {"path": path, "line": n, "raw": raw, "when": rec["when"] if rec else None, "text": text}
    return None


def _look_alike(text, item_text, when):
    """An older line in the same note about the same thing, by its words, or None."""
    best = None
    for n, raw, rec in _note_lines(text):
        if not rec or not rec.get("when") or records.day_of(rec["when"]) >= records.day_of(when):
            continue
        if records.squash(rec["text"]) == records.squash(item_text):
            continue
        score = records.similarity(rec["text"], item_text)
        if score >= records.SIMILAR and (best is None or score > best[0]):
            best = (score, n, rec)
    if not best:
        return None
    return {"line": best[1], "when": best[2]["when"], "text": best[2]["text"]}


def _short_day(when):
    d = records.day_of(when)
    return "%d-%d" % (int(d[5:7]), int(d[8:10])) if when and not d.startswith("0000") else "earlier"


def _plan(lib, it, settings_ctx):
    """Decide where one item goes and how. Returns a plan dict."""
    ctx = settings_ctx
    tags = records.item_tags(it, ctx["lang"])
    target, how, words = None, None, []
    sug = (it.get("suggest") or {}).get("target")
    if sug and _usable_suggestion(lib, sug, ctx["writable"]):
        target, how = sug, "suggested"
    if not target:
        target = _by_category(lib, it, tags, ctx["candidates"])
        how = "category" if target else None
    if not target and ctx["assigned"] is not None and it["id"] in ctx["assigned"]:
        target, how = ctx["assigned"][it["id"]], "command"
    if not target and how != "command":
        target, _score, words = best_target(ctx["candidates"], it["text"])
        how = "matched" if target else None
    if not target:
        target, how = ctx["fallback"], "fallback"
    plan = {"item": it, "tags": tags, "target": target, "how": how, "words": words, "op": "append"}
    journal = records.in_journal(lib, target)
    plan["journal"] = journal
    if it.get("replaces"):
        old = _find_replaced(lib, it["replaces"], target, ctx["readable"])
        if old:
            plan.update(op="replace_line", target=old["path"], old=old, journal=False)
            return plan
        plan["replaces_missing"] = True
    body = _read(lib, target)
    if journal:
        want = records.squash(it["text"])
        for _n, _raw, rec in _note_lines(body):
            if rec and rec.get("when") == tags["when"] and records.squash(rec["text"]) == want:
                plan["op"] = "none"
                break
        return plan
    n = _said_already(body, it["text"])
    if n:
        plan.update(op="none", line=n)
        return plan
    elsewhere = ctx["said"].get(records.squash(it["text"]))
    if elsewhere:
        plan.update(op="none", target=elsewhere[0], line=elsewhere[1])
        return plan
    plan["alike"] = _look_alike(body, it["text"], tags["when"])
    return plan


def _reason(plan, lang):
    it, how, target = plan["item"], plan["how"], plan["target"]
    if plan["op"] == "replace_line":
        old = plan["old"]
        return (
            "The user changed their mind: this replaces line %d (said %s). The older wording stays as a short note "
            "at the end of the line." % (old["line"], _short_day(old["when"]))
        )
    if how == "suggested":
        why = "The agent suggested this note."
    elif how == "category":
        why = "Its category (%s) goes here." % (records.category_label(it.get("category"), lang) or "minor, journal only")
    elif how == "matched":
        why = "Seems to belong in this note"
        if plan["words"]:
            why += " (shared words: %s)" % ", ".join(plan["words"][:5])
        why += "."
    elif how == "command":
        why = "The classifier chose this note."
    else:
        why = "Did not clearly fit any note, so it is parked here for the user to sort."
    if plan.get("replaces_missing"):
        why += " It was meant to replace an older line (%r), which was not found, so it is added instead." % it["replaces"]
    alike = plan.get("alike")
    if alike:
        why += (
            " Line %d (said %s) looks similar: %r. The newer one counts; if it replaces that line, "
            "the user can drop the older one." % (alike["line"], _short_day(alike["when"]), alike["text"][:60])
        )
    return why


def _journal_category(lib, plan, lang):
    """The category written next to a journal line: given, or where the item was filed; not 'journal'."""
    it = plan["item"]
    if it.get("category"):
        cat = records.category_label(it["category"], lang)
    elif plan["journal"]:
        cat = None
    else:
        cat = records.page_category(lib, plan["target"], None, lang)
    if records.category_key(cat) in ("journal", "unsorted"):
        return None
    return cat


def _new_note(lib, target, lang):
    """Header for a note this proposal would create, when brainlib knows what the note is for."""
    if target == "decisions.md":
        page = DECISIONS_PAGE["zh" if lang == "zh" else "en"]
        return {"title": page["title"], "description": page["description"], "read_when": list(page["read_when"])}
    return None


def run(lib, actor="agent/unknown", limit=200, dry_run=False, only=None):
    settings = onboard.settings(lib)
    proposals.require_not_read_only(settings)
    lang = records.lib_lang(lib)
    items = [
        i for i in inbox.all_items(lib)
        if i["status"] == "pending" and i.get("text") and (only is None or i["id"] in only)
    ]
    held = [i for i in items if not onboard.allows_provenance(settings, i["provenance"])]
    items = [i for i in items if onboard.allows_provenance(settings, i["provenance"])][:limit]
    summary = {
        "items": len(items),
        "held_by_record_policy": len(held),
        "proposals": [],
        "duplicates": 0,
        "logged": 0,
        "auto_applied": 0,
    }
    if not items:
        return summary

    index = load_index(lib)
    fallback = lib.config.get("fallback_note") or "inbox-unsorted.md"
    readable = [
        n for n in index["notes"] if not n.get("not_utf8") and privacy.is_readable_by_agents(n["sensitivity"])
    ]
    notes = [
        n
        for n in readable
        if n["authority"] == "canonical" and not n.get("stream") and n["tier"] in ("L0", "L2") and n["path"] != fallback
    ]
    candidates = [(n, _fields(n)) for n in notes]

    assigned = None
    backend = (lib.config.get("classifier") or {}).get("backend", "rules")
    if backend == "command":
        cmd = (lib.config.get("classifier") or {}).get("command")
        if cmd:
            assigned = _command_assignments(lib, cmd, items, notes)
    if assigned is None:
        backend = "rules"

    said = {}
    for r in (read_json(lib.out("records.json")) or {}).get("records") or []:
        if r.get("source") == "note" and r.get("level") != "L3":
            said.setdefault(records.squash(r["text"]), (r["where"], r["line"]))
    ctx = {
        "lang": lang,
        "candidates": candidates,
        "assigned": assigned,
        "fallback": fallback,
        "writable": {n["path"] for n in readable if n["authority"] != "archived"},
        "readable": [n["path"] for n in readable if n["authority"] != "archived" and not n.get("stream")],
        "said": said,
    }
    log_on = lib.config.get("daily_log", True) is not False and records.journal_dir(lib)
    plans = [_plan(lib, it, ctx) for it in items]

    days = {}
    for plan in plans:
        if plan["journal"] and plan["op"] == "append":
            role = "file"
        elif log_on and not plan["journal"]:
            role = "log"
        else:
            continue
        day = plan["target"] if plan["journal"] else records.journal_target(lib, plan["tags"]["when"])
        cat = _journal_category(lib, plan, lang)
        line = records.format_line(plan["item"], lang, with_category=bool(cat), category=cat)
        days.setdefault(day, []).append((records.time_key(plan["tags"]["when"]), line, plan, role))

    batch = new_id("B")

    def propose(op, target, content, reason, evidence, **extra):
        if dry_run:
            summary["proposals"].append(
                {"target": target, "op": op, "items": len(evidence), "reason": reason, "content": content}
            )
            return None
        try:
            p = proposals.create(lib, op, target, content, reason, actor=actor, evidence=evidence, **extra)
        except BrainError as e:
            summary.setdefault("errors", []).append({"target": target, "error": e.message})
            return None
        summary["proposals"].append(
            {"id": p["id"], "target": target, "op": op, "items": len(evidence), "approval": p["approval"]}
        )
        return p

    for plan in plans:
        it = plan["item"]
        ev = [{"item": it["id"], "provenance": it["provenance"], "role": "file"}]
        if plan["op"] == "none":
            summary["duplicates"] += 1
            if not dry_run:
                inbox.set_status(lib, it["id"], "duplicate", ref=plan["target"])
            continue
        if plan["journal"]:
            continue
        if plan["op"] == "replace_line":
            old = plan["old"]
            content = records.format_line(it, lang, history=records.history_note(old["when"], old["text"], lang))
            p = propose("replace_line", plan["target"], content, _reason(plan, lang), ev, old_line=old["raw"])
        else:
            content = records.format_line(it, lang, with_category=plan["target"] == ctx["fallback"])
            p = propose("append", plan["target"], content, _reason(plan, lang), ev, new_note=_new_note(lib, plan["target"], lang))
        if p:
            inbox.set_status(lib, it["id"], "proposed", ref=p["id"])

    for day, rows in sorted(days.items()):
        rows.sort(key=lambda r: r[0])
        content = "\n".join(r[1] for r in rows)
        logged = sum(1 for r in rows if r[3] == "log")
        filed = len(rows) - logged
        reason = "The day's journal, in the order things were said: %d record(s)" % len(rows)
        if logged:
            reason += ", %d of them also filed in a note or said before" % logged
        reason += "."
        ev = [{"item": r[2]["item"]["id"], "provenance": r[2]["item"]["provenance"], "role": r[3]} for r in rows]
        p = propose("append", day, content, reason, ev, order="time")
        summary["logged"] += logged
        if p and filed:
            for r in rows:
                if r[3] == "file":
                    inbox.set_status(lib, r[2]["item"]["id"], "proposed", ref=p["id"])

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
