from __future__ import annotations

import locale
import os

LANGS = ("zh-TW", "en")

MESSAGES: dict[str, dict[str, str]] = {
    # Severity names
    "severity.error": {"zh-TW": "錯誤", "en": "ERROR"},
    "severity.warn": {"zh-TW": "警告", "en": "WARN"},
    "severity.info": {"zh-TW": "提示", "en": "INFO"},

    # Labels
    "label.fix": {"zh-TW": "建議", "en": "Fix"},
    "label.score": {"zh-TW": "分數", "en": "score"},
    "label.hit_rate": {"zh-TW": "命中率", "en": "hit rate"},
    "label.list_sep": {"zh-TW": "、", "en": ", "},

    # Summary
    "summary.scanned": {
        "zh-TW": "{tool} {version} — 掃描 {units} 個安裝單位、{skills} 個 skill（其中 {non_invocable} 個不可自動觸發）",
        "en": "{tool} {version} — scanned {units} install units, {skills} skills ({non_invocable} not model-invocable)",
    },
    "summary.counts": {
        "zh-TW": "🔴 錯誤 {errors}   🟠 警告 {warns}   🟡 提示 {infos}",
        "en": "🔴 Errors {errors}   🟠 Warnings {warns}   🟡 Info {infos}",
    },
    "summary.hidden": {
        "zh-TW": "（{n} 項較低嚴重度的結果未顯示，加上 --min-severity info 可顯示全部）",
        "en": "({n} lower-severity findings hidden; use --min-severity info to show all)",
    },
    "summary.suppressed": {
        "zh-TW": "（{n} 項已被抑制，加上 --show-suppressed 可顯示）",
        "en": "({n} suppressed; use --show-suppressed to show them)",
    },
    "summary.tokens": {
        "zh-TW": "技能清單成本估計：每輪約 {total:,} tokens",
        "en": "Skill listing cost estimate: ~{total:,} tokens per turn",
    },
    "summary.tokens_new": {
        "zh-TW": "技能清單成本估計：每輪約 {total:,} tokens（新來源增加約 {new_src:,}）",
        "en": "Skill listing cost estimate: ~{total:,} tokens per turn (new sources add ~{new_src:,})",
    },

    # Rule titles and descriptions
    "rule.SPEC-NO-FRONTMATTER.title": {"zh-TW": "缺少 YAML frontmatter", "en": "Missing YAML frontmatter"},
    "rule.SPEC-NO-FRONTMATTER.desc": {
        "zh-TW": "SKILL.md 必須以 '---' 包住的 YAML frontmatter 開頭。",
        "en": "SKILL.md must start with YAML frontmatter enclosed in '---' lines.",
    },
    "rule.SPEC-BAD-YAML.title": {"zh-TW": "frontmatter 的 YAML 無效", "en": "Invalid frontmatter YAML"},
    "rule.SPEC-BAD-YAML.desc": {
        "zh-TW": "frontmatter 無法解析，或內容不是鍵值對。",
        "en": "Frontmatter could not be parsed, or is not a key/value mapping.",
    },
    "rule.SPEC-NO-NAME.title": {"zh-TW": "缺少 name 欄位", "en": "Missing name field"},
    "rule.SPEC-NO-NAME.desc": {
        "zh-TW": "frontmatter 沒有 name，已改用資料夾名稱。",
        "en": "Frontmatter has no name; the directory name is used instead.",
    },
    "rule.SPEC-NO-DESC.title": {"zh-TW": "缺少 description 欄位", "en": "Missing description field"},
    "rule.SPEC-NO-DESC.desc": {
        "zh-TW": "沒有 description，模型無法判斷何時該使用這個 skill。",
        "en": "Without a description the model cannot tell when to use this skill.",
    },
    "rule.SPEC-NAME-FORMAT.title": {"zh-TW": "name 格式不符規格", "en": "Invalid name format"},
    "rule.SPEC-NAME-FORMAT.desc": {
        "zh-TW": "Agent Skills 規格：name 只能有小寫英數字與連字號，1–64 字元，不可以連字號開頭或結尾，也不可有連續連字號。",
        "en": "Agent Skills spec: name must be 1-64 lowercase letters, digits and hyphens, not starting/ending with a hyphen and without consecutive hyphens.",
    },
    "rule.SPEC-DESC-LONG.title": {"zh-TW": "description 過長", "en": "Description too long"},
    "rule.SPEC-DESC-LONG.desc": {
        "zh-TW": "description 超過 Agent Skills 規格的 1024 字元上限（Claude Code 會在清單中截斷到 1,536 字元）。",
        "en": "Description exceeds the Agent Skills limit of 1024 characters (Claude Code truncates listings at 1,536).",
    },
    "rule.SPEC-DESC-SHORT.title": {"zh-TW": "description 過短", "en": "Description too short"},
    "rule.SPEC-DESC-SHORT.desc": {
        "zh-TW": "description 太短（英文少於 40 字元、中文少於 15 字），模型難以判斷何時使用。",
        "en": "Description is very short (<40 chars, or <15 CJK chars); too vague to route reliably.",
    },
    "rule.SPEC-NAME-DIR.title": {"zh-TW": "name 與資料夾名稱不同", "en": "Name differs from directory"},
    "rule.SPEC-NAME-DIR.desc": {
        "zh-TW": "Agent Skills 規格要求 name 與所在資料夾名稱相同。",
        "en": "The Agent Skills spec requires name to match the parent directory name.",
    },
    "rule.SRC-FETCH.title": {"zh-TW": "來源抓取失敗", "en": "Failed to fetch source"},
    "rule.SRC-FETCH.desc": {"zh-TW": "無法下載或讀取來源。", "en": "The source could not be cloned or read."},
    "rule.SRC-UNSUPPORTED.title": {"zh-TW": "不支援的來源型別", "en": "Unsupported source type"},
    "rule.SRC-UNSUPPORTED.desc": {
        "zh-TW": "manifest 使用了目前不支援的 source 格式，該 plugin 已略過。",
        "en": "The manifest uses a source format that is not supported yet; the plugin was skipped.",
    },
    "rule.SRC-STUB-BROKEN.title": {"zh-TW": "symlink 文字檔指向不存在的目標", "en": "Broken symlink stub"},
    "rule.SRC-STUB-BROKEN.desc": {
        "zh-TW": "git 以文字檔儲存的 symlink 所指向的目標不存在。",
        "en": "A symlink stored by git as a text file points to a missing target.",
    },
    "rule.NAME-CLASH.title": {"zh-TW": "同名 skill", "en": "Skill name clash"},
    "rule.NAME-CLASH.desc": {
        "zh-TW": "兩個 skill 同名。都沒有命名空間時，低優先的一份會被遮蔽（個人 > 專案）；至少一方是 plugin 時，兩份都會出現在清單上讓模型猜。",
        "en": "Two skills share a name. Without namespaces the lower-priority copy is shadowed (personal beats project); if either is a plugin skill, both are listed and the model has to guess.",
    },
    "rule.DUP-CONTENT.title": {"zh-TW": "內容重複收錄", "en": "Duplicate skill content"},
    "rule.DUP-CONTENT.desc": {
        "zh-TW": "名稱不同但內文幾乎相同（Jaccard ≥ 0.90），可能是改名後重複收錄。",
        "en": "Different names but near-identical bodies (Jaccard >= 0.90), likely the same skill renamed.",
    },
    "rule.OVERLAP.title": {"zh-TW": "觸發重疊", "en": "Trigger overlap"},
    "rule.OVERLAP.desc": {
        "zh-TW": "兩個 skill 的名稱與描述很相似，可能搶同一類請求。",
        "en": "Two skills have very similar names and descriptions and may compete for the same requests.",
    },
    "rule.RULE-CONFLICT.title": {"zh-TW": "可能的規則矛盾（未確認）", "en": "Possible rule conflict (unconfirmed)"},
    "rule.RULE-CONFLICT.title_confirmed": {"zh-TW": "規則矛盾（LLM 已確認）", "en": "Rule conflict (confirmed by LLM)"},
    "rule.RULE-CONFLICT.desc": {
        "zh-TW": "兩個 skill 對相近主題下了方向相反的指示。",
        "en": "Two skills give opposite instructions about the same topic.",
    },
    "rule.GREEDY.title": {"zh-TW": "過度貪婪的描述", "en": "Overly greedy description"},
    "rule.GREEDY.desc": {
        "zh-TW": "描述用了過寬或強制觸發的措辭，可能攔截不相關的請求。",
        "en": "The description uses overly broad or forceful wording that can hijack unrelated requests.",
    },
    "rule.REF-BROKEN.title": {"zh-TW": "附帶檔案不存在", "en": "Broken bundled-file reference"},
    "rule.REF-BROKEN.desc": {
        "zh-TW": "skill 引用的附帶檔案（references/、scripts/、assets/ 等）不存在。",
        "en": "A bundled file referenced by the skill (references/, scripts/, assets/, ...) does not exist.",
    },
    "rule.REF-ABSPATH.title": {"zh-TW": "寫死絕對路徑", "en": "Hardcoded absolute path"},
    "rule.REF-ABSPATH.desc": {
        "zh-TW": "skill 內文含有某台電腦專屬的絕對路徑，換一台電腦就會失效。",
        "en": "The skill body contains a machine-specific absolute path that breaks on other machines.",
    },
    "rule.ROUTE-STEAL.title": {"zh-TW": "請求被搶走", "en": "Requests stolen by another skill"},
    "rule.ROUTE-STEAL.desc": {
        "zh-TW": "路由模擬中，為 A 設計的請求有 25% 以上被路由到 B。",
        "en": "In routing simulation, at least 25% of requests written for A were routed to B.",
    },
    "rule.ROUTE-DEAD.title": {"zh-TW": "幾乎不會被選中", "en": "Rarely selected"},
    "rule.ROUTE-DEAD.desc": {
        "zh-TW": "路由模擬中命中率低於 25%，連為它量身設計的請求都選不到它。",
        "en": "Hit rate below 25% in routing simulation, even for requests written for it.",
    },
    "rule.SUPPRESS-UNUSED.title": {"zh-TW": "沒有作用的抑制規則", "en": "Unused suppression rule"},
    "rule.SUPPRESS-UNUSED.desc": {
        "zh-TW": "設定檔中的 [[ignore]] 沒有匹配任何結果，建議清理。",
        "en": "An [[ignore]] entry in the config did not match any finding; consider removing it.",
    },

    # NAME-CLASH / DUP-CONTENT
    "name_clash.shadow": {
        "zh-TW": "同名遮蔽：{name} — 由 {winner} 勝出，另一份永遠不會被使用。內容：{variant}（相似度 {jaccard:.2f}）",
        "en": "Shadowed: {name} — {winner} wins and the other copy is never used. Content: {variant} (similarity {jaccard:.2f})",
    },
    "name_clash.shadow_tie": {
        "zh-TW": "同名遮蔽：{name} — 兩者優先度相同，哪一份生效取決於安裝位置。內容：{variant}（相似度 {jaccard:.2f}）",
        "en": "Shadowed: {name} — equal priority, so which copy wins depends on where it is installed. Content: {variant} (similarity {jaccard:.2f})",
    },
    "name_clash.both": {
        "zh-TW": "同名共存：{name} — 至少一方是 plugin（有命名空間），兩份都會出現在技能清單上，模型要猜用哪一個，清單 token 也重複計算。內容：{variant}（相似度 {jaccard:.2f}）",
        "en": "Listed twice: {name} — at least one copy is a namespaced plugin skill, so both appear in the listing; the model has to guess and the listing cost is paid twice. Content: {variant} (similarity {jaccard:.2f})",
    },
    "name_clash.newer": {"zh-TW": "；{unit} 宣告的版本較新", "en": "; {unit} declares the newer version"},
    "name_clash.fix": {
        "zh-TW": "只保留一份 {name}，或在 .skillclash.toml 的 [[ignore]] 標記為刻意保留。",
        "en": "Keep a single copy of {name}, or mark the duplicate as intentional with [[ignore]] in .skillclash.toml.",
    },
    "dup_content.msg": {
        "zh-TW": "名稱不同但內文幾乎相同（相似度 {jaccard:.2f}），可能是同一個 skill 改名後重複收錄。",
        "en": "Different names but near-identical bodies (similarity {jaccard:.2f}); probably the same skill renamed.",
    },
    "dup_content.fix": {
        "zh-TW": "確認是否重複安裝，停用 {a} 或 {b} 其中之一。",
        "en": "Check whether this is a double install and disable either {a} or {b}.",
    },

    # OVERLAP
    "overlap.msg": {
        "zh-TW": "觸發文字相似（餘弦相似度 {cosine:.2f}），兩者可能搶同一類請求。\n共同關鍵詞：{terms}",
        "en": "Similar trigger text (cosine {cosine:.2f}); both may be picked for the same requests.\nShared terms: {terms}",
    },
    "overlap.fix": {
        "zh-TW": "在 {a} 與 {b} 的 description 中寫清楚各自負責的情境與不負責的情境。",
        "en": "State in the descriptions of {a} and {b} which situations each one covers and which it does not.",
    },

    # RULE-CONFLICT
    "rule_conflict.msg": {
        "zh-TW": "靜態偵測到方向相反、主題相近的指示（未經確認）。\n共同主題詞：{topics}\nA（第 {la} 行）：「{qa}」\nB（第 {lb} 行）：「{qb}」",
        "en": "Statically detected opposite instructions on a similar topic (unconfirmed).\nShared topic terms: {topics}\nA (line {la}): \"{qa}\"\nB (line {lb}): \"{qb}\"",
    },
    "rule_conflict.fix": {
        "zh-TW": "確認 {a} 與 {b} 是否真的衝突；若是刻意覆寫，可在 .skillclash.toml 用 [[override]] 標記。用 --judge 可讓 LLM 確認。",
        "en": "Check whether {a} and {b} really conflict; mark intentional overrides with [[override]] in .skillclash.toml. Use --judge to have an LLM confirm.",
    },

    # GREEDY
    "greedy.msg": {
        "zh-TW": "描述用了過寬或強制觸發的措辭（分數 {score:.1f}）。\n命中片語：{phrases}",
        "en": "The description uses broad or forceful trigger wording (score {score:.1f}).\nMatched phrases: {phrases}",
    },
    "greedy.stuffing": {
        "zh-TW": "觸發詞灌水（{n} 個分隔項）",
        "en": "keyword stuffing ({n} separated items)",
    },
    "greedy.fix": {
        "zh-TW": "把 {name} 的 description 改寫成具體情境，避免「always」「any task」「一律使用」這類泛稱。",
        "en": "Rewrite the description of {name} around concrete situations; avoid phrases like \"always\", \"any task\" or \"use by default\".",
    },

    # REF-*
    "ref_abs.local": {
        "zh-TW": "含有本機絕對路徑 '{raw}'（這台電腦上存在，換一台電腦就會失效）。",
        "en": "Contains the local absolute path '{raw}' (it exists here but breaks on other machines).",
    },
    "ref_abs.remote": {
        "zh-TW": "寫死絕對路徑 '{raw}'，在其他電腦上無法使用。",
        "en": "Hardcoded absolute path '{raw}' will not exist on other machines.",
    },
    "ref_abs.fix": {
        "zh-TW": "改用相對路徑，或使用 ${CLAUDE_SKILL_DIR} / ${CLAUDE_PLUGIN_ROOT}。",
        "en": "Use a relative path, ${CLAUDE_SKILL_DIR} or ${CLAUDE_PLUGIN_ROOT} instead.",
    },
    "ref_broken.msg": {
        "zh-TW": "引用的附帶檔案 '{raw}' 不在 skill 或 plugin 目錄中。",
        "en": "The bundled file '{raw}' is not present in the skill or plugin directory.",
    },
    "ref_broken.fix": {
        "zh-TW": "確認 '{raw}' 的路徑拼寫，或把該檔案一起提交。",
        "en": "Check the spelling of '{raw}' or commit the missing file.",
    },

    # SPEC fixes and details
    "spec.current": {"zh-TW": "目前為 '{v}'", "en": "currently '{v}'"},
    "spec.length": {"zh-TW": "{n} 字元，上限 {max}", "en": "{n} chars, limit {max}"},
    "spec.length_min": {"zh-TW": "{n} 字元，建議至少 {min}", "en": "{n} chars, recommended minimum {min}"},
    "spec.fix.no_frontmatter": {
        "zh-TW": "在檔案開頭加上以 --- 包住的 YAML frontmatter，至少包含 name 與 description。",
        "en": "Add YAML frontmatter enclosed in --- at the top of the file with at least name and description.",
    },
    "spec.fix.bad_yaml": {
        "zh-TW": "修正 frontmatter 的 YAML 語法（常見原因：描述中有未加引號的冒號）。",
        "en": "Fix the frontmatter YAML (a common cause is an unquoted colon in the description).",
    },
    "spec.fix.no_name": {"zh-TW": "在 frontmatter 加上 name: {dir}。", "en": "Add name: {dir} to the frontmatter."},
    "spec.fix.name_format": {
        "zh-TW": "把 name 改成小寫英數字與連字號，例如 my-skill-name。",
        "en": "Rename to lowercase letters, digits and hyphens, e.g. my-skill-name.",
    },
    "spec.fix.name_dir": {
        "zh-TW": "讓資料夾名稱與 name 一致。",
        "en": "Make the directory name and the name field match.",
    },
    "spec.fix.no_desc": {
        "zh-TW": "加上 description，寫清楚這個 skill 做什麼、什麼時候該用。",
        "en": "Add a description that says what the skill does and when to use it.",
    },
    "spec.fix.desc_long": {
        "zh-TW": "把 description 精簡到 1024 字元內，細節移到內文。",
        "en": "Trim the description to 1024 characters and move details into the body.",
    },
    "spec.fix.desc_short": {
        "zh-TW": "補上具體的使用情境與關鍵字。",
        "en": "Add concrete use cases and keywords.",
    },

    # Routing simulation
    "route.steal.msg": {
        "zh-TW": "為 {a} 設計的請求中，有 {pct:.0f}% 被路由到 {b}。\n範例：{samples}",
        "en": "{pct:.0f}% of the requests written for {a} were routed to {b}.\nExamples: {samples}",
    },
    "route.steal.fix": {
        "zh-TW": "讓 {a} 的描述更具體，或在 {b} 的描述中排除這類情境。",
        "en": "Make the description of {a} more specific, or exclude these situations in {b}.",
    },
    "route.dead.msg": {
        "zh-TW": "命中率只有 {pct:.0f}%，連為它量身設計的請求都很少選到它。",
        "en": "Hit rate is only {pct:.0f}%; even requests written for it rarely select it.",
    },
    "route.dead.fix": {
        "zh-TW": "重寫 {name} 的描述，加入使用者實際會用的說法。",
        "en": "Rewrite the description of {name} using the words users actually type.",
    },

    # Suppression
    "suppress.unused.msg": {
        "zh-TW": "規則 {rule} 的 [[ignore]] 沒有匹配任何結果（原因：'{reason}'）。",
        "en": "The [[ignore]] entry for {rule} matched nothing (reason: '{reason}').",
    },
    "suppress.unused.fix": {
        "zh-TW": "從 .skillclash.toml 移除這條規則。",
        "en": "Remove this entry from .skillclash.toml.",
    },
}


def default_lang() -> str:
    """Pick the report language: SKILLCLASH_LANG, else zh-TW for Chinese locales, else en."""
    env = os.environ.get("SKILLCLASH_LANG")
    if env in LANGS:
        return env
    candidates = [os.environ.get("LC_ALL"), os.environ.get("LANG")]
    try:
        candidates.append(locale.getlocale()[0])
    except ValueError:
        pass
    for c in candidates:
        if c and (c.lower().startswith("zh") or "chinese" in c.lower()):
            return "zh-TW"
    return "en"


def t(key: str, lang: str = "zh-TW", **kwargs: object) -> str:
    """Get localized string by key and language, formatting kwargs."""
    entry = MESSAGES.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
