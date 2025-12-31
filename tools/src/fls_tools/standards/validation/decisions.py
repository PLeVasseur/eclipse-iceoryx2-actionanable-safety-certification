#!/usr/bin/env python3
"""
validate_decisions.py - Validate decision files in a decisions directory.

This tool validates individual guideline verification decision files used in the
parallel verification workflow.

Validation checks:
1. Schema validation against decision_file.schema.json
2. Filename-to-guideline_id consistency (Dir_1.1.json should contain "Dir 1.1")
3. No duplicate guideline_ids across files
4. FLS ID format validity
5. Non-empty reason fields on matches
6. If --batch-report provided: verify guideline_ids exist in batch

Usage:
    uv run validate-decisions \\
        --decisions-dir cache/verification/batch4_decisions/

    uv run validate-decisions \\
        --decisions-dir cache/verification/batch4_decisions/ \\
        --batch-report cache/verification/batch4_session6.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema

from fls_tools.shared import get_project_root, get_coding_standards_dir


def load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return None


def load_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        print(f"WARNING: Decision file schema not found: {schema_path}", file=sys.stderr)
        return None
    return load_json(schema_path)


def guideline_id_to_filename(guideline_id: str) -> str:
    """Convert guideline ID to expected filename."""
    return guideline_id.replace(" ", "_") + ".json"


def filename_to_guideline_id(filename: str) -> str:
    """Convert filename back to guideline ID."""
    # Remove .json extension and replace underscores with spaces
    base = filename.rsplit(".json", 1)[0]
    return base.replace("_", " ")


def validate_decision_file(
    path: Path,
    schema: dict | None,
    batch_guideline_ids: set[str] | None = None,
) -> tuple[bool, list[str], dict | None]:
    """
    Validate a single decision file.
    
    Returns:
        (is_valid, errors, parsed_data)
    """
    errors = []
    
    # Load file
    data = load_json(path)
    if data is None:
        errors.append(f"Failed to parse JSON")
        return False, errors, None
    
    # Schema validation
    if schema:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema error: {e.message}")
            if e.path:
                errors.append(f"  Path: {'.'.join(str(p) for p in e.path)}")
    
    # Filename consistency
    expected_filename = guideline_id_to_filename(data.get("guideline_id", ""))
    if path.name != expected_filename:
        errors.append(
            f"Filename mismatch: file is '{path.name}' but guideline_id suggests '{expected_filename}'"
        )
    
    # Check guideline exists in batch report
    if batch_guideline_ids is not None:
        gid = data.get("guideline_id")
        if gid and gid not in batch_guideline_ids:
            errors.append(f"Guideline '{gid}' not found in batch report")
    
    # Validate FLS IDs format
    fls_id_pattern = re.compile(r"^fls_[a-zA-Z0-9]+$")
    for match_type in ["accepted_matches", "rejected_matches"]:
        for i, match in enumerate(data.get(match_type, [])):
            fls_id = match.get("fls_id", "")
            if not fls_id_pattern.match(fls_id):
                errors.append(f"{match_type}[{i}]: Invalid fls_id format '{fls_id}'")
            
            # Check reason is non-empty (schema enforces minLength but double-check)
            reason = match.get("reason", "")
            if not reason or not reason.strip():
                errors.append(f"{match_type}[{i}]: Empty reason field")
    
    is_valid = len(errors) == 0
    return is_valid, errors, data


def validate_decisions_directory(
    decisions_dir: Path,
    schema: dict | None,
    batch_report_path: Path | None = None,
) -> tuple[int, int, list[tuple[str, list[str]]], set[str]]:
    """
    Validate all decision files in a directory.
    
    Returns:
        (valid_count, invalid_count, errors_by_file, guideline_ids)
    """
    # Load batch report for cross-reference if provided
    batch_guideline_ids = None
    if batch_report_path and batch_report_path.exists():
        batch_report = load_json(batch_report_path)
        if batch_report:
            batch_guideline_ids = {
                g["guideline_id"] for g in batch_report.get("guidelines", [])
            }
    
    # Find all decision files
    decision_files = sorted(decisions_dir.glob("*.json"))
    
    valid_count = 0
    invalid_count = 0
    errors_by_file = []
    all_guideline_ids = set()
    guideline_id_to_file = {}
    
    for path in decision_files:
        is_valid, errors, data = validate_decision_file(path, schema, batch_guideline_ids)
        
        if data:
            gid = data.get("guideline_id")
            if gid:
                # Check for duplicates
                if gid in all_guideline_ids:
                    errors.append(
                        f"Duplicate guideline_id '{gid}' - also in {guideline_id_to_file[gid]}"
                    )
                    is_valid = False
                else:
                    all_guideline_ids.add(gid)
                    guideline_id_to_file[gid] = path.name
        
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1
            errors_by_file.append((path.name, errors))
    
    return valid_count, invalid_count, errors_by_file, all_guideline_ids


def main():
    parser = argparse.ArgumentParser(
        description="Validate decision files in a decisions directory"
    )
    parser.add_argument(
        "--decisions-dir",
        type=str,
        required=True,
        help="Path to the decisions directory",
    )
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to batch report for cross-reference validation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show details for valid files too",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Resolve paths
    decisions_dir = Path(args.decisions_dir)
    if not decisions_dir.is_absolute():
        decisions_dir = root / decisions_dir
    
    batch_report_path = None
    if args.batch_report:
        batch_report_path = Path(args.batch_report)
        if not batch_report_path.is_absolute():
            batch_report_path = root / batch_report_path
    
    # Check directory exists
    if not decisions_dir.exists():
        print(f"ERROR: Decisions directory not found: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not decisions_dir.is_dir():
        print(f"ERROR: Not a directory: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Load schema
    schema = load_schema(root)
    
    # Validate
    print(f"Validating decisions in {decisions_dir}")
    print()
    
    valid_count, invalid_count, errors_by_file, guideline_ids = validate_decisions_directory(
        decisions_dir, schema, batch_report_path
    )
    
    total_count = valid_count + invalid_count
    
    if total_count == 0:
        print("No decision files found.")
        sys.exit(0)
    
    # Print results
    print(f"Found {total_count} decision files")
    print()
    
    if errors_by_file:
        print("Validation errors:")
        for filename, errors in errors_by_file:
            print(f"  {filename}:")
            for error in errors:
                print(f"    - {error}")
        print()
    
    # Cross-reference with batch report
    if batch_report_path and batch_report_path.exists():
        batch_report = load_json(batch_report_path)
        if batch_report:
            batch_guidelines = {g["guideline_id"] for g in batch_report.get("guidelines", [])}
            missing = batch_guidelines - guideline_ids
            extra = guideline_ids - batch_guidelines
            
            print("Cross-reference with batch report:")
            print(f"  Batch guidelines: {len(batch_guidelines)}")
            print(f"  Decisions found: {len(guideline_ids)}")
            print(f"  Coverage: {len(guideline_ids)}/{len(batch_guidelines)} ({100*len(guideline_ids)/len(batch_guidelines):.0f}%)")
            if missing:
                print(f"  Pending: {len(missing)} guidelines")
            if extra:
                print(f"  Extra (not in batch): {len(extra)}")
            print()
    
    # Summary
    print("Summary:")
    print(f"  Valid: {valid_count}/{total_count}")
    print(f"  Invalid: {invalid_count}/{total_count}")
    
    if invalid_count > 0:
        print()
        print("Validation FAILED")
        sys.exit(1)
    else:
        print()
        print("Validation PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
