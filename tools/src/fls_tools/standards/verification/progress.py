#!/usr/bin/env python3
"""
check_progress.py - Phase 0: Check Verification Progress

This script shows current verification status and helps determine where to resume:
- Last session ID and next session ID to use
- Current batch and its status
- Whether a batch report exists in cache/verification/
- If resuming, which guideline to continue from
- Suggested command for Phase 1 (if batch report doesn't exist)

Usage:
    uv run python verification/check_progress.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_verification_cache_dir,
    get_verification_progress_path,
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


def main():
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
    
    # Summary stats
    summary = progress.get("summary", {})
    print(f"Total guidelines: {progress.get('total_guidelines', 'N/A')}")
    print(f"Verified: {summary.get('total_verified', 'N/A')}")
    print(f"Pending: {summary.get('total_pending', 'N/A')}")
    print()
    
    # Current batch
    if current_batch:
        pending_count = sum(
            1 for g in current_batch.get("guidelines", [])
            if g.get("status") == "pending"
        )
        print(f"Current batch: {current_batch['batch_id']} ({current_batch['name']})")
        print(f"Status: {current_batch['status']}")
        print(f"Pending in batch: {pending_count} guidelines")
        print()
        
        # Check for existing batch report
        matching_reports = [
            r for r in batch_reports
            if r["batch_id"] == current_batch["batch_id"]
        ]
        
        if matching_reports:
            # Found existing report(s)
            latest = max(matching_reports, key=lambda r: r["session_id"])
            print("-" * 60)
            print("EXISTING BATCH REPORT FOUND")
            print("-" * 60)
            print(f"Path: {latest['path']}")
            print(f"Session: {latest['session_id']}")
            print(f"Progress: {latest['verified']}/{latest['total']} guidelines have verification_decision")
            
            if latest['verified'] < latest['total']:
                resume_from = find_resume_guideline(latest['path'])
                if resume_from:
                    print(f"Resume from: {resume_from}")
                print()
                print("To continue Phase 2:")
                print(f"  Read {latest['path'].name} and resume analysis from {resume_from}")
            else:
                print()
                print("All guidelines have verification_decision populated.")
                print("Ready for Phase 3 (human review) and Phase 4 (apply changes).")
                print()
                print("To apply changes:")
                print(f"  uv run python verification/apply_verification.py \\")
                print(f"      --batch-report {latest['path'].relative_to(root)} \\")
                print(f"      --session {latest['session_id']}")
        else:
            # No existing report
            print("-" * 60)
            print("NO BATCH REPORT FOUND")
            print("-" * 60)
            output_path = f"../cache/verification/batch{current_batch['batch_id']}_session{next_session}.json"
            print()
            print("To start Phase 1:")
            print(f"  uv run python verification/verify_batch.py \\")
            print(f"      --batch {current_batch['batch_id']} \\")
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
