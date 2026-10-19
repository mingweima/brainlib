"""Proposals: the only way a note changes. Each proposal is one readable JSON file.

Operations
- append: add text at the end of a note, or at the end of a section. Still valid if the
  note changed in the meantime. Creates the note if it does not exist yet.
- create: make a new note. Fails if the file already exists.
- replace: replace a whole note. Records the hash of the version it was based on; if the
  note changed since, the proposal goes stale and must be redone.

Who approves
- Core (L0) and entry (L1) pages: always the owner.
- edit_mode read_only: nothing changes at all.
- edit_mode inbox_only or propose: the owner approves everything.
- edit_mode auto_low_risk: appends to journal streams and zones marked auto_apply go in directly.
- edit_mode auto_most: appends and new notes in L2/L3 go in directly; replace still needs the owner.
- Never: private notes, the vault, anything outside the library, outside material into L0/L1.
Every change writes a receipt (hashes only, never content) and keeps a backup for undo.
"""

import re
from pathlib import Path

from . import frontmatter, onboard, privacy
from .scan import build_entry, looks_like_stream, scan_library
from .util import (
    BrainError,
    EXIT_APPROVAL,
    EXIT_CONFLICT,
    EXIT_PRIVACY,
    FileLock,
    append_jsonl,
    atomic_write,
    new_id,
    now_iso,
    read_json,
    rel_posix,
    safe_resolve,
    sha256_bytes,
    sha256_file,
    strip_dot_slash,
    today_str,
    write_json,
)

OPS = ("append", "create", "replace")
OPEN_STATES = ("open", "deferred")


def _dir(lib):
    return lib.state("proposals")


def _path(lib, pid):
    if not re.match(r"^P-[0-9T]+-[0-9a-f]{6}$", pid or ""):
        raise BrainError("Not a proposal id: %r" % pid, fix="Run `brainlib review` to see open proposals.")
    return _dir(lib) / ("%s.json" % pid)


def get(lib, pid):
    p = read_json(_path(lib, pid))
    if not p:
        raise BrainError("No such proposal: %s" % pid, fix="Run `brainlib review` to see open proposals.")
    return p


def _save(lib, p):
    write_json(_path(lib, p["id"]), p)


def list_proposals(lib, states=OPEN_STATES):
    d = _dir(lib)
    out = []
    for f in sorted(d.glob("P-*.json")):
        p = read_json(f)
        if p and (states is None or p.get("status") in states):
            out.append(p)
    out.sort(key=lambda p: p.get("created_at") or "")
    return out


def require_not_read_only(settings):
    if settings.get("edit_mode") == "read_only":
        raise BrainError(
            "The user chose read-only mode (onboarding question Q4), so nothing may be written.",
            fix=(
                "Do not save or change anything. If the user now asks you to remember or change things, "
                "ask them whether to switch modes, then run `brainlib onboard answer Q4 <letter>`."
            ),
            code=EXIT_APPROVAL,
        )


def target_info(lib, target):
    """Resolve a target path and collect what the policy needs to know about it."""
    target = strip_dot_slash(target)
    if not target.lower().endswith((".md", ".markdown")):
        raise BrainError("Only Markdown notes can be changed: %s" % target, fix="Use a path ending in .md")
    full = safe_resolve(lib.root, target)
    rel = rel_posix(lib.root, full)
    vault = lib.vault_dir.resolve()
    try:
        full.relative_to(vault)
        raise BrainError("The vault cannot be changed through proposals.", fix="Use `brainlib vault add`.", code=EXIT_PRIVACY)
    except ValueError:
        pass
    if lib.is_ignored(rel):
        raise BrainError("That location is ignored by brainlib: %s" % rel, fix="Choose a normal notes folder.")
    zone = lib.zone_for(rel)
    exists = full.is_file()
    if exists:
        text = full.read_text(encoding="utf-8", errors="replace")
        entry = build_entry(lib, rel, text, full.stat().st_mtime)
        tier, sensitivity, stream = entry["tier"], entry["sensitivity"], entry["stream"]
    else:
        sensitivity = privacy.resolve_sensitivity({}, zone)
        tier = str(zone.get("tier") or "L2").upper()
        stream = looks_like_stream(rel, zone)
    if sensitivity in ("private", "secret"):
        raise BrainError(
            "That note is private; agents cannot change it.",
            fix="Tell the user they can edit it themselves.",
            code=EXIT_PRIVACY,
        )
    return {"rel": rel, "full": full, "exists": exists, "zone": zone, "tier": tier, "stream": stream}


def _approval(settings, op, info):
    mode = settings.get("edit_mode", "propose")
    if info["tier"] in ("L0", "L1"):
        return "owner"
    if mode == "auto_most" and op in ("append", "create") and info["tier"] in ("L2", "L3"):
        return "auto"
    if mode == "auto_low_risk" and op == "append" and (info["zone"].get("auto_apply") or info["stream"]):
        return "auto"
    return "owner"


def create(lib, op, target, content, reason, actor="agent/unknown", evidence=None, heading=None):
    settings = onboard.settings(lib)
    require_not_read_only(settings)
    if op not in OPS:
        raise BrainError("Unknown operation %r." % op, fix="Use append, create or replace.")
    content = (content or "").rstrip() + "\n"
    if not content.strip():
        raise BrainError("The proposal has no content.", fix="Pass the text to add.")
    if not (reason or "").strip():
        raise BrainError("Every proposal needs a reason.", fix='Add --reason "why this change helps the user".')
    privacy.refuse_if_secret(content, "proposal content")
    info = target_info(lib, target)
    evidence = list(evidence or [])
    provs = sorted({e.get("provenance") for e in evidence if e.get("provenance")})
    if info["tier"] in ("L0", "L1") and provs and all(p == "third-party" for p in provs):
        raise BrainError(
            "Outside material cannot go straight into core or entry pages (L0/L1).",
            fix="Put it in a regular note first; the user can promote it later.",
            code=EXIT_APPROVAL,
        )
    if op == "create" and info["exists"]:
        raise BrainError("%s already exists." % info["rel"], fix="Use append to add to it.", code=EXIT_CONFLICT)
    if op == "replace" and not info["exists"]:
        raise BrainError("%s does not exist." % info["rel"], fix="Use create for a new note.")
    p = {
        "schema": "brainlib/proposal@0.1",
        "id": new_id("P"),
        "created_at": now_iso(),
        "actor": actor,
        "status": "open",
        "op": op,
        "target": info["rel"],
        "heading": heading,
        "content": content,
        "base_sha256": sha256_file(info["full"]) if op == "replace" else None,
        "reason": reason.strip(),
        "evidence": evidence,
        "provenance": provs,
        "tier": info["tier"],
        "approval": _approval(settings, op, info),
        "edit_mode": settings.get("edit_mode"),
    }
    _save(lib, p)
    return p


def _append_text(existing, content, heading):
    text = existing if existing.endswith("\n") or not existing else existing + "\n"
    if not heading:
        sep = "" if not text or text.endswith("\n\n") else "\n"
        return text + sep + content
    lines = text.splitlines(keepends=True)
    hpat = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
    start, level = None, None
    for i, line in enumerate(lines):
        m = hpat.match(line.rstrip("\n"))
        if m and m.group(2).strip().lower() == heading.strip().lower():
            start, level = i, len(m.group(1))
            break
    if start is None:
        sep = "" if not text or text.endswith("\n\n") else "\n"
        return text + sep + "## %s\n\n" % heading.strip() + content
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = hpat.match(lines[j].rstrip("\n"))
        if m and len(m.group(1)) <= level:
            end = j
            break
    before = lines[:end]
    while before and before[-1].strip() == "" and len(before) > start + 1:
        before.pop()
    block = "".join(before)
    if not block.endswith("\n"):
        block += "\n"
    if len(before) == start + 1:
        block += "\n"
    rest = "".join(lines[end:])
    return block + content + ("\n" + rest if rest else "")


def _new_note_text(rel, content):
    title = Path(rel).stem.replace("-", " ").replace("_", " ").strip().capitalize() or "Note"
    fm = {"type": "Note", "title": title, "created": today_str()}
    return frontmatter.render(fm, "# %s\n\n%s" % (title, content))


def _check_approver(lib, p, approved_by, user_words):
    if p["approval"] == "auto" and not str(approved_by or "").startswith("human:"):
        return "auto"
    if not str(approved_by or "").startswith("human:"):
        raise BrainError(
            "This change needs the user's yes (%s, %s)." % (p["target"], p["tier"]),
            fix=(
                "Show the user the change (`brainlib review %s`). Only if they clearly agree, run "
                "`brainlib apply %s --as %s --user-said \"<their words>\"`." % (p["id"], p["id"], lib.owner)
            ),
            code=EXIT_APPROVAL,
        )
    if p["tier"] in ("L0", "L1") and not (user_words or "").strip():
        raise BrainError(
            "Core and entry pages (L0/L1) need the user's own words of approval.",
            fix='Add --user-said "<what the user said when they agreed>".',
            code=EXIT_APPROVAL,
        )
    if user_words and _echoes_content(user_words, p.get("content")):
        raise BrainError(
            "--user-said repeats the text being saved. It must be the user's answer to this change, not the words being recorded.",
            fix=(
                "Show the user this change (`brainlib review %s`) and ask whether to apply it. Then pass their reply, "
                "for example --user-said \"可以\" or --user-said \"yes\"." % p["id"]
            ),
            code=EXIT_APPROVAL,
        )
    return "owner"


_MARKER = re.compile(r"\[(?:said|judgment|extracted|inferred|guess|external)[^\]]*\]")


def _squash(text):
    return re.sub(r"[\W_]+", "", _MARKER.sub("", text or "").lower())


def _echoes_content(user_words, content):
    """True when the 'approval' is really the content itself, e.g. the user's original request."""
    said = _squash(user_words)
    if not said:
        return False
    for line in (content or "").splitlines():
        part = _squash(line)
        if len(part) >= 6 and part in said:
            return True
    return len(said) >= 8 and said in _squash(content)


def apply(lib, pid, approved_by=None, user_words=None):
    """Apply one proposal. Returns the receipt."""
    settings = onboard.settings(lib)
    require_not_read_only(settings)
    p = get(lib, pid)
    if p["status"] not in OPEN_STATES:
        raise BrainError("Proposal %s is %s, not open." % (pid, p["status"]), fix="Run `brainlib review`.")
    approval = _check_approver(lib, p, approved_by, user_words)
    with FileLock(lib.state("write.lock")):
        info = target_info(lib, p["target"])
        full = info["full"]
        before = full.read_bytes() if full.is_file() else None
        before_sha = sha256_bytes(before) if before is not None else None
        if p["op"] == "create" and before is not None:
            return _stale(lib, p, "the file was created in the meantime")
        if p["op"] == "replace" and before_sha != p.get("base_sha256"):
            return _stale(lib, p, "the note changed after this proposal was made")
        if p["op"] == "append":
            new = _append_text(before.decode("utf-8", "replace"), p["content"], p.get("heading")) if before is not None else _new_note_text(p["target"], p["content"])
        elif p["op"] == "create":
            new = p["content"] if p["content"].lstrip().startswith(("---", "#")) else _new_note_text(p["target"], p["content"])
        else:
            new = p["content"]
        if before is not None and b"\r\n" in before:
            new = new.replace("\r\n", "\n").replace("\n", "\r\n")
        backup = None
        if before is not None:
            backup = lib.state("backups", "%s.bak" % p["id"])
            atomic_write(backup, before, private=True)
        atomic_write(full, new)
        after_sha = sha256_file(full)
        receipt = {
            "schema": "brainlib/receipt@0.1",
            "proposal": p["id"],
            "op": p["op"],
            "target": p["target"],
            "tier": p["tier"],
            "before_sha256": before_sha,
            "after_sha256": after_sha,
            "approval": approval,
            "approved_by": approved_by or "auto",
            "user_words_given": bool((user_words or "").strip()),
            "at": now_iso(),
            "contains_content": False,
        }
        append_jsonl(lib.state("receipts", "%s.jsonl" % today_str()), receipt)
        p.update(
            {
                "status": "applied",
                "decided_at": receipt["at"],
                "decided_by": approved_by or "auto",
                "user_words": (user_words or "").strip()[:300] or None,
                "after_sha256": after_sha,
                "backup": backup.name if backup else None,
            }
        )
        _save(lib, p)
    _mark_items(lib, p, "applied")
    scan_library(lib, write=True)
    return receipt


def _stale(lib, p, why):
    p["status"] = "stale"
    p["stale_reason"] = why
    _save(lib, p)
    _mark_items(lib, p, "pending")
    raise BrainError(
        "Proposal %s is out of date: %s." % (p["id"], why),
        fix="Run `brainlib classify` (or make a new proposal) based on the current note.",
        code=EXIT_CONFLICT,
    )


def _mark_items(lib, p, status):
    from . import inbox

    for ev in p.get("evidence") or []:
        if ev.get("item"):
            inbox.set_status(lib, ev["item"], status, ref=p["id"])


def apply_auto(lib, actor="agent/unknown"):
    done, failed = [], []
    for p in list_proposals(lib, states=("open",)):
        if p.get("approval") != "auto":
            continue
        try:
            done.append(apply(lib, p["id"], approved_by=None))
        except BrainError as e:
            failed.append({"proposal": p["id"], "error": e.message})
    return done, failed


def decide(lib, pid, status, by, note=None):
    if status not in ("rejected", "deferred"):
        raise ValueError(status)
    p = get(lib, pid)
    if p["status"] not in OPEN_STATES:
        raise BrainError("Proposal %s is %s, not open." % (pid, p["status"]), fix="Run `brainlib review`.")
    if status == "rejected" and not str(by or "").startswith("human:") and p["approval"] != "auto":
        raise BrainError("Only the user can reject this proposal.", fix="Ask the user, then pass --as %s." % lib.owner, code=EXIT_APPROVAL)
    p.update({"status": status, "decided_at": now_iso(), "decided_by": by, "decision_note": (note or "")[:300] or None})
    _save(lib, p)
    _mark_items(lib, p, "rejected" if status == "rejected" else "deferred")
    return p


def undo(lib, pid, by):
    """Restore the note to how it was before an applied proposal, if nothing changed since."""
    p = get(lib, pid)
    if p["status"] != "applied":
        raise BrainError("Only applied proposals can be undone.", fix="Run `brainlib review %s`." % pid)
    if not str(by or "").startswith("human:"):
        raise BrainError("Undo needs the user's yes.", fix="Ask the user, then pass --as %s." % lib.owner, code=EXIT_APPROVAL)
    with FileLock(lib.state("write.lock")):
        full = safe_resolve(lib.root, p["target"])
        if sha256_file(full) != p.get("after_sha256"):
            raise BrainError(
                "The note changed after this proposal was applied, so it cannot be undone automatically.",
                fix="Edit the note by hand.",
                code=EXIT_CONFLICT,
            )
        if p.get("backup"):
            atomic_write(full, lib.state("backups", p["backup"]).read_bytes())
        else:
            full.unlink()
        p.update({"status": "undone", "undone_at": now_iso(), "undone_by": by})
        _save(lib, p)
        append_jsonl(
            lib.state("receipts", "%s.jsonl" % today_str()),
            {
                "schema": "brainlib/receipt@0.1",
                "proposal": p["id"],
                "op": "undo",
                "target": p["target"],
                "before_sha256": p.get("after_sha256"),
                "after_sha256": sha256_file(full),
                "approved_by": by,
                "at": now_iso(),
                "contains_content": False,
            },
        )
    scan_library(lib, write=True)
    return p


def render(p, lang="en", full=False):
    lines = [
        "PROPOSAL %s  [%s]" % (p["id"], p["status"]),
        "  change: %s %s%s" % (p["op"], p["target"], (" (section: %s)" % p["heading"]) if p.get("heading") else ""),
        "  page level: %s; needs: %s" % (p["tier"], "the user's yes" if p["approval"] == "owner" else "nothing (low risk, applies automatically)"),
        "  why: %s" % p["reason"],
    ]
    if p.get("provenance"):
        lines.append("  based on: %s" % ", ".join(p["provenance"]))
    content = p["content"].rstrip("\n")
    if not full and len(content) > 600:
        content = content[:600] + "\n  ... (%d more characters; use `brainlib review %s`)" % (len(p["content"]) - 600, p["id"])
    lines.append("  text:")
    lines.extend("    " + ln for ln in content.splitlines())
    return "\n".join(lines)
