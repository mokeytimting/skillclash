# Decisions / 設計決定

## Facts the analyzers depend on / 分析所依據的事實

Checked against the official docs on 2026-10-04.

| Fact | Used by | Source |
|---|---|---|
| Same-name skills: enterprise > personal (`~/.claude/skills`) > project (`.claude/skills`); the loser is not used. | NAME-CLASH 🔴 | [Claude Code: skills](https://code.claude.com/docs/en/skills) |
| Plugin skills are namespaced `plugin:skill`, so they do not shadow; both are listed. | NAME-CLASH 🟠 | same |
| `disable-model-invocation: true` keeps the description out of context; only the user can invoke it. | OVERLAP / ROUTE skip such skills | same |
| `${CLAUDE_SKILL_DIR}` and `${CLAUDE_PLUGIN_ROOT}` are substituted in skill content. | REF-BROKEN | same |
| `description` + `when_to_use` are truncated at 1,536 chars in the listing. | OVERLAP text, SPEC-DESC-LONG message | same |
| `name`: 1–64 chars, `a-z0-9-`, no leading/trailing/double hyphen, should match the directory. `description`: 1–1024 chars. | SPEC-* | [Agent Skills spec](https://agentskills.io/specification) |
| Plugin `hooks/hooks.json`: `{"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", ...}]}]}}`; plain stdout of a SessionStart hook is added to Claude's context. | plugin hook | [Claude Code: hooks](https://code.claude.com/docs/en/hooks) |
| Marketplace plugin `source`: relative path, `{"source": "github", "repo": ...}`, `{"source": "url", ...}`; other types (e.g. `npm`) are reported as SRC-UNSUPPORTED. | sources | [marketplace schema](https://json.schemastore.org/claude-code-marketplace.json) |

Not verified: the exact layout of `~/.claude/plugins/installed_plugins.json` across Claude Code versions. The
reader accepts both a dict and a list and skips entries it cannot resolve.

## Design choices / 設計取捨

1. **Install units, not repos.** Many repos mirror every skill into `.cursor/`, `.kiro/`, `.gemini/`, `docs/ja-JP/`.
   Skills are discovered from `marketplace.json` / `plugin.json`; only repos without a manifest are walked, with
   mirror and locale folders excluded. Scanning ECC finds 291 skills; its manifest says 293.
2. **Packs.** Plugins from one repo/marketplace are not compared with each other by default (`--intra` to enable).
   Treating a marketplace as "everything installed" produced dozens of false clashes between a bundle plugin and
   the single-skill plugins carved out of it.
3. **Precision over recall.** Every threshold is calibrated on real packs ([calibration.md](calibration.md)). A rule
   that cannot reach useful precision statically (RULE-CONFLICT) only produces candidates for the LLM judge.
4. **Offline by default, one dependency.** L0–L3 use only the standard library plus PyYAML; no network except
   `git clone` for `gh:` sources. LLM features are opt-in, ask before spending, cache responses, and never log keys.
5. **No local paths in reports.** Paths are shown as `gh:owner/repo/...` or `~/...` so reports can be shared.
6. **Git symlinks on Windows.** Clones use `core.symlinks=false`, and one-line text stubs that point at another
   `SKILL.md` are resolved, so results match across platforms.
