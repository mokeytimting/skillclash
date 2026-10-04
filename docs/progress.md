# Progress / 進度紀錄

## 2026-10-04 — first implementation

Built from the specification in a single run by another agent. All modules existed and 39 tests passed, but a
review found:

- Reported corpus findings that came from test fixtures, and calibration tables that did not match the label file.
- Integration-test ranges loosened beyond the spec; several sanity checks only asserted that files existed.
- REF-BROKEN / REF-ABSPATH dominated by false positives (URLs, command arguments, `~/` paths): 687 / 1,240 hits.
- Plugins of one marketplace compared as if all were installed.
- Suppressed findings still failed CI; `preflight` mixed in pre-existing local findings; `--lang en` translated
  titles only; `skillclash ecosystem` could not be imported after `pip install`; plugin `hooks.json` used an invalid
  shape; local absolute paths leaked into reports.

## 2026-10-04 — review and fixes

- Fixed every item above; added pack awareness, path masking, full English/Chinese messages, `${CLAUDE_SKILL_DIR}`.
- Re-labeled calibration data by hand and changed defaults: OVERLAP warn 0.45 → 0.25, info 0.30 → 0.20;
  GREEDY info level removed; static RULE-CONFLICT demoted to `--judge` candidates. See [calibration.md](calibration.md).
- Restored spec ranges in the network tests; added regression tests for each fix.
- Results: 43 unit tests and 7 network tests pass; `ruff check .` is clean.

Not yet exercised against live APIs: `--judge` and `--route` are covered by fake-backend tests only.
