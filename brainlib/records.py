"""Records: what agents write down, with four tags, wherever each one lives now.

A record starts as an inbox item (`brainlib note`). Organising files it as one line in a note
and one line in the day's journal. Every record carries when the user said it (to the minute),
a category (the area of the library it belongs to), its importance and a privacy level. Tags an
agent leaves out are inferred and marked as inferred, so older agents keep working.

Records get tiers like pages: new ones surface at L0/L1, filed ones sit at the tier of their
page, and archived or old journal entries sink to L3. The newest statement about the same
thing counts; see docs/records.md.
"""

import os
import re
from datetime import date as _date, datetime as _datetime, timedelta
from pathlib import Path

from . import config, i18n, provenance
from .util import BrainError, now, parse_date, read_json

IMPORTANCE = ("high", "normal", "low")
PRIVACY = ("normal", "private", "confidential", "secret")
LEVELS = ("L0", "L1", "L2", "L3")
SORTS = ("time", "importance", "category", "privacy", "level")

_IMPORTANCE_ALIASES = {
    "high": "high", "important": "high", "重要": "high", "高": "high", "3": "high",
    "normal": "normal", "medium": "normal", "一般": "normal", "中": "normal", "普通": "normal", "2": "normal",
    "low": "low", "minor": "low", "次要": "low", "低": "low", "1": "low",
}
IMPORTANCE_WORDS = {"zh": {"high": "重要", "low": "次要"}, "en": {"high": "important", "low": "minor"}}
_WORD_IMPORTANCE = {"重要": "high", "important": "high", "次要": "low", "minor": "low"}

_PRIVACY_ALIASES = {
    "normal": "normal", "普通": "normal", "公开": "normal", "public": "normal", "internal": "normal",
    "private": "private", "秘密": "private",
    "confidential": "confidential", "机密": "confidential", "vault": "confidential",
    "secret": "secret", "绝密": "secret", "top-secret": "secret", "top secret": "secret",
}
PRIVACY_LABELS = {
    "zh": {"normal": "普通", "private": "秘密", "confidential": "机密", "secret": "绝密"},
    "en": {"normal": "normal", "private": "private", "confidential": "confidential", "secret": "secret"},
}

CATEGORIES = {
    "me": {
        "zh": "关于我", "en": "about me", "target": "me.md",
        "aliases": ("关于我", "我", "偏好", "习惯", "价值观", "about me", "me", "profile", "preference", "preferences", "habit", "habits"),
    },
    "decisions": {
        "zh": "决定", "en": "decisions", "target": "decisions.md",
        "aliases": ("决定", "决策", "decision", "decisions"),
    },
    "journal": {
        "zh": "日记", "en": "journal", "target": None,
        "aliases": ("日记", "日志", "事件", "计划", "安排", "journal", "diary", "log", "event", "events", "plan", "plans"),
    },
    "unsorted": {
        "zh": "未分类", "en": "unsorted", "target": None,
        "aliases": ("未分类", "其他", "unsorted", "other", "misc"),
    },
}
_CATEGORY_ALIASES = {}
for _key, _info in CATEGORIES.items():
    _CATEGORY_ALIASES[_key] = _key
    for _a in _info["aliases"] + (_info["zh"], _info["en"]):
        _CATEGORY_ALIASES[_a.lower()] = _key

MAX_CATEGORY = 40
MAX_REPLACES = 200
SIMILAR = 0.5


# --- language --------------------------------------------------------------

def lib_lang(lib):
    """The language labels are written in: the user's choice, else the library's, else the default."""
    for value in (
        os.environ.get("BRAINLIB_LANG"),
        (lib.config.get("lang") if lib is not None else None),
        config.global_state().get("lang"),
    ):
        if i18n.normalize(value):
            return i18n.normalize(value)
    return i18n.DEFAULT_LANG


# --- the four tags ---------------------------------------------------------

def normalize_importance(value):
    if value is None or str(value).strip() == "":
        return None
    key = _IMPORTANCE_ALIASES.get(str(value).strip().lower())
    if not key:
        raise BrainError("Unknown importance %r." % value, fix="Use high, normal or low (重要、一般、次要).")
    return key


def normalize_privacy(value):
    if value is None or str(value).strip() == "":
        return None
    key = _PRIVACY_ALIASES.get(str(value).strip().lower())
    if not key:
        raise BrainError(
            "Unknown privacy level %r." % value,
            fix="Use normal, private, confidential or secret (普通、秘密、机密、绝密).",
        )
    return key


def clean_category(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("[]()（）,，;；")
    if not text:
        return None
    if len(text) > MAX_CATEGORY:
        raise BrainError("The category is too long.", fix="Use a short name such as 关于我, 决定, 日记 or a folder name.")
    return text


def category_key(label):
    """The built-in category a label means (me, decisions, journal, unsorted), or None."""
    if not label:
        return None
    return _CATEGORY_ALIASES.get(str(label).strip().lower())


def category_label(label, lang):
    key = category_key(label)
    if key:
        return CATEGORIES[key]["zh" if lang == "zh" else "en"]
    return label


def builtin_label(key, lang):
    return CATEGORIES[key]["zh" if lang == "zh" else "en"]


def importance_word(importance, lang):
    return IMPORTANCE_WORDS["zh" if lang == "zh" else "en"].get(importance)


def privacy_label(privacy, lang):
    return PRIVACY_LABELS["zh" if lang == "zh" else "en"].get(privacy, privacy)


# --- time ------------------------------------------------------------------

_DATE_ONLY = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_DATE_TIME = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})[ T](\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?$")
_TIME_ONLY = re.compile(r"^(\d{1,2}):(\d{2})$")


def minute(value):
    """'YYYY-MM-DD HH:MM' in local time from an ISO timestamp; dates stay dates; else None."""
    if not value:
        return None
    s = str(value).strip()
    if _DATE_ONLY.match(s):
        return _fmt_date(s)
    try:
        dt = _datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        m = _DATE_TIME.match(s)
        if not m:
            return None
        y, mo, d, h, mi = (int(x) for x in m.groups())
        dt = _datetime(y, mo, d, h, mi)
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def _fmt_date(s):
    m = _DATE_ONLY.match(s)
    y, mo, d = (int(x) for x in m.groups())
    return _date(y, mo, d).isoformat()


def parse_said_at(value):
    """Normalise --said-at: a date, a date and time, an ISO timestamp, or a time today."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if _DATE_ONLY.match(s):
            return _fmt_date(s)
        m = _TIME_ONLY.match(s)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            return now().replace(hour=h, minute=mi).strftime("%Y-%m-%d %H:%M")
        out = minute(s)
        if out:
            return out
    except ValueError:
        pass
    raise BrainError(
        "Cannot read the time %r." % value,
        fix='Write when the user said it like "2026-10-20 09:42", or just "2026-10-20".',
    )


def time_key(when):
    """Sortable key: 'YYYY-MM-DD HH:MM'; a bare date sorts at midnight; unknown sorts first."""
    if not when:
        return "0000-00-00 00:00"
    s = str(when)
    if len(s) == 10:
        return s + " 00:00"
    return minute(s) or s[:16]


def day_of(when):
    return time_key(when)[:10]


# --- markers written into notes ----------------------------------------------

_KINDS = "said|judgment|extracted|inferred|guess|external"
_MARK = re.compile(
    r"\[(?P<kind>%s)"
    r"(?::\s*(?P<src>[^\],，;；·]+?))?"
    r"(?:\s+(?P<date>\d{4}-\d{2}-\d{2})(?:[ T](?P<time>\d{1,2}:\d{2}))?)?"
    r"(?P<rest>(?:\s*[,，;；·]\s*[^\],，;；·]+)*)\s*\]" % _KINDS
)
MARK = _MARK
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_HISTORY = re.compile(
    r"\s*(?:（(?:\d{1,2}-\d{1,2}|以前) 说的是：(?P<zh>[^（）]*)）|\(on (?:\d{1,2}-\d{1,2}|earlier): (?P<en>[^()]*)\))\s*$"
)


def marker(prov, when=None, source=None, importance="normal", category=None, lang="zh"):
    """Inline source label, e.g. [said 2026-10-20 09:42, 重要] or [external: example.org 2026-10-20 09:42]."""
    info = provenance.LEVELS[provenance.normalize(prov)]
    head = info["marker"]
    if head in ("external", "extracted") and source:
        head += ": %s" % re.sub(r"[\],，;；·]+", " ", str(source)).strip()
    if when:
        head += " %s" % when
    extras = []
    word = importance_word(importance, lang)
    if word:
        extras.append(word)
    if category:
        extras.append(category)
    return "[%s%s]" % (head, "".join(", %s" % e for e in extras))


def parse_marker(text):
    """The first source label in a piece of text, as a dict, or None."""
    m = _MARK.search(text or "")
    if not m:
        return None
    kind = m.group("kind")
    when = m.group("date")
    if when and m.group("time"):
        h, mi = m.group("time").split(":")
        when = "%s %02d:%s" % (when, int(h), mi)
    importance, category = "normal", None
    for part in re.split(r"[,，;；·]", m.group("rest") or ""):
        part = part.strip()
        if not part:
            continue
        if part.lower() in _WORD_IMPORTANCE:
            importance = _WORD_IMPORTANCE[part.lower()]
        elif category is None and not part[0].isdigit():
            category = part
    return {
        "provenance": provenance.normalize(kind),
        "source": (m.group("src") or "").strip() or None,
        "when": when,
        "importance": importance,
        "category": category,
        "span": m.span(),
    }


def parse_line(line):
    """A list item that carries a source label, as a record dict; anything else gives None."""
    m = _LIST_ITEM.match(line.rstrip("\r\n"))
    if not m:
        return None
    body = m.group(1)
    mk = parse_marker(body)
    if not mk:
        return None
    a, b = mk["span"]
    text = (body[:a] + body[b:]).strip()
    if not text:
        return None
    rec = dict(mk)
    rec.pop("span")
    rec["text"] = text
    rec["raw"] = line.rstrip("\r\n")
    return rec


def parse_lines(text):
    out = []
    for n, line in enumerate((text or "").splitlines(), start=1):
        rec = parse_line(line)
        if rec:
            rec["line"] = n
            out.append(rec)
    return out


def line_time_key(line):
    rec = parse_line(line)
    if not rec or not rec.get("when"):
        return None
    return time_key(rec["when"])


def strip_history(text):
    return _HISTORY.sub("", text or "").strip()


def history_of(text):
    """The older wording kept at the end of a replaced line, or None."""
    m = _HISTORY.search(text or "")
    return (m.group("zh") or m.group("en") or "").strip() or None if m else None


def history_note(old_when, old_text, lang):
    """The trace a replaced line leaves: （10-13 说的是：聚类到公司层面）."""
    old = strip_history(old_text)
    if len(old) > 60:
        old = old[:59].rstrip() + "…"
    day = ""
    if old_when:
        d = parse_date(str(old_when)[:10])
        day = "%d-%d" % (d.month, d.day) if d else ""
    if lang == "zh":
        return "（%s 说的是：%s）" % (day or "以前", old)
    return " (on %s: %s)" % (day or "earlier", old)


def squash(text):
    """Comparable form: no labels, no history note, no punctuation or spaces, lower case."""
    t = _MARK.sub("", strip_history(text or ""))
    return re.sub(r"[\W_]+", "", t.lower())


def replaced_item(new, items):
    """The latest item said no later than `new` whose words contain what `new` replaces, or None."""
    want = squash(new.get("replaces"))
    if not want:
        return None
    mine = time_key(new.get("said_at") or new.get("captured_at") or new.get("when"))
    best = None
    for it in items:
        if it.get("id") == new.get("id") or want not in squash(it.get("text")):
            continue
        when = time_key(it.get("said_at") or it.get("captured_at") or it.get("when"))
        if when <= mine and (best is None or when > best[0]):
            best = (when, it)
    return best[1] if best else None


def similarity(a, b):
    """How much two statements overlap in topic words (0..1); fewer than two shared words is 0."""
    from .scan import _content_tokens

    ta = _content_tokens(strip_history(a), fallback=False)
    tb = _content_tokens(strip_history(b), fallback=False)
    if not ta or not tb:
        return 0.0
    common = ta & tb
    if len(common) < 2:
        return 0.0
    return len(common) / float(min(len(ta), len(tb)))


# --- where records go ------------------------------------------------------

def journal_dir(lib):
    """The first journal-like zone (`stream: true`), e.g. 'journal/', or None."""
    for z in lib.config.get("zones") or []:
        if z.get("stream") and z.get("path"):
            return z["path"].rstrip("/") + "/"
    return None


def journal_target(lib, when):
    d = journal_dir(lib)
    if not d:
        return None
    day = day_of(when) if when else now().date().isoformat()
    if day.startswith("0000"):
        day = now().date().isoformat()
    return "%s%s.md" % (d, day)


def in_journal(lib, rel):
    d = journal_dir(lib)
    return bool(d and rel.startswith(d))


def page_category(lib, rel, title=None, lang="zh"):
    """The category a filed line gets from where it lives."""
    rel = rel or ""
    if rel.lower() == "me.md":
        return builtin_label("me", lang)
    if rel.lower() == "decisions.md":
        return builtin_label("decisions", lang)
    if in_journal(lib, rel):
        return builtin_label("journal", lang)
    if rel == (lib.config.get("fallback_note") or "inbox-unsorted.md"):
        return builtin_label("unsorted", lang)
    if "/" in rel:
        return rel.split("/", 1)[0]
    return title or Path(rel).stem


def item_tags(it, lang):
    """The four tags of an inbox item, filling in what the agent left out (category stays None)."""
    when = minute(it.get("said_at")) if it.get("said_at") else None
    estimated = bool(it.get("said_at_estimated")) or not when
    if not when:
        when = minute(it.get("captured_at"))
    if it.get("category"):
        category, cat_inferred = category_label(it["category"], lang), False
    else:
        category, cat_inferred = None, True
    if it.get("importance"):
        importance, imp_inferred = it["importance"], False
    else:
        importance = "high" if category_key(it.get("category")) == "decisions" else "normal"
        imp_inferred = True
    privacy = it.get("privacy") or ("private" if it.get("sensitivity") == "private" else "normal")
    return {
        "when": when,
        "estimated": estimated,
        "category": category,
        "category_inferred": cat_inferred,
        "importance": importance,
        "importance_inferred": imp_inferred,
        "privacy": privacy,
    }


def format_line(it, lang, with_category=False, category=None, history=None):
    """The line a record becomes in a note or the journal."""
    tags = item_tags(it, lang)
    src = (it.get("source") or {}).get("ref")
    cat = None
    if with_category:
        cat = category or tags["category"]
    mark = marker(it["provenance"], when=tags["when"], source=src, importance=tags["importance"], category=cat, lang=lang)
    text = re.sub(r"\s+", " ", it.get("text") or "").strip()
    return "- %s %s%s" % (mark, text, history or "")


# --- the record list behind index, log and health --------------------------

def page_records(lib, entry, text, lang):
    """Records found in one note: every list item that carries a source label."""
    out = []
    default_cat = page_category(lib, entry["path"], entry.get("title"), lang)
    for rec in parse_lines(text):
        cat = rec.get("category")
        out.append(
            {
                "id": "%s:%d" % (entry["path"], rec["line"]),
                "text": rec["text"],
                "provenance": rec["provenance"],
                "when": rec["when"],
                "estimated": False,
                "category": category_label(cat, lang) if cat else default_cat,
                "category_inferred": not cat,
                "importance": rec["importance"],
                "privacy": "normal",
                "level": entry["tier"],
                "where": entry["path"],
                "line": rec["line"],
                "source": "journal" if entry.get("stream") else "note",
                "status": "filed",
                "raw": rec["raw"],
            }
        )
    return out


def outdated_pairs(page_recs):
    """Look-alike lines in the same note said at different times: the older one may be out of date."""
    by_page = {}
    for r in page_recs:
        if r["source"] == "note" and r.get("when"):
            by_page.setdefault(r["where"], []).append(r)
    pairs = []
    for path, recs in by_page.items():
        recs = sorted(recs, key=lambda r: time_key(r["when"]))
        for i, old in enumerate(recs):
            for new in recs[i + 1:]:
                if day_of(old["when"]) == day_of(new["when"]) or squash(old["text"]) == squash(new["text"]):
                    continue
                if similarity(old["text"], new["text"]) >= SIMILAR:
                    pairs.append(
                        {
                            "path": path,
                            "older": {"line": old["line"], "when": old["when"], "text": old["text"][:80]},
                            "newer": {"line": new["line"], "when": new["when"], "text": new["text"][:80]},
                        }
                    )
    return pairs


def _item_record(it, lang):
    tags = item_tags(it, lang)
    sug = (it.get("suggest") or {}).get("target")
    category = tags["category"]
    if not category:
        category = page_category_for_target(it, sug, lang)
    importance = tags["importance"]
    return {
        "id": it["id"],
        "text": re.sub(r"\s+", " ", it.get("text") or "").strip(),
        "provenance": it["provenance"],
        "when": tags["when"],
        "estimated": tags["estimated"],
        "category": category,
        "category_inferred": tags["category_inferred"],
        "importance": importance,
        "importance_inferred": tags["importance_inferred"],
        "privacy": "normal",
        "level": "L0" if importance == "high" else "L1",
        "where": None,
        "line": None,
        "source": "inbox",
        "status": it.get("status"),
        "replaces": it.get("replaces"),
    }


def page_category_for_target(it, target, lang):
    if not target:
        return builtin_label("unsorted", lang)
    key = None
    if target.lower() == "me.md":
        key = "me"
    elif target.lower() == "decisions.md":
        key = "decisions"
    if key:
        return builtin_label(key, lang)
    return target.split("/", 1)[0] if "/" in target else Path(target).stem


def collect(lib, include_duplicates=False):
    """Every record an agent may see, plus counts of the private ones it may not."""
    from . import inbox
    from .scan import load_index, scan_library

    lang = lib_lang(lib)
    load_index(lib)
    data = read_json(lib.out("records.json"))
    if not data or data.get("schema") != "brainlib/records@0.1":
        scan_library(lib, write=True)
        data = read_json(lib.out("records.json")) or {}
    recs = [dict(r) for r in data.get("records") or []]
    hidden = dict(data.get("private_hidden") or {})
    restated = []
    for it in inbox.all_items(lib):
        if it.get("sensitivity") == "private" or not it.get("text"):
            if it.get("sensitivity") == "private" and it["status"] in inbox.NOT_FILED + ("private-held",):
                level = it.get("privacy") or "private"
                hidden[level] = hidden.get(level, 0) + 1
            continue
        if it["status"] in inbox.NOT_FILED:
            recs.append(_item_record(it, lang))
        elif it["status"] == "duplicate":
            restated.append(it)
    unfiled = [r for r in recs if r["source"] == "inbox"]
    for r in unfiled:
        old = replaced_item(r, unfiled)
        if old:
            old["superseded_by"] = "inbox:%s" % r["id"]
    if not include_duplicates:
        recs = [r for r in recs if not (r["source"] == "inbox" and r.get("superseded_by"))]
    else:
        for r in recs:
            if r["source"] == "inbox" and r.get("superseded_by"):
                r["twin"] = True
    filed, replaced = {}, []
    for r in recs:
        if r["source"] != "journal":
            filed.setdefault(squash(r["text"]), []).append(r)
            old = history_of(r["text"]) if r["source"] == "note" else None
            if old and squash(old):
                replaced.append((squash(old), r))
    out = []
    for r in recs:
        if r["source"] == "journal":
            sq = squash(r["text"])
            twins = filed.get(sq)
            if twins:
                for t in twins:
                    if time_key(r.get("when")) > time_key(t.get("last_said") or t.get("when")):
                        t["last_said"] = r["when"]
            newer = next((n for old, n in replaced if sq.startswith(old) and time_key(n["when"]) >= time_key(r["when"])), None)
            if newer:
                r["superseded_by"] = "%s:%s" % (newer["where"], newer["line"])
            if twins or newer:
                if not include_duplicates:
                    continue
                r["twin"] = True
        out.append(r)
    for it in restated:
        when = minute(it.get("said_at")) or minute(it.get("captured_at"))
        for t in filed.get(squash(it.get("text")), []):
            if time_key(when) > time_key(t.get("last_said") or t.get("when")):
                t["last_said"] = when
    return out, hidden


def matches_category(rec, wanted):
    if not wanted:
        return True
    w = str(wanted).strip().lower()
    key = category_key(w)
    cat = str(rec.get("category") or "")
    if cat.lower() == w:
        return True
    if key and category_key(cat) == key:
        return True
    where = rec.get("where") or ""
    return bool(where) and (where.lower() == w or where.lower().startswith(w.rstrip("/") + "/"))


def select(records, sort="time", category=None, importance=None, since=None, until=None, levels=None, privacy=None):
    """Filter and sort records. Newest first unless sorting by another tag, then newest first within it."""
    imp = normalize_importance(importance) if importance else None
    priv = normalize_privacy(privacy) if privacy else None
    lv = {str(x).strip().upper() for x in (levels or []) if str(x).strip()}
    bad = lv - set(LEVELS)
    if bad:
        raise BrainError("Unknown level %s." % ", ".join(sorted(bad)), fix="Use L0, L1, L2 or L3.")
    lo = parse_date(since) if since else None
    hi = parse_date(until) if until else None
    if since and lo is None or until and hi is None:
        raise BrainError("Dates must look like 2026-10-20.", fix="Use --since YYYY-MM-DD and --until YYYY-MM-DD.")
    out = []
    for r in records:
        if not matches_category(r, category):
            continue
        if imp and r.get("importance") != imp:
            continue
        if priv and r.get("privacy", "normal") != priv:
            continue
        if lv and r.get("level") not in lv:
            continue
        day = parse_date(day_of(r.get("last_said") or r.get("when")))
        if lo and (day is None or day < lo):
            continue
        if hi and (day is None or day > hi):
            continue
        out.append(r)
    if sort not in SORTS:
        raise BrainError("Unknown sort %r." % sort, fix="Use one of: %s." % ", ".join(SORTS))
    out.sort(key=lambda r: time_key(r.get("last_said") or r.get("when")), reverse=True)
    if sort == "importance":
        out.sort(key=lambda r: IMPORTANCE.index(r.get("importance", "normal")))
    elif sort == "category":
        out.sort(key=lambda r: str(r.get("category") or "").lower())
    elif sort == "privacy":
        out.sort(key=lambda r: PRIVACY.index(r.get("privacy", "normal")))
    elif sort == "level":
        out.sort(key=lambda r: LEVELS.index(r.get("level", "L2")) if r.get("level") in LEVELS else 9)
    return out


def render(r, lang):
    """One line for agents: when, level, source label, text, then category, importance and where."""
    when = r.get("when") or "time unknown"
    if r.get("estimated") and len(when) == 16:
        when = "%s ~%s" % (when[:10], when[11:])
    label = provenance.LEVELS[r["provenance"]]["marker"]
    bits = [r.get("category") or "?"]
    word = importance_word(r.get("importance"), "en")
    if word:
        bits.append(word)
    if r.get("where"):
        bits.append("%s:%s" % (r["where"], r["line"]) if r.get("line") else r["where"])
    else:
        bits.append("not filed yet")
    if r.get("last_said") and time_key(r["last_said"]) > time_key(r.get("when")):
        bits.append("said again %s" % r["last_said"])
    if r.get("superseded_by"):
        bits.append("replaced later, see %s" % r["superseded_by"])
    text = r["text"] if len(r["text"]) <= 200 else r["text"][:199] + "…"
    return "%s  %s  [%s] %s  (%s)" % (when, r.get("level", "?"), label, text, " · ".join(bits))


def recent_journal_days(records, days=7):
    """Journal files of the last few days, with how many records each holds."""
    cutoff = (now().date() - timedelta(days=days - 1)).isoformat()
    counts = {}
    for r in records:
        if r.get("source") == "journal" and r.get("where"):
            day = Path(r["where"]).stem[:10]
            if day >= cutoff:
                counts[r["where"]] = counts.get(r["where"], 0) + 1
    return sorted(counts.items(), reverse=True)


CAPS = {"important": 10, "recent": 20, "outdated": 5, "journal_days": 7}


def index_view(lib):
    """The record sections of the default index, each with a fixed cap, newest said first."""
    recs, hidden = collect(lib, include_duplicates=True)
    shown = select([r for r in recs if not r.get("twin")])
    important = [r for r in shown if r["source"] == "inbox" and r.get("importance") == "high"]
    listed = {r["id"] for r in important[: CAPS["important"]]}
    recent = [r for r in shown if r["id"] not in listed and r.get("level") != "L3"]
    by_line = {(r.get("where"), r.get("line")): r for r in recs if r.get("where")}
    outdated = []
    for o in (read_json(lib.out("reports.json")) or {}).get("outdated") or []:
        old, new = by_line.get((o["path"], o["older_line"])), by_line.get((o["path"], o["newer_line"]))
        if old and new:
            outdated.append({"path": o["path"], "older": old, "newer": new})
    return {
        "important": important[: CAPS["important"]],
        "important_more": max(0, len(important) - CAPS["important"]),
        "journal_days": recent_journal_days(recs, CAPS["journal_days"]),
        "recent": recent[: CAPS["recent"]],
        "recent_more": max(0, len(recent) - CAPS["recent"]),
        "outdated": outdated[: CAPS["outdated"]],
        "outdated_more": max(0, len(outdated) - CAPS["outdated"]),
        "total": len(shown),
        "private_hidden": hidden,
    }


def day_view(lib, day=None, days=7):
    """Records grouped by the day they were said: one day, or the last few days that have any."""
    recs, hidden = collect(lib, include_duplicates=True)
    seen, by_day = set(), {}
    rank = {"note": 0, "inbox": 1, "journal": 2}
    for r in sorted(recs, key=lambda r: rank.get(r.get("source"), 3)):
        if not r.get("when"):
            continue
        key = (squash(r["text"]), r["when"])
        if key in seen:
            continue
        seen.add(key)
        by_day.setdefault(day_of(r["when"]), []).append(r)
    if day:
        d = parse_date(day)
        if d is None:
            raise BrainError("Dates must look like 2026-10-20.", fix="Use --day YYYY-MM-DD.")
        wanted = [d.isoformat()]
    else:
        cutoff = (now().date() - timedelta(days=max(1, days) - 1)).isoformat()
        wanted = sorted((k for k in by_day if k >= cutoff), reverse=True)
    out = []
    for k in wanted:
        rows = sorted(by_day.get(k, []), key=lambda r: time_key(r["when"]))
        out.append({"day": k, "records": rows})
    return out, hidden
