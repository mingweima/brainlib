"""Onboarding: ten multiple-choice questions, asked once, then revisited over time.

Nothing here is fixed. Every answer keeps its history and has a date when it should be
checked again. When the user says something that contradicts an earlier answer, agents
record a signal (`brainlib onboard signal`); enough signals make the question due again.
New versions of brainlib can add questions; only the new ones are asked.
Answers live in the state folder, never inside the notes.
"""

import json
import re
from datetime import timedelta
from pathlib import Path

from . import privacy, vault
from .util import (
    BrainError,
    append_jsonl,
    now_iso,
    parse_date,
    read_json,
    read_jsonl,
    today,
    write_json,
)

SIGNALS_TO_REASK = 3
DEFAULT_SETTINGS = {
    "edit_mode": "propose",
    "record_policy": "important",
    "private_handling": "exclude",
    "review_cadence": "weekly",
    "question_style": "choices",
    "audience": "unsure",
    "purposes": [],
    "areas": [],
    "sensitive_topics": [],
    "existing_notes": None,
}
CADENCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "on_request": None}
RECORD_ORDER = ["explicit_only", "important", "with_inferences", "with_external"]


def load_questions():
    path = Path(__file__).parent / "data" / "onboarding.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _question(qid):
    data = load_questions()
    for q in data["questions"]:
        if q["id"].lower() == str(qid).strip().lower():
            return q
    raise BrainError(
        "Unknown question %r." % qid,
        fix="Questions are Q1 to Q%d. Run `brainlib onboard list`." % len(data["questions"]),
    )


def _profile_path(lib):
    return lib.state("profile.json")


def profile(lib):
    return read_json(
        _profile_path(lib),
        {"schema": "brainlib/profile@0.1", "questions_version": 0, "answers": {}, "started_at": None},
    )


def _save(lib, prof):
    write_json(_profile_path(lib), prof)


def _signals(lib):
    return read_jsonl(lib.state("profile-signals.jsonl"))


def _new_signals(lib, qid, answer_entry):
    """Signals recorded after the question was last answered (counted by position, not by clock)."""
    sig = [s for s in _signals(lib) if s.get("question") == qid]
    if not answer_entry:
        return len(sig)
    if "signals_at_answer" in answer_entry:
        return max(0, len(sig) - int(answer_entry["signals_at_answer"] or 0))
    since = answer_entry.get("answered_at")
    return len([s for s in sig if not since or s.get("at", "") > since])


def status(lib):
    """One row per question: state is unanswered, answered, skipped or due."""
    data = load_questions()
    prof = profile(lib)
    rows = []
    td = today()
    for q in data["questions"]:
        a = prof["answers"].get(q["id"])
        row = {"id": q["id"], "key": q["key"], "state": "unanswered", "reason": None, "answer": a}
        if a:
            row["state"] = "skipped" if a.get("skipped") else "answered"
            revisit = parse_date(a.get("revisit_at"))
            n = _new_signals(lib, q["id"], a)
            if revisit and revisit <= td:
                row["state"], row["reason"] = "due", "it is time to check this answer again"
            elif n >= SIGNALS_TO_REASK:
                row["state"], row["reason"] = "due", "the user said %d things that may not fit this answer" % n
        rows.append(row)
    return rows


def started(lib):
    return bool(profile(lib).get("started_at"))


def is_complete(lib):
    return all(r["state"] != "unanswered" for r in status(lib))


def next_question(lib):
    rows = status(lib)
    for r in rows:
        if r["state"] == "unanswered":
            return _question(r["id"]), "not answered yet"
    for r in rows:
        if r["state"] == "due":
            return _question(r["id"]), r["reason"]
    return None, None


def _parse_choices(q, raw):
    if raw is None:
        raise BrainError("No answer given.", fix="Pass the option letter(s), for example `a` or `a,c`, or `skip`.")
    tokens = [t for t in re.split(r"[\s,;/、，]+", str(raw).strip()) if t]
    if len(tokens) == 1 and len(tokens[0]) > 1 and tokens[0].isalpha() and tokens[0].islower():
        letters = list(tokens[0])
        if all(any(o["id"] == ch for o in q["options"]) for ch in letters) and not any(
            o["value"] == tokens[0] for o in q["options"]
        ):
            tokens = letters
    chosen = []
    for t in tokens:
        tl = t.lower().strip(").")
        match = None
        for i, o in enumerate(q["options"]):
            if tl in (o["id"], o["value"].lower(), str(i + 1)):
                match = o
        if not match:
            valid = ", ".join("%s (%s)" % (o["id"], o["value"]) for o in q["options"])
            raise BrainError("%s has no option %r." % (q["id"], t), fix="Valid options: %s" % valid)
        if match["id"] not in chosen:
            chosen.append(match["id"])
    if not chosen:
        raise BrainError("No option chosen.", fix="Pass at least one option letter, or `skip`.")
    if not q.get("multi") and len(chosen) > 1:
        raise BrainError(
            "%s takes exactly one answer, got %d." % (q["id"], len(chosen)),
            fix="Ask the user which single option fits best.",
        )
    return chosen


def answer(lib, qid, raw, other_text=None, actor="agent/unknown"):
    q = _question(qid)
    prof = profile(lib)
    data = load_questions()
    previous = prof["answers"].get(q["id"])
    now = now_iso()
    skipped = str(raw).strip().lower() in ("skip", "skipped", "pass", "跳过")
    if skipped:
        chosen, values = [], []
        days = 0 if not q.get("revisit_days") else max(30, q["revisit_days"] // 2)
    else:
        chosen = _parse_choices(q, raw)
        values = [o["value"] for o in q["options"] if o["id"] in chosen]
        days = q.get("revisit_days") or 0
    if other_text:
        privacy.refuse_if_secret(other_text)
        other_text = other_text.strip()[:500]
    entry = {
        "choices": chosen,
        "values": values,
        "other_text": other_text or None,
        "skipped": skipped,
        "answered_at": now,
        "revisit_at": (today() + timedelta(days=days)).isoformat() if days else None,
        "actor": actor,
        "signals_at_answer": len([s for s in _signals(lib) if s.get("question") == q["id"]]),
    }
    prof["answers"][q["id"]] = entry
    prof["started_at"] = prof.get("started_at") or now
    prof["questions_version"] = data["questions_version"]
    _save(lib, prof)
    append_jsonl(
        lib.state("profile-history.jsonl"),
        {"question": q["id"], "key": q["key"], "new": entry, "previous": previous, "at": now},
    )
    return q, entry


def signal(lib, qid, text, actor="agent/unknown"):
    """Record that something the user said may not fit their earlier answer."""
    q = _question(qid)
    text = (text or "").strip()
    if not text:
        raise BrainError("Signal text is empty.", fix="Quote what the user said, briefly.")
    privacy.refuse_if_secret(text)
    append_jsonl(
        lib.state("profile-signals.jsonl"),
        {"question": q["id"], "text": text[:500], "actor": actor, "at": now_iso()},
    )
    a = profile(lib)["answers"].get(q["id"])
    return q, _new_signals(lib, q["id"], a)


def reset(lib, qid=None):
    prof = profile(lib)
    now = now_iso()
    targets = [_question(qid)["id"]] if qid else list(prof["answers"].keys())
    for t in targets:
        previous = prof["answers"].pop(t, None)
        append_jsonl(lib.state("profile-history.jsonl"), {"question": t, "new": None, "previous": previous, "at": now})
    _save(lib, prof)
    return targets


def settings(lib):
    """What the answers mean in practice. Config `settings` overrides win."""
    s = dict(DEFAULT_SETTINGS)
    data = load_questions()
    prof = profile(lib)
    for q in data["questions"]:
        a = prof["answers"].get(q["id"])
        if not a or a.get("skipped") or not a.get("values"):
            continue
        if q.get("multi"):
            s[q["key"]] = [v for v in a["values"] if v != "other"]
        elif a["values"][0] != "other":
            s[q["key"]] = a["values"][0]
    s.update(lib.settings_override())
    s["review_cadence_days"] = CADENCE_DAYS.get(s.get("review_cadence"), 7)
    level = {"read_only": 0, "inbox_only": 1}.get(s["edit_mode"], 2)
    features = ["read"]
    if level >= 1:
        features.append("inbox")
    if level >= 2:
        features += ["proposals", "receipts"]
        if s["private_handling"] == "vault":
            features.append("vault")
            if vault.is_initialized(lib):
                level = 3
        if "understand" in s["purposes"] or s["question_style"] == "guess_first":
            features.append("calibration")
        if s["audience"] in ("solo_many_agents", "shared"):
            features.append("roles")
            level = 4
    s["level"] = level
    s["features"] = features
    return s


def sensitive_topic_names(lib, settings_=None):
    """The topics the user marked sensitive (Q6), unless they want no special handling for them (Q7)."""
    s = settings_ or settings(lib)
    if s.get("private_handling") == "normal":
        return []
    q = next(q for q in load_questions()["questions"] if q["key"] == "sensitive_topics")
    chosen = set(s.get("sensitive_topics") or []) - {"none", "other"}
    names = [o["en"] for o in q["options"] if o.get("value") in chosen]
    other = (profile(lib)["answers"].get(q["id"]) or {}).get("other_text")
    if other:
        names.append('"%s"' % other)
    return names


def allows_provenance(settings_, prov):
    """Does the user's record policy allow saving this kind of statement?"""
    policy = settings_.get("record_policy", "important")
    rank = RECORD_ORDER.index(policy) if policy in RECORD_ORDER else 1
    if prov in ("agent-inference", "agent-guess"):
        return rank >= 2
    if prov == "third-party":
        return rank >= 3
    return True


def _t(block, lang):
    return block.get(lang) or block.get("en") or ""


def render_question(q, lang="en", reason=None, number=None, total=10):
    lines = []
    head = "QUESTION %s" % q["id"]
    if number:
        head += " (%d of %d)" % (number, total)
    head += " - pick any that fit" if q.get("multi") else " - pick one"
    lines.append(head)
    if reason and reason != "not answered yet":
        lines.append("WHY AGAIN: %s. Say so briefly before asking." % reason)
    lines.append("ASK THE USER (in their language, word for word is fine):")
    lines.append("  " + _t(q["ask"], lang))
    rec = set(q.get("recommended") or [])
    for o in q["options"]:
        tag = "  (recommended)" if o["id"] in rec else ""
        lines.append("  %s) %s%s" % (o["id"], o.get(lang) or o["en"], tag))
    lines.append("  They may also skip this question.")
    lines.append("IF THEY ASK WHY: " + _t(q["why"], lang))
    example = "a,c" if q.get("multi") else (q.get("recommended") or ["a"])[0]
    lines.append("THEN RECORD: brainlib onboard answer %s <letter%s>" % (q["id"], "s" if q.get("multi") else ""))
    lines.append("  example: brainlib onboard answer %s %s" % (q["id"], example))
    lines.append("  if they skip: brainlib onboard answer %s skip" % q["id"])
    if any(o["value"] == "other" for o in q["options"]):
        lines.append('  if they pick "other": add --other "their words"')
    lines.append("Ask one question at a time. Do not answer for the user.")
    return "\n".join(lines)


def render_summary(lib, lang="en"):
    data = load_questions()
    prof = profile(lib)
    out = []
    for q in data["questions"]:
        a = prof["answers"].get(q["id"])
        if not a:
            out.append("%s %s -> (not answered)" % (q["id"], _t(q["ask"], lang)))
            continue
        if a.get("skipped"):
            ans = "(skipped)"
        else:
            ans = "; ".join(
                "%s) %s" % (o["id"], o.get(lang) or o["en"]) for o in q["options"] if o["id"] in a["choices"]
            )
            if a.get("other_text"):
                ans += ' - "%s"' % a["other_text"]
        when = (a.get("answered_at") or "")[:10]
        again = a.get("revisit_at") or "never"
        out.append("%s %s -> %s  [answered %s, check again %s]" % (q["id"], _t(q["ask"], lang), ans, when, again))
    s = settings(lib)
    out.append("")
    out.append(
        "IN PRACTICE: edit_mode=%s, record_policy=%s, private_handling=%s, review every %s, question_style=%s, level=%d"
        % (
            s["edit_mode"],
            s["record_policy"],
            s["private_handling"],
            ("%d day(s)" % s["review_cadence_days"]) if s["review_cadence_days"] else "time the user asks",
            s["question_style"],
            s["level"],
        )
    )
    return "\n".join(out)
