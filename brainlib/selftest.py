"""`brainlib selftest`: run the main flows end to end in a throwaway folder.

Nothing outside a temporary directory is touched. The vault part runs only when `age`
is installed. Exit code 0 means everything passed.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _Run:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.failures = []
        self.passed = 0

    def cli(self, *argv):
        from .cli import main

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(list(argv))
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 2
        return code or 0, out.getvalue() + err.getvalue()

    def check(self, name, ok, detail=""):
        if ok:
            self.passed += 1
            if self.verbose:
                print("PASS %s" % name)
        else:
            self.failures.append(name)
            print("FAIL %s%s" % (name, (": " + detail.strip()[:400]) if detail else ""))


def run(verbose=False):
    from . import agentcheck, config, mcp

    tmp = Path(tempfile.mkdtemp(prefix="brainlib-selftest-"))
    saved = {k: os.environ.get(k) for k in ("BRAINLIB_HOME", "BRAINLIB_PREFIX", "BRAINLIB_LIBRARY", "BRAINLIB_LANG", "BRAINLIB_VAULT_IDENTITY")}
    os.environ["BRAINLIB_HOME"] = str(tmp / "home")
    os.environ["BRAINLIB_PREFIX"] = "brainlib"
    for k in ("BRAINLIB_LIBRARY", "BRAINLIB_LANG", "BRAINLIB_VAULT_IDENTITY"):
        os.environ.pop(k, None)
    r = _Run(verbose)
    try:
        lib_dir = tmp / "brain"
        code, out = r.cli("next")
        r.check("next asks for the agent self-check first", "agent-check" in out, out)

        r.cli("agent-check")
        s = config.global_state()["agent_check_session"]
        target = [n["path"] for n in s["data"]["notes"] if n["tier"] == s["ask_tier"]][0]
        right = "abc"[[o["ok"] for o in s["privacy"]].index(True)]
        r.cli("agent-check", "answer", "1", s["code"])
        r.cli("agent-check", "answer", "2", ",".join(p["answer"] for p in s["prov"]))
        r.cli("agent-check", "answer", "3", right)
        r.cli("agent-check", "answer", "4", target)
        code, out = r.cli("agent-check", "finish", "--model", "selftest")
        r.check("agent self-check can be passed", "RESULT: PASS" in out, out)

        code, out = r.cli("next")
        r.check("next asks for the language", "brainlib lang" in out, out)
        r.cli("lang", "zh")
        code, out = r.cli("next")
        r.check("next asks where the library lives", "brainlib init" in out and "brainlib doctor" in out, out)
        code, out = r.cli("init", str(lib_dir))
        r.check("init creates a library", code == 0 and (lib_dir / "me.md").is_file(), out)
        lib = ["--library", str(lib_dir)]
        code, out = r.cli("next", *lib)
        r.check("next asks to check permissions once", "permissions" in out, out)
        r.cli("next", "--done", "permissions", *lib)

        for _ in range(12):
            code, out = r.cli("next", *lib)
            if "onboarding question" not in out:
                break
            qid = out.split("onboarding question ", 1)[1].split(" ", 1)[0]
            choice = {"Q1": "a,e", "Q4": "c", "Q5": "b", "Q7": "b"}.get(qid, "a")
            r.cli("onboard", "answer", qid, choice, *lib)
        code, out = r.cli("onboard", "summary", *lib)
        r.check("all ten onboarding questions recorded", out.count("answered 20") == 10 or out.count("[answered") == 10, out)

        code, out = r.cli("note", "我早上只喝茶，不喝咖啡。", "--said", *lib)
        r.check("note saves the user's words to the inbox", code == 0 and "SAVED" in out, out)
        code, out = r.cli("note", "我早上只喝茶，不喝咖啡。", "--said", *lib)
        r.check("the same note twice is saved once", "ALREADY SAVED" in out, out)
        code, out = r.cli("find", "早上喝什么", *lib)
        r.check("what was just noted can be found before it is filed", "NOT FILED YET" in out and "只喝茶" in out, out)
        fake = "ghp_" + "A1b2C3d4" * 5
        code, out = r.cli("note", "token " + fake, "--said", *lib)
        r.check("secrets are refused", code == 3 and fake not in out, out)
        code, out = r.cli("note", "我对花生过敏。", "--said", "--private", *lib)
        r.check("a private note follows the user's choice for sensitive things (Q7)", code == 3 and "NOT saved" in out, out)
        code, out = r.cli("note", "the user is probably a morning person", "--inferred", *lib)
        r.check("inferences are refused when the user chose 'important things only'", code == 4, out)

        before_me = _sha(lib_dir / "me.md")
        code, out = r.cli("classify", *lib)
        r.check("classify turns the inbox into a suggested change", code == 0 and "suggested change" in out, out)
        r.check("classify changes no note", _sha(lib_dir / "me.md") == before_me)
        code, out = r.cli("review", "--json", *lib)
        allps = json.loads(out)
        ps = [p for p in allps if not p["target"].startswith("journal/")]
        r.check("one suggested change is waiting", len(ps) == 1, out)
        r.check(
            "the day's journal gets the same record, with the time it was said",
            any(p["target"].startswith("journal/") and re.search(r"\[said \d{4}-\d\d-\d\d \d\d:\d\d\] 我早上只喝茶", p["content"]) for p in allps),
            out,
        )
        pid = ps[0]["id"] if ps else "P-00000000T000000-000000"
        code, out = r.cli("apply", pid, *lib)
        r.check("apply without the user's yes is refused", code == 4, out)
        code, out = r.cli("apply", pid, "--as", "human:me", "--user-said", "好的", *lib)
        r.check("apply with the user's yes works", code == 0 and "APPLIED" in out, out)
        target = lib_dir / ps[0]["target"] if ps else lib_dir / "missing.md"
        r.check("the note now has the user's words with a source marker", target.is_file() and "[said " in target.read_text(encoding="utf-8"))
        code, out = r.cli("undo", pid, "--as", "human:me", *lib)
        r.check("undo restores the note", code == 0 and ("[said " not in target.read_text(encoding="utf-8") if target.exists() else True), out)

        code, out = r.cli("note", "回复别超过三段", "--said", "--said-at", "2026-10-13 21:05", "--category", "关于我", *lib)
        r.check("a note keeps when it was said, to the minute, and its category", "2026-10-13 21:05" in out and "关于我" in out, out)
        r.cli("classify", *lib)
        first = [p for p in json.loads(r.cli("review", "--json", *lib)[1]) if p["target"] == "me.md"]
        if first:
            r.cli("apply", first[0]["id"], "--as", "human:me", "--user-said", "好的", *lib)
        r.cli("note", "回复别超过五段", "--said", "--category", "关于我", "--replaces", "三段", *lib)
        r.cli("classify", *lib)
        swap = [p for p in json.loads(r.cli("review", "--json", *lib)[1]) if p["op"] == "replace_line"]
        r.check(
            "a change of mind becomes a replace-line suggestion that keeps the old wording",
            len(swap) == 1 and "说的是：回复别超过三段" in swap[0]["content"],
            json.dumps(swap, ensure_ascii=False)[:400],
        )
        if swap:
            r.cli("apply", swap[0]["id"], "--as", "human:me", "--user-said", "对，改了", *lib)
        me = (lib_dir / "me.md").read_text(encoding="utf-8")
        r.check("after the user's yes only the newer statement stays", "回复别超过五段" in me and "] 回复别超过三段" not in me, me[-300:])
        code, out = r.cli("index", "--category", "关于我", *lib)
        r.check("records can be filtered by category", code == 0 and "回复别超过五段" in out, out)
        code, out = r.cli("log", "--days", "2", *lib)
        r.check("the log shows records by the day they were said", code == 0 and "回复别超过五段" in out, out)
        code, out = r.cli("find", "段", *lib)
        r.check("a single Chinese character finds notes", code == 0 and "me.md" in out, out)

        (lib_dir / "private" / "health.md").write_text("# Health\n\nprivate details\n", encoding="utf-8")
        code, out = r.cli("read", "private/health.md", *lib)
        r.check("private notes cannot be read", code == 3 and "private details" not in out, out)
        code, out = r.cli("find", "health", "--json", *lib)
        r.check("private notes never show up in search", "private/health.md" not in out, out)
        code, out = r.cli("read", "../outside.md", *lib)
        r.check("paths outside the library are refused", code == 3, out)

        plain = tmp / "plain"
        (plain / "sub").mkdir(parents=True)
        (plain / "a.md").write_text("# Groceries\n\n- eggs\n", encoding="utf-8")
        (plain / "sub" / "b.md").write_bytes(b"---\nupdated: 2020-01-01\n\xe6\x9d\x83\xe5\xa8\x81: yes\n---\n\nold style\r\n")
        hashes = {p: _sha(p) for p in plain.rglob("*.md")}
        code, out = r.cli("adopt", str(plain))
        r.cli("scan", "--library", str(plain))
        r.cli("health", "--library", str(plain))
        r.check("adopting existing notes changes none of them", all(_sha(p) == h for p, h in hashes.items()), out)

        code, out = r.cli("privacy", "scan", "--library", str(lib_dir))
        r.check("library privacy scan runs", code in (0, 3), out)

        init = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        tools = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        call = mcp.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kb_find", "arguments": {"query": "我"}}},
            library=str(lib_dir),
        )
        r.check(
            "MCP server answers initialize, tools/list and tools/call",
            init["result"]["protocolVersion"] == "2025-06-18" and len(tools["result"]["tools"]) >= 10 and not call["result"]["isError"],
            json.dumps(call, ensure_ascii=False),
        )

        if shutil.which("age") and shutil.which("age-keygen"):
            ident = tmp / "test-identity.txt"
            gen = subprocess.run(["age-keygen", "-o", str(ident)], capture_output=True, text=True)
            pub = [ln.split(":", 1)[1].strip() for ln in ident.read_text(encoding="utf-8").splitlines() if ln.startswith("# public key:")][0]
            code, out = r.cli("vault", "init", "--recipient", pub, *lib)
            r.check("vault can be set up with your own key", code == 0, out + gen.stderr)
            code, out = r.cli("vault", "add", "--all-private", *lib)
            files = list((lib_dir / "vault").rglob("*.age"))
            r.check("private notes are encrypted into the vault", code == 0 and len(files) == 1, out)
            r.check("the vault file is not readable text", files and b"private details" not in files[0].read_bytes())
            os.environ["BRAINLIB_VAULT_IDENTITY"] = str(ident)
            dest = tmp / "opened.md"
            code, out = r.cli("vault", "open", "private/health.md", "--out", str(dest), *lib)
            r.check("the owner can open a vault file", code == 0 and dest.is_file() and "private details" in dest.read_text(encoding="utf-8"), out)
            os.environ.pop("BRAINLIB_VAULT_IDENTITY", None)
            code, out = r.cli("vault", "open", "private/health.md", *lib)
            r.check("agents cannot open the vault without the owner's terminal", code == 3, out)
        elif verbose:
            print("SKIP vault checks: age is not installed")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)

    total = r.passed + len(r.failures)
    if r.failures:
        print("SELFTEST FAILED: %d of %d checks failed." % (len(r.failures), total))
        return 1
    print("SELFTEST PASSED: %d checks." % total)
    return 0
