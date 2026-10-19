# brainlib

**Your own AI brain library. One copy shared by every AI assistant you use, and it knows you better the longer you use it.**

[中文](README.md)

You probably use several AIs at once. One writes, one looks things up, one codes. They are all very capable, yet none of them really knows you.

Every time you switch tools or open a new chat, you have to explain all the context again from scratch. Even when an AI remembers a little, that memory lives on the provider's servers, and you can't take it with you when you switch.
Over time the context grows too big for the AI to handle, and its memory gets muddled or it starts making things up.

What brainlib does is simple. It keeps what your AIs learn about you, as they learn it, in a folder on your own computer. We call it your brain library. Whichever AI you use, it reads the brain library first,
the way a new colleague reads the handover notes on day one. Once it has read them, it knows who you are and how to work with you.

After each conversation, the AI writes what it learned into the brain library. The longer you use it, the better it knows you. Switch models or switch tools, and everything in the brain library is still yours.

We call this goal cyber-immortality. Record your thinking and the way you make decisions completely, so that whatever AI comes next can act the way you would.

**Get started with one sentence.** Tell your AI assistant "Please read AGENTS.md at https://github.com/mingweima/brainlib and set up brainlib for me."
It will ask you a few multiple-choice questions. Answer each with a single letter, and it does the rest.
This needs an AI assistant that can run commands on your computer, such as Cursor, Claude Code, Codex or Trae. AIs on the web or on your phone can't do it yet.

## Why I built brainlib

I'm Mingwei, the developer of brainlib. I use several AI assistants at once, spread across different tools. Some help me look things up and do research, some write code, some organize my notes.
I want every exchange with them to go both ways. I get information and knowledge from the AI, and the AI learns my way of thinking and my experience from me. The longer that builds up, the better they can make judgments the way I would.

So I first built a brain library for myself. Every AI reads it before it starts and writes to it when it's done, keeping what I said apart from what it guessed, and asking me before it changes anything.
I also wanted to be able to hand the whole library to a brand-new AI at any time and have it take over after one read. I've been working this way myself, and brainlib is the part of it that works for anyone, packaged so you can start with one sentence.

## What it looks like in use

**Switch AIs without starting over.** On Monday you mention in Cursor that you don't like exclamation marks in your writing. On Wednesday you ask Claude Code to write an email. It reads the brain library first, and the email has no exclamation marks.

**It keeps your exact words.** You say "I'm going to Chengdu on a business trip next month", and it records that sentence as it is, marked as yours and dated.
Even if it records a guess of its own, such as "probably likes spicy food", that is marked as the assistant's guess and never taken as what you think.

**It asks before changing your notes.** It never edits your notes on its own. Every so often it shows you its suggested tidy-ups, for example "Add 'only drinks tea in the morning' to About me?"
It changes the note only after you say yes, and if something went wrong, just say so and it's undone.

**When you change your mind, it follows.** You once said "remind me to tidy up every day", then said "not now" a few times. It comes back and asks whether once a week would suit you better.
After a few months, it also checks those first multiple-choice answers with you again.

**New model? Just switch.** The brain library is on your own computer, not with any company. A new model reads it once and knows on day one who you are and how you work.

**It stays away from private things.** Say "My bank card PIN is 1234, please remember it", and it refuses and suggests a password manager. brainlib never hands notes in the private folder to the AI, and anything that really matters can go in a vault only you can open. <!-- brainlib:allow -->

**Several AIs, one brain library.** One looks things up, one writes code, one organizes your notes. Whatever any of them learns goes into the same library, so you don't have to pass it along.

## How it differs from typical AI memory

| What you care about | Typical AI memory | brainlib |
|---|---|---|
| If I switch AIs, will it still know me? | Usually not. Each provider keeps its own memory, and switching often means starting over | **One brain library, shared by every AI you connect.** It lives on your own computer, and each connected AI reads it before it starts |
| Does it record what I said, or what it guessed? | Usually it can't tell | **Every entry says where it came from.** Your exact words, your views, the AI's guesses and material from the web are each marked, so you can tell them apart at a glance. Only what you said counts as what you mean |
| Will it change things on its own? | Mostly the AI decides by itself what to remember and change | **It asks before changing anything.** Changes happen only after you agree. The most important pages (such as About me) need your explicit yes every time, and mistakes can be undone |
| What about privacy? | Mostly down to settings and the AI's good behavior | **Privacy has hard rules.** brainlib never hands private notes to the AI. The most sensitive ones can go in a vault that only opens with your passphrase. Passwords, ID numbers and the like are refused outright. What it can't do is spelled out under Privacy below |
| I'm not technical. Can I install it? | Often means installing and configuring a pile of software | **Installed with one sentence.** Send one sentence to an AI assistant that can run commands, and it reads the instructions and installs brainlib itself. Your computer needs Python; if it's missing, the AI asks you first and then helps you install it |
| My AI isn't very smart. Will it work? | Usually no warning | **It tests itself before working.** Before starting, it takes a 4-question quiz graded by the program. If it fails, it tells you first, so you don't waste your time |
| Will my existing notes get messed up? | Often you have to import them into its own format first | **Your notes stay as they are.** Connecting changes not a single character, and by default later changes need your OK. If you stop using it one day, your notes are exactly as they were |
| What if I change my mind? | Rarely checks back with you | **It changes with you.** Every few months it checks again, and when what you do no longer matches what you said before, it asks again |
| Is it too complicated? | Either too simple, or complex from day one | **It starts simple.** By default it only suggests and never edits. Once you're comfortable, unlock more one level at a time, such as recording journal entries directly or adding a vault |
| Does it speak my language? | Similar open-source tools are mostly English-only | **Chinese first, English too.** It asks your language before anything else, then sticks to it |

Other projects have done some of these on their own. brainlib puts them together, has source labels and ask-before-editing switched on from day one, and installs with one sentence.

## Getting started (no Python knowledge needed)

1. Open an AI assistant that can run commands on your computer, such as Cursor, Claude Code, Codex or Trae.
2. Say this to it.

   > Please read AGENTS.md at https://github.com/mingweima/brainlib and set up brainlib for me.

3. Just answer its questions. It first asks which language you prefer, then where to keep the brain library, then 10 multiple-choice questions about you, and finally which AI tools you use, so it can connect them all to the brain library.
   It asks you before it installs anything or changes any tool's settings.
4. After that, just talk normally, for example "Remember that I only drink tea in the morning", "Tidy up this week's notes" or "What was that book I said I wanted to read?"

Before it starts, the assistant takes a 4-question self-test. A small model, or one that fails the test, will tell you up front that it may not do well.

## Common questions

**Does it cost anything?** It's free for personal use. Your AI tools charge their own prices, and brainlib adds nothing.

**I only use ChatGPT, Doubao or Kimi on the web or on my phone. Will it work?** Not yet. brainlib runs commands on your computer, which web and phone AIs can't do.
Assistants that can run commands, such as Cursor, Claude Code, Codex and Trae, all work, and the Claude desktop app can connect over MCP (see [docs/mcp.md](docs/mcp.md)).

**Will my notes be uploaded?** brainlib itself uploads nothing, and the brain library is just a folder on your computer. But whatever the AI reads goes to the company behind its model, as with any AI use.
Put anything you don't want the AI to see in the library's `private` folder, and brainlib won't hand it to the AI. For what really matters, the vault is safest.

**Can I try it without letting it write anything?** Pick "read-only" for question 4. It then only reads your notes and writes nothing. You can change this at any time.

**Can I bring over what ChatGPT already remembers about me?** Not automatically yet. You can copy that text to the AI and have it put it in the inbox, then confirm what's right when you tidy up.

**What if I stop using it?** Your notes are still plain Markdown files that open anywhere and go wherever you go. To make the AI stop using it, ask the AI to remove the lines it added to each tool
(`brainlib connect --tool <tool> --remove`).

## Five levels, from simple to advanced

Each level includes everything in the level before it, and switching levels never requires changing your notes.

| Level | What it can do | Good for |
|---|---|---|
| 0 Read-only | Helps the AI understand your notes. It can search and run health checks, and writes nothing | Trying it out |
| 1 Capture | Adds an inbox, so what the AI learns is kept outside your notes first | Doing your own tidying |
| 2 Organize | Adds suggested edits that apply only after you approve them, with a receipt each time and undo. Low-risk entries such as journals can be recorded automatically | Most people (default) |
| 3 Vault | Adds an encrypted vault for private content that only you can open | People with private content |
| 4 Multi-assistant | Adds MCP and your own checks, for several AIs splitting up the work | Power users |

Your starting level depends on how you answer the questions and which features you turn on, and you can change it at any time.

## Privacy

**What brainlib guarantees.**

- Search, read, the index and the MCP interface never return private notes, not even their titles.
- Anything in a note or an edit that looks like a password, secret key, ID number or bank card number is refused.
- The vault is encrypted with [age](https://github.com/FiloSottile/age), and its key is locked with your passphrase. Only you can type the passphrase, in your own terminal, so the AI can't open it.
- Edit receipts and health reports never copy your notes. They record only which note changed, who approved it, and counts.
- Before you publish or share anything, you can scan it against your own private word list (real names, company, address and so on), and it passes only with zero matches.

**What it can't do, so you know.**

- An AI's own file-reading tools may still be able to read private files that aren't encrypted. brainlib tells it not to and ships permission templates for common tools, but the most reliable protection is the vault.
- File names inside the vault are visible.
- Your sync provider can see notes that aren't encrypted.

## Requirements

- macOS, Windows or Linux. v0.1 has only been tested on macOS so far. If something goes wrong on Windows or Linux, please tell us on GitHub.
- Python 3.9 or newer. If you don't have it, your AI assistant will help you install it. Nothing else to install. No pip, no virtual environment, no dependencies.
- age (for the vault) and git are optional.

## Files

```text
AGENTS.md          Entry point for AI assistants (Chinese; English in AGENTS.en.md)
brainlib.py        Launcher for macOS/Linux; on Windows use brainlib.cmd
brainlib/          The program (Python standard library only)
skills/            Six task guides: setup, onboarding, capture, organize, privacy, maintenance
spec/              Note format, provenance labels, command conventions
docs/              Status, roadmap, threat model, MCP setup
templates/         Permission templates for AI tools
examples/          Two fictional example libraries
tests/             Tests
```

## License

brainlib is released under the [PolyForm Noncommercial License 1.0.0](LICENSE). Individuals can use, modify and share it free of charge for personal use, research, study and hobby projects, and so can charities, schools, public research organizations and government institutions.
**Commercial use is not allowed**, and the licensor keeps all commercial rights. For a commercial license, contact the developer through GitHub (github.com/mingweima/brainlib). This is a summary, and the LICENSE text governs.

Developer Mingwei Ma, Capibara Capital.
