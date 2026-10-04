from __future__ import annotations

import re
from typing import Any

from skillclash.analyzers.similarity import (
    MinHashLSH,
    compute_minhash,
    extract_shingles,
    jaccard_similarity,
)
from skillclash.i18n import t
from skillclash.model import Finding, InstallUnit, Severity, Skill, UnitKind
from skillclash.paths import make_ref, same_pack, units_by_skill


def _version_key(raw: object) -> tuple[int, ...] | None:
    nums = re.findall(r"\d+", str(raw))
    return tuple(int(n) for n in nums) if nums else None


def _declared_version(skill: Skill) -> object:
    fm = skill.frontmatter
    meta = fm.get("metadata")
    return fm.get("version") or (meta.get("version") if isinstance(meta, dict) else None)


def compare_skill_versions(skill_a: Skill, skill_b: Skill) -> str | None:
    """Return the unit id whose copy declares the higher version, or None if unknown.

    File timestamps are not used: for cloned repos they only reflect clone time.
    """
    ka = _version_key(_declared_version(skill_a) or "")
    kb = _version_key(_declared_version(skill_b) or "")
    if ka is None or kb is None or ka == kb:
        return None
    return skill_a.unit_id if ka > kb else skill_b.unit_id


def _downgrade(sev: Severity) -> Severity:
    return Severity.WARN if sev == Severity.ERROR else Severity.INFO


def check_duplicates(
    units: list[InstallUnit],
    *,
    intra: bool = False,
    lang: str = "zh-TW",
) -> tuple[list[Finding], set[tuple[str, str]]]:
    """Analyze L1 duplicate skills and name clashes.

    Pairs from the same pack (one repo / marketplace) are skipped unless ``intra`` is set:
    a user picks plugins from a marketplace, so the author's own overlaps are not install-time clashes.

    Returns:
        (findings, name_clash_pairs)
    """
    findings: list[Finding] = []
    name_clash_pairs: set[tuple[str, str]] = set()

    unit_of = units_by_skill(units)
    all_skills: list[Skill] = [
        sk for u in units if u.kind != UnitKind.MEMORY for sk in u.skills
    ]

    # 1. NAME-CLASH: same (case-insensitive) name in different units
    by_name: dict[str, list[Skill]] = {}
    for sk in all_skills:
        by_name.setdefault(sk.name.lower(), []).append(sk)

    shingle_cache: dict[str, set[str]] = {}

    def shingles(sk: Skill) -> set[str]:
        if sk.id not in shingle_cache:
            shingle_cache[sk.id] = extract_shingles(sk.body)
        return shingle_cache[sk.id]

    for skills in by_name.values():
        if len(skills) < 2:
            continue
        for i in range(len(skills)):
            for j in range(i + 1, len(skills)):
                sa, sb = skills[i], skills[j]
                if sa.unit_id == sb.unit_id:
                    continue  # reported as a unit warning by the source resolver
                unit_a, unit_b = unit_of[sa.id], unit_of[sb.id]
                intra_pack = same_pack(unit_a, unit_b)
                if intra_pack and not intra:
                    continue
                if sa.id > sb.id:
                    sa, sb, unit_a, unit_b = sb, sa, unit_b, unit_a
                name_clash_pairs.add((sa.id, sb.id))

                namespaced = unit_a.namespaced or unit_b.namespaced
                sev = Severity.WARN if namespaced else Severity.ERROR
                if intra_pack:
                    sev = _downgrade(sev)

                jaccard = jaccard_similarity(shingles(sa), shingles(sb))
                variant = "identical" if jaccard >= 0.98 else "drifted" if jaccard >= 0.5 else "different"
                newer = compare_skill_versions(sa, sb) if variant == "drifted" else None

                if namespaced:
                    msg = t("name_clash.both", lang, name=sa.name, variant=variant, jaccard=jaccard)
                elif unit_a.priority == unit_b.priority:
                    msg = t("name_clash.shadow_tie", lang, name=sa.name, variant=variant, jaccard=jaccard)
                else:
                    winner = unit_a if unit_a.priority > unit_b.priority else unit_b
                    msg = t("name_clash.shadow", lang, name=sa.name, winner=winner.label,
                            variant=variant, jaccard=jaccard)
                if newer:
                    msg += t("name_clash.newer", lang, unit=newer)

                evidence: dict[str, Any] = {
                    "variant": variant,
                    "jaccard": round(jaccard, 3),
                    "newer": newer,
                    "shadowing": not namespaced,
                    "same_pack": intra_pack,
                }
                findings.append(
                    Finding(
                        rule="NAME-CLASH",
                        severity=sev,
                        title=f"{t('rule.NAME-CLASH.title', lang)}: {sa.name}",
                        message=msg,
                        skills=[make_ref(sa), make_ref(sb)],
                        evidence=evidence,
                        confidence=1.0,
                        source="static",
                        fix=t("name_clash.fix", lang, name=sa.name),
                    )
                )

    # 2. DUP-CONTENT: different names, body Jaccard >= 0.90
    skill_by_id = {sk.id: sk for sk in all_skills}
    sig_cache: dict[str, list[int]] = {}
    lsh = MinHashLSH()
    for sk in all_skills:
        sig = compute_minhash(shingles(sk))
        sig_cache[sk.id] = sig
        lsh.insert(sk.id, sig)

    checked: set[tuple[str, str]] = set()
    for sa in all_skills:
        if not shingle_cache[sa.id]:
            continue
        for cid in lsh.query_candidates(sig_cache[sa.id]):
            if cid <= sa.id or (sa.id, cid) in checked:
                continue
            checked.add((sa.id, cid))
            sb = skill_by_id[cid]
            if sa.unit_id == sb.unit_id or sa.name.lower() == sb.name.lower():
                continue
            intra_pack = same_pack(unit_of[sa.id], unit_of[sb.id])
            if intra_pack and not intra:
                continue
            jaccard = jaccard_similarity(shingle_cache[sa.id], shingle_cache[sb.id])
            if jaccard < 0.90:
                continue
            findings.append(
                Finding(
                    rule="DUP-CONTENT",
                    severity=Severity.INFO if intra_pack else Severity.WARN,
                    title=f"{t('rule.DUP-CONTENT.title', lang)}: {sa.name} ↔ {sb.name}",
                    message=t("dup_content.msg", lang, jaccard=jaccard),
                    skills=[make_ref(sa), make_ref(sb)],
                    evidence={"jaccard": round(jaccard, 3), "same_pack": intra_pack},
                    confidence=1.0,
                    source="static",
                    fix=t("dup_content.fix", lang, a=sa.qualified_name, b=sb.qualified_name),
                )
            )

    return findings, name_clash_pairs
