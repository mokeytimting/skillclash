# Rules / 規則

Every finding has a rule code, a severity and the quoted text it is based on.
Run `skillclash explain <CODE>` for a one-line summary in your terminal.

每個結果都有規則代碼、嚴重度，以及作為依據的原文引用。終端機可用 `skillclash explain <代碼>` 查看摘要。

**Severity / 嚴重度:** 🔴 error · 🟠 warn · 🟡 info. Text output shows warn and above by default
(`--min-severity info` shows everything). The exit code is 1 when there is at least one finding at or above
`--fail-on` (default `error`).

By default, skills that ship in the **same repo or marketplace** are not compared with each other: you choose
which plugins of a marketplace to install, and the author owns overlaps inside their own pack. Use `--intra`
to include them (their severity is lowered by one level).

預設**不比較同一個 repo／marketplace 裡的 skill**：marketplace 的 plugin 是由使用者自己挑選安裝的，包內的重疊由作者負責。
加上 `--intra` 可以納入比較（嚴重度自動降一級）。

---

## Conflicts between skills / skill 之間的衝突

### NAME-CLASH

🔴 / 🟠 Two skills share a name.

- **🔴 error — shadowing.** Neither copy is namespaced (personal `~/.claude/skills`, project
  `.claude/skills`, or a repo without a plugin manifest). Claude Code keeps only one: personal beats project.
  The other copy is silently never used.
- **🟠 warn — listed twice.** At least one copy is a plugin skill (`plugin:name`). Both appear in the skill
  listing, the model has to pick, and you pay the listing tokens twice.

`evidence.variant` compares the bodies: `identical` (Jaccard ≥ 0.98), `drifted` (≥ 0.5, the copies diverged)
or `different` (a rewrite or an unrelated skill that happens to share the name). When both copies declare a
`version`, the newer one is named.

🔴／🟠 兩個 skill 同名。都沒有命名空間時會互相**遮蔽**（個人 > 專案），被遮蔽的那份永遠不會被使用；
至少一方是 plugin 時，兩份**都會出現在清單上**，模型得猜用哪個，token 也付兩次。

**Fix:** keep one copy, or rename. **Suppress:** `[[ignore]] rule = "NAME-CLASH"  skills = ["name"]`.

### DUP-CONTENT

🟠 Different names, near-identical bodies (Jaccard ≥ 0.90): the same skill installed twice under two names.

🟠 名稱不同但內文幾乎相同：同一個 skill 被改名後裝了兩次。

### OVERLAP

🟠 / 🟡 Two skills describe themselves so similarly that the model may pick either for the same request.
Compared text: name + `description` + `when_to_use` + `triggers`, TF‑IDF cosine with Chinese character
bigrams. 🟠 at cosine ≥ 0.25, 🟡 at ≥ 0.20 (calibrated, see [calibration.md](calibration.md)). Skills with
`disable-model-invocation: true` are skipped because the model never picks them.

🟠／🟡 兩個 skill 的描述太像，模型可能把同一個請求交給任一個。比對名稱、description、when_to_use、triggers，
中文用字元 bigram。cosine ≥ 0.25 為警告，≥ 0.20 為提示。

**Fix:** state in each description what it covers *and* what it does not ("NOT for X — use Y").

### RULE-CONFLICT

🟠 Two skills (or a skill and a `CLAUDE.md`) give opposite instructions for the same situation.
Static detection (opposite "always/never/必須/禁止" sentences on the same topic) is a **candidate generator
only**: it was right 0 times out of 15 on real packs. Candidates are sent to the LLM with `--judge`; only
conflicts the LLM confirms, with quotes verified against the files, are reported. `--rule-candidates` shows
the raw candidates as 🟡.

🟠 兩個 skill（或 skill 與 CLAUDE.md）對同一情境下了相反的指示。靜態偵測只用來**產生候選**（實測 15 個全是誤報），
需要 `--judge` 由 LLM 確認且引用通過原文比對後才會輸出。

**Intentional override:** `[[override]] skill = "x"  topics = ["scratchpad"]  reason = "..."`.

### ROUTE-STEAL / ROUTE-DEAD

Only with `--route`. An LLM writes test requests for each skill, then a router model (Claude by default)
picks a skill from the full listing, three votes per request.

- 🟠 **ROUTE-STEAL:** at least 25% of the requests written for A were routed to B.
- 🟡 **ROUTE-DEAD:** fewer than 25% of A's own requests selected A.

只有加 `--route` 才會執行：先由 LLM 為每個 skill 產生測試請求，再讓路由模型從完整清單中挑選（每句投票 3 次）。
A 的請求有 ≥ 25% 被 B 搶走為 ROUTE-STEAL；A 連自己的請求都選不到 25% 為 ROUTE-DEAD。

---

## Description quality / 描述品質

### GREEDY

🟠 The description claims requests far outside its own domain ("Use on ANY coding task",
"use proactively whenever…", "before finishing any reply"). Weighted phrase score ≥ 5. Scoped wording like
"any time a .pptx file is involved" is not flagged.

🟠 描述宣稱要處理遠超出自身領域的請求。範圍明確的寫法（例如「只要涉及 .pptx 檔」）不會被標記。

**Fix:** describe concrete situations instead of claiming everything.

### SPEC-*

Checks against the [Agent Skills specification](https://agentskills.io/specification).

| Code | Severity | Meaning / 說明 |
|---|---|---|
| `SPEC-NO-FRONTMATTER` | 🔴 | No `---` YAML frontmatter / 缺少 frontmatter |
| `SPEC-BAD-YAML` | 🔴 | Frontmatter does not parse (often an unquoted `:`) / YAML 解析失敗 |
| `SPEC-NO-DESC` | 🔴 | Empty description: the model cannot know when to use it / 沒有 description |
| `SPEC-NO-NAME` | 🟠 | No `name`; directory name used / 沒有 name |
| `SPEC-NAME-FORMAT` | 🟠 | Name not 1–64 chars of `a-z0-9-` / name 格式不符 |
| `SPEC-DESC-LONG` | 🟠 | Description over 1024 chars (Claude Code truncates listings at 1,536) / description 過長 |
| `SPEC-DESC-SHORT` | 🟡 | Under 40 chars (15 CJK chars) / description 過短 |
| `SPEC-NAME-DIR` | 🟡 | Name differs from its directory / name 與資料夾不同 |

---

## Files and sources / 檔案與來源

### REF-BROKEN

🟠 A file the skill bundles is missing: a relative markdown link, a `${CLAUDE_SKILL_DIR}` /
`${CLAUDE_PLUGIN_ROOT}` path, or a `references/`, `scripts/`, `assets/`… path when that folder exists next to
the skill. Paths that describe the user's own project (`src/app.ts`, `word/document.xml`) are not checked.

🟠 skill 附帶的檔案不存在。描述使用者自己專案的路徑不檢查。

### REF-ABSPATH

🟠 / 🟡 A machine-specific absolute path. 🟠 when it is inside someone's home directory
(`/Users/kevin/…`, `C:\Users\kevin\…`); 🟡 for other drive paths, which are usually examples. `~/…` is
portable and never flagged.

**Fix:** use a relative path, `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}`.

### SRC-FETCH / SRC-UNSUPPORTED / SRC-STUB-BROKEN

- 🔴 **SRC-FETCH:** a source could not be cloned or read.
- 🟡 **SRC-UNSUPPORTED:** a marketplace entry uses a source type skillclash cannot read yet (e.g. `npm`).
- 🟠 **SRC-STUB-BROKEN:** a symlink stored by git as a one-line text file points nowhere.

### SUPPRESS-UNUSED

🟡 An `[[ignore]]` entry in `.skillclash.toml` matched nothing; remove it so the allowlist does not rot.

---

## Suppressing findings / 抑制結果

`.skillclash.toml` (searched in the current directory, the git root, then `~/.config/skillclash/config.toml`
or `%APPDATA%\skillclash\config.toml`):

```toml
[thresholds]
overlap_warn = 0.25
overlap_info = 0.20

[severity]
GREEDY = "off"          # or "info" / "warn" / "error"

[[ignore]]
rule = "NAME-CLASH"
skills = ["deepseek-orchestrator"]   # name, plugin:name or full id
reason = "I keep both copies on purpose"

[[ignore]]
rule = "OVERLAP"
pair = ["document-skills:pdf", "my-pdf-helper"]
reason = "checked: different jobs"

[[override]]
skill = "my-skill"
topics = ["scratchpad", "temp"]
reason = "deliberately overrides the system default"
```

Inline, inside a SKILL.md:

```markdown
<!-- skillclash-ignore: OVERLAP with=pdf reason="different jobs" -->
```

Suppressed findings do not affect the exit code; `--show-suppressed` lists them.
被抑制的結果不影響結束碼，可用 `--show-suppressed` 顯示。
