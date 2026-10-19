---
name: brainlib-setup
description: 第一次在一台电脑上安装和设置 brainlib：检查 Python、做自测、选语言、定库的位置、开系统权限和工具权限、把用户的 AI 工具接上大脑库。用户说“帮我装大脑库”“设置 brainlib”，或换了电脑、换了 AI 助手时使用。
---

# 安装和设置 brainlib

## 步骤

1. 读仓库根目录的 `AGENTS.md` 第 0 步和第 1 步：确认你能运行命令，确认电脑上有 Python 3.9 或更新版本。
2. 运行 `brainlib agent-check`，做完 4 道题，再运行 `brainlib agent-check finish --model "你的模型名"`。
3. 运行 `brainlib next`。它会让你请用户选语言；用户选好后运行 `brainlib lang zh` 或 `brainlib lang en`。
4. 运行 `brainlib doctor`，看这台电脑的情况和建议的库位置。
5. 用 `brainlib next` 给的原话，出选择题问用户库放哪里：
   - a）新建：`brainlib init "<建议的路径>"`
   - b）已有笔记：`brainlib adopt "<用户的笔记文件夹>"`。adopt 绝不改用户的笔记，只在那个文件夹里加一个 `.brainlib/config.json`。
   - c）同步盘：在同步盘里新建一个空文件夹，再 `brainlib init "<那个文件夹>"`。提醒用户：同步服务商能看到明文，私密内容要放进保险箱。
6. 开权限（见下面“开权限”），都做完后运行 `brainlib next --done permissions`。
7. 继续运行 `brainlib next`，进入 10 道选择题（见 `skills/brainlib-onboarding/SKILL.md`）。
8. 选择题做完，`brainlib next` 会让你接上用户的 AI 工具（见下面“接上用户的 AI 工具”），都接好后运行 `brainlib next --done connect`。

## 库放在哪里

| 用户的情况 | 建议 |
|---|---|
| 只在这台电脑上用 | 主目录下的新文件夹，例如 macOS/Linux 的 `~/brain`、Windows 的 `%USERPROFILE%\brain`（即“用户”文件夹下你自己名字的那个文件夹里）。最私密，也最少权限弹窗。 |
| 已经用 Obsidian、Logseq 或别的文件夹记笔记 | 直接 `adopt` 那个文件夹。 |
| 想在手机或多台电脑上用 | 放进 iCloud、OneDrive、坚果云等同步盘。私密笔记放保险箱，加密后再同步。 |

不要把库放进 brainlib 程序自己的文件夹里。路径照用户说的写，带空格的路径要加引号。

## 开权限

### 系统权限

- **macOS：** 库在“文稿”“桌面”“下载”或 iCloud 里时，系统可能拦截。命令报 `Operation not permitted` 时，请用户打开“系统设置 → 隐私与安全性 → 文件和文件夹”（不行就“完全磁盘访问权限”），给运行你的程序（终端、Cursor、Claude 等）打开开关。放在 `~/brain` 一般不用开。
- **Windows：** “文档”“桌面”常被 OneDrive 同步；“受控文件夹访问”可能拦住写入。写不进去时，请用户打开“Windows 安全中心 → 病毒和威胁防护 → 勒索软件防护 → 允许应用通过受控文件夹访问”。最省事的是用 `%USERPROFILE%\brain`。中文显示成乱码时，改用 `brainlib.cmd` 运行。
- **Linux：** 运行 `ls -ld "<库文件夹>"`，确认用户自己有读写权限。

### 你自己的工具权限

目标：你能运行 brainlib 命令，但工具层面就读不到 `vault/` 和 `private/`，也不能直接改笔记。
按你所在的工具，从 `templates/agent-permissions/` 选模板：

- Claude Code：把 `claude-code.settings.json` 的内容合并进库文件夹的 `.claude/settings.json`。
- Cursor：把 `cursorignore.txt` 的内容追加到库文件夹的 `.cursorignore`。Cursor 常常不让 AI 改这个文件，被拦了就别换办法写（终端命令也不行），把这几行给用户看，请他自己加。
- 其他工具：照 `templates/agent-permissions/README.md` 里的通用做法。

改设置前先问用户，改完告诉用户改了哪个文件。

## 接上用户的 AI 工具

不接的话，用户下次新开一个对话，AI 根本不知道有大脑库，也就不会先读、不会记。接法是在每个工具的“全局说明”里加几行字，让它每次开始新任务前先运行 `brainlib next`。

1. 运行 `brainlib connect`。它列出这台电脑上找到的工具、哪些已经接好，最后是要加的那几行字。
2. 问用户平常用哪几个 AI 工具，把要加的字给用户看，用户同意了再加。
3. 能直接写文件的工具（Claude Code、Codex、Gemini CLI、Windsurf），运行 `brainlib connect --tool <工具> --write`。它只在两行标记之间写，原有内容不动，旧文件先备份。
4. 规则只能在设置界面里改的工具（Cursor、Trae，以及别的工具），运行 `brainlib connect --tool <工具>`，把它打出的文字交给用户，告诉用户粘贴到哪里。
5. 用户以后不想要了，运行 `brainlib connect --tool <工具> --remove`；设置界面里的，请用户自己删掉那几行。

只加大脑库这几行，不要顺手改工具的其他设置。

这一步和上面「你自己的工具权限」是两件事。权限模板（比如库文件夹里的 `.cursorignore`）让工具读不到私密文件夹；
这里加的几行让工具每次新开对话先运行 `brainlib next`。两样都要做。

### 保险箱（用户第 7 题选了 b 时）

接完工具以后，`brainlib next` 会提醒这一步。

1. 需要先装 age。`brainlib doctor` 会给出这台电脑的安装命令。
2. 请用户自己在终端运行 `brainlib vault init`，设一个口令。
3. 告诉用户：口令要自己记好，忘了谁都打不开；不要告诉任何 AI，包括我。
4. 用户说以后再弄，就运行 `brainlib next --snooze private`。保险箱设好之前，敏感的事不会被记下。

## 不要做的事

- 不要替用户决定库放在哪里。
- 不要没问用户就改系统设置或别的程序的设置。
- 不要让用户把口令、密码发给你。
