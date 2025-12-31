#!/usr/bin/env python3
"""
merge_decisions.py - Merge per-guideline decision files into a batch report.

This tool merges individual decision files from a decisions directory back into
a batch report for Phase 3 review. Supports incremental merging (can merge
partial progress).

Features:
- Merges all valid decision files from a directory
- Populates verification_decision fields in batch report
- Aggregates proposed_applicability_change entries to top-level array
- Updates summary statistics
- Optionally validates decision files before merging

Usage:
    # Using --batch for automatic path resolution (recommended):
    uv run merge-decisions --batch 4 --session 6

    # With validation:
    uv run merge-decisions --batch 4 --session 6 --validate

    # Dry run:
    uv run merge-decisions --batch 4 --session 6 --dry-run

    # Using explicit paths (use absolute paths):
    uv run merge-decisions \\
        --batch-report /path/to/batch4_session6.json \\
        --decisions-dir /path/to/batch4_decisions/
"""

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_coding_standards_dir,
    get_batch_decisions_dir,
    get_batch_report_path,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
)


def load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: dict) -> None:
    """Save a JSON file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_decision_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        return None
    return load_json(schema_path)


def validate_decision(decision: dict, schema: dict) -> list[str]:
    """Validate a decision against the schema. Returns list of errors."""
    errors = []
    try:
        jsonschema.validate(instance=decision, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema error: {e.message}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema definition error: {e.message}")
    return errors


def find_guideline_index(report: dict, guideline_id: str) -> int | None:
    """Find guideline index in report by ID."""
    for i, g in enumerate(report.get("guidelines", [])):
        if g.get("guideline_id") == guideline_id:
            return i
    return None


def update_summary(report: dict) -> None:
    """Update the batch report summary statistics."""
    guidelines = report.get("guidelines", [])
    verified_count = sum(
        1 for g in guidelines
        if g.get("verification_decision") and g["verification_decision"].get("decision")
    )
    
    changes = report.get("applicability_changes", [])
    changes_proposed = len(changes)
    changes_approved = sum(1 for c in changes if c.get("approved") is True)
    
    report["summary"] = {
        "total_guidelines": len(guidelines),
        "verified_count": verified_count,
        "applicability_changes_proposed": changes_proposed,
        "applicability_changes_approved": changes_approved,
    }


def load_decision_files(
    decisions_dir: Path,
    schema: dict | None = None,
    validate: bool = False,
) -> tuple[list[dict], list[tuple[str, list[str]]]]:
    """
    Load all decision files from a directory.
    
    Returns:
        (valid_decisions, errors_by_file)
    """
    decision_files = sorted(decisions_dir.glob("*.json"))
    
    valid_decisions = []
    errors_by_file = []
    
    for path in decision_files:
        decision = load_json(path)
        if decision is None:
            errors_by_file.append((path.name, ["Failed to parse JSON"]))
            continue
        
        errors = []
        
        # Schema validation
        if validate and schema:
            errors.extend(validate_decision(decision, schema))
        
        # Filename consistency check
        expected_filename = decision.get("guideline_id", "").replace(" ", "_") + ".json"
        if path.name != expected_filename:
            errors.append(
                f"Filename mismatch: file is '{path.name}' but guideline_id suggests '{expected_filename}'"
            )
        
        if errors:
            errors_by_file.append((path.name, errors))
        else:
            valid_decisions.append(decision)
    
    return valid_decisions, errors_by_file


def merge_decisions_into_report(
    report: dict,
    decisions: list[dict],
) -> tuple[int, int, list[str]]:
    """
    Merge decisions into a batch report.
    
    Returns:
        (merged_count, skipped_count, skipped_guidelines)
    """
    merged_count = 0
    skipped_count = 0
    skipped_guidelines = []
    
    # Track existing applicability changes by (guideline_id, field)
    existing_changes = {
        (c["guideline_id"], c["field"]): i
        for i, c in enumerate(report.get("applicability_changes", []))
    }
    
    for decision in decisions:
        guideline_id = decision.get("guideline_id")
        if not guideline_id:
            skipped_count += 1
            skipped_guidelines.append("(missing guideline_id)")
            continue
        
        # Find guideline in report
        idx = find_guideline_index(report, guideline_id)
        if idx is None:
            skipped_count += 1
            skipped_guidelines.append(guideline_id)
            continue
        
        # Build verification_decision from decision file
        verification_decision = {
            "decision": decision.get("decision"),
            "confidence": decision.get("confidence"),
            "fls_rationale_type": decision.get("fls_rationale_type"),
            "accepted_matches": decision.get("accepted_matches", []),
            "rejected_matches": decision.get("rejected_matches", []),
            "notes": decision.get("notes"),
        }
        
        # Handle proposed applicability change
        proposed_change = decision.get("proposed_applicability_change")
        if proposed_change:
            verification_decision["proposed_applicability_change"] = proposed_change
            
            # Add to top-level applicability_changes array
            change_entry = {
                "guideline_id": guideline_id,
                "field": proposed_change["field"],
                "current_value": proposed_change["current_value"],
                "proposed_value": proposed_change["proposed_value"],
                "rationale": proposed_change["rationale"],
                "approved": None,  # Pending human review
            }
            
            key = (guideline_id, proposed_change["field"])
            if key in existing_changes:
                # Update existing entry
                report["applicability_changes"][existing_changes[key]] = change_entry
            else:
                # Add new entry
                if "applicability_changes" not in report:
                    report["applicability_changes"] = []
                report["applicability_changes"].append(change_entry)
                existing_changes[key] = len(report["applicability_changes"]) - 1
        
        # Update guideline in report
        report["guidelines"][idx]["verification_decision"] = verification_decision
        merged_count += 1
    
    return merged_count, skipped_count, skipped_guidelines


def main():
    parser = argparse.ArgumentParser(
        description="Merge per-guideline decision files into a batch report"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Batch number - auto-resolves paths to cache/verification/",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="Session number (required with --batch)",
    )
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to the batch report JSON file (use --batch instead when possible)",
    )
    parser.add_argument(
        "--decisions-dir",
        type=str,
        default=None,
        help="Path to the decisions directory (use --batch instead when possible)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate decision files against schema before merging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be merged without writing to file",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Determine paths - either from --batch or explicit paths
    use_batch_mode = args.batch is not None
    use_explicit_mode = args.batch_report is not None or args.decisions_dir is not None
    
    if use_batch_mode and use_explicit_mode:
        print("ERROR: Cannot mix --batch with --batch-report/--decisions-dir", file=sys.stderr)
        sys.exit(1)
    
    if not use_batch_mode and not use_explicit_mode:
        print("ERROR: Either --batch or --batch-report/--decisions-dir must be provided", file=sys.stderr)
        sys.exit(1)
    
    if use_batch_mode:
        if args.session is None:
            print("ERROR: --session is required with --batch", file=sys.stderr)
            sys.exit(1)
        report_path = get_batch_report_path(root, args.batch, args.session)
        decisions_dir = get_batch_decisions_dir(root, args.batch)
    else:
        # Explicit paths mode - both required
        if args.batch_report is None or args.decisions_dir is None:
            print("ERROR: Both --batch-report and --decisions-dir are required in explicit mode", file=sys.stderr)
            sys.exit(1)
        
        # Resolve paths correctly and validate
        try:
            report_path = resolve_path(Path(args.batch_report))
            report_path = validate_path_in_project(report_path, root)
            
            decisions_dir = resolve_path(Path(args.decisions_dir))
            decisions_dir = validate_path_in_project(decisions_dir, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Check paths exist
    if not report_path.exists():
        print(f"ERROR: Batch report not found: {report_path}", file=sys.stderr)
        sys.exit(1)
    
    if not decisions_dir.exists():
        print(f"ERROR: Decisions directory not found: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not decisions_dir.is_dir():
        print(f"ERROR: Not a directory: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Load batch report
    report = load_json(report_path)
    if report is None:
        print(f"ERROR: Failed to parse batch report: {report_path}", file=sys.stderr)
        sys.exit(1)
    
    # Load schema for validation
    schema = None
    if args.validate:
        schema = load_decision_schema(root)
        if schema is None:
            print("WARNING: Decision file schema not found, skipping validation", file=sys.stderr)
    
    # Load decision files
    print(f"Loading decision files from {decisions_dir}...")
    decisions, errors_by_file = load_decision_files(decisions_dir, schema, args.validate)
    
    if errors_by_file:
        print(f"\nValidation errors in {len(errors_by_file)} file(s):", file=sys.stderr)
        for filename, errors in errors_by_file:
            print(f"  {filename}:", file=sys.stderr)
            for error in errors:
                print(f"    - {error}", file=sys.stderr)
        
        if args.validate:
            print("\nERROR: Validation failed. Fix errors and retry.", file=sys.stderr)
            sys.exit(1)
        else:
            print("\nWARNING: Proceeding with valid files only.", file=sys.stderr)
    
    if not decisions:
        print("No valid decision files found.")
        sys.exit(0)
    
    print(f"Found {len(decisions)} valid decision file(s)")
    
    # Merge decisions
    print(f"\nMerging decisions into batch report...")
    merged_count, skipped_count, skipped_guidelines = merge_decisions_into_report(
        report, decisions
    )
    
    # Update summary
    update_summary(report)
    
    # Report results
    print(f"\nMerge results:")
    print(f"  Merged: {merged_count}")
    if skipped_count > 0:
        print(f"  Skipped (not in batch): {skipped_count}")
        for gid in skipped_guidelines:
            print(f"    - {gid}")
    
    # Report applicability changes
    changes = report.get("applicability_changes", [])
    pending_changes = [c for c in changes if c.get("approved") is None]
    if pending_changes:
        print(f"\nApplicability changes proposed: {len(pending_changes)}")
        for c in pending_changes:
            print(f"  - {c['guideline_id']}: {c['field']}: {c['current_value']} -> {c['proposed_value']}")
    
    # Summary
    summary = report.get("summary", {})
    total = summary.get("total_guidelines", 0)
    verified = summary.get("verified_count", 0)
    print(f"\nBatch summary:")
    print(f"  Total guidelines: {total}")
    print(f"  Verified: {verified}")
    print(f"  Pending: {total - verified}")
    
    if args.dry_run:
        print(f"\n[DRY RUN] No files were modified.")
    else:
        save_json(report_path, report)
        print(f"\nUpdated: {report_path}")


if __name__ == "__main__":
    main()
