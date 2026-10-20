"""Small helpers shared by every module. Standard library only."""

import contextlib
import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
import time
from pathlib import Path

# Exit codes are part of the CLI contract; agents can branch on them.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_PRIVACY = 3
EXIT_APPROVAL = 4
EXIT_CONFLICT = 5


class BrainError(Exception):
    """An error with a plain-language fix. `code` becomes the process exit code."""

    def __init__(self, message, fix=None, code=EXIT_USAGE):
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.code = code


def now():
    return _dt.datetime.now().astimezone().replace(microsecond=0)


def now_iso():
    return now().isoformat()


def today():
    return now().date()


def today_str():
    return today().isoformat()


def parse_date(value):
    """Return a datetime.date from 'YYYY-MM-DD', an ISO timestamp, or a date; else None."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path):
    path = Path(path)
    if not path.exists():
        return None
    return sha256_bytes(path.read_bytes())


def new_id(prefix):
    stamp = now().strftime("%Y%m%dT%H%M%S")
    return "%s-%s-%s" % (prefix, stamp, secrets.token_hex(3))


def slug(text, fallback="item"):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-._").lower()
    return s[:60] or fallback


def ensure_private_dir(path):
    """Create a directory readable only by the current user (mode 700 on POSIX)."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def atomic_write(path, data, private=False):
    """Write a file so readers never see a half-written version."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    if private:
        mode = 0o600
    else:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path, obj, private=True):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n", private=private)


_LOCK_DEPTH = [0]
LOCK_ENV = "BRAINLIB_LOCK_HELD"


@contextlib.contextmanager
def command_lock(home, wait=60.0, stale=600.0):
    """Let one brainlib command run at a time, so commands an agent starts in parallel
    cannot overwrite each other's state. Nested calls in the same process, and brainlib
    processes started by the holder, go straight through."""
    if _LOCK_DEPTH[0] or os.environ.get(LOCK_ENV):
        _LOCK_DEPTH[0] += 1
        try:
            yield
        finally:
            _LOCK_DEPTH[0] -= 1
        return
    path = ensure_private_dir(Path(home)) / "command.lock"
    deadline = time.monotonic() + wait
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except (FileExistsError, PermissionError) as e:
            _raise_unless_busy(e)
            if _lock_is_stale(path, stale):
                _remove_lock(path)
                continue
            if time.monotonic() > deadline:
                raise BrainError(
                    "Another brainlib command is still running.",
                    fix="Wait for it to finish, then run this command again. Run brainlib commands one at a time. "
                    "If no brainlib command is running, delete %s." % path,
                )
            time.sleep(0.05)
    try:
        os.write(fd, ("%d %f\n" % (os.getpid(), time.time())).encode("ascii"))
    finally:
        os.close(fd)
    _LOCK_DEPTH[0] = 1
    os.environ[LOCK_ENV] = str(os.getpid())
    try:
        yield
    finally:
        _LOCK_DEPTH[0] = 0
        os.environ.pop(LOCK_ENV, None)
        _remove_lock(path)


def _raise_unless_busy(e):
    # Windows reports a lock file that is still being deleted as PermissionError.
    if isinstance(e, PermissionError) and os.name != "nt":
        raise e


def _remove_lock(path, tries=40):
    # On Windows a file cannot be deleted while another process has it open, even for a moment.
    for _ in range(tries):
        try:
            os.unlink(str(path))
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.05)


def _lock_is_stale(path, stale):
    """A lock is stale when it is older than `stale` seconds or the process that took it has ended."""
    try:
        parts = path.read_text(encoding="ascii").split()
    except (OSError, ValueError):
        parts = []
    try:
        started = float(parts[1])
    except (IndexError, ValueError):
        try:
            started = path.stat().st_mtime
        except OSError:
            return False
    if time.time() - started > stale:
        return True
    try:
        pid = int(parts[0])
    except (IndexError, ValueError):
        return False
    return not _pid_alive(pid)


def _pid_alive(pid):
    if os.name == "nt":  # os.kill would terminate the process on Windows
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: the process exists
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def append_jsonl(path, obj):
    """Append one JSON object per line. Append-only files are never rewritten."""
    path = Path(path)
    ensure_private_dir(path.parent)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


class FileLock:
    """Cross-platform exclusive lock using an O_EXCL lock file.

    A lock older than `stale_after` seconds, or left by a process that has ended,
    is assumed abandoned and broken.
    """

    def __init__(self, path, timeout=10.0, stale_after=600.0):
        self.path = Path(path)
        self.timeout = timeout
        self.stale_after = stale_after
        self._fd = None

    def __enter__(self):
        ensure_private_dir(self.path.parent)
        deadline = time.time() + self.timeout
        while True:
            try:
                self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(self._fd, ("%d %s" % (os.getpid(), now_iso())).encode())
                return self
            except (FileExistsError, PermissionError) as e:
                _raise_unless_busy(e)
                if _lock_is_stale(self.path, self.stale_after):
                    _remove_lock(self.path)
                    continue
                if time.time() > deadline:
                    raise BrainError(
                        "Another brainlib process is writing to this library.",
                        fix="Wait a moment and try again. If no other process is running, delete %s" % self.path,
                        code=EXIT_CONFLICT,
                    )
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            if self._fd is not None:
                os.close(self._fd)
        except OSError:
            pass
        self._fd = None
        _remove_lock(self.path)
        return False


def strip_dot_slash(rel):
    """Drop leading "./" only. `str.lstrip("./")` would also eat "../" and dot folders like ".obsidian/"."""
    rel = str(rel).strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def safe_resolve(root, rel):
    """Resolve `rel` under `root`, refusing anything that escapes (../, absolute paths, symlinks)."""
    root = Path(root).resolve()
    rel = str(rel).strip().replace("\\", "/")
    if not rel:
        raise BrainError("Empty path.", fix="Give a path relative to the library folder, like notes/ideas.md")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        raise BrainError(
            "Absolute paths are not allowed: %s" % rel,
            fix="Give a path relative to the library folder.",
            code=EXIT_PRIVACY,
        )
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise BrainError(
            "Path escapes the library folder: %s" % rel,
            fix="Only files inside the library can be read or written.",
            code=EXIT_PRIVACY,
        )
    return target


def rel_posix(root, path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def mask(value, keep=2):
    """Show only the edges of a sensitive value, never the whole thing."""
    value = str(value)
    if len(value) <= keep * 2 + 2:
        return "*" * len(value)
    return value[:keep] + "*" * min(12, len(value) - keep * 2) + value[-keep:]
