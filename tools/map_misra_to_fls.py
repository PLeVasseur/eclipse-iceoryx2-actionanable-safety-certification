#!/usr/bin/env python3
"""
Map MISRA C:2025 guidelines to Ferrocene Language Specification (FLS) sections.

This script:
1. Loads MISRA C:2025 rules from standards/misra_c_2025.json
2. Loads MISRA ADD-6 Rust applicability data from misra_rust_applicability.json
3. Loads concept-to-FLS mappings from concept_to_fls.json
4. Matches guideline titles against concept keywords
5. Generates draft FLS mappings with low confidence

Usage:
    uv run python map_misra_to_fls.py [--limit N] [--rules-only] [--output PATH]
    
Options:
    --limit N       Process only first N guidelines (for testing)
    --rules-only    Skip directives, process only rules
    --output PATH   Output file path (default: ../coding-standards-fls-mapping/mappings/misra_c_to_fls.json)
    --verbose       Print detailed matching information
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, path: Path) -> None:
    """Save data to a JSON file with pretty formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")


def normalize_text(text: str) -> str:
    """Normalize text for keyword matching."""
    # Lowercase, replace hyphens with spaces, remove extra whitespace
    text = text.lower()
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def match_concepts(title: str, concepts: dict[str, dict], verbose: bool = False) -> list[str]:
    """
    Match a guideline title against concept keywords.
    Returns list of matched concept names.
    """
    normalized_title = normalize_text(title)
    matched = []
    
    for concept_name, concept_data in concepts.items():
        keywords = concept_data.get("keywords", [])
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            # Check if keyword appears in title (word boundary aware for short keywords)
            if len(normalized_keyword) <= 3:
                # For short keywords, require word boundary
                pattern = rf"\b{re.escape(normalized_keyword)}\b"
                if re.search(pattern, normalized_title):
                    if concept_name not in matched:
                        matched.append(concept_name)
                        if verbose:
                            print(f"  Matched '{keyword}' -> {concept_name}")
                    break
            else:
                # For longer keywords, simple substring match
                if normalized_keyword in normalized_title:
                    if concept_name not in matched:
                        matched.append(concept_name)
                        if verbose:
                            print(f"  Matched '{keyword}' -> {concept_name}")
                    break
    
    return matched


def get_misra_category_hint(guideline_id: str, category_hints: dict) -> tuple[list[str], str | None, str | None]:
    """
    Get hint from MISRA category (e.g., 'Rule 11' for pointer conversions).
    Returns (concept_list, typical_applicability_all, typical_applicability_safe)
    """
    # Extract rule number (e.g., "Rule 11.1" -> "Rule 11")
    match = re.match(r"(Rule|Dir)\s+(\d+)", guideline_id)
    if not match:
        return [], None, None
    
    category = f"{match.group(1)} {match.group(2)}"
    hint = category_hints.get(category)
    if hint:
        return (
            hint.get("concepts", []),
            hint.get("typical_applicability_all_rust"),
            hint.get("typical_applicability_safe_rust")
        )
    return [], None, None


def collect_fls_ids(concept_names: list[str], concepts: dict[str, dict]) -> tuple[list[str], list[str]]:
    """
    Collect all FLS IDs and sections from matched concepts.
    Returns (fls_ids, fls_sections) with duplicates removed.
    """
    fls_ids = []
    fls_sections = []
    
    for name in concept_names:
        concept = concepts.get(name, {})
        for fls_id in concept.get("fls_ids", []):
            if fls_id and fls_id not in fls_ids:
                fls_ids.append(fls_id)
        for section in concept.get("fls_sections", []):
            if section and section not in fls_sections:
                fls_sections.append(section)
    
    return fls_ids, fls_sections


def determine_applicability(
    concept_names: list[str],
    concepts: dict[str, dict],
    category_hint_all: str | None,
    category_hint_safe: str | None
) -> tuple[str, str]:
    """
    Determine applicability values based on matched concepts.
    Returns (applicability_all_rust, applicability_safe_rust)
    """
    if not concept_names:
        return "unmapped", "unmapped"
    
    # Collect applicabilities from all matched concepts
    all_rust_apps = []
    safe_rust_apps = []
    
    for name in concept_names:
        concept = concepts.get(name, {})
        all_app = concept.get("typical_applicability_all_rust")
        safe_app = concept.get("typical_applicability_safe_rust")
        if all_app:
            all_rust_apps.append(all_app)
        if safe_app:
            safe_rust_apps.append(safe_app)
    
    # Priority: not_applicable > rust_prevents > partial > direct > unmapped
    priority = ["not_applicable", "rust_prevents", "partial", "direct", "unmapped"]
    
    def pick_best(apps: list[str], hint: str | None) -> str:
        if not apps:
            return hint or "unmapped"
        # Return the highest priority value found
        for p in priority:
            if p in apps:
                return p
        return hint or "unmapped"
    
    return (
        pick_best(all_rust_apps, category_hint_all),
        pick_best(safe_rust_apps, category_hint_safe)
    )


def convert_misra_applicability(misra_app: str, misra_category: str | None = None) -> str:
    """Convert MISRA ADD-6 applicability to our schema values.
    
    If misra_category is 'implicit', it means the Rust compiler enforces this,
    which maps to 'rust_prevents'.
    """
    # Special case: if MISRA says the compiler enforces it, that's rust_prevents
    if misra_category and misra_category.lower() == "implicit":
        return "rust_prevents"
    
    mapping = {
        "Yes": "direct",
        "No": "not_applicable", 
        "Partial": "partial"
    }
    return mapping.get(misra_app, "unmapped")


def convert_misra_category(misra_cat: str) -> str | None:
    """Convert MISRA ADD-6 adjusted category to our schema values."""
    mapping = {
        "required": "required",
        "advisory": "advisory",
        "recommended": "recommended",
        "disapplied": "disapplied",
        "implicit": "implicit",
        "n_a": "n_a"
    }
    return mapping.get(misra_cat.lower() if misra_cat else "", None)


def determine_fls_rationale_type(
    applicability_all: str,
    applicability_safe: str,
    concept_names: list[str],
    has_fls_ids: bool
) -> str | None:
    """
    Determine the fls_rationale_type based on applicability and matched concepts.
    Returns None if no FLS IDs are present.
    """
    if not has_fls_ids:
        return None
    
    # Map applicability to rationale type
    if applicability_all == "rust_prevents" or applicability_safe == "rust_prevents":
        return "rust_prevents"
    elif applicability_all == "not_applicable":
        # FLS IDs are for context/alternative concepts
        return "no_equivalent"
    elif applicability_all == "partial" or applicability_safe == "partial":
        return "partial_mapping"
    elif applicability_all == "direct":
        return "direct_mapping"
    else:
        # Default for unmapped or unknown
        return "partial_mapping"


def generate_notes(
    guideline_id: str,
    concept_names: list[str],
    concepts: dict[str, dict],
    misra_rust_data: dict | None,
    applicability_all: str,
    applicability_safe: str
) -> str:
    """Generate notes explaining the mapping."""
    notes_parts = []
    
    # Add MISRA's comment if available
    if misra_rust_data and misra_rust_data.get("comment"):
        notes_parts.append(f"MISRA ADD-6: {misra_rust_data['comment']}")
    
    # Add concept-based rationale
    if concept_names:
        rationales = []
        for name in concept_names[:3]:  # Limit to first 3 to avoid too long notes
            concept = concepts.get(name, {})
            rationale = concept.get("rationale")
            if rationale:
                rationales.append(rationale)
        if rationales:
            notes_parts.append("; ".join(rationales[:2]))  # Limit to 2 rationales
    
    # Add applicability explanation if different between all/safe
    if applicability_all != applicability_safe:
        if applicability_safe == "rust_prevents" and applicability_all == "partial":
            notes_parts.append("Safe Rust prevents this issue; applies to unsafe code")
        elif applicability_safe == "not_applicable" and applicability_all != "not_applicable":
            notes_parts.append("Only applicable in unsafe Rust")
    
    return ". ".join(notes_parts) if notes_parts else "Automated mapping - requires manual review"


def create_mapping_entry(
    guideline: dict,
    concepts_data: dict,
    misra_rust_data: dict | None,
    category_hints: dict,
    verbose: bool = False
) -> dict:
    """Create a single mapping entry for a guideline."""
    guideline_id = guideline["id"]
    title = guideline.get("title", "")
    guideline_type = guideline.get("guideline_type", "rule")
    
    if verbose:
        print(f"\n{guideline_id}: {title}")
    
    concepts = concepts_data.get("concepts", {})
    
    # Step 1: Match title against concept keywords
    matched_concepts = match_concepts(title, concepts, verbose)
    
    # Step 2: Get category hints
    hint_concepts, hint_all, hint_safe = get_misra_category_hint(guideline_id, category_hints)
    
    # Add category hint concepts if not already matched
    for c in hint_concepts:
        if c not in matched_concepts:
            matched_concepts.append(c)
    
    # Step 3: Collect FLS IDs from matched concepts
    fls_ids, fls_sections = collect_fls_ids(matched_concepts, concepts)
    
    # Step 4: Determine applicability
    if misra_rust_data:
        # Use MISRA ADD-6 data if available
        raw_category = misra_rust_data.get("adjusted_category", "")
        applicability_all = convert_misra_applicability(
            misra_rust_data.get("applicability_all_rust", ""), raw_category
        )
        applicability_safe = convert_misra_applicability(
            misra_rust_data.get("applicability_safe_rust", ""), raw_category
        )
        misra_category = convert_misra_category(raw_category)
        misra_comment = misra_rust_data.get("comment") or None
    else:
        # Fallback to concept-based determination
        applicability_all, applicability_safe = determine_applicability(
            matched_concepts, concepts, hint_all, hint_safe
        )
        misra_category = None
        misra_comment = None
    
    # Step 5: Generate notes
    notes = generate_notes(
        guideline_id, matched_concepts, concepts,
        misra_rust_data, applicability_all, applicability_safe
    )
    
    # Step 6: Determine confidence
    if not fls_ids and applicability_all not in ["not_applicable", "rust_prevents"]:
        confidence = None  # No FLS mapping found
    elif misra_rust_data:
        confidence = "medium"  # Has MISRA ADD-6 data
    elif matched_concepts:
        confidence = "low"  # Only keyword matching
    else:
        confidence = None
    
    if verbose:
        print(f"  -> Concepts: {matched_concepts}")
        print(f"  -> FLS IDs: {len(fls_ids)}, Sections: {len(fls_sections)}")
        print(f"  -> Applicability: all={applicability_all}, safe={applicability_safe}")
    
    entry = {
        "guideline_id": guideline_id,
        "guideline_title": title,
        "guideline_type": guideline_type,
        "applicability_all_rust": applicability_all,
        "applicability_safe_rust": applicability_safe,
    }
    
    # Add FLS data only if we have it
    if fls_ids:
        entry["fls_ids"] = fls_ids
        # Add rationale type when FLS IDs are present (required by schema)
        rationale_type = determine_fls_rationale_type(
            applicability_all, applicability_safe, matched_concepts, bool(fls_ids)
        )
        if rationale_type:
            entry["fls_rationale_type"] = rationale_type
    if fls_sections:
        entry["fls_sections"] = fls_sections
    
    # Add MISRA-specific fields
    if misra_category:
        entry["misra_rust_category"] = misra_category
    if misra_comment:
        entry["misra_rust_comment"] = misra_comment
    
    # Add confidence and notes
    if confidence:
        entry["confidence"] = confidence
    entry["notes"] = notes
    
    return entry


def main():
    parser = argparse.ArgumentParser(description="Map MISRA C:2025 guidelines to FLS")
    parser.add_argument("--limit", type=int, help="Process only first N guidelines")
    parser.add_argument("--rules-only", action="store_true", help="Skip directives")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--verbose", action="store_true", help="Print detailed matching info")
    args = parser.parse_args()
    
    # Paths
    base_dir = Path(__file__).parent.parent / "coding-standards-fls-mapping"
    tools_dir = Path(__file__).parent
    
    standards_path = base_dir / "standards" / "misra_c_2025.json"
    rust_app_path = base_dir / "misra_rust_applicability.json"
    concepts_path = base_dir / "concept_to_fls.json"
    output_path = Path(args.output) if args.output else base_dir / "mappings" / "misra_c_to_fls.json"
    
    # Load data
    print("Loading data...")
    standards = load_json(standards_path)
    rust_applicability = load_json(rust_app_path)
    concepts_data = load_json(concepts_path)
    
    # Extract all guidelines from categories
    all_guidelines = []
    for category in standards.get("categories", []):
        for guideline in category.get("guidelines", []):
            all_guidelines.append(guideline)
    
    print(f"Loaded {len(all_guidelines)} guidelines from MISRA C:2025")
    print(f"Loaded {len(rust_applicability.get('guidelines', {}))} guidelines from MISRA ADD-6")
    print(f"Loaded {len(concepts_data.get('concepts', {}))} concepts")
    
    # Filter if needed
    if args.rules_only:
        all_guidelines = [g for g in all_guidelines if g.get("guideline_type") == "rule"]
        print(f"Filtered to {len(all_guidelines)} rules")
    
    if args.limit:
        all_guidelines = all_guidelines[:args.limit]
        print(f"Limited to {len(all_guidelines)} guidelines")
    
    # Process guidelines
    print("\nProcessing guidelines...")
    mappings = []
    category_hints = concepts_data.get("misra_category_hints", {})
    rust_guidelines = rust_applicability.get("guidelines", {})
    
    stats = {
        "total": 0,
        "direct": 0,
        "partial": 0,
        "not_applicable": 0,
        "rust_prevents": 0,
        "unmapped": 0,
        "with_fls_ids": 0,
    }
    
    for guideline in all_guidelines:
        guideline_id = guideline["id"]
        misra_rust_data = rust_guidelines.get(guideline_id)
        
        entry = create_mapping_entry(
            guideline, concepts_data, misra_rust_data,
            category_hints, args.verbose
        )
        mappings.append(entry)
        
        # Update stats
        stats["total"] += 1
        app_all = entry.get("applicability_all_rust", "unmapped")
        stats[app_all] = stats.get(app_all, 0) + 1
        if entry.get("fls_ids"):
            stats["with_fls_ids"] += 1
    
    # Create output structure
    output = {
        "standard": "MISRA-C",
        "standard_version": "2025",
        "fls_version": "1.0 (2024)",
        "mapping_date": date.today().isoformat(),
        "methodology": "Automated keyword matching against concept_to_fls.json with MISRA ADD-6 applicability data. All mappings have low/medium confidence and require manual review.",
        "statistics": {
            "total_guidelines": stats["total"],
            "mapped": stats["direct"] + stats["partial"],
            "unmapped": stats["unmapped"],
            "not_applicable": stats["not_applicable"],
            "rust_prevents": stats["rust_prevents"],
            "with_fls_references": stats["with_fls_ids"],
        },
        "mappings": mappings
    }
    
    # Save output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output, output_path)
    
    # Print summary
    print("\n" + "="*60)
    print("MAPPING SUMMARY")
    print("="*60)
    print(f"Total guidelines processed: {stats['total']}")
    print(f"  direct:         {stats['direct']}")
    print(f"  partial:        {stats['partial']}")
    print(f"  not_applicable: {stats['not_applicable']}")
    print(f"  rust_prevents:  {stats['rust_prevents']}")
    print(f"  unmapped:       {stats['unmapped']}")
    print(f"  with FLS IDs:   {stats['with_fls_ids']}")
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
