#!/usr/bin/env python3
"""
batch_check.py - Batch membership validation for verification workflow.

Provides functions to validate that a guideline belongs to a specific batch
before beginning verification work. Can be used standalone or by other tools.

Usage (standalone):
    uv run check-guideline --standard misra-c --guideline "Rule 15.4" --batch 2
    
Usage (imported):
    from fls_tools.standards.verification.batch_check import validate_guideline_in_batch
    is_valid, error_msg, actual_batch = validate_guideline_in_batch(root, standard, guideline, batch)
"""

import argparse
import json
import sys
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_verification_progress_path,
    VALID_STANDARDS,
)


def load_progress_data(root: Path, standard: str) -> dict | None:
    """Load progress.json for a standard. Returns None if not found."""
    progress_path = get_verification_progress_path(root, standard)
    if not progress_path.exists():
        return None
    
    with open(progress_path) as f:
        return json.load(f)


def get_batch_info(progress: dict, batch_id: int) -> dict | None:
    """
    Get batch info by ID.
    
    Returns dict with: batch_id, name, status, guidelines (list of guideline dicts)
    Returns None if batch not found.
    """
    for batch in progress.get("batches", []):
        if batch.get("batch_id") == batch_id:
            return {
                "batch_id": batch_id,
                "name": batch.get("name", ""),
                "status": batch.get("status", "pending"),
                "guidelines": batch.get("guidelines", []),
            }
    return None


def get_batch_guidelines(progress: dict, batch_id: int) -> set[str] | None:
    """Get set of guideline IDs in a batch. Returns None if batch not found."""
    batch_info = get_batch_info(progress, batch_id)
    if batch_info is None:
        return None
    
    return {g.get("guideline_id") for g in batch_info["guidelines"] if g.get("guideline_id")}


def find_guideline_batch(progress: dict, guideline_id: str) -> tuple[int | None, str | None]:
    """
    Find which batch a guideline belongs to.
    
    Returns:
        (batch_id, batch_name) or (None, None) if not found
    """
    for batch in progress.get("batches", []):
        for guideline in batch.get("guidelines", []):
            if guideline.get("guideline_id") == guideline_id:
                return batch.get("batch_id"), batch.get("name", "")
    
    return None, None


def get_guideline_info(progress: dict, guideline_id: str) -> dict | None:
    """
    Get full info about a guideline.
    
    Returns dict with:
        - batch_id
        - batch_name
        - batch_status
        - guideline_status (pending/verified)
        - verified (bool)
        - session_id (if verified)
    
    Returns None if guideline not found.
    """
    for batch in progress.get("batches", []):
        for guideline in batch.get("guidelines", []):
            if guideline.get("guideline_id") == guideline_id:
                return {
                    "batch_id": batch.get("batch_id"),
                    "batch_name": batch.get("name", ""),
                    "batch_status": batch.get("status", "pending"),
                    "guideline_status": guideline.get("status", "pending"),
                    "verified": guideline.get("verified", False),
                    "session_id": guideline.get("session_id"),
                }
    
    return None


def validate_guideline_in_batch(
    root: Path,
    standard: str,
    guideline_id: str,
    batch_id: int,
) -> tuple[bool, str | None, int | None]:
    """
    Validate that a guideline is in the specified batch.
    
    Returns:
        (is_valid, error_message, actual_batch_id)
        
    If is_valid is True: error_message is None, actual_batch_id == batch_id
    If is_valid is False: error_message explains why, actual_batch_id is correct batch (or None)
    """
    progress = load_progress_data(root, standard)
    
    if progress is None:
        return (
            False,
            f"Progress file not found for standard '{standard}'. "
            f"Run: uv run scaffold-progress --standard {standard}",
            None,
        )
    
    # Check if the specified batch exists
    batch_info = get_batch_info(progress, batch_id)
    if batch_info is None:
        return (
            False,
            f"Batch {batch_id} not found in progress file for '{standard}'",
            None,
        )
    
    # Find which batch the guideline actually belongs to
    actual_batch_id, actual_batch_name = find_guideline_batch(progress, guideline_id)
    
    if actual_batch_id is None:
        return (
            False,
            f"Guideline '{guideline_id}' not found in any batch",
            None,
        )
    
    if actual_batch_id != batch_id:
        return (
            False,
            f"Guideline '{guideline_id}' is not in batch {batch_id}. "
            f"Actual batch: {actual_batch_id} ({actual_batch_name})",
            actual_batch_id,
        )
    
    return True, None, batch_id


def format_success_output(
    guideline_id: str,
    batch_id: int,
    progress: dict,
) -> str:
    """Format success output for check-guideline command."""
    info = get_guideline_info(progress, guideline_id)
    if info is None:
        return f"OK: Guideline '{guideline_id}' is in batch {batch_id}"
    
    lines = [
        f"OK: Guideline '{guideline_id}' is in batch {batch_id}",
        f"  Batch: {info['batch_id']} ({info['batch_name']})",
        f"  Batch status: {info['batch_status']}",
    ]
    
    if info["verified"]:
        session_info = f" (session {info['session_id']})" if info["session_id"] else ""
        lines.append(f"  Guideline status: verified{session_info}")
    else:
        lines.append(f"  Guideline status: {info['guideline_status']}")
    
    return "\n".join(lines)


def format_error_output(
    guideline_id: str,
    batch_id: int,
    error_msg: str,
    actual_batch_id: int | None,
    progress: dict | None,
) -> str:
    """Format error output for check-guideline command."""
    lines = [f"ERROR: {error_msg}"]
    
    if actual_batch_id is not None and progress is not None:
        batch_info = get_batch_info(progress, actual_batch_id)
        if batch_info:
            lines.append(f"  Batch {actual_batch_id} status: {batch_info['status']}")
    
    return "\n".join(lines)


def main():
    """CLI entry point for check-guideline command."""
    parser = argparse.ArgumentParser(
        description="Validate that a guideline belongs to a specific batch"
    )
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard (e.g., misra-c, cert-cpp)",
    )
    parser.add_argument(
        "--guideline",
        type=str,
        required=True,
        help="Guideline ID (e.g., 'Rule 15.4', 'Dir 1.1')",
    )
    parser.add_argument(
        "--batch",
        type=int,
        required=True,
        help="Expected batch number",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Validate
    is_valid, error_msg, actual_batch = validate_guideline_in_batch(
        root, args.standard, args.guideline, args.batch
    )
    
    progress = load_progress_data(root, args.standard)
    
    if is_valid:
        assert progress is not None  # Can't be valid without progress file
        print(format_success_output(args.guideline, args.batch, progress))
        sys.exit(0)
    else:
        assert error_msg is not None  # Must have error message if not valid
        print(format_error_output(
            args.guideline, args.batch, error_msg, actual_batch, progress
        ), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
