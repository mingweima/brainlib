"""Unit tests. Run: python3 -m unittest discover -s tests

Secrets used in tests are assembled at runtime so the repository's own privacy scan stays clean.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brainlib import (  # noqa: E402
    agentcheck,
    classify,
    cli,
    config,
    connect,
    frontmatter,
    inbox,
    mcp,
    nextstep,
    onboard,
    privacy,
    proposals,
    scan,
)
from brainlib.util import BrainError, atomic_write, command_lock, today, write_json  # noqa: E402

FAKE_TOKEN = "gh" + "p_" + "Zx9" * 13
FAKE_CARD = "4111" + "1111" + "1111" + "1111"


def make_id():
    """A syntactically valid Chinese resident ID number (checksum computed)."""
    body = "11010119900307" + "123"
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check = "10X98765432"[sum(int(a) * b for a, b in zip(body, weights)) % 11]  # brainlib:allow (GB 11643 table)
    return body + check


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="brainlib-test-"))
        self._env = {k: os.environ.get(k) for k in ("BRAINLIB_HOME", "BRAINLIB_PREFIX", "BRAINLIB_LIBRARY", "BRAINLIB_LANG", "BRAINLIB_PRIVATE_WORDS")}
        os.environ["BRAINLIB_HOME"] = str(self.tmp / "home")
        os.environ["BRAINLIB_PREFIX"] = "brainlib"
        for k in ("BRAINLIB_LIBRARY", "BRAINLIB_LANG", "BRAINLIB_PRIVATE_WORDS"):
            os.environ.pop(k, None)
        self.root = self.tmp / "lib"
        self.root.mkdir()

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def lib(self, cfg=None):
        if cfg is not None:
            config.write_config(self.root, cfg)
        return config.load(str(self.root))

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue() + err.getvalue()


class FrontMatterTests(Base):
    def test_parses_common_shapes(self):
        data, body, errors, has = frontmatter.read(
            "---\ntitle: Plan\ntags: [a, b]\nread_when:\n  - planning\n  - review\nowner: human:alex\n"
            "generated:\n  at: 2026-01-02\nnotes: |\n  line one\n  line two\n---\n# Body\n"
        )
        self.assertTrue(has)
        self.assertEqual(errors, [])
        self.assertEqual(data["tags"], ["a", "b"])
        self.assertEqual(data["read_when"], ["planning", "review"])
        self.assertEqual(data["owner"], "human:alex")
        self.assertEqual(data["generated"]["at"], "2026-01-02")
        self.assertIn("line two", data["notes"])
        self.assertTrue(body.startswith("# Body"))

    def test_never_raises_on_garbage(self):
        for text in ("---\n: : :\n[unclosed\n---\nbody", "---\nno end", "", "plain text"):
            data, _body, _errors, _has = frontmatter.read(text)
            self.assertIsInstance(data, dict)


class ScanTests(Base):
    def test_inference_and_legacy_values(self):
        self.write("README.md", "# Home\n\nThe entry page.\n")
        self.write("me.md", "# Me\n\n- [said 2026-10-20] allergic to peanuts\n")
        self.write("people/me.md", "# A note someone else called me\n")
        self.write("old.md", "---\nauthority: 归档\nttl: 30\nupdated: 2020-01-01\n---\n# Old\n")
        self.write("journal/2020-01-05.md", "# A day\n")
        lib = self.lib({})
        entries = {e["path"]: e for e in scan.scan_library(lib)["entries"]}
        self.assertEqual(entries["README.md"]["tier"], "L1")
        self.assertEqual(entries["me.md"]["tier"], "L0")
        self.assertEqual(entries["people/me.md"]["tier"], "L2")
        self.assertEqual(entries["old.md"]["authority"], "archived")
        self.assertEqual(entries["old.md"]["stale_after"], "2020-01-31")
        self.assertTrue(entries["journal/2020-01-05.md"]["stream"])
        self.assertEqual(entries["journal/2020-01-05.md"]["tier"], "L3")

    def test_private_notes_hidden_everywhere(self):
        self.write("a.md", "# Garden\n\nTomatoes.\n")
        self.write("secret-diary.md", "---\nsensitivity: private\ntitle: Diary about garden\n---\ngarden secrets\n")
        self.write("private/x.md", "# garden plan\n")
        lib = self.lib({"zones": [{"path": "private/", "sensitivity": "private"}]})
        scan.scan_library(lib)
        index = json.loads(lib.out("index.json").read_text(encoding="utf-8"))
        paths = [n["path"] for n in index["notes"]]
        self.assertEqual(paths, ["a.md"])
        self.assertEqual(index["private_hidden"], 2)
        guide = lib.out("llms.txt").read_text(encoding="utf-8")
        self.assertNotIn("Diary", guide)
        self.assertEqual([r["path"] for r in scan.find(lib, "garden")], ["a.md"])
        reports = json.loads(lib.out("reports.json").read_text(encoding="utf-8"))
        self.assertEqual(reports["private_plaintext"], 2)
        self.assertNotIn("secret-diary", json.dumps(reports))

    def test_broken_links(self):
        self.write("a.md", "# A\n\n[b](b.md) [[c]] [[missing]] [img](pic.png)\n")
        self.write("b.md", "# B\n")
        self.write("c.md", "# C\n")
        reports = scan.scan_library(self.lib({}))["reports"]
        self.assertEqual([b["target"] for b in reports["broken_links"]], ["[[missing]]"])


class PrivacyTests(Base):
    def test_detects_secrets_and_personal_numbers(self):
        self.assertIsNotNone(privacy.find_secret("token " + FAKE_TOKEN))
        self.assertIsNotNone(privacy.find_secret("card " + FAKE_CARD))
        self.assertIsNotNone(privacy.find_secret("身份证 " + make_id()))
        self.assertIsNotNone(privacy.find_secret("我的银行卡密码是 " + "48" + "21"))
        self.assertIsNone(privacy.find_secret("the password is in my password manager"))
        self.assertIsNone(privacy.find_secret("api key: <your-key>"))
        self.assertIsNone(privacy.find_secret("call me at " + "138" + "0000" + "1111"))

    def test_secrets_in_notes_are_hidden_from_agents_and_from_backups(self):
        self.write("keys.md", "# Keys\n\n- weather api token: %s\n- learn to swim\n" % FAKE_TOKEN)
        lib = self.lib({})
        code, out = self.cli("read", "keys.md", "--library", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertNotIn(FAKE_TOKEN, out)
        self.assertIn("[hidden by brainlib: github-token]", out)
        self.assertIn("brainlib hid 1", out)
        code, out = self.cli("index", "--library", str(self.root))
        self.assertNotIn(FAKE_TOKEN, out)
        self.assertNotIn(FAKE_TOKEN, lib.out("index.json").read_text(encoding="utf-8"))
        self.assertNotIn(FAKE_TOKEN, lib.out("llms.txt").read_text(encoding="utf-8"))
        with self.assertRaises(BrainError):
            proposals.create(lib, "replace", "keys.md", "# Keys\n\n- token: [hidden by brainlib: github-token]\n", "tidy")
        first = proposals.create(lib, "append", "keys.md", "- buy goggles", "user said so")
        self.assertFalse(proposals.apply(lib, first["id"], approved_by="human:me")["secret_removed"])
        clean = "# Keys\n\n- weather api token: in my password manager\n- learn to swim\n- buy goggles\n"
        fix = proposals.create(lib, "replace", "keys.md", clean, "move the token out")
        self.assertTrue(proposals.apply(lib, fix["id"], approved_by="human:me")["secret_removed"])
        for f in lib.state("backups").glob("*.bak"):
            self.assertNotIn(FAKE_TOKEN.encode("utf-8"), f.read_bytes(), f.name)
        code, out = self.cli("undo", fix["id"], "--as", "human:me", "--library", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("stay hidden", out)
        self.assertNotIn(FAKE_TOKEN, (self.root / "keys.md").read_text(encoding="utf-8"))

    def test_masked_excerpts_never_show_the_value(self):
        hits = privacy.scan_text("x " + FAKE_TOKEN)
        self.assertTrue(hits)
        self.assertNotIn(FAKE_TOKEN, json.dumps([h.as_dict() for h in hits]))

    def test_words_and_allow_list(self):
        (self.root / ".brainlib-allow").write_text("LICENSE Jane Doe\n.brainlib-allow Jane Doe\n", encoding="utf-8")
        (self.root / "LICENSE").write_text("Copyright Jane Doe\njane was here\n", encoding="utf-8")
        words = self.tmp / "words.txt"
        words.write_text("Jane\n", encoding="utf-8")
        hits, notes = privacy.scan_files(self.root, ["LICENSE", ".brainlib-allow"], "release", words_path=str(words))
        self.assertEqual([(h.path, h.line) for h in hits], [("LICENSE", 2)])
        self.assertTrue(any("allowed phrase" in n for n in notes))

    def test_release_needs_word_list(self):
        with self.assertRaises(BrainError) as cm:
            privacy.scan_files(self.root, [], "release", words_path=None)
        self.assertEqual(cm.exception.code, 3)

    def test_neutral_emails_pass_commit_mode(self):
        (self.root / "a.md").write_text("alex@example.com\nreal.person" + "@" + "gmail.com\n", encoding="utf-8")
        hits, _ = privacy.scan_files(self.root, ["a.md"], "commit")
        self.assertEqual([h.line for h in hits if h.rule == "email"], [2])


class InboxTests(Base):
    def test_provenance_dedup_and_refusals(self):
        lib = self.lib({})
        item, dup = inbox.add(lib, "I like tea", "said")
        self.assertIsNone(dup)
        self.assertEqual(item["provenance"], "principal-said")
        _item, dup = inbox.add(lib, "  i like   TEA ", "said")
        self.assertEqual(dup, item["id"])
        with self.assertRaises(BrainError) as cm:
            inbox.add(lib, "key " + FAKE_TOKEN, "said")
        self.assertEqual(cm.exception.code, 3)
        with self.assertRaises(BrainError):
            inbox.add(lib, "x", "rumour")

    def test_private_items(self):
        lib = self.lib({})
        with self.assertRaises(BrainError):
            inbox.add(lib, "my health detail", "said", sensitivity="private")
        with self.assertRaises(BrainError):
            inbox.add(lib, "my health detail", "said", sensitivity="private", private_handling="exclude")
        item, _ = inbox.add(lib, "my health detail", "said", sensitivity="private", private_handling="ask_first")
        self.assertEqual([i["status"] for i in inbox.all_items(lib)], ["private-held"])
        self.assertEqual(item["sensitivity"], "private")

    def test_noted_items_are_found_before_they_are_filed(self):
        self.write("me.md", "---\ntitle: 关于我\ntier: L0\n---\n\n# 关于我\n")
        lib = self.lib({})
        tea, _ = inbox.add(lib, "我早上只喝茶，不喝咖啡。", "said", said_at="2026-10-20")
        inbox.add(lib, "我早上的血压偏高。", "said", sensitivity="private", private_handling="normal")
        code, out = self.cli("find", "早上喝什么", "--library", str(self.root), "--json")
        self.assertEqual(code, 0, out)
        res = json.loads(out)
        self.assertEqual([n["line"] for n in res["not_filed"]], ["[said 2026-10-20] 我早上只喝茶，不喝咖啡。"])
        code, out = self.cli("index", "--library", str(self.root))
        self.assertIn("[said 2026-10-20] 我早上只喝茶", out)
        self.assertNotIn("血压", out)
        inbox.set_status(lib, tea["id"], "applied")
        code, out = self.cli("find", "早上喝什么", "--library", str(self.root), "--json")
        self.assertEqual(json.loads(out)["not_filed"], [])

    def test_note_now_turns_it_into_a_labelled_change_at_once(self):
        self.write("projects/house.md", "# House\n\nThe budget is in the budget note.\n")
        lib = self.lib({})
        args = ("note", "add 20k to the renovation budget", "--said", "--target", "projects/house.md", "--now")
        code, out = self.cli(*args, "--library", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("NEXT: show this to the user", out)
        self.assertIn("[said %s] add 20k" % today().isoformat(), out)
        [p] = proposals.list_proposals(lib, states=("open",))
        code, out = self.cli(*args, "--library", str(self.root))
        self.assertIn(p["id"], out)
        self.assertEqual(len(proposals.list_proposals(lib, states=("open",))), 1)
        code, out = self.cli("note", "some words", "--said", "--now", "--library", str(self.root))
        self.assertEqual(code, 2, out)
        argv = mcp._argv_for("kb_note", {"text": "x", "provenance": "said", "private": False, "now": True}, None)
        self.assertIn("--not-sensitive", argv)
        self.assertIn("--now", argv)


class ProposalTests(Base):
    def setUp(self):
        super().setUp()
        self.write("me.md", "---\ntier: L0\n---\n# Me\n")
        self.write("notes/tea.md", "# Tea\r\n\r\nGreen tea.\r\n")
        self.write("private/p.md", "# P\n")

    def test_append_apply_receipt_undo_and_crlf(self):
        lib = self.lib({"zones": [{"path": "private/", "sensitivity": "private"}]})
        p = proposals.create(lib, "append", "notes/tea.md", "- likes oolong", "user said so", evidence=[{"provenance": "principal-said"}])
        self.assertEqual(p["approval"], "owner")
        with self.assertRaises(BrainError) as cm:
            proposals.apply(lib, p["id"])
        self.assertEqual(cm.exception.code, 4)
        r = proposals.apply(lib, p["id"], approved_by="human:me")
        data = (self.root / "notes/tea.md").read_bytes()
        self.assertIn(b"- likes oolong\r\n", data)
        self.assertNotIn(b"\n\n", data.replace(b"\r\n", b"\r"))
        self.assertFalse(r["contains_content"])
        receipts = list(lib.state("receipts").glob("*.jsonl"))
        self.assertNotIn("oolong", receipts[0].read_text(encoding="utf-8"))
        proposals.undo(lib, p["id"], "human:me")
        self.assertEqual((self.root / "notes/tea.md").read_bytes(), b"# Tea\r\n\r\nGreen tea.\r\n")

    def test_notes_not_saved_as_utf8_are_reported_and_left_alone(self):
        old = self.root / "notes" / "old.md"
        original = "# 旧笔记\n\n以前用记事本写的。\n".encode("gbk")
        old.write_bytes(original)
        lib = self.lib()
        self.assertEqual(scan.scan_library(lib)["reports"]["not_utf8"], ["notes/old.md"])
        with self.assertRaises(BrainError):
            proposals.create(lib, "append", "notes/old.md", "- one more line", "user asked")
        code, out = self.cli("note", "one more line for the old note", "--said", "--target", "notes/old.md", "--library", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("not saved as UTF-8", out)
        summary = classify.run(lib)
        self.assertNotIn("errors", summary)
        self.assertNotIn("notes/old.md", [p["target"] for p in summary["proposals"]])
        self.assertEqual(old.read_bytes(), original)

    def test_policy(self):
        lib = self.lib({"zones": [{"path": "private/", "sensitivity": "private"}]})
        p = proposals.create(lib, "append", "me.md", "- [said 2026-01-01] calm", "profile")
        with self.assertRaises(BrainError) as cm:
            proposals.apply(lib, p["id"], approved_by="human:me")
        self.assertEqual(cm.exception.code, 4)
        proposals.apply(lib, p["id"], approved_by="human:me", user_words="yes, add it")
        with self.assertRaises(BrainError):
            proposals.create(lib, "append", "me.md", "x", "web", evidence=[{"provenance": "third-party"}])
        for bad in ("private/p.md", "../escape.md", "/etc/passwd.md", "vault/x.md"):
            with self.assertRaises(BrainError):
                proposals.create(lib, "append", bad, "x", "r")
        with self.assertRaises(BrainError):
            proposals.create(lib, "append", "notes/tea.md", "token " + FAKE_TOKEN, "r")

    def test_approval_must_be_an_answer_not_the_recorded_words(self):
        lib = self.lib({})
        p = proposals.create(lib, "append", "me.md", "- 我早上只喝茶，不喝咖啡。 [said 2026-10-20]", "profile")
        for echo in ("记住我早上只喝茶，不喝咖啡；我下个月要去成都出差。", "我早上只喝茶不喝咖啡"):
            with self.assertRaises(BrainError) as cm:
                proposals.apply(lib, p["id"], approved_by="human:me", user_words=echo)
            self.assertEqual(cm.exception.code, 4)
        proposals.apply(lib, p["id"], approved_by="human:me", user_words="可以，加进去吧")
        self.assertIn("只喝茶", (self.root / "me.md").read_text(encoding="utf-8"))

    def test_replace_goes_stale(self):
        lib = self.lib({})
        p = proposals.create(lib, "replace", "notes/tea.md", "# Tea\n\nNew.\n", "rewrite")
        self.write("notes/tea.md", "# Tea\n\nChanged meanwhile.\n")
        with self.assertRaises(BrainError) as cm:
            proposals.apply(lib, p["id"], approved_by="human:me")
        self.assertEqual(cm.exception.code, 5)
        self.assertEqual(proposals.get(lib, p["id"])["status"], "stale")

    def test_read_only_mode_blocks_writes(self):
        lib = self.lib({"settings": {"edit_mode": "read_only"}})
        with self.assertRaises(BrainError):
            proposals.create(lib, "append", "notes/tea.md", "x", "r")

    def test_auto_low_risk_journal(self):
        lib = self.lib({"zones": [{"path": "journal/", "stream": True, "auto_apply": True}], "settings": {"edit_mode": "auto_low_risk"}})
        inbox.add(lib, "went for a run", "said", target="journal/2026-10-20.md")
        self.write("journal/2026-10-20.md", "# Today\n")
        summary = classify.run(lib)
        self.assertEqual(summary["auto_applied"], 1)
        self.assertIn("went for a run", (self.root / "journal/2026-10-20.md").read_text(encoding="utf-8"))

    def test_suggested_new_note_is_created_after_approval(self):
        lib = self.lib({"zones": [{"path": "private/", "sensitivity": "private"}]})
        inbox.add(lib, "wants to learn the cello", "said", target="hobbies/music.md")
        inbox.add(lib, "a private plan", "said", target="private/plan.md")
        summary = classify.run(lib)
        targets = sorted(p["target"] for p in summary["proposals"])
        self.assertEqual(targets, ["hobbies/music.md", "inbox-unsorted.md"])
        pid = [p["id"] for p in summary["proposals"] if p["target"] == "hobbies/music.md"][0]
        proposals.apply(lib, pid, approved_by="human:me")
        self.assertIn("cello", (self.root / "hobbies/music.md").read_text(encoding="utf-8"))

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_writes_keep_file_permissions(self):
        p = self.write("notes/shared.md", "# Shared\n")
        os.chmod(p, 0o644)
        atomic_write(p, "# Shared\n\nmore\n")
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o644)


class ClassifyTests(Base):
    def test_function_words_do_not_pick_a_note(self):
        for lang, said in (("en", "Remember that I only drink tea in the morning."), ("zh", "这个周末我想去爬山")):
            os.environ["BRAINLIB_LANG"] = lang
            root = self.tmp / ("lib-" + lang)
            self.cli("init", str(root))
            lib = config.load(str(root))
            inbox.add(lib, said, "said")
            targets = [p["target"] for p in classify.run(lib, dry_run=True)["proposals"]]
            self.assertEqual(targets, ["inbox-unsorted.md"], lang)
        root = self.tmp / "lib-en"
        (root / "tea.md").write_text("---\ntitle: Tea\n---\n# Tea\n", encoding="utf-8")
        lib = config.load(str(root))
        scan.scan_library(lib)
        targets = [p["target"] for p in classify.run(lib, dry_run=True)["proposals"]]
        self.assertEqual(targets, ["tea.md"])
        self.assertEqual([e["path"] for e in scan.find(lib, "what do I drink in the morning")][:1], [])
        self.assertIn("drink tea", scan.find_noted(lib, "what do I drink in the morning")[0]["line"])

    def test_new_lines_on_me_land_under_recently_noted(self):
        for lang, heading in (("en", "## Recently noted"), ("zh", "## 最近记下的")):
            os.environ["BRAINLIB_LANG"] = lang
            root = self.tmp / ("me-" + lang)
            self.cli("init", str(root))
            lib = config.load(str(root))
            p = proposals.create(lib, "append", "me.md", "- [said 2026-10-20] likes oolong", "profile")
            proposals.apply(lib, p["id"], approved_by="human:me", user_words="yes")
            text = (root / "me.md").read_text(encoding="utf-8")
            self.assertGreater(text.index("likes oolong"), text.index(heading), lang)


class OnboardingTests(Base):
    def test_questions_complete_and_bilingual(self):
        data = onboard.load_questions()
        self.assertEqual(len(data["questions"]), 10)
        for q in data["questions"]:
            self.assertTrue(q["ask"]["zh"] and q["ask"]["en"] and q["why"]["zh"] and q["why"]["en"], q["id"])
            for o in q["options"]:
                self.assertTrue(o["zh"] and o["en"], (q["id"], o["id"]))

    def test_answer_forms_and_settings(self):
        lib = self.lib({})
        onboard.answer(lib, "Q1", "ae")
        onboard.answer(lib, "q4", "propose")
        onboard.answer(lib, "Q5", "3")
        onboard.answer(lib, "Q7", "b")
        with self.assertRaises(BrainError):
            onboard.answer(lib, "Q4", "a,b")
        with self.assertRaises(BrainError):
            onboard.answer(lib, "Q4", "z")
        s = onboard.settings(lib)
        self.assertEqual(s["purposes"], ["remember", "understand"])
        self.assertEqual(s["edit_mode"], "propose")
        self.assertEqual(s["record_policy"], "with_inferences")
        self.assertIn("calibration", s["features"])
        self.assertTrue(onboard.allows_provenance(s, "agent-inference"))
        self.assertFalse(onboard.allows_provenance(s, "third-party"))

    def test_answers_evolve(self):
        lib = self.lib({})
        for q in onboard.load_questions()["questions"]:
            onboard.answer(lib, q["id"], "skip" if q["id"] == "Q2" else "a")
        self.assertTrue(onboard.is_complete(lib))
        self.assertEqual(onboard.next_question(lib), (None, None))
        for text in ("just do it", "stop asking", "you decide"):
            onboard.signal(lib, "Q4", text)
        q, reason = onboard.next_question(lib)
        self.assertEqual(q["id"], "Q4")
        self.assertIn("3", reason)
        onboard.answer(lib, "Q4", "d")
        self.assertIsNone(onboard.next_question(lib)[0])
        prof = onboard.profile(lib)
        prof["answers"]["Q8"]["revisit_at"] = (today() - timedelta(days=1)).isoformat()
        write_json(lib.state("profile.json"), prof)
        self.assertEqual(onboard.next_question(lib)[0]["id"], "Q8")
        history = lib.state("profile-history.jsonl").read_text(encoding="utf-8")
        self.assertEqual(history.count('"question": "Q4"'), 2)


class ConnectTests(Base):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "userhome"
        self.home.mkdir()
        self._home_env = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "CODEX_HOME")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.home)
        os.environ.pop("CODEX_HOME", None)

    def tearDown(self):
        for k, v in self._home_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def test_write_is_idempotent_and_removable(self):
        lib = self.lib({})
        path = self.home / ".claude" / "CLAUDE.md"
        path.parent.mkdir()
        original = "# Mine\n\nKeep this line.\n"
        path.write_text(original, encoding="utf-8")
        r = connect.write(lib, "claude-code", 'python3 "/x/brainlib.py"', "zh")
        self.assertTrue(r["changed"])
        self.assertTrue(Path(r["backup"]).is_file())
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(original.rstrip("\n")))
        self.assertIn('python3 "/x/brainlib.py" next', text)
        self.assertIn(str(self.root), text)
        self.assertFalse(connect.write(lib, "claude-code", 'python3 "/x/brainlib.py"', "zh")["changed"])
        connect.remove("claude-code")
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        with self.assertRaises(BrainError):
            connect.write(lib, "cursor", "brainlib", "zh")

    def test_next_asks_to_connect_after_onboarding(self):
        lib = self.lib({})
        for q in onboard.load_questions()["questions"]:
            onboard.answer(lib, q["id"], "a")
        nextstep.mark_done(lib, "permissions")
        self.assertEqual(nextstep.compute(lib)["key"], "connect")
        nextstep.mark_done(lib, "connect")
        self.assertNotEqual(nextstep.compute(lib)["key"], "connect")
        code, out = self.cli("connect", "--tool", "cursor", "--library", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("SAY TO USER", out)
        self.assertIn("<!-- brainlib:start -->", out)

    def test_next_offers_the_vault_when_the_user_chose_it(self):
        lib = self.lib({})
        for q in onboard.load_questions()["questions"]:
            onboard.answer(lib, q["id"], "b" if q["id"] == "Q7" else "a")
        nextstep.mark_done(lib, "permissions")
        nextstep.mark_done(lib, "connect")
        s = nextstep.compute(lib)
        self.assertEqual(s["key"], "private")
        self.assertTrue(any("vault init" in r for r in s["run"]))
        self.assertIn("口令", s["say"])
        nextstep.snooze(lib, "private")
        self.assertNotEqual(nextstep.compute(lib)["key"], "private")

    def test_suggestions_wait_for_the_review_the_user_chose(self):
        lib = self.lib({"zones": [{"path": "journal/", "stream": True, "auto_apply": True}]})
        self.write("me.md", "---\ntier: L0\n---\n# Me\n")
        for q in onboard.load_questions()["questions"]:
            onboard.answer(lib, q["id"], {"Q4": "c", "Q8": "b"}.get(q["id"], "a"))
        nextstep.mark_done(lib, "permissions")
        nextstep.mark_done(lib, "connect")
        nextstep.mark_reviewed(lib)
        code, out = self.cli("note", "likes window seats", "--said", "--target", "me.md", "--library", str(self.root))
        self.assertEqual(code, 2, out)
        self.assertIn("Health", out)
        code, out = self.cli(
            "note", "likes window seats", "--said", "--not-sensitive", "--target", "me.md", "--library", str(self.root)
        )
        self.assertEqual(code, 0, out)
        self.assertIn("again with --now", out)
        s = nextstep.compute(lib)
        self.assertEqual(s["key"], "classify")
        self.assertIn("sensitive (onboarding Q6): Health.", s["rules"])
        self.assertIn("ALWAYS, whatever the user asks", nextstep.render(s))
        code, out = self.cli("classify", "--library", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("next review", out)
        self.assertNotIn("NEXT:", out)
        scan.scan_library(lib)
        s = nextstep.compute(lib)
        self.assertEqual(s["key"], "all-clear")
        self.assertIn("1 suggested change(s) wait", s["next"])
        self.assertIn("--target journal/%s.md" % today().isoformat(), s["rules"])
        self.assertIn("propose only to fix or remove", s["rules"])
        code, out = self.cli("note", "I am allergic to peanuts", "--said", "--private", "--library", str(self.root))
        self.assertEqual(code, 3, out)
        self.assertIn("NOT saved", out)
        code, out = self.cli(
            "propose", "append", "me.md", "--text", "- likes aisle seats [said 2026-10-20]", "--reason", "user said so",
            "--library", str(self.root),
        )
        self.assertEqual(code, 2, out)
        self.assertIn("Only brainlib note adds these labels", out)
        self.write("people/ann.md", "# Ann\n- likes tea [said 2026-10-01]\n- typo hre\n")
        code, out = self.cli(
            "propose", "replace", "people/ann.md", "--text", "# Ann\n- likes tea [said 2026-10-01]\n- typo here\n",
            "--reason", "fix a typo", "--library", str(self.root),
        )
        self.assertEqual(code, 0, out)

    def test_daily_hint_names_the_users_own_sensitive_topics(self):
        lib = self.lib()
        onboard.answer(lib, "Q6", "a,g", other_text="my divorce")
        onboard.answer(lib, "Q7", "c")
        line = nextstep._sensitive_line(lib, onboard.settings(lib))
        self.assertIn('Health; "my divorce".', line)
        self.assertIn("ask the user first", line)
        onboard.answer(lib, "Q7", "d")
        self.assertEqual(nextstep._sensitive_line(lib, onboard.settings(lib)), "")


class AgentCheckTests(Base):
    def test_small_model_is_judged_by_whole_words(self):
        for name in ("gpt-4o-mini", "Gemini 2.0 Flash", "claude-3-haiku", "Qwen2.5-7B-Instruct", "composer-2.5-fast", "Llama 3.2 3B"):
            self.assertTrue(agentcheck.is_small_model(name), name)
        for name in ("Gemini 4 Argon", "MiniMax-M2", "Llama 3.1 70B", "DeepSeek-R1 671B", "Mistral Large 123B", "", None):
            self.assertFalse(agentcheck.is_small_model(name), name)

    def test_result_is_said_in_both_languages_until_one_is_chosen(self):
        for lang, has_zh in ((None, True), ("en", False)):
            if lang:
                self.cli("lang", lang)
            s = agentcheck.start("agent/b")
            for i, a in enumerate(self._answers(s), 1):
                agentcheck.answer(i, a)
            say = agentcheck.finish(model="test-model")[1]
            self.assertEqual("自测" in say, has_zh, say)
            self.assertIn("self-check", say)

    def _answers(self, s):
        target = [n["path"] for n in s["data"]["notes"] if n["tier"] == s["ask_tier"]][0]
        right = "abc"[[o["ok"] for o in s["privacy"]].index(True)]
        return [s["code"], ",".join(p["answer"] for p in s["prov"]), right, target]

    def test_pass_and_failure_must_be_told(self):
        s = agentcheck.start("agent/a", lang="zh")
        answers = self._answers(s)
        agentcheck.answer(1, answers[0])
        agentcheck.answer(1, "changed my mind")
        agentcheck.answer(2, answers[1])
        agentcheck.answer(3, answers[2])
        agentcheck.answer(4, "notes/wrong.md")
        result, say = agentcheck.finish(model="tiny-7b")
        self.assertFalse(result["passed"])
        self.assertEqual(result["score"], 3)
        self.assertIn("3/4", say)
        s = agentcheck.start("agent/a")
        for i, a in enumerate(self._answers(s), 1):
            agentcheck.answer(i, a)
        self.assertTrue(agentcheck.finish()[0]["passed"])
        self.assertEqual(agentcheck.state("agent/a")[0], "failed")
        agentcheck.acknowledge("agent/a")
        self.assertEqual(agentcheck.state("agent/a")[0], "ok")
        self.assertEqual(agentcheck.state("agent/b")[0], "missing")


class CliTests(Base):
    def test_rewrite_only_touches_commands(self):
        os.environ["BRAINLIB_PREFIX"] = 'python3 "/x y/brainlib.py"'
        text = cli.rewrite("RUN: brainlib next\nbrainlib works offline; see brainlib-setup and `brainlib vault init`")
        self.assertIn('RUN: python3 "/x y/brainlib.py" next', text)
        self.assertIn("brainlib works offline", text)
        self.assertIn("brainlib-setup", text)
        self.assertIn('`python3 "/x y/brainlib.py" vault init`', text)
        code, out = self.cli("next", "--json")
        self.assertEqual(code, 0)
        self.assertIn("agent-check", json.loads(out)["run"][0])

    def test_exit_codes_and_errors(self):
        self.write("a.md", "# A\n")
        code, out = self.cli("read", "missing.md", "--library", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("ERROR:", out)
        self.assertIn("FIX:", out)
        code, out = self.cli("note", "hello", "--library", str(self.root))
        self.assertEqual(code, 2)
        code, out = self.cli("note", "hello", "--said", "--library", str(self.root))
        self.assertEqual(code, 0)
        code, out = self.cli("lang", "klingon")
        self.assertEqual(code, 2)

    @unittest.skipIf(os.name == "nt", "uses a shell script as a stand-in python3")
    def test_run_lines_name_a_python_that_can_run_brainlib(self):
        from brainlib import cli

        bindir = self.tmp / "bin"
        bindir.mkdir()
        fake = bindir / "python3"
        fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake.chmod(0o755)
        saved = os.environ["PATH"]
        try:
            os.environ["PATH"] = str(bindir)
            cli._python.cache_clear()
            self.assertIn(cli._python(), (sys.executable, '"%s"' % sys.executable))
            fake.unlink()
            fake.symlink_to(sys.executable)
            cli._python.cache_clear()
            self.assertEqual(cli._python(), "python3")
        finally:
            os.environ["PATH"] = saved
            cli._python.cache_clear()

    def test_forgiving_forms_small_models_use(self):
        lib = ["--library", str(self.root)]
        self.write("a.md", "# A\n")
        code, out = self.cli("help")
        self.assertEqual(code, 0)
        self.assertIn("connect", out)
        code, out = self.cli("vault", *lib)
        self.assertEqual(code, 0, out)
        self.assertIn("vault set up", out)
        code, out = self.cli("onboard", "answer", "Q2 a,c", *lib)
        self.assertEqual(code, 0, out)
        self.assertIn("RECORDED Q2", out)
        code, out = self.cli("privacy", "scan", "--mode", "library", str(self.root / "a.md"), *lib)
        self.assertEqual(code, 0, out)
        self.assertIn("1 file(s)", out)
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            cli.main(["privacy", "scan", "--bogus"])
        self.assertEqual(cm.exception.code, 2)

    def test_adopt_leaves_notes_byte_identical(self):
        files = {
            "a.md": b"# A\n\nplain\n",
            "b/c.md": b"---\nauthority: \xe6\x9d\x83\xe5\xa8\x81\nweird: [unclosed\n---\r\nCRLF body\r\n",
            ".obsidian/app.json": b"{}",
        }
        for rel, data in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        self.cli("adopt", str(self.root))
        self.cli("scan", "--library", str(self.root))
        self.cli("health", "--library", str(self.root))
        self.cli("next", "--library", str(self.root))
        for rel, data in files.items():
            self.assertEqual((self.root / rel).read_bytes(), data, rel)

    def test_parallel_commands_do_not_lose_answers(self):
        launcher = str(Path(__file__).resolve().parent.parent / "brainlib.py")
        procs = [
            subprocess.Popen(
                [sys.executable, launcher, "onboard", "answer", "Q%d" % n, "a", "--library", str(self.root)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for n in range(1, 7)
        ]
        self.assertEqual([p.wait(timeout=60) for p in procs], [0] * 6)
        answers = onboard.profile(self.lib())["answers"]
        self.assertEqual(sorted(answers), ["Q%d" % n for n in range(1, 7)])

    def test_command_lock_reenters_waits_and_clears_stale_locks(self):
        home = self.tmp / "home"
        lock = home / "command.lock"
        with command_lock(home):
            with command_lock(home, wait=0):
                self.assertTrue(lock.exists())
        self.assertFalse(lock.exists())
        lock.write_text("%d %f\n" % (os.getpid(), time.time()), encoding="ascii")
        with self.assertRaises(BrainError):
            with command_lock(home, wait=0.2):
                pass
        if os.name != "nt":
            gone = subprocess.Popen([sys.executable, "-c", "pass"])
            gone.wait()
            lock.write_text("%d %f\n" % (gone.pid, time.time()), encoding="ascii")
            with command_lock(home, wait=0.2):
                pass
        lock.write_text("%d %f\n" % (os.getpid(), time.time() - 3600), encoding="ascii")
        with command_lock(home, wait=0.2):
            pass
        self.assertFalse(lock.exists())


class McpTests(Base):
    def test_protocol_and_refusals(self):
        self.write("a.md", "# Tea notes\n")
        config.write_config(self.root, {})
        init = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(init["result"]["protocolVersion"], mcp.PROTOCOL_VERSIONS[0])
        self.assertIsNone(mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        names = {t["name"] for t in mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
        self.assertIn("kb_decide", names)
        res = mcp.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kb_decide", "arguments": {"id": "P-1", "decision": "apply"}}},
            library=str(self.root),
        )
        self.assertTrue(res["result"]["isError"])
        res = mcp.handle(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "kb_find", "arguments": {"query": "tea"}}},
            library=str(self.root),
        )
        self.assertIn("a.md", res["result"]["content"][0]["text"])
        self.assertEqual(mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "nope"})["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
