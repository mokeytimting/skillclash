"""Corpus utilities used to calibrate thresholds and to produce docs/corpus-summary.md.

    python tools/corpus.py sample  -> tests/fixtures/calibration_candidates.jsonl (for labeling)
    python tools/corpus.py score   -> precision per band from tests/fixtures/calibration_labels.jsonl
    python tools/corpus.py summary -> docs/corpus-summary.md (+ corpus-report.html with --html)

Uses cached clones; set SKILLCLASH_CACHE_DIR to reuse an existing cache.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from skillclash.analyzers import run_analyzers  # noqa: E402
from skillclash.analyzers.greedy import score_greedy_description  # noqa: E402
from skillclash.model import ScanResult  # noqa: E402
from skillclash.sources import resolve_sources  # noqa: E402

CORPUS = [
    "gh:anthropics/skills", "gh:obra/superpowers", "gh:mattpocock/skills",
    "gh:addyosmani/agent-skills", "gh:alirezarezvani/claude-skills",
    "gh:affaan-m/ECC", "gh:garrytan/gstack", "gh:pbakaus/impeccable",
    "gh:DietrichGebert/ponytail", "gh:JuliusBrussee/caveman", "gh:thedotmack/claude-mem",
]
CANDIDATES = ROOT / "tests" / "fixtures" / "calibration_candidates.jsonl"
LABELS = ROOT / "tests" / "fixtures" / "calibration_labels.jsonl"


def load(offline: bool):
    units, stats = resolve_sources(CORPUS, offline=offline)
    if stats["fetch_errors"]:
        print("fetch errors:", stats["fetch_errors"], file=sys.stderr)
    return units


def band(c: float) -> str:
    return ">=0.45" if c >= 0.45 else "0.30-0.45" if c >= 0.30 else "0.20-0.30"


def gband(s: float) -> str:
    return ">=5" if s >= 5 else "3-4.9" if s >= 3 else "1-2.9"


def cmd_sample(offline: bool) -> None:
    units = load(offline)
    cfg = {"thresholds": {"overlap_info": 0.20, "overlap_warn": 0.45}}
    findings, _ = run_analyzers(units, cfg, lang="en")
    rng = random.Random(42)
    rows = []

    by_band = collections.defaultdict(list)
    for f in findings:
        if f.rule == "OVERLAP":
            by_band[band(f.evidence["cosine"])].append(f)
    for b in (">=0.45", "0.30-0.45", "0.20-0.30"):
        pool = sorted(by_band[b], key=lambda f: f.fingerprint)
        for f in rng.sample(pool, min(20, len(pool))):
            rows.append({
                "type": "overlap", "band": b, "cosine": f.evidence["cosine"],
                "skill_a": f.skills[0].qualified_name, "skill_b": f.skills[1].qualified_name,
                "desc_a": f.evidence["desc_a"][:500], "desc_b": f.evidence["desc_b"][:500],
                "shared_terms": f.evidence["shared_terms"],
            })

    scored = []
    for u in units:
        for sk in u.skills:
            if sk.model_invocable and sk.description:
                s, m = score_greedy_description(sk.description, "en")
                if s >= 1:
                    scored.append((s, sk, [x["phrase"] for x in m]))
    by_g = collections.defaultdict(list)
    for item in scored:
        by_g[gband(item[0])].append(item)
    for b, n in ((">=5", 10), ("3-4.9", 15), ("1-2.9", 15)):
        pool = sorted(by_g[b], key=lambda x: x[1].id)
        for s, sk, phrases in rng.sample(pool, min(n, len(pool))):
            rows.append({
                "type": "greedy", "band": b, "score": s, "skill": sk.qualified_name,
                "matches": phrases, "description": sk.description[:700],
            })

    CANDIDATES.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} candidates to {CANDIDATES}")
    print("overlap pool sizes:", {k: len(v) for k, v in by_band.items()})
    print("greedy pool sizes:", {k: len(v) for k, v in by_g.items()})


def cmd_score() -> None:
    rows = [json.loads(x) for x in LABELS.read_text(encoding="utf-8").splitlines() if x.strip()]
    print("OVERLAP (label: clash = would compete for the same request)")
    for b in (">=0.45", "0.30-0.45", "0.20-0.30"):
        rs = [r for r in rows if r["type"] == "overlap" and r["band"] == b]
        c = collections.Counter(r["label"] for r in rs)
        if rs:
            print(f"  {b:10} n={len(rs):2}  {dict(c)}  clash-precision={c['clash'] / len(rs):.2f}"
                  f"  clash+related={(c['clash'] + c['related']) / len(rs):.2f}")
    print("GREEDY (label: greedy = genuinely over-broad)")
    for b in (">=5", "3-4.9", "1-2.9"):
        rs = [r for r in rows if r["type"] == "greedy" and r["band"] == b]
        c = collections.Counter(r["label"] for r in rs)
        if rs:
            print(f"  {b:6} n={len(rs):2}  {dict(c)}  precision={c['greedy'] / len(rs):.2f}")


def cmd_summary(offline: bool, html: bool) -> None:
    from skillclash.report.html import generate_html_report

    units = load(offline)
    t0 = time.perf_counter()
    findings, stats = run_analyzers(units, {}, lang="en")
    elapsed = time.perf_counter() - t0
    skills = sum(len(u.skills) for u in units)
    by_rule = collections.Counter((f.rule, f.severity.value) for f in findings)

    lines = [
        "# Corpus scan / 語料掃描",
        "",
        f"{len(CORPUS)} public skill packs, {len(units)} install units, {skills} skills. "
        f"Static analysis (L0–L3) took {elapsed:.1f} s. Default thresholds, no LLM.",
        "",
        "Regenerate: `python tools/corpus.py summary`",
        "",
        "| Rule | Severity | Count |",
        "|---|---|---|",
    ]
    for (rule, sev), n in sorted(by_rule.items(), key=lambda kv: (["error", "warn", "info"].index(kv[0][1]), -kv[1])):
        lines.append(f"| `{rule}` | {sev} | {n} |")

    def pair(f):
        return " ↔ ".join(f"`{s.qualified_name}`" for s in f.skills)

    lines += ["", "## Name clashes across packs", ""]
    for f in sorted((f for f in findings if f.rule == "NAME-CLASH"), key=lambda f: f.skills[0].name):
        lines.append(f"- {pair(f)} — {f.evidence['variant']} (similarity {f.evidence['jaccard']})")
    lines += ["", "## Strongest trigger overlaps", ""]
    for f in sorted((f for f in findings if f.rule == "OVERLAP"), key=lambda f: -f.evidence["cosine"])[:15]:
        lines.append(f"- {pair(f)} — cosine {f.evidence['cosine']:.2f}; shared: {', '.join(f.evidence['shared_terms'][:5])}")
    lines += ["", "## Greedy descriptions", ""]
    for f in sorted((f for f in findings if f.rule == "GREEDY"), key=lambda f: -f.evidence["score"]):
        phrases = ", ".join(m["phrase"] for m in f.evidence["matches"])
        lines.append(f"- `{f.skills[0].qualified_name}` — score {f.evidence['score']:.0f}: {phrases}")
    lines += [
        "",
        "Static RULE-CONFLICT candidates are not listed: on this corpus 0 of 15 sampled candidates were",
        "real contradictions (see docs/calibration.md). Use `--judge` to have an LLM confirm them.",
        "",
    ]

    (ROOT / "docs" / "corpus-summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:8 + len(by_rule) + 2]))
    if html:
        report = generate_html_report(ScanResult(units, findings, stats, {}), lang="en")
        (ROOT / "docs" / "corpus-report.html").write_text(report, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["sample", "score", "summary"])
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--html", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.command == "sample":
        cmd_sample(a.offline)
    elif a.command == "score":
        cmd_score()
    else:
        cmd_summary(a.offline, a.html)


if __name__ == "__main__":
    main()
