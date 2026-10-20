"""Keep brainlib on the latest release.

At most once every CHECK_HOURS, `brainlib next` asks GitHub which release is the latest. The request
carries nothing about the user or their notes. When a newer release is out, `next` tells the agent to
run `brainlib update`, which does what fits how brainlib was installed:

- a git checkout of the official repository is fast-forwarded to the release tag; local changes, or a
  clone of some other repository, stop it;
- an unpacked folder gets the release zip: brainlib checks what is inside, backs the current program up
  to ~/.brainlib/backups/, then copies the new files over;
- a pip install gets the pip command to run.

The new version then adapts what the old one set up: it rebuilds every library's index, refreshes the
brainlib lines it wrote into the user's tool instruction files, and rewrites a library AGENTS.md that
an older brainlib wrote and nobody edited since. If the program changed some other way, the first
`brainlib next` that runs the new code does the same. Each copy of the program remembers its own
version and only rewrites files that run it, or run a copy that is gone, so two copies sharing
~/.brainlib leave each other alone; when one is deleted, the next copy to run takes over the files
that named it. A copy on a drive that is not mounted, or in a folder that can't be read, is not taken
for deleted; nor is one deleted together with the folder around it, which looks the same as a drive
that is not mounted. After going back to an older version, brainlib does not update itself to the
version the user left.

`brainlib update --off` stops the checks; so does the environment variable BRAINLIB_NO_UPDATE_CHECK=1.
Adapting after a manual update still happens; it never goes online.
"""

import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

from . import __version__, config
from .util import EXIT_FINDINGS, BrainError, atomic_write, ensure_private_dir, now, now_iso

REPO = "mingweima/brainlib"
API_LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES = "https://github.com/%s/releases" % REPO
GIT_URL = "https://github.com/%s.git" % REPO
ZIP_URL = "https://github.com/%s/archive/refs/tags/%%s.zip" % REPO
CHECK_HOURS = 24
PROGRAM_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = "brainlib/data/templates/library"
AGENTS_TEMPLATES = ("AGENTS.md", "AGENTS.zh.md")
SLOTS = ("{BRAINLIB_CMD}", "{LIBRARY}", "{WRITING_SKILL}")


def parse_version(v):
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", str(v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def newer(a, b):
    """True when version a is later than version b."""
    pa, pb = parse_version(a), parse_version(b)
    return bool(pa and pb and pa > pb)


def _state():
    return dict(config.global_state().get("update") or {})


def _save(st):
    gs = config.global_state()
    gs["update"] = st
    config.save_global_state(gs)


def checks_off():
    """Why automatic checks are off, or None when they are on."""
    if os.environ.get("BRAINLIB_NO_UPDATE_CHECK", "").strip() not in ("", "0"):
        return "BRAINLIB_NO_UPDATE_CHECK is set"
    if _state().get("auto") is False:
        return "the user turned them off with `brainlib update --off`"
    return None


def set_auto(on):
    st = _state()
    st["auto"] = bool(on)
    _save(st)


def seen_version(st=None):
    """The version this copy of the program last adapted to."""
    st = _state() if st is None else st
    return (st.get("seen") or {}).get(str(PROGRAM_DIR))


def _set_seen(st, version):
    seen = dict(st.get("seen") or {})
    seen[str(PROGRAM_DIR)] = version
    st["seen"] = seen


def installed_version():
    """The version in the program files now, which is newer than __version__ in a process started before an update."""
    disk = _version_in(PROGRAM_DIR)
    return disk if newer(disk, __version__) else __version__


def remember_version():
    """A library set up by this version needs no adapting later; without this, a fresh install would look
    like an update from an unknown older version."""
    st = _state()
    if not seen_version(st):
        _set_seen(st, __version__)
        _save(st)


def _exists(path):
    """True or False, or None when it can't be told (a folder that can't be read, for example)."""
    try:
        os.stat(str(path))
        return True
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return None


def _still_there(program):
    """Whether a copy of the program may still be in that folder. Only a copy known to be deleted counts as
    gone: one in a folder that can't be read, or whose parent is missing too (a drive that is not mounted),
    stays."""
    p = Path(program)
    found = _exists(p)
    if found is False:
        return _exists(p.parent) is not True
    if found is None:
        return True
    return any(_exists(f) is not False for f in (p / "brainlib.py", p / "brainlib" / "__init__.py"))


def _newest(versions):
    return max((v for v in versions if parse_version(v)), key=parse_version, default=None)


# --- asking GitHub ----------------------------------------------------------

def _no_prompt_env():
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _get(url, timeout):
    """Bytes at url. Falls back to curl, which has its own certificates when Python's are missing."""
    headers = {"User-Agent": "brainlib/%s" % __version__}
    if url.startswith("https://api.github.com/"):
        headers["Accept"] = "application/vnd.github+json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            return resp.read()
    except (OSError, ValueError, http.client.HTTPException) as e:
        first = e
    curl = shutil.which("curl")
    if curl:
        try:
            r = subprocess.run(
                [curl, "-fsSL", "--max-time", str(int(timeout)), "-A", "brainlib/%s" % __version__, url],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout + 5,
            )
            if r.returncode == 0:
                return r.stdout
        except (OSError, subprocess.SubprocessError):
            pass
    raise OSError(str(first))


def _latest_tag_by_git(timeout):
    git = shutil.which("git")
    if not git:
        return None
    try:
        r = subprocess.run(
            [git, "ls-remote", "--tags", "--refs", GIT_URL],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=_no_prompt_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    tags = [line.rsplit("refs/tags/", 1)[-1] for line in r.stdout.splitlines() if "refs/tags/" in line]
    found = sorted((parse_version(t), t) for t in tags if parse_version(t))
    return found[-1][1] if found else None


def fetch_latest(thorough=False):
    """{"version", "tag"} of the latest release. BRAINLIB_UPDATE_FEED may name a JSON file to read instead (for tests)."""
    feed = os.environ.get("BRAINLIB_UPDATE_FEED")
    try:
        if feed:
            data = json.loads(Path(feed).read_text(encoding="utf-8"))
        else:
            data = json.loads(_get(API_LATEST, timeout=8 if thorough else 3).decode("utf-8"))
        tag = str(data.get("tag_name") or "")
        if parse_version(tag):
            return {"version": "%d.%d.%d" % parse_version(tag), "tag": tag}
        error = "the answer named no version"
    except (OSError, ValueError, AttributeError) as e:
        error = str(e) or e.__class__.__name__
    tag = _latest_tag_by_git(30) if thorough and not feed else None
    if tag:
        return {"version": "%d.%d.%d" % parse_version(tag), "tag": tag}
    raise BrainError("Could not find out the latest brainlib release (%s)." % error[:200], code=EXIT_FINDINGS)


def _hours_since(stamp):
    try:
        return (now() - datetime.fromisoformat(stamp)).total_seconds() / 3600
    except (TypeError, ValueError):
        return float("inf")


def _info(st):
    installed = installed_version()
    return {
        "current": __version__,
        "installed": installed,
        "latest": st.get("latest"),
        "tag": st.get("tag"),
        "available": newer(st.get("latest"), installed),
        "checked_at": st.get("checked_at"),
        "error": st.get("error"),
    }


def check(force=False):
    """What is known about the latest release, asking GitHub at most once every CHECK_HOURS unless forced.
    Returns None when automatic checks are off and force is False."""
    if not force and checks_off():
        return None
    st = _state()
    if force or _hours_since(st.get("checked_at")) >= CHECK_HOURS:
        try:
            rel = fetch_latest(thorough=force)
            st.update(latest=rel["version"], tag=rel["tag"], error=None)
        except BrainError as e:
            st["error"] = e.message
        st["checked_at"] = now_iso()
        _save(st)
    return _info(st)


def known_newer():
    """What the last check found, when it is less than CHECK_HOURS old and names a newer release; else None.
    `brainlib update` uses it instead of asking GitHub again."""
    st = _state()
    if _hours_since(st.get("checked_at")) < CHECK_HOURS and not st.get("error"):
        info = _info(st)
        if info["available"]:
            return info
    return None


# --- updating the program ---------------------------------------------------

def install_kind(program=PROGRAM_DIR):
    program = Path(program)
    if (program / ".git").exists():
        return "git"
    if (program / "brainlib.py").is_file() and (program / "brainlib" / "__init__.py").is_file():
        return "folder"
    return "package"


def _git(program, *args, timeout=60):
    try:
        return subprocess.run(
            ["git", "-C", str(program)] + list(args),
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=_no_prompt_env(),
        )
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _first_line(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[0][:200] if lines else "no details"


def _official(url):
    u = (url or "").strip().lower().rstrip("/")
    u = u[:-4] if u.endswith(".git") else u
    return u.endswith(("github.com/" + REPO, "github.com:" + REPO))


def update_git(program, tag, url=GIT_URL, check_origin=True):
    program = Path(program)
    if not shutil.which("git"):
        raise BrainError(
            "This copy of brainlib is a git checkout, but git is not installed.",
            fix="Install git, or download the new release from %s and replace the folder." % RELEASES,
        )
    if check_origin:
        origin = _git(program, "remote", "get-url", "origin").stdout.strip()
        if not _official(origin):
            raise BrainError(
                "This copy of brainlib was cloned from %s, not from the official repository, so it was left alone." % (origin or "no known place"),
                fix="Update it from wherever it came from, or ask the user.",
            )
    if _git(program, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise BrainError(
            "The brainlib program folder %s has local changes, so it was left alone." % program,
            fix="Ask the user whether the changes matter. If not, they can run `git -C \"%s\" stash`, then `brainlib update` again." % program,
        )
    r = _git(program, "fetch", "--quiet", "--no-tags", url, "+refs/tags/%s:refs/tags/%s" % (tag, tag), timeout=180)
    if r.returncode:
        raise BrainError("Could not download brainlib %s: %s" % (tag, _first_line(r.stderr)), fix="Check the internet connection, then run `brainlib update` again.")
    r = _git(program, "merge", "--ff-only", "--quiet", "refs/tags/%s" % tag)
    if r.returncode:
        raise BrainError(
            "This checkout has commits that are not in the official history, so it could not move to %s." % tag,
            fix="Ask the user. They can keep their version, or move to the release with `git -C \"%s\" reset --hard %s`, which drops their commits." % (program, tag),
        )


def _download(url, dest):
    try:
        Path(dest).write_bytes(_get(url, timeout=120))
    except OSError as e:
        raise BrainError("Could not download %s (%s)." % (url, _first_line(str(e))), fix="Check the internet connection, then run `brainlib update` again.")


def _unpack(archive, dest):
    """Extract a release zip after checking every path; return the folder that has brainlib.py in it."""
    try:
        zf = zipfile.ZipFile(str(archive))
    except (OSError, zipfile.BadZipFile):
        raise BrainError("The download is not a valid zip file, so nothing was changed.", fix="Run `brainlib update` again later.")
    with zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        tops = {n.split("/", 1)[0] for n in names}
        bad = [n for n in names if n.startswith("/") or ".." in n.split("/") or ":" in n.split("/")[0]]
        if bad or len(tops) != 1:
            raise BrainError(
                "The download has an unexpected path (%s), so nothing was changed." % (bad[0] if bad else ", ".join(sorted(tops)) or "empty"),
                fix="Tell the user; do not retry.",
            )
        try:
            zf.extractall(str(dest))
        except (OSError, EOFError, RuntimeError, ValueError, zipfile.BadZipFile, zlib.error) as e:
            raise BrainError("The download could not be unpacked (%s), so nothing was changed." % _first_line(str(e)), fix="Run `brainlib update` again later.")
    top = Path(dest) / tops.pop()
    if not (top / "brainlib.py").is_file() or not (top / "brainlib" / "__init__.py").is_file():
        raise BrainError("The download does not look like brainlib, so nothing was changed.", fix="Tell the user; do not retry.")
    return top


def _version_in(folder):
    try:
        text = (Path(folder) / "brainlib" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"""__version__\s*=\s*["']([^"']+)["']""", text)
    return m.group(1) if m else None


def _backup_program(program):
    folder = ensure_private_dir(config.brainlib_home() / "backups")
    dest = folder / ("program-%s-%s" % (__version__, now().strftime("%Y%m%dT%H%M%S")))
    shutil.copytree(str(program), str(dest), ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    return dest


def _copy_over(new, program):
    new, program = Path(new), Path(program)
    for src in sorted(p for p in new.rglob("*") if p.is_file()):
        dest = program / src.relative_to(new)
        if dest.is_file() and dest.read_bytes() == src.read_bytes():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".brainlib-new")
        shutil.copyfile(str(src), str(tmp))
        if dest.is_file():
            shutil.copymode(str(dest), str(tmp))
        os.replace(str(tmp), str(dest))
    for old in sorted((program / "brainlib").rglob("*"), reverse=True):
        if old.is_file() and "__pycache__" not in old.parts and not (new / old.relative_to(program)).exists():
            old.unlink()


def update_folder(program, tag, version, archive=None):
    """Replace an unpacked copy of brainlib with the release. Returns the backup folder."""
    try:
        work = tempfile.TemporaryDirectory(prefix="brainlib-update-")
    except OSError as e:
        raise BrainError("Could not make a temporary folder (%s), so nothing was changed." % _first_line(str(e)), fix="Tell the user; check that the disk is not full.")
    with work as tmp:
        if archive is None:
            archive = Path(tmp) / "release.zip"
            _download(ZIP_URL % tag, archive)
        new = _unpack(archive, Path(tmp) / "new")
        got = _version_in(new)
        if got != version:
            raise BrainError("The download says it is brainlib %s, not %s, so nothing was changed." % (got or "nothing", version), fix="Run `brainlib update` again later.")
        try:
            backup = _backup_program(program)
        except OSError as e:
            raise BrainError("Could not back up the current program (%s), so nothing was changed." % _first_line(str(e)), fix="Tell the user; check that the disk is not full.")
        try:
            _copy_over(new, program)
        except OSError as e:
            try:
                _copy_over(backup, program)
                after = "The old version was put back from the backup in %s." % backup
            except OSError:
                after = "Putting the old version back failed too; it is in %s." % backup
            raise BrainError(
                "Could not replace the program files (%s). %s" % (_first_line(str(e)), after),
                fix="Tell the user. If brainlib no longer starts, copy everything in %s back into %s." % (backup, program),
            )
    return backup


def install(rel, program=PROGRAM_DIR):
    """Bring the program to release rel. Returns {"kind", "backup", "command"}."""
    kind = install_kind(program)
    if kind == "git":
        update_git(program, rel["tag"])
        return {"kind": kind, "backup": None, "command": None}
    if kind == "folder":
        return {"kind": kind, "backup": str(update_folder(program, rel["tag"], rel["version"])), "command": None}
    py = '"%s"' % sys.executable if " " in sys.executable else sys.executable
    return {"kind": kind, "backup": None, "command": '%s -m pip install --upgrade "git+%s@%s"' % (py, GIT_URL, rel["tag"])}


def run_adapt(program, old, backup=None):
    """Let the new code adapt what the old one set up. Returns (exit code, its output)."""
    argv = [sys.executable, str(Path(program) / "brainlib.py"), "update", "--adapt", old]
    if backup:
        argv += ["--old-program", str(backup)]
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, _first_line(str(e))
    if r.returncode:
        return r.returncode, _first_line(r.stderr or r.stdout)
    return 0, r.stdout.strip()


# --- adapting after an update ----------------------------------------------

def _made_from(text, template):
    """The match when text is template with only its slots filled in, i.e. nobody edited it; else None. A
    filled slot stays within one line, and a slot used twice holds the same text both times."""
    pattern, used = [], set()
    for p in re.split("(%s)" % "|".join(re.escape(s) for s in SLOTS), template):
        if p in SLOTS:
            name = "s%d" % SLOTS.index(p)
            pattern.append("(?P=%s)" % name if name in used else "(?P<%s>[^\n]+?)" % name)
            used.add(name)
        else:
            pattern.append(re.escape(p))
    return re.fullmatch("".join(pattern), text)


def _runs_here(cmd):
    """True when cmd, the brainlib command written into a file, runs this copy of the program or a copy
    that is gone. Only then may this copy rewrite the file; a copy that still exists keeps its own files."""
    cmd = (cmd or "").strip()
    m = re.search(r'"([^"]*brainlib\.py)"', cmd)
    if m:
        target = Path(m.group(1))
        try:
            if target.resolve() == (PROGRAM_DIR / "brainlib.py").resolve():
                return True
        except OSError:
            return False
        return not _still_there(target.parent)
    if cmd == "brainlib":
        return install_kind() == "package" or not shutil.which("brainlib")
    return cmd.endswith(" -m brainlib") and install_kind() == "package"


def _templates(old_program=None):
    """Library AGENTS.md templates that brainlib wrote: earlier versions' from the backup of the old program
    or from git tags, then this version's own."""
    found = []
    if old_program:
        for name in AGENTS_TEMPLATES:
            p = Path(old_program) / TEMPLATE_DIR / name
            if p.is_file():
                found.append((name, p.read_text(encoding="utf-8")))
    elif (PROGRAM_DIR / ".git").exists() and shutil.which("git"):
        for tag in _git(PROGRAM_DIR, "tag", "--list", "v*").stdout.split()[-40:]:
            for name in AGENTS_TEMPLATES:
                r = _git(PROGRAM_DIR, "show", "%s:%s/%s" % (tag, TEMPLATE_DIR, name))
                if r.returncode == 0 and r.stdout:
                    found.append((name, r.stdout))
    for name in AGENTS_TEMPLATES:
        p = PROGRAM_DIR / TEMPLATE_DIR / name
        if p.is_file():
            found.append((name, p.read_text(encoding="utf-8")))
    return found


def _refresh_agents_file(lib, old_program):
    from .cli import agents_text

    path = lib.root / "AGENTS.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if any(text == agents_text(lib.root, lang) for lang in ("en", "zh")):
        return None
    for name, template in _templates(old_program):
        m = _made_from(text, template)
        if m is None:
            continue
        if not _runs_here(m.groupdict().get("s0")):
            return None
        folder = ensure_private_dir(config.brainlib_home() / "backups" / "agents")
        shutil.copy2(str(path), str(folder / ("%s-%s.md" % (lib.id, now().strftime("%Y%m%dT%H%M%S")))))
        atomic_write(path, agents_text(lib.root, "zh" if name.endswith(".zh.md") else "en"))
        return str(path)
    return None


def _reason(e):
    return _first_line(getattr(e, "message", "") or str(e) or e.__class__.__name__)


def _refresh_tool_files(roots):
    """Refresh the brainlib block in each tool's instruction file that names a registered library and runs
    this copy of brainlib, or a copy that is gone. Returns (files changed, problems)."""
    from . import connect
    from .cli import standalone_cmd

    done, failed = [], []
    for key, t in connect.TOOLS.items():
        if not t["file"]:
            continue
        try:
            text = connect.read_text(t["file"]())
            start, end = text.find(connect.START), text.find(connect.END)
            if start == -1 or end < start:
                continue
            inside = text[start:end]
            root = next((r for r in sorted(roots, key=len, reverse=True) if r in inside), None)
            cmd = re.search(r"`([^`\n]+?) next`", inside)
            if root is None or not Path(root).is_dir() or cmd is None or not _runs_here(cmd.group(1)):
                continue
            lang = "zh" if "大脑库" in inside else "en"
            r = connect.write(config.load(root), key, standalone_cmd(), lang)
            if r["changed"]:
                done.append(r["file"])
        except (BrainError, OSError, ValueError) as e:
            failed.append("the brainlib lines for %s (%s)" % (t["name"], _reason(e)))
    return done, failed


def whats_new(old, lang):
    """The change notes of every release after old, up to this one, in the user's language."""
    path = PROGRAM_DIR / "docs" / "status.md"
    if not path.is_file():
        return []
    out, version, last = [], None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+v(\d+\.\d+\.\d+)", line)
        if m:
            version = m.group(1)
            continue
        if line.startswith("## "):
            version = None
        wanted = version and not newer(version, __version__) and (newer(version, old) if parse_version(old) else version == __version__)
        if not wanted:
            continue
        if line.startswith("- "):
            last = {"zh": line[2:].strip(), "en": None}
            out.append(last)
        elif line.startswith("  ") and last is not None and last["en"] is None:
            last["en"] = line.strip()
    return [(n["en"] if lang == "en" and n["en"] else n["zh"]) for n in out]


def adapt(old=None, old_program=None, rebuild=True):
    """Make what an older brainlib set up fit this version. Safe to run more than once; a part that fails
    is reported, and the rest still runs."""
    from . import scan

    roots = [r for r in (config.registry().get("libraries") or {})]
    report = {"from": old or None, "to": __version__, "rebuilt": 0, "agents_files": [], "tool_files": [], "failed": []}
    for root in roots:
        if not Path(root).is_dir():
            continue
        try:
            lib = config.load(root)
            if rebuild:
                scan.scan_library(lib)
                report["rebuilt"] += 1
            changed = _refresh_agents_file(lib, old_program)
            if changed:
                report["agents_files"].append(changed)
        except (BrainError, OSError, ValueError) as e:
            report["failed"].append("the library at %s (%s)" % (root, _reason(e)))
    report["tool_files"], failed = _refresh_tool_files(roots)
    report["failed"] += failed
    st = _state()
    _set_seen(st, __version__)
    st["last"] = {"from": old or None, "to": __version__, "at": now_iso()}
    _save(st)
    return report


def render_adapt(report, lang):
    zh = lang == "zh"
    old, new = report["from"], report["to"]
    back = newer(old, new)
    if back:
        lines = ["WENT BACK: brainlib is now %s (it was %s). It will not update itself to %s again; a newer release still installs as usual." % (new, old, old)]
    else:
        lines = ["UPDATED: brainlib is now %s%s." % (new, " (it was %s)" % old if old else "")]
        news = whats_new(old, lang)
        if news:
            lines.append("WHAT'S NEW:")
            lines.extend("- " + n for n in news[:12])
        else:
            lines.append("WHAT'S NEW: see %s" % RELEASES)
    for f in report["tool_files"]:
        lines.append("REFRESHED: the brainlib lines in %s (the old file was backed up)" % f)
    for f in report["agents_files"]:
        lines.append("REFRESHED: %s (nobody had edited it; the old file was backed up)" % f)
    for f in report["failed"]:
        lines.append("COULD NOT REFRESH: %s" % f)
    if report["rebuilt"]:
        lines.append("REBUILT: the index of %d librar%s" % (report["rebuilt"], "y" if report["rebuilt"] == 1 else "ies"))
    lines.append(
        "RESTART: if an app runs brainlib as an MCP server (Claude Desktop, for example), ask the user to restart that app "
        "so it uses this version."
    )
    if back:
        say = (
            "brainlib 回到了 %s（原来是 %s）。它不会再自己装回 %s，有更新的版本时照常更新。" % (new, old, old) if zh else
            "brainlib is back on version %s (it was %s). It won't update itself to %s again, but newer releases will still install." % (new, old, old)
        )
        todo = "Say the sentence below to the user."
    else:
        say = "brainlib 已经更新到 %s%s。" % (new, "（原来是 %s）" % old if old else "") if zh else "brainlib is now on version %s%s." % (new, " (it was %s)" % old if old else "")
        todo = "Say the sentence below to the user, then sum up WHAT'S NEW for them in one or two sentences of your own."
    if report["failed"]:
        todo += " Also tell them what could not be refreshed; everything else is done."
    lines.append("NEXT: %s" % todo)
    lines.append("SAY TO USER: %s" % say)
    lines.append("THEN: run `brainlib next` again; its rules may have changed.")
    return "\n".join(lines)


def on_next(lang):
    """What `brainlib next` has to say about updates, as {"instead": text to show instead of the step,
    "offer": a newer release that becomes the step, "notices": lines to show above the step, "info": what
    check() found about a newer release the user has not gone back from}. A release becomes the step only
    the first time; after that it is a notice at most once a day, so a failing update never keeps the agent
    from its work. Never raises."""
    out = {"instead": None, "offer": None, "notices": [], "info": None}
    try:
        if not _still_there(PROGRAM_DIR):
            out["notices"].append(
                "RESTART: the files of this brainlib (%s) are gone, but this process still runs it. Ask the user to "
                "restart the app that runs brainlib (Claude Desktop, for example); if its settings name this folder, "
                "they need to point it at the copy they kept." % PROGRAM_DIR
            )
            return out
        st = _state()
        disk = installed_version()
        copies = dict(st.get("seen") or {})
        seen = copies.pop(str(PROGRAM_DIR), None)
        gone = [d for d in copies if not _still_there(d)]
        others = [d for d in copies if d not in gone]
        if seen is None and gone and not others:
            last = _newest(copies[d] for d in gone)
            seen = last if newer(__version__, last) else __version__  # this copy stands in for the deleted ones
        if newer(disk, __version__):
            out["notices"].append(
                "RESTART: brainlib %s is installed, but this process still runs %s. Ask the user to restart the app "
                "that runs brainlib (Claude Desktop, for example)." % (disk, __version__)
            )
        elif seen != __version__ or gone:
            st["seen"] = {d: v for d, v in copies.items() if d not in gone}
            if newer(seen, __version__):
                st["skip"] = seen
            _set_seen(st, __version__)
            _save(st)  # before adapting, so a part that keeps failing is not retried on every run
            if seen == __version__ or (seen is None and others):
                r = adapt(rebuild=False)
                out["notices"] += [
                    "REFRESHED: %s now runs this copy of brainlib, because the copy it named is gone (the old file was backed up)." % f
                    for f in r["tool_files"] + r["agents_files"]
                ]
                out["notices"] += ["COULD NOT REFRESH: %s. Tell the user." % f for f in r["failed"]]
            elif seen or config.registry().get("libraries"):
                out["instead"] = render_adapt(adapt(seen), lang)
                return out
    except Exception:  # noqa: BLE001 - an update problem must never block the daily routine
        pass
    try:
        info = check()
        st = _state()
        skip = st.get("skip")
        if info and info["available"] and not (skip and not newer(info["latest"], skip)):
            out["info"] = info
            if st.get("offered") != info["tag"]:
                st.update(offered=info["tag"], noted_at=now_iso())
                _save(st)
                out["offer"] = info
            elif _hours_since(st.get("noted_at")) >= CHECK_HOURS:
                st["noted_at"] = now_iso()
                _save(st)
                out["notices"].append(
                    "NOTE: brainlib %s is out, but this computer still has %s. After the step below, run `brainlib update`; "
                    "if it does not work, tell the user what it said." % (info["latest"], info["installed"])
                )
    except Exception:  # noqa: BLE001
        pass
    return out
