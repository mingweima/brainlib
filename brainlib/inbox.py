"""The inbox: the only place agents write what they learn. Append-only, outside the library.

An inbox item never changes a note by itself. `brainlib classify` turns items into
proposals; only an approved proposal changes a note.
"""

import re
from pathlib import Path

from . import privacy, provenance
from .util import (
    BrainError,
    EXIT_PRIVACY,
    append_jsonl,
    new_id,
    now_iso,
    read_jsonl,
    sha256_text,
    slug,
    strip_dot_slash,
    today_str,
)

MAX_TEXT = 4000
SOURCE_KINDS = ("conversation", "note", "annotation", "feedback", "interaction", "import", "connector")
STATUSES = ("pending", "proposed", "applied", "rejected", "deferred", "duplicate", "private-held")
NOT_FILED = ("pending", "proposed", "deferred")


def _items_files(lib):
    base = lib.state("inbox")
    if not base.exists():
        return []
    return sorted(p for p in base.glob("*/*.jsonl"))


def _status_log(lib):
    return lib.state("item-status.jsonl")


def all_items(lib):
    items = []
    for f in _items_files(lib):
        items.extend(read_jsonl(f))
    status = {}
    for ev in read_jsonl(_status_log(lib)):
        status[ev.get("item")] = ev
    for it in items:
        ev = status.get(it["id"])
        it["status"] = ev.get("status") if ev else ("private-held" if it.get("sensitivity") == "private" else "pending")
        it["status_ref"] = ev.get("ref") if ev else None
    items.sort(key=lambda x: x.get("captured_at") or "")
    return items


def not_filed_for_agents(lib):
    """Items written down but not in any note yet, newest first. Private items are never included."""
    items = [
        it
        for it in all_items(lib)
        if it["status"] in NOT_FILED and it.get("text") and it.get("sensitivity") != "private"
    ]
    items.reverse()
    return items


def describe(it):
    """One line for agents, with the same source marker the note would get, e.g. `[said 2026-10-20] ...`."""
    date = (it.get("said_at") or it.get("captured_at") or "")[:10] or None
    source = (it.get("source") or {}).get("ref")
    return "%s %s" % (provenance.marker(it["provenance"], date=date, source=source), it["text"].replace("\n", " "))


def set_status(lib, item_id, status, ref=None):
    if status not in STATUSES:
        raise ValueError(status)
    append_jsonl(_status_log(lib), {"item": item_id, "status": status, "ref": ref, "at": now_iso()})


def _norm(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def add(
    lib,
    text,
    provenance_level,
    actor="agent/unknown",
    source_kind="conversation",
    source_ref=None,
    said_at=None,
    target=None,
    tier=None,
    tags=None,
    sensitivity="internal",
    private_handling="exclude",
):
    """Validate and append one inbox item. Returns (item, duplicate_of_or_None).

    Private items are encrypted into the vault when it is set up. Without a vault they are
    kept (outside the library, readable only by this user account) only if the user chose
    `ask_first` or `normal` for sensitive things; otherwise they are refused.
    """
    text = (text or "").strip()
    if not text:
        raise BrainError("Nothing to save: the text is empty.", fix="Pass the exact words to remember.")
    if len(text) > MAX_TEXT:
        raise BrainError(
            "Text is too long for one inbox item (%d characters, limit %d)." % (len(text), MAX_TEXT),
            fix="Save the key point in a sentence or two. Long material belongs in a note of its own.",
        )
    prov = provenance.normalize(provenance_level)
    if source_kind not in SOURCE_KINDS:
        raise BrainError("Unknown source kind %r." % source_kind, fix="Use one of: %s" % ", ".join(SOURCE_KINDS))
    sensitivity = (sensitivity or "internal").lower()
    if sensitivity == "secret":
        raise BrainError(
            "Secrets are never stored in the library.",
            fix="Keep it in a password manager and save only where to find it.",
            code=EXIT_PRIVACY,
        )
    if sensitivity not in ("public", "internal", "private"):
        raise BrainError("Unknown sensitivity %r." % sensitivity, fix="Use public, internal or private.")
    privacy.refuse_if_secret(text)
    if target:
        target = strip_dot_slash(target)
        if not target.lower().endswith((".md", ".markdown")):
            target += ".md"

    digest = sha256_text(_norm(text))
    for it in all_items(lib):
        if it.get("content_sha256") == digest and it["status"] in ("pending", "proposed", "private-held"):
            return it, it["id"]

    item = {
        "schema": "brainlib/inbox-item@0.1",
        "id": new_id("I"),
        "captured_at": now_iso(),
        "actor": actor or "agent/unknown",
        "source": {"kind": source_kind, "ref": source_ref},
        "provenance": prov,
        "sensitivity": sensitivity,
        "content_sha256": digest,
    }
    if prov == "principal-said":
        item["said_at"] = said_at or item["captured_at"]
        if not said_at:
            item["said_at_estimated"] = True
    elif said_at:
        item["said_at"] = said_at
    if target or tier or tags:
        item["suggest"] = {"target": target, "tier": tier, "tags": list(tags or [])}

    if sensitivity == "private":
        from . import vault

        if private_handling == "exclude":
            raise BrainError(
                "Sensitive things are kept out of the library (onboarding Q7), so this was NOT saved.",
                fix="Do not save it anywhere else, and do not put it into a note with propose either. Tell the user it "
                "was not saved because they chose to keep sensitive things out of the library (onboarding Q7), and ask "
                "whether to keep this one anyway. If they say yes, run the same command with --not-sensitive instead of "
                "--private, and run brainlib onboard signal Q7 \"<their words>\" so that choice is checked again later.",
                code=EXIT_PRIVACY,
            )
        if vault.is_initialized(lib) and vault.age_bin():
            rel = Path("inbox-private") / today_str() / ("%s.age" % item["id"])
            vault.encrypt_to(lib, text, lib.state(*rel.parts))
            item["encrypted_ref"] = rel.as_posix()
        elif private_handling in ("ask_first", "normal"):
            item["text"] = text
        else:
            raise BrainError(
                "This item is private, and the vault is not set up, so it was NOT saved.",
                fix=(
                    "Do not save it any other way (not with propose either). Tell the user: 'I didn't save that "
                    "because it's private. If you want me to keep private things, please run `brainlib vault init` "
                    "yourself in a terminal (it asks you for a passphrase).'"
                ),
                code=EXIT_PRIVACY,
            )
    else:
        item["text"] = text

    path = lib.state("inbox", today_str(), "%s.jsonl" % slug(item["actor"], "agent"))
    append_jsonl(path, item)
    if sensitivity == "private":
        set_status(lib, item["id"], "private-held")
    return item, None
