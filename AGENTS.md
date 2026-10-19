# brainlib：给 AI 助手的说明（先读这一页）

English version: [AGENTS.en.md](AGENTS.en.md)

你拿到的是 brainlib。它把用户的笔记变成一个“大脑库”：普通的 Markdown 文件夹，任何 AI
助手都能安全地读、记、整理。你的工作是帮用户装好、问清楚他想怎么用，之后日常帮他记录和整理。
用户不需要懂 Python，也不需要懂命令行：命令都由你来运行，用户只需要回答选择题、点确认。

## 第 0 步：先检查你自己

1. 你能运行终端命令并看到输出吗？试着运行 `python3 --version`（Windows 上运行 `py -3 --version`）。
   如果你根本没法运行命令，停下来，原样告诉用户：
   “我没法在你的电脑上运行命令，所以装不了也管不了大脑库。请换一个能运行终端命令的 AI 助手
   （例如 Cursor、Claude Code、Codex、Trae），再让它读这个文件。”
2. 能运行命令的话，装好后先做自测：运行 `brainlib agent-check`，照它的 4 道题做完，
   最后运行 `brainlib agent-check finish --model "你的模型名"`。
3. 自测没通过，`brainlib next` 会给你一段话，原样转告用户，不要隐瞒。
4. 即使通过了，如果你是小模型或快速模型（名字里有 mini、flash、lite、haiku、nano、7B、8B 之类的单独一个词，Gemini 里的 mini 不算），
   也要告诉用户：复杂的整理你可能做错，所以每一处改动都会先请他确认。

## 第 1 步：让 brainlib 能运行

brainlib 只需要电脑上有 **Python 3.9 或更新版本**。不用 pip，不用虚拟环境，不用装任何依赖。

**检查 Python：** macOS 和 Linux 运行 `python3 --version`；Windows 运行 `py -3 --version`，不行再试 `python --version`。

**没有 Python 时**，先用一句话告诉用户为什么要装（“brainlib 需要一个叫 Python 的免费基础软件”），
征得同意后，按系统安装：

| 系统 | 安装方法 |
|---|---|
| macOS | 运行 `xcode-select --install`，请用户在弹出的窗口里点“安装”（里面带 python3）。已有 Homebrew 时也可以 `brew install python`。 |
| Windows | 运行 `winget install -e --id Python.Python.3.12`；没有 winget，就请用户打开“Microsoft Store”搜索 Python 3.12 安装。装完要新开一个终端。 |
| Linux | Debian/Ubuntu 运行 `sudo apt install python3`；Fedora 运行 `sudo dnf install python3`。 |

**还没有这个仓库时**（比如用户只给了你网址）：有 git 就运行
`git clone https://github.com/mingweima/brainlib.git`；没有 git，就下载
`https://github.com/mingweima/brainlib/archive/refs/heads/main.zip` 并解压。
GitHub 打不开时，请用户换个网络，或者请别人把压缩包发给他。
仓库放在用户的主目录下（比如 `~/brainlib`），不要放进笔记文件夹里。

**怎么运行：** 在仓库文件夹里：

- macOS / Linux：`python3 brainlib.py <命令>`
- Windows：`py -3 brainlib.py <命令>`，或者 `brainlib.cmd <命令>`

本文写的 `brainlib <命令>` 都是这个意思。brainlib 自己输出的 `RUN:` 行已经换成了这台电脑上的完整写法，照抄运行即可。

## 第 2 步：之后只做一件事

反复运行 `brainlib next`，照它的输出做。输出格式是固定的：

- `NEXT:` 要做什么
- `WHY:` 为什么
- `RUN:` 要运行的命令（原样运行；可能有好几行，按说明选一行）
- `SAY TO USER:` 要对用户说的话（用用户选的语言说，可以原样念）
- `THEN:` 做完后再运行 `brainlib next`

一次只运行一条 brainlib 命令，等它结束、看完输出再运行下一条。同时运行好几条时，后面那条看到的可能还是旧状态。

`brainlib next` 会依次带你走完：自测 → 请用户选语言 → 检查电脑、定库放在哪里 → 开权限 →
10 道了解用户的选择题 → 接上用户常用的 AI 工具 → 日常的记录和整理。一次只问用户一个问题，不要替用户回答。
接上工具以后，用户每次新开对话，那个 AI 都会先运行 `brainlib next`，所以库一直有人读、有人记。
用户选语言之前，brainlib 给你的话是中英两句，用用户和你说话的那种语言说。

## 六条铁律

1. **不直接改笔记。** 不要自己编辑、移动、删除笔记文件。学到的东西用 `brainlib note` 记进收件箱；
   改笔记走提案，先把这条修改拿给用户看，他点头后才生效。
2. **分清是谁说的。** 用户原话用 `--said`，用户明确表达的看法用 `--judgment`，摘自用户自己写的东西用
   `--extracted 文件`，你的推断用 `--inferred`，你的猜测用 `--guess`，外部资料用 `--external 来源`。
   你的推断和猜测永远不能写成用户的观点。
3. **不碰私密内容。** 不打开 `vault/` 和标为 private 的笔记，不问、不记保险箱口令。
   密码、密钥一律不存，最多记一句“在哪里能找到”。
4. **不外发。** 用户没有明确要求，不把库里的任何内容发到网上或别的服务。
5. **偏好会变。** 用户说的话和他之前的选择对不上时，运行
   `brainlib onboard signal <题号> "用户原话"`；用户明确要改，直接 `brainlib onboard answer <题号> <新选项>`。
6. **拿不准就问。** 运行 `brainlib next`，或者出一道选择题问用户。

## 出错时

每个错误都会打印两行：`ERROR:`（出了什么事）和 `FIX:`（怎么办），照 `FIX:` 做。退出码：
0 正常，1 发现了问题，2 用法不对，3 隐私拦截，4 需要用户同意，5 冲突（笔记已经变了）。
同一个错误换两种办法都不行，就停下来，把 `ERROR:` 那一行告诉用户。

## 更多

- 每项任务的详细步骤在 `skills/` 下：`brainlib-setup`（安装和权限）、`brainlib-onboarding`（10 道题）、
  `brainlib-capture`（记录）、`brainlib-organize`（整理和审批）、`brainlib-privacy`（隐私和保险箱）、
  `brainlib-maintain`（体检和查找）。照 `brainlib next` 做时一般用不到它们，遇到细节问题再看；`next` 或 `doctor` 指到哪个文件，就去读那个文件。
- 用 MCP 接入（例如 Claude Desktop）：见 [docs/mcp.md](docs/mcp.md)。
- 笔记格式、来源标记等规格：见 `spec/`。
