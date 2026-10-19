"""Where a statement came from. The most important field in the library.

Only the first three levels may be used as the owner's own view. Agent inferences,
guesses and outside material can never be silently promoted to the owner's name; the
only promotion path is the owner explicitly saying they adopt it.
"""

from .util import BrainError

LEVELS = {
    "principal-said": {
        "aliases": ["said", "quote", "owner-said"],
        "owner_view": True,
        "marker": "said",
        "en": "you said",
        "zh": "你说的",
        "help": "The owner's own words, quoted exactly, with when they said it.",
    },
    "principal-judgment": {
        "aliases": ["judgment", "judgement", "view", "owner-view"],
        "owner_view": True,
        "marker": "judgment",
        "en": "your view",
        "zh": "你的看法",
        "help": "A view the owner clearly expressed, paraphrased.",
    },
    "principal-authored": {
        "aliases": ["extracted", "authored", "from-owner-writing"],
        "owner_view": True,
        "marker": "extracted",
        "en": "from your writing",
        "zh": "摘自你写的东西",
        "help": "Extracted from something the owner wrote. The extraction is the agent's work and can be wrong; cite the file.",
    },
    "agent-inference": {
        "aliases": ["inferred", "inference", "agent"],
        "owner_view": False,
        "marker": "inferred",
        "en": "agent inferred",
        "zh": "助手推断",
        "help": "An agent's conclusion with stated evidence. Not the owner's view.",
    },
    "agent-guess": {
        "aliases": ["guess", "guessed"],
        "owner_view": False,
        "marker": "guess",
        "en": "agent guess",
        "zh": "助手猜测",
        "help": "An agent's guess without evidence. Prefer not writing it at all.",
    },
    "third-party": {
        "aliases": ["external", "web", "source", "outside"],
        "owner_view": False,
        "marker": "external",
        "en": "outside source",
        "zh": "外部资料",
        "help": "Anything from outside: web pages, articles, emails, other people. Always name the source.",
    },
}

_ALIASES = {}
for _key, _info in LEVELS.items():
    _ALIASES[_key] = _key
    for _a in _info["aliases"]:
        _ALIASES[_a] = _key


def normalize(value):
    key = _ALIASES.get(str(value or "").strip().lower())
    if not key:
        raise BrainError(
            "Unknown provenance: %r" % value,
            fix=(
                "Use one of: said (the user's exact words), judgment (a view the user stated), "
                "extracted (from the user's own writing), inferred (your conclusion), guess, "
                "external (outside material)."
            ),
        )
    return key


def is_owner_view(key):
    return LEVELS[normalize(key)]["owner_view"]


def marker(key, date=None, source=None):
    """Inline marker written into notes, e.g. [said 2026-10-20] or [external: example.org]."""
    info = LEVELS[normalize(key)]
    m = info["marker"]
    if m == "said" and date:
        return "[said %s]" % date
    if m == "external" and source:
        return "[external: %s]" % source
    if m == "extracted" and source:
        return "[extracted: %s]" % source
    return "[%s]" % m


def label(key, lang="en"):
    info = LEVELS[normalize(key)]
    return info.get(lang) or info["en"]
