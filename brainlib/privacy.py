"""Privacy rules: detect secrets and personal data, resolve sensitivity, scan files.

Never print a full secret. Findings carry a masked excerpt, a rule name and a location.

Lines containing the marker `brainlib:allow` are skipped (for documented false positives).
"""

import datetime as _dt
import fnmatch
import os
import re
import subprocess
from pathlib import Path

from .config import SENSITIVITIES
from .util import BrainError, EXIT_PRIVACY, mask

ALLOW_MARKER = "brainlib:allow"

# (rule, kind, regex). kind: secret | personal | contact | path
_RULES = [
    ("private-key-block", "secret", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"),
    ("age-secret-key", "secret", r"AGE-SECRET-KEY-1[0-9A-Z]{50,}"),
    ("aws-access-key", "secret", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("github-token", "secret", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ("api-key-sk", "secret", r"\bsk-(?:ant-|proj-|live-)?[A-Za-z0-9_\-]{24,}\b"),
    ("slack-token", "secret", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    ("google-api-key", "secret", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("stripe-live-key", "secret", r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b"),
    ("jwt", "secret", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    (
        "password-assignment",
        "secret",
        r"(?i)(?:\b(?:password|passwd|passcode|pwd)\b|密码|口令)\s*(?:is\s+|是)?[:=：]\s*[^\s,;，；]{4,}",
    ),
    (
        "password-phrase",
        "secret",
        r"(?i)(?:\b(?:password|passwd|passcode|pwd|pin)\b|密码|口令)\s*(?:is|是|为)\s*(?=[^\s,;，；。]*[0-9!@#$%^&*])[^\s,;，；。]{4,}",
    ),
    ("cn-mobile", "personal", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ("email", "contact", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("home-path", "path", r"(?:/Users/[^/\s]+/|/home/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)"),  # brainlib:allow
]
_COMPILED = [(r, k, re.compile(p)) for r, k, p in _RULES]

_ID18 = re.compile(r"(?<![0-9A-Za-z])(\d{17}[\dXx])(?![0-9A-Za-z])")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

# Placeholders that look like secrets in docs and tests but are not.
_PLACEHOLDER = re.compile(r"(?i)(example|placeholder|your[-_]?(?:key|token|password)|xxxx|\*\*\*\*|<[^>]+>)")
# Addresses that are reserved for examples or are not personal.
_NEUTRAL_EMAIL = re.compile(r"(?i)@(?:[\w-]+\.)*(?:example\.(?:com|org|net)|example|test|invalid|localhost|users\.noreply\.github\.com)$")


def _valid_cn_id(s):
    s = s.upper()
    try:
        _dt.date(int(s[6:10]), int(s[10:12]), int(s[12:14]))
    except ValueError:
        return False
    if not (1900 <= int(s[6:10]) <= 2099):
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    total = sum(int(c) * w for c, w in zip(s[:17], weights))
    return "10X98765432"[total % 11] == s[17]  # brainlib:allow (check-digit table from GB 11643)


def _luhn(digits):
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


class Hit:
    __slots__ = ("rule", "kind", "line", "excerpt", "path")

    def __init__(self, rule, kind, line, excerpt, path=None):
        self.rule, self.kind, self.line, self.excerpt, self.path = rule, kind, line, excerpt, path

    def as_dict(self):
        d = {"rule": self.rule, "kind": self.kind, "line": self.line, "excerpt": self.excerpt}
        if self.path:
            d["path"] = self.path
        return d

    def __repr__(self):
        return "Hit(%s,%s,line %s)" % (self.rule, self.kind, self.line)


def scan_text(text, kinds=("secret", "personal"), words=None, allowed_phrases=None):
    """Return a list of Hit. `words` is an optional list of private terms (case-insensitive).

    `allowed_phrases` are exact phrases that may contain private terms on purpose (for
    example the author's name in a copyright line); only those occurrences are skipped.
    """
    hits = []
    lowered_words = [w.lower() for w in (words or []) if w.strip()]
    lowered_allowed = sorted({p.lower() for p in (allowed_phrases or []) if p.strip()}, key=len, reverse=True)
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for rule, kind, rx in _COMPILED:
            if kind not in kinds:
                continue
            for m in rx.finditer(line):
                value = m.group(0)
                if kind == "secret" and _PLACEHOLDER.search(value):
                    continue
                if kind == "contact" and _NEUTRAL_EMAIL.search(value):
                    continue
                hits.append(Hit(rule, kind, lineno, mask(value)))
        if "personal" in kinds:
            for m in _ID18.finditer(line):
                if _valid_cn_id(m.group(1)):
                    hits.append(Hit("cn-resident-id", "personal", lineno, mask(m.group(1))))
            for m in _CARD.finditer(line):
                digits = re.sub(r"\D", "", m.group(0))
                if 13 <= len(digits) <= 19 and digits[0] in "3456" and _luhn(digits):
                    hits.append(Hit("payment-card", "personal", lineno, mask(digits)))
        if lowered_words:
            low = line.lower()
            for phrase in lowered_allowed:
                low = low.replace(phrase, " " * len(phrase))
            for w in lowered_words:
                if w in low:
                    hits.append(Hit("private-word", "word", lineno, mask(w, keep=1)))
    return hits


# Personal numbers that are refused like secrets: they enable fraud if leaked.
REFUSED_PERSONAL = ("payment-card", "cn-resident-id")


def find_secret(text):
    """Return the first Hit for a secret, a payment card or an ID number, or None."""
    for h in scan_text(text, kinds=("secret", "personal")):
        if h.kind == "secret" or h.rule in REFUSED_PERSONAL:
            return h
    return None


def refuse_if_secret(text, what="This text"):
    hit = find_secret(text)
    if hit:
        raise BrainError(
            "%s looks like it contains a password, key, card number or ID number (%s). It was NOT saved." % (what, hit.rule),
            fix=(
                "Keep secrets in a password manager. In the library, write only where to find it, "
                "for example 'bank login: in my password manager under Bank'."
            ),
            code=EXIT_PRIVACY,
        )


def load_words(path):
    if not path:
        return None
    path = Path(path).expanduser()
    if not path.is_file():
        return None
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line)
    return words


def resolve_sensitivity(front_matter, zone):
    value = (front_matter or {}).get("sensitivity") or (zone or {}).get("sensitivity") or "internal"
    value = str(value).strip().lower()
    return value if value in SENSITIVITIES else "internal"


def is_readable_by_agents(sensitivity):
    return sensitivity in ("public", "internal")


# --- repository / file scanning -------------------------------------------------

TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".py", ".json", ".toml", ".cfg", ".ini", ".yml", ".yaml",
    ".sh", ".js", ".ts", ".html", ".css", ".csv", "", ".gitignore",
}


def git_files(root, staged=False):
    cmd = ["git", "-C", str(root), "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"] if staged else [
        "git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        raise BrainError("Not a git repository: %s" % root, fix="Run inside a git repository or pass file paths.")
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


ALLOW_FILE = ".brainlib-allow"


def load_allow(root):
    """Read `.brainlib-allow`: lines of `<path glob> <phrase>` that may name private terms on purpose."""
    path = Path(root) / ALLOW_FILE
    entries = []
    if not path.is_file():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip():
            entries.append((parts[0], parts[1].strip()))
    return entries


def scan_files(root, paths, mode, words_path=None):
    """Scan files for privacy problems.

    mode: 'library' (secrets + personal data), 'commit' (also home paths and the private
    word list if present), 'release' (like commit, but a missing word list is an error).
    Returns (hits, notes) where notes are human-readable warnings.
    """
    root = Path(root)
    notes = []
    allow = load_allow(root)
    if allow:
        notes.append(
            "%d allowed phrase(s) from %s (review them: each one is deliberately public)" % (len(allow), ALLOW_FILE)
        )
    kinds = ("secret", "personal") if mode == "library" else ("secret", "personal", "contact", "path")
    words = None
    if mode in ("commit", "release"):
        words_path = words_path or os.environ.get("BRAINLIB_PRIVATE_WORDS")
        words = load_words(words_path)
        if words is None:
            if mode == "release":
                raise BrainError(
                    "Release scan needs your private word list, and none was found.",
                    fix=(
                        "Create a text file outside the repo with one private term per line (your names, "
                        "company, home paths) and pass --words PATH or set BRAINLIB_PRIVATE_WORDS. "
                        "A release scan without it could pass while leaking."
                    ),
                    code=EXIT_PRIVACY,
                )
            notes.append("private word list not found: only generic rules were checked (set BRAINLIB_PRIVATE_WORDS)")
    hits = []
    for rel in paths:
        p = root / rel
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        allowed = [phrase for glob, phrase in allow if fnmatch.fnmatch(rel, glob)]
        for h in scan_text(text, kinds=kinds, words=words, allowed_phrases=allowed):
            if h.kind == "contact" and mode == "library":
                continue
            h.path = rel
            hits.append(h)
    return hits, notes
