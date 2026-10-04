from __future__ import annotations

import re
import unicodedata

# English stopwords
EN_STOPWORDS = frozenset([
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where",
    "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with",
    "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
    "your", "yours", "yourself", "yourselves",
])

# Chinese function bigrams
ZH_STOPWORDS = frozenset([
    "使用", "如果", "需要", "可以", "時候", "这个", "這個", "進行", "进行",
    "相關", "相关", "並且", "并且", "以及", "或者", "能夠", "能够", "透過",
    "通过", "根據", "根据", "關於", "关于", "對於", "对于", "為了", "为了",
    "因為", "因为", "所以", "這些", "这些", "那些", "什麼", "什么", "怎麼",
    "怎么", "怎樣", "怎样", "一個", "一个", "一些", "很多", "可能", "應該",
    "应该", "並且", "以及",
])

# Skill template words that appear everywhere in skill descriptions
SKILL_TEMPLATE_WORDS = frozenset([
    "use", "used", "using", "when", "whenever", "user", "users", "want",
    "wants", "ask", "asks", "asked", "skill", "skills", "claude", "agent",
    "help", "helps", "task", "tasks", "request", "need", "needs", "trigger",
    "triggers", "mention", "mentions", "invoke", "invoking", "this", "that",
    "also", "like", "etc", "tool", "tools", "assistant",
    # Chinese template words/bigrams
    "使用者", "用戶", "用户", "技能", "觸發", "触发", "請求", "请求",
    "任務", "任务", "調用", "调用", "幫助", "帮助", "執行", "执行",
])

URL_PATTERN = re.compile(r"https?://\S+|ftp://\S+|www\.\S+")
LATIN_WORD_PATTERN = re.compile(r"[a-z][a-z0-9+#.]*[a-z0-9+#]|[a-z]")
CJK_CHAR_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def stem_latin(word: str) -> str:
    """Lightweight suffix stripping: ies->y, then ing/ed/es/s if remaining len >= 3."""
    if word.endswith("ies") and len(word) >= 5:
        return word[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix):
            stem = word[: -len(suffix)]
            if len(stem) >= 3:
                return stem
    return word


def tokenize(
    text: str,
    extra_stopwords: list[str] | None = None,
    extra_templates: list[str] | None = None,
) -> list[str]:
    """Tokenize English & CJK mixed text for TF-IDF and topic matching."""
    if not text:
        return []

    # 1. Normalize and lowercase
    norm = unicodedata.normalize("NFKC", text).lower()

    # 2. Remove URLs
    norm = URL_PATTERN.sub(" ", norm)

    # Remove inline backticks but keep content
    norm = norm.replace("`", " ")

    # Strip markdown symbols
    for ch in ("#", "*", "_", "~", "[", "]", "(", ")", ">", "<", "=", "|", "!", "{", "}"):
        norm = norm.replace(ch, " ")

    # Custom stops
    custom_stops = set(extra_stopwords or [])
    custom_templates = set(extra_templates or [])

    tokens: list[str] = []
    curr_cjk: list[str] = []
    curr_latin: list[str] = []

    def flush_latin() -> None:
        if not curr_latin:
            return
        segment = "".join(curr_latin)
        curr_latin.clear()
        for m in LATIN_WORD_PATTERN.finditer(segment):
            raw = m.group(0)
            if raw in EN_STOPWORDS or raw in SKILL_TEMPLATE_WORDS or raw in custom_stops or raw in custom_templates:
                continue
            stemmed = stem_latin(raw)
            if stemmed in EN_STOPWORDS or stemmed in SKILL_TEMPLATE_WORDS or stemmed in custom_stops or stemmed in custom_templates:
                continue
            if len(stemmed) >= 2 or stemmed in ("c", "r"):
                tokens.append(stemmed)

    def flush_cjk() -> None:
        if not curr_cjk:
            return
        chars = "".join(curr_cjk)
        curr_cjk.clear()
        if len(chars) == 1:
            ch = chars[0]
            if ch not in ZH_STOPWORDS and ch not in custom_stops:
                tokens.append(ch)
            return

        # Generate character bigrams
        for i in range(len(chars) - 1):
            bg = chars[i : i + 2]
            if bg in ZH_STOPWORDS or bg in SKILL_TEMPLATE_WORDS or bg in custom_stops or bg in custom_templates:
                continue
            tokens.append(bg)

    for char in norm:
        if CJK_CHAR_PATTERN.match(char):
            flush_latin()
            curr_cjk.append(char)
        elif char.isalnum() or char in "+#.-":
            flush_cjk()
            curr_latin.append(char)
        else:
            flush_latin()
            flush_cjk()

    flush_latin()
    flush_cjk()

    return tokens
