from __future__ import annotations

JUDGE_SYSTEM_PROMPT = """You are auditing AI agent "skills" (instruction files that an assistant loads on demand).
Decide whether two skills conflict when both are installed together.
Definitions:
- "conflict": following one skill's instructions would violate the other's for the same situation.
- "overlap": both would plausibly be chosen for the same user request (routing ambiguity), but instructions do not contradict.
- "compatible": related, but they cover clearly different situations.
- "unrelated": no meaningful relationship.
Quote exact text from the skills as evidence. Respond with JSON only."""

JUDGE_USER_PROMPT_TEMPLATE = """Skill A: {qualified_name_a}
Description: {description_a}
Relevant excerpts (rules / lines):
{excerpts_a}

Skill B: {qualified_name_b}
Description: {description_b}
Relevant excerpts:
{excerpts_b}

Static analysis flagged this pair because: {reason}

Return JSON:
{{"verdict":"conflict|overlap|compatible|unrelated","confidence":0.0-1.0,
 "situation":"<the user situation where they collide, or empty>",
 "quote_a":"<exact quote from A>","quote_b":"<exact quote from B>",
 "explanation":"<one or two sentences in {lang_name}>",
 "suggested_fix":"<concrete fix in {lang_name}>"}}"""

PROMPTGEN_USER_TEMPLATE = """Below is an AI agent skill. Write {k} realistic messages a user might type that SHOULD cause an assistant to use this skill.
Rules: do not mention the skill's name; message 1 direct; message 2 indirect (avoid words from the description);
message 3 in Traditional Chinese; message 4 somewhat ambiguous. Each under 40 words.
Return JSON only: {{"prompts": ["...", "..."]}}

Name: {name}
Description: {description}
Body (truncated):
{body_first_60_lines}"""

ROUTER_SYSTEM_TEMPLATE = """You are an assistant with access to the following skills. A skill should be loaded only when the user's request matches its description.
Available skills:
{listing}

For the user's message, decide which single skill (if any) you would load first.
Respond with JSON only: {{"skill": "<exact skill name from the list>"}} or {{"skill": "none"}}."""
