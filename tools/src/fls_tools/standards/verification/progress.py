#!/usr/bin/env python3
"""
check_progress.py - Phase 0: Check Verification Progress

This script shows current verification status and helps determine where to resume:
- Last session ID and next session ID to use
- Current batch and its status
- Whether a batch report exists in cache/verification/
- Whether a decisions directory exists (for parallel mode)
- Worker assignment suggestions for remaining guidelines
- If resuming, which guideline to continue from
- Suggested command for Phase 1 (if batch report doesn't exist)

Usage:
    uv run check-progress
    uv run check-progress --workers 4
"""

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_verification_cache_dir,
    get_verification_progress_path,
    get_coding_standards_dir,
)


def load_json(path: Path) -> dict | None:
    """Load a JSON file, return None if not found."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def is_verification_complete(guideline: dict) -> bool:
    """Check if a guideline's verification_decision has been completed.
    
    The batch tool scaffolds verification_decision as a dict with None values.
    A decision is complete only when the 'decision' field is populated.
    """
    vd = guideline.get("verification_decision")
    return vd is not None and vd.get("decision") is not None


def find_batch_reports(cache_dir: Path) -> list[dict]:
    """Find all batch reports in cache/verification/."""
    reports = []
    if not cache_dir.exists():
        return reports
    
    for f in cache_dir.glob("batch*_session*.json"):
        try:
            data = load_json(f)
            if data and "batch_id" in data and "session_id" in data:
                # Count verified guidelines (decision field must be populated)
                total = len(data.get("guidelines", []))
                verified = sum(
                    1 for g in data.get("guidelines", [])
                    if is_verification_complete(g)
                )
                reports.append({
                    "path": f,
                    "batch_id": data["batch_id"],
                    "session_id": data["session_id"],
                    "total": total,
                    "verified": verified,
                    "generated_date": data.get("generated_date"),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(reports, key=lambda r: (r["batch_id"], r["session_id"]))


def find_resume_guideline(report_path: Path) -> str | None:
    """Find the first guideline without a completed verification decision."""
    data = load_json(report_path)
    if not data:
        return None
    
    for g in data.get("guidelines", []):
        if not is_verification_complete(g):
            return g.get("guideline_id")
    
    return None


def load_decision_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        return None
    return load_json(schema_path)


def validate_decision_file(path: Path, schema: dict | None) -> tuple[bool, str | None]:
    """
    Validate a decision file.
    
    Returns:
        (is_valid, guideline_id or None)
    """
    data = load_json(path)
    if data is None:
        return False, None
    
    guideline_id = data.get("guideline_id")
    
    # Check filename matches guideline_id
    expected_filename = (guideline_id or "").replace(" ", "_") + ".json"
    if path.name != expected_filename:
        return False, guideline_id
    
    # Schema validation
    if schema:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError:
            return False, guideline_id
    
    return True, guideline_id


def find_decisions_directory(cache_dir: Path, batch_id: int) -> Path | None:
    """Find decisions directory for a batch."""
    decisions_dir = cache_dir / f"batch{batch_id}_decisions"
    if decisions_dir.exists() and decisions_dir.is_dir():
        return decisions_dir
    return None


def analyze_decisions_directory(
    decisions_dir: Path,
    batch_guidelines: list[str],
    schema: dict | None,
) -> dict:
    """
    Analyze a decisions directory.
    
    Returns dict with:
        - total_files: number of .json files
        - valid_count: number of valid decision files
        - invalid_count: number of invalid files
        - invalid_files: list of invalid filenames
        - decided_guidelines: set of guideline IDs with valid decisions
        - remaining_guidelines: list of guideline IDs without decisions
    """
    decision_files = list(decisions_dir.glob("*.json"))
    
    valid_count = 0
    invalid_count = 0
    invalid_files = []
    decided_guidelines = set()
    
    for path in decision_files:
        is_valid, guideline_id = validate_decision_file(path, schema)
        if is_valid and guideline_id:
            valid_count += 1
            decided_guidelines.add(guideline_id)
        else:
            invalid_count += 1
            invalid_files.append(path.name)
    
    remaining_guidelines = [g for g in batch_guidelines if g not in decided_guidelines]
    
    return {
        "total_files": len(decision_files),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "invalid_files": invalid_files,
        "decided_guidelines": decided_guidelines,
        "remaining_guidelines": remaining_guidelines,
    }


def suggest_worker_assignment(
    remaining_guidelines: list[str],
    num_workers: int,
) -> list[tuple[int, list[str]]]:
    """
    Suggest worker assignment for remaining guidelines.
    
    Returns list of (worker_num, guideline_list) tuples.
    """
    if not remaining_guidelines:
        return []
    
    assignments = []
    per_worker = len(remaining_guidelines) // num_workers
    remainder = len(remaining_guidelines) % num_workers
    
    start = 0
    for i in range(num_workers):
        # Distribute remainder among first workers
        count = per_worker + (1 if i < remainder else 0)
        if count > 0:
            worker_guidelines = remaining_guidelines[start:start + count]
            assignments.append((i + 1, worker_guidelines))
            start += count
    
    return assignments


def main():
    parser = argparse.ArgumentParser(
        description="Check verification progress and suggest next steps"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of workers for parallel assignment suggestions (default: 3)",
    )
    args = parser.parse_args()
    root = get_project_root()
    
    # Load verification progress
    progress_path = get_verification_progress_path(root)
    progress = load_json(progress_path)
    
    if not progress:
        print("ERROR: verification_progress.json not found", file=sys.stderr)
        print(f"       Expected at: {progress_path}", file=sys.stderr)
        sys.exit(1)
    
    # Find last and next session
    sessions = progress.get("sessions", [])
    last_session = max((s["session_id"] for s in sessions), default=0)
    next_session = last_session + 1
    
    # Find current batch (first non-completed)
    current_batch = None
    for batch in progress.get("batches", []):
        if batch["status"] != "completed":
            current_batch = batch
            break
    
    # Find batch reports in cache
    cache_dir = get_verification_cache_dir(root)
    batch_reports = find_batch_reports(cache_dir)
    
    # Output
    print("=" * 60)
    print("VERIFICATION PROGRESS")
    print("=" * 60)
    print()
    print(f"Last session: {last_session}")
    print(f"Next session: {next_session}")
    print()
    
    # Compute counts from actual guideline data (not stale summary)
    total_verified = 0
    total_pending = 0
    for batch in progress.get("batches", []):
        for g in batch.get("guidelines", []):
            if g.get("verified", False):
                total_verified += 1
            else:
                total_pending += 1
    
    print(f"Total guidelines: {progress.get('total_guidelines', 'N/A')}")
    print(f"Verified: {total_verified}")
    print(f"Pending: {total_pending}")
    
    # Warn if cached summary is stale
    summary = progress.get("summary", {})
    cached_verified = summary.get("total_verified")
    cached_pending = summary.get("total_pending")
    if cached_verified is not None and cached_verified != total_verified:
        print()
        print(f"WARNING: Cached summary is stale (shows {cached_verified} verified)")
        print("         Consider running: uv run scaffold-progress --preserve-completed")
    
    print()
    
    # Load decision file schema for validation
    decision_schema = load_decision_schema(root)
    
    # Current batch
    if current_batch:
        batch_id = current_batch["batch_id"]
        batch_guidelines = [g["guideline_id"] for g in current_batch.get("guidelines", [])]
        pending_count = sum(
            1 for g in current_batch.get("guidelines", [])
            if not g.get("verified", False)
        )
        print(f"Current batch: {batch_id} ({current_batch['name']})")
        print(f"Status: {current_batch['status']}")
        print(f"Pending in batch: {pending_count} guidelines")
        print()
        
        # Check for decisions directory (parallel mode)
        decisions_dir = find_decisions_directory(cache_dir, batch_id)
        decisions_analysis = None
        
        if decisions_dir:
            decisions_analysis = analyze_decisions_directory(
                decisions_dir, batch_guidelines, decision_schema
            )
            
            print("-" * 60)
            print("DECISIONS DIRECTORY")
            print("-" * 60)
            print(f"Path: {decisions_dir}")
            pct = 100 * decisions_analysis["valid_count"] / len(batch_guidelines) if batch_guidelines else 0
            print(f"Progress: {decisions_analysis['valid_count']}/{len(batch_guidelines)} decisions ({pct:.0f}%)")
            print(f"  Valid: {decisions_analysis['valid_count']}")
            print(f"  Invalid: {decisions_analysis['invalid_count']}")
            
            if decisions_analysis["invalid_files"]:
                print(f"  Invalid files: {', '.join(decisions_analysis['invalid_files'][:5])}")
                if len(decisions_analysis["invalid_files"]) > 5:
                    print(f"    ... and {len(decisions_analysis['invalid_files']) - 5} more")
            
            remaining = decisions_analysis["remaining_guidelines"]
            if remaining:
                print()
                print(f"Remaining guidelines ({len(remaining)}):")
                # Show first 10
                display_remaining = remaining[:10]
                print(f"  {', '.join(display_remaining)}")
                if len(remaining) > 10:
                    print(f"  ... and {len(remaining) - 10} more")
                
                # Worker assignment suggestions
                print()
                print("-" * 60)
                print(f"SUGGESTED WORKER ASSIGNMENT ({args.workers} workers)")
                print("-" * 60)
                assignments = suggest_worker_assignment(remaining, args.workers)
                for worker_num, worker_guidelines in assignments:
                    if len(worker_guidelines) > 0:
                        first = worker_guidelines[0]
                        last = worker_guidelines[-1]
                        print(f"Worker {worker_num} ({len(worker_guidelines)} guidelines): {first} -> {last}")
                
                print()
                print("To continue parallel verification:")
                print(f"  uv run record-decision --batch {batch_id} \\")
                print(f"      --guideline \"<GUIDELINE_ID>\" ...")
                
                print()
                print("To merge completed decisions:")
        
        # Check for existing batch report
        matching_reports = [
            r for r in batch_reports
            if r["batch_id"] == batch_id
        ]
        
        if matching_reports:
            # Found existing report(s)
            latest = max(matching_reports, key=lambda r: r["session_id"])
            print()
            print("-" * 60)
            print("BATCH REPORT")
            print("-" * 60)
            print(f"Path: {latest['path']}")
            print(f"Session: {latest['session_id']}")
            print(f"Progress: {latest['verified']}/{latest['total']} guidelines have verification_decision")
            
            if decisions_dir and decisions_analysis:
                # Parallel mode - suggest merge
                if decisions_analysis["valid_count"] > 0:
                    print()
                    print("To merge decisions into batch report:")
                    print(f"  uv run merge-decisions \\")
                    print(f"      --batch-report {latest['path'].relative_to(root)} \\")
                    print(f"      --decisions-dir {decisions_dir.relative_to(root)} \\")
                    print(f"      --validate")
            elif latest['verified'] < latest['total']:
                # Sequential mode
                resume_from = find_resume_guideline(latest['path'])
                if resume_from:
                    print(f"Resume from: {resume_from}")
                print()
                print("To continue Phase 2 (sequential):")
                print(f"  Read {latest['path'].name} and resume analysis from {resume_from}")
                print()
                print("To enable parallel mode:")
                print(f"  mkdir -p {cache_dir.relative_to(root)}/batch{batch_id}_decisions")
            
            if latest['verified'] == latest['total'] or (
                decisions_analysis and decisions_analysis["valid_count"] == len(batch_guidelines)
            ):
                print()
                print("All guidelines have verification decisions.")
                print("Ready for Phase 3 (human review) and Phase 4 (apply changes).")
                print()
                print("To apply changes:")
                print(f"  uv run apply-verification \\")
                print(f"      --batch-report {latest['path'].relative_to(root)} \\")
                print(f"      --session {latest['session_id']}")
        else:
            # No existing report
            print()
            print("-" * 60)
            print("NO BATCH REPORT FOUND")
            print("-" * 60)
            output_path = f"../cache/verification/batch{batch_id}_session{next_session}.json"
            print()
            print("To start Phase 1:")
            print(f"  uv run verify-batch \\")
            print(f"      --batch {batch_id} \\")
            print(f"      --session {next_session} \\")
            print(f"      --mode llm \\")
            print(f"      --output {output_path}")
    else:
        print("All batches completed!")
        print()
    
    # Show all batches summary
    print()
    print("-" * 60)
    print("ALL BATCHES")
    print("-" * 60)
    print(f"{'Batch':<6} {'Name':<30} {'Status':<12} {'Verified':<10} {'Pending':<10}")
    print("-" * 60)
    
    for batch in progress.get("batches", []):
        verified = sum(1 for g in batch.get("guidelines", []) if g.get("status") == "verified")
        pending = sum(1 for g in batch.get("guidelines", []) if g.get("status") == "pending")
        print(f"{batch['batch_id']:<6} {batch['name']:<30} {batch['status']:<12} {verified:<10} {pending:<10}")
    
    print()


if __name__ == "__main__":
    main()
