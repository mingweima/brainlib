# v0.1.3 现状 / Status

## 能用的 / Works

- 命令行工具包括 `next`、`agent-check`、`lang`、`doctor`、`connect`、`init`、`adopt`、`scan`、`index`、`find`、`read`、`health`、
  `note`、`inbox`、`classify`、`propose`、`review`、`apply`、`reject`、`defer`、`undo`、`onboard`、`privacy scan`、
  `hooks install`、`vault`、`mcp`、`selftest`、`help`。
- 能接上用户的 AI 工具。在 Claude Code、Codex、Gemini CLI、Windsurf 的全局说明文件里加几行（有标记，可撤回，先备份）；
  Cursor、Trae 等只能在设置里改的，给出文字请用户粘贴。这样每个新对话都会先运行 `brainlib next`。
- 10 道开场选择题，带复查日期、信号和历史；答案决定权限、记录范围、隐私处理、审阅节奏和提问方式。
- 来源六级标记；按用户设置拦截不该记的类型。
- 刚记下、还没整理进笔记的内容，`find` 和 `index` 马上就能查到，带着来源标记；私密的不出现。
- 提案、审批、收据、备份和撤销；L0/L1 永远要用户同意；`--user-said` 只收用户对这条修改的回答，照抄要记的原话会被拒绝；保留 CRLF 换行。
- 隐私方面，私密笔记不出现在任何输出里；拒存密码、密钥、银行卡号、身份证号；age 保险箱；发布扫描和放行清单；git 钩子。
- AI 同时发出好几条 brainlib 命令时，它们会排队执行，不会互相覆盖记录。
- MCP 服务器（stdio）。
- Python 3.9 及以上；零依赖。按 macOS、Windows、Linux 三个系统写的，目前只在 macOS 上实测过。

## 还没有的 / Not yet

- Windows 和 Linux 上的实测，以及在三个系统上自动跑测试。
- 隐私的硬的一层，比如钥匙要本人在场才能用、出口门禁、保险箱文件名加密，见 [roadmap.md](roadmap.md)。v0.1 的保险箱靠口令，是可选的。
- 语义搜索（v0.1 是关键词和中文双字匹配）。
- 规则分类只看字词重合，归类比较粗，没把握时放进 `inbox-unsorted.md` 等用户整理。AI 记录时用 `--target` 指明该放哪篇，会准得多。
- 通过提案移动或删除文件。
- 从 Notion、Apple 备忘录、ChatGPT 记忆等直接导入。
- 多助手的角色分工与裁剪。档位 4 目前只多了 MCP 和自定义检查，接上的每个助手都能看到整个库，私密部分除外。
- 「先猜再问」和猜中率统计这类更深的校准（档位 3 目前只有保险箱）。
- 各工具全局说明文件的位置按 2026 年的常见版本写，工具改版后可能要更新。
- 技能说明目前以中文为主，英文版只有 `AGENTS.en.md` 和 `README.en.md`。

## 更新记录 / Changes

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
