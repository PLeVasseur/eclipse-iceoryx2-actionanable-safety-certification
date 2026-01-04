#!/usr/bin/env python3
"""
reset_verification.py - Reset All Verification State for a Standard

This tool resets all verification state to allow re-verification of all guidelines.
It performs two operations:

1. Resets `confidence` from "high" to "medium" for all entries in the mapping file
2. Regenerates the progress.json file via scaffold-progress --force

Usage:
    # Reset all MISRA C verification state
    uv run reset-verification --standard misra-c

    # Preview changes without writing
    uv run reset-verification --standard misra-c --dry-run

    # Also delete cached batch reports
    uv run reset-verification --standard misra-c --delete-cache
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_standard_mappings_path,
    get_verification_cache_dir,
    get_verification_progress_path,
    VALID_STANDARDS,
)


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save a JSON file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def reset_mappings(root: Path, standard: str, dry_run: bool) -> tuple[int, int, int]:
    """
    Reset confidence from 'high' to 'medium' for all entries in the mapping file.
    
    Handles both v1 (top-level confidence) and v2/v3 (per-context confidence) formats.
    
    Returns:
        Tuple of (total_entries, v1_reset_count, v2_context_reset_count)
    """
    mappings_path = get_standard_mappings_path(root, standard)
    
    if not mappings_path.exists():
        print(f"Mappings file not found: {mappings_path}")
        return 0, 0, 0
    
    data = load_json(mappings_path)
    mappings = data.get("mappings", [])
    
    total = len(mappings)
    v1_reset_count = 0
    v2_context_reset_count = 0
    
    for m in mappings:
        # v1 format: top-level confidence
        if m.get("confidence") == "high":
            if not dry_run:
                m["confidence"] = "medium"
            v1_reset_count += 1
        
        # v2/v3 format: per-context confidence
        for context in ("all_rust", "safe_rust"):
            ctx = m.get(context)
            if isinstance(ctx, dict) and ctx.get("confidence") == "high":
                if not dry_run:
                    ctx["confidence"] = "medium"
                v2_context_reset_count += 1
    
    if not dry_run and (v1_reset_count > 0 or v2_context_reset_count > 0):
        save_json(mappings_path, data)
    
    return total, v1_reset_count, v2_context_reset_count


def regenerate_progress(root: Path, standard: str, dry_run: bool) -> bool:
    """
    Regenerate the progress.json file via scaffold-progress --force.
    
    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        print("Would regenerate progress.json via scaffold-progress --force")
        return True
    
    try:
        result = subprocess.run(
            ["uv", "run", "scaffold-progress", "--standard", standard, "--force"],
            cwd=root / "tools",
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            print(f"ERROR: scaffold-progress failed:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return False
        
        print("Regenerated progress.json")
        return True
    
    except Exception as e:
        print(f"ERROR: Failed to run scaffold-progress: {e}", file=sys.stderr)
        return False


def delete_cache(root: Path, standard: str, dry_run: bool) -> int:
    """
    Delete all cached verification artifacts.
    
    Returns:
        Number of items deleted
    """
    cache_dir = get_verification_cache_dir(root, standard)
    
    if not cache_dir.exists():
        print(f"Cache directory does not exist: {cache_dir}")
        return 0
    
    # Count items
    items = list(cache_dir.glob("*"))
    count = len(items)
    
    if count == 0:
        print("Cache directory is empty")
        return 0
    
    if dry_run:
        print(f"Would delete {count} item(s) from {cache_dir}:")
        for item in items[:10]:
            print(f"  - {item.name}")
        if count > 10:
            print(f"  ... and {count - 10} more")
        return count
    
    # Delete each item
    for item in items:
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    
    print(f"Deleted {count} item(s) from {cache_dir}")
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Reset all verification state for a standard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Reset all MISRA C verification state
    uv run reset-verification --standard misra-c

    # Preview changes without writing
    uv run reset-verification --standard misra-c --dry-run

    # Also delete cached batch reports
    uv run reset-verification --standard misra-c --delete-cache
        """
    )
    
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard to reset (e.g., misra-c, cert-cpp)",
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be reset without making changes",
    )
    
    parser.add_argument(
        "--delete-cache",
        action="store_true",
        help="Also delete cached batch reports and decision files",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    if args.dry_run:
        print("DRY RUN - No changes will be made\n")
    
    print(f"Resetting verification state for: {args.standard}")
    print()
    
    # Step 1: Reset mappings
    print("Step 1: Resetting confidence in mappings file...")
    mappings_path = get_standard_mappings_path(root, args.standard)
    print(f"  File: {mappings_path}")
    
    total, v1_reset_count, v2_context_reset_count = reset_mappings(root, args.standard, args.dry_run)
    
    if total == 0:
        print("  No mappings found")
    else:
        action = "Would reset" if args.dry_run else "Reset"
        if v1_reset_count > 0:
            print(f"  {action} {v1_reset_count}/{total} v1 entries (top-level confidence)")
        if v2_context_reset_count > 0:
            print(f"  {action} {v2_context_reset_count} v2/v3 per-context confidence fields")
        if v1_reset_count == 0 and v2_context_reset_count == 0:
            print(f"  No entries with 'high' confidence found (0/{total})")
    
    print()
    
    # Step 2: Regenerate progress
    print("Step 2: Regenerating progress.json...")
    progress_path = get_verification_progress_path(root, args.standard)
    print(f"  File: {progress_path}")
    
    if not regenerate_progress(root, args.standard, args.dry_run):
        print("  ERROR: Failed to regenerate progress file")
        sys.exit(1)
    
    print()
    
    # Step 3: Delete cache (optional)
    if args.delete_cache:
        print("Step 3: Deleting cached verification artifacts...")
        cache_dir = get_verification_cache_dir(root, args.standard)
        print(f"  Directory: {cache_dir}")
        delete_cache(root, args.standard, args.dry_run)
        print()
    
    # Summary
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN COMPLETE - No changes were made")
        print()
        print("Run without --dry-run to apply changes:")
        cmd = f"uv run reset-verification --standard {args.standard}"
        if args.delete_cache:
            cmd += " --delete-cache"
        print(f"  {cmd}")
    else:
        print("RESET COMPLETE")
        print()
        print("Next steps:")
        print(f"  1. Run: uv run check-progress --standard {args.standard}")
        print(f"  2. Start verification with: uv run verify-batch --standard {args.standard} --batch 1 --session 1")


if __name__ == "__main__":
    main()
