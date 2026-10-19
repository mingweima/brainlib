"""MCP server on stdin/stdout (newline-delimited JSON-RPC 2.0). Standard library only.

Every tool runs the same code as the command line, so behavior, refusals and exit codes
are identical. Tools that need the owner's own terminal (vault init/open, interactive
review) are deliberately not offered here.
"""

import contextlib
import io
import json
import os
import sys

from . import __version__

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "brainlib manages the user's personal knowledge library. Start every session with kb_next and follow it. "
    "When its output says `RUN: brainlib <command>`, call the matching tool: next->kb_next, agent-check->kb_agent_check, "
    "lang->kb_lang, find->kb_find, read->kb_read, index->kb_index, health->kb_health, note->kb_note, "
    "onboard->kb_onboard, classify->kb_classify, review->kb_proposals, apply/reject/defer->kb_decide, doctor->kb_doctor. "
    "Never claim the user approved something they did not approve. Never ask for the vault passphrase."
)


def _s(desc, **props):
    return {"type": "object", "properties": props, "additionalProperties": False, "description": desc}


STR = {"type": "string"}
BOOL = {"type": "boolean"}
INT = {"type": "integer"}

TOOLS = [
    {"name": "kb_next", "description": "The one thing to do next. Call this first and after every step.", "inputSchema": _s("")},
    {
        "name": "kb_agent_check",
        "description": "The agent's 4-task self-check. action: start, data, answer (task, value), finish (model), ack, status.",
        "inputSchema": _s("", action=STR, task=STR, value=STR, model=STR),
    },
    {"name": "kb_lang", "description": "Set the user's language: zh or en.", "inputSchema": _s("", value=STR)},
    {"name": "kb_doctor", "description": "Check this computer and suggest where the library should live.", "inputSchema": _s("")},
    {"name": "kb_find", "description": "Find notes about a topic or task. Use before answering anything about the user.", "inputSchema": _s("", query=STR, limit=INT)},
    {"name": "kb_read", "description": "Read one note by path. Private notes are refused.", "inputSchema": _s("", path=STR)},
    {"name": "kb_index", "description": "The reading guide: the most important notes first.", "inputSchema": _s("")},
    {"name": "kb_health", "description": "Tidy-up issues: broken links, outdated pages, conflicts.", "inputSchema": _s("")},
    {
        "name": "kb_note",
        "description": (
            "Save something to the inbox (changes no note). provenance: said (user's exact words), judgment, "
            "extracted (with source = file), inferred, guess, external (with source). private=true for sensitive things."
        ),
        "inputSchema": _s("", text=STR, provenance=STR, source=STR, said_at=STR, target=STR, private=BOOL),
    },
    {
        "name": "kb_onboard",
        "description": "Onboarding questions. action: next, answer (question, choice, other), summary, signal (question, text).",
        "inputSchema": _s("", action=STR, question=STR, choice=STR, other=STR, text=STR),
    },
    {"name": "kb_classify", "description": "Turn inbox items into suggested changes (changes no note).", "inputSchema": _s("", dry_run=BOOL)},
    {"name": "kb_proposals", "description": "List suggested changes, or show one by id.", "inputSchema": _s("", id=STR)},
    {
        "name": "kb_decide",
        "description": (
            "Apply, reject or defer a suggested change. apply/reject need user_confirmed=true and user_words: "
            "the user's own words. Never set them unless the user really said so."
        ),
        "inputSchema": _s("", id=STR, decision=STR, user_confirmed=BOOL, user_words=STR),
    },
]
for _t in TOOLS:
    for _k in ("text", "query", "path", "id", "decision", "value"):
        if _k in _t["inputSchema"]["properties"] and _t["name"] in (
            "kb_note", "kb_find", "kb_read", "kb_decide", "kb_lang",
        ):
            _t["inputSchema"].setdefault("required", []).append(_k)


class _Fail(Exception):
    pass


def _run_cli(argv):
    from .cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 2
    text = (out.getvalue() + err.getvalue()).strip()
    return code or 0, text


def _argv_for(name, a, library):
    lib = ["--library", library] if library else []
    actor = ["--as", "agent/mcp"]
    g = a.get
    if name == "kb_next":
        return ["next"] + lib + actor
    if name == "kb_agent_check":
        action = g("action") or "start"
        argv = ["agent-check", action] + actor
        if action == "answer":
            argv += [str(g("task") or ""), str(g("value") or "")]
        if g("model"):
            argv += ["--model", g("model")]
        return argv
    if name == "kb_lang":
        return ["lang", g("value")]
    if name == "kb_doctor":
        return ["doctor"] + lib
    if name == "kb_find":
        return ["find", g("query"), "--limit", str(g("limit") or 10)] + lib
    if name == "kb_read":
        return ["read", g("path")] + lib
    if name == "kb_index":
        return ["index"] + lib
    if name == "kb_health":
        return ["health"] + lib
    if name == "kb_note":
        prov = (g("provenance") or "").strip().lower()
        flag = {"said": ["--said"], "judgment": ["--judgment"], "inferred": ["--inferred"], "guess": ["--guess"]}.get(prov)
        if prov in ("extracted", "external"):
            flag = ["--" + prov, g("source") or "unknown source"]
        if flag is None:
            raise _Fail("provenance must be one of: said, judgment, extracted, inferred, guess, external")
        argv = ["note", g("text")] + flag + lib + actor
        if g("said_at"):
            argv += ["--said-at", g("said_at")]
        if g("target"):
            argv += ["--target", g("target")]
        if g("private"):
            argv.append("--private")
        return argv
    if name == "kb_onboard":
        action = g("action") or "next"
        argv = ["onboard", action] + lib + actor
        if action == "answer":
            argv += [g("question") or "", g("choice") or ""]
            if g("other"):
                argv += ["--other", g("other")]
        elif action == "signal":
            argv += [g("question") or "", g("text") or ""]
        return argv
    if name == "kb_classify":
        return ["classify"] + (["--dry-run"] if g("dry_run") else []) + lib + actor
    if name == "kb_proposals":
        return ["review"] + ([g("id")] if g("id") else []) + lib
    if name == "kb_decide":
        decision = (g("decision") or "").lower()
        pid = g("id")
        if decision == "defer":
            return ["defer", pid] + lib + actor
        if decision not in ("apply", "reject"):
            raise _Fail("decision must be apply, reject or defer")
        if g("user_confirmed") is not True or not (g("user_words") or "").strip():
            raise _Fail(
                "This needs the user's yes. Show them the change, and call again with user_confirmed=true and "
                "user_words set to what they said."
            )
        from . import config

        owner = config.load(library).owner
        argv = [decision, pid, "--as", owner] + lib
        if decision == "apply":
            argv += ["--user-said", g("user_words")]
        return argv
    raise _Fail("unknown tool %s" % name)


def handle(msg, library=None):
    """Handle one JSON-RPC message; return the response dict, or None for notifications."""
    mid = msg.get("id")
    method = msg.get("method")
    if mid is None:
        return None
    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "brainlib", "version": __version__},
            "instructions": INSTRUCTIONS,
        }
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS}:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "Unknown tool: %s" % name}}
        try:
            code, text = _run_cli(_argv_for(name, args, library))
        except _Fail as e:
            code, text = 2, "ERROR: %s" % e
        except Exception as e:  # never crash the server
            code, text = 1, "ERROR: internal error: %s" % e
        is_error = code not in (0, 1)
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {"content": [{"type": "text", "text": text or "(no output)"}], "isError": is_error},
        }
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found: %s" % method}}


def serve(library=None):
    from .cli import _utf8_streams

    os.environ["BRAINLIB_PREFIX"] = "brainlib"
    _utf8_streams()
    stdin = sys.stdin
    stdout = sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            if isinstance(msg, list):
                resp = [r for r in (handle(m, library) for m in msg) if r is not None] or None
            else:
                resp = handle(msg, library)
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0
