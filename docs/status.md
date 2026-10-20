# v0.2.0 现状 / Status

## 能用的 / Works

- 命令行工具包括 `next`、`agent-check`、`lang`、`doctor`、`connect`、`init`、`adopt`、`scan`、`index`、`log`、`find`、`read`、`health`、
  `note`、`inbox`、`classify`、`propose`、`review`、`apply`、`reject`、`defer`、`undo`、`onboard`、`privacy scan`、
  `hooks install`、`vault`、`mcp`、`selftest`、`help`。
- 能接上用户的 AI 工具。在 Claude Code、Codex、Gemini CLI、Windsurf 的全局说明文件里加几行（有标记，可撤回，先备份）；
  Cursor、Trae 等只能在设置里改的，给出文字请用户粘贴。这样每个新对话都会先运行 `brainlib next`。
- 10 道开场选择题，带复查日期、信号和历史；答案决定权限、记录范围、隐私处理、审阅节奏和提问方式。
- 来源六级标记；按用户设置拦截不该记的类型。
- 每条记录带说话时间（精确到分钟）、分类、重要性、私密等级，记录也分 L0 到 L3。`index` 长度固定，带条件时能按任一标签排序和筛选；每条记录按说话时间写进当天的日志，`log` 按天看；同一件事以最新的说法为准。见 [records.md](records.md)。
- 刚记下、还没整理进笔记的内容，`find` 和 `index` 马上就能查到，带着来源标记；私密的不出现。
- 提案、审批、收据、备份和撤销；L0/L1 永远要用户同意；`--user-said` 只收用户对这条修改的回答，照抄要记的原话会被拒绝；保留 CRLF 换行。
- 隐私方面，私密笔记不出现在任何输出里；拒存密码、密钥、银行卡号、身份证号，笔记里原有的这类内容拿给 AI 时遮住；age 保险箱；发布扫描和放行清单；git 钩子。
- AI 同时发出好几条 brainlib 命令时，它们会排队执行，不会互相覆盖记录。
- MCP 服务器（stdio）。
- Python 3.9 及以上；零依赖。GitHub 上每次提交都会在 macOS、Windows、Linux 上自动跑自检、单元测试和隐私扫描；实际装起来用，macOS 和 Linux 上试过，Windows 上还没有。

## 还没有的 / Not yet

- 在 Windows 上实际装起来用一遍。
- 隐私的硬的一层，比如钥匙要本人在场才能用、出口门禁、保险箱文件名加密，见 [roadmap.md](roadmap.md)。v0.1 的保险箱靠口令，是可选的。
- 语义搜索。现在是关键词匹配，中文按两个字一组，单个汉字按包含匹配，同义词查不到。
- 规则分类只看字词重合，归类比较粗，没把握时放进 `inbox-unsorted.md` 等用户整理。AI 记录时用 `--category` 或 `--target` 指明该放哪里，会准得多。
- 字面不像的矛盾说法认不出来，比如「回复别超过三段」和「越详细越好」，要靠 AI 记录时加 `--replaces`。
- 隐私加强往后放，包括漏加 `--private` 时的补救和更多密钥格式，见 [roadmap.md](roadmap.md)。
- 通过提案移动或删除文件。
- 从 Notion、Apple 备忘录、ChatGPT 记忆等直接导入。
- 多助手的角色分工与裁剪。档位 4 目前只多了 MCP 和自定义检查，接上的每个助手都能看到整个库，私密部分除外。
- 「先猜再问」和猜中率统计这类更深的校准（档位 3 目前只有保险箱）。
- 各工具全局说明文件的位置按 2026 年的常见版本写，工具改版后可能要更新。
- 技能说明目前以中文为主，英文版只有 `AGENTS.en.md` 和 `README.en.md`。

## 更新记录 / Changes

### v0.2.0（2026-10-20）

- 每条记录带四个标签：说话时间（精确到分钟）、分类、重要性、私密等级。`note` 新加 `--category`、`--importance`、`--privacy`，`--said-at` 可以写到分钟，没写的由 brainlib 推断。机密只进保险箱，绝密一律不存。
  Every record carries four tags: when it was said (to the minute), category, importance and privacy level. `note` gains `--category`, `--importance` and `--privacy`, and `--said-at` takes a time; anything left out is inferred. Confidential items only go into the vault; secret ones are never stored.
- 记录像页面一样分 L0 到 L3。`index` 长度固定，依次列核心页、还没整理的重要记录、入口页、最近 7 天的日志、按说话时间排的最近记录、可能过时的说法；带上条件时改为列记录，能按任一标签排序和筛选。
  Records get tiers like pages. `index` has a fixed length: core pages, important records not filed yet, entry pages, the last 7 days of journal, recent records by when they were said, and lines that may be out of date. With filters it lists records, sorted and filtered by any tag.
- 每日日志。整理时每条记录按说话时间插进那一天的 `journal/<日期>.md`，补记的旧话插到它自己那天。新的日记文件头写 `type: Journal`，标题和创建日期都是那一天。新命令 `brainlib log` 按天看记录。
  Daily log. Organising puts every record into the journal of the day it was said, in time order. New journal files get `type: Journal` with that day as title and creation date. The new `brainlib log` shows records by day.
- 同一件事以最新的说法为准。`note --replaces "<旧说法里的几个词>"` 生成替换一行的建议，旧说法留在新行末尾的括号里；用户把老偏好再说一遍时，笔记不重复，只在日志里记下新的时间；`health` 和索引会列出同一篇里字面很像、日期不同的几行。新加的 `propose replace_line` 和 `remove_line` 可以改掉或删掉一行。
  The newest statement counts. `note --replaces "<old words>"` makes a replace-line proposal that keeps the old wording in brackets; restating an old preference adds nothing to the note and logs the new time; `health` and the index list look-alike lines with different dates. The new `propose replace_line` and `remove_line` change or remove one line.
- 整理时每条记录单独一条建议，可以收一部分、拒一部分。分类是「决定」的记录进 `decisions.md`，第一次用到时建。规则分类不再把东西放进入口页（L1），first、第一、不确定这类词不再算主题词。
  Each record now gets its own proposal, so the user can take some and leave others. Decisions go to `decisions.md`, created on first use. The rules classifier no longer files things into entry pages (L1) and ignores words like "first" or 不确定.
- `find` 能搜单个汉字。
  `find` matches single Chinese characters.
- 日常规则加了几条：每行开头是说话时间，新旧冲突时信最新的；改主意时加 `--replaces`；对话快结束时把定下的事和偏好一件一条记下来，闲聊不记。中文用户另有一份说人话的规矩 `skills/brainlib-writing/SKILL.md`，日常规则和库里的 `AGENTS.md` 都指向它。
  The daily rules now say that each line starts with when it was said and the newest one counts, to use `--replaces` for a change of mind, and to note decisions and preferences near the end of a conversation, skipping small talk. Chinese users also get a writing guide, `skills/brainlib-writing/SKILL.md`, which the daily rules and the library's `AGENTS.md` point to.
- MCP 的 `kb_note` 和 `kb_index` 支持新参数，新工具 `kb_log`。
  MCP: `kb_note` and `kb_index` take the new parameters; there is a new `kb_log` tool.
- 几处小修。在 Windows 上同时跑几条 brainlib 命令，偶尔会有一条白等 60 秒再报错，现在不会了；自测没过时 `agent-check finish` 退出码是 1；终端里逐条审阅有中文提示，按 Ctrl-D 不再报错；`connect --remove` 删完以后文件空了就删掉文件（有备份）；开场题结束语写对了每题隔多久再确认；还没选语言时，`agent-check` 的题中英文都出；中文库的日常规则里，敏感话题带中文名；Claude Code 权限模板的允许规则带上了引号，和 `RUN:` 行对得上。
  Small fixes: on Windows, running several brainlib commands at once no longer leaves one of them waiting 60 seconds before it fails; `agent-check finish` exits with 1 when the check fails; interactive review speaks Chinese and no longer crashes on Ctrl-D; `connect --remove` deletes the file when nothing else is left in it (a backup is kept); the onboarding outro gives the right recheck intervals; before a language is chosen, `agent-check` shows its tasks in both languages; in Chinese libraries the daily rules name sensitive topics in Chinese too; the Claude Code permission template's allow rule now has the quotes that `RUN:` lines use.
- 旧库不用迁移，旧的来源标记照样认。
  Existing libraries need no migration; old source labels still read.

### v0.1.5（2026-10-20）

- 用户勾过敏感话题以后，`note` 不再要求每条都说明是否敏感。涉及这些话题的照旧加 `--private`，按第 7 题处理；`--not-sensitive` 仍然认，但用不着了。日常提示照旧列出这些话题。
  Notes no longer have to say whether they are sensitive once the user has marked topics. Anything about those topics still gets `--private` and is handled as the user chose (Q7); `--not-sensitive` is still accepted but no longer needed. The daily hint still lists the topics.
- brainlib 拒存的敏感内容，用户说这一条可以记，AI 就去掉 `--private` 再记一次，并给第 7 题记一条信号。
  When brainlib refuses something sensitive and the user says this one is fine to keep, the agent saves it again without `--private` and records a signal on Q7.
- LICENSE 的版权声明只写开发者个人，公司名留在 README 的署名里。README 加了一条额外许可，个人在自己的工作中用 brainlib 也免费；部署给他人使用、做进产品或者用来提供服务，仍然需要商业授权。
  The LICENSE notice now names only the developer; the company stays in the README credit. The README adds a permission: individuals may also use brainlib free of charge in their own work, while deploying it for others, building it into a product or using it to provide a service still needs a commercial license.
- README 重写。开头换成开发者自己写的介绍，新加一节讲缓存区、修改建议和读笔记怎么转；对比表删了，常见问题补上装完多了什么、会不会多费额度、两台电脑怎么用。
  The README was rewritten. It opens with the developer's own introduction and a new section on how the buffer, suggested changes and reading fit together; the comparison table is gone, and the FAQ now covers what gets installed, whether it costs extra quota, and using two computers.

### v0.1.4（2026-10-20）

- 笔记里原本存着的密码、密钥、银行卡号和身份证号，`read`、索引、`llms.txt` 和 `find` 拿给 AI 时都会遮住。AI 要改这篇笔记，遮住的几行就不动，或者请用户自己改。
  Passwords, keys, card and ID numbers already in notes are hidden whenever `read`, the index, `llms.txt` or `find` shows them to the agent. To change such a note, the agent leaves the hidden lines alone or asks the user to edit them.
- 一次改动把密钥从笔记里删掉时，撤销用的备份里也把它遮住，这篇笔记以前的备份一并遮住。撤销以后密钥不会回来，所以先确认用户已经存进密码管理器。
  When a change removes a secret from a note, the undo backup hides it too, and so do older backups of that note. Undo will not bring it back, so the user should save it in a password manager first.
- 用户在第 6 题勾过敏感话题以后，每条 `note` 都要表态，涉及这些话题的加 `--private`，其他的加 `--not-sensitive`，两个都没加就不存。日常提示会列出这些话题，连同用户自己补充的；第 7 题选了「读或用之前先问我」的，还会提醒先问。
  Once the user has marked sensitive topics (Q6), every `note` must say `--private` (about one of them) or `--not-sensitive`; with neither, nothing is saved. The daily hint lists the topics, including any the user added in their own words, and if the user chose to be asked first (Q7), it says to ask.
- 用户点名记进哪篇时，`note --target <那篇> --now` 当场生成带「用户原话」标记的修改建议，和 `propose` 一样快。用户说的话一律用 `note` 记，`propose` 只用来改正或删掉已有的内容，来源标记就不会丢。brainlib 拒绝保存的敏感内容，提示里写明不能再用 `propose` 写进笔记，要问用户这一条要不要破例；用户说可以记，就改用 `--not-sensitive`，并记一条第 7 题的信号，以后再确认这道题。
  When the user names the note, `note --target <that note> --now` makes the suggested change right away, with the "user said" label, as quickly as `propose` would. What the user says always goes through `note`; `propose` is only for correcting or removing what is already there, so the source label is kept. When brainlib refuses to save something sensitive, it says not to write it into a note with `propose` either and to ask the user about this one; if they say it is fine to keep, the agent uses `--not-sensitive` and records a signal on Q7, so that answer is checked again later.
- 这套记录规则以前只在 `brainlib next` 没事可做时出现，现在设置做完以后每一步都带着。以前库里有一件待办，AI 就看不到它们。
  These recording rules used to appear only when `brainlib next` had nothing else to do; once setup is done, every step now carries them. A single pending task used to hide them.
- `propose` 的内容里如果有目标笔记原来没有的来源标记，比如 `[said …]`，会被拒绝。这类标记只能由 `note` 加上。
  `propose` refuses text with a source label such as `[said …]` that the target note does not already have; only `note` adds those labels.
- 不是 UTF-8 编码的笔记，比如老版本记事本存的文件，brainlib 一律不改，`health` 会列出来，请用户另存一次。以前往里加内容会把整篇写成乱码。
  Notes not saved as UTF-8, such as files from older Notepad versions, are never changed; `health` lists them so the user can save them again. Adding to them used to garble the whole note.
- 根目录的 `me.md` 没写层级时按核心页算。接手已有的笔记文件夹以后，第一次记下的偏好在每次对话开头也会读到。
  A top-level `me.md` without a tier counts as a core page, so the first preference saved in an adopted folder is read at the start of every conversation.
- 电脑上的 `python3` 版本太旧时，`RUN:` 行会换成能跑 brainlib 的那个 Python，`AGENTS.md` 也写了旧版本怎么办。
  When `python3` is too old, the `RUN:` lines name a Python that can run brainlib, and `AGENTS.md` says what to do about an old version.
- `connect` 说明网页版和手机 App 里的 AI 跑不了命令，接不上。工具不让改它自己的权限文件时，AI 不绕过去（终端命令也不行），请用户自己加，`doctor` 的那条待办里也写明了。
  `connect` says that AIs in a web page or phone app cannot run commands, so they cannot be connected. When a tool blocks edits to its own permission files, the agent asks the user to add the lines instead of working around it (shell commands included); the `doctor` item says so too.

### v0.1.3（2026-10-20）

- 用户选语言之前，brainlib 给 AI 的话中英两句都有。以前英文用户听到的第一句是中文。
  Until the user picks a language, the lines brainlib gives the agent to say come in both Chinese and English. English-speaking users used to hear Chinese first.
- 新建的 `me.md` 最后多了一节「最近记下的」，新记的事先放在这里。以前它们会排在「眼下的重点」下面。已经建好的库不变。
  New libraries' `me.md` ends with a "Recently noted" section, where new lines land; they used to end up under "Current priorities". Existing libraries are unchanged.

### v0.1.2（2026-10-20）

- 自测判断小模型改成按整个词看。以前 Gemini 因为名字里含 mini，会被当成小模型，AI 会对用户说自己是小模型。
  The self-check now judges small models by whole words, so "Gemini" no longer counts as "mini".
- 用户选了每周或每月看一次整理建议时，`classify` 不再叫 AI 马上拿给用户看，和 `brainlib next` 的说法一致了。
  When the user chose weekly or monthly reviews, `classify` no longer tells the agent to review right away, matching `brainlib next`.
- 日常提示教 AI 把发生过或计划中的事记进当天的日记。用户在第 4 题允许日记直接记时，这类记录会直接写进去。
  The daily hints tell agents to put events and plans in today's journal, so the user's choice to let journal entries go in directly takes effect.
- `brainlib doctor` 写明每个工具的权限该改哪个文件、用哪份模板，路径都是完整路径。
  `brainlib doctor` now names the exact file and template for each tool's permissions, with full paths.

### v0.1.1（2026-10-20）

- AI 一次并行发出好几条命令时，开场选择题的答案以前可能丢失。现在命令会排队执行，答案和记录都不会互相覆盖。
  Commands an agent starts in parallel now wait for each other, so onboarding answers and notes are no longer lost.
- 分类和查找跳过 the、in、这个、什么 这类虚词。以前「I only drink tea in the morning」会因为一个 in 被分进库的首页。
  Classify and find ignore function words, so a note no longer lands on the index page because of a word like "in".
- 给 AI 的说明里加了两句，一是一次只运行一条命令，二是用户自己的偏好、习惯和价值观记录时加 `--target me.md`。
  The agent instructions now say to run one command at a time and to add `--target me.md` for the user's own preferences.

### v0.1.0（2026-10-20）

- 第一版。First release.
