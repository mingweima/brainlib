"""Sentences meant for the user, in the user's language.

Lines meant for the agent (NEXT, WHY, RUN, FIX) stay in English: they are a stable
contract that any model can follow. Lines after `SAY TO USER:` use the user's language.
Chinese is the default until the user picks a language.
"""

LANGS = ("zh", "en")
DEFAULT_LANG = "zh"

ALIASES = {
    "zh": "zh", "zh-cn": "zh", "zh_cn": "zh", "zh-hans": "zh", "cn": "zh", "chinese": "zh", "中文": "zh", "简体中文": "zh", "a": "zh",
    "en": "en", "en-us": "en", "en_us": "en", "en-gb": "en", "english": "en", "英文": "en", "英语": "en", "b": "en",
}

MESSAGES = {
    "choose_lang": {
        "zh": "你希望我用哪种语言和你交流？ a) 中文  b) English  c) 其他（告诉我是哪种）",
        "en": "Which language would you like me to use? a) 中文 (Chinese)  b) English  c) Other (tell me which)",
    },
    "choose_library": {
        "zh": (
            "你的大脑库放在哪里？ a) 在这台电脑上新建一个文件夹 {suggested}（推荐，最私密）  "
            "b) 我已经有笔记文件夹了（告诉我在哪里）  "
            "c) 放在同步盘里，多台设备都能用（比如 iCloud、OneDrive、坚果云；同步服务商能看到明文，私密内容会放进加密保险箱）  "
            "d) 其他"
        ),
        "en": (
            "Where should your library live? a) A new folder on this computer: {suggested} (recommended, most private)  "
            "b) I already have a notes folder (tell me where)  "
            "c) A synced folder for several devices, like iCloud or OneDrive (the sync provider can read plain text; private notes go in the encrypted vault)  "
            "d) Something else"
        ),
    },
    "secrets": {
        "zh": "我在你的笔记里发现了像密码或密钥的内容（{where}）。放在密码管理器里更安全，笔记里只留一句“在哪里能找到”。要不要你自己挪一下？",
        "en": "I noticed what looks like a password or secret key in your notes ({where}). It would be safer in a password manager, with only a pointer left in the note. Would you like to move it yourself?",
    },
    "private_encrypted": {
        "zh": "我已经把 {n} 篇私密笔记加密放进了保险箱。原来能直接读的文件还在；如果要删掉它们，请你自己在终端运行 `brainlib vault add --all-private --remove-plaintext`。",
        "en": "I've made encrypted copies of {n} private note(s) in the vault. The readable originals are still there; if you want them removed, run `brainlib vault add --all-private --remove-plaintext` yourself.",
    },
    "private_no_vault": {
        "zh": "你有 {n} 篇标了私密的笔记。要把它们锁进加密保险箱，请你自己在终端运行 `brainlib vault init`，它会请你设一个口令。口令请不要告诉我。",
        "en": "You have {n} note(s) marked private. To lock them in the encrypted vault, please run `brainlib vault init` yourself in a terminal; it will ask you to choose a passphrase. Please don't tell me the passphrase.",
    },
    "vault_setup": {
        "zh": (
            "你选了把敏感的事放进加密保险箱。设置要你自己在终端里运行 `brainlib vault init`，再设一个只有你知道的口令。"
            "口令请不要告诉我，也要自己记好，忘了谁都打不开。保险箱设好之前，敏感的事我先不记。现在设，还是以后再说？"
        ),
        "en": (
            "You chose to keep sensitive things in an encrypted vault. To set it up, run `brainlib vault init` yourself in a terminal "
            "and choose a passphrase only you know. Please don't tell me the passphrase, and keep it safe: if it's lost, nobody can open the vault. "
            "Until the vault is set up, I won't record sensitive things. Set it up now, or later?"
        ),
    },
    "review": {
        "zh": "我整理出 {n} 条对你笔记的修改建议，现在一起过一下吗？大概一分钟。",
        "en": "I have {n} suggested change(s) to your notes. Shall we go through them now? It only takes a minute.",
    },
    "check_pass": {
        "zh": "我先做了一个小自测（4 道题），都做对了，可以帮你管理大脑库。",
        "en": "I did a short self-check (4 questions) and passed, so I can help manage your library.",
    },
    "check_pass_small": {
        "zh": "我做了一个小自测，都做对了。不过我是比较小的模型，复杂的整理可能出错，所以每次改动我都会先请你确认。",
        "en": "I passed a short self-check. I'm a smaller model, though, so complex organizing may go wrong; I'll ask you before every change.",
    },
    "check_fail": {
        "zh": (
            "我先做了一个小自测，只做对了 {score}/{total} 道，说明我可能管不好你的大脑库（比如分不清哪些是你的原话、哪些是我的猜测）。"
            "建议换一个更强的 AI 模型来做记录和整理；我可以先只做“只读查询”。要我先切到只读模式吗？"
        ),
        "en": (
            "I did a short self-check and got only {score} of {total} right, so I may not manage your library well "
            "(for example, telling your own words apart from my guesses). A stronger AI model would be better for recording "
            "and organizing; I can stick to read-only lookups for now. Shall I switch to read-only mode?"
        ),
    },
    "permissions": {
        "zh": "为了让我能读写你的大脑库，可能需要你在系统里给我（或终端）开一下文件夹权限。我会一步步告诉你点哪里，你只需要确认。",
        "en": "So I can read and write your library, you may need to give me (or the terminal) access to the folder. I'll tell you step by step what to click; you only need to confirm.",
    },
    "connect": {
        "zh": (
            "为了让你以后每次新开对话，AI 都先看一眼大脑库，聊完也记得把新东西记下来，我想在你常用的 AI 工具里加几行全局说明。"
            "你平常用哪几个？比如 Cursor、Claude Code、Codex、Trae。加之前我会把要加的文字给你看。"
        ),
        "en": (
            "So that every new conversation starts by checking your brain library, and new things get remembered afterwards, "
            "I'd like to add a few lines to the global instructions of the AI tools you use. Which ones do you use, "
            "for example Cursor, Claude Code, Codex or Trae? I'll show you the text before adding it."
        ),
    },
    "connect_paste": {
        "zh": "这个工具的规则只能在设置里改，我没法替你写进去。请{where}",
        "en": "This tool keeps its rules in a settings screen, so I can't add them for you. Please {where}",
    },
}


def normalize(lang):
    if not lang:
        return None
    return ALIASES.get(str(lang).strip().lower())


def t(key, lang=None, **kw):
    lang = normalize(lang) or DEFAULT_LANG
    block = MESSAGES[key]
    text = block.get(lang) or block["en"]
    return text.format(**kw) if kw else text


def both(key, **kw):
    """Chinese then English, for what is said before the user has picked a language."""
    return "%s\n%s" % (t(key, "zh", **kw), t(key, "en", **kw))
