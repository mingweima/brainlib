"""Find the library, load its optional config, and decide where state and outputs live.

A library is any folder of Markdown notes. Config is optional: with no config at all,
brainlib runs read-only with safe defaults (level 0). `brainlib init` / `brainlib adopt`
write `.brainlib/config.json` inside the library; it holds settings only, never content.

State (inbox, proposals, receipts, profile) and outputs (index, reading guide, reports)
live outside the library by default, under ~/.brainlib/libraries/<library-id>/, so
synced folders never carry conversation snippets or derived copies.
"""

import copy
import hashlib
import json
import os
from pathlib import Path

from .util import BrainError, ensure_private_dir, read_json, slug, strip_dot_slash, write_json

CONFIG_DIR = ".brainlib"
CONFIG_FILE = "config.json"

TIERS = ("L0", "L1", "L2", "L3")
AUTHORITIES = ("canonical", "pointer", "archived")
SENSITIVITIES = ("public", "internal", "private", "secret")

# Older or localized values that must keep working (backward compatibility).
AUTHORITY_ALIASES = {
    "权威": "canonical",
    "指针": "pointer",
    "归档": "archived",
    "stable": "canonical",
    "deprecated": "archived",
    "stub": "pointer",
}

DEFAULTS = {
    "brainlib_config": 1,
    "owner": "human:me",
    "library_name": None,
    "zones": [
        {"path": "_archive/", "authority": "archived", "tier": "L3"},
    ],
    "fallback_note": "inbox-unsorted.md",
    "stream_days": 14,
    "ttl_days": {"L0": 90, "L1": 180, "L2": 365, "L3": 0},
    "ignore": [".git/", ".obsidian/", ".trash/", ".brainlib/", "node_modules/", ".venv/"],
    "vault_dir": "vault/",
    "state_dir": None,
    "out_dir": None,
    "privacy": {"words_file": None},
    "settings": {},
}


def brainlib_home():
    return Path(os.environ.get("BRAINLIB_HOME") or (Path.home() / ".brainlib"))


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def find_config_root(start):
    p = Path(start).resolve()
    for candidate in [p] + list(p.parents):
        if (candidate / CONFIG_DIR / CONFIG_FILE).is_file():
            return candidate
    return None


def global_state():
    """Settings that belong to the person, not to one library: language and agent self-checks."""
    return read_json(brainlib_home() / "global.json", default={}) or {}


def save_global_state(data):
    ensure_private_dir(brainlib_home())
    write_json(brainlib_home() / "global.json", data)


def registry_path():
    return brainlib_home() / "registry.json"


def registry():
    return read_json(registry_path(), default={"default": None, "libraries": {}})


def register(root, make_default=True):
    reg = registry()
    root = str(Path(root).resolve())
    reg.setdefault("libraries", {})[root] = {"registered": True}
    if make_default or not reg.get("default"):
        reg["default"] = root
    ensure_private_dir(brainlib_home())
    write_json(registry_path(), reg)


class Library:
    def __init__(self, root, config, has_config):
        self.root = Path(root).resolve()
        self.config = config
        self.has_config = has_config
        name = config.get("library_name") or self.root.name or "library"
        self.name = name
        lib_id = config.get("library_id")
        if not lib_id:
            digest = hashlib.sha1(str(self.root).encode("utf-8")).hexdigest()[:8]
            lib_id = "%s-%s" % (slug(name, "library"), digest)
        self.id = lib_id
        base = brainlib_home() / "libraries" / self.id
        self.state_dir = Path(config.get("state_dir") or (base / "state")).expanduser()
        self.out_dir = Path(config.get("out_dir") or (base / "out")).expanduser()

    # --- paths -------------------------------------------------------------
    @property
    def owner(self):
        return self.config.get("owner") or "human:me"

    @property
    def vault_dir(self):
        return self.root / (self.config.get("vault_dir") or "vault/").strip("/")

    @property
    def config_path(self):
        return self.root / CONFIG_DIR / CONFIG_FILE

    def state(self, *parts):
        ensure_private_dir(self.state_dir)
        return self.state_dir.joinpath(*parts)

    def out(self, *parts):
        ensure_private_dir(self.out_dir)
        return self.out_dir.joinpath(*parts)

    # --- zones -------------------------------------------------------------
    def zone_for(self, rel):
        """Merge every zone whose path prefix matches `rel` (longest prefix wins)."""
        rel = rel.replace("\\", "/")
        merged = {}
        zones = sorted(self.config.get("zones") or [], key=lambda z: len(z.get("path", "")))
        for z in zones:
            prefix = strip_dot_slash(z.get("path") or "")
            if not prefix:
                continue
            if not prefix.endswith("/") and not prefix.endswith(".md"):
                prefix += "/"
            if rel == prefix or rel.startswith(prefix):
                merged.update({k: v for k, v in z.items() if k != "path"})
        return merged

    def is_ignored(self, rel):
        rel = rel.replace("\\", "/")
        vault = (self.config.get("vault_dir") or "vault/").strip("/") + "/"
        for pat in list(self.config.get("ignore") or []) + [vault]:
            pat = strip_dot_slash(pat)
            if not pat:
                continue
            if pat.endswith("/"):
                if rel.startswith(pat) or ("/" + pat) in ("/" + rel):
                    return True
            elif rel == pat:
                return True
        parts = rel.split("/")
        return any(p.startswith(".") for p in parts[:-1])

    def words_file(self):
        p = os.environ.get("BRAINLIB_PRIVATE_WORDS") or (self.config.get("privacy") or {}).get("words_file")
        return Path(p).expanduser() if p else None

    def settings_override(self):
        return self.config.get("settings") or {}


def load(library=None, cwd=None, required=True):
    """Locate the library and return a Library.

    Order: explicit path, BRAINLIB_LIBRARY, a .brainlib/ folder above the current
    directory, the registered default library.
    """
    root = None
    if library:
        root = Path(library).expanduser()
        if not root.is_dir():
            raise BrainError(
                "Library folder not found: %s" % library,
                fix="Check the path. A library is just a folder of Markdown notes.",
            )
    elif os.environ.get("BRAINLIB_LIBRARY"):
        root = Path(os.environ["BRAINLIB_LIBRARY"]).expanduser()
    else:
        found = find_config_root(cwd or os.getcwd())
        if found:
            root = found
        else:
            default = registry().get("default")
            if default and Path(default).is_dir():
                root = Path(default)
    if root is None:
        if not required:
            return None
        raise BrainError(
            "No library selected.",
            fix=(
                "Ask the user which folder holds their notes, then pass it with --library PATH, "
                "or run `brainlib init PATH` (new library) / `brainlib adopt PATH` (existing notes)."
            ),
        )
    root = root.resolve()
    cfg_path = root / CONFIG_DIR / CONFIG_FILE
    raw = {}
    has_config = cfg_path.is_file()
    if has_config:
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise BrainError(
                "Config file is not valid JSON: %s (%s)" % (cfg_path, e),
                fix="Fix the JSON syntax, or move the file away to fall back to defaults.",
            )
    config = _merge(DEFAULTS, raw)
    if raw.get("zones") is not None:
        config["zones"] = raw["zones"]
    return Library(root, config, has_config)


def write_config(root, values):
    root = Path(root).resolve()
    path = root / CONFIG_DIR / CONFIG_FILE
    existing = read_json(path, default={}) or {}
    merged = dict(existing)
    merged.update(values)
    merged.setdefault("brainlib_config", 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, merged, private=False)
    return path
