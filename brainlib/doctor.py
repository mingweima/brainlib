"""`brainlib doctor`: check this computer and suggest where the library should live.

The same command works on macOS, Windows and Linux. It only looks; it changes nothing.
"""

import os
import platform
import shutil
import stat
import sys
from pathlib import Path

from . import config, vault

PERMISSION_TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "agent-permissions"

SYNC_MARKERS = {
    "iCloud": ("mobile documents", "icloud drive", "iclouddrive", "com~apple~clouddocs"),
    "OneDrive": ("onedrive",),
    "Dropbox": ("dropbox",),
    "Google Drive": ("google drive", "googledrive", "my drive"),
    "Nutstore": ("nutstore", "坚果云"),
    "Baidu Netdisk": ("baidunetdisk", "百度网盘"),
}

INSTALL = {
    "python": {
        "macos": "Run `xcode-select --install` and click Install in the window that opens (it includes python3). With Homebrew: `brew install python`.",
        "windows": "Run `winget install -e --id Python.Python.3.12`, or install Python 3.12 from the Microsoft Store. Then open a new terminal.",
        "linux": "Debian/Ubuntu: `sudo apt install python3`. Fedora: `sudo dnf install python3`.",
    },
    "age": {
        "macos": "`brew install age` (needs Homebrew), or download from https://github.com/FiloSottile/age/releases",
        "windows": "`winget install FiloSottile.age`, or download from https://github.com/FiloSottile/age/releases",
        "linux": "Debian/Ubuntu: `sudo apt install age`. Fedora: `sudo dnf install age`.",
    },
}


def os_name():
    s = platform.system()
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(s, (s or "unknown").lower())


def suggested_library_path():
    return Path.home() / "brain"


def detect_sync(path):
    low = str(Path(path).expanduser()).lower()
    for name, marks in SYNC_MARKERS.items():
        if any(m in low for m in marks):
            return name
    return None


def _protected_hint(path, osn):
    p = Path(path).expanduser()
    home = Path.home()
    if osn == "macos":
        for sub in ("Documents", "Desktop", "Downloads", "Library/Mobile Documents"):
            try:
                p.relative_to(home / sub)
                return (
                    "macOS asks before apps can use ~/%s. If a command fails with 'Operation not permitted', the user should "
                    "open System Settings > Privacy & Security > Files and Folders (or Full Disk Access) and allow the terminal "
                    "or AI app you run in." % sub
                )
            except ValueError:
                continue
    if osn == "windows":
        for sub in ("Documents", "Desktop", "OneDrive"):
            try:
                p.relative_to(home / sub)
                return (
                    "On Windows, Documents and Desktop are often synced by OneDrive, and 'Controlled folder access' can block "
                    "writes there. If writing fails, the user can allow the app under Windows Security > Virus & threat "
                    "protection > Ransomware protection, or choose a folder like %s instead." % suggested_library_path()
                )
            except ValueError:
                continue
    return None


def check(lib=None):
    osn = os_name()
    home = config.brainlib_home()
    r = {
        "os": osn,
        "os_version": platform.release(),
        "python": "%d.%d.%d" % sys.version_info[:3],
        "python_ok": sys.version_info >= (3, 9),
        "python_path": sys.executable,
        "output_encoding": (getattr(sys.stdout, "encoding", None) or "").lower(),
        "age_installed": bool(vault.age_bin()),
        "git_installed": bool(shutil.which("git")),
        "brainlib_home": str(home),
        "library": str(lib.root) if lib else None,
        "library_sync": detect_sync(lib.root) if lib else None,
        "suggested_library": str(suggested_library_path()),
        "suggested_exists": suggested_library_path().exists(),
        "todo": [],
    }
    todo = r["todo"]
    if not r["python_ok"]:
        todo.append("Python is older than 3.9. " + INSTALL["python"].get(osn, ""))
    if not r["age_installed"]:
        todo.append(
            "Optional, needed only for the encrypted vault: install `age`. " + INSTALL["age"].get(osn, "")
        )
    if osn == "windows" and "utf" not in r["output_encoding"]:
        todo.append("Chinese text may show as garbled. Run brainlib through brainlib.cmd, or set PYTHONUTF8=1.")
    if osn != "windows" and home.exists():
        mode = stat.S_IMODE(home.stat().st_mode)
        if mode & 0o077:
            todo.append("%s can be read by other accounts on this computer; run `chmod 700 %s`." % (home, home))
    target = lib.root if lib else suggested_library_path()
    hint = _protected_hint(target, osn)
    if hint:
        todo.append(hint)
    if lib and r["library_sync"]:
        todo.append(
            "The library is inside %s. The sync provider can read plain-text notes; keep private notes in the vault "
            "(they are encrypted before syncing)." % r["library_sync"]
        )
    if lib:
        try:
            probe = lib.root / ".brainlib-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            r["library_writable"] = True
        except OSError:
            r["library_writable"] = False
            todo.append("The library folder cannot be written. " + (_protected_hint(lib.root, osn) or "Check its permissions."))
    folder = lib.root if lib else "<library folder>"
    todo.append(
        "Limit what your own AI tool may do: allow brainlib commands, block reading vault/ and private/, and block "
        "editing notes directly. Cursor: add the lines of %s to %s. Claude Code: merge %s into %s, replacing "
        "/ABSOLUTE/PATH/TO/brainlib with %s. Other tools: set the same three limits in their permission settings "
        "(details: %s)."
        % (
            PERMISSION_TEMPLATES / "cursorignore.txt",
            Path(str(folder)) / ".cursorignore",
            PERMISSION_TEMPLATES / "claude-code.settings.json",
            Path(str(folder)) / ".claude" / "settings.json",
            PERMISSION_TEMPLATES.parent.parent,
            PERMISSION_TEMPLATES / "README.md",
        )
    )
    return r


def render(r):
    lines = [
        "COMPUTER: %s %s, Python %s (%s)" % (r["os"], r["os_version"], r["python"], "ok" if r["python_ok"] else "too old"),
        "age (for the vault): %s; git: %s" % ("installed" if r["age_installed"] else "not installed", "installed" if r["git_installed"] else "not installed"),
        "brainlib settings folder: %s" % r["brainlib_home"],
    ]
    if r["library"]:
        lines.append("library: %s%s" % (r["library"], (" (synced by %s)" % r["library_sync"]) if r["library_sync"] else ""))
    else:
        lines.append(
            "no library yet; suggested new folder: %s%s"
            % (r["suggested_library"], " (already exists)" if r["suggested_exists"] else "")
        )
    if r["todo"]:
        lines.append("TODO (explain each to the user in plain words; do only what they agree to):")
        lines.extend("  - %s" % t for t in r["todo"])
    return "\n".join(lines)
