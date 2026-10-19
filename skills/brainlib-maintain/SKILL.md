---
name: brainlib-maintain
description: 给大脑库做体检（断链、过期、冲突、缺说明），理解 L0 到 L3 分层和笔记开头的字段，帮用户查找和归档。brainlib next 提示 health，或者用户想整理库的结构时使用。
---

# 体检和维护

## 体检

运行 `brainlib health`。它列出问题，每类附一句怎么修。用大白话给用户解释，修改一律走提案（见 `skills/brainlib-organize/SKILL.md`）。

| 问题 | 意思 | 怎么修 |
|---|---|---|
| 断链 | 链接指向一篇不存在的笔记 | 改链接，或者新建那一篇 |
| 过期 | 页面过了该复查的日期 | 问用户内容还对不对，再提议更新 |
| 冲突 | 同一文件夹里两篇主页面同名 | 问用户哪篇是现在用的，另一篇标 `authority: archived` |
| 缺说明 | 重要页面没有 description 或 read_when | 提议加一句说明和“什么时候读” |
| 文件头读不懂 | 笔记开头的格式写错了 | 提议改正 |
| 库里有密码 | 见 `skills/brainlib-privacy/SKILL.md` | 请用户挪进密码管理器 |

不想现在处理：`brainlib next --snooze health`，一周后再提醒。

## 分层

| 层 | 是什么 | 例子 | 改动要求 |
|---|---|---|---|
| L0 核心 | 最重要的几页，替用户做事前必读 | `me.md` | 每次都要用户亲口同意 |
| L1 入口 | 目录、索引 | `README.md` | 每次都要用户同意 |
| L2 普通 | 大多数笔记 | 项目、读书笔记 | 按用户第 4 题的设置 |
| L3 存档 | 旧东西、两周以前的日记 | `_archive/` 里的笔记 | 按用户第 4 题的设置 |

笔记没写 tier 时，brainlib 自己推断，不会改文件。想固定下来，就提议在笔记开头加 `tier: L1` 这样一行。

## 笔记开头的字段

全部可选。旧笔记没有这一段也完全能用。

```yaml
---
type: Note
title: 每周计划
description: 一句话说明这篇是什么
read_when: [做周计划时, 用户问这周安排时]
tier: L2
authority: canonical   # canonical 当前有效；pointer 只是指向别处；archived 已存档
updated: 2026-10-20
sensitivity: internal  # public / internal / private / secret
---
```

完整规则见 `spec/front-matter.md`。

## 查找

- `brainlib index`：给 AI 看的阅读指南，最重要的页排在前面。
- `brainlib find "主题"`：按主题找笔记。
- `brainlib read <路径>`：读一篇。

## 归档

用户说某篇过时了，提议在它开头加 `authority: archived`。要挪进 `_archive/` 文件夹的话，
v0.1 里请用户自己挪，或者先提议新建一篇、再请用户删掉旧的。
