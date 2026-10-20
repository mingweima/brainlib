---
name: brainlib-organize
description: 把收件箱整理成修改建议，和用户一起审批，然后应用、拒绝或留到以后；也包括撤销和自己提建议。brainlib next 提示 classify、review 或 auto-apply 时使用。
---

# 整理和审批

## 流程

1. `brainlib classify`：把收件箱变成修改建议。这一步不改任何笔记。每条记录单独一条建议；另外每天一条日志建议，
   把当天记下的事按说话时间排进 `journal/<日期>.md`。笔记里已经有的话不会重复加，只在日志里记下这次的时间。
2. `brainlib review`：列出等用户决定的建议。什么时候拿给用户看，按用户第 8 题的节奏，`brainlib next` 会提醒你。
3. 一条一条给用户看：改哪篇、为什么、要加的文字是什么。替换一行的建议会同时列出旧行和新行。问用户：可以 / 不要 / 以后再说。
   理由里写着「looks similar」的，是笔记里有一句字面很像的旧话。问用户新说法是不是取代了旧的；是的话，按下面的办法再提一条删掉旧行。
4. 按用户的回答运行：
   - 可以：`brainlib apply <ID> --as human:me --user-said "用户的原话，比如：好的，加上吧"`
   - 不要：`brainlib reject <ID> --as human:me`
   - 以后再说：`brainlib defer <ID>`
5. 用户反悔了：`brainlib undo <ID> --as human:me`。只要那篇笔记之后没再变过，就能恢复原样。

## 铁律

- 只有用户真的说了同意，才能写 `--as human:me`，并把用户的原话写进 `--user-said`。
- `--user-said` 写的是用户看过这条修改之后的回答，比如「可以」。用户当初说的「帮我记一下……」不算同意这条修改，要先拿给他看。两者一样时程序会拒绝（退出码 4）。
- 最重要的页（L0，比如 `me.md`）和入口页（L1，比如 `README.md`）每次都要用户亲口同意。
- 外部资料不能直接进 L0 和 L1 页。
- 私密笔记和保险箱不能通过提案改。
- 用户第 4 题选了“只读”时，什么都不能写。

## 自动生效的改动

用户第 4 题选了 d 或 e 时，一部分低风险的补充可以不问直接生效（比如日记追加）。
`brainlib next` 提示 auto-apply 时运行 `brainlib apply --auto`，然后告诉用户加了什么。

## 自己提建议

| 想做什么 | 命令 |
|---|---|
| 在一篇笔记末尾加内容 | `brainlib propose append <路径> --text "要加的内容" --reason "为什么"` |
| 加到某一节的末尾 | 再加 `--heading "那一节的标题"` |
| 新建一篇 | `brainlib propose create <路径> --text "内容" --reason "为什么"` |
| 整篇换成新版本 | `brainlib propose replace <路径> --file <新版本文件> --reason "为什么"` |
| 改掉其中一行 | `brainlib propose replace_line <路径> --line "那一行里的几个词" --text "改好的这一行" --reason "为什么"` |
| 删掉其中一行 | `brainlib propose remove_line <路径> --line "那一行里的几个词" --reason "为什么"` |

整篇替换的建议在笔记变了之后会失效（退出码 5）；改一行、删一行的建议在那一行没了时失效。失效了就根据最新的笔记重新提。
用户改了主意时，不要用这里的办法改，而是用 `brainlib note "<新说法>" --said --replaces "<旧说法里的几个词>"` 记新说法，来源标记和说话时间才在。
