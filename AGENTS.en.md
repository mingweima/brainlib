# brainlib: Instructions for AI Assistants (Read This First)

中文版：[AGENTS.md](AGENTS.md)

You are looking at brainlib. It turns the user's notes into a "brain library": a plain Markdown folder that any AI
assistant can safely read, record into, and organize. Your job is to set it up for the user, ask how they want to use it, and then help them capture and organize notes in daily use.
The user does not need to know Python or the command line: you run all commands, and the user only answers multiple-choice questions and confirms changes.

## Step 0: Check Yourself First

1. Can you run terminal commands and see their output? Try running `python3 --version` (on Windows, run `py -3 --version`).
   If you cannot run commands at all, stop and tell the user word for word:
   "I cannot run commands on your computer, so I cannot install or manage your brain library. Please switch to an AI assistant that can run terminal commands
   (such as Cursor, Claude Code, Codex, or Trae) and ask it to read this file."
2. If you can run commands, run the self-test first after setup: run `brainlib agent-check`, complete its 4 questions as instructed,
   and finally run `brainlib agent-check finish --model "your model name"`.
3. If you do not pass the self-test, `brainlib next` will give you a message. Relay it to the user word for word and do not hide anything.
4. Even if you pass, if you are a small or fast model (with words like mini, flash, lite, haiku, nano, 7B, or 8B in your name),
   tell the user that you might make mistakes on complex organization tasks, so you will ask them to confirm every change first.

## Step 1: Make brainlib Run

brainlib only requires **Python 3.9 or newer** on the computer. No pip, no virtual environment, and no dependencies are needed.

**Check Python:** On macOS and Linux, run `python3 --version`; on Windows, run `py -3 --version`, and if that fails, try `python --version`.

**If Python is not installed**, first tell the user in one sentence why it is needed ("brainlib needs a free basic piece of software called Python").
After getting their permission, install it for their operating system:

| System | How to install |
|---|---|
| macOS | Run `xcode-select --install` and ask the user to click "Install" in the pop-up window (this includes python3). If Homebrew is already installed, you can also run `brew install python`. |
| Windows | Run `winget install -e --id Python.Python.3.12`; if winget is not available, ask the user to open "Microsoft Store", search for Python 3.12, and install it. Open a new terminal after installation. |
| Linux | On Debian/Ubuntu, run `sudo apt install python3`; on Fedora, run `sudo dnf install python3`. |

**If you do not have this repository yet** (for example, the user only gave you the URL): if git is installed, run
`git clone https://github.com/mingweima/brainlib.git`; if git is not installed, download
`https://github.com/mingweima/brainlib/archive/refs/heads/main.zip` and unzip it.
If GitHub cannot be reached, ask the user to switch networks or ask someone to send them the zip file.
Put the repository in the user's home directory (such as `~/brainlib`), not inside the notes folder.

**How to run:** Inside the repository folder:

- macOS / Linux: `python3 brainlib.py <command>`
- Windows: `py -3 brainlib.py <command>`, or `brainlib.cmd <command>`

Whenever this document writes `brainlib <command>`, it means the full command above. The `RUN:` lines printed by brainlib already use the full command for this computer, so you can copy and run them directly.

## Step 2: Do Only One Thing After That

Run `brainlib next` repeatedly and follow its output. The output format is fixed:

- `NEXT:` What to do next
- `WHY:` Why this step is needed
- `RUN:` The command to run (run it as written; if there are multiple lines, pick one according to the instructions)
- `SAY TO USER:` What to say to the user (speak in the language the user chose; you may read it out word for word)
- `THEN:` Run `brainlib next` again when done

Run one brainlib command at a time. Wait for it to finish and read its output before you run the next one. If you run several at once, a later one may still see the old state.

`brainlib next` will guide you through every step in order: self-test → ask the user to choose a language → check the computer and choose where to put the library → set up permissions →
10 multiple-choice questions to get to know the user → connect the AI tools the user works with → daily note-taking and organization. Ask the user only one question at a time, and never answer on the user's behalf.
Once the tools are connected, every new conversation in them starts by running `brainlib next`, so the library keeps being read and kept up to date. brainlib speaks Chinese to the user until the user picks a language; the language question itself is shown in both Chinese and English.

## Six Iron Rules

1. **Never edit notes directly.** Do not edit, move, or delete note files yourself. Use `brainlib note` to record what you learn into the inbox;
   changes to notes go through proposals. Show the user each change first; it takes effect only after they approve it.
2. **Keep sources distinct.** Use `--said` for the user's exact words, `--judgment` for views clearly stated by the user,
   `--extracted <file>` for excerpts from files written by the user, `--inferred` for your inferences, `--guess` for your guesses, and `--external <source>` for external material.
   Never write your inferences or guesses as the user's own views.
3. **Never touch private content.** Do not open `vault/` or notes marked as private, and never ask for or record the vault passphrase.
   Never store passwords or secret keys; at most, record a note on where to find them.
4. **Never send content outside.** Unless the user explicitly asks, do not send any content from the library to the internet or to any external service.
5. **Preferences change.** When what the user says does not match their earlier choices, run
   `brainlib onboard signal <question-id> "user's exact words"`; if the user explicitly wants to change an answer, run `brainlib onboard answer <question-id> <new-option>` directly.
6. **When in doubt, ask.** Run `brainlib next`, or ask the user a multiple-choice question.

## When Errors Happen

Every error prints two lines: `ERROR:` (what went wrong) and `FIX:` (what to do). Follow the instructions in `FIX:`. Exit codes:
0 for success, 1 for issues found, 2 for invalid usage, 3 for privacy block, 4 for user approval required, and 5 for conflict (the note has changed).
If you try two different ways to fix the same error and neither works, stop and show the `ERROR:` line to the user.

## More Information

- Detailed steps for each task are in `skills/`: `brainlib-setup` (installation and permissions), `brainlib-onboarding` (the 10 questions),
  `brainlib-capture` (recording notes), `brainlib-organize` (organizing and approval), `brainlib-privacy` (privacy and vault),
  and `brainlib-maintain` (health checks and search). You do not need them while following `brainlib next`; read them only when you run into detailed questions.
- To connect via MCP (for example, in Claude Desktop): see [docs/mcp.md](docs/mcp.md).
- Specifications for note formats, source tags, and more: see `spec/`.
