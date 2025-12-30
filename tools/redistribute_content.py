#!/usr/bin/env python3
"""
Redistribute unmigrated content to correct chapters based on FLS structure.
"""

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
FLS_MAPPING_DIR = ROOT_DIR / "iceoryx2-fls-mapping"
BACKUP_DIR = FLS_MAPPING_DIR / "backup"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def merge_section_content(target: dict, source: dict) -> dict:
    """Merge source section content into target section."""
    if source.get("findings"):
        if not target.get("findings"):
            target["findings"] = {}
        target["findings"].update(source["findings"])
    
    if source.get("samples"):
        if not target.get("samples"):
            target["samples"] = []
        target["samples"].extend(source["samples"])
    
    if source.get("status") and source["status"] != "MUST_BE_FILLED":
        target["status"] = source["status"]
    
    if source.get("safety_notes"):
        if not target.get("safety_notes"):
            target["safety_notes"] = []
        target["safety_notes"].extend(source["safety_notes"])
    
    return target


def redistribute_ch3_visibility_to_ch14():
    """Move Chapter 3 visibility content to Chapter 14 visibility section."""
    print("Redistributing Ch3 visibility -> Ch14 visibility...")
    
    backup3 = load_json(BACKUP_DIR / "fls_chapter03_items.json")
    ch14 = load_json(FLS_MAPPING_DIR / "fls_chapter14_entities_resolution.json")
    
    source = backup3.get("sections", {}).get("visibility", {})
    if source and "visibility" in ch14.get("sections", {}):
        ch14["sections"]["visibility"] = merge_section_content(
            ch14["sections"]["visibility"], source
        )
        save_json(FLS_MAPPING_DIR / "fls_chapter14_entities_resolution.json", ch14)
        print("  Done")
    else:
        print("  Skipped - source or target not found")


def redistribute_ch4_marker_traits():
    """Move Chapter 4 marker_traits content to Chapter 4 traits section."""
    print("Redistributing Ch4 marker_traits -> Ch4 traits...")
    
    backup4 = load_json(BACKUP_DIR / "fls_chapter04_types_and_traits.json")
    ch4 = load_json(FLS_MAPPING_DIR / "fls_chapter04_types_and_traits.json")
    
    source = backup4.get("sections", {}).get("marker_traits", {})
    if source and "traits" in ch4.get("sections", {}):
        ch4["sections"]["traits"] = merge_section_content(
            ch4["sections"]["traits"], source
        )
        save_json(FLS_MAPPING_DIR / "fls_chapter04_types_and_traits.json", ch4)
        print("  Done")
    else:
        print("  Skipped - source or target not found")


def redistribute_ch4_drop_trait_to_ch15():
    """Move Chapter 4 drop_trait content to Chapter 15 destructors section."""
    print("Redistributing Ch4 drop_trait -> Ch15 destructors...")
    
    backup4 = load_json(BACKUP_DIR / "fls_chapter04_types_and_traits.json")
    ch15 = load_json(FLS_MAPPING_DIR / "fls_chapter15_ownership_destruction.json")
    
    source = backup4.get("sections", {}).get("drop_trait", {})
    if source and "destructors" in ch15.get("sections", {}):
        ch15["sections"]["destructors"] = merge_section_content(
            ch15["sections"]["destructors"], source
        )
        save_json(FLS_MAPPING_DIR / "fls_chapter15_ownership_destruction.json", ch15)
        print("  Done")
    else:
        print("  Skipped - source or target not found")


def redistribute_ch7_values_overview():
    """Distribute Chapter 7 values_overview content to appropriate sections."""
    print("Redistributing Ch7 values_overview -> Ch7 sections...")
    
    backup7 = load_json(BACKUP_DIR / "fls_chapter07_values.json")
    ch7 = load_json(FLS_MAPPING_DIR / "fls_chapter07_values.json")
    
    source = backup7.get("sections", {}).get("values_overview", {})
    if source:
        # Put legality rules and undefined behavior findings in constants section
        # (as a reasonable home for general value rules)
        if "constants" in ch7.get("sections", {}):
            ch7["sections"]["constants"] = merge_section_content(
                ch7["sections"]["constants"], source
            )
        save_json(FLS_MAPPING_DIR / "fls_chapter07_values.json", ch7)
        print("  Done - merged into constants section")
    else:
        print("  Skipped - source not found")


def redistribute_ch8_statements():
    """Distribute Chapter 8 statement content to new sections."""
    print("Redistributing Ch8 statement content...")
    
    backup8 = load_json(BACKUP_DIR / "fls_chapter08_statements.json")
    ch8 = load_json(FLS_MAPPING_DIR / "fls_chapter08_statements.json")
    
    sections = ch8.get("sections", {})
    backup_sections = backup8.get("sections", {})
    
    # item_statements -> item_statement section
    if "item_statements" in backup_sections and "item_statement" in sections:
        sections["item_statement"] = merge_section_content(
            sections["item_statement"], backup_sections["item_statements"]
        )
        print("  Merged item_statements -> item_statement")
    
    # macro_statements -> macro_statement section
    if "macro_statements" in backup_sections and "macro_statement" in sections:
        sections["macro_statement"] = merge_section_content(
            sections["macro_statement"], backup_sections["macro_statements"]
        )
        print("  Merged macro_statements -> macro_statement")
    
    # empty_statements -> empty_statement section
    if "empty_statements" in backup_sections and "empty_statement" in sections:
        sections["empty_statement"] = merge_section_content(
            sections["empty_statement"], backup_sections["empty_statements"]
        )
        print("  Merged empty_statements -> empty_statement")
    
    # statements_overview -> distribute to let_statements
    if "statements_overview" in backup_sections and "let_statements" in sections:
        sections["let_statements"] = merge_section_content(
            sections["let_statements"], backup_sections["statements_overview"]
        )
        print("  Merged statements_overview -> let_statements")
    
    save_json(FLS_MAPPING_DIR / "fls_chapter08_statements.json", ch8)
    print("  Done")


def redistribute_ch19_unsafe_operations():
    """Split Chapter 19 unsafe_operations content across 10 new sections."""
    print("Redistributing Ch19 unsafe_operations -> 10 sections...")
    
    backup19 = load_json(BACKUP_DIR / "fls_chapter19_unsafety.json")
    ch19 = load_json(FLS_MAPPING_DIR / "fls_chapter19_unsafety.json")
    
    source = backup19.get("sections", {}).get("unsafe_operations", {})
    if not source:
        print("  Skipped - source not found")
        return
    
    findings = source.get("findings", {})
    samples = source.get("samples", [])
    sections = ch19.get("sections", {})
    
    # Map findings to appropriate sections
    finding_mapping = {
        "union_types": "union_field_access",
        "static_mut_usage": "mutable_static_access", 
        "unsafe_fn_purposes": "unsafe_function_call",
        "unsafe_impl_categories": "unsafety_definition",
        "unsafe_operation_patterns": "unsafe_operations_list",
        "unsafe_trait": "unsafety_definition",
        "safety_documentation": "unsafe_context",
        "testing_unsafe": "unsafe_context",
    }
    
    for finding_key, section_key in finding_mapping.items():
        if finding_key in findings and section_key in sections:
            if not sections[section_key].get("findings"):
                sections[section_key]["findings"] = {}
            sections[section_key]["findings"][finding_key] = findings[finding_key]
            sections[section_key]["status"] = "demonstrated"
    
    # Distribute samples based on content
    for sample in samples:
        file_path = sample.get("file", "")
        code = sample.get("code", "")
        
        target_section = None
        if "union" in code.lower() or "union" in file_path.lower():
            target_section = "union_field_access"
        elif "static mut" in code.lower():
            target_section = "mutable_static_access"
        elif "unsafe fn" in code.lower() or "unsafe_fn" in file_path:
            target_section = "unsafe_function_call"
        elif "*const" in code or "*mut" in code or "ptr" in file_path.lower():
            target_section = "raw_pointer_dereference"
        else:
            target_section = "unsafe_operations_list"  # Default
        
        if target_section in sections:
            if not sections[target_section].get("samples"):
                sections[target_section]["samples"] = []
            sections[target_section]["samples"].append(sample)
            sections[target_section]["status"] = "demonstrated"
    
    # Mark all sections with content as demonstrated
    for section_key in sections:
        if sections[section_key].get("findings") or sections[section_key].get("samples"):
            sections[section_key]["status"] = "demonstrated"
    
    save_json(FLS_MAPPING_DIR / "fls_chapter19_unsafety.json", ch19)
    print("  Done")


def main():
    print("=" * 60)
    print("REDISTRIBUTING UNMIGRATED CONTENT")
    print("=" * 60)
    print()
    
    redistribute_ch3_visibility_to_ch14()
    redistribute_ch4_marker_traits()
    redistribute_ch4_drop_trait_to_ch15()
    redistribute_ch7_values_overview()
    redistribute_ch8_statements()
    redistribute_ch19_unsafe_operations()
    
    print()
    print("Redistribution complete!")


if __name__ == "__main__":
    main()
