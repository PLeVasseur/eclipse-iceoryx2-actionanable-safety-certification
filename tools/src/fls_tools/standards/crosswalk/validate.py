#!/usr/bin/env python3
"""Validate the concept crosswalk file.

This tool validates concept_to_fls.json against the JSON schema and
checks that all referenced IDs are valid.

Usage:
    uv run validate-concept-crosswalk
    uv run validate-concept-crosswalk --verbose
"""

import argparse
import json
import sys
from pathlib import Path

from .validation import load_valid_ids, validate_all_concepts


def get_project_root() -> Path:
    """Get the project root directory."""
    current = Path(__file__).resolve()
    while current.parent != current:
        if (current / "AGENTS.md").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find project root")


def load_crosswalk(path: Path) -> dict:
    """Load the concept crosswalk file."""
    with open(path) as f:
        return json.load(f)


def validate_schema(crosswalk: dict, schema_path: Path) -> list[str]:
    """Validate crosswalk against JSON schema.

    Returns list of validation error messages.
    """
    try:
        import jsonschema
    except ImportError:
        return ["WARNING: jsonschema not installed, skipping schema validation"]

    if not schema_path.exists():
        return [f"WARNING: Schema file not found: {schema_path}"]

    with open(schema_path) as f:
        schema = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for error in validator.iter_errors(crosswalk):
        path = " -> ".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"Schema error at {path}: {error.message}")

    return errors


def check_duplicate_aliases(concepts: dict) -> list[str]:
    """Check for duplicate aliases across concepts.

    Returns list of error messages for any duplicates found.
    """
    alias_to_concepts: dict[str, list[str]] = {}

    for key, concept in concepts.items():
        for alias in concept.get("aliases", []):
            if alias not in alias_to_concepts:
                alias_to_concepts[alias] = []
            alias_to_concepts[alias].append(key)

    errors = []
    for alias, concept_keys in alias_to_concepts.items():
        if len(concept_keys) > 1:
            errors.append(
                f"Duplicate alias '{alias}' in concepts: {', '.join(concept_keys)}"
            )

    return errors


def check_alias_conflicts(concepts: dict) -> list[str]:
    """Check for aliases that conflict with concept keys.

    Returns list of error messages for any conflicts found.
    """
    concept_keys = set(concepts.keys())
    errors = []

    for key, concept in concepts.items():
        for alias in concept.get("aliases", []):
            if alias in concept_keys and alias != key:
                errors.append(
                    f"Alias '{alias}' in concept '{key}' conflicts with existing concept key"
                )

    return errors


def compute_statistics(concepts: dict) -> dict:
    """Compute statistics about the crosswalk."""
    stats = {
        "total_concepts": len(concepts),
        "concepts_with_fls_ids": 0,
        "concepts_with_reference_ids": 0,
        "concepts_with_ucg_ids": 0,
        "concepts_with_nomicon_ids": 0,
        "concepts_with_clippy_lints": 0,
        "total_fls_ids": 0,
        "total_reference_ids": 0,
        "total_ucg_ids": 0,
        "total_nomicon_ids": 0,
        "total_clippy_lints": 0,
        "concepts_with_c_terms": 0,
        "concepts_with_rust_terms": 0,
        "concepts_with_aliases": 0,
    }

    for concept in concepts.values():
        if concept.get("fls_ids"):
            stats["concepts_with_fls_ids"] += 1
            stats["total_fls_ids"] += len(concept["fls_ids"])

        if concept.get("reference_ids"):
            stats["concepts_with_reference_ids"] += 1
            stats["total_reference_ids"] += len(concept["reference_ids"])

        if concept.get("ucg_ids"):
            stats["concepts_with_ucg_ids"] += 1
            stats["total_ucg_ids"] += len(concept["ucg_ids"])

        if concept.get("nomicon_ids"):
            stats["concepts_with_nomicon_ids"] += 1
            stats["total_nomicon_ids"] += len(concept["nomicon_ids"])

        if concept.get("clippy_lints"):
            stats["concepts_with_clippy_lints"] += 1
            stats["total_clippy_lints"] += len(concept["clippy_lints"])

        if concept.get("c_terms"):
            stats["concepts_with_c_terms"] += 1

        if concept.get("rust_terms"):
            stats["concepts_with_rust_terms"] += 1

        if concept.get("aliases"):
            stats["concepts_with_aliases"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Validate the concept crosswalk file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed validation information",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show statistics, skip validation",
    )

    args = parser.parse_args()

    # Find project root and load data
    project_root = get_project_root()
    crosswalk_path = (
        project_root / "coding-standards-fls-mapping" / "concept_to_fls.json"
    )
    schema_path = (
        project_root
        / "coding-standards-fls-mapping"
        / "schema"
        / "concept_crosswalk.schema.json"
    )

    if not crosswalk_path.exists():
        print(f"ERROR: Crosswalk file not found: {crosswalk_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Validating: {crosswalk_path}")
    print("=" * 60)

    crosswalk = load_crosswalk(crosswalk_path)
    concepts = crosswalk.get("concepts", {})

    # Compute and show statistics
    stats = compute_statistics(concepts)

    print("\nStatistics:")
    print(f"  Total concepts: {stats['total_concepts']}")
    print(f"  Concepts with FLS IDs: {stats['concepts_with_fls_ids']} ({stats['total_fls_ids']} total IDs)")
    print(f"  Concepts with Reference IDs: {stats['concepts_with_reference_ids']} ({stats['total_reference_ids']} total IDs)")
    print(f"  Concepts with UCG IDs: {stats['concepts_with_ucg_ids']} ({stats['total_ucg_ids']} total IDs)")
    print(f"  Concepts with Nomicon IDs: {stats['concepts_with_nomicon_ids']} ({stats['total_nomicon_ids']} total IDs)")
    print(f"  Concepts with Clippy lints: {stats['concepts_with_clippy_lints']} ({stats['total_clippy_lints']} total lints)")
    print(f"  Concepts with C terms: {stats['concepts_with_c_terms']}")
    print(f"  Concepts with Rust terms: {stats['concepts_with_rust_terms']}")
    print(f"  Concepts with aliases: {stats['concepts_with_aliases']}")

    if args.stats_only:
        return

    # Validation
    all_errors = []
    all_warnings = []

    # Schema validation
    print("\nSchema validation...")
    schema_results = validate_schema(crosswalk, schema_path)
    for msg in schema_results:
        if msg.startswith("WARNING:"):
            all_warnings.append(msg)
            if args.verbose:
                print(f"  {msg}")
        else:
            all_errors.append(msg)
            print(f"  ERROR: {msg}")

    if not schema_results:
        print("  OK")

    # Check duplicate aliases
    print("\nChecking for duplicate aliases...")
    dup_errors = check_duplicate_aliases(concepts)
    all_errors.extend(dup_errors)
    for msg in dup_errors:
        print(f"  ERROR: {msg}")
    if not dup_errors:
        print("  OK")

    # Check alias conflicts with keys
    print("\nChecking for alias/key conflicts...")
    conflict_errors = check_alias_conflicts(concepts)
    all_errors.extend(conflict_errors)
    for msg in conflict_errors:
        print(f"  ERROR: {msg}")
    if not conflict_errors:
        print("  OK")

    # ID validation
    print("\nValidating IDs...")
    valid_ids = load_valid_ids(project_root)

    # Check if we have valid IDs loaded
    id_sources = {
        "FLS": len(valid_ids.fls_ids),
        "Reference": len(valid_ids.reference_ids),
        "UCG": len(valid_ids.ucg_ids),
        "Nomicon": len(valid_ids.nomicon_ids),
        "Clippy": len(valid_ids.clippy_lints),
    }

    if args.verbose:
        print("  Valid ID counts loaded:")
        for source, count in id_sources.items():
            status = "OK" if count > 0 else "MISSING"
            print(f"    {source}: {count} ({status})")

    invalid_results = validate_all_concepts(concepts, valid_ids)

    if invalid_results:
        for result in invalid_results:
            for msg in result.error_messages():
                all_errors.append(f"{result.concept_key}: {msg}")
                print(f"  ERROR in '{result.concept_key}': {msg}")
    else:
        print("  OK")

    # Summary
    print("\n" + "=" * 60)
    if all_errors:
        print(f"FAILED: {len(all_errors)} error(s)")
        sys.exit(1)
    elif all_warnings:
        print(f"PASSED with {len(all_warnings)} warning(s)")
    else:
        print("PASSED")


if __name__ == "__main__":
    main()
