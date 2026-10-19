"""Health: turn scan reports into plain-language issues, plus optional custom checks.

Custom checks (advanced) are commands listed in the config:
    "checks": [{"name": "spelling", "command": ["my-checker", "--quiet"], "timeout": 60}]
Each runs in the library folder; only its exit code and first output line are reported.
"""

import subprocess

from .scan import scan_library

EXPLAIN = {
    "secrets_in_library": ("A password or key seems to be stored in a note.", "Move it to a password manager; leave only a pointer."),
    "secret_level_files": ("Some notes are marked `sensitivity: secret`. Secrets should never be stored.", "Keep only a pointer, for example 'in my password manager'."),
    "private_plaintext": ("Some private notes are stored as readable text.", "If the user chose the vault: `brainlib vault add --all-private`."),
    "broken_links": ("A link points to a note that does not exist.", "Fix the link or create the missing note (via `brainlib propose`)."),
    "stale": ("A page is past its check-again date.", "Ask the user whether it is still true; then propose an update."),
    "conflicts": ("Two main pages in the same folder have the same title.", "Ask the user which one is current; mark the other `authority: archived`."),
    "missing_meta": ("An important page (L0/L1) has no description or read_when.", "Propose adding a one-line description and when to read it."),
    "frontmatter_errors": ("A note's header (front matter) could not be fully read.", "Fix the YAML syntax at the top of the note."),
    "invalid_values": ("A header field has a value brainlib does not know.", "Use the values listed in spec/front-matter.md."),
    "future_dates": ("A note says it was updated in the future.", "Fix the date in the `updated` field."),
}
ORDER = list(EXPLAIN)


def health(lib):
    result = scan_library(lib, write=True)
    reports = result["reports"]
    issues = []
    for key in ORDER:
        val = reports.get(key)
        count = val if isinstance(val, int) else len(val or [])
        if not count:
            continue
        what, fix = EXPLAIN[key]
        items = [] if isinstance(val, int) else val[:20]
        issues.append({"kind": key, "count": count, "what": what, "fix": fix, "items": items})
    custom = run_custom(lib)
    return {"notes": len(result["entries"]), "issues": issues, "custom_checks": custom}


def run_custom(lib):
    out = []
    for c in lib.config.get("checks") or []:
        cmd = c.get("command")
        if not cmd:
            continue
        try:
            p = subprocess.run(
                cmd,
                cwd=str(lib.root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(c.get("timeout") or 60),
            )
            first = (p.stdout or p.stderr or "").strip().splitlines()[:1]
            out.append({"name": c.get("name") or cmd[0], "ok": p.returncode == 0, "first_line": (first[0][:200] if first else "")})
        except (OSError, subprocess.TimeoutExpired) as e:
            out.append({"name": c.get("name") or str(cmd), "ok": False, "first_line": str(e)[:200]})
    return out


def render(h):
    lines = ["Checked %d note(s)." % h["notes"]]
    if not h["issues"] and all(c["ok"] for c in h["custom_checks"]):
        lines.append("No issues found.")
    for i in h["issues"]:
        lines.append("")
        lines.append("%s (%d)" % (i["what"], i["count"]))
        lines.append("  FIX: %s" % i["fix"])
        for it in i["items"]:
            if isinstance(it, dict):
                desc = ", ".join("%s=%s" % (k, v) for k, v in it.items() if v is not None)
            else:
                desc = str(it)
            lines.append("  - %s" % desc)
    for c in h["custom_checks"]:
        lines.append("custom check %s: %s %s" % (c["name"], "ok" if c["ok"] else "FAILED", c["first_line"]))
    return "\n".join(lines)
