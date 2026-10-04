# skillclash

**Find the agent skills that fight each other.** skillclash checks Claude Code / [Agent Skills](https://agentskills.io)
for name clashes, overlapping triggers, contradicting instructions and broken references — on your machine, or
in a skill pack *before* you install it.

[繁體中文](README.zh-TW.md) · [Rules](docs/rules.md) · [How the thresholds were set](docs/calibration.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

```text
$ skillclash compare gh:obra/superpowers gh:addyosmani/agent-skills gh:mattpocock/skills gh:thedotmack/claude-mem

🟠 NAME-CLASH  Skill name clash: test-driven-development
   ├ plugin:addy-agent-skills/agent-skills  gh:addyosmani/agent-skills/skills/test-driven-development/SKILL.md:1
   └ plugin:superpowers-dev/superpowers     gh:obra/superpowers/skills/test-driven-development/SKILL.md:1
   Listed twice: test-driven-development — at least one copy is a namespaced plugin skill, so both appear
   in the listing; the model has to guess and the listing cost is paid twice. Content: different (similarity 0.00)
   "Drives development with tests using the red-green-refactor loop. Use when implementing any logic,..."
   "Use when implementing any feature or bugfix, before writing implementation code"
   Fix: Keep a single copy of test-driven-development, or mark the duplicate as intentional ...
```

## Why

Skill packs are getting big — single repos ship 300+ skills — and people install several at once. Then:

- two skills answer to the same request, and the model picks one at random;
- a skill with the same name as yours silently replaces it (personal beats project);
- one skill says "always run the tests", another says "never run tests yourself";
- a description that says "use on ANY coding task" hijacks everything else;
- a skill points at `references/guide.md` that was never committed, or at `C:\Users\someone\tools\x.py`.

Claude Code's built-in `/skill-doctor` tells you what each skill **costs** and how often it is **used**.
skillclash answers the other question: **do these skills get in each other's way?** — and it can answer it for
a repo you have not installed yet.

## Install

```bash
pip install git+https://github.com/mokeytimting/skillclash
```

Requires Python 3.11+ and `git` (for `gh:` sources). The only dependency is PyYAML.

## Usage

```bash
skillclash audit                                  # skills installed on this machine
skillclash preflight gh:affaan-m/ECC              # what would installing this pack clash with?
skillclash compare gh:obra/superpowers gh:addyosmani/agent-skills   # two packs, ignoring your machine
skillclash scan local ./my-skills --format html -o report.html      # any mix of sources
skillclash explain OVERLAP                        # what a rule means
```

| Source | Meaning |
|---|---|
| `local` | `~/.claude/skills`, the current project's `.claude/skills`, enabled plugins, and `CLAUDE.md` files |
| `gh:owner/repo[@ref][#plugin]` | a GitHub repo, shallow-cloned into a cache; `#plugin` picks one plugin of a marketplace |
| `./path` | a local folder (a skill, a plugin, or a marketplace repo) |

Useful options: `--format text|json|html`, `--lang en|zh-TW`, `--min-severity info`, `--fail-on warn`,
`--offline`, `--refresh`, `--intra` (also compare skills inside the same pack). `skillclash <command> -h` lists all.

Repos are read, never executed: skillclash parses `marketplace.json` / `plugin.json` to find what would actually be
installed, so the copies many repos keep for Cursor, Kiro, Gemini or translated docs are not counted twice.

## What it checks

| Rule | Severity | Finds |
|---|---|---|
| `NAME-CLASH` | 🔴 / 🟠 | Same name in two places: one silently shadows the other, or both are listed and the model must guess |
| `OVERLAP` | 🟠 / 🟡 | Descriptions similar enough that both compete for the same requests (TF‑IDF, CJK-aware) |
| `DUP-CONTENT` | 🟠 | The same skill installed twice under different names |
| `GREEDY` | 🟠 | Descriptions that claim far more than their domain ("use on ANY task") |
| `RULE-CONFLICT` | 🟠 | Opposite instructions for the same situation — confirmed by an LLM (`--judge`) |
| `ROUTE-STEAL` / `ROUTE-DEAD` | 🟠 / 🟡 | Measured by simulating routing with an LLM (`--route`) |
| `REF-BROKEN` / `REF-ABSPATH` | 🟠 / 🟡 | Missing bundled files; paths that only exist on the author's machine |
| `SPEC-*` | 🔴 – 🟡 | Frontmatter problems from the Agent Skills spec |

Details, examples and fixes: [docs/rules.md](docs/rules.md).

## What it found in 11 popular packs

We ran it on anthropics/skills, obra/superpowers, mattpocock/skills, addyosmani/agent-skills,
alirezarezvani/claude-skills, affaan-m/ECC, garrytan/gstack, pbakaus/impeccable, DietrichGebert/ponytail,
JuliusBrussee/caveman and thedotmack/claude-mem — 871 skills in 114 installable plugins:

- **22 name clashes across packs.** `handoff` exists in four places; `test-driven-development` in both superpowers and
  agent-skills. Most "copies" are rewrites, not verbatim: several start with "Derived from Matt Pocock's …".
- **15 trigger overlaps (warn)**, e.g. `canary` ↔ `ecc:canary-watch`, `senior-devops` ↔ `deployment-patterns`,
  `careful` ↔ `safety-guard`.
- **4 greedy descriptions**, e.g. "Use on ANY coding task" and "Stop and check this skill before finishing any reply".
- **22 broken bundled-file references.**

Full list: [docs/corpus-summary.md](docs/corpus-summary.md) (regenerate with `python tools/corpus.py summary`).

## Optional: LLM checks

Static checks are free and offline. Two opt-in checks call an LLM; both print the expected number of calls and ask
before spending (`--yes` to skip in CI), cache responses on disk, and cap total calls with `--max-calls`.

| Flag | What it does | Default backend | Keys |
|---|---|---|---|
| `--judge` | Sends OVERLAP and rule-conflict candidates to an LLM, which confirms or dismisses each one. Quotes it returns are checked against the actual files. | DeepSeek (any OpenAI-compatible API) | `DEEPSEEK_API_KEY` or `SKILLCLASH_OPENAI_API_KEY` + `SKILLCLASH_OPENAI_BASE_URL` |
| `--route` | Generates test requests for each skill, asks Claude which skill it would load, and builds a confusion matrix. | Claude (`claude-sonnet-5-5`) | `ANTHROPIC_API_KEY` |

Models can be changed with `SKILLCLASH_JUDGE_MODEL` and `SKILLCLASH_ROUTE_MODEL`.

## Use it from Claude Code

```text
/plugin marketplace add mokeytimting/skillclash
/plugin install skillclash@skillclash
```

The plugin adds a `skillclash` skill (ask "do my skills conflict?") and a session-start hook that prints one line
when your installed skills changed and now contain warnings. Both need the CLI on your `PATH`.

## In CI

```yaml
- run: pip install git+https://github.com/mokeytimting/skillclash
- run: skillclash scan ./skills --fail-on warn
```

Exit codes: `0` nothing at or above `--fail-on`, `1` findings, `2` usage error, `3` every source failed to load.

## Silencing a finding

Add a `.skillclash.toml` to your project (or `~/.config/skillclash/config.toml`):

```toml
[[ignore]]
rule = "NAME-CLASH"
skills = ["my-skill"]
reason = "I keep both copies on purpose"
```

Or inline in a SKILL.md: `<!-- skillclash-ignore: OVERLAP with=pdf reason="different jobs" -->`.
Unused ignore entries are reported so the list does not rot. More in [docs/rules.md](docs/rules.md#suppressing-findings--抑制結果).

## Accuracy and limits

- Thresholds were calibrated by hand-labeling findings on the 11 packs above ([calibration.md](docs/calibration.md)).
  Samples are small and had one reviewer; expect some false positives, and please report them.
- Static rule-conflict detection was wrong on all 15 sampled candidates, so it only feeds `--judge`.
- `--judge` and `--route` are tested with fake backends; results against live models have not been benchmarked yet.
- Reports never contain your local paths (`~/…` and `gh:owner/repo/…` instead) and never contain API keys.

## Development

```bash
pip install -e ".[dev]"
pytest                 # unit tests, offline
pytest -m network      # checks against the real packs (clones them)
ruff check .
```

`tools/corpus.py` regenerates the corpus summary and re-scores the calibration labels.

## License

MIT
