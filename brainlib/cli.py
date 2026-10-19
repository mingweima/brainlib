"""Command line. Run `brainlib next` when unsure what to do.

Every error prints two lines, `ERROR:` and `FIX:`, and exits with a documented code:
0 ok, 1 findings, 2 usage, 3 privacy, 4 approval needed, 5 conflict.
"""

import argparse
import builtins
import functools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import (
    __version__,
    agentcheck,
    checks,
    classify,
    config,
    connect,
    doctor,
    i18n,
    inbox,
    nextstep,
    onboard,
    privacy,
    proposals,
    provenance,
    scan,
    vault,
)
from .scan import build_entry
from .util import (
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_PRIVACY,
    EXIT_USAGE,
    BrainError,
    command_lock,
    rel_posix,
    safe_resolve,
    slug,
)

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES = PACKAGE_DIR / "data" / "templates" / "library"
MAX_READ_BYTES = 200_000


# --- helpers ----------------------------------------------------------------

SUBCOMMANDS = (
    "next", "init", "adopt", "scan", "index", "find", "read", "health", "lint", "note", "inbox", "classify",
    "propose", "review", "apply", "reject", "defer", "undo", "onboard", "privacy", "hooks", "vault", "mcp",
    "selftest", "version", "lang", "doctor", "agent-check", "connect",
)
_CMD_RE = re.compile(r"(?<![\w/\\.-])brainlib (?=(?:%s)\b)" % "|".join(sorted(SUBCOMMANDS, key=len, reverse=True)))


def brainlib_cmd():
    """The exact way to run brainlib on this computer, usable from any folder."""
    env = os.environ.get("BRAINLIB_PREFIX")
    if env:
        return env
    argv0 = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if argv0 in ("brainlib", "brainlib.exe") and shutil.which("brainlib"):
        return "brainlib"
    launcher = PACKAGE_DIR.parent / "brainlib.py"
    if launcher.is_file():
        return '%s "%s"' % (_python(), launcher)
    if shutil.which("brainlib"):
        return "brainlib"
    return "%s -m brainlib" % _python()


@functools.lru_cache(maxsize=None)
def _python():
    """How a fresh terminal starts a Python that can run brainlib: the usual short name when it is this
    Python or also new enough, otherwise the full path of the Python running now."""
    for name in ("py -3", "python") if os.name == "nt" else ("python3",):
        exe = shutil.which(name.split()[0])
        if exe and (_same_file(exe, sys.executable) or _new_enough(name)):
            return name
    if not sys.executable:
        return "python" if os.name == "nt" else "python3"
    return '"%s"' % sys.executable if " " in sys.executable else sys.executable


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except (OSError, TypeError, ValueError):
        return False


def _new_enough(name):
    try:
        return subprocess.run(
            name.split() + ["-c", "import sys; sys.exit(sys.version_info < (3, 9))"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def rewrite(text):
    """Replace `brainlib <command>` with the full command for this computer, so agents can copy it as is."""
    prefix = brainlib_cmd()
    if prefix == "brainlib" or not isinstance(text, str):
        return text
    return _CMD_RE.sub(lambda _m: prefix + " ", text)


def print(*args, **kwargs):  # noqa: A001 - every line printed by the CLI goes through rewrite()
    builtins.print(*(rewrite(a) for a in args), **kwargs)


def _rewrite_deep(obj):
    if isinstance(obj, str):
        return rewrite(obj)
    if isinstance(obj, list):
        return [_rewrite_deep(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _rewrite_deep(v) for k, v in obj.items()}
    return obj


def print_json(obj, **kwargs):
    builtins.print(json.dumps(_rewrite_deep(obj), **kwargs))


def _lang(args, lib=None):
    for value in (
        getattr(args, "lang", None),
        os.environ.get("BRAINLIB_LANG"),
        lib.config.get("lang") if lib else None,
        config.global_state().get("lang"),
    ):
        if i18n.normalize(value):
            return i18n.normalize(value)
    return i18n.DEFAULT_LANG


def _actor(args):
    return getattr(args, "as_", None) or os.environ.get("BRAINLIB_ACTOR") or "agent/unknown"


def _emit(args, data, text):
    if getattr(args, "json", False):
        print_json(data, ensure_ascii=False, indent=2, default=str)
    else:
        print(text)


def _lib(args, required=True):
    return config.load(getattr(args, "library", None), required=required)


def _short(text, n=100):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


# --- setup ------------------------------------------------------------------

def _detect_zones(root):
    zones = [{"path": "_archive/", "authority": "archived", "tier": "L3"}]
    for child in sorted(Path(root).iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        low = child.name.lower()
        if low in ("journal", "journals", "daily", "dailies", "diary", "log", "logs"):
            zones.append({"path": child.name + "/", "stream": True, "auto_apply": True})
        elif low in ("private", "personal-private", "secret", "secrets"):
            zones.append({"path": child.name + "/", "sensitivity": "private"})
        elif low in ("archive", "archives", "old") and child.name != "_archive":
            zones.append({"path": child.name + "/", "authority": "archived", "tier": "L3"})
    return zones


def _write_agents_file(root):
    lang = i18n.normalize(config.global_state().get("lang")) or i18n.DEFAULT_LANG
    name = "AGENTS.zh.md" if lang == "zh" and (TEMPLATES / "AGENTS.zh.md").is_file() else "AGENTS.md"
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    text = text.replace("{BRAINLIB_CMD}", brainlib_cmd()).replace("{LIBRARY}", str(Path(root).resolve()))
    (Path(root) / "AGENTS.md").write_text(text, encoding="utf-8")


def cmd_init(args):
    root = Path(args.path).expanduser()
    if root.exists() and any(not p.name.startswith(".") for p in root.iterdir()):
        raise BrainError(
            "%s already has files in it." % root,
            fix="To use existing notes, run `brainlib adopt %s` instead. It never changes your notes." % args.path,
        )
    root.mkdir(parents=True, exist_ok=True)
    lang = _lang(args)
    for name in ("README", "me"):
        src = TEMPLATES / ("%s.zh.md" % name if lang == "zh" else "%s.md" % name)
        shutil.copyfile(src, root / ("%s.md" % name))
    for d in ("journal", "private", "_archive"):
        (root / d).mkdir(exist_ok=True)
    _write_agents_file(root)
    values = {
        "library_name": args.name or root.resolve().name,
        "owner": "human:%s" % slug(args.owner, "me") if args.owner else "human:me",
        "zones": [
            {"path": "journal/", "stream": True, "auto_apply": True},
            {"path": "private/", "sensitivity": "private"},
            {"path": "_archive/", "authority": "archived", "tier": "L3"},
        ],
        "ignore": list(config.DEFAULTS["ignore"]) + ["AGENTS.md"],
    }
    if getattr(args, "lang", None):
        values["lang"] = args.lang
    config.write_config(root, values)
    config.register(root, make_default=True)
    lib = config.load(str(root))
    scan.scan_library(lib)
    _emit(
        args,
        {"ok": True, "library": str(lib.root), "id": lib.id},
        "CREATED a new library at %s\n"
        "  me.md (your most important page), README.md, journal/, private/, _archive/, AGENTS.md\n"
        "  This is now your default library.\n"
        "NEXT: run `brainlib next`" % lib.root,
    )
    return EXIT_OK


def cmd_adopt(args):
    root = Path(args.path).expanduser()
    if not root.is_dir():
        raise BrainError("Folder not found: %s" % root, fix="Check the path to the notes folder.")
    existing = config.find_config_root(root)
    values = {}
    if not (existing and Path(existing).resolve() == root.resolve()):
        values = {
            "library_name": args.name or root.resolve().name,
            "owner": "human:%s" % slug(args.owner, "me") if args.owner else "human:me",
            "zones": _detect_zones(root),
        }
    if getattr(args, "lang", None):
        values["lang"] = args.lang
    if values:
        config.write_config(root, values)
    config.register(root, make_default=True)
    if args.agents_file:
        if (root / "AGENTS.md").exists():
            raise BrainError("AGENTS.md already exists in that folder; it was left alone.", fix="Leave out --agents-file.")
        _write_agents_file(root)
    lib = config.load(str(root))
    result = scan.scan_library(lib)
    entries = result["entries"]
    with_fm = sum(1 for e in entries if e["has_front_matter"])
    hidden = sum(1 for e in entries if not privacy.is_readable_by_agents(e["sensitivity"]))
    zones = [z["path"] for z in lib.config.get("zones") or []]
    _emit(
        args,
        {"ok": True, "library": str(lib.root), "notes": len(entries), "with_front_matter": with_fm, "private_hidden": hidden},
        "ADOPTED %s\n"
        "  %d note(s) found, %d with a front-matter header, %d private (hidden from agents).\n"
        "  Your notes were not changed. Settings are in .brainlib/config.json (zones: %s).\n"
        "NEXT: run `brainlib next`" % (lib.root, len(entries), with_fm, hidden, ", ".join(zones) or "none"),
    )
    return EXIT_OK


# --- reading ----------------------------------------------------------------

def cmd_next(args):
    lib = _lib(args, required=False)
    if lib is not None and (args.snooze or args.done):
        if args.done:
            if args.done not in nextstep.ONE_TIME_STEPS:
                raise BrainError("Unknown step %r." % args.done, fix="Steps you can mark done: %s" % ", ".join(nextstep.ONE_TIME_STEPS))
            nextstep.mark_done(lib, args.done)
            print("OK: %s is done.\nTHEN: run `brainlib next` again." % args.done)
        else:
            until = nextstep.snooze(lib, args.snooze)
            print("OK: %s is snoozed until %s.\nTHEN: run `brainlib next` again." % (args.snooze, until))
        return EXIT_OK
    lang = _lang(args, lib)
    lang_chosen = bool(i18n.normalize(config.global_state().get("lang")) or (lib and i18n.normalize(lib.config.get("lang"))))
    s = nextstep.preflight(_actor(args), lang, lang_chosen)
    if s is None:
        s = nextstep.no_library(lang) if lib is None else nextstep.compute(lib, lang=lang)
    _emit(args, s, nextstep.render(s))
    return EXIT_OK


def cmd_lang(args):
    gs = config.global_state()
    if not args.value:
        current = i18n.normalize(gs.get("lang"))
        print("Language: %s" % (current or "not chosen yet (default %s)" % i18n.DEFAULT_LANG))
        return EXIT_OK
    lang = i18n.normalize(args.value)
    if not lang:
        raise BrainError("Unknown language %r." % args.value, fix="Use zh (中文) or en (English).")
    gs["lang"] = lang
    config.save_global_state(gs)
    print("OK: language set to %s. Speak to the user in this language from now on.\nTHEN: run `brainlib next`." % lang)
    return EXIT_OK


def cmd_doctor(args):
    lib = _lib(args, required=False)
    r = doctor.check(lib)
    _emit(args, r, doctor.render(r))
    return EXIT_OK


def _standalone_cmd():
    """Like brainlib_cmd(), but always runnable from a fresh terminal (MCP sets a bare `brainlib` prefix)."""
    prefix = brainlib_cmd()
    if prefix == "brainlib" and not shutil.which("brainlib"):
        saved = os.environ.pop("BRAINLIB_PREFIX", None)
        try:
            prefix = brainlib_cmd()
        finally:
            if saved is not None:
                os.environ["BRAINLIB_PREFIX"] = saved
    return prefix


def cmd_connect(args):
    lib = _lib(args)
    lang = _lang(args, lib)
    cmd = _standalone_cmd()
    if args.tool and (args.write or args.remove):
        r = connect.remove(args.tool) if args.remove else connect.write(lib, args.tool, cmd, lang)
        if r["changed"]:
            text = "%s %s" % ("REMOVED the brainlib lines from" if args.remove else "ADDED the brainlib lines to", r["file"])
            if r["backup"]:
                text += "\n  The old file was backed up to %s" % r["backup"]
        else:
            text = "NO CHANGE: %s was already up to date." % r["file"]
        text += "\nTHEN: connect the user's other tools, or run: brainlib next --done connect"
        _emit(args, r, text)
        return EXIT_OK
    if args.tool:
        t = connect.TOOLS[args.tool]
        if t["file"]:
            head = "NEXT: Show the user the text below. Only after they say yes, add it to %s.\nRUN: brainlib connect --tool %s --write" % (
                t["file"](),
                args.tool,
            )
        else:
            where = t["where"].get(lang) or t["where"]["en"]
            head = "NEXT: Give the user the text below to paste; brainlib cannot change %s's settings.\nSAY TO USER: %s" % (
                t["name"],
                i18n.t("connect_paste", lang, where=where),
            )
        text = "%s\n--- text ---\n%s\n--- end ---\nTHEN: connect the user's other tools, or run: brainlib next --done connect" % (
            head,
            connect.block(lib, cmd, lang),
        )
        _emit(args, {"tool": args.tool, "file": str(t["file"]()) if t["file"] else None, "text": connect.block(lib, cmd, lang)}, text)
        return EXIT_OK
    _emit(args, {"tools": connect.status(), "text": connect.block(lib, cmd, lang)}, connect.render_status(lib, cmd, lang))
    return EXIT_OK


def cmd_agent_check(args):
    actor = _actor(args)
    action = args.action or "start"
    if action == "start":
        s = agentcheck.start(actor, lang=_lang(args), model=args.model)
        print(agentcheck.render(s))
        return EXIT_OK
    if action == "data":
        print_json(agentcheck.data(), ensure_ascii=False, indent=2)
        return EXIT_OK
    if action == "answer":
        if len(args.rest) < 2:
            raise BrainError("Usage: brainlib agent-check answer <task number> <answer>", fix="For example: brainlib agent-check answer 3 c")
        first = agentcheck.answer(args.rest[0], " ".join(args.rest[1:]))
        print("RECORDED task %s." % args.rest[0] if first else "Task %s was already answered; the first answer counts." % args.rest[0])
        return EXIT_OK
    if action == "finish":
        result, say = agentcheck.finish(model=args.model)
        lines = ["RESULT: %s (%d of %d)" % ("PASS" if result["passed"] else "FAIL", result["score"], result["total"])]
        lines.append("SAY TO USER: %s" % say)
        if not result["passed"]:
            lines.append("THEN: after telling the user, run `brainlib agent-check ack`, then `brainlib next`.")
        else:
            lines.append("THEN: run `brainlib next`.")
        _emit(args, {"result": result, "say": say}, "\n".join(lines))
        return EXIT_OK
    if action == "ack":
        agentcheck.acknowledge(actor)
        print("OK: noted that the user was told.\nTHEN: run `brainlib next`.")
        return EXIT_OK
    if action == "status":
        st, last = agentcheck.state(actor)
        _emit(args, {"state": st, "last": last}, "self-check: %s%s" % (st, (" (%d of %d on %s)" % (last["score"], last["total"], last["at"][:10])) if last else ""))
        return EXIT_OK
    raise BrainError("Unknown action %r." % action, fix="Use start, data, answer, finish, ack or status.")


def cmd_scan(args):
    lib = _lib(args)
    result = scan.scan_library(lib)
    n = len(result["entries"])
    hidden = sum(1 for e in result["entries"] if not privacy.is_readable_by_agents(e["sensitivity"]))
    _emit(
        args,
        {"notes": n, "private_hidden": hidden, "out_dir": str(lib.out_dir)},
        "Scanned %d note(s); %d private note(s) hidden from agents. Notes were not changed.\n"
        "Reading guide: `brainlib index`. Search: `brainlib find \"<topic>\"`." % (n, hidden),
    )
    return EXIT_OK


NOTED_HEAD = (
    "Written down in earlier conversations, not filed into a note yet. Use them like notes and keep their source "
    "labels: only [said] and [judgment] are the user's own view."
)


def cmd_index(args):
    lib = _lib(args)
    index = scan.load_index(lib)
    items = inbox.not_filed_for_agents(lib)
    if args.json:
        print_json(dict(index, not_filed=[inbox.describe(it) for it in items[:20]]), ensure_ascii=False, indent=2)
        return EXIT_OK
    text = lib.out("llms.txt").read_text(encoding="utf-8").rstrip("\n")
    if items:
        text += "\n\n## Noted recently (newest first)\n%s\n" % NOTED_HEAD
        text += "\n".join("- %s" % _short(inbox.describe(it), 300) for it in items[:10])
        if len(items) > 10:
            text += "\n- (%d more; search them with brainlib find \"<topic>\")" % (len(items) - 10)
    print(text)
    return EXIT_OK


def cmd_find(args):
    lib = _lib(args)
    query = " ".join(args.query)
    results = scan.find(lib, query, limit=args.limit)
    noted = scan.find_noted(lib, query)
    if args.json:
        print_json({"query": query, "notes": results, "not_filed": noted}, ensure_ascii=False, indent=2)
        return EXIT_OK
    if not results and not noted:
        print("No matching notes for: %s\nTry other words, or run `brainlib index` to see the reading guide." % query)
        return EXIT_OK
    for r in results:
        line = "%s  (%s, %s)" % (r["path"], r["tier"], r["title"])
        if r.get("description"):
            line += "\n    %s" % _short(r["description"], 140)
        print(line)
    if results:
        print("\nRead one with: brainlib read <path>")
    if noted:
        print("\nNOTED, NOT FILED YET: %s" % NOTED_HEAD)
        for n in noted:
            print("  %s" % _short(n["line"], 300))
    return EXIT_OK


def cmd_read(args):
    lib = _lib(args)
    full = safe_resolve(lib.root, args.path)
    rel = rel_posix(lib.root, full)
    if not full.is_file():
        raise BrainError("No such file in the library: %s" % rel, fix="Use `brainlib find \"<topic>\"` to find notes.")
    try:
        full.relative_to(lib.vault_dir.resolve())
        raise BrainError("The vault cannot be read by agents.", fix="Only the user can open it, with `brainlib vault open`.", code=EXIT_PRIVACY)
    except ValueError:
        pass
    if lib.is_ignored(rel):
        raise BrainError("That file is outside what brainlib manages: %s" % rel, fix="Read notes only.", code=EXIT_PRIVACY)
    zone = lib.zone_for(rel)
    if full.suffix.lower() in scan.NOTE_SUFFIXES:
        text = full.read_text(encoding="utf-8", errors="replace")
        sensitivity = build_entry(lib, rel, text, full.stat().st_mtime)["sensitivity"]
    else:
        if full.suffix.lower() not in (".txt", ".csv", ".json"):
            raise BrainError("Only text notes can be read: %s" % rel, fix="Read .md, .txt, .csv or .json files.")
        sensitivity = privacy.resolve_sensitivity({}, zone)
        text = full.read_text(encoding="utf-8", errors="replace")
    if not privacy.is_readable_by_agents(sensitivity):
        raise BrainError(
            "That note is private.",
            fix="Do not try to read it another way. If the user wants you to use it, they can paste the part they choose.",
            code=EXIT_PRIVACY,
        )
    if len(text.encode("utf-8")) > MAX_READ_BYTES:
        text = text[:MAX_READ_BYTES] + "\n\n[... truncated: the note is longer than %d bytes]" % MAX_READ_BYTES
    # Note content is printed untouched (no command rewriting).
    if args.json:
        builtins.print(json.dumps({"path": rel, "text": text}, ensure_ascii=False))
    else:
        builtins.print(text)
    return EXIT_OK


def cmd_health(args):
    lib = _lib(args)
    h = checks.health(lib)
    _emit(args, h, checks.render(h))
    bad = h["issues"] or any(not c["ok"] for c in h["custom_checks"])
    return EXIT_FINDINGS if bad else EXIT_OK


# --- writing ------------------------------------------------------------------

def _provenance_from(args):
    chosen = [
        (k, v)
        for k, v in (
            ("said", args.said),
            ("judgment", args.judgment),
            ("extracted", args.extracted),
            ("inferred", args.inferred),
            ("guess", args.guess),
            ("external", args.external),
        )
        if v
    ]
    if len(chosen) != 1:
        raise BrainError(
            "Say where this came from, with exactly one of: --said, --judgment, --extracted FILE, --inferred, --guess, --external SOURCE.",
            fix=(
                "--said: the user's exact words. --judgment: a view the user stated. --extracted FILE: from the user's "
                "own writing. --inferred: your conclusion. --guess: your guess. --external SOURCE: outside material."
            ),
        )
    key, value = chosen[0]
    ref = value if isinstance(value, str) else None
    return provenance.normalize(key), ref


def cmd_note(args):
    lib = _lib(args)
    settings = onboard.settings(lib)
    proposals.require_not_read_only(settings)
    prov, ref = _provenance_from(args)
    if not onboard.allows_provenance(settings, prov):
        raise BrainError(
            "The user asked not to record this kind of thing (onboarding Q5: %s), so it was NOT saved." % settings["record_policy"],
            fix="Only save what the user said or wrote. If they want more recorded, ask them about Q5.",
            code=4,
        )
    text = " ".join(args.text)
    if text.strip() == "-":
        text = sys.stdin.read()
    item, dup = inbox.add(
        lib,
        text,
        prov,
        actor=_actor(args),
        source_kind=args.source_kind,
        source_ref=ref,
        said_at=args.said_at,
        target=args.target,
        tags=args.tag,
        sensitivity="private" if args.private else "internal",
        private_handling=settings.get("private_handling", "exclude"),
    )
    if dup:
        _emit(args, {"duplicate_of": dup}, "ALREADY SAVED as %s. Nothing new was written." % dup)
        return EXIT_OK
    shown = "(private: encrypted)" if item.get("encrypted_ref") else _short(item.get("text"), 120)
    _emit(
        args,
        {"saved": item["id"], "provenance": item["provenance"]},
        "SAVED to the inbox as %s [%s]: %s\n"
        "No note was changed. It becomes a suggested change when `brainlib classify` runs."
        % (item["id"], provenance.label(item["provenance"]), shown),
    )
    return EXIT_OK


def cmd_inbox(args):
    lib = _lib(args)
    items = inbox.all_items(lib)
    if not args.all:
        items = [i for i in items if i["status"] in ("pending", "private-held")]
    if args.json:
        print_json(items, ensure_ascii=False, indent=2)
        return EXIT_OK
    if not items:
        print("The inbox is empty.")
        return EXIT_OK
    for i in items:
        text = "(private, encrypted)" if i.get("encrypted_ref") else ("(private)" if i.get("sensitivity") == "private" else _short(i.get("text")))
        print("%s  [%s] [%s] %s: %s" % (i["id"], i["status"], provenance.label(i["provenance"]), (i.get("captured_at") or "")[:10], text))
    return EXIT_OK


def cmd_classify(args):
    lib = _lib(args)
    s = classify.run(lib, actor=_actor(args), dry_run=args.dry_run)
    if args.json:
        print_json(s, ensure_ascii=False, indent=2)
        return EXIT_OK
    lines = []
    if not s["items"]:
        lines.append("Nothing to sort: the inbox has no pending items.")
    else:
        verb = "Would make" if args.dry_run else "Made"
        lines.append("%s %d suggested change(s) from %d inbox item(s)." % (verb, len(s["proposals"]), s["items"]))
        for p in s["proposals"]:
            lines.append("  - %s: %d item(s)%s" % (p["target"], p["items"], ("  [%s]" % p["id"]) if p.get("id") else ""))
        if s["duplicates"]:
            lines.append("  %d item(s) were already in the notes and were skipped." % s["duplicates"])
        if s.get("auto_applied"):
            lines.append("  %d low-risk change(s) were applied automatically, as the user allowed." % s["auto_applied"])
    if s.get("held_by_record_policy"):
        lines.append("%d item(s) are held back because of the user's recording choice (Q5)." % s["held_by_record_policy"])
    for e in s.get("errors") or []:
        lines.append("  could not propose for %s: %s" % (e.get("target") or e.get("proposal"), e["error"]))
    if any(p.get("approval") == "owner" for p in s["proposals"]):
        waiting = [p for p in proposals.list_proposals(lib, states=("open",)) if p.get("approval") == "owner"]
        if nextstep.review_due(lib, onboard.settings(lib), len(waiting)):
            lines.append("NEXT: these need the user's yes. Run `brainlib review` and go through them with the user.")
        else:
            lines.append(
                "These wait for the user's next review, as often as the user chose (onboarding Q8); brainlib next "
                "brings them up when it is time. If the user wants to see them now, run `brainlib review`."
            )
    print("\n".join(lines))
    return EXIT_OK


def cmd_propose(args):
    lib = _lib(args)
    if args.file:
        content = Path(args.file).expanduser().read_text(encoding="utf-8")
    elif args.text == "-":
        content = sys.stdin.read()
    else:
        content = args.text
    if content is None:
        raise BrainError("No content given.", fix='Pass --text "..." or --file PATH (or --text - to read from stdin).')
    p = proposals.create(lib, args.op, args.path, content, args.reason, actor=_actor(args), heading=args.heading)
    _emit(
        args,
        p,
        proposals.render(p)
        + "\nNEXT: show this to the user. If they agree: brainlib apply %s --as %s --user-said \"<their words>\"" % (p["id"], lib.owner),
    )
    return EXIT_OK


def _interactive_review(lib, ps):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise BrainError("--interactive needs a real terminal.", fix="Run it yourself in a terminal, or use `brainlib review`.")
    for p in ps:
        print(proposals.render(p, full=True))
        while True:
            ans = input("Apply this change? [y]es / [n]o / [l]ater / [q]uit: ").strip().lower()
            if ans in ("y", "yes"):
                proposals.apply(lib, p["id"], approved_by=lib.owner, user_words="approved in the terminal")
                print("applied.\n")
                break
            if ans in ("n", "no"):
                proposals.decide(lib, p["id"], "rejected", lib.owner)
                print("rejected.\n")
                break
            if ans in ("l", "later", ""):
                proposals.decide(lib, p["id"], "deferred", lib.owner)
                print("kept for later.\n")
                break
            if ans in ("q", "quit"):
                return


def cmd_review(args):
    lib = _lib(args)
    if args.id:
        p = proposals.get(lib, args.id)
        _emit(args, p, proposals.render(p, full=True))
        return EXIT_OK
    ps = proposals.list_proposals(lib)
    nextstep.mark_reviewed(lib)
    if args.interactive:
        _interactive_review(lib, ps)
        return EXIT_OK
    if args.json:
        print_json(ps, ensure_ascii=False, indent=2)
        return EXIT_OK
    if not ps:
        print("No suggested changes are waiting.")
        return EXIT_OK
    for p in ps:
        print(proposals.render(p))
        print()
    print(
        "For each one, show the user the text, ask yes / no / later, and wait for their reply. Then run:\n"
        "  brainlib apply <ID> --as %s --user-said \"<their reply, word for word>\"\n"
        "  brainlib reject <ID> --as %s\n"
        "  brainlib defer <ID>" % (lib.owner, lib.owner)
    )
    return EXIT_OK


def cmd_apply(args):
    lib = _lib(args)
    if args.auto:
        done, failed = proposals.apply_auto(lib, actor=_actor(args))
        _emit(
            args,
            {"applied": done, "failed": failed},
            "Applied %d low-risk change(s) automatically.%s"
            % (len(done), "".join("\n  failed %s: %s" % (f["proposal"], f["error"]) for f in failed)),
        )
        return EXIT_OK
    if not args.id:
        raise BrainError("Which proposal?", fix="Pass its id, for example `brainlib apply P-20260101T120000-abc123 --as %s`." % lib.owner)
    r = proposals.apply(lib, args.id, approved_by=getattr(args, "as_", None), user_words=args.user_said)
    _emit(
        args,
        r,
        "APPLIED %s to %s. A receipt was written (no content in it).\n"
        "If the user wants it back: brainlib undo %s --as %s" % (args.id, r["target"], args.id, lib.owner),
    )
    return EXIT_OK


def cmd_reject(args):
    lib = _lib(args)
    p = proposals.decide(lib, args.id, "rejected", getattr(args, "as_", None), note=args.note)
    print("REJECTED %s. The note was not changed." % p["id"])
    return EXIT_OK


def cmd_defer(args):
    lib = _lib(args)
    p = proposals.decide(lib, args.id, "deferred", getattr(args, "as_", None) or "agent/unknown", note=args.note)
    print("KEPT FOR LATER: %s." % p["id"])
    return EXIT_OK


def cmd_undo(args):
    lib = _lib(args)
    p = proposals.undo(lib, args.id, getattr(args, "as_", None))
    print("UNDONE %s: %s is back to how it was." % (p["id"], p["target"]))
    return EXIT_OK


# --- onboarding -------------------------------------------------------------------

def cmd_onboard(args):
    lib = _lib(args)
    lang = _lang(args, lib)
    data = onboard.load_questions()
    action = args.action
    if action == "next":
        q, reason = onboard.next_question(lib)
        if not q:
            print("All questions are answered and none is due. Run `brainlib onboard summary` to see them.")
            return EXIT_OK
        if not onboard.started(lib):
            print("SAY TO USER FIRST: %s\n" % (data["intro"].get(lang) or data["intro"]["en"]))
        number = [x["id"] for x in data["questions"]].index(q["id"]) + 1
        print(onboard.render_question(q, lang=lang, reason=reason, number=number, total=len(data["questions"])))
        return EXIT_OK
    if action == "answer":
        rest = args.rest[0].split() if len(args.rest) == 1 else args.rest
        if len(rest) < 2:
            raise BrainError("Usage: brainlib onboard answer <QID> <letter(s)|skip>", fix="For example: brainlib onboard answer Q4 c")
        was_complete = onboard.is_complete(lib)
        q, entry = onboard.answer(lib, rest[0], " ".join(rest[1:]), other_text=args.other, actor=_actor(args))
        if entry["skipped"]:
            shown = "skipped"
        else:
            shown = "; ".join("%s) %s" % (o["id"], o.get(lang) or o["en"]) for o in q["options"] if o["id"] in entry["choices"])
        lines = ["RECORDED %s: %s" % (q["id"], shown)]
        if not was_complete and onboard.is_complete(lib):
            lines.append("SAY TO USER: %s" % (data["outro"].get(lang) or data["outro"]["en"]))
        lines.append("THEN: run `brainlib next`.")
        print("\n".join(lines))
        return EXIT_OK
    if action == "summary":
        _emit(args, {"profile": onboard.profile(lib), "settings": onboard.settings(lib)}, onboard.render_summary(lib, lang))
        return EXIT_OK
    if action == "list":
        for q in data["questions"]:
            print("%s  %s" % (q["id"], q["ask"].get(lang) or q["ask"]["en"]))
        return EXIT_OK
    if action == "signal":
        if len(args.rest) < 2:
            raise BrainError('Usage: brainlib onboard signal <QID> "<what the user said>"', fix='For example: brainlib onboard signal Q4 "just do it, stop asking"')
        q, n = onboard.signal(lib, args.rest[0], " ".join(args.rest[1:]), actor=_actor(args))
        left = max(0, onboard.SIGNALS_TO_REASK - n)
        print(
            "NOTED for %s (%d so far). %s"
            % (q["id"], n, "It is now due: `brainlib next` will ask the user again." if not left else "%d more and I'll ask the user again." % left)
        )
        return EXIT_OK
    if action == "reset":
        done = onboard.reset(lib, args.rest[0] if args.rest else None)
        print("RESET: %s. The history is kept. Run `brainlib next` to ask again." % (", ".join(done) or "nothing"))
        return EXIT_OK
    raise BrainError("Unknown onboard action %r." % action, fix="Use next, answer, summary, list, signal or reset.")


# --- privacy, hooks, vault -------------------------------------------------------------

def _walk_files(root, lib=None):
    out = []
    for dirpath, dirnames, filenames in os.walk(str(root)):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = [d for d in dirnames if d != ".git" and not (lib and lib.is_ignored(rel_dir + d + "/"))]
        for fn in filenames:
            rel = rel_dir + fn
            if lib and lib.is_ignored(rel):
                continue
            out.append(rel)
    return sorted(out)


def cmd_privacy(args):
    mode = args.mode
    if mode == "library":
        lib = _lib(args)
        root = lib.root
        files = _walk_files(root, lib)
    else:
        root = Path(args.path or os.getcwd()).resolve()
        if (root / ".git").exists():
            files = privacy.git_files(root, staged=args.staged)
        else:
            files = _walk_files(root)
    if args.files:
        files = [f for f in files if f in set(args.files)] or list(args.files)
    hits, notes = privacy.scan_files(root, files, mode, words_path=args.words)
    data = {"mode": mode, "files": len(files), "hits": [h.as_dict() for h in hits], "notes": notes}
    if args.json:
        print_json(data, ensure_ascii=False, indent=2)
    else:
        for n in notes:
            print("NOTE: %s" % n)
        for h in hits:
            print("%s:%s  %s (%s)  %s" % (h.path, h.line, h.rule, h.kind, h.excerpt))
        if hits:
            print("FOUND %d privacy problem(s) in %d file(s) checked (mode %s)." % (len(hits), len(files), mode))
            print("FIX: remove or replace each one. For a deliberate exception, add `brainlib:allow` to that line, or list the exact phrase in %s." % privacy.ALLOW_FILE)
        else:
            print("OK: no privacy problems in %d file(s) (mode %s)." % (len(files), mode))
    return EXIT_PRIVACY if hits else EXIT_OK


HOOK = """#!/bin/sh
# Installed by brainlib: stops a {what} that contains secrets, personal data or private terms.
# Set BRAINLIB_PRIVATE_WORDS to a file of your private terms (kept outside the repository).
exec {cmd} privacy scan --mode commit {extra}--path "$(git rev-parse --show-toplevel)"
"""


def cmd_hooks(args):
    root = Path(args.path or os.getcwd()).resolve()
    hooks = root / ".git" / "hooks"
    if not hooks.is_dir():
        raise BrainError("No git repository at %s." % root, fix="Run inside a git repository, or pass --path.")
    written = []
    for name, what, extra in (("pre-commit", "commit", "--staged "), ("pre-push", "push", "")):
        target = hooks / name
        if target.exists() and not args.force:
            raise BrainError("%s already has a %s hook." % (root, name), fix="Merge it by hand, or pass --force to replace it.")
        target.write_text(HOOK.format(what=what, cmd=brainlib_cmd(), extra=extra), encoding="utf-8")
        os.chmod(target, 0o755)
        written.append(name)
    print("INSTALLED %s hooks in %s." % (" and ".join(written), root))
    return EXIT_OK


def cmd_vault(args):
    lib = _lib(args)
    a = args.action
    if a == "status":
        s = vault.status(lib)
        _emit(
            args,
            s,
            "age installed: %s\nvault set up: %s\nkey locked with a passphrase: %s\nencrypted files: %d"
            % ("yes" if s["age_installed"] else "no (install it to use the vault)", "yes" if s["initialized"] else "no",
               "yes" if s["key_locked_with_passphrase"] else "no", s["encrypted_files"]),
        )
        return EXIT_OK
    if a == "init":
        r = vault.init(lib, bring_recipient=args.recipient)
        print("VAULT READY. Public key: %s\nKeep your passphrase safe offline; nobody can recover it." % r["recipient"])
        return EXIT_OK
    if a == "add":
        if args.all_private:
            n = vault.add_all_private(lib, remove_plaintext=args.remove_plaintext)
            print("ENCRYPTED %d private note(s) into the vault.%s" % (n, " The readable copies were removed." if args.remove_plaintext and n else ""))
            return EXIT_OK
        if not args.name:
            raise BrainError("Which file?", fix="Pass a path, or --all-private.")
        name = vault.add(lib, args.name, remove_plaintext=args.remove_plaintext)
        print("ENCRYPTED into the vault as %s.%s" % (name, " The readable copy was removed." if args.remove_plaintext else ""))
        return EXIT_OK
    if a == "list":
        files = vault.list_files(lib)
        _emit(args, files, "\n".join(files) if files else "The vault is empty.")
        return EXIT_OK
    if a == "open":
        if not args.name:
            raise BrainError("Which file?", fix="Run `brainlib vault list` to see the names.")
        vault.open_file(lib, args.name, out=args.out)
        return EXIT_OK
    raise BrainError("Unknown vault action %r." % a, fix="Use status, init, add, list or open.")


# --- other -----------------------------------------------------------------------

def cmd_mcp(args):
    from .mcp import serve

    return serve(getattr(args, "library", None))


def cmd_selftest(args):
    from .selftest import run

    return run(verbose=args.verbose)


def cmd_version(args):
    print("brainlib %s" % __version__)
    return EXIT_OK


# --- parser --------------------------------------------------------------------------

class Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(rewrite("ERROR: %s\nFIX: run `%s --help`, or `brainlib next` if unsure what to do.\n" % (message, self.prog)))
        raise SystemExit(EXIT_USAGE)


def _common(sub):
    sub.add_argument("--library", default=argparse.SUPPRESS, help="path to the notes folder")
    sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable output")
    sub.add_argument("--lang", default=argparse.SUPPRESS, help="language for questions: en or zh")
    sub.add_argument("--as", dest="as_", default=argparse.SUPPRESS, help="who is acting, e.g. agent/claude or human:me")


def build_parser():
    p = Parser(prog="brainlib", description="A personal knowledge library that any AI agent can use safely. Start with `brainlib next`.")
    p.add_argument("--library", default=None, help="path to the notes folder")
    p.add_argument("--json", action="store_true", default=False, help="machine-readable output")
    p.add_argument("--lang", default=None, help="language for questions: en or zh")
    p.add_argument("--as", dest="as_", default=None, help="who is acting, e.g. agent/claude or human:me")
    sp = p.add_subparsers(dest="command", parser_class=Parser)

    def add(name, func, help_, aliases=()):
        s = sp.add_parser(name, help=help_, aliases=list(aliases))
        _common(s)
        s.set_defaults(func=func)
        return s

    s = add("next", cmd_next, "show the one thing to do next (start here)")
    s.add_argument("--snooze", metavar="KEY", help="put a suggestion off for a week (key from the output)")
    s.add_argument("--done", metavar="STEP", help="mark a one-time step as done, e.g. permissions")
    s = add("lang", cmd_lang, "show or set the user's language: zh or en")
    s.add_argument("value", nargs="?")
    add("doctor", cmd_doctor, "check this computer and suggest where the library should live")
    s = add("connect", cmd_connect, "make new conversations in the user's AI tools start from this library")
    s.add_argument("--tool", choices=tuple(connect.TOOLS))
    s.add_argument("--write", action="store_true", help="add the lines to the tool's user-level instruction file")
    s.add_argument("--remove", action="store_true", help="take the lines out again")
    s = add("agent-check", cmd_agent_check, "the agent's 4-task self-check (do it first)")
    s.add_argument("action", nargs="?", choices=("start", "data", "answer", "finish", "ack", "status"))
    s.add_argument("rest", nargs="*")
    s.add_argument("--model", help="your model name, if you know it")
    s = add("init", cmd_init, "create a new library")
    s.add_argument("path")
    s.add_argument("--name")
    s.add_argument("--owner", help="a short name for the owner, e.g. alex")
    s = add("adopt", cmd_adopt, "use an existing folder of notes (never changes them)")
    s.add_argument("path")
    s.add_argument("--name")
    s.add_argument("--owner")
    s.add_argument("--agents-file", action="store_true", help="also write an AGENTS.md pointer into the folder")
    add("scan", cmd_scan, "rebuild the index (never changes notes)")
    add("index", cmd_index, "print the reading guide for agents")
    s = add("find", cmd_find, "find notes about a topic or task")
    s.add_argument("query", nargs="+")
    s.add_argument("--limit", type=int, default=10)
    s = add("read", cmd_read, "print one note (private notes are refused)")
    s.add_argument("path")
    add("health", cmd_health, "list tidy-up issues", aliases=("lint",))

    s = add("note", cmd_note, "save something to the inbox (changes no notes)")
    s.add_argument("text", nargs="+", help='the text, or "-" to read stdin')
    g = s.add_argument_group("where it came from (pick exactly one)")
    g.add_argument("--said", action="store_true", help="the user's exact words")
    g.add_argument("--judgment", action="store_true", help="a view the user clearly stated")
    g.add_argument("--extracted", metavar="FILE", help="from the user's own writing (cite the file)")
    g.add_argument("--inferred", action="store_true", help="your own conclusion")
    g.add_argument("--guess", action="store_true", help="your guess")
    g.add_argument("--external", metavar="SOURCE", help="outside material (name the source)")
    s.add_argument("--said-at", help="when the user said it (YYYY-MM-DD)")
    s.add_argument("--private", action="store_true", help="sensitive: goes to the vault or is refused")
    s.add_argument("--target", help="the note it probably belongs in")
    s.add_argument("--tag", action="append")
    s.add_argument("--source-kind", default="conversation", choices=inbox.SOURCE_KINDS)
    s = add("inbox", cmd_inbox, "list inbox items")
    s.add_argument("--all", action="store_true", help="include items already handled")
    s = add("classify", cmd_classify, "turn inbox items into suggested changes")
    s.add_argument("--dry-run", action="store_true")
    s = add("propose", cmd_propose, "suggest a change to a note")
    s.add_argument("op", choices=proposals.OPS)
    s.add_argument("path")
    s.add_argument("--text")
    s.add_argument("--file")
    s.add_argument("--reason", required=True)
    s.add_argument("--heading", help="for append: add at the end of this section")
    s = add("review", cmd_review, "show suggested changes")
    s.add_argument("id", nargs="?")
    s.add_argument("--interactive", action="store_true", help="decide one by one in your own terminal")
    s = add("apply", cmd_apply, "apply a suggested change after the user said yes")
    s.add_argument("id", nargs="?")
    s.add_argument("--auto", action="store_true", help="apply only the changes the user allowed to go in automatically")
    s.add_argument("--user-said", help="the user's words of approval")
    s = add("reject", cmd_reject, "reject a suggested change")
    s.add_argument("id")
    s.add_argument("--note")
    s = add("defer", cmd_defer, "keep a suggested change for later")
    s.add_argument("id")
    s.add_argument("--note")
    s = add("undo", cmd_undo, "undo an applied change")
    s.add_argument("id")

    s = add("onboard", cmd_onboard, "the ten getting-to-know-you questions")
    s.add_argument("action", choices=("next", "answer", "summary", "list", "signal", "reset"))
    s.add_argument("rest", nargs="*")
    s.add_argument("--other", help='the user\'s own words when they pick "other"')

    s = add("privacy", cmd_privacy, "check files for secrets, personal data and private terms")
    s.add_argument("action", choices=("scan",))
    s.add_argument("files", nargs="*")
    s.add_argument("--mode", choices=("library", "commit", "release"), default="library")
    s.add_argument("--words", help="file of private terms, one per line (keep it outside the repo)")
    s.add_argument("--staged", action="store_true", help="only files staged for commit")
    s.add_argument("--path", help="repository folder for commit/release modes")
    s = add("hooks", cmd_hooks, "install git hooks that run the privacy check")
    s.add_argument("action", choices=("install",))
    s.add_argument("--path")
    s.add_argument("--force", action="store_true")
    s = add("vault", cmd_vault, "the encrypted vault for private notes")
    s.add_argument("action", nargs="?", default="status", choices=("status", "init", "add", "list", "open"))
    s.add_argument("name", nargs="?")
    s.add_argument("--recipient", help="init: use your own age public key instead of a passphrase-locked one")
    s.add_argument("--all-private", action="store_true")
    s.add_argument("--remove-plaintext", action="store_true")
    s.add_argument("--out", help="open: write to this file instead of the screen")

    add("mcp", cmd_mcp, "run as an MCP server on stdin/stdout")
    s = add("selftest", cmd_selftest, "check that brainlib works on this computer")
    s.add_argument("--verbose", action="store_true")
    add("version", cmd_version, "print the version")
    add("help", cmd_help, "list all commands")
    return p


def cmd_help(args):
    build_parser().print_help()
    print("\nNot sure where to start? Run: brainlib next")
    return EXIT_OK


def _utf8_streams():
    """Agents read our output through pipes; on Windows pipes default to the local code page."""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            if os.name == "nt" and not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None):
    _utf8_streams()
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    spill = next((n for n in ("files", "rest") if isinstance(getattr(args, n, None), list)), None)
    if extra and spill and not any(e.startswith("-") for e in extra):
        getattr(args, spill).extend(extra)
    elif extra:
        parser.error("unrecognized arguments: %s" % " ".join(extra))
    if not getattr(args, "command", None):
        parser.print_help()
        print("\nNot sure where to start? Run: brainlib next")
        return EXIT_OK
    try:
        if args.command == "mcp":  # long-running; each tool call takes the lock itself
            return args.func(args) or EXIT_OK
        with command_lock(config.brainlib_home()):
            return args.func(args) or EXIT_OK
    except BrainError as e:
        if getattr(args, "json", False):
            print_json({"error": e.message, "fix": e.fix, "code": e.code}, ensure_ascii=False)
        sys.stderr.write(rewrite("ERROR: %s\n" % e.message))
        if e.fix:
            sys.stderr.write(rewrite("FIX: %s\n" % e.fix))
        return e.code
    except KeyboardInterrupt:
        return 130
