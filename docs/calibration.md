# Threshold calibration / 門檻校正

All default thresholds come from manually labeling findings on the 11-pack corpus listed in
[corpus-summary.md](corpus-summary.md). Labels live in
[`tests/fixtures/calibration_labels.jsonl`](../tests/fixtures/calibration_labels.jsonl); re-score them with
`python tools/corpus.py score`.

> 所有預設門檻都來自對 11 個公開 skill 包的人工標註。標註檔在
> `tests/fixtures/calibration_labels.jsonl`，可用 `python tools/corpus.py score` 重算。

**Who labeled:** one reviewer (Claude Opus 5.5) reading both descriptions, on 2026-10-04. No second
annotator, so treat the numbers as indicative. Sample sizes are small because the corpus itself is small:
after excluding pairs from the same pack there were only 28 overlap pairs at cosine ≥ 0.20 (26 labeled).

**標註者：** 由一位審查者（Claude Opus 5.5）於 2026-10-04 逐一閱讀兩邊描述後標註，沒有第二位標註者，數字僅供參考。
樣本數小是因為語料本身就小：排除同一包內的配對後，cosine ≥ 0.20 的重疊配對只有 28 組（標註了 26 組）。

## OVERLAP

Label: **clash** = a realistic request would reasonably go to either skill; **related** = same domain,
different job; **unrelated**.

| Cosine | n | clash | related | unrelated | clash precision |
|---|---|---|---|---|---|
| ≥ 0.45 | 2 | 2 | 0 | 0 | 1.00 |
| 0.30–0.45 | 4 | 3 | 1 | 0 | 0.75 |
| 0.25–0.30 | 8 | 7 | 1 | 0 | 0.88 |
| 0.20–0.25 | 12 | 2 | 8 | 2 | 0.17 |

Cumulative clash precision: ≥ 0.30 → 0.83 (n = 6), **≥ 0.25 → 0.86 (n = 14)**, ≥ 0.20 → 0.54 (n = 26).

**Chosen:** `overlap_warn = 0.25` (target ≥ 0.8 met). `overlap_info = 0.20`: only 17% are true clashes, but
83% are at least related, which is what an INFO hint is for. INFO is hidden in text output by default.

Of the 14 labeled clashes, the original defaults flagged 2 as WARN (≥ 0.45) and 5 at all (≥ 0.30);
the new WARN threshold flags 12, e.g. `senior-devops` ↔ `deployment-patterns` (0.30) and
`careful` ↔ `safety-guard` (0.26).

> **選定：** WARN 門檻 0.25（精確率 0.86，達到 ≥ 0.8 的目標）；INFO 門檻 0.20（真正衝突只佔 17%，但 83% 至少相關，適合當提示）。
> 14 組真正的衝突中，原本的門檻只把 2 組列為 WARN、總共只顯示 5 組；新門檻會把其中 12 組列為 WARN。

## GREEDY

Label: **greedy** = the description claims requests well outside its own domain; **normal** = broad but scoped
(e.g. "any time a .pptx file is involved").

| Score | n | greedy | normal | precision |
|---|---|---|---|---|
| ≥ 5 | 2 | 2 | 0 | 1.00 |
| 3–4.9 | 9 | 2 | 7 | 0.22 |
| 1–2.9 | 15 | 2 | 13 | 0.13 |

Scores 3–4.9 were mostly well-scoped descriptions that happen to say "whenever" or list many triggers
(`pptx`, `xlsx`, `docx`). **Chosen:** report only score ≥ 5 (WARN) and drop the INFO level.
Two phrases taken from the true positives were added at weight 3: "use proactively" and
"before finishing any reply". After that change, 4 of the 6 labeled greedy descriptions score ≥ 5 and
none of the 20 labeled normal ones do. Known misses: `claude-api` (3) and `karpathy-coder` (2).

> 分數 3–4.9 大多是範圍明確、只是寫了「whenever」或列很多觸發詞的描述，所以取消 INFO，只報分數 ≥ 5。
> 另外從真實案例補了兩個權重 3 的片語。調整後 6 個真正過寬的描述抓到 4 個，20 個正常描述沒有誤報。

## RULE-CONFLICT (static)

A random sample of 15 of the 151 static candidates contained **no** real contradiction. Typical false
positive: "Recommendation is ALWAYS present" vs "Never present recommendations without evidence".
Keyword polarity cannot tell these apart, so static candidates are no longer reported by default; they are
sent to `--judge` (LLM) or shown with `--rule-candidates`.

> 隨機抽查 151 個靜態候選中的 15 個，**沒有一個**是真的矛盾。關鍵字正反向無法分辨這類句子，
> 因此靜態候選預設不再輸出，只交給 `--judge` 確認，或用 `--rule-candidates` 顯示。

## REF-BROKEN / REF-ABSPATH

Checked by sampling after the parser fixes (fragments like `file.md#anchor` and `file.py:42`, URLs in
inline code, command arguments, `~/` paths and example paths are no longer reported):

- REF-ABSPATH: the remaining hits were all documentation examples (`C:\app`, `D:\project\dist`), so drive
  paths are INFO; only paths inside a user's home directory (`/Users/<name>/`, `C:\Users\<name>\`) are WARN.
- REF-BROKEN: remaining hits are mostly real (links to sibling folders that do not ship with the skill,
  missing `references/*.md`). Bare `scripts/…` paths are resolved against the skill directory only (as the
  spec defines) and only when that folder exists there; this removed examples like `scripts/tool.js` in
  documentation that were matched against an unrelated plugin-level `scripts/` folder.

Before these fixes the same corpus produced 1,240 REF-ABSPATH and 687 REF-BROKEN findings.
