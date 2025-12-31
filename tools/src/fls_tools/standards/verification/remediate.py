#!/usr/bin/env python3
"""
remediate_decisions.py - Add search_tools_used to existing decision files.

This tool adds search_tools_used (either reconstructed search history or waivers)
to existing decision files that were created before search tracking was required.

Usage:
    # Add waivers to all decision files (using --batch for correct path resolution)
    uv run remediate-decisions \\
        --batch 4 \\
        --waiver "legacy_decision:PLeVasseur:2026-01-01:Decision made before search tracking"

    # Add reconstructed search history to a specific decision
    uv run remediate-decisions \\
        --batch 4 \\
        --guideline "Dir 4.7" \\
        --search "search-fls:error handling Result Option:10" \\
        --search "read-fls-chapter:chapter_16.json"

    # Dry run to see what would be changed
    uv run remediate-decisions \\
        --batch 4 \\
        --waiver "legacy_decision:PLeVasseur:2026-01-01" \\
        --dry-run

    # List decisions missing search_tools_used
    uv run remediate-decisions \\
        --batch 4 \\
        --list-missing
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_batch_decisions_dir,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
)


VALID_SEARCH_TOOLS = ["search-fls", "search-fls-deep", "recompute-similarity", "read-fls-chapter", "grep-fls"]
VALID_WAIVER_REASONS = ["legacy_decision", "batch_report_sufficient", "manual_fls_review"]


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save a JSON file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def parse_search(search_str: str) -> dict:
    """Parse a search string into a search_tool_usage object."""
    parts = search_str.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid search format: '{search_str}'. Expected 'tool:query[:result_count]'")
    
    tool, query = parts[0], parts[1]
    if tool not in VALID_SEARCH_TOOLS:
        raise ValueError(f"Invalid tool '{tool}'. Must be one of: {', '.join(VALID_SEARCH_TOOLS)}")
    
    entry: dict = {"tool": tool, "query": query}
    if len(parts) == 3:
        try:
            entry["result_count"] = int(parts[2])
        except ValueError:
            raise ValueError(f"Invalid result_count '{parts[2]}'. Must be integer.")
    
    return entry


def parse_waiver(waiver_str: str) -> dict:
    """Parse a waiver string into a search_waiver object."""
    parts = waiver_str.split(":", 3)
    if len(parts) < 3:
        raise ValueError(f"Invalid waiver format: '{waiver_str}'. Expected 'reason:approved_by:approval_date[:notes]'")
    
    reason, approved_by, approval_date = parts[0], parts[1], parts[2]
    
    if reason not in VALID_WAIVER_REASONS:
        raise ValueError(f"Invalid waiver reason '{reason}'. Must be one of: {', '.join(VALID_WAIVER_REASONS)}")
    
    try:
        datetime.strptime(approval_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format '{approval_date}'. Expected YYYY-MM-DD")
    
    result = {
        "waiver_reason": reason,
        "approved_by": approved_by,
        "approval_date": approval_date,
    }
    
    if len(parts) == 4:
        result["notes"] = parts[3]
    
    return result


def get_decision_files(decisions_dir: Path) -> list[Path]:
    """Get all JSON decision files in the directory."""
    if not decisions_dir.exists():
        return []
    return sorted(decisions_dir.glob("*.json"))


def needs_remediation(decision: dict) -> bool:
    """Check if a decision file needs remediation (missing search_tools_used)."""
    return "search_tools_used" not in decision or decision.get("search_tools_used") is None


def main():
    parser = argparse.ArgumentParser(
        description="Add search_tools_used to existing decision files"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Batch number - auto-resolves to cache/verification/batch{N}_decisions/",
    )
    parser.add_argument(
        "--decisions-dir",
        type=str,
        default=None,
        help="Path to directory containing decision files (use --batch instead when possible)",
    )
    parser.add_argument(
        "--guideline",
        type=str,
        default=None,
        help="Specific guideline ID to remediate (default: all files)",
    )
    parser.add_argument(
        "--waiver",
        type=str,
        default=None,
        help="Waiver to add (format: reason:approved_by:approval_date[:notes])",
    )
    parser.add_argument(
        "--search",
        action="append",
        default=[],
        help="Search tool usage to add (format: tool:query[:result_count]). Repeatable.",
    )
    parser.add_argument(
        "--list-missing",
        action="store_true",
        help="List decision files missing search_tools_used",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing files",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Determine decisions directory
    if args.batch is not None and args.decisions_dir is not None:
        print("ERROR: Cannot specify both --batch and --decisions-dir", file=sys.stderr)
        sys.exit(1)
    
    if args.batch is None and args.decisions_dir is None:
        print("ERROR: Either --batch or --decisions-dir must be provided", file=sys.stderr)
        sys.exit(1)
    
    if args.batch is not None:
        decisions_dir = get_batch_decisions_dir(root, args.batch)
    else:
        # Resolve the path correctly (don't use root / relative_path)
        decisions_dir = resolve_path(Path(args.decisions_dir))
        
        # Validate it's within the project
        try:
            decisions_dir = validate_path_in_project(decisions_dir, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    if not decisions_dir.exists():
        print(f"ERROR: Decisions directory not found: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Get decision files
    decision_files = get_decision_files(decisions_dir)
    if not decision_files:
        print(f"No decision files found in {decisions_dir}")
        sys.exit(0)
    
    # Filter to specific guideline if requested
    if args.guideline:
        filename = args.guideline.replace(" ", "_") + ".json"
        decision_files = [f for f in decision_files if f.name == filename]
        if not decision_files:
            print(f"ERROR: Decision file not found for guideline '{args.guideline}'", file=sys.stderr)
            sys.exit(1)
    
    # List missing mode
    if args.list_missing:
        missing = []
        for df in decision_files:
            decision = load_json(df)
            if needs_remediation(decision):
                missing.append(df.stem.replace("_", " "))
        
        if missing:
            print(f"Decision files missing search_tools_used ({len(missing)}):")
            for g in missing:
                print(f"  - {g}")
        else:
            print("All decision files have search_tools_used")
        sys.exit(0)
    
    # Validate that we have something to add
    if not args.waiver and not args.search:
        print("ERROR: Either --waiver or --search must be provided", file=sys.stderr)
        print("  Use --list-missing to see which files need remediation", file=sys.stderr)
        sys.exit(1)
    
    if args.waiver and args.search:
        print("ERROR: Cannot specify both --waiver and --search", file=sys.stderr)
        sys.exit(1)
    
    # Parse search_tools_used value
    search_tools_used = None
    if args.waiver:
        try:
            search_tools_used = parse_waiver(args.waiver)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            search_tools_used = [parse_search(s) for s in args.search]
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Process files
    updated = 0
    skipped = 0
    
    for df in decision_files:
        decision = load_json(df)
        guideline_id = decision.get("guideline_id", df.stem)
        
        if not needs_remediation(decision):
            skipped += 1
            if not args.guideline:  # Only print if processing all
                print(f"  SKIP: {guideline_id} (already has search_tools_used)")
            continue
        
        # Add search_tools_used
        decision["search_tools_used"] = search_tools_used
        
        if args.dry_run:
            print(f"  DRY RUN: Would update {guideline_id}")
            if isinstance(search_tools_used, list):
                print(f"    Search tools: {len(search_tools_used)}")
                for s in search_tools_used:
                    print(f"      - {s['tool']}: {s['query']}")
            else:
                print(f"    Waiver: {search_tools_used['waiver_reason']}")
                print(f"    Approved by: {search_tools_used['approved_by']}")
        else:
            save_json(df, decision)
            print(f"  UPDATED: {guideline_id}")
        
        updated += 1
    
    # Summary
    print()
    if args.dry_run:
        print(f"DRY RUN Summary: Would update {updated}, skip {skipped}")
    else:
        print(f"Summary: Updated {updated}, skipped {skipped}")


if __name__ == "__main__":
    main()
