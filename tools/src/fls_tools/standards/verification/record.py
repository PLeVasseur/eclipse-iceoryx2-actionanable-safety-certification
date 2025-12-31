#!/usr/bin/env python3
"""
record_decision.py - Record a verification decision for a guideline.

This tool records verification decisions either:
1. In-place mode: Updates verification_decision field in a batch report
2. Per-guideline mode: Writes individual decision files (for parallel verification)

Features:
- Validates decisions against appropriate schema
- Supports accepted and rejected matches with full metadata
- Handles optional applicability change proposals
- Per-guideline mode enables parallel verification by multiple workers

Usage (in-place mode - updates batch report):
    uv run record-decision \\
        --batch-report cache/verification/batch4_session6.json \\
        --guideline "Dir 1.1" \\
        --decision accept_with_modifications \\
        --confidence high \\
        --rationale-type direct_mapping \\
        --accept-match "fls_abc123:Section Title:0:0.65:FLS states X which addresses MISRA concern Y"

Usage (per-guideline mode - parallel-safe):
    uv run record-decision \\
        --output-dir cache/verification/batch4_decisions/ \\
        --guideline "Dir 1.1" \\
        --decision accept_with_modifications \\
        --confidence high \\
        --rationale-type direct_mapping \\
        --accept-match "fls_abc123:Section Title:0:0.65:FLS states X which addresses MISRA concern Y"

    # Optionally include batch report for validation context:
    uv run record-decision \\
        --output-dir cache/verification/batch4_decisions/ \\
        --batch-report cache/verification/batch4_session6.json \\
        --guideline "Dir 1.1" \\
        ...

Match format: fls_id:fls_title:category:score:reason
  - fls_id: FLS identifier (e.g., fls_abc123)
  - fls_title: Human-readable title (e.g., "Type Cast Expressions")
  - category: Integer category code (0=section, -2=legality_rules, etc.)
  - score: Similarity score 0-1 (e.g., 0.65)
  - reason: Justification text (may contain colons)

Change format: field:current_value:proposed_value:rationale
  - field: applicability_all_rust, applicability_safe_rust, or fls_rationale_type
  - current_value: Current value of the field
  - proposed_value: Proposed new value
  - rationale: Justification (may contain colons)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from fls_tools.shared import get_project_root, get_coding_standards_dir


# Valid enum values from schema
VALID_DECISIONS = ["accept_with_modifications", "accept_no_matches", "accept_existing", "reject"]
VALID_CONFIDENCE = ["high", "medium", "low"]
VALID_RATIONALE_TYPES = [
    "direct_mapping",
    "rust_alternative",
    "rust_prevents",
    "no_equivalent",
    "partial_mapping",
]
VALID_CATEGORIES = [0, -1, -2, -3, -4, -5, -6, -7, -8]
VALID_CHANGE_FIELDS = ["applicability_all_rust", "applicability_safe_rust", "fls_rationale_type"]


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save a JSON file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_batch_report_schema(root: Path) -> dict | None:
    """Load the batch report schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "batch_report.schema.json"
    if not schema_path.exists():
        return None
    return load_json(schema_path)


def load_decision_file_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        return None
    return load_json(schema_path)


def guideline_id_to_filename(guideline_id: str) -> str:
    """Convert guideline ID to filename (spaces to underscores)."""
    return guideline_id.replace(" ", "_") + ".json"


def validate_report(report: dict, schema: dict) -> list[str]:
    """Validate a batch report against the schema. Returns list of errors."""
    errors = []
    try:
        jsonschema.validate(instance=report, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema validation error: {e.message}")
        if e.path:
            errors.append(f"  Path: {'.'.join(str(p) for p in e.path)}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema error: {e.message}")
    return errors


def parse_match(match_str: str) -> dict:
    """
    Parse a match string into a match dict.
    
    Format: fls_id:fls_title:category:score:reason
    The reason may contain colons, so we split from the left with maxsplit=4.
    """
    parts = match_str.split(":", 4)
    if len(parts) < 5:
        raise ValueError(
            f"Invalid match format: '{match_str}'. "
            f"Expected 'fls_id:fls_title:category:score:reason'"
        )
    
    fls_id, fls_title, category_str, score_str, reason = parts
    
    # Validate fls_id format
    if not fls_id.startswith("fls_"):
        raise ValueError(f"Invalid fls_id: '{fls_id}'. Must start with 'fls_'")
    
    # Parse and validate category
    try:
        category = int(category_str)
    except ValueError:
        raise ValueError(f"Invalid category: '{category_str}'. Must be an integer.")
    
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")
    
    # Parse and validate score
    try:
        score = float(score_str)
    except ValueError:
        raise ValueError(f"Invalid score: '{score_str}'. Must be a number.")
    
    if not (0 <= score <= 1):
        raise ValueError(f"Invalid score: {score}. Must be between 0 and 1.")
    
    return {
        "fls_id": fls_id,
        "fls_title": fls_title,
        "category": category,
        "score": round(score, 3),
        "reason": reason,
    }


def parse_applicability_change(change_str: str, guideline_id: str) -> dict:
    """
    Parse an applicability change string.
    
    Format: field:current_value:proposed_value:rationale
    The rationale may contain colons, so we split from the left with maxsplit=3.
    """
    parts = change_str.split(":", 3)
    if len(parts) < 4:
        raise ValueError(
            f"Invalid change format: '{change_str}'. "
            f"Expected 'field:current_value:proposed_value:rationale'"
        )
    
    field, current_value, proposed_value, rationale = parts
    
    if field not in VALID_CHANGE_FIELDS:
        raise ValueError(f"Invalid field: '{field}'. Must be one of {VALID_CHANGE_FIELDS}")
    
    return {
        "guideline_id": guideline_id,
        "field": field,
        "current_value": current_value,
        "proposed_value": proposed_value,
        "rationale": rationale,
        "approved": None,  # Pending human review
    }


def find_guideline(report: dict, guideline_id: str) -> tuple[int, dict] | None:
    """Find a guideline in the report by ID. Returns (index, guideline) or None."""
    for i, g in enumerate(report.get("guidelines", [])):
        if g.get("guideline_id") == guideline_id:
            return i, g
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


def validate_decision_file(decision: dict, schema: dict) -> list[str]:
    """Validate a decision file against the schema. Returns list of errors."""
    errors = []
    try:
        jsonschema.validate(instance=decision, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema validation error: {e.message}")
        if e.path:
            errors.append(f"  Path: {'.'.join(str(p) for p in e.path)}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema error: {e.message}")
    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Record a verification decision for a guideline"
    )
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to the batch report JSON file (required for in-place mode, optional for per-guideline mode)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Write decision to individual file in this directory (enables parallel mode)",
    )
    parser.add_argument(
        "--guideline",
        type=str,
        required=True,
        help="Guideline ID (e.g., 'Dir 1.1', 'Rule 10.1')",
    )
    parser.add_argument(
        "--decision",
        type=str,
        required=True,
        choices=VALID_DECISIONS,
        help="Verification decision type",
    )
    parser.add_argument(
        "--confidence",
        type=str,
        required=True,
        choices=VALID_CONFIDENCE,
        help="Confidence level in the decision",
    )
    parser.add_argument(
        "--rationale-type",
        type=str,
        required=True,
        choices=VALID_RATIONALE_TYPES,
        help="Type of FLS rationale",
    )
    parser.add_argument(
        "--accept-match",
        type=str,
        action="append",
        default=[],
        dest="accept_matches",
        help="Accepted FLS match (format: fls_id:fls_title:category:score:reason). Repeatable.",
    )
    parser.add_argument(
        "--reject-match",
        type=str,
        action="append",
        default=[],
        dest="reject_matches",
        help="Rejected FLS match (format: fls_id:fls_title:category:score:reason). Repeatable.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Additional notes about the decision",
    )
    parser.add_argument(
        "--propose-change",
        type=str,
        default=None,
        help="Propose applicability change (format: field:current:proposed:rationale)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be recorded without writing to file",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Determine mode: per-guideline (--output-dir) or in-place (--batch-report)
    per_guideline_mode = args.output_dir is not None
    
    if not per_guideline_mode and args.batch_report is None:
        print("ERROR: Either --output-dir or --batch-report must be provided", file=sys.stderr)
        sys.exit(1)
    
    # Resolve paths
    output_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = root / output_dir
    
    report_path = None
    report = None
    if args.batch_report:
        report_path = Path(args.batch_report)
        if not report_path.is_absolute():
            report_path = root / report_path
        
        if report_path.exists():
            report = load_json(report_path)
        elif not per_guideline_mode:
            # In-place mode requires batch report to exist
            print(f"ERROR: Batch report not found: {report_path}", file=sys.stderr)
            sys.exit(1)
    
    # Validate guideline exists in batch report (if available)
    if report:
        result = find_guideline(report, args.guideline)
        if result is None:
            if per_guideline_mode:
                print(f"WARNING: Guideline '{args.guideline}' not found in batch report", file=sys.stderr)
            else:
                print(f"ERROR: Guideline '{args.guideline}' not found in batch report", file=sys.stderr)
                available = [g["guideline_id"] for g in report.get("guidelines", [])[:10]]
                print(f"  Available guidelines (first 10): {available}", file=sys.stderr)
                sys.exit(1)
    
    # Parse matches
    try:
        accepted_matches = [parse_match(m) for m in args.accept_matches]
        rejected_matches = [parse_match(m) for m in args.reject_matches]
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Handle applicability change proposal
    proposed_change = None
    if args.propose_change:
        try:
            change_data = parse_applicability_change(args.propose_change, args.guideline)
            proposed_change = {
                "field": change_data["field"],
                "current_value": change_data["current_value"],
                "proposed_value": change_data["proposed_value"],
                "rationale": change_data["rationale"],
            }
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    if per_guideline_mode:
        # === PER-GUIDELINE MODE ===
        assert output_dir is not None
        
        # Build decision file
        decision_file = {
            "guideline_id": args.guideline,
            "decision": args.decision,
            "confidence": args.confidence,
            "fls_rationale_type": args.rationale_type,
            "accepted_matches": accepted_matches,
            "rejected_matches": rejected_matches,
            "notes": args.notes,
            "proposed_applicability_change": proposed_change,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Validate against decision file schema
        schema = load_decision_file_schema(root)
        if schema:
            errors = validate_decision_file(decision_file, schema)
            if errors:
                print("ERROR: Decision file fails schema validation:", file=sys.stderr)
                for err in errors:
                    print(f"  {err}", file=sys.stderr)
                sys.exit(1)
        
        # Prepare output path
        filename = guideline_id_to_filename(args.guideline)
        output_path = output_dir / filename
        
        # Output or save
        if args.dry_run:
            print("DRY RUN - Would write decision file:")
            print(f"  Path: {output_path}")
            print(f"  Guideline: {args.guideline}")
            print(f"  Decision: {args.decision}")
            print(f"  Confidence: {args.confidence}")
            print(f"  Rationale Type: {args.rationale_type}")
            print(f"  Accepted Matches: {len(accepted_matches)}")
            for m in accepted_matches:
                reason_preview = m['reason'][:60] + '...' if len(m['reason']) > 60 else m['reason']
                print(f"    - {m['fls_id']} ({m['score']:.3f}): {reason_preview}")
            print(f"  Rejected Matches: {len(rejected_matches)}")
            for m in rejected_matches:
                reason_preview = m['reason'][:60] + '...' if len(m['reason']) > 60 else m['reason']
                print(f"    - {m['fls_id']} ({m['score']:.3f}): {reason_preview}")
            if args.notes:
                print(f"  Notes: {args.notes}")
            if proposed_change:
                print(f"  Proposed Change: {proposed_change['field']}: "
                      f"{proposed_change['current_value']} -> {proposed_change['proposed_value']}")
        else:
            # Create output directory if needed
            output_dir.mkdir(parents=True, exist_ok=True)
            
            save_json(output_path, decision_file)
            print(f"Recorded decision for {args.guideline}")
            print(f"  Output: {output_path}")
            print(f"  Decision: {args.decision}, Confidence: {args.confidence}")
            print(f"  Accepted: {len(accepted_matches)}, Rejected: {len(rejected_matches)}")
            if proposed_change:
                print(f"  Proposed change: {proposed_change['field']}: "
                      f"{proposed_change['current_value']} -> {proposed_change['proposed_value']}")
    
    else:
        # === IN-PLACE MODE ===
        # At this point, we know report and report_path are not None
        assert report is not None
        assert report_path is not None
        
        # Find guideline index
        result = find_guideline(report, args.guideline)
        assert result is not None  # Already validated above
        guideline_idx, guideline = result
        
        # Build verification decision
        verification_decision = {
            "decision": args.decision,
            "confidence": args.confidence,
            "fls_rationale_type": args.rationale_type,
            "accepted_matches": accepted_matches,
            "rejected_matches": rejected_matches,
            "notes": args.notes,
        }
        
        if proposed_change:
            verification_decision["proposed_applicability_change"] = proposed_change
        
        # Update guideline
        report["guidelines"][guideline_idx]["verification_decision"] = verification_decision
        
        # Add applicability change to top-level array if proposed
        if proposed_change:
            applicability_change = {
                "guideline_id": args.guideline,
                "field": proposed_change["field"],
                "current_value": proposed_change["current_value"],
                "proposed_value": proposed_change["proposed_value"],
                "rationale": proposed_change["rationale"],
                "approved": None,
            }
            # Remove any existing change for this guideline/field combination
            existing_changes = report.get("applicability_changes", [])
            filtered_changes = [
                c for c in existing_changes
                if not (c["guideline_id"] == args.guideline and c["field"] == applicability_change["field"])
            ]
            filtered_changes.append(applicability_change)
            report["applicability_changes"] = filtered_changes
        
        # Update summary
        update_summary(report)
        
        # Validate against schema
        schema = load_batch_report_schema(root)
        if schema:
            errors = validate_report(report, schema)
            if errors:
                print("ERROR: Updated report fails schema validation:", file=sys.stderr)
                for err in errors:
                    print(f"  {err}", file=sys.stderr)
                sys.exit(1)
        
        # Output or save
        if args.dry_run:
            print("DRY RUN - Would record the following decision:")
            print(f"  Guideline: {args.guideline}")
            print(f"  Decision: {args.decision}")
            print(f"  Confidence: {args.confidence}")
            print(f"  Rationale Type: {args.rationale_type}")
            print(f"  Accepted Matches: {len(accepted_matches)}")
            for m in accepted_matches:
                reason_preview = m['reason'][:60] + '...' if len(m['reason']) > 60 else m['reason']
                print(f"    - {m['fls_id']} ({m['score']:.3f}): {reason_preview}")
            print(f"  Rejected Matches: {len(rejected_matches)}")
            for m in rejected_matches:
                reason_preview = m['reason'][:60] + '...' if len(m['reason']) > 60 else m['reason']
                print(f"    - {m['fls_id']} ({m['score']:.3f}): {reason_preview}")
            if args.notes:
                print(f"  Notes: {args.notes}")
            if proposed_change:
                print(f"  Proposed Change: {proposed_change['field']}: "
                      f"{proposed_change['current_value']} -> {proposed_change['proposed_value']}")
            print()
            print(f"  Updated summary: {report['summary']}")
        else:
            save_json(report_path, report)
            print(f"Recorded decision for {args.guideline}")
            print(f"  Decision: {args.decision}, Confidence: {args.confidence}")
            print(f"  Accepted: {len(accepted_matches)}, Rejected: {len(rejected_matches)}")
            if proposed_change:
                print(f"  Proposed change: {proposed_change['field']}: "
                      f"{proposed_change['current_value']} -> {proposed_change['proposed_value']}")
            print(f"  Progress: {report['summary']['verified_count']}/{report['summary']['total_guidelines']}")


if __name__ == "__main__":
    main()
