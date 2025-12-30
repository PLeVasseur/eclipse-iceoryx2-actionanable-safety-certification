#!/usr/bin/env python3
"""
Migrate content from backup FLS chapter files to new restructured files.

This script handles:
1. Key name mapping (e.g., 'array_expression' -> 'array_expressions')
2. Merging content from backup into correct sections
3. Reporting unmigrated content
"""

import json
import glob
import re
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
FLS_MAPPING_DIR = ROOT_DIR / "iceoryx2-fls-mapping"
BACKUP_DIR = FLS_MAPPING_DIR / "backup"

# Key mappings for specific chapters
# Format: {chapter: {backup_key: mapping_key}}
KEY_MAPPINGS = {
    2: {
        "lexical_elements_separators_punctuation": "lexical_elements_separators_and_punctuation",
    },
    3: {
        # Simplified keys to full declaration names
        "modules": "module_declaration",
        "structs": "struct_declaration",
        "enums": "enum_declaration",
        "unions": "union_declaration",
        "type_aliases": "type_alias_declaration",
        "traits": "trait_declaration",
        "constants": "constant_declaration",
        "statics": "static_declaration",
        "functions": "function_declaration",
        "extern_blocks": "external_block",
        "extern_crate": "external_crate_import",
        "visibility": None,  # No direct mapping - content goes to design_patterns
        "derive_macros": "macro_rules_declaration",  # Best match
    },
    4: {
        # Chapter 4 has nested structure differences
        "marker_traits": None,  # Will handle in design_patterns
        "drop_trait": None,  # Will handle in design_patterns
    },
    6: {
        # Singular to plural mappings
        "array_expression": "array_expressions",
        "await_expression": "await_expressions",
        "break_expression": "loop_expressions",  # break is part of loop expressions
        "call_expression": "invocation_expressions",  # Fixed: call -> invocation
        "closure_expression": "closure_expressions",
        "continue_expression": "loop_expressions",  # continue is part of loop expressions
        "field_access_expression": "field_access_expressions",
        "if_expression": "if_and_if_let_expressions",
        "if_let_expression": "if_and_if_let_expressions",
        "index_expression": "indexing_expressions",  # Fixed: index -> indexing
        "loop_expression": "loop_expressions",
        "match_expression": "match_expressions",
        "method_call_expression": "invocation_expressions",  # Fixed: method_call -> invocation
        "parenthesized_expression": "parenthesized_expressions",
        "range_expression": "range_expressions",
        "return_expression": "return_expressions",
        "struct_expression": "struct_expressions",
        "tuple_expression": "tuple_expressions",
        "underscore_expression": "underscore_expressions",
    },
    7: {
        "values_overview": None,  # Will merge into other sections
    },
    8: {
        "statements_overview": None,  # Will merge into expression_statements
        "item_statements": None,  # No direct mapping
        "macro_statements": None,  # No direct mapping  
        "empty_statements": None,  # No direct mapping
    },
    12: {
        # Numbered keys to semantic keys
        "12.1": "generic_parameters",
        "12.2": "generic_arguments",  # Fixed
        "12.3": "where_clauses",  # Fixed
        "12.4": "generic_conformance",
    },
    13: {
        # Numbered keys to semantic keys
        "13.1": "attribute_properties",
        "13.2": "builtin_attributes",
        "13.2.1": None,  # These are subsections, will be handled
        "13.2.2": None,
        "13.2.3": None,
        "13.2.4": None,
        "13.2.5": None,
        "13.2.6": None,
        "13.2.7": None,
        "13.2.8": None,
        "13.2.9": None,
        "13.2.10": None,
        "13.2.11": None,
        "13.2.12": None,
        "13.2.13": None,
    },
    14: {
        # Numbered keys to semantic keys
        "14.1": "entities",
        "14.2": "namespaces",
        "14.3": "resolution",
        "14.4": "scopes",  # Fixed: scope -> scopes
        "14.5": "shadowing",
        "14.6": "visibility",
        "14.7": "preludes",
        "14.8": "paths",  # Fixed: path_resolution -> paths
        "14.9": "use_imports",  # Fixed: name_resolution -> use_imports
    },
    19: {
        # Single section to multiple sections - will need special handling
        "unsafe_operations": None,  
    },
    22: {
        "macros_asm_globalasm_and_nakedasm": "macros_asm_global_asm_and_naked_asm",
    },
}


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find_best_section_match(backup_key: str, mapping_keys: set, chapter: int) -> str | None:
    """Find the best matching mapping key for a backup key."""
    # Direct match
    if backup_key in mapping_keys:
        return backup_key
    
    # Check explicit mapping
    if chapter in KEY_MAPPINGS and backup_key in KEY_MAPPINGS[chapter]:
        mapped = KEY_MAPPINGS[chapter][backup_key]
        if mapped and mapped in mapping_keys:
            return mapped
    
    # Try singular/plural variations
    if backup_key.endswith("s") and backup_key[:-1] in mapping_keys:
        return backup_key[:-1]
    if backup_key + "s" in mapping_keys:
        return backup_key + "s"
    
    # Try adding/removing underscores and 'and'
    variations = [
        backup_key.replace("_", "_and_"),
        backup_key.replace("_and_", "_"),
    ]
    for var in variations:
        if var in mapping_keys:
            return var
    
    return None


def migrate_section_content(backup_section: dict, template_section: dict) -> dict:
    """Migrate content from backup section to template section."""
    result = template_section.copy()
    
    # Copy findings
    if backup_section.get("findings"):
        result["findings"] = backup_section["findings"]
    
    # Copy samples
    if backup_section.get("samples"):
        result["samples"] = backup_section["samples"]
    
    # Copy status
    if backup_section.get("status") and backup_section["status"] != "MUST_BE_FILLED":
        result["status"] = backup_section["status"]
    
    # Copy safety_notes
    if backup_section.get("safety_notes"):
        result["safety_notes"] = backup_section["safety_notes"]
    
    # Handle subsections
    if backup_section.get("subsections") and template_section.get("subsections"):
        for sub_key, sub_content in backup_section["subsections"].items():
            if sub_key in template_section["subsections"]:
                result["subsections"][sub_key] = migrate_section_content(
                    sub_content, template_section["subsections"][sub_key]
                )
    
    return result


def migrate_chapter(chapter_num: int) -> tuple[dict | None, list]:
    """
    Migrate a chapter from backup to new structure.
    Returns (migrated_data, unmigrated_content).
    """
    # Load files
    template_files = list(glob.glob(str(FLS_MAPPING_DIR / f"fls_chapter{chapter_num:02d}_*.json")))
    backup_files = list(glob.glob(str(BACKUP_DIR / f"fls_chapter{chapter_num:02d}_*.json")))
    
    if not template_files or not backup_files:
        return None, [f"Chapter {chapter_num}: Missing files"]
    
    template = load_json(Path(template_files[0]))
    backup = load_json(Path(backup_files[0]))
    
    unmigrated = []
    mapping_keys = set(template.get("sections", {}).keys())
    
    # Preserve metadata from backup
    for key in ["version_changes", "summary", "statistics", "design_patterns", 
                "cross_chapter_references", "safety_critical_summary"]:
        if key in backup and backup[key]:
            template[key] = backup[key]
    
    # Migrate sections
    for backup_key, backup_section in backup.get("sections", {}).items():
        target_key = find_best_section_match(backup_key, mapping_keys, chapter_num)
        
        if target_key:
            template["sections"][target_key] = migrate_section_content(
                backup_section, template["sections"][target_key]
            )
        else:
            unmigrated.append({
                "chapter": chapter_num,
                "backup_key": backup_key,
                "content_summary": {
                    "has_findings": bool(backup_section.get("findings")),
                    "has_samples": bool(backup_section.get("samples")),
                    "status": backup_section.get("status"),
                }
            })
    
    return template, unmigrated


def main():
    # Chapters that need migration (not exact matches, not empty)
    chapters_to_migrate = [2, 3, 4, 6, 7, 8, 12, 13, 14, 19, 22]
    
    all_unmigrated = []
    
    for chapter in chapters_to_migrate:
        print(f"Migrating Chapter {chapter}...")
        result, unmigrated = migrate_chapter(chapter)
        
        if result:
            files = list(glob.glob(str(FLS_MAPPING_DIR / f"fls_chapter{chapter:02d}_*.json")))
            save_json(Path(files[0]), result)
            print(f"  Saved {files[0]}")
        
        if unmigrated:
            all_unmigrated.extend(unmigrated)
            for item in unmigrated:
                print(f"  UNMIGRATED: {item['backup_key']}")
    
    # Report unmigrated content
    if all_unmigrated:
        print("\n" + "="*60)
        print("UNMIGRATED CONTENT REPORT")
        print("="*60)
        for item in all_unmigrated:
            print(f"\nChapter {item['chapter']}: '{item['backup_key']}'")
            print(f"  Has findings: {item['content_summary']['has_findings']}")
            print(f"  Has samples: {item['content_summary']['has_samples']}")
            print(f"  Status: {item['content_summary']['status']}")
    else:
        print("\nAll content migrated successfully!")


if __name__ == "__main__":
    main()
