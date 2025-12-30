#!/usr/bin/env python3
"""
Restructure FLS chapter JSON files to match fls_section_mapping.json structure.

This script:
1. Reads fls_section_mapping.json for the authoritative section structure
2. Reads existing chapter JSON files for metadata and content
3. Generates new JSON files with correct section structure and placeholder content

Usage:
    python restructure_fls_json.py [--dry-run] [--chapter N]
    
Options:
    --dry-run   Print what would be done without writing files
    --chapter N Only process chapter N (for testing)
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import date
from typing import Any

# Paths
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
MAPPING_FILE = SCRIPT_DIR / "fls_section_mapping.json"
FLS_MAPPING_DIR = ROOT_DIR / "iceoryx2-fls-mapping"
BACKUP_DIR = FLS_MAPPING_DIR / "backup"

# Chapter file name mapping
CHAPTER_FILES = {
    2: "fls_chapter02_lexical_elements.json",
    3: "fls_chapter03_items.json",
    4: "fls_chapter04_types_and_traits.json",
    5: "fls_chapter05_patterns.json",
    6: "fls_chapter06_expressions.json",
    7: "fls_chapter07_values.json",
    8: "fls_chapter08_statements.json",
    9: "fls_chapter09_functions.json",
    10: "fls_chapter10_associated_items.json",
    11: "fls_chapter11_implementations.json",
    12: "fls_chapter12_generics.json",
    13: "fls_chapter13_attributes.json",
    14: "fls_chapter14_entities_resolution.json",
    15: "fls_chapter15_ownership_destruction.json",
    16: "fls_chapter16_exceptions_errors.json",
    17: "fls_chapter17_concurrency.json",
    18: "fls_chapter18_program_structure.json",
    19: "fls_chapter19_unsafety.json",
    20: "fls_chapter20_macros.json",
    21: "fls_chapter21_ffi.json",
    22: "fls_chapter22_inline_assembly.json",
}

# FLS URL base
FLS_URL_BASE = "https://rust-lang.github.io/fls/"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict, dry_run: bool = False) -> None:
    """Save JSON file with consistent formatting."""
    if dry_run:
        print(f"[DRY RUN] Would write to: {path}")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote: {path}")


def create_section_template(section_data: dict, section_key: str) -> dict:
    """Create a section template from mapping data."""
    section = {
        "fls_section": section_data.get("fls_section", "MUST_BE_FILLED"),
        "fls_ids": [section_data["fls_id"]] if section_data.get("fls_id") else [],
        "description": section_data.get("title", "MUST_BE_FILLED"),
        "status": "MUST_BE_FILLED",
        "findings": {},
        "samples": [],
    }
    
    # Process subsections recursively
    if "subsections" in section_data:
        section["subsections"] = {}
        for sub_key, sub_data in section_data["subsections"].items():
            section["subsections"][sub_key] = create_section_template(sub_data, sub_key)
    
    return section


def create_chapter_template(chapter_num: int, mapping_data: dict, existing_data: dict | None) -> dict:
    """Create a chapter template from mapping data, preserving existing metadata."""
    chapter_mapping = mapping_data.get(str(chapter_num), {})
    
    # Determine FLS URL
    file_name = chapter_mapping.get("file", "")
    fls_url = f"{FLS_URL_BASE}{file_name}.html" if file_name else "MUST_BE_FILLED"
    
    # Start with template structure
    template = {
        "chapter": chapter_num,
        "title": chapter_mapping.get("title", "MUST_BE_FILLED"),
        "fls_url": fls_url,
        "fls_id": chapter_mapping.get("fls_id", "MUST_BE_FILLED"),
        "repository": "eclipse-iceoryx/iceoryx2",
        "version": "0.8.0",
        "analysis_date": str(date.today()),
        "version_changes": {
            "from_version": "0.7.0",
            "to_version": "0.8.0",
            "summary": "MUST_BE_FILLED",
            "key_changes": []
        },
        "summary": "MUST_BE_FILLED",
        "statistics": {},
        "sections": {},
    }
    
    # Preserve existing metadata if available
    if existing_data:
        for key in ["version_changes", "summary", "statistics", "design_patterns", 
                    "cross_chapter_references", "safety_critical_summary"]:
            if key in existing_data and existing_data[key]:
                template[key] = existing_data[key]
        
        # Preserve analysis_date if already set
        if "analysis_date" in existing_data:
            template["analysis_date"] = existing_data["analysis_date"]
    
    # Create sections from mapping
    sections_mapping = chapter_mapping.get("sections", {})
    for section_key, section_data in sections_mapping.items():
        template["sections"][section_key] = create_section_template(section_data, section_key)
    
    return template


def process_chapter(chapter_num: int, mapping_data: dict, dry_run: bool = False) -> dict:
    """Process a single chapter and return the new template."""
    filename = CHAPTER_FILES.get(chapter_num)
    if not filename:
        print(f"Warning: No filename defined for chapter {chapter_num}")
        return {}
    
    existing_path = FLS_MAPPING_DIR / filename
    backup_path = BACKUP_DIR / filename
    
    # Load existing data if available
    existing_data = None
    if backup_path.exists():
        existing_data = load_json(backup_path)
        print(f"Loaded backup: {backup_path}")
    elif existing_path.exists():
        existing_data = load_json(existing_path)
        print(f"Loaded existing: {existing_path}")
    else:
        print(f"No existing data for chapter {chapter_num}")
    
    # Create new template
    template = create_chapter_template(chapter_num, mapping_data, existing_data)
    
    # Save to FLS mapping directory
    output_path = FLS_MAPPING_DIR / filename
    save_json(output_path, template, dry_run)
    
    return template


def main():
    parser = argparse.ArgumentParser(description="Restructure FLS chapter JSON files")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    parser.add_argument("--chapter", type=int, help="Only process specific chapter")
    args = parser.parse_args()
    
    # Load mapping
    if not MAPPING_FILE.exists():
        print(f"Error: Mapping file not found: {MAPPING_FILE}")
        sys.exit(1)
    
    mapping_data = load_json(MAPPING_FILE)
    print(f"Loaded mapping with {len(mapping_data)} chapters")
    
    # Determine which chapters to process
    if args.chapter:
        chapters = [args.chapter]
    else:
        # Process all chapters that have mappings (skip chapter 1 as discussed)
        chapters = [int(k) for k in mapping_data.keys() if k.isdigit() and int(k) != 1]
        chapters.sort()
    
    print(f"Processing chapters: {chapters}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    # Process each chapter
    for chapter_num in chapters:
        print(f"--- Chapter {chapter_num} ---")
        process_chapter(chapter_num, mapping_data, args.dry_run)
        print()
    
    print("Done!")
    if args.dry_run:
        print("(No files were written - remove --dry-run to apply changes)")


if __name__ == "__main__":
    main()
