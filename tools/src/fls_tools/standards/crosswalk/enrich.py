#!/usr/bin/env python3
"""Enrich concept crosswalk with cross-references to Rust documentation sources.

This tool allows adding Reference, UCG, Nomicon, and Clippy cross-references
to concepts in concept_to_fls.json.

Usage:
    # Show existing concept
    uv run enrich-concept --concept "type_conversions" --show

    # Add reference ID to existing concept
    uv run enrich-concept --concept "type_conversions" --add-reference "expressions.operator-expr.type-cast"

    # Add multiple IDs at once
    uv run enrich-concept --concept "type_conversions" \
        --add-reference "type-coercions" \
        --add-clippy "cast_ptr_alignment"

    # Create new concept
    uv run enrich-concept --concept "drop_glue" \
        --description "Compiler-generated destructor code" \
        --add-rust-term "drop glue" \
        --add-fls "fls_u2mzjgiwbkz0"
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .matching import ConceptEmbeddings, MatchResults, find_similar_concepts
from .validation import ValidationResult, load_valid_ids, validate_concept_ids


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


def save_crosswalk(path: Path, data: dict):
    """Save the concept crosswalk file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def show_concept(key: str, concept: dict):
    """Display a concept's current state."""
    print(f"\n{'='*60}")
    print(f"Concept: {key}")
    print(f"{'='*60}")
    print(f"Description: {concept.get('description', '(none)')}")
    print(f"\nKeywords: {', '.join(concept.get('keywords', []))}")

    if concept.get("c_terms"):
        print(f"C Terms: {', '.join(concept['c_terms'])}")
    if concept.get("rust_terms"):
        print(f"Rust Terms: {', '.join(concept['rust_terms'])}")
    if concept.get("aliases"):
        print(f"Aliases: {', '.join(concept['aliases'])}")

    print(f"\nFLS IDs ({len(concept.get('fls_ids', []))}):")
    for fls_id in concept.get("fls_ids", []):
        print(f"  - {fls_id}")

    if concept.get("fls_sections"):
        print(f"FLS Sections: {', '.join(concept['fls_sections'])}")

    if concept.get("reference_ids"):
        print(f"\nReference IDs ({len(concept['reference_ids'])}):")
        for ref_id in concept["reference_ids"]:
            print(f"  - {ref_id}")

    if concept.get("ucg_ids"):
        print(f"\nUCG IDs ({len(concept['ucg_ids'])}):")
        for ucg_id in concept["ucg_ids"]:
            print(f"  - {ucg_id}")

    if concept.get("nomicon_ids"):
        print(f"\nNomicon IDs ({len(concept['nomicon_ids'])}):")
        for nomicon_id in concept["nomicon_ids"]:
            print(f"  - {nomicon_id}")

    if concept.get("clippy_lints"):
        print(f"\nClippy Lints ({len(concept['clippy_lints'])}):")
        for lint in concept["clippy_lints"]:
            print(f"  - {lint}")

    print(f"\nApplicability (all Rust): {concept.get('typical_applicability_all_rust', '(not set)')}")
    print(f"Applicability (safe Rust): {concept.get('typical_applicability_safe_rust', '(not set)')}")

    if concept.get("rationale"):
        print(f"\nRationale: {concept['rationale']}")

    print()


def prompt_for_concept_selection(results: MatchResults, query: str) -> Optional[str]:
    """Prompt user to select from similar concepts or create new.

    Returns:
        concept_key if user selects existing, None if user wants new concept.
    """
    candidates = results.all_candidates()

    if not candidates:
        return None

    print(f"\nSimilar concepts found for '{query}':")
    print("-" * 50)

    for i, match in enumerate(candidates[:5], 1):
        match_info = f"[{match.score:.2f}] via {match.matched_via}"
        print(f"  {i}. {match.concept_key} {match_info}")

    print(f"  n. Create new concept '{query}'")
    print()

    while True:
        choice = input("Select [1-5/n]: ").strip().lower()
        if choice == "n":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(candidates[:5]):
                return candidates[idx].concept_key
        except ValueError:
            pass
        print("Invalid choice. Please enter a number 1-5 or 'n'.")


def add_to_list(concept: dict, field: str, values: list[str]) -> list[str]:
    """Add values to a list field, avoiding duplicates. Returns list of added values."""
    if field not in concept:
        concept[field] = []
    added = []
    for v in values:
        if v not in concept[field]:
            concept[field].append(v)
            added.append(v)
    return added


def main():
    parser = argparse.ArgumentParser(
        description="Enrich concept crosswalk with Rust documentation cross-references",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--concept",
        required=True,
        help="Concept key (or alias) to modify/create",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display current concept state and exit",
    )
    parser.add_argument(
        "--description",
        help="Set/update concept description",
    )
    parser.add_argument(
        "--add-keyword",
        action="append",
        default=[],
        dest="add_keywords",
        metavar="WORD",
        help="Add to keywords list (can be repeated)",
    )
    parser.add_argument(
        "--add-c-term",
        action="append",
        default=[],
        dest="add_c_terms",
        metavar="TERM",
        help="Add to c_terms list (can be repeated)",
    )
    parser.add_argument(
        "--add-rust-term",
        action="append",
        default=[],
        dest="add_rust_terms",
        metavar="TERM",
        help="Add to rust_terms list (can be repeated)",
    )
    parser.add_argument(
        "--add-alias",
        action="append",
        default=[],
        dest="add_aliases",
        metavar="ALIAS",
        help="Add to aliases list (can be repeated)",
    )
    parser.add_argument(
        "--add-fls",
        action="append",
        default=[],
        dest="add_fls_ids",
        metavar="ID",
        help="Add FLS ID (can be repeated)",
    )
    parser.add_argument(
        "--add-reference",
        action="append",
        default=[],
        dest="add_reference_ids",
        metavar="ID",
        help="Add Reference ID (can be repeated)",
    )
    parser.add_argument(
        "--add-ucg",
        action="append",
        default=[],
        dest="add_ucg_ids",
        metavar="ID",
        help="Add UCG ID (can be repeated)",
    )
    parser.add_argument(
        "--add-nomicon",
        action="append",
        default=[],
        dest="add_nomicon_ids",
        metavar="ID",
        help="Add Nomicon ID (can be repeated)",
    )
    parser.add_argument(
        "--add-clippy",
        action="append",
        default=[],
        dest="add_clippy_lints",
        metavar="LINT",
        help="Add Clippy lint name (can be repeated)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without writing to file",
    )
    parser.add_argument(
        "--force-new",
        action="store_true",
        help="Create new concept without fuzzy matching check",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip ID validation (not recommended)",
    )

    args = parser.parse_args()

    # Find project root and load data
    project_root = get_project_root()
    crosswalk_path = project_root / "coding-standards-fls-mapping" / "concept_to_fls.json"

    if not crosswalk_path.exists():
        print(f"ERROR: Crosswalk file not found: {crosswalk_path}", file=sys.stderr)
        sys.exit(1)

    crosswalk = load_crosswalk(crosswalk_path)
    concepts = crosswalk.get("concepts", {})

    # Load valid IDs for validation
    valid_ids = None
    if not args.skip_validation:
        valid_ids = load_valid_ids(project_root)

    # Load embeddings for fuzzy matching
    embeddings_cache = project_root / "embeddings" / "concepts" / "embeddings.pkl"
    concept_embeddings = ConceptEmbeddings(project_root)

    # Find the concept
    query = args.concept
    target_key: Optional[str] = None
    is_new_concept = False

    # Check for exact match first
    if query in concepts:
        target_key = query
    else:
        # Check aliases
        for key, concept in concepts.items():
            if query in concept.get("aliases", []):
                target_key = key
                break

    # If not found and not forcing new, do fuzzy matching
    if target_key is None and not args.force_new:
        # Load embeddings for semantic matching
        concept_embeddings.load_or_generate(concepts, cache_path=embeddings_cache)

        results = find_similar_concepts(
            query, concepts, embeddings=concept_embeddings
        )

        if results.has_exact_or_normalized():
            # This shouldn't happen given above checks, but handle it
            target_key = results.best_match().concept_key
        elif results.all_candidates():
            # Prompt user
            target_key = prompt_for_concept_selection(results, query)
            if target_key is None:
                is_new_concept = True
                target_key = query
        else:
            # No matches, create new
            is_new_concept = True
            target_key = query

    elif target_key is None:
        # Force new
        is_new_concept = True
        target_key = query

    # Handle --show
    if args.show:
        if is_new_concept:
            print(f"Concept '{target_key}' does not exist.")
        else:
            show_concept(target_key, concepts[target_key])
        return

    # Prepare concept entry
    if is_new_concept:
        if not args.description and not args.add_keywords:
            print(
                f"ERROR: New concept '{target_key}' requires --description or --add-keyword",
                file=sys.stderr,
            )
            sys.exit(1)
        concept = {
            "description": args.description or "",
            "keywords": [],
        }
    else:
        concept = concepts[target_key]

    # Track changes
    changes = []

    # Update description
    if args.description and args.description != concept.get("description"):
        old_desc = concept.get("description", "(none)")
        concept["description"] = args.description
        changes.append(f"Description: {old_desc} -> {args.description}")

    # Add to lists
    field_mappings = [
        ("keywords", args.add_keywords),
        ("c_terms", args.add_c_terms),
        ("rust_terms", args.add_rust_terms),
        ("aliases", args.add_aliases),
        ("fls_ids", args.add_fls_ids),
        ("reference_ids", args.add_reference_ids),
        ("ucg_ids", args.add_ucg_ids),
        ("nomicon_ids", args.add_nomicon_ids),
        ("clippy_lints", args.add_clippy_lints),
    ]

    for field, values in field_mappings:
        if values:
            added = add_to_list(concept, field, values)
            if added:
                changes.append(f"Added to {field}: {', '.join(added)}")

    # Validate IDs if not skipping
    if valid_ids and not args.skip_validation:
        validation = validate_concept_ids(target_key, concept, valid_ids)
        if not validation.valid:
            print(f"ERROR: Invalid IDs found:", file=sys.stderr)
            for msg in validation.error_messages():
                print(f"  {msg}", file=sys.stderr)
            sys.exit(1)

    # Report changes
    if not changes:
        print("No changes to make.")
        return

    print(f"\n{'='*60}")
    if is_new_concept:
        print(f"Creating new concept: {target_key}")
    else:
        print(f"Updating concept: {target_key}")
    print(f"{'='*60}")

    for change in changes:
        print(f"  • {change}")

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        return

    # Update crosswalk
    concepts[target_key] = concept
    crosswalk["concepts"] = concepts

    # Update metadata last_updated
    from datetime import date
    crosswalk["metadata"]["last_updated"] = date.today().isoformat()

    # Save
    save_crosswalk(crosswalk_path, crosswalk)
    print(f"\nSaved to {crosswalk_path}")

    # Regenerate embeddings cache since concepts changed
    if not is_new_concept or args.add_keywords or args.description:
        print("Regenerating concept embeddings cache...")
        concept_embeddings.load_or_generate(concepts, cache_path=None)  # Force regenerate
        concept_embeddings.load_or_generate(concepts, cache_path=embeddings_cache)
        print(f"Saved embeddings to {embeddings_cache}")


if __name__ == "__main__":
    main()
