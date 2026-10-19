"""The vault: private notes stored only as ciphertext, using the free `age` tool.

How it protects you:
- Encrypting needs only the public key (vault/recipient.txt), so agents can put things in.
- Decrypting needs the private key, which is itself locked with a passphrase that only the
  owner types, in their own terminal. Agents never see it, so they can never read the vault.
- Bring-your-own-key works too: pass `--recipient` (for example a hardware key or a
  Secure Enclave plugin recipient) and keep the identity wherever that tool keeps it.

File names inside vault/ are visible; give private files neutral names.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .util import (
    BrainError,
    EXIT_PRIVACY,
    ensure_private_dir,
    read_json,
    rel_posix,
    safe_resolve,
    sha256_bytes,
    sha256_file,
    write_json,
)

RECIPIENT_FILE = "recipient.txt"
IDENTITY_FILE = "identity.age"

_README = """# Vault

This folder holds private files encrypted with age (files ending in .age).

- To open one: run `brainlib vault open <name>` yourself, in your own terminal.
- identity.age is your private key, locked with your passphrase. Keep a copy of the
  passphrase somewhere safe offline. Without it, nobody (including you) can open these files.
- Never type or paste your passphrase into a chat with an AI agent.
"""


def age_bin():
    return shutil.which("age")


def _require_age():
    if not age_bin():
        raise BrainError(
            "The vault needs the free `age` encryption tool, which is not installed.",
            fix=(
                "Install it, then try again. macOS: `brew install age`. Debian/Ubuntu: `sudo apt install age`. "
                "Windows: `winget install FiloSottile.age`."
            ),
        )


def paths(lib):
    d = lib.vault_dir
    return d, d / RECIPIENT_FILE, d / IDENTITY_FILE


def is_initialized(lib):
    _d, rfile, _i = paths(lib)
    return rfile.is_file()


def recipient(lib):
    _d, rfile, _i = paths(lib)
    if not rfile.is_file():
        raise BrainError("The vault is not set up.", fix="Ask the user to run `brainlib vault init` in their own terminal.")
    for line in rfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise BrainError("vault/recipient.txt has no key in it.", fix="Run `brainlib vault init` again in a new library.")


def _is_interactive():
    return sys.stdin.isatty() and sys.stderr.isatty()


def init(lib, bring_recipient=None):
    _require_age()
    d, rfile, ifile = paths(lib)
    if rfile.exists():
        raise BrainError("The vault is already set up.", fix="Run `brainlib vault status`.")
    if bring_recipient:
        ensure_private_dir(d)
        rfile.write_text("# public key used to encrypt vault files\n%s\n" % bring_recipient.strip(), encoding="utf-8")
        (d / "README.md").write_text(_README, encoding="utf-8")
        return {"mode": "own-key", "recipient": bring_recipient.strip()}
    if not _is_interactive():
        raise BrainError(
            "The vault must be set up by the owner, in their own terminal.",
            fix=(
                "Tell the user: 'Please open a terminal and run `brainlib vault init --library <your folder>`. "
                "It will ask you to choose a passphrase. Do not tell me the passphrase.'"
            ),
            code=EXIT_PRIVACY,
        )
    keygen = shutil.which("age-keygen")
    if not keygen:
        raise BrainError("`age-keygen` was not found next to `age`.", fix="Reinstall age.")
    gen = subprocess.run([keygen], capture_output=True, text=True, check=True)
    identity = gen.stdout
    pub = None
    for line in identity.splitlines():
        if line.startswith("# public key:"):
            pub = line.split(":", 1)[1].strip()
    if not pub:
        raise BrainError("Could not read the new public key from age-keygen.", fix="Check that age is installed correctly.")
    ensure_private_dir(d)
    print("Choose a vault passphrase. You will need it every time you open a private file.", file=sys.stderr)
    p = subprocess.run([age_bin(), "-p", "-a", "-o", str(ifile)], input=identity, text=True)
    identity = None
    if p.returncode != 0 or not ifile.is_file():
        raise BrainError("Locking the key with a passphrase did not finish.", fix="Run `brainlib vault init` again.")
    rfile.write_text("# public key used to encrypt vault files\n%s\n" % pub, encoding="utf-8")
    (d / "README.md").write_text(_README, encoding="utf-8")
    return {"mode": "passphrase", "recipient": pub}


def encrypt_to(lib, text_or_bytes, dest):
    _require_age()
    dest = Path(dest)
    ensure_private_dir(dest.parent)
    data = text_or_bytes.encode("utf-8") if isinstance(text_or_bytes, str) else text_or_bytes
    p = subprocess.run([age_bin(), "-r", recipient(lib), "-a", "-o", str(dest)], input=data, capture_output=True)
    if p.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        raise BrainError("Encryption failed: %s" % p.stderr.decode("utf-8", "replace").strip(), fix="Check `brainlib vault status`.")
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    return dest


def add(lib, rel, remove_plaintext=False):
    """Encrypt a library file into the vault. Returns the vault-relative name."""
    src = safe_resolve(lib.root, rel)
    if not src.is_file():
        raise BrainError("File not found: %s" % rel, fix="Give a path relative to the library folder.")
    d, _r, _i = paths(lib)
    try:
        src.relative_to(d.resolve())
        raise BrainError("That file is already inside the vault folder.", fix="Nothing to do.")
    except ValueError:
        pass
    rel_src = rel_posix(lib.root, src)
    name = rel_src + ".age"
    dest = d / name
    data = src.read_bytes()
    encrypt_to(lib, data, dest)
    manifest = read_json(lib.state("vault-manifest.json"), {}) or {}
    manifest[rel_src] = sha256_bytes(data)
    write_json(lib.state("vault-manifest.json"), manifest)
    if remove_plaintext:
        src.unlink()
    return name


def private_paths(lib):
    from .scan import scan_library

    result = scan_library(lib, write=False)
    return [e["path"] for e in result["entries"] if e["sensitivity"] == "private"]


def unencrypted_private(lib):
    """Private notes with no up-to-date encrypted copy in the vault."""
    manifest = read_json(lib.state("vault-manifest.json"), {}) or {}
    out = []
    for rel in private_paths(lib):
        if manifest.get(rel) != sha256_file(lib.root / rel):
            out.append(rel)
    return out


def add_all_private(lib, remove_plaintext=False):
    """Encrypt every private note that has no current vault copy. Returns the count (names are not printed)."""
    todo = private_paths(lib) if remove_plaintext else unencrypted_private(lib)
    for rel in todo:
        add(lib, rel, remove_plaintext=remove_plaintext)
    return len(todo)


def list_files(lib):
    d, _r, ifile = paths(lib)
    if not d.is_dir():
        return []
    return sorted(
        p.relative_to(d).as_posix() for p in d.rglob("*.age") if p.resolve() != ifile.resolve()
    )


def open_file(lib, name, out=None):
    """Decrypt for the owner. Refuses to run without a real terminal (no agent can type the passphrase)."""
    _require_age()
    d, _r, ifile = paths(lib)
    src = safe_resolve(d, name if name.endswith(".age") else name + ".age")
    if not src.is_file():
        raise BrainError("No such vault file: %s" % name, fix="Run `brainlib vault list`.")
    identity = os.environ.get("BRAINLIB_VAULT_IDENTITY") or str(ifile)
    if not os.environ.get("BRAINLIB_VAULT_IDENTITY") and not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise BrainError(
            "Only the owner can open the vault, in their own terminal.",
            fix="Tell the user they can run `brainlib vault open %s` themselves. Never ask for the passphrase." % name,
            code=EXIT_PRIVACY,
        )
    cmd = [age_bin(), "-d", "-i", identity]
    if out:
        cmd += ["-o", str(out)]
    cmd.append(str(src))
    p = subprocess.run(cmd)
    if p.returncode != 0:
        raise BrainError("Could not open the file (wrong passphrase or damaged file).", fix="Try again.", code=EXIT_PRIVACY)
    if out:
        try:
            os.chmod(out, 0o600)
        except OSError:
            pass


def status(lib):
    d, rfile, ifile = paths(lib)
    return {
        "age_installed": bool(age_bin()),
        "initialized": rfile.is_file(),
        "key_locked_with_passphrase": ifile.is_file(),
        "encrypted_files": len(list_files(lib)),
        "vault_folder": rel_posix(lib.root, d) if d.exists() else (lib.config.get("vault_dir") or "vault/"),
    }
