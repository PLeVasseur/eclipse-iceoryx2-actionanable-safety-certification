#!/usr/bin/env python3
"""
reset-review - Clear human review decisions from outlier analysis files.

This tool removes the `human_review` section from outlier analysis files,
allowing them to be re-reviewed without losing the LLM analysis.

Usage:
    # Reset a single guideline
    uv run reset-review --standard misra-c --guideline "Rule 10.1"

    # Reset all guidelines in a batch
    uv run reset-review --standard misra-c --batch 1

    # Reset all guidelines across all batches
    uv run reset-review --standard misra-c --all --force

    # Preview what would be reset without making changes
    uv run reset-review --standard misra-c --batch 1 --dry-run
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    get_outlier_analysis_dir,
    get_review_state_path,
    load_outlier_analysis,
    save_outlier_analysis,
    load_review_state,
    save_json_file,
    guideline_to_filename,
    filename_to_guideline,
)


def reset_guideline(guideline_id: str, root: Path, dry_run: bool = False) -> bool:
    """
    Reset human review for a single guideline.
    
    Returns True if the file was modified (or would be modified in dry_run).
    """
    analysis = load_outlier_analysis(guideline_id, root)
    if analysis is None:
        print(f"  WARNING: No analysis file found for {guideline_id}", file=sys.stderr)
        return False
    
    if analysis.get("human_review") is None:
        print(f"  {guideline_id}: no human_review to reset (already null)")
        return False
    
    if dry_run:
        print(f"  {guideline_id}: would reset human_review")
        return True
    
    # Reset human_review to null
    analysis["human_review"] = None
    save_outlier_analysis(guideline_id, analysis, root)
    print(f"  {guideline_id}: reset human_review")
    return True


def get_guidelines_in_batch(batch: int, root: Path) -> list[str]:
    """Get all guideline IDs in a specific batch."""
    outlier_dir = get_outlier_analysis_dir(root)
    guidelines = []
    
    for path in outlier_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("batch") == batch:
                guidelines.append(data.get("guideline_id"))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(guidelines)


def get_all_guidelines(root: Path) -> list[str]:
    """Get all guideline IDs from outlier analysis files."""
    outlier_dir = get_outlier_analysis_dir(root)
    guidelines = []
    
    for path in outlier_dir.glob("*.json"):
        guideline_id = filename_to_guideline(path.stem)
        guidelines.append(guideline_id)
    
    return sorted(guidelines)


def update_review_state(root: Path, reset_count: int, dry_run: bool = False) -> None:
    """Update review_state.json to reflect reset."""
    if dry_run:
        return
    
    state = load_review_state(root)
    state["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    # Decrement counts (rough approximation - full recompute would be more accurate)
    # For now, just note that a reset occurred
    if "reset_log" not in state:
        state["reset_log"] = []
    
    state["reset_log"].append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "count": reset_count,
    })
    
    save_json_file(get_review_state_path(root), state)


def main():
    parser = argparse.ArgumentParser(
        description="Clear human review decisions from outlier analysis files."
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c)",
    )
    
    # Scope selection (mutually exclusive)
    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument(
        "--guideline",
        help="Reset a single guideline (e.g., 'Rule 10.1')",
    )
    scope_group.add_argument(
        "--batch",
        type=int,
        help="Reset all guidelines in a specific batch",
    )
    scope_group.add_argument(
        "--all",
        action="store_true",
        help="Reset all guidelines across all batches",
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Required for --all to prevent accidental full reset",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be reset without saving",
    )
    
    args = parser.parse_args()
    
    standard = normalize_standard(args.standard)
    root = get_project_root()
    
    # Safety check for --all
    if args.all and not args.force:
        print("ERROR: --all requires --force to confirm intent", file=sys.stderr)
        print("  This will reset ALL human review decisions.", file=sys.stderr)
        sys.exit(1)
    
    # Determine which guidelines to reset
    if args.guideline:
        guidelines = [args.guideline]
        scope_desc = f"guideline {args.guideline}"
    elif args.batch:
        guidelines = get_guidelines_in_batch(args.batch, root)
        scope_desc = f"batch {args.batch} ({len(guidelines)} guidelines)"
    else:  # args.all
        guidelines = get_all_guidelines(root)
        scope_desc = f"all batches ({len(guidelines)} guidelines)"
    
    if not guidelines:
        print(f"No guidelines found for {scope_desc}", file=sys.stderr)
        sys.exit(1)
    
    # Show what will be reset
    if args.dry_run:
        print(f"DRY RUN: Would reset human_review for {scope_desc}")
    else:
        print(f"Resetting human_review for {scope_desc}")
    
    # Reset each guideline
    reset_count = 0
    for guideline_id in guidelines:
        if reset_guideline(guideline_id, root, args.dry_run):
            reset_count += 1
    
    # Update review state
    if reset_count > 0 and not args.dry_run:
        update_review_state(root, reset_count)
    
    # Summary
    print()
    if args.dry_run:
        print(f"Would reset {reset_count}/{len(guidelines)} guidelines")
    else:
        print(f"Reset {reset_count}/{len(guidelines)} guidelines")


if __name__ == "__main__":
    main()
