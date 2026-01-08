#!/usr/bin/env python3
"""
extract-comparison-data - Extract comparison data between decisions and mapping file.

This tool extracts and compares decision files against the current mapping file,
computing flags and comparison diffs for each guideline.

Outputs:
- cache/analysis/comparison_data/batch{N}/{guideline}.json - Per-guideline data
- cache/analysis/comparison_data/batch{N}_summary.json - Batch statistics
- cache/analysis/comparison_data/cross_batch_summary.json - Cross-batch patterns

Usage:
    uv run extract-comparison-data --standard misra-c --batches 1,2,3
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fls_tools.shared import (
    VALID_STANDARDS,
    normalize_standard,
    get_project_root,
    is_v2_family,
)

from .shared import (
    get_comparison_data_dir,
    load_mapping_file,
    load_add6_data,
    load_progress_file,
    load_all_decision_files,
    compute_comparison,
    compute_flags,
    is_outlier,
    get_active_flags,
    get_batch_expected_pattern,
    check_pattern_conformance,
    save_json_file,
    load_json_file,
    guideline_to_filename,
    normalize_applicability,
    OUTLIER_THRESHOLDS,
)


def extract_guideline_data(
    guideline_id: str,
    mapping: dict,
    decision: dict,
    add6_data: dict,
    batch: int,
) -> dict:
    """
    Extract comparison data for a single guideline.
    
    Returns per-guideline JSON structure as defined in plan.
    """
    # Parse guideline type and chapter
    parts = guideline_id.split()
    guideline_type = parts[0] if parts else "Unknown"
    try:
        chapter = int(parts[1].split(".")[0]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        chapter = 0
    
    # Get ADD-6 data for this guideline
    add6 = add6_data.get(guideline_id, {})
    
    # Get mapping and decision context data
    mapping_entry = mapping.get(guideline_id, {})
    
    # Normalize to v2 structure for comparison
    if is_v2_family(mapping_entry):
        mapping_all_rust = mapping_entry.get("all_rust", {})
        mapping_safe_rust = mapping_entry.get("safe_rust", {})
    else:
        # v1 family: single context applies to both
        mapping_all_rust = mapping_entry
        mapping_safe_rust = mapping_entry
    
    if is_v2_family(decision):
        decision_all_rust = decision.get("all_rust", {})
        decision_safe_rust = decision.get("safe_rust", {})
    else:
        decision_all_rust = decision
        decision_safe_rust = decision
    
    # Prepare ADD-6 context data
    add6_all_rust = {
        "applicability": add6.get("applicability_all_rust"),
        "adjusted_category": add6.get("adjusted_category"),
    }
    add6_safe_rust = {
        "applicability": add6.get("applicability_safe_rust"),
        "adjusted_category": add6.get("adjusted_category"),
    }
    
    # Compute comparisons
    comparison_all_rust = compute_comparison(mapping_all_rust, decision_all_rust, add6_all_rust)
    comparison_safe_rust = compute_comparison(mapping_safe_rust, decision_safe_rust, add6_safe_rust)
    
    # Compute flags
    flags = compute_flags(comparison_all_rust, comparison_safe_rust, decision, batch)
    
    return {
        "guideline_id": guideline_id,
        "batch": batch,
        "guideline_type": guideline_type,
        "misra_chapter": chapter,
        "add6": {
            "applicability_all_rust": add6.get("applicability_all_rust"),
            "applicability_safe_rust": add6.get("applicability_safe_rust"),
            "adjusted_category": add6.get("adjusted_category"),
            "rationale_codes": add6.get("rationale", []),
            "comment": add6.get("comment", ""),
        },
        "mapping": {
            "schema_version": mapping_entry.get("schema_version", "unknown"),
            "all_rust": {
                "applicability": mapping_all_rust.get("applicability"),
                "adjusted_category": mapping_all_rust.get("adjusted_category"),
                "rationale_type": mapping_all_rust.get("rationale_type"),
                "confidence": mapping_all_rust.get("confidence"),
                "accepted_matches": mapping_all_rust.get("accepted_matches", []),
                "rejected_matches": mapping_all_rust.get("rejected_matches", []),
                "notes": mapping_all_rust.get("notes"),
            },
            "safe_rust": {
                "applicability": mapping_safe_rust.get("applicability"),
                "adjusted_category": mapping_safe_rust.get("adjusted_category"),
                "rationale_type": mapping_safe_rust.get("rationale_type"),
                "confidence": mapping_safe_rust.get("confidence"),
                "accepted_matches": mapping_safe_rust.get("accepted_matches", []),
                "rejected_matches": mapping_safe_rust.get("rejected_matches", []),
                "notes": mapping_safe_rust.get("notes"),
            },
        },
        "decision": {
            "schema_version": decision.get("schema_version", "unknown"),
            "all_rust": {
                "decision": decision_all_rust.get("decision"),
                "applicability": decision_all_rust.get("applicability"),
                "adjusted_category": decision_all_rust.get("adjusted_category"),
                "rationale_type": decision_all_rust.get("rationale_type"),
                "confidence": decision_all_rust.get("confidence"),
                "analysis_summary": decision_all_rust.get("analysis_summary"),
                "accepted_matches": decision_all_rust.get("accepted_matches", []),
                "rejected_matches": decision_all_rust.get("rejected_matches", []),
                "search_tools_used": decision_all_rust.get("search_tools_used", []),
                "notes": decision_all_rust.get("notes"),
            },
            "safe_rust": {
                "decision": decision_safe_rust.get("decision"),
                "applicability": decision_safe_rust.get("applicability"),
                "adjusted_category": decision_safe_rust.get("adjusted_category"),
                "rationale_type": decision_safe_rust.get("rationale_type"),
                "confidence": decision_safe_rust.get("confidence"),
                "analysis_summary": decision_safe_rust.get("analysis_summary"),
                "accepted_matches": decision_safe_rust.get("accepted_matches", []),
                "rejected_matches": decision_safe_rust.get("rejected_matches", []),
                "search_tools_used": decision_safe_rust.get("search_tools_used", []),
                "notes": decision_safe_rust.get("notes"),
            },
        },
        "comparison": {
            "all_rust": comparison_all_rust,
            "safe_rust": comparison_safe_rust,
        },
        "flags": flags,
    }


def compute_batch_summary(
    batch: int,
    guideline_data: list[dict],
) -> dict:
    """Compute summary statistics for a batch."""
    expected = get_batch_expected_pattern(batch)
    
    # Schema distribution
    mapping_schemas = defaultdict(int)
    decision_schemas = defaultdict(int)
    
    # Pattern conformance
    all_rust_conforms = 0
    safe_rust_conforms = 0
    
    # Categorization vs ADD-6
    all_rust_app_matches = 0
    all_rust_app_differs = 0
    all_rust_cat_matches = 0
    all_rust_cat_differs = 0
    safe_rust_app_matches = 0
    safe_rust_app_differs = 0
    safe_rust_cat_matches = 0
    safe_rust_cat_differs = 0
    
    # Rationale type distribution
    all_rust_rationale = defaultdict(int)
    safe_rust_rationale = defaultdict(int)
    
    # Rationale type transitions
    all_rust_transitions = defaultdict(int)
    safe_rust_transitions = defaultdict(int)
    
    # FLS changes
    all_rust_fls_added = 0
    all_rust_fls_removed = 0
    all_rust_with_removals = 0
    all_rust_with_additions_gte_2 = 0
    safe_rust_fls_added = 0
    safe_rust_fls_removed = 0
    safe_rust_with_removals = 0
    safe_rust_with_additions_gte_2 = 0
    
    # Quality
    has_analysis_summary = 0
    has_search_tools = 0
    has_rejected_matches = 0
    
    # Flagged guidelines
    flagged = defaultdict(list)
    
    for g in guideline_data:
        gid = g["guideline_id"]
        comp_ar = g["comparison"]["all_rust"]
        comp_sr = g["comparison"]["safe_rust"]
        flags = g["flags"]
        
        # Schema distribution
        mapping_schemas[g["mapping"]["schema_version"]] += 1
        decision_schemas[g["decision"]["schema_version"]] += 1
        
        # Pattern conformance (simplified check)
        decision = g["decision"]
        dec_ar = decision["all_rust"]
        dec_sr = decision["safe_rust"]
        
        # Check all_rust conformance
        exp_ar = expected.get("all_rust", {})
        ar_conforms = True
        for field, exp_val in exp_ar.items():
            actual = dec_ar.get(field)
            if field == "applicability":
                actual = normalize_applicability(actual)
                exp_val = normalize_applicability(exp_val)
            if actual != exp_val:
                ar_conforms = False
                break
        if ar_conforms:
            all_rust_conforms += 1
        
        # Check safe_rust conformance
        exp_sr = expected.get("safe_rust", {})
        sr_conforms = True
        for field, exp_val in exp_sr.items():
            actual = dec_sr.get(field)
            if field == "applicability":
                actual = normalize_applicability(actual)
                exp_val = normalize_applicability(exp_val)
            if actual != exp_val:
                sr_conforms = False
                break
        if sr_conforms:
            safe_rust_conforms += 1
        
        # Categorization vs ADD-6
        if not comp_ar.get("applicability_differs_from_add6"):
            all_rust_app_matches += 1
        else:
            all_rust_app_differs += 1
        if not comp_ar.get("adjusted_category_differs_from_add6"):
            all_rust_cat_matches += 1
        else:
            all_rust_cat_differs += 1
        
        if not comp_sr.get("applicability_differs_from_add6"):
            safe_rust_app_matches += 1
        else:
            safe_rust_app_differs += 1
        if not comp_sr.get("adjusted_category_differs_from_add6"):
            safe_rust_cat_matches += 1
        else:
            safe_rust_cat_differs += 1
        
        # Rationale type distribution
        ar_rat = dec_ar.get("rationale_type")
        sr_rat = dec_sr.get("rationale_type")
        if ar_rat:
            all_rust_rationale[ar_rat] += 1
        if sr_rat:
            safe_rust_rationale[sr_rat] += 1
        
        # Rationale type transitions
        if comp_ar.get("rationale_type_changed"):
            trans = comp_ar["rationale_type_mapping_to_decision"]
            all_rust_transitions[trans] += 1
        if comp_sr.get("rationale_type_changed"):
            trans = comp_sr["rationale_type_mapping_to_decision"]
            safe_rust_transitions[trans] += 1
        
        # FLS changes
        all_rust_fls_added += len(comp_ar.get("fls_added", []))
        all_rust_fls_removed += len(comp_ar.get("fls_removed", []))
        if comp_ar.get("fls_removed"):
            all_rust_with_removals += 1
        if len(comp_ar.get("fls_added", [])) >= 2:
            all_rust_with_additions_gte_2 += 1
        
        safe_rust_fls_added += len(comp_sr.get("fls_added", []))
        safe_rust_fls_removed += len(comp_sr.get("fls_removed", []))
        if comp_sr.get("fls_removed"):
            safe_rust_with_removals += 1
        if len(comp_sr.get("fls_added", [])) >= 2:
            safe_rust_with_additions_gte_2 += 1
        
        # Quality
        if comp_ar.get("has_analysis_summary") or comp_sr.get("has_analysis_summary"):
            has_analysis_summary += 1
        if comp_ar.get("has_search_tools") or comp_sr.get("has_search_tools"):
            has_search_tools += 1
        if comp_ar.get("has_rejected_matches") or comp_sr.get("has_rejected_matches"):
            has_rejected_matches += 1
        
        # Flagged guidelines
        for flag_name, flag_val in flags.items():
            if flag_val:
                flagged[flag_name].append(gid)
    
    total = len(guideline_data)
    
    return {
        "batch_id": batch,
        "batch_name": expected.get("name", f"Batch {batch}"),
        "expected_pattern": {
            "all_rust": expected.get("all_rust", {}),
            "safe_rust": expected.get("safe_rust", {}),
        },
        "guideline_count": total,
        "schema_distribution": {
            "mapping": dict(mapping_schemas),
            "decision": dict(decision_schemas),
        },
        "pattern_conformance": {
            "all_rust": {
                "conforms": all_rust_conforms,
                "outliers": total - all_rust_conforms,
                "rate": all_rust_conforms / total if total > 0 else 0,
            },
            "safe_rust": {
                "conforms": safe_rust_conforms,
                "outliers": total - safe_rust_conforms,
                "rate": safe_rust_conforms / total if total > 0 else 0,
            },
        },
        "categorization_summary": {
            "all_rust": {
                "applicability_matches_add6": all_rust_app_matches,
                "applicability_differs_from_add6": all_rust_app_differs,
                "adjusted_category_matches_add6": all_rust_cat_matches,
                "adjusted_category_differs_from_add6": all_rust_cat_differs,
            },
            "safe_rust": {
                "applicability_matches_add6": safe_rust_app_matches,
                "applicability_differs_from_add6": safe_rust_app_differs,
                "adjusted_category_matches_add6": safe_rust_cat_matches,
                "adjusted_category_differs_from_add6": safe_rust_cat_differs,
            },
        },
        "rationale_type_distribution": {
            "all_rust": dict(all_rust_rationale),
            "safe_rust": dict(safe_rust_rationale),
        },
        "rationale_type_transitions": {
            "all_rust": dict(all_rust_transitions),
            "safe_rust": dict(safe_rust_transitions),
        },
        "fls_changes_summary": {
            "all_rust": {
                "total_added": all_rust_fls_added,
                "total_removed": all_rust_fls_removed,
                "net_change": all_rust_fls_added - all_rust_fls_removed,
                "guidelines_with_removals": all_rust_with_removals,
                "guidelines_with_additions_gte_2": all_rust_with_additions_gte_2,
            },
            "safe_rust": {
                "total_added": safe_rust_fls_added,
                "total_removed": safe_rust_fls_removed,
                "net_change": safe_rust_fls_added - safe_rust_fls_removed,
                "guidelines_with_removals": safe_rust_with_removals,
                "guidelines_with_additions_gte_2": safe_rust_with_additions_gte_2,
            },
        },
        "quality_summary": {
            "has_analysis_summary": has_analysis_summary,
            "has_search_tools_documented": has_search_tools,
            "has_rejected_matches": has_rejected_matches,
        },
        "flagged_guidelines": {k: v for k, v in flagged.items() if v},
        "guidelines": [g["guideline_id"] for g in guideline_data],
    }


def compute_cross_batch_summary(
    all_batch_data: dict[int, list[dict]],
    batch_summaries: dict[int, dict],
) -> dict:
    """Compute cross-batch summary and systematic patterns."""
    from typing import Any
    
    # Aggregate FLS changes across batches
    # Type: dict[str, {"count": int, "batches": dict[int, int], "guidelines": list[str]}]
    fls_removed_counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "batches": defaultdict(int), "guidelines": []}
    )
    fls_added_counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "batches": defaultdict(int), "guidelines": []}
    )
    
    # Aggregate rationale type transitions
    all_transitions = defaultdict(int)
    
    # Track outliers
    multi_dimension_outliers = []
    
    total_guidelines = 0
    
    for batch, guidelines in all_batch_data.items():
        total_guidelines += len(guidelines)
        
        for g in guidelines:
            gid = g["guideline_id"]
            
            # Track FLS removals
            for context in ["all_rust", "safe_rust"]:
                for fls_id in g["comparison"][context].get("fls_removed", []):
                    fls_removed_counts[fls_id]["count"] += 1
                    fls_removed_counts[fls_id]["batches"][batch] += 1
                    if gid not in fls_removed_counts[fls_id]["guidelines"]:
                        fls_removed_counts[fls_id]["guidelines"].append(gid)
                
                for fls_id in g["comparison"][context].get("fls_added", []):
                    fls_added_counts[fls_id]["count"] += 1
                    fls_added_counts[fls_id]["batches"][batch] += 1
                    if gid not in fls_added_counts[fls_id]["guidelines"]:
                        fls_added_counts[fls_id]["guidelines"].append(gid)
            
            # Track transitions (use all_rust as primary)
            trans = g["comparison"]["all_rust"].get("rationale_type_mapping_to_decision")
            if trans:
                all_transitions[trans] += 1
            
            # Track multi-dimension outliers
            if g["flags"].get("multi_dimension_outlier"):
                active = get_active_flags(g["flags"])
                multi_dimension_outliers.append({
                    "guideline_id": gid,
                    "flag_count": len(active),
                    "flags": active,
                })
    
    # Filter to systematic patterns (2+ occurrences)
    systematic_removals = [
        {
            "fls_id": fls_id,
            "removal_count": data["count"],
            "batches": dict(data["batches"]),
            "guidelines": data["guidelines"][:10],  # Limit for readability
        }
        for fls_id, data in fls_removed_counts.items()
        if data["count"] >= OUTLIER_THRESHOLDS["systematic_pattern"]
    ]
    systematic_removals.sort(key=lambda x: x["removal_count"], reverse=True)
    
    systematic_additions = [
        {
            "fls_id": fls_id,
            "addition_count": data["count"],
            "batches": dict(data["batches"]),
            "guidelines": data["guidelines"][:10],
        }
        for fls_id, data in fls_added_counts.items()
        if data["count"] >= OUTLIER_THRESHOLDS["systematic_pattern"]
    ]
    systematic_additions.sort(key=lambda x: x["addition_count"], reverse=True)
    
    # Schema distribution overall
    overall_mapping_schemas = defaultdict(int)
    overall_decision_schemas = defaultdict(int)
    for summary in batch_summaries.values():
        for schema, count in summary["schema_distribution"]["mapping"].items():
            overall_mapping_schemas[schema] += count
        for schema, count in summary["schema_distribution"]["decision"].items():
            overall_decision_schemas[schema] += count
    
    # Outlier flag distribution
    flag_distribution = defaultdict(int)
    for g_list in all_batch_data.values():
        for g in g_list:
            flag_count = len([f for f, v in g["flags"].items() if v and f != "multi_dimension_outlier"])
            flag_distribution[flag_count] += 1
    
    return {
        "extraction_date": datetime.utcnow().isoformat() + "Z",
        "total_guidelines": total_guidelines,
        "batches": {
            batch: {"name": summary["batch_name"], "count": summary["guideline_count"]}
            for batch, summary in batch_summaries.items()
        },
        "overall_schema_distribution": {
            "mapping": dict(overall_mapping_schemas),
            "decision": dict(overall_decision_schemas),
        },
        "batch_pattern_conformance": {
            batch: {
                "all_rust": summary["pattern_conformance"]["all_rust"],
                "safe_rust": summary["pattern_conformance"]["safe_rust"],
            }
            for batch, summary in batch_summaries.items()
        },
        "systematic_patterns": {
            "fls_sections_frequently_removed": systematic_removals[:20],
            "fls_sections_frequently_added": systematic_additions[:20],
            "rationale_type_transitions_overall": dict(all_transitions),
        },
        "outlier_concentration": {
            "guidelines_flagged_on_multiple_dimensions": multi_dimension_outliers,
            "distribution": {f"{k}_flag{'s' if k != 1 else ''}": v for k, v in sorted(flag_distribution.items())},
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract comparison data between decision files and mapping file."
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
        help="Comma-separated list of batch numbers to process (e.g., 1,2,3)",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory (default: cache/analysis/comparison_data/)",
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
    
    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = get_comparison_data_dir(root)
    
    print(f"Extracting comparison data for {args.standard}, batches {batches}")
    print(f"Output directory: {output_dir}")
    
    # Load reference data
    print("\nLoading reference data...")
    mapping = load_mapping_file(standard, root)
    print(f"  Loaded {len(mapping)} guidelines from mapping file")
    
    add6_data = load_add6_data(root)
    print(f"  Loaded {len(add6_data)} guidelines from ADD-6 data")
    
    progress = load_progress_file(standard, root)
    
    # Process each batch
    all_batch_data = {}
    batch_summaries = {}
    
    for batch in batches:
        print(f"\nProcessing batch {batch}...")
        
        # Load decision files for this batch
        decisions = load_all_decision_files(standard, batch, root)
        print(f"  Loaded {len(decisions)} decision files")
        
        if not decisions:
            print(f"  WARNING: No decision files found for batch {batch}")
            continue
        
        # Create batch output directory
        batch_dir = output_dir / f"batch{batch}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each guideline
        guideline_data = []
        for guideline_id, decision in decisions.items():
            data = extract_guideline_data(
                guideline_id, mapping, decision, add6_data, batch
            )
            guideline_data.append(data)
            
            # Save per-guideline file
            filename = guideline_to_filename(guideline_id) + ".json"
            save_json_file(batch_dir / filename, data)
        
        all_batch_data[batch] = guideline_data
        
        # Compute and save batch summary
        summary = compute_batch_summary(batch, guideline_data)
        batch_summaries[batch] = summary
        save_json_file(output_dir / f"batch{batch}_summary.json", summary)
        
        # Report
        flagged_count = len([g for g in guideline_data if is_outlier(g["flags"])])
        print(f"  Processed {len(guideline_data)} guidelines")
        print(f"  Flagged as outliers: {flagged_count}")
    
    # Compute and save cross-batch summary
    if batch_summaries:
        print("\nComputing cross-batch summary...")
        cross_batch = compute_cross_batch_summary(all_batch_data, batch_summaries)
        save_json_file(output_dir / "cross_batch_summary.json", cross_batch)
        
        total_outliers = sum(
            len([g for g in data if is_outlier(g["flags"])])
            for data in all_batch_data.values()
        )
        print(f"\nTotal guidelines processed: {cross_batch['total_guidelines']}")
        print(f"Total outliers flagged: {total_outliers}")
        print(f"Systematic FLS removals: {len(cross_batch['systematic_patterns']['fls_sections_frequently_removed'])}")
        print(f"Systematic FLS additions: {len(cross_batch['systematic_patterns']['fls_sections_frequently_added'])}")
    
    print(f"\nOutput written to: {output_dir}")


if __name__ == "__main__":
    main()
