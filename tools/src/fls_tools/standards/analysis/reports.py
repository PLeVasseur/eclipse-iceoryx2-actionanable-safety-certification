#!/usr/bin/env python3
"""
generate-analysis-reports - Generate Markdown reports from analysis data.

This tool synthesizes three layers of data:
1. Comparison data - Raw diffs (flags, FLS added/removed)
2. Outlier analysis - LLM verdicts and reasoning
3. Human review - Accept/reject decisions

Output:
- combined_report.md - Full report with all sections
- final_report.md - Executive summary
- batch{N}_report.md - Per-batch details
- cross_batch_report.md - Systematic patterns

Usage:
    uv run generate-analysis-reports --standard misra-c --batches 1,2,3
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    get_comparison_data_dir,
    get_reports_dir,
    get_outlier_analysis_dir,
    load_json_file,
    load_outlier_analysis,
    load_review_state,
    recompute_review_summary,
    is_outlier,
    get_active_flags,
    filename_to_guideline,
    FLAG_TYPES,
)


# Priority weights for attention scoring
PRIORITY_WEIGHTS = {
    "specificity_decreased": 10,
    "multi_dimension_outlier": 8,
    "rationale_type_changed": 5,
    "fls_removed": 4,
    "applicability_differs_from_add6": 4,
    "adjusted_category_differs_from_add6": 3,
    "fls_added": 2,
    "batch_pattern_outlier": 2,
    "missing_analysis_summary": 1,
    "missing_search_tools": 1,
}

LLM_VERDICT_PRIORITY = {
    "inappropriate": 10,
    "needs_review": 7,
    "appropriate": 0,
    "n_a": 0,
}


def compute_attention_score(flags: dict, llm_analysis: dict | None, human_review: dict | None) -> int:
    """
    Compute attention priority score for a guideline.
    
    Higher score = needs more attention.
    """
    score = 0
    
    # Score from flags
    for flag, is_set in flags.items():
        if is_set and flag in PRIORITY_WEIGHTS:
            score += PRIORITY_WEIGHTS[flag]
    
    # Score from LLM verdicts
    if llm_analysis:
        for aspect in ["categorization", "fls_removals", "fls_additions", "add6_divergence", "specificity"]:
            aspect_data = llm_analysis.get(aspect, {})
            if isinstance(aspect_data, dict):
                verdict = aspect_data.get("verdict", "")
                score += LLM_VERDICT_PRIORITY.get(verdict, 0)
    
    # Reduce score if human already reviewed
    if human_review:
        status = human_review.get("overall_status", "pending")
        if status == "fully_reviewed":
            score = max(0, score - 15)  # Significantly reduce priority
        elif status == "partial":
            score = max(0, score - 5)
    
    return score


def format_flags(flags: dict) -> str:
    """Format active flags as a comma-separated string."""
    active = [f for f, v in flags.items() if v]
    return ", ".join(active) if active else "none"


def format_llm_verdict(llm_analysis: dict | None, aspect: str) -> str:
    """Get verdict for an aspect from LLM analysis."""
    if not llm_analysis:
        return "unanalyzed"
    aspect_data = llm_analysis.get(aspect, {})
    if isinstance(aspect_data, dict):
        return aspect_data.get("verdict", "n/a")
    return "n/a"


def format_llm_summary(llm_analysis: dict | None) -> str:
    """Get one-line summary from LLM analysis."""
    if not llm_analysis:
        return "Awaiting LLM analysis"
    return llm_analysis.get("summary", "No summary provided")


def format_human_status(human_review: dict | None) -> str:
    """Get human review status."""
    if not human_review:
        return "pending"
    return human_review.get("overall_status", "pending")


def load_all_outlier_data(
    batches: list[int],
    comp_dir: Path,
    root: Path,
) -> dict[str, dict]:
    """
    Load all outlier data for given batches.
    
    Returns dict mapping guideline_id to combined data:
    {
        "guideline_id": str,
        "batch": int,
        "comparison": dict,  # from comparison_data
        "flags": dict,
        "llm_analysis": dict | None,  # from outlier_analysis
        "human_review": dict | None,
        "attention_score": int,
    }
    """
    all_data = {}
    
    for batch in batches:
        batch_dir = comp_dir / f"batch{batch}"
        if not batch_dir.exists():
            continue
        
        for f in batch_dir.glob("*.json"):
            if f.name.startswith("batch") or f.name == "cross_batch_summary.json":
                continue
            
            guideline_id = filename_to_guideline(f.stem)
            comp_data = load_json_file(f)
            if not comp_data:
                continue
            
            # Load outlier analysis if it exists
            outlier = load_outlier_analysis(guideline_id, root)
            
            flags = comp_data.get("flags", {})
            llm_analysis = outlier.get("llm_analysis") if outlier else None
            human_review = outlier.get("human_review") if outlier else None
            
            attention_score = compute_attention_score(flags, llm_analysis, human_review)
            
            all_data[guideline_id] = {
                "guideline_id": guideline_id,
                "batch": batch,
                "comparison": comp_data.get("comparison", {}),
                "flags": flags,
                "llm_analysis": llm_analysis,
                "human_review": human_review,
                "attention_score": attention_score,
            }
    
    return all_data


def generate_combined_report(
    batches: list[int],
    all_data: dict[str, dict],
    batch_summaries: dict[int, dict],
    cross_batch: dict,
    root: Path,
) -> str:
    """Generate combined report with all sections."""
    lines = [
        "# Verification Comparison Analysis Report",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
    ]
    
    # ==========================================================================
    # Executive Summary
    # ==========================================================================
    lines.append("## Executive Summary")
    lines.append("")
    
    total = len(all_data)
    analyzed = sum(1 for d in all_data.values() if d["llm_analysis"])
    unanalyzed = total - analyzed
    
    fully_reviewed = sum(1 for d in all_data.values() 
                         if d["human_review"] and d["human_review"].get("overall_status") == "fully_reviewed")
    partial_reviewed = sum(1 for d in all_data.values()
                           if d["human_review"] and d["human_review"].get("overall_status") == "partial")
    pending_review = total - fully_reviewed - partial_reviewed
    
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total outliers | {total} |")
    lines.append(f"| LLM analyzed | {analyzed} |")
    lines.append(f"| Awaiting LLM analysis | {unanalyzed} |")
    lines.append(f"| Human fully reviewed | {fully_reviewed} |")
    lines.append(f"| Human partially reviewed | {partial_reviewed} |")
    lines.append(f"| Human review pending | {pending_review} |")
    lines.append("")
    
    # LLM verdict distribution
    if analyzed > 0:
        verdict_counts = {"appropriate": 0, "inappropriate": 0, "needs_review": 0}
        for d in all_data.values():
            llm = d.get("llm_analysis")
            if llm:
                rec = llm.get("overall_recommendation", "")
                if rec in verdict_counts:
                    verdict_counts[rec] += 1
        
        lines.append("### LLM Recommendation Distribution")
        lines.append("")
        lines.append("| Recommendation | Count |")
        lines.append("|----------------|-------|")
        for rec, count in sorted(verdict_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {rec} | {count} |")
        lines.append("")
    
    # ==========================================================================
    # Needs Attention (High Priority)
    # ==========================================================================
    lines.append("## Needs Attention")
    lines.append("")
    lines.append("Guidelines sorted by priority score (higher = needs more attention).")
    lines.append("")
    
    # Sort by attention score descending
    sorted_data = sorted(all_data.values(), key=lambda x: -x["attention_score"])
    
    # Show top priority items (score > 5 or top 20, whichever is more)
    high_priority = [d for d in sorted_data if d["attention_score"] > 5]
    if len(high_priority) < 20:
        high_priority = sorted_data[:20]
    
    if high_priority:
        lines.append("| Guideline | Batch | Score | LLM Verdict | Human Status | Flags |")
        lines.append("|-----------|-------|-------|-------------|--------------|-------|")
        
        for d in high_priority:
            gid = d["guideline_id"]
            batch = d["batch"]
            score = d["attention_score"]
            llm_rec = d["llm_analysis"].get("overall_recommendation", "unanalyzed") if d["llm_analysis"] else "unanalyzed"
            human_status = format_human_status(d["human_review"])
            flags = format_flags(d["flags"])
            
            lines.append(f"| {gid} | {batch} | {score} | {llm_rec} | {human_status} | {flags[:40]}{'...' if len(flags) > 40 else ''} |")
        
        lines.append("")
        
        # Show LLM summaries for top items
        lines.append("### LLM Analysis Summaries (Top Priority)")
        lines.append("")
        for d in high_priority[:10]:
            if d["llm_analysis"]:
                gid = d["guideline_id"]
                summary = format_llm_summary(d["llm_analysis"])
                rec = d["llm_analysis"].get("overall_recommendation", "n/a")
                lines.append(f"**{gid}** ({rec}):")
                lines.append(f"  {summary[:200]}{'...' if len(summary) > 200 else ''}")
                lines.append("")
    else:
        lines.append("No high-priority items.")
        lines.append("")
    
    # ==========================================================================
    # By Flag Type
    # ==========================================================================
    lines.append("## By Flag Type")
    lines.append("")
    
    for flag_name in FLAG_TYPES:
        flagged = [d for d in all_data.values() if d["flags"].get(flag_name)]
        if not flagged:
            continue
        
        lines.append(f"### {flag_name} ({len(flagged)} guidelines)")
        lines.append("")
        
        # Sort by attention score
        flagged_sorted = sorted(flagged, key=lambda x: -x["attention_score"])
        
        lines.append("| Guideline | Batch | LLM Verdict | Human Status | Summary |")
        lines.append("|-----------|-------|-------------|--------------|---------|")
        
        for d in flagged_sorted[:15]:  # Limit to 15 per flag
            gid = d["guideline_id"]
            batch = d["batch"]
            llm_rec = d["llm_analysis"].get("overall_recommendation", "unanalyzed") if d["llm_analysis"] else "unanalyzed"
            human_status = format_human_status(d["human_review"])
            summary = format_llm_summary(d["llm_analysis"])[:60]
            
            lines.append(f"| {gid} | {batch} | {llm_rec} | {human_status} | {summary}... |")
        
        if len(flagged) > 15:
            lines.append(f"| ... | | | | ({len(flagged) - 15} more) |")
        
        lines.append("")
    
    # ==========================================================================
    # Awaiting Analysis
    # ==========================================================================
    unanalyzed_list = [d for d in all_data.values() if not d["llm_analysis"]]
    if unanalyzed_list:
        lines.append("## Awaiting LLM Analysis")
        lines.append("")
        lines.append(f"{len(unanalyzed_list)} guidelines have comparison data but no LLM analysis yet.")
        lines.append("")
        
        # Group by batch
        by_batch: dict[int, list] = {}
        for d in unanalyzed_list:
            batch = d["batch"]
            if batch not in by_batch:
                by_batch[batch] = []
            by_batch[batch].append(d["guideline_id"])
        
        for batch in sorted(by_batch.keys()):
            guidelines = by_batch[batch]
            lines.append(f"**Batch {batch}:** {', '.join(guidelines[:10])}")
            if len(guidelines) > 10:
                lines.append(f"  ... and {len(guidelines) - 10} more")
            lines.append("")
    
    # ==========================================================================
    # Fully Reviewed
    # ==========================================================================
    reviewed_list = [d for d in all_data.values() 
                     if d["human_review"] and d["human_review"].get("overall_status") == "fully_reviewed"]
    if reviewed_list:
        lines.append("## Fully Reviewed")
        lines.append("")
        lines.append(f"{len(reviewed_list)} guidelines have been fully reviewed by human.")
        lines.append("")
        
        # Brief summary
        lines.append("| Guideline | Batch | LLM Verdict | Flags |")
        lines.append("|-----------|-------|-------------|-------|")
        for d in reviewed_list[:20]:
            gid = d["guideline_id"]
            batch = d["batch"]
            llm_rec = d["llm_analysis"].get("overall_recommendation", "n/a") if d["llm_analysis"] else "n/a"
            flags = format_flags(d["flags"])[:30]
            lines.append(f"| {gid} | {batch} | {llm_rec} | {flags} |")
        
        if len(reviewed_list) > 20:
            lines.append(f"| ... | | | ({len(reviewed_list) - 20} more) |")
        lines.append("")
    
    # ==========================================================================
    # Batch Summaries
    # ==========================================================================
    lines.append("## Batch Summaries")
    lines.append("")
    
    for batch in sorted(batches):
        batch_data = [d for d in all_data.values() if d["batch"] == batch]
        if not batch_data:
            continue
        
        analyzed_count = sum(1 for d in batch_data if d["llm_analysis"])
        reviewed_count = sum(1 for d in batch_data 
                            if d["human_review"] and d["human_review"].get("overall_status") == "fully_reviewed")
        
        summary = batch_summaries.get(batch, {})
        batch_name = summary.get("batch_name", f"Batch {batch}")
        
        lines.append(f"### Batch {batch}: {batch_name}")
        lines.append("")
        lines.append(f"- **Total:** {len(batch_data)}")
        lines.append(f"- **LLM analyzed:** {analyzed_count}")
        lines.append(f"- **Human reviewed:** {reviewed_count}")
        lines.append("")
    
    return "\n".join(lines)


def generate_final_report(
    batches: list[int],
    all_data: dict[str, dict],
    batch_summaries: dict[int, dict],
    cross_batch: dict,
    root: Path,
) -> str:
    """Generate executive summary report."""
    lines = [
        "# Verification Comparison Analysis - Final Report",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        "## Overview",
        "",
    ]
    
    total = len(all_data)
    analyzed = sum(1 for d in all_data.values() if d["llm_analysis"])
    fully_reviewed = sum(1 for d in all_data.values() 
                         if d["human_review"] and d["human_review"].get("overall_status") == "fully_reviewed")
    
    lines.append(f"**Total outliers:** {total}")
    lines.append(f"**LLM analyzed:** {analyzed} ({analyzed*100//total if total else 0}%)")
    lines.append(f"**Human reviewed:** {fully_reviewed} ({fully_reviewed*100//total if total else 0}%)")
    lines.append("")
    
    # Batch breakdown
    lines.append("### Batch Summary")
    lines.append("")
    lines.append("| Batch | Name | Total | Analyzed | Reviewed |")
    lines.append("|-------|------|-------|----------|----------|")
    
    for batch in sorted(batches):
        batch_data = [d for d in all_data.values() if d["batch"] == batch]
        summary = batch_summaries.get(batch, {})
        name = summary.get("batch_name", f"Batch {batch}")
        count = len(batch_data)
        analyzed_count = sum(1 for d in batch_data if d["llm_analysis"])
        reviewed_count = sum(1 for d in batch_data 
                            if d["human_review"] and d["human_review"].get("overall_status") == "fully_reviewed")
        
        lines.append(f"| {batch} | {name} | {count} | {analyzed_count} | {reviewed_count} |")
    
    lines.append("")
    
    # LLM verdict distribution
    verdict_counts = {"accept": 0, "reject": 0, "needs_review": 0, "unanalyzed": 0}
    for d in all_data.values():
        llm = d.get("llm_analysis")
        if llm:
            rec = llm.get("overall_recommendation", "needs_review")
            if rec in verdict_counts:
                verdict_counts[rec] += 1
        else:
            verdict_counts["unanalyzed"] += 1
    
    lines.append("### LLM Recommendations")
    lines.append("")
    lines.append("| Recommendation | Count | % |")
    lines.append("|----------------|-------|---|")
    for rec, count in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        pct = count * 100 // total if total else 0
        lines.append(f"| {rec} | {count} | {pct}% |")
    lines.append("")
    
    # Top flags
    flag_counts = {flag: 0 for flag in FLAG_TYPES}
    for d in all_data.values():
        for flag, is_set in d["flags"].items():
            if is_set and flag in flag_counts:
                flag_counts[flag] += 1
    
    lines.append("### Flag Distribution")
    lines.append("")
    lines.append("| Flag | Count |")
    lines.append("|------|-------|")
    for flag, count in sorted(flag_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            lines.append(f"| {flag} | {count} |")
    lines.append("")
    
    return "\n".join(lines)


def generate_batch_report(
    batch: int,
    all_data: dict[str, dict],
    summary: dict,
    root: Path,
) -> str:
    """Generate per-batch detail report."""
    batch_data = [d for d in all_data.values() if d["batch"] == batch]
    
    lines = [
        f"# Batch {batch} Report: {summary.get('batch_name', '')}",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        "## Summary",
        "",
        f"**Total guidelines:** {len(batch_data)}",
        f"**LLM analyzed:** {sum(1 for d in batch_data if d['llm_analysis'])}",
        f"**Human reviewed:** {sum(1 for d in batch_data if d['human_review'] and d['human_review'].get('overall_status') == 'fully_reviewed')}",
        "",
    ]
    
    # All guidelines in this batch
    lines.append("## Guidelines")
    lines.append("")
    lines.append("| Guideline | Score | LLM Verdict | Human Status | Top Flags |")
    lines.append("|-----------|-------|-------------|--------------|-----------|")
    
    sorted_batch = sorted(batch_data, key=lambda x: -x["attention_score"])
    for d in sorted_batch:
        gid = d["guideline_id"]
        score = d["attention_score"]
        llm_rec = d["llm_analysis"].get("overall_recommendation", "unanalyzed") if d["llm_analysis"] else "unanalyzed"
        human_status = format_human_status(d["human_review"])
        flags = format_flags(d["flags"])[:35]
        
        lines.append(f"| {gid} | {score} | {llm_rec} | {human_status} | {flags} |")
    
    lines.append("")
    
    # LLM summaries for this batch
    analyzed = [d for d in batch_data if d["llm_analysis"]]
    if analyzed:
        lines.append("## LLM Analysis Details")
        lines.append("")
        
        for d in sorted(analyzed, key=lambda x: -x["attention_score"]):
            gid = d["guideline_id"]
            llm = d["llm_analysis"]
            rec = llm.get("overall_recommendation", "n/a")
            summary_text = llm.get("summary", "No summary")
            
            lines.append(f"### {gid}")
            lines.append("")
            lines.append(f"**Recommendation:** {rec}")
            lines.append(f"**Summary:** {summary_text}")
            lines.append("")
            
            # Show aspect verdicts
            for aspect in ["categorization", "fls_removals", "fls_additions", "specificity", "add6_divergence"]:
                aspect_data = llm.get(aspect, {})
                if isinstance(aspect_data, dict) and aspect_data.get("verdict"):
                    verdict = aspect_data.get("verdict")
                    reasoning = aspect_data.get("reasoning", "")[:100]
                    lines.append(f"- **{aspect}:** {verdict} - {reasoning}...")
            
            lines.append("")
    
    return "\n".join(lines)


def generate_cross_batch_report(
    batches: list[int],
    all_data: dict[str, dict],
    cross_batch: dict,
    root: Path,
) -> str:
    """Generate cross-batch patterns report."""
    lines = [
        "# Cross-Batch Analysis Report",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        f"**Batches analyzed:** {', '.join(map(str, batches))}",
        f"**Total guidelines:** {len(all_data)}",
        "",
    ]
    
    # Systematic patterns from cross_batch summary
    patterns = cross_batch.get("systematic_patterns", {})
    
    # Systematic removals
    removals = patterns.get("fls_sections_frequently_removed", [])
    if removals:
        lines.append("## Systematic FLS Removals")
        lines.append("")
        lines.append("FLS sections removed across multiple guidelines:")
        lines.append("")
        lines.append("| FLS ID | Count | Guidelines |")
        lines.append("|--------|-------|------------|")
        
        for r in removals[:15]:
            fls_id = r["fls_id"]
            count = r["removal_count"]
            guidelines = ", ".join(r.get("guidelines", [])[:5])
            if len(r.get("guidelines", [])) > 5:
                guidelines += "..."
            lines.append(f"| {fls_id} | {count} | {guidelines} |")
        
        lines.append("")
    
    # Systematic additions
    additions = patterns.get("fls_sections_frequently_added", [])
    if additions:
        lines.append("## Systematic FLS Additions")
        lines.append("")
        lines.append("FLS sections added across multiple guidelines:")
        lines.append("")
        lines.append("| FLS ID | Count | Guidelines |")
        lines.append("|--------|-------|------------|")
        
        for a in additions[:15]:
            fls_id = a["fls_id"]
            count = a["addition_count"]
            guidelines = ", ".join(a.get("guidelines", [])[:5])
            if len(a.get("guidelines", [])) > 5:
                guidelines += "..."
            lines.append(f"| {fls_id} | {count} | {guidelines} |")
        
        lines.append("")
    
    # Multi-dimension outliers
    multi_dim = [d for d in all_data.values() if d["flags"].get("multi_dimension_outlier")]
    if multi_dim:
        lines.append("## Multi-Dimension Outliers")
        lines.append("")
        lines.append("Guidelines with multiple flags set:")
        lines.append("")
        lines.append("| Guideline | Batch | Score | Flags |")
        lines.append("|-----------|-------|-------|-------|")
        
        for d in sorted(multi_dim, key=lambda x: -x["attention_score"])[:20]:
            gid = d["guideline_id"]
            batch = d["batch"]
            score = d["attention_score"]
            active_flags = [f for f, v in d["flags"].items() if v and f != "multi_dimension_outlier"]
            flags = ", ".join(active_flags[:3])
            if len(active_flags) > 3:
                flags += f" (+{len(active_flags)-3})"
            lines.append(f"| {gid} | {batch} | {score} | {flags} |")
        
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Markdown reports from analysis data."
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c)",
    )
    parser.add_argument(
        "--batches",
        required=True,
        help="Comma-separated list of batch numbers (e.g., 1,2,3)",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory (default: cache/analysis/reports/)",
    )
    
    args = parser.parse_args()
    
    # Parse batches
    try:
        batches = [int(b.strip()) for b in args.batches.split(",")]
    except ValueError:
        print(f"ERROR: Invalid batch numbers: {args.batches}", file=sys.stderr)
        sys.exit(1)
    
    standard = normalize_standard(args.standard)
    root = get_project_root()
    
    comp_dir = get_comparison_data_dir(root)
    
    if args.output_dir:
        reports_dir = Path(args.output_dir)
    else:
        reports_dir = get_reports_dir(root)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Load all outlier data (comparison + analysis)
    print(f"Loading outlier data for batches {batches}...", file=sys.stderr)
    all_data = load_all_outlier_data(batches, comp_dir, root)
    print(f"  Loaded {len(all_data)} guidelines", file=sys.stderr)
    
    # Load batch summaries
    batch_summaries: dict[int, dict] = {}
    for batch in batches:
        summary_path = comp_dir / f"batch{batch}_summary.json"
        if summary_path.exists():
            batch_summaries[batch] = load_json_file(summary_path) or {}
        else:
            print(f"WARNING: No summary for batch {batch}", file=sys.stderr)
    
    # Load cross-batch summary
    cross_batch_path = comp_dir / "cross_batch_summary.json"
    cross_batch = load_json_file(cross_batch_path) or {}
    
    if not all_data:
        print("ERROR: No outlier data found", file=sys.stderr)
        print(f"  Run: uv run extract-comparison-data --standard {args.standard} --batches {args.batches}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Generating reports...", file=sys.stderr)
    
    # Generate combined report
    combined_report = generate_combined_report(batches, all_data, batch_summaries, cross_batch, root)
    combined_path = reports_dir / "combined_report.md"
    combined_path.write_text(combined_report)
    print(f"  Wrote: {combined_path}", file=sys.stderr)
    
    # Generate final report
    final_report = generate_final_report(batches, all_data, batch_summaries, cross_batch, root)
    final_path = reports_dir / "final_report.md"
    final_path.write_text(final_report)
    print(f"  Wrote: {final_path}", file=sys.stderr)
    
    # Generate per-batch reports
    for batch in batches:
        if batch in batch_summaries:
            batch_report = generate_batch_report(batch, all_data, batch_summaries[batch], root)
            batch_path = reports_dir / f"batch{batch}_report.md"
            batch_path.write_text(batch_report)
            print(f"  Wrote: {batch_path}", file=sys.stderr)
    
    # Generate cross-batch report
    cross_report = generate_cross_batch_report(batches, all_data, cross_batch, root)
    cross_path = reports_dir / "cross_batch_report.md"
    cross_path.write_text(cross_report)
    print(f"  Wrote: {cross_path}", file=sys.stderr)
    
    # Print summary
    analyzed = sum(1 for d in all_data.values() if d["llm_analysis"])
    reviewed = sum(1 for d in all_data.values() 
                   if d["human_review"] and d["human_review"].get("overall_status") == "fully_reviewed")
    
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Total outliers: {len(all_data)}", file=sys.stderr)
    print(f"  LLM analyzed: {analyzed}", file=sys.stderr)
    print(f"  Human reviewed: {reviewed}", file=sys.stderr)
    print(f"\nReports written to: {reports_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
