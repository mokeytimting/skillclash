from __future__ import annotations

import re

from skillclash.model import Rule
from skillclash.parse.tokenize import tokenize

# Markers definitions: (pattern_or_str, polarity, strength)
MARKERS = [
    # Multi-word negative
    (r"\b(?:must\s+not|do\s+not|don't|dont|should\s+not|shouldn't)\b", -1, 2),
    (r"\b(?:be\s+sure\s+to|make\s+sure)\b", 1, 2),
    # Single-word English
    (r"\balways\b", 1, 2),
    (r"\bmust\b", 1, 2),
    (r"\brequired\b", 1, 2),
    (r"\bensure\b", 1, 2),
    (r"\bshould\b", 1, 1),
    (r"\bprefer\b", 1, 1),
    (r"\brecommended\b", 1, 1),
    (r"\bnever\b", -1, 2),
    (r"\bforbidden\b", -1, 2),
    (r"\bprohibited\b", -1, 2),
    (r"\bavoid\b", -1, 1),
    # Chinese negative
    ("盡量不要", -1, 1),
    ("尽量不要", -1, 1),
    ("絕對不", -1, 2),
    ("绝对不", -1, 2),
    ("禁止", -1, 2),
    ("不得", -1, 2),
    # 「不可」but not 不可能 / 不可或缺 / 不可少
    ("re:不可(?!能|或缺|少|思議|思议)", -1, 2),
    ("絕不", -1, 2),
    ("绝不", -1, 2),
    ("切勿", -1, 2),
    ("嚴禁", -1, 2),
    ("严禁", -1, 2),
    ("避免", -1, 1),
    ("不要", -1, 1),
    # 「別」only as an imperative at the start of a clause, not in 特別 / 類別 / 識別
    ("re:(?:^|[，,：:、])\\s*[別别](?=[\\u4e00-\\u9fff])", -1, 1),
    # Chinese positive
    ("一定要", 1, 2),
    ("一律", 1, 2),
    ("必須", 1, 2),
    ("必须", 1, 2),
    ("務必", 1, 2),
    ("务必", 1, 2),
    ("總是", 1, 2),
    ("总是", 1, 2),
    ("優先", 1, 1),
    ("优先", 1, 1),
    ("盡量", 1, 1),
    ("尽量", 1, 1),
    ("建議", 1, 1),
    ("建议", 1, 1),
]

SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?;。！？；\n]+")
LIST_ITEM_PREFIX = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")


def extract_rules(body: str, line_offset: int) -> list[Rule]:
    """Extract actionable rules with polarity, strength, and topic from markdown body."""
    lines = body.splitlines()
    in_code_block = False
    in_html_comment = False

    rules: list[Rule] = []

    for idx, raw_line in enumerate(lines):
        line_num = line_offset + idx
        stripped = raw_line.strip()

        # Handle fenced code block
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Handle HTML comment
        if "<!--" in stripped and "-->" in stripped:
            stripped = re.sub(r"<!--.*?-->", "", stripped).strip()
        elif "<!--" in stripped:
            in_html_comment = True
            continue
        elif "-->" in stripped:
            in_html_comment = False
            continue
        if in_html_comment:
            continue

        # Skip headers
        if stripped.startswith("#"):
            continue
        if not stripped:
            continue

        # Remove list item prefix if present
        content = LIST_ITEM_PREFIX.sub("", stripped)

        # Split into sub-sentences
        sub_sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(content) if s.strip()]

        for sent in sub_sentences:
            if len(sent) < 4:
                continue

            # Match markers
            # Specific handle: "always avoid" -> negative rule
            sent_lower = sent.lower()

            matches: list[tuple[int, int, int, int, str]] = []  # (start_pos, -length, polarity, strength, matched_text)
            for marker_pat, polarity, strength in MARKERS:
                if marker_pat.startswith(r"\b"):
                    for m in re.finditer(marker_pat, sent_lower):
                        matches.append((m.start(), -len(m.group(0)), polarity, strength, m.group(0)))
                elif marker_pat.startswith("re:"):
                    for m in re.finditer(marker_pat[3:], sent):
                        matches.append((m.start(), -len(m.group(0)), polarity, strength, m.group(0)))
                else:
                    pos = 0
                    while True:
                        idx_found = sent.find(marker_pat, pos)
                        if idx_found == -1:
                            break
                        matches.append((idx_found, -len(marker_pat), polarity, strength, marker_pat))
                        pos = idx_found + len(marker_pat)

            if not matches:
                continue

            # Check if there is an 'avoid' or negative constraint coupled with 'always' / 'make sure'
            # e.g., "always avoid"
            has_avoid_or_neg = any(m[2] < 0 for m in matches)
            has_strong_pos = any(m[2] > 0 and m[3] == 2 for m in matches)

            if has_avoid_or_neg and has_strong_pos:
                # E.g. "always avoid X" -> this is a strong negative prohibition (polarity -1, strength 2)
                best_polarity = -1
                best_strength = 2
            else:
                # Sort by start position first, then longest match
                matches.sort(key=lambda x: (x[0], x[1]))
                best_polarity = matches[0][2]
                best_strength = matches[0][3]

            # Extract topic: clean marker words from sentence text before tokenizing
            clean_sent = sent
            marker_tokens = set()
            for _, _, _, _, matched_word in matches:
                clean_sent = re.sub(re.escape(matched_word), " ", clean_sent, flags=re.IGNORECASE)
                marker_tokens.update(tokenize(matched_word))

            raw_tokens = tokenize(clean_sent)
            topic = frozenset([t for t in raw_tokens if t not in marker_tokens])

            if len(topic) < 2:
                continue

            rules.append(
                Rule(
                    text=sent,
                    polarity=best_polarity,
                    strength=best_strength,
                    topic=topic,
                    line=line_num,
                )
            )

            if len(rules) >= 200:
                return rules

    return rules
