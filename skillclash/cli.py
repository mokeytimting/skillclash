from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Sequence

import skillclash
from skillclash.analyzers import run_analyzers
from skillclash.config import load_config
from skillclash.i18n import LANGS, MESSAGES, default_lang
from skillclash.model import InstallUnit, ScanResult, Severity
from skillclash.report.json_out import generate_json_str
from skillclash.report.text import format_text_report
from skillclash.sources import resolve_sources

SEVERITY_RANK = {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}
# Options echoed into the JSON report; paths and other machine-specific values are left out.
REPORTED_ARGS = (
    "command", "sources", "format", "lang", "min_severity", "fail_on", "offline", "intra",
    "rule_candidates", "judge", "judge_limit", "route", "route_skills", "route_prompts", "route_repeats", "max_calls",
)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add shared options to a parser or subparser."""
    parser.add_argument("--format", choices=["text", "json", "html"], default="text",
                        help="output format (default: text)")
    parser.add_argument("-o", "--output", metavar="PATH",
                        help="write the report to PATH (html defaults to skillclash-report.html)")
    parser.add_argument("--lang", choices=list(LANGS), default=None,
                        help="report language (default: from SKILLCLASH_LANG or the system locale)")
    parser.add_argument("--min-severity", choices=["info", "warn", "error"], default="warn",
                        help="lowest severity shown in text output (default: warn)")
    parser.add_argument("--fail-on", choices=["error", "warn", "never"], default="error",
                        help="lowest severity that makes the exit code 1 (default: error)")
    parser.add_argument("--config", metavar="PATH", help="path to a .skillclash.toml file")
    parser.add_argument("--offline", action="store_true", help="never touch the network; use cached clones only")
    parser.add_argument("--refresh", action="store_true", help="re-fetch cached GitHub sources")
    parser.add_argument("--no-follow-external", action="store_true",
                        help="do not clone other repos referenced by a marketplace")
    parser.add_argument("--intra", action="store_true",
                        help="also compare skills that ship in the same repo/marketplace")
    parser.add_argument("--judge", action="store_true", help="confirm candidates with an LLM (needs an API key)")
    parser.add_argument("--judge-limit", type=int, default=50, help="max candidates sent to --judge (default: 50)")
    parser.add_argument("--route", action="store_true", help="run the LLM routing simulation (needs an API key)")
    parser.add_argument("--route-skills", type=int, default=40, help="max skills in the simulation (default: 40)")
    parser.add_argument("--route-prompts", type=int, default=4, help="test prompts per skill (default: 4)")
    parser.add_argument("--route-repeats", type=int, default=3, help="votes per prompt (default: 3)")
    parser.add_argument("--max-calls", type=int, default=300, help="total LLM call budget (default: 300)")
    parser.add_argument("--yes", action="store_true", help="skip the LLM cost confirmation prompt")
    parser.add_argument("--no-llm-cache", action="store_true", help="do not reuse cached LLM responses")
    parser.add_argument("--show-suppressed", action="store_true", help="include suppressed findings in the report")
    parser.add_argument("--rule-candidates", action="store_true",
                        help="also list unconfirmed RULE-CONFLICT candidates (noisy without --judge)")
    parser.add_argument("--changed-only", action="store_true",
                        help="exit silently when the installed skill set has not changed since the last run")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print a one-line summary of problems")


def build_parser() -> argparse.ArgumentParser:
    """Build root CLI parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="skillclash",
        description="Find conflicts, overlaps and duplicates between AI agent skills (Claude Code / Agent Skills).",
    )
    parser.add_argument("--version", action="version", version=f"skillclash {skillclash.__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_audit = sub.add_parser("audit", help="check the skills installed on this machine")
    p_audit.add_argument("--project", metavar="PATH", help="project root (default: the current git repo)")
    add_common_args(p_audit)

    p_pre = sub.add_parser("preflight", help="check what installing SOURCE would clash with")
    p_pre.add_argument("sources", nargs="+", metavar="SOURCE", help="e.g. gh:owner/repo or a local folder")
    p_pre.add_argument("--project", metavar="PATH", help="project root (default: the current git repo)")
    add_common_args(p_pre)

    p_cmp = sub.add_parser("compare", help="compare two or more sources, ignoring this machine")
    p_cmp.add_argument("sources", nargs="+", metavar="SOURCE")
    add_common_args(p_cmp)

    p_scan = sub.add_parser("scan", help="analyze any combination of sources (including 'local')")
    p_scan.add_argument("sources", nargs="+", metavar="SOURCE")
    add_common_args(p_scan)

    p_explain = sub.add_parser("explain", help="explain a rule code, e.g. NAME-CLASH")
    p_explain.add_argument("rule", metavar="RULE_CODE")
    p_explain.add_argument("--lang", choices=list(LANGS), default=None)

    p_eco = sub.add_parser("ecosystem", help="build the static ecosystem conflict map")
    eco_sub = p_eco.add_subparsers(dest="eco_command", metavar="SUBCOMMAND")
    p_build = eco_sub.add_parser("build", help="build the site")
    p_build.add_argument("--packs", default="ecosystem/packs.toml", help="packs list (TOML)")
    p_build.add_argument("--out", default="site", help="output directory")
    p_build.add_argument("--offline", action="store_true", help="use cached clones only")

    return parser


def handle_explain(rule_code: str, lang: str) -> int:
    code = rule_code.upper()
    title = MESSAGES.get(f"rule.{code}.title")
    if not title:
        print(f"Unknown rule code: {rule_code}", file=sys.stderr)
        return 2
    desc = MESSAGES.get(f"rule.{code}.desc", {})
    print(f"[{code}] {title.get(lang) or title['en']}")
    if desc:
        print(desc.get(lang) or desc["en"])
    print(f"\n{skillclash.REPO_URL}/blob/main/docs/rules.md#{code.lower()}")
    return 0


def _skill_fingerprint(units: list[InstallUnit]) -> str:
    parts = []
    for u in units:
        for s in u.skills:
            try:
                mtime = s.path.stat().st_mtime
            except OSError:
                mtime = 0
            parts.append(f"{s.id}:{s.path}:{mtime}")
    return hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()


def _unchanged_since_last_run(units: list[InstallUnit]) -> bool:
    from skillclash.cache import get_cache_root

    fp_file = get_cache_root() / "last_scan_fingerprint.txt"
    current = _skill_fingerprint(units)
    try:
        if fp_file.is_file() and fp_file.read_text(encoding="utf-8").strip() == current:
            return True
        fp_file.write_text(current, encoding="utf-8")
    except OSError:
        pass
    return False


def _confirm(prompt: str, args: argparse.Namespace) -> bool | None:
    """True to proceed, False if declined, None if confirmation is impossible (non-TTY without --yes)."""
    if args.yes:
        return True
    if not sys.stdin.isatty():
        return None
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def execute_pipeline(
    sources: list[str],
    args: argparse.Namespace,
    new_sources: list[str] | None = None,
) -> int:
    """Run the scan. With ``new_sources`` (preflight) only findings touching them are kept."""
    lang = args.lang
    config, _ = load_config(args.config)
    extra_excludes = config.get("sources", {}).get("exclude_dirs_extra", [])
    resolve_kwargs: dict[str, Any] = dict(
        offline=args.offline,
        refresh=args.refresh,
        no_follow_external=args.no_follow_external,
        project_path=getattr(args, "project", None),
        extra_excludes=extra_excludes,
    )

    units, stats = resolve_sources(sources, **resolve_kwargs)
    new_unit_ids: set[str] = set()
    if new_sources:
        new_units, new_stats = resolve_sources(new_sources, **resolve_kwargs)
        new_unit_ids = {u.id for u in new_units}
        units = [u for u in units if u.id not in new_unit_ids] + new_units
        stats["fetch_errors"] += new_stats["fetch_errors"]
        stats["new_unit_ids"] = sorted(new_unit_ids)

    if args.changed_only and _unchanged_since_last_run(units):
        return 0

    if not units or (
        stats["fetch_errors"] and all(any("SRC-FETCH:" in w for w in u.warnings) for u in units)
    ):
        print("All sources failed to load.", file=sys.stderr)
        for spec, err in stats["fetch_errors"]:
            print(f"  {spec}: {err}", file=sys.stderr)
        return 3

    findings, extra_stats = run_analyzers(
        units, config, lang=lang, intra=args.intra,
        rule_candidates=args.judge or args.rule_candidates,
    )
    stats.update(extra_stats)

    if new_unit_ids:
        findings = [f for f in findings if any(s.unit_id in new_unit_ids for s in f.skills)]

    if args.judge:
        cands = [f for f in findings if f.rule in ("OVERLAP", "RULE-CONFLICT")]
        est_calls = min(len(cands), args.judge_limit, args.max_calls)
        if est_calls:
            ok = _confirm(f"--judge will make about {est_calls} LLM calls (~{est_calls * 1200:,} tokens). Continue?", args)
            if ok is None:
                print("--judge needs --yes when stdin is not a terminal.", file=sys.stderr)
                return 2
            if ok:
                from skillclash.llm.backend import OpenAICompatBackend
                from skillclash.llm.judge import run_judge

                try:
                    backend = OpenAICompatBackend(use_cache=not args.no_llm_cache)
                    findings, dismissed, truncated = run_judge(
                        findings, units, backend,
                        limit=args.judge_limit, max_calls=args.max_calls, lang=lang,
                    )
                    stats["dismissed_by_llm"] = dismissed
                    stats["llm_judge"] = backend.stats
                    stats["judge_truncated"] = truncated
                    if not args.rule_candidates:
                        # Unjudged static candidates stay out of the report
                        findings = [
                            f for f in findings
                            if f.rule != "RULE-CONFLICT" or f.source == "llm"
                        ]
                except Exception as e:  # noqa: BLE001 - report and continue with static results
                    print(f"LLM judge failed: {e}", file=sys.stderr)

    if args.route:
        invocable = sum(1 for u in units for sk in u.skills if sk.model_invocable)
        target = min(invocable, args.route_skills)
        est_calls = min(target * (1 + args.route_prompts * args.route_repeats), args.max_calls)
        if est_calls:
            ok = _confirm(f"--route will make about {est_calls} LLM calls (~{est_calls * 800:,} tokens). Continue?", args)
            if ok is None:
                print("--route needs --yes when stdin is not a terminal.", file=sys.stderr)
                return 2
            if ok:
                from skillclash.llm.backend import AnthropicBackend, OpenAICompatBackend
                from skillclash.llm.route import run_route_simulation

                try:
                    gen_backend = OpenAICompatBackend(use_cache=not args.no_llm_cache)
                    route_backend = (
                        AnthropicBackend(use_cache=not args.no_llm_cache)
                        if os.environ.get("ANTHROPIC_API_KEY")
                        else gen_backend
                    )
                    route_findings, route_stats = run_route_simulation(
                        units, gen_backend, route_backend,
                        overlap_clusters=stats.get("overlap_clusters", []),
                        max_route_skills=args.route_skills,
                        prompts_per_skill=args.route_prompts,
                        repeats=args.route_repeats,
                        max_calls=args.max_calls,
                        lang=lang,
                    )
                    findings.extend(route_findings)
                    stats["route_matrix"] = route_stats
                except Exception as e:  # noqa: BLE001
                    print(f"LLM routing simulation failed: {e}", file=sys.stderr)

    from skillclash.suppress import apply_suppressions

    active, suppressed = apply_suppressions(findings, units, config, lang=lang)
    stats["suppressed_count"] = len(suppressed)
    report_findings = active + suppressed if args.show_suppressed else active

    scan_result = ScanResult(units=units, findings=report_findings, stats=stats, config_used=config)
    min_sev = Severity(args.min_severity)

    if args.changed_only and args.quiet:
        issues = [f for f in active if f.severity in (Severity.ERROR, Severity.WARN)]
        if issues:
            print(
                f"skillclash: {len(issues)} skill conflict(s) or warning(s) among installed skills. "
                "Run `skillclash audit` for details."
            )
        return 0

    if args.format == "json":
        reported = {k: v for k, v in vars(args).items() if k in REPORTED_ARGS}
        out = generate_json_str(scan_result, args=reported)
    elif args.format == "html":
        from skillclash.report.html import generate_html_report

        out = generate_html_report(scan_result, lang=lang)
        args.output = args.output or "skillclash-report.html"
    else:
        out = format_text_report(scan_result, min_severity=min_sev, lang=lang)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        if not args.quiet:
            print(f"Report written to {args.output}")
    else:
        print(out)

    if args.fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[Severity(args.fail_on)]
    return 1 if any(SEVERITY_RANK[f.severity] >= threshold for f in active) else 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI main entry point."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "lang", None) is None and hasattr(args, "lang"):
        args.lang = default_lang()

    if not args.command:
        parser.print_help()
        return 0
    if args.command == "explain":
        return handle_explain(args.rule, args.lang)
    if args.command == "audit":
        return execute_pipeline(["local"], args)
    if args.command == "preflight":
        return execute_pipeline(["local"], args, new_sources=list(args.sources))
    if args.command == "compare":
        if len(args.sources) < 2:
            print("compare needs at least two sources.", file=sys.stderr)
            return 2
        return execute_pipeline(args.sources, args)
    if args.command == "scan":
        return execute_pipeline(args.sources, args)
    if args.command == "ecosystem":
        if args.eco_command == "build":
            from skillclash.ecosystem import build_ecosystem_site

            return build_ecosystem_site(args.packs, args.out, offline=args.offline)
        parser.parse_args(["ecosystem", "--help"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
