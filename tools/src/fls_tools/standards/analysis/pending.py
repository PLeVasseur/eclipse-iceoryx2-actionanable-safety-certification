#!/usr/bin/env python3
"""
list-pending-outliers - Show outliers not yet analyzed.

This tool lists all flagged guidelines that don't have an outlier analysis yet,
or have analysis but no human review.

Usage:
    uv run list-pending-outliers --standard misra-c --batches 1,2,3
    uv run list-pending-outliers --standard misra-c --batches 1 --flag fls_removed
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    get_comparison_data_dir,
    get_outlier_analysis_dir,
    load_json_file,
    load_outlier_analysis,
    is_outlier,
    get_active_flags,
    FLAG_TYPES,
    guideline_to_filename,
    filename_to_guideline,
)


def main():
    parser = argparse.ArgumentParser(
        description="List outliers that need analysis or review."
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
        "--flag",
        choices=FLAG_TYPES,
        help="Filter to guidelines with specific flag set",
    )
    parser.add_argument(
        "--needs-analysis",
        action="store_true",
        help="Show only guidelines without any analysis",
    )
    parser.add_argument(
        "--needs-review",
        action="store_true",
        help="Show only guidelines with analysis but no human review",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of guidelines to show (default: 50)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show flag details for each guideline",
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
    
    # Collect all flagged guidelines
    flagged_guidelines: list[dict] = []
    
    for batch in batches:
        batch_dir = comp_dir / f"batch{batch}"
        if not batch_dir.exists():
            print(f"WARNING: No comparison data for batch {batch}", file=sys.stderr)
            continue
        
        for f in batch_dir.glob("*.json"):
            data = load_json_file(f)
            if not data:
                continue
            
            gid = data.get("guideline_id", filename_to_guideline(f.name))
            flags = data.get("flags", {})
            
            # Check if this is an outlier
            if not is_outlier(flags):
                continue
            
            # Filter by flag if specified
            if args.flag and not flags.get(args.flag):
                continue
            
            # Check analysis status
            analysis = load_outlier_analysis(gid, root)
            has_analysis = analysis is not None
            has_review = has_analysis and analysis.get("human_review") is not None
            
            # Filter by status
            if args.needs_analysis and has_analysis:
                continue
            if args.needs_review and (not has_analysis or has_review):
                continue
            
            active = get_active_flags(flags)
            flagged_guidelines.append({
                "guideline_id": gid,
                "batch": batch,
                "flag_count": len(active),
                "active_flags": active,
                "has_analysis": has_analysis,
                "has_review": has_review,
            })
    
    # Sort by flag count (most flagged first)
    flagged_guidelines.sort(key=lambda x: (-x["flag_count"], x["guideline_id"]))
    
    # Print results
    if not flagged_guidelines:
        print("No pending outliers found matching criteria.")
        return
    
    # Summary by status
    needs_analysis_count = sum(1 for g in flagged_guidelines if not g["has_analysis"])
    needs_review_count = sum(1 for g in flagged_guidelines if g["has_analysis"] and not g["has_review"])
    fully_reviewed_count = sum(1 for g in flagged_guidelines if g["has_review"])
    
    print(f"Found {len(flagged_guidelines)} flagged guidelines:")
    print(f"  Needs analysis: {needs_analysis_count}")
    print(f"  Needs review: {needs_review_count}")
    print(f"  Fully reviewed: {fully_reviewed_count}")
    print()
    
    # Flag distribution
    flag_counts: dict[str, int] = defaultdict(int)
    for g in flagged_guidelines:
        for flag in g["active_flags"]:
            flag_counts[flag] += 1
    
    print("Flag distribution:")
    for flag, count in sorted(flag_counts.items(), key=lambda x: -x[1]):
        print(f"  {flag}: {count}")
    print()
    
    # Show guidelines
    shown = min(len(flagged_guidelines), args.limit)
    print(f"Guidelines ({shown}/{len(flagged_guidelines)}):")
    print()
    
    for g in flagged_guidelines[:args.limit]:
        status = "✓ reviewed" if g["has_review"] else ("◐ analyzed" if g["has_analysis"] else "○ pending")
        print(f"  {g['guideline_id']} (batch {g['batch']}) [{status}]")
        if args.verbose:
            print(f"    Flags ({g['flag_count']}): {', '.join(g['active_flags'])}")
    
    if len(flagged_guidelines) > args.limit:
        print(f"\n  ... and {len(flagged_guidelines) - args.limit} more")


if __name__ == "__main__":
    main()
