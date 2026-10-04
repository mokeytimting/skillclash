# Corpus scan / 語料掃描

11 public skill packs, 114 install units, 871 skills. Static analysis (L0–L3) took 14.6 s. Default thresholds, no LLM.

Regenerate: `python tools/corpus.py summary`

| Rule | Severity | Count |
|---|---|---|
| `NAME-CLASH` | warn | 22 |
| `REF-BROKEN` | warn | 22 |
| `OVERLAP` | warn | 15 |
| `GREEDY` | warn | 4 |
| `SPEC-DESC-LONG` | warn | 2 |
| `SPEC-NAME-FORMAT` | warn | 2 |
| `SPEC-DESC-SHORT` | info | 13 |
| `OVERLAP` | info | 13 |
| `REF-ABSPATH` | info | 7 |
| `SPEC-NAME-DIR` | info | 3 |

## Name clashes across packs

- `benchmark` ↔ `ecc:benchmark` — different (similarity 0.0)
- `example-skills:brand-guidelines` ↔ `marketing-skills:brand-guidelines` — different (similarity 0.0)
- `caveman:caveman` ↔ `caveman:caveman` — different (similarity 0.025)
- `code-tour:code-tour` ↔ `ecc:code-tour` — different (similarity 0.007)
- `engineering-advanced-skills:codebase-onboarding` ↔ `ecc:codebase-onboarding` — different (similarity 0.0)
- `deep-research:deep-research` ↔ `ecc:deep-research` — different (similarity 0.0)
- `markdown-html-skills:design-system` ↔ `ecc:design-system` — different (similarity 0.0)
- `freeze` ↔ `c-level-agents:freeze` — different (similarity 0.0)
- `grill-me:grill-me` ↔ `mattpocock-skills:grill-me` — different (similarity 0.0)
- `grill-with-docs:grill-with-docs` ↔ `mattpocock-skills:grill-with-docs` — different (similarity 0.0)
- `handoff-engineering:handoff` ↔ `mattpocock-skills:handoff` — different (similarity 0.13)
- `handoff-productivity:handoff` ↔ `mattpocock-skills:handoff` — different (similarity 0.051)
- `mattpocock-skills:handoff` ↔ `claude-mem:handoff` — different (similarity 0.0)
- `handoff-engineering:handoff` ↔ `claude-mem:handoff` — different (similarity 0.0)
- `handoff-productivity:handoff` ↔ `claude-mem:handoff` — different (similarity 0.0)
- `example-skills:internal-comms` ↔ `business-operations-skills:internal-comms` — different (similarity 0.0)
- `business-operations-skills:knowledge-ops` ↔ `ecc:knowledge-ops` — different (similarity 0.0)
- `research-ops-skills:market-research` ↔ `ecc:market-research` — different (similarity 0.0)
- `office-hours` ↔ `c-level-agents:office-hours` — different (similarity 0.0)
- `research-orchestrator:research` ↔ `mattpocock-skills:research` — different (similarity 0.0)
- `retro` ↔ `mattpocock-skills:retro` — different (similarity 0.0)
- `agent-skills:test-driven-development` ↔ `superpowers:test-driven-development` — different (similarity 0.001)

## Strongest trigger overlaps

- `canary` ↔ `ecc:canary-watch` — cosine 0.60; shared: canary, deploy, monitor, watch, post
- `grill-me:grill-me` ↔ `mattpocock-skills:grilling` — cosine 0.60; shared: grill, relentlessly, stres, plan, decision
- `engineering-skills:senior-qa` ↔ `ecc:react-testing` — cosine 0.38; shared: react, test, jest, component, playwright
- `engineering-skills:stripe-integration-expert` ↔ `ecc:customer-billing-ops` — cosine 0.35; shared: bill, subscription, stripe, portal, customer
- `agent-skills:deprecation-and-migration` ↔ `ecc:database-migrations` — cosine 0.31; shared: migration, downtime, renam, column, database
- `apple-hig-expert:apple-hig-expert` ↔ `ecc:liquid-glass-design` — cosine 0.31; shared: glas, liquid, ios, design, ui
- `engineering-skills:senior-devops` ↔ `ecc:deployment-patterns` — cosine 0.30; shared: deployment, cd, containerization, ci, sett
- `marketing-skills:x-twitter-growth` ↔ `ecc:x-api` — cosine 0.29; shared: twitter, thread, tweet, post, content
- `ra-qm-skills:capa-officer` ↔ `ecc:quality-nonconformance` — cosine 0.28; shared: capa, cause, root, analysi, nonconformance
- `ecc:architecture-decision-records` ↔ `mattpocock-skills:domain-modeling` — cosine 0.28; shared: adr, discuss, record, codebase
- `design-review` ↔ `ecc:design-system` — cosine 0.27; shared: visual, design, slop, spac, audit
- `diagram` ↔ `engineering-skills:senior-architect` — cosine 0.26; shared: diagram, mermaid, architecture, make, create
- `careful` ↔ `ecc:safety-guard` — cosine 0.26; shared: careful, destructive, safety, command
- `caveman:migration` ↔ `ecc:database-migrations` — cosine 0.26; shared: migration, reversible, rollback, safe, schema
- `agent-skills:api-and-interface-design` ↔ `engineering-skills:senior-backend` — cosine 0.25; shared: api, backend, rest, graphql, design

## Greedy descriptions

- `llm-cost-optimizer:llm-cost-optimizer` — score 6: use proactively, all requests, whenever
- `ponytail:ponytail` — score 6: use on any, whenever, keyword stuffing (29 separated items)
- `academy-guide:academy-guide` — score 5: before finishing any reply, keyword stuffing (18 separated items)
- `engineering-skills:epic-design` — score 5: use this skill for any, keyword stuffing (27 separated items)

Static RULE-CONFLICT candidates are not listed: on this corpus 0 of 15 sampled candidates were
real contradictions (see docs/calibration.md). Use `--judge` to have an LLM confirm them.
