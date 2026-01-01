#!/usr/bin/env python3
"""
reset_batch.py - Reset verification decisions for a batch

This tool resets verification decisions to allow re-verification of guidelines.
It can reset an entire batch or specific guidelines within a batch.

What it resets:
- In batch report (cache/verification/batchN_sessionM.json):
  - Sets verification_decision to null for affected guidelines
  - Clears applicability_changes array
- In verification_progress.json:
  - Sets status to "pending" for affected guidelines
  - Clears verified_date and session_id

Usage:
    # Reset all guidelines in batch 3
    uv run reset-batch --batch 3

    # Reset specific guidelines in batch 3
    uv run reset-batch --batch 3 --guidelines "Rule 22.1,Rule 22.2"

    # Preview changes without writing
    uv run reset-batch --batch 3 --dry-run

    # Specify a specific batch report file
    uv run reset-batch --batch 3 --batch-report ../cache/verification/batch3_session5.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_verification_progress_path,
    get_verification_cache_dir,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
    VALID_STANDARDS,
)


def find_batch_report(root: Path, standard: str, batch_id: int) -> Path | None:
    """Find the most recent batch report for a given batch ID."""
    cache_dir = get_verification_cache_dir(root, standard)
    if not cache_dir.exists():
        return None
    
    # Find all batch reports for this batch, sorted by session (descending)
    reports = sorted(
        cache_dir.glob(f"batch{batch_id}_session*.json"),
        key=lambda p: int(p.stem.split("session")[1]),
        reverse=True
    )
    
    return reports[0] if reports else None


def reset_batch_report(
    report_path: Path,
    guideline_ids: list[str] | None,
    dry_run: bool
) -> tuple[int, list[str]]:
    """
    Reset verification decisions in a batch report.
    
    Returns:
        Tuple of (count of reset guidelines, list of reset guideline IDs)
    """
    with open(report_path) as f:
        data = json.load(f)
    
    reset_ids = []
    
    for guideline in data.get("guidelines", []):
        gid = guideline.get("guideline_id")
        
        # If specific guidelines requested, only reset those
        if guideline_ids and gid not in guideline_ids:
            continue
        
        # Check if there's a verification decision to reset
        if guideline.get("verification_decision") is not None:
            reset_ids.append(gid)
            if not dry_run:
                guideline["verification_decision"] = None
    
    # Clear applicability_changes array
    if not dry_run and data.get("applicability_changes"):
        data["applicability_changes"] = []
    
    if not dry_run and reset_ids:
        with open(report_path, "w") as f:
            json.dump(data, f, indent=2)
    
    return len(reset_ids), reset_ids


def reset_verification_progress(
    root: Path,
    standard: str,
    batch_id: int,
    guideline_ids: list[str] | None,
    dry_run: bool
) -> tuple[int, list[str]]:
    """
    Reset verification status in verification_progress.json.
    
    Returns:
        Tuple of (count of reset guidelines, list of reset guideline IDs)
    """
    progress_path = get_verification_progress_path(root, standard)
    
    if not progress_path.exists():
        print(f"WARNING: verification_progress.json not found at {progress_path}")
        return 0, []
    
    with open(progress_path) as f:
        data = json.load(f)
    
    reset_ids = []
    
    # Find the batch
    for batch in data.get("batches", []):
        if batch.get("batch_id") != batch_id:
            continue
        
        for guideline in batch.get("guidelines", []):
            gid = guideline.get("guideline_id")
            
            # If specific guidelines requested, only reset those
            if guideline_ids and gid not in guideline_ids:
                continue
            
            # Reset if currently verified
            if guideline.get("status") == "verified":
                reset_ids.append(gid)
                if not dry_run:
                    guideline["status"] = "pending"
                    guideline["verified_date"] = None
                    guideline["session_id"] = None
        
        # Update batch status if we reset any guidelines
        if not dry_run and reset_ids:
            batch["status"] = "in_progress"
        
        break
    
    # Update summary counts
    if not dry_run and reset_ids:
        # Recompute summary
        total_verified = 0
        total_pending = 0
        by_batch = {}
        
        for batch in data.get("batches", []):
            bid = str(batch["batch_id"])
            verified = sum(1 for g in batch.get("guidelines", []) if g.get("status") == "verified")
            pending = sum(1 for g in batch.get("guidelines", []) if g.get("status") == "pending")
            total_verified += verified
            total_pending += pending
            by_batch[bid] = {"verified": verified, "pending": pending}
        
        data["summary"]["total_verified"] = total_verified
        data["summary"]["total_pending"] = total_pending
        data["summary"]["by_batch"] = by_batch
        data["summary"]["last_updated"] = datetime.now().isoformat()
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        
        with open(progress_path, "w") as f:
            json.dump(data, f, indent=2)
    
    return len(reset_ids), reset_ids


def main():
    parser = argparse.ArgumentParser(
        description="Reset verification decisions for a batch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Reset all guidelines in batch 3
    uv run reset-batch --standard misra-c --batch 3

    # Reset specific guidelines
    uv run reset-batch --standard misra-c --batch 3 --guidelines "Rule 22.1,Rule 22.2"

    # Preview changes
    uv run reset-batch --standard misra-c --batch 3 --dry-run
        """
    )
    
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard (e.g., misra-c, cert-cpp)",
    )
    
    parser.add_argument(
        "--batch", "-b",
        type=int,
        required=True,
        help="Batch ID to reset"
    )
    
    parser.add_argument(
        "--guidelines", "-g",
        type=str,
        default=None,
        help="Comma-separated list of guideline IDs to reset (default: all in batch)"
    )
    
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to specific batch report file (default: auto-detect most recent)"
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be reset without making changes"
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Parse guideline IDs if provided
    guideline_ids = None
    if args.guidelines:
        guideline_ids = [g.strip() for g in args.guidelines.split(",")]
    
    # Find or use specified batch report
    if args.batch_report:
        try:
            report_path = resolve_path(Path(args.batch_report))
            report_path = validate_path_in_project(report_path, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        report_path = find_batch_report(root, args.standard, args.batch)
    
    if args.dry_run:
        print("DRY RUN - No changes will be made\n")
    
    # Reset batch report if it exists
    report_reset_count = 0
    report_reset_ids = []
    if report_path and report_path.exists():
        print(f"Batch report: {report_path}")
        report_reset_count, report_reset_ids = reset_batch_report(
            report_path, guideline_ids, args.dry_run
        )
        if report_reset_ids:
            print(f"  Would reset {report_reset_count} verification decisions:" if args.dry_run 
                  else f"  Reset {report_reset_count} verification decisions:")
            for gid in report_reset_ids:
                print(f"    - {gid}")
        else:
            print("  No verification decisions to reset")
    else:
        print(f"No batch report found for batch {args.batch}")
    
    print()
    
    # Reset verification progress
    print(f"Verification progress: {get_verification_progress_path(root, args.standard)}")
    progress_reset_count, progress_reset_ids = reset_verification_progress(
        root, args.standard, args.batch, guideline_ids, args.dry_run
    )
    if progress_reset_ids:
        print(f"  Would reset {progress_reset_count} guidelines to pending:" if args.dry_run
              else f"  Reset {progress_reset_count} guidelines to pending:")
        for gid in progress_reset_ids:
            print(f"    - {gid}")
    else:
        print("  No guidelines to reset (none were verified)")
    
    print()
    
    # Summary
    total_reset = max(report_reset_count, progress_reset_count)
    if args.dry_run:
        print(f"Would reset {total_reset} guidelines in batch {args.batch}")
        print("\nRun without --dry-run to apply changes")
    else:
        print(f"Reset {total_reset} guidelines in batch {args.batch}")
        if report_path and report_path.exists():
            print(f"\nNext step: Re-run verification with:")
            print(f"  uv run verify-batch --standard {args.standard} --batch {args.batch} --session <NEW_SESSION_ID>")


if __name__ == "__main__":
    main()
