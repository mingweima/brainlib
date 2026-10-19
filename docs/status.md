# v0.1.1 现状 / Status

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

### v0.1.1（2026-10-20）

- AI 一次并行发出好几条命令时，开场选择题的答案以前可能丢失。现在命令会排队执行，答案和记录都不会互相覆盖。
  Commands an agent starts in parallel now wait for each other, so onboarding answers and notes are no longer lost.
- 分类和查找跳过 the、in、这个、什么 这类虚词。以前「I only drink tea in the morning」会因为一个 in 被分进库的首页。
  Classify and find ignore function words, so a note no longer lands on the index page because of a word like "in".
- 给 AI 的说明里加了两句，一是一次只运行一条命令，二是用户自己的偏好、习惯和价值观记录时加 `--target me.md`。
  The agent instructions now say to run one command at a time and to add `--target me.md` for the user's own preferences.

### v0.1.0（2026-10-20）

- 第一版。First release.
