"""`brainlib next`: exactly one clear next step, so agents of any size know what to do.

The output format is stable and meant to be followed literally:

    NEXT: <what to do>
    WHY: <one sentence>
    RUN: <command>              (zero or more)
    SAY TO USER: <sentence>     (optional; say it in the user's language)
    THEN: run `brainlib next` again.
"""

from datetime import timedelta
from pathlib import Path

from . import agentcheck, config, doctor, i18n, inbox, onboard, proposals, scan, vault
from .util import now_iso, parse_date, read_json, today, write_json

SNOOZE_DAYS = 7
ONE_TIME_STEPS = ("permissions", "connect")
SETUP_SKILL = Path(__file__).resolve().parent.parent / "skills" / "brainlib-setup" / "SKILL.md"


def mark_done(lib, key):
    path = lib.state("setup.json")
    data = read_json(path, {}) or {}
    data[key] = now_iso()
    write_json(path, data)


def _done(lib, key):
    return bool((read_json(lib.state("setup.json"), {}) or {}).get(key))


def _snoozed(lib):
    data = read_json(lib.state("next-snoozed.json"), {}) or {}
    t = today()
    return {k for k, until in data.items() if parse_date(until) and parse_date(until) >= t}


def snooze(lib, key, days=SNOOZE_DAYS):
    path = lib.state("next-snoozed.json")
    data = read_json(path, {}) or {}
    data[key] = (today() + timedelta(days=days)).isoformat()
    write_json(path, data)
    return data[key]


def mark_reviewed(lib):
    write_json(lib.state("last-review.json"), {"at": today().isoformat()})


def review_due(lib, settings, open_count):
    days = settings.get("review_cadence_days")
    if open_count >= 10:
        return True
    if days is None:
        return False
    last = parse_date((read_json(lib.state("last-review.json"), {}) or {}).get("at"))
    return last is None or (today() - last).days >= days


def step(key, nxt, why, run=None, say=None, extra=None, snoozable=False):
    return {"key": key, "next": nxt, "why": why, "run": list(run or []), "say": say, "extra": extra, "snoozable": snoozable}


def preflight(actor, lang, lang_chosen):
    """Steps that come before any library work: the agent self-check and the user's language."""
    st, last = agentcheck.state(actor)
    if st == "missing":
        return step(
            "agent-check",
            "Do the 4-task self-check before anything else.",
            "It shows whether you can manage the user's notes reliably; if not, the user must be warned.",
            run=["brainlib agent-check"],
        )
    if st == "failed":
        return step(
            "agent-check-warn",
            "Tell the user the result of your self-check.",
            "You got %d of %d right; the user should decide how much to trust you with their notes." % (last["score"], last["total"]),
            say=(
                i18n.t("check_fail", lang, score=last["score"], total=last["total"])
                if lang_chosen
                else i18n.both("check_fail", score=last["score"], total=last["total"])
            ),
            run=[
                "After telling the user: brainlib agent-check ack",
                "If the user wants read-only mode, answer onboarding question Q4 with a when you get there.",
            ],
            extra="Wait for the user's answer. Unless they say stop, carry on with setup: run brainlib agent-check ack, then brainlib next.",
        )
    if not lang_chosen:
        return step(
            "language",
            "Ask the user which language they prefer.",
            "Everything you say to the user should be in their language.",
            say="%s\n%s" % (i18n.MESSAGES["choose_lang"]["zh"], i18n.MESSAGES["choose_lang"]["en"]),
            run=["Then record it: brainlib lang zh   (or: brainlib lang en)"],
            extra="For another language, record en for brainlib's texts and speak the user's language yourself.",
        )
    return None


def no_library(lang):
    suggested = str(doctor.suggested_library_path())
    return step(
        "choose-library",
        "Check this computer, then ask the user where their library should live.",
        "brainlib works on a folder of Markdown notes, and no folder is selected yet.",
        run=[
            "brainlib doctor",
            "If they pick a): brainlib init \"%s\"" % suggested,
            "If they pick b): brainlib adopt \"<their notes folder>\"   (their notes are never changed)",
            "If they pick c): brainlib init \"<a new folder inside their synced drive>\"",
        ],
        say=i18n.t("choose_library", lang, suggested=suggested),
        extra=(
            "Ask one question at a time. Use the folder path exactly as the user gives it; on Windows a path looks like "
            "%USERPROFILE%\\brain or D:\\notes\\brain, on macOS and Linux like ~/brain."
        ),
    )


def compute(lib, lang="zh"):
    settings = onboard.settings(lib)
    snoozed = _snoozed(lib)

    # 0. One-time setup: computer and tool permissions.
    if not _done(lib, "permissions"):
        guide = (" Step-by-step guide: %s" % SETUP_SKILL) if SETUP_SKILL.is_file() else ""
        return step(
            "permissions",
            "Check this computer and your own tool permissions with the user (one time).",
            "The library must be readable and writable for you, while vault/ and private/ stay out of your reach.",
            run=["brainlib doctor", "When everything the user agreed to is done: brainlib next --done permissions"],
            say=i18n.t("permissions", lang),
            extra="Go through the TODO lines from `brainlib doctor` one by one. Do only what the user agrees to." + guide,
        )

    # 1. Onboarding comes first: it decides permissions.
    if not onboard.is_complete(lib):
        q, _reason = onboard.next_question(lib)
        data = onboard.load_questions()
        number = [x["id"] for x in data["questions"]].index(q["id"]) + 1
        say = None
        if not onboard.started(lib):
            say = data["intro"].get(lang) or data["intro"]["en"]
        return step(
            "onboarding",
            "Ask the user onboarding question %s (%d of %d)." % (q["id"], number, len(data["questions"])),
            "Until these are answered, brainlib uses safe defaults: suggest changes, never apply without a yes.",
            say=say,
            extra=onboard.render_question(q, lang=lang, number=number, total=len(data["questions"])),
        )

    # 1b. One time: new conversations in the user's tools must know the library exists.
    if not _done(lib, "connect") and "connect" not in snoozed:
        return step(
            "connect",
            "Ask the user which AI tools they use, and connect each one to this library (one time).",
            "Otherwise a new conversation does not know the library exists, so nothing gets read or remembered.",
            run=["brainlib connect", "When the user's tools are connected: brainlib next --done connect"],
            say=i18n.t("connect", lang),
            extra="Show the user the text before writing it into any tool. If the user says not now: brainlib next --snooze connect",
            snoozable=True,
        )

    # 2. Keep the index current (scanning never changes notes).
    if scan.is_stale(lib):
        scan.scan_library(lib, write=True)
    reports = scan.load_index(lib, refresh_if_stale=False) and (read_json(lib.out("reports.json"), {}) or {})

    # 3. Privacy problems.
    secrets = reports.get("secrets_in_library") or []
    if secrets and "secrets" not in snoozed:
        where = ", ".join(
            "%s%s" % (s["path"], (" line %s" % s["line"]) if s.get("line") else "") for s in secrets[:3]
        )
        return step(
            "secrets",
            "Tell the user a password or key seems to be stored in their notes.",
            "Secrets in notes can leak through backups, sync or agents.",
            say=i18n.t("secrets", lang, where=where),
            run=["Do not copy the secret anywhere. If the user says not now: brainlib next --snooze secrets"],
            snoozable=True,
        )
    priv = reports.get("private_plaintext") or 0
    if settings.get("private_handling") == "vault" and "private" not in snoozed:
        if not vault.is_initialized(lib):
            run = [] if vault.age_bin() else [
                "age is not installed yet. brainlib doctor shows the install command for this computer; install it only if the user agrees."
            ]
            run += [
                "Only the user may run this, in their own terminal: brainlib vault init",
                "If the user says not now: brainlib next --snooze private",
            ]
            return step(
                "private",
                ("Suggest the user set up the vault for %d private note(s)." % priv) if priv
                else "Help the user set up the encrypted vault they chose (onboarding Q7).",
                "The user chose the encrypted vault for sensitive things, but it is not set up yet. Until it is, sensitive things are not saved.",
                say=i18n.t("private_no_vault", lang, n=priv) if priv else i18n.t("vault_setup", lang),
                run=run,
                snoozable=True,
            )
        if priv and vault.age_bin():
            todo = len(vault.unencrypted_private(lib))
            if todo:
                return step(
                    "private",
                    "Encrypt %d private note(s) into the vault." % todo,
                    "The user chose to keep sensitive notes in the encrypted vault.",
                    run=["brainlib vault add --all-private"],
                    say=i18n.t("private_encrypted", lang, n=todo),
                    snoozable=True,
                )

    # 4. Suggested changes waiting for a decision.
    open_ps = proposals.list_proposals(lib, states=("open",))
    auto = [p for p in open_ps if p.get("approval") == "auto"]
    if auto:
        return step(
            "auto-apply",
            "Apply %d low-risk change(s) the user already allowed." % len(auto),
            "The user's edit setting lets these go in without asking.",
            run=["brainlib apply --auto"],
        )
    owner = [p for p in open_ps if p.get("approval") == "owner"]
    if owner and review_due(lib, settings, len(owner)) and "review" not in snoozed:
        return step(
            "review",
            "Go through %d suggested change(s) with the user." % len(owner),
            "Changes to the user's notes need their yes, and it is review time.",
            run=["brainlib review"],
            say=i18n.t("review", lang, n=len(owner)),
            extra=(
                "For each one: show it, ask yes / no / later. Then run one of:\n"
                "  brainlib apply <ID> --as %s --user-said \"<their words>\"\n"
                "  brainlib reject <ID> --as %s\n"
                "  brainlib defer <ID>\n"
                "If the user says not now: brainlib next --snooze review" % (lib.owner, lib.owner)
            ),
            snoozable=True,
        )

    # 5. Inbox backlog.
    pending = [i for i in inbox.all_items(lib) if i["status"] == "pending"]
    if pending and settings.get("edit_mode") != "inbox_only":
        return step(
            "classify",
            "Sort %d inbox item(s) into suggested changes." % len(pending),
            "Things you wrote down are waiting; sorting them only creates suggestions, it changes no notes.",
            run=["brainlib classify"],
        )

    # 6. Earlier answers due for a check, or contradicted by what the user said.
    q, reason = onboard.next_question(lib)
    if q and "revisit" not in snoozed:
        return step(
            "revisit",
            "Check onboarding answer %s with the user again." % q["id"],
            "Preferences change over time: %s." % reason,
            extra=onboard.render_question(q, lang=lang, reason=reason),
            run=["If the user would rather not now: brainlib next --snooze revisit"],
            snoozable=True,
        )

    # 7. Tidy-up suggestions.
    issues = sum(
        len(reports.get(k) or [])
        for k in ("broken_links", "stale", "conflicts", "frontmatter_errors", "invalid_values", "future_dates", "not_utf8")
    )
    if issues and "health" not in snoozed:
        return step(
            "health",
            "Look at %d tidy-up issue(s) in the notes." % issues,
            "Broken links, outdated pages or conflicting notes make answers worse over time.",
            run=["brainlib health"],
            extra="Explain the issues to the user in plain words and offer to fix them via `brainlib propose`. If not now: brainlib next --snooze health",
            snoozable=True,
        )

    journal = next((z["path"] for z in lib.config.get("zones") or [] if z.get("stream") and z.get("path")), None)
    waiting = (
        " %d suggested change(s) wait for the user's next review, as often as the user chose (onboarding Q8)." % len(owner)
        if owner else ""
    )
    return step(
        "all-clear",
        "Nothing needs doing now.%s Help the user with whatever they ask." % waiting,
        "The library is up to date.",
        extra=(
            "Once per conversation, before your first answer: run brainlib index and read every core page (L0) it lists "
            "with brainlib read <path>. They tell you who the user is and how to work with them.\n"
            "Before answering anything about the user, run: brainlib find \"<topic>\" and read the top notes with brainlib read <path>.\n"
            "When the user tells you something worth remembering, run: brainlib note \"<their exact words>\" --said\n"
            "If it is about the user themself (a preference, habit or value), add --target me.md.\n"
            + (
                "If it is something that happened or is planned (a trip, an event, how the day went), add --target %s%s.md.\n"
                % (journal.rstrip("/") + "/", today().isoformat())
                if journal else ""
            )
            + "Record your own conclusions only as --inferred, and outside material only as --external <source>.\n"
            "Never edit note files directly, never open the vault, never store passwords."
        ),
    )


def render(s):
    lines = ["NEXT: %s" % s["next"], "WHY: %s" % s["why"]]
    for r in s["run"]:
        lines.append("RUN: %s" % r)
    if s.get("say"):
        lines.append("SAY TO USER: %s" % s["say"])
    if s.get("extra"):
        lines.append(s["extra"])
    lines.append("THEN: run `brainlib next` again.")
    return "\n".join(lines)
