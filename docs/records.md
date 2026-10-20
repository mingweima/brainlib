# 记录、分层索引和每日日志 / Records, tiered index and daily log

> 这页讲 v0.2 起 brainlib 怎么存一条记录、怎么排、怎么取舍。需求来自 2026-10-20 开发者提的四条要求和一次全新环境下的沙盒测试；隐私那几条按开发者的意思往后放，见本页最后一节。

## 一条记录带四个标签

AI 用 `brainlib note` 记下的每一句话都是一条记录。v0.2 起每条记录固定带四个标签，AI 可以自己填，没填的由 brainlib 推断，并在记录里标明是推断的，所以旧的 AI 照老办法记也能跑。

| 标签 | 取值 | 没填时 |
|---|---|---|
| 说话时间 | 用户说这句话的时间，精确到分钟，例如 `2026-10-20 09:42` | 取记下的那一刻，并标明是估计的 |
| 分类 | 属于库里哪个区，例如「关于我」「决定」「日记」，或者库里已有的文件夹名 | 按落到哪篇笔记推断，推断不出就是「未分类」 |
| 重要性 | 重要、一般、次要 | 一般；分类是「决定」的算重要 |
| 私密等级 | 普通、秘密、机密、绝密 | 普通；加了 `--private` 的算秘密 |

说话时间和记下时间分开存。补记以前说过的话时，AI 用 `--said-at "2026-10-13 21:05"` 写明当时的时间，排序和取舍都按说话时间，不按记下的时间。

私密等级沿用原来的处理办法。秘密就是原来的 `--private`，按用户在第 7 题选的方式处理；机密只能进加密保险箱，没有保险箱就不存；绝密一律不存，和密码、密钥一样。

## 记录也分 L0 到 L3

页面早就分 L0 到 L3，v0.2 让每条记录也有层级，规则是新的先在上层露出，旧的往下沉。

- **L0。** 核心页（比如 `me.md`）里的每一行，以及刚记下、还没整理、标了重要的记录。AI 每次开工前都要看。
- **L1。** 刚记下、还没整理的其他记录，以及各区的入口页。它们出现在索引的「最近记下的」里。
- **L2。** 已经整理进普通笔记的记录，以及 14 天内的日志。
- **L3。** 归档区里的，以及 14 天前的日志。索引不再列出，但 `find` 和按条件筛选时仍然找得到。

## 索引长度固定，能按任一标签排序和筛选

`brainlib index` 的默认输出不随库变大。它依次列出核心页、还没整理的重要记录（最多 10 条）、各区入口页、最近 7 天的日志、按说话时间排的最近记录（最多 20 条），以及可能过时的说法（最多 5 处）。超出的部分只给一句「还有几条，怎么查」。

带上条件时，`index` 改为列记录。可以按说话时间、重要性、分类、私密等级或层级排序，也可以按分类、重要性、日期范围和层级筛选，例如 `brainlib index --category 决定 --since 2026-10-01 --sort importance`。私密的记录从不出现在给 AI 看的输出里，按私密等级筛选时只给条数。全量的机器可读清单在状态目录的 `records.json` 里，MCP 的 `kb_index` 也接受同样的条件。

## 每日日志

整理时，每条记录都会按说话时间插进当天的日志 `journal/2026-10-20.md`，同一天里按时间先后排，补记的旧话会插到对应的位置。日志是流水账，记下用户哪天几点说了什么；笔记页记的是现在算数的说法。

日志按用户第 4 题的选择写入。选了「小的、低风险的补充直接加」或「大部分直接做」的，日志直接写；选了「提出修改建议」的，每天的日志合成一条建议给用户看。笔记页那边每条记录单独一条建议，用户可以收一部分、拒一部分；拒掉的只是不进那篇笔记，日志里那一行照旧留着，因为用户确实说过。`brainlib log` 随时可以按天看记录，包括还没整理的。不想要日志的库，在配置里写 `"daily_log": false`。

分类是「日记」的记录，以及没写分类、重要性是「次要」的记录，只进日志，不进笔记页。

AI 的日常规则里加了一条，对话快结束时，把这次用户定下的事和说过的偏好一件一条记下来，闲聊不记。

## 同一件事以最新说法为准

这条分三层保证。

第一层在读的时候。每一行都带说话时间，日常规则写明，同一件事有新旧两种说法时以时间最新的为准，所以就算旧说法还没删，AI 也知道该信哪句。

第二层在写的时候。用户改了主意，AI 记新说法时加 `--replaces "<旧说法里的几个词>"`，整理时 brainlib 会生成一条替换建议，把旧的那一行换成新的，并在行尾留一句「（10-13 说的是：标准误聚类到公司层面）」，用户点头才生效。旧说法要是还在缓存区、没整理进笔记，整理时只有新说法进笔记，并带上同样的括号；旧的那条标成「已被替换」，留在日志里，索引不再列它，它要是已经单独等着用户批，那条建议会作废。AI 没加这个参数时，brainlib 会在同一篇笔记里找字面很像的旧行，找到了只在建议理由里提一句，不自动替换。字面像不等于改了主意，比如「熟悉 PyTorch」和「熟悉 JAX」可以同时成立，自动替换反而会丢掉一句真话。用户把老偏好再说一遍时，笔记不动，只把这次的时间记进日志，索引里会显示这句最近一次是哪天说的。旧说法被换掉以后，日志里当天那一行还在，但索引和 `index` 的筛选结果不再列它，按天看时会注明后来换了。

第三层在体检的时候。`brainlib health` 和索引的「可能过时」一节会列出同一篇笔记里字面很像、日期不同的几行，提醒用户留新的那句。用户同意删旧的，AI 用 `brainlib propose remove_line <笔记> --line "<旧行里的几个词>"` 提建议。字面不像的冲突（比如「回复别超过三段」和「越详细越好」）程序认不出，只能靠前两层。

## 写进笔记的样子

一条记录写进笔记是一行，来源标记放在开头。

```text
- [said 2026-10-20 09:42] 回复别超过三段。
- [said 2026-10-20 09:45, 重要] 阅读 app 先做 iOS。
- [inferred 2026-10-20 10:02] 用户写东西时偏爱短句。
```

方括号里依次是来源、说话时间，再往后是可选的补充。重要性只在不是「一般」时写，日志和「未分类」页里还会写分类。笔记页的分类由它所在的页面和小节决定，不重复写。手改笔记时，旧格式 `[said 2026-10-20]` 照样认，标记放在行尾也认。

## 和旧版本兼容

v0.1 的库不用迁移。旧记录没有分类和重要性，读出来按推断值处理；旧的来源标记只有日期，按当天零点排序。命令行和 MCP 只加了可选参数，原来的写法都还能用。分类是「决定」的记录会落到 `decisions.md`，这页第一次用到时才建。

## 这一版没做的

- 隐私方面的加强，包括漏加 `--private` 时补救、更多密钥格式的识别、`find` 先遮蔽再匹配，都按开发者的意思往后放。
- 字面不像的冲突识别要靠语言模型，规则后端做不到。
- 同义词还查不到，比如搜「可视化」找不到写着「画图」的笔记。单个汉字已经能搜了。
- 每天的日志建议只能整条批；笔记页的建议已经是一条记录一条。

## English summary

Every record now carries four tags: when the user said it (to the minute), a category (the area of the library it belongs to), importance (high, normal, low) and a privacy level (normal, private, confidential, secret). Agents may set them with `--said-at`, `--category`, `--importance` and `--privacy`; anything left out is inferred and marked as inferred. Records get tiers like pages: new ones surface at L0/L1 in the index, filed ones sit at L2, and archived or old journal entries sink to L3. The default `brainlib index` has a fixed length; with filters it lists records sorted by any tag. Organising writes every record into the day's journal in time order, and `brainlib log` shows records by day. The newest statement about the same thing wins: lines carry the time they were said, `--replaces "<old words>"` turns a change of mind into a replace-line proposal that keeps the old wording as a short note, look-alike older lines are only pointed out (looking alike is not changing one's mind), and `brainlib health` lists look-alike lines with different dates. Each record gets its own proposal, so the user can take some and leave others; the day's journal is one proposal per day. Set `"daily_log": false` to turn the journal off.
