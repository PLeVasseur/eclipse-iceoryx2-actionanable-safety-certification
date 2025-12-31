#!/usr/bin/env python3
"""
Sync fls_section_mapping.json with fabricated sections from extracted FLS content.

This script reads the extracted FLS chapter files and generates fabricated
section entries for rubric content (legality rules, dynamic semantics, etc.)
that doesn't have traditional section headings in the FLS.

The fabricated sections use a negative number encoding scheme:
    X.-1.Y  = General (intro text before first rubric)
    X.-2.Y  = Legality Rules
    X.-3.Y  = Dynamic Semantics
    X.-4.Y  = Undefined Behavior
    X.-5.Y  = Implementation Requirements
    X.-6.Y  = Implementation Permissions
    X.-7.Y  = Examples
    X.-8.Y  = Syntax

Usage:
    uv run python tools/sync_fls_section_mapping.py [--dry-run]

Options:
    --dry-run    Show what would be added without modifying the file

Output:
    Updates tools/fls_section_mapping.json with fabricated section entries
"""

import argparse
import json
from datetime import date
from pathlib import Path


# Category codes mapping (must match extract_fls_content.py)
CATEGORY_CODES = {
    "section": 0,
    "general": -1,
    "legality_rules": -2,
    "dynamic_semantics": -3,
    "undefined_behavior": -4,
    "implementation_requirements": -5,
    "implementation_permissions": -6,
    "examples": -7,
    "syntax": -8,
}

# Human-readable names for fabricated section keys
CATEGORY_SECTION_KEYS = {
    -1: "_general",
    -2: "_legality_rules",
    -3: "_dynamic_semantics",
    -4: "_undefined_behavior",
    -5: "_implementation_requirements",
    -6: "_implementation_permissions",
    -7: "_examples",
    -8: "_syntax",
}

CATEGORY_TITLES = {
    -1: "General",
    -2: "Legality Rules",
    -3: "Dynamic Semantics",
    -4: "Undefined Behavior",
    -5: "Implementation Requirements",
    -6: "Implementation Permissions",
    -7: "Examples",
    -8: "Syntax",
}


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def load_fls_index(project_root: Path) -> dict:
    """Load FLS index.json."""
    index_path = project_root / "embeddings" / "fls" / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(
            f"FLS index not found at {index_path}. "
            "Run extract_fls_content.py first."
        )
    with open(index_path, encoding='utf-8') as f:
        return json.load(f)


def load_chapter_file(project_root: Path, filename: str) -> dict:
    """Load a chapter JSON file."""
    chapter_path = project_root / "embeddings" / "fls" / filename
    with open(chapter_path, encoding='utf-8') as f:
        return json.load(f)


def load_section_mapping(project_root: Path) -> dict:
    """Load existing fls_section_mapping.json."""
    mapping_path = project_root / "tools" / "fls_section_mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(f"Section mapping not found at {mapping_path}")
    with open(mapping_path, encoding='utf-8') as f:
        return json.load(f)


def save_section_mapping(project_root: Path, mapping: dict):
    """Save updated fls_section_mapping.json."""
    mapping_path = project_root / "tools" / "fls_section_mapping.json"
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)


def generate_fabricated_sections(chapter_data: dict) -> dict:
    """
    Generate fabricated section entries for a chapter's rubric content.
    
    Returns dict of fabricated sections to add under the chapter's "sections" key.
    """
    chapter_num = chapter_data['chapter']
    fabricated = {}
    
    # Track which categories have content and their paragraph counts
    category_paragraphs = {}  # category_code -> list of (section_fls_id, paragraph_id)
    
    for section in chapter_data['sections']:
        section_fls_id = section['fls_id']
        
        for cat_key, rubric_data in section.get('rubrics', {}).items():
            cat_code = int(cat_key)
            if cat_code not in category_paragraphs:
                category_paragraphs[cat_code] = []
            
            for para_id in rubric_data.get('paragraphs', {}).keys():
                category_paragraphs[cat_code].append((section_fls_id, para_id))
    
    # Generate fabricated section entries for each category with content
    for cat_code, paragraphs in sorted(category_paragraphs.items()):
        if cat_code == 0:  # Skip "section" category
            continue
        
        section_key = CATEGORY_SECTION_KEYS.get(cat_code)
        if not section_key:
            continue
        
        # Create the top-level fabricated section (e.g., 8.-2)
        fls_section = f"{chapter_num}.{cat_code}"
        
        fabricated[section_key] = {
            "fls_section": fls_section,
            "title": CATEGORY_TITLES.get(cat_code, "Unknown"),
            "category": cat_code,
            "fls_id": None,  # Fabricated sections don't have native FLS IDs
            "paragraph_count": len(paragraphs),
            "subsections": {}
        }
        
        # Group paragraphs by their parent section
        by_section = {}
        for section_fls_id, para_id in paragraphs:
            if section_fls_id not in by_section:
                by_section[section_fls_id] = []
            by_section[section_fls_id].append(para_id)
        
        # Create subsection entries for each parent section that has this rubric
        ordinal = 1
        for section_fls_id, para_ids in by_section.items():
            # Find the section title
            section_title = None
            for s in chapter_data['sections']:
                if s['fls_id'] == section_fls_id:
                    section_title = s['title']
                    break
            
            subsection_key = f"from_{section_fls_id}"
            subsection_fls_section = f"{chapter_num}.{cat_code}.{ordinal}"
            
            fabricated[section_key]["subsections"][subsection_key] = {
                "fls_section": subsection_fls_section,
                "title": section_title or section_fls_id,
                "category": cat_code,
                "fls_id": section_fls_id,  # Reference to parent section
                "paragraph_ids": para_ids,
                "paragraph_count": len(para_ids)
            }
            ordinal += 1
    
    return fabricated


def merge_fabricated_sections(existing_sections: dict, fabricated: dict) -> dict:
    """
    Merge fabricated sections into existing sections dict.
    
    Fabricated sections (keys starting with _) are replaced entirely.
    Existing non-fabricated sections are preserved.
    """
    # Remove old fabricated sections
    result = {k: v for k, v in existing_sections.items() if not k.startswith('_')}
    
    # Add new fabricated sections
    result.update(fabricated)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Sync fls_section_mapping.json with fabricated sections'
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be added without modifying the file')
    args = parser.parse_args()
    
    project_root = get_project_root()
    
    # Load FLS index
    print("Loading FLS index...")
    index = load_fls_index(project_root)
    print(f"  Found {len(index['chapters'])} chapters")
    
    # Load existing section mapping
    print("\nLoading existing section mapping...")
    mapping = load_section_mapping(project_root)
    print(f"  Found {len(mapping)} chapters in mapping")
    
    # Process each chapter
    print("\nGenerating fabricated sections...")
    total_fabricated = 0
    total_paragraphs = 0
    
    for chapter_info in index['chapters']:
        chapter_num = chapter_info['chapter']
        chapter_key = str(chapter_num)
        
        # Load chapter data
        chapter_data = load_chapter_file(project_root, chapter_info['file'])
        
        # Generate fabricated sections
        fabricated = generate_fabricated_sections(chapter_data)
        
        if fabricated:
            fab_count = len(fabricated)
            para_count = sum(f.get('paragraph_count', 0) for f in fabricated.values())
            total_fabricated += fab_count
            total_paragraphs += para_count
            
            print(f"  Chapter {chapter_num:02d}: {fab_count} fabricated sections, {para_count} paragraphs")
            
            if args.dry_run:
                for key, value in fabricated.items():
                    print(f"    {key}: {value['fls_section']} ({value['paragraph_count']} paragraphs)")
            else:
                # Merge into mapping
                if chapter_key in mapping:
                    if 'sections' not in mapping[chapter_key]:
                        mapping[chapter_key]['sections'] = {}
                    mapping[chapter_key]['sections'] = merge_fabricated_sections(
                        mapping[chapter_key]['sections'],
                        fabricated
                    )
    
    print(f"\nTotal: {total_fabricated} fabricated sections, {total_paragraphs} paragraphs")
    
    if args.dry_run:
        print("\n[DRY RUN] No changes made to fls_section_mapping.json")
    else:
        # Save updated mapping
        print("\nSaving updated section mapping...")
        save_section_mapping(project_root, mapping)
        print(f"  Saved to: {project_root / 'tools' / 'fls_section_mapping.json'}")
    
    return 0


if __name__ == "__main__":
    exit(main())
