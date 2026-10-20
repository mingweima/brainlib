# 给 AI 工具设权限 / Agent tool permissions

brainlib 自己会拦住私密笔记、密码和未经同意的改动。工具层面再设一道权限，就算 AI 一时糊涂，也读不到不该读的东西。

brainlib already refuses private notes, secrets and unapproved changes. A second fence in
the AI tool itself means a confused agent still cannot reach what it should not.

## 目标 / Goals

1. 允许运行 brainlib 命令。Allow running brainlib commands.
2. 禁止读取 `vault/` 和 `private/`。Block reading `vault/` and `private/`.
3. 禁止直接编辑笔记（改动走 brainlib 的提案）。Block editing notes directly (changes go through brainlib proposals).

## 各工具 / Per tool

| 工具 Tool | 做法 What to do |
|---|---|
| Claude Code | 把 `claude-code.settings.json` 合并进库文件夹的 `.claude/settings.json`，把里面的 `/ABSOLUTE/PATH/TO/brainlib` 换成 brainlib 程序文件夹的实际路径。允许规则要和命令的开头一字不差：brainlib 输出的 `RUN:` 行开头是什么（包括引号和 Python 的写法），规则里就写什么。这个文件只在用 Claude Code 打开库文件夹时生效；在别的文件夹里也要用，就把这几条放进用户目录的 `~/.claude/settings.json`。Merge into `.claude/settings.json` in the library folder and replace the placeholder path. An allow rule must match the start of the command exactly, so copy it from the start of a `RUN:` line brainlib prints, quotes and Python name included. This file only applies when Claude Code opens the library folder; to use brainlib from other folders too, put the lines in `~/.claude/settings.json`. |
| Cursor | 把 `cursorignore.txt` 的内容追加到库文件夹的 `.cursorignore`。Append to `.cursorignore` in the library folder. |
| 其他 Others | 照上面三条目标，在工具的权限或沙盒设置里配置；做不到的部分，由 brainlib 自身的检查和 AGENTS.md 的规则兜底。Configure the three goals in the tool's permission or sandbox settings; whatever it cannot express is still covered by brainlib's own checks and the AGENTS.md rules. |

各工具的设置格式会随版本变化，改之前请对照该工具当前的文档。改设置前先问用户。
工具不让你改它的权限文件时，不要换一条命令绕过去，把要加的几行给用户看，请用户自己加。

Tool settings formats change between versions; check the tool's current documentation, and ask the user before changing anything.
If the tool will not let you change its permission files, do not get around it with another command; show the user the lines and ask them to add them.
