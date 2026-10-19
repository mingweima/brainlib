"""Connect the user's AI tools, so every new conversation starts from the brain library.

Most assistants read a user-level instruction file at the start of every conversation. `brainlib connect`
writes a short block there, between markers so it can be updated or removed later. Tools whose user rules
live in a settings screen get the same text to paste. Nothing is written without `--write`, and the agent
must ask the user first.
"""

import os
import shutil
from pathlib import Path

from . import config
from .util import BrainError, EXIT_USAGE, atomic_write, ensure_private_dir, now

START = "<!-- brainlib:start -->"
END = "<!-- brainlib:end -->"


def _home():
    return Path.home()


def _codex_home():
    return Path(os.environ.get("CODEX_HOME") or (_home() / ".codex"))


TOOLS = {
    "claude-code": {"name": "Claude Code", "file": lambda: _home() / ".claude" / "CLAUDE.md", "seen": lambda: _home() / ".claude"},
    "codex": {"name": "Codex", "file": lambda: _codex_home() / "AGENTS.md", "seen": _codex_home},
    "gemini": {"name": "Gemini CLI", "file": lambda: _home() / ".gemini" / "GEMINI.md", "seen": lambda: _home() / ".gemini"},
    "windsurf": {
        "name": "Windsurf",
        "file": lambda: _home() / ".codeium" / "windsurf" / "memories" / "global_rules.md",
        "seen": lambda: _home() / ".codeium" / "windsurf",
    },
    "cursor": {
        "name": "Cursor",
        "file": None,
        "seen": lambda: _home() / ".cursor",
        "where": {
            "zh": "打开 Cursor 设置，进入 Rules 里的 User Rules，把下面这段文字粘贴进去。",
            "en": "open Cursor Settings, go to Rules, then User Rules, and paste the text below.",
        },
    },
    "trae": {
        "name": "Trae",
        "file": None,
        "seen": lambda: _home() / ".trae",
        "where": {
            "zh": "打开 Trae 设置里的「规则」，把下面这段文字加到个人规则里。",
            "en": "open Rules in Trae's settings and add the text below to your user rules.",
        },
    },
    "other": {
        "name": "other tools",
        "file": None,
        "seen": lambda: None,
        "where": {
            "zh": "打开那个工具的设置，找到叫「自定义指令」「系统提示词」或「规则」的地方，把下面这段文字粘贴进去。",
            "en": "open the tool's settings, find its custom instructions, system prompt or rules, and paste the text below.",
        },
    },
}

TEXT = {
    "zh": (
        "## 我的大脑库\n"
        "我有一个大脑库（brainlib），在 {library}。\n"
        "- 开始一项新任务前，先运行 `{cmd} next`，按它的提示做。\n"
        "- 需要了解我的偏好、背景和做事方式时，先用 `{cmd} find <关键词>` 查，再用 `{cmd} read <路径>` 读。\n"
        "- 我说了值得长期记住的话，用 `{cmd} note` 记下来，照实标明是我说的、你推断的还是外部资料。\n"
        "- 不要直接改大脑库里的文件；要改就用 `{cmd} propose`，等我同意。\n"
        "- 不要打开 vault/ 和 private/ 里的文件，不要记密码和密钥。"
    ),
    "en": (
        "## My brain library\n"
        "I keep a brain library (brainlib) at {library}.\n"
        "- Before starting a new task, run `{cmd} next` and follow what it says.\n"
        "- When you need my preferences, background or way of working, search with `{cmd} find <words>`, then read with `{cmd} read <path>`.\n"
        "- When I say something worth keeping, save it with `{cmd} note`, marking honestly whether I said it, you inferred it, or it came from outside.\n"
        "- Never edit files in the library directly; suggest changes with `{cmd} propose` and wait for my yes.\n"
        "- Never open files in vault/ or private/, and never store passwords or keys."
    ),
}


def block(lib, cmd, lang):
    body = TEXT.get(lang) or TEXT["en"]
    return "%s\n%s\n%s" % (START, body.format(library=lib.root, cmd=cmd), END)


def _tool(key):
    t = TOOLS.get((key or "").strip().lower())
    if t is None:
        raise BrainError("Unknown tool %r." % key, fix="Use one of: %s" % ", ".join(TOOLS), code=EXIT_USAGE)
    return t


def _without_block(text):
    start, end = text.find(START), text.find(END)
    if start == -1 or end == -1 or end < start:
        return text, False
    before, after = text[:start].rstrip("\n"), text[end + len(END):].lstrip("\n")
    joined = before + ("\n\n" if before and after else "") + after
    return joined + ("\n" if joined and not joined.endswith("\n") else ""), True


def _read(path):
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _backup(path, key):
    if not path.is_file():
        return None
    folder = ensure_private_dir(config.brainlib_home() / "backups" / "connect")
    dest = folder / ("%s-%s%s" % (key, now().strftime("%Y%m%dT%H%M%S"), path.suffix or ".txt"))
    shutil.copy2(str(path), str(dest))
    return dest


def status():
    rows = []
    for key, t in TOOLS.items():
        seen = t["seen"]()
        path = t["file"]() if t["file"] else None
        rows.append(
            {
                "tool": key,
                "name": t["name"],
                "detected": bool(seen and seen.exists()),
                "file": str(path) if path else None,
                "connected": bool(path and START in _read(path)),
                "where": t.get("where"),
            }
        )
    return rows


def write(lib, key, cmd, lang):
    """Add or refresh the block in the tool's user-level instruction file."""
    t = _tool(key)
    if not t["file"]:
        raise BrainError(
            "%s keeps its rules in a settings screen, so brainlib cannot write them." % t["name"],
            fix="Run `brainlib connect --tool %s` and ask the user to paste the text it prints." % key,
            code=EXIT_USAGE,
        )
    path = t["file"]()
    old = _read(path)
    rest, _had = _without_block(old)
    new = (rest.rstrip("\n") + "\n\n" if rest.strip() else "") + block(lib, cmd, lang) + "\n"
    if new == old:
        return {"tool": key, "file": str(path), "changed": False, "backup": None}
    backup = _backup(path, key)
    atomic_write(path, new)
    return {"tool": key, "file": str(path), "changed": True, "backup": str(backup) if backup else None}


def remove(key):
    t = _tool(key)
    if not t["file"]:
        raise BrainError(
            "%s keeps its rules in a settings screen." % t["name"],
            fix="Ask the user to delete the lines from %s to %s in that tool's settings." % (START, END),
            code=EXIT_USAGE,
        )
    path = t["file"]()
    old = _read(path)
    new, had = _without_block(old)
    if not had:
        return {"tool": key, "file": str(path), "changed": False, "backup": None}
    backup = _backup(path, key)
    atomic_write(path, new)
    return {"tool": key, "file": str(path), "changed": True, "backup": str(backup) if backup else None}


def render_status(lib, cmd, lang):
    rows = status()
    found = [r["tool"] for r in rows if r["detected"] and not r["connected"]]
    done = [r["tool"] for r in rows if r["connected"]]
    lines = [
        "NEXT: Ask the user which AI tools they use. For each tool they name, run its line below; it shows the text and what to do next.",
        "WHY: A new conversation does not know the brain library exists unless the tool's user-level instructions say so.",
        "AIs used in a web page or a phone app (ChatGPT, Doubao or Kimi there, for example) cannot run commands, so they "
        "cannot use the library. Do not add the text to them; tell the user so in one sentence.",
        "FOUND ON THIS COMPUTER: %s" % (", ".join(found) or "none that brainlib knows, so ask the user"),
        "ALREADY CONNECTED: %s" % (", ".join(done) or "none"),
    ]
    lines += ["RUN: brainlib connect --tool %s" % r["tool"] for r in rows if not r["connected"]]
    lines += [
        "THEN: when the user's tools are connected, run: brainlib next --done connect",
        "--- the text that gets added ---",
        block(lib, cmd, lang),
        "--- end ---",
    ]
    return "\n".join(lines)
