# skillclash

**找出會互相打架的 agent skill。** skillclash 檢查 Claude Code／[Agent Skills](https://agentskills.io) 之間的同名衝突、
觸發重疊、互相矛盾的指示，以及壞掉的檔案引用。可以檢查你電腦上已安裝的 skill，也可以在**安裝之前**先檢查網路上的 skill 包。

[English](README.md) · [規則說明](docs/rules.md) · [門檻怎麼訂的](docs/calibration.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

```text
$ skillclash compare gh:obra/superpowers gh:addyosmani/agent-skills gh:mattpocock/skills gh:thedotmack/claude-mem --lang zh-TW

🟠 NAME-CLASH  同名 skill: test-driven-development
   ├ plugin:addy-agent-skills/agent-skills  gh:addyosmani/agent-skills/skills/test-driven-development/SKILL.md:1
   └ plugin:superpowers-dev/superpowers     gh:obra/superpowers/skills/test-driven-development/SKILL.md:1
   同名共存：test-driven-development — 至少一方是 plugin（有命名空間），兩份都會出現在技能清單上，
   模型要猜用哪一個，清單 token 也重複計算。內容：different（相似度 0.00）
   建議: 只保留一份 test-driven-development，或在 .skillclash.toml 的 [[ignore]] 標記為刻意保留。
```

## 為什麼需要它

skill 包越來越大，單一 repo 動輒 300 個以上，而且大家常常同時裝好幾個。接著就會發生：

- 兩個 skill 都對同一類請求有反應，模型每次隨便挑一個；
- 別人的 skill 跟你的同名，悄悄把你的蓋掉（個人層級優先於專案層級）；
- 一個 skill 說「一定要跑測試」，另一個說「不要自己跑測試」；
- 某個描述寫著「Use on ANY coding task」，把其他 skill 的工作全搶走；
- skill 引用的 `references/guide.md` 根本沒提交，或指向 `C:\Users\某人\tools\x.py`。

Claude Code 內建的 `/skill-doctor` 告訴你每個 skill **花多少 token、被用了幾次**。
skillclash 回答另一個問題：**這些 skill 放在一起會不會互相干擾？** 而且可以在你安裝之前就先回答。

## 安裝

```bash
pip install git+https://github.com/mokeytimting/skillclash
```

需要 Python 3.11 以上，以及 `git`（用於 `gh:` 來源）。唯一的相依套件是 PyYAML。

## 使用方式

```bash
skillclash audit                                  # 檢查這台電腦上已安裝的 skill
skillclash preflight gh:affaan-m/ECC              # 安裝這個包之前，先看會跟誰衝突
skillclash compare gh:obra/superpowers gh:addyosmani/agent-skills   # 比較兩個包，不看本機
skillclash scan local ./my-skills --format html -o report.html      # 任意組合來源
skillclash explain OVERLAP                        # 查詢規則的意思
```

| 來源寫法 | 意義 |
|---|---|
| `local` | `~/.claude/skills`、目前專案的 `.claude/skills`、已啟用的 plugin，以及 `CLAUDE.md` |
| `gh:owner/repo[@ref][#plugin]` | GitHub repo，淺層 clone 到快取；`#plugin` 只取 marketplace 中的某個 plugin |
| `./路徑` | 本機資料夾（單一 skill、plugin 或 marketplace repo 皆可） |

常用參數：`--format text|json|html`、`--lang en|zh-TW`、`--min-severity info`、`--fail-on warn`、`--offline`、
`--refresh`、`--intra`（同一個包內的 skill 也互相比較）。完整說明請用 `skillclash <指令> -h`。

repo 只會被讀取，絕不執行。skillclash 透過 `marketplace.json`／`plugin.json` 推算實際會安裝哪些 skill，
所以很多 repo 為 Cursor、Kiro、Gemini 或翻譯文件準備的鏡像副本不會被重複計算。

## 檢查項目

| 規則 | 嚴重度 | 找什麼 |
|---|---|---|
| `NAME-CLASH` | 🔴 / 🟠 | 兩處同名：一份悄悄遮蔽另一份，或兩份都出現在清單上讓模型猜 |
| `OVERLAP` | 🟠 / 🟡 | 描述太像，會搶同一類請求（TF‑IDF，支援中文） |
| `DUP-CONTENT` | 🟠 | 同一個 skill 換了名字裝了兩次 |
| `GREEDY` | 🟠 | 描述宣稱的範圍遠超出自身領域（「use on ANY task」） |
| `RULE-CONFLICT` | 🟠 | 同一情境下相反的指示，由 LLM 確認（`--judge`） |
| `ROUTE-STEAL` / `ROUTE-DEAD` | 🟠 / 🟡 | 用 LLM 模擬路由實測（`--route`） |
| `REF-BROKEN` / `REF-ABSPATH` | 🟠 / 🟡 | 附帶檔案不存在；只存在作者電腦上的路徑 |
| `SPEC-*` | 🔴 – 🟡 | 違反 Agent Skills 規格的 frontmatter |

細節、範例與修正方式：[docs/rules.md](docs/rules.md)。

## 在 11 個熱門 skill 包中發現了什麼

我們掃描了 anthropics/skills、obra/superpowers、mattpocock/skills、addyosmani/agent-skills、alirezarezvani/claude-skills、
affaan-m/ECC、garrytan/gstack、pbakaus/impeccable、DietrichGebert/ponytail、JuliusBrussee/caveman 和 thedotmack/claude-mem，
共 114 個可安裝的 plugin、871 個 skill：

- **22 個跨包同名衝突。** `handoff` 出現在四個地方；`test-driven-development` 同時存在於 superpowers 和 agent-skills。
  多數「副本」其實是改寫版，不是原封不動的複製，有好幾個開頭寫著「Derived from Matt Pocock's …」。
- **15 組觸發重疊（警告）**，例如 `canary` ↔ `ecc:canary-watch`、`senior-devops` ↔ `deployment-patterns`、
  `careful` ↔ `safety-guard`。
- **4 個過度貪婪的描述**，例如「Use on ANY coding task」和「Stop and check this skill before finishing any reply」。
- **22 個附帶檔案引用失效。**

完整清單見 [docs/corpus-summary.md](docs/corpus-summary.md)（可用 `python tools/corpus.py summary` 重新產生）。

## 選用：LLM 檢查

靜態檢查免費且完全離線。另外有兩項需要手動開啟的 LLM 檢查：執行前都會先列出預估呼叫次數並詢問是否繼續
（CI 中可用 `--yes` 略過），回應會快取在本機，總呼叫數可用 `--max-calls` 限制。

| 參數 | 功能 | 預設後端 | 金鑰 |
|---|---|---|---|
| `--judge` | 把觸發重疊與規則矛盾的候選交給 LLM 逐一確認或排除，LLM 回傳的引用會再與原始檔案比對 | DeepSeek（任何 OpenAI 相容 API） | `DEEPSEEK_API_KEY`，或 `SKILLCLASH_OPENAI_API_KEY` + `SKILLCLASH_OPENAI_BASE_URL` |
| `--route` | 為每個 skill 產生測試請求，問 Claude 會載入哪個 skill，產生混淆矩陣 | Claude（`claude-sonnet-5-5`） | `ANTHROPIC_API_KEY` |

模型可用 `SKILLCLASH_JUDGE_MODEL`、`SKILLCLASH_ROUTE_MODEL` 更換。

## 在 Claude Code 中使用

```text
/plugin marketplace add mokeytimting/skillclash
/plugin install skillclash@skillclash
```

這個 plugin 會加入一個 `skillclash` skill（直接問「我的 skill 有沒有衝突？」），以及一個工作階段啟動 hook：
當已安裝的 skill 有變動且出現警告時，會顯示一行提醒。兩者都需要 CLI 在 `PATH` 上。

## 用在 CI

```yaml
- run: pip install git+https://github.com/mokeytimting/skillclash
- run: skillclash scan ./skills --fail-on warn
```

結束碼：`0` 沒有達到 `--fail-on` 等級的結果；`1` 有；`2` 參數錯誤；`3` 所有來源都讀取失敗。

## 忽略某個結果

在專案中加入 `.skillclash.toml`（或 `~/.config/skillclash/config.toml`）：

```toml
[[ignore]]
rule = "NAME-CLASH"
skills = ["my-skill"]
reason = "刻意保留兩份"
```

也可以寫在 SKILL.md 裡：`<!-- skillclash-ignore: OVERLAP with=pdf reason="用途不同" -->`。
沒有作用的忽略規則會被回報，避免白名單越積越多。更多寫法見 [docs/rules.md](docs/rules.md#suppressing-findings--抑制結果)。

## 準確度與限制

- 門檻是在上述 11 個包上人工標註後校正的（[calibration.md](docs/calibration.md)）。樣本不大，且只有一位標註者，
  仍可能有誤報，歡迎回報。
- 靜態的規則矛盾偵測在抽查的 15 個候選中全部判錯，所以只用來提供 `--judge` 候選。
- `--judge` 和 `--route` 目前只用假後端測試過，尚未對真實模型做效果評估。
- 報告中不會出現你的本機路徑（改以 `~/…`、`gh:owner/repo/…` 顯示），也不會出現 API 金鑰。

## 開發

```bash
pip install -e ".[dev]"
pytest                 # 單元測試，不需網路
pytest -m network      # 對真實 skill 包的檢查（會 clone repo）
ruff check .
```

`tools/corpus.py` 可重新產生語料摘要，並重算校正標註的精確率。

## 授權

MIT
