---
name: skillclash
description: Check installed agent skills for name clashes, overlapping triggers, contradicting instructions and broken references. Use when the user asks whether their skills conflict, why the wrong skill keeps being picked, or wants to vet a skill pack (gh:owner/repo) before installing it.
allowed-tools: Bash(skillclash:*) Read
---

# skillclash

Runs the `skillclash` CLI (install with `pip install git+https://github.com/mokeytimting/skillclash`) and explains the results.

## Steps

1. Pick the command:
   - Installed skills: `skillclash audit --format json`
   - Before installing a pack: `skillclash preflight gh:owner/repo --format json`
   - Two packs against each other: `skillclash compare gh:a/b gh:c/d --format json`
2. If the command is missing, tell the user to run `pip install git+https://github.com/mokeytimting/skillclash` and stop.
3. Read the `findings` array. Report at most 10, ordered error → warn → info, in the user's language. For each one give:
   - rule code and severity
   - the skills involved (`qualified_name`) and file paths
   - the quoted evidence
   - the suggested fix
4. If there are no findings, say so in one line.
5. Mention follow-ups only when relevant:
   - `--format html -o report.html` for a browsable report
   - `--judge` / `--route` for LLM confirmation (they need an API key and cost money; ask first)
   - `.skillclash.toml` `[[ignore]]` entries for findings the user says are intentional
