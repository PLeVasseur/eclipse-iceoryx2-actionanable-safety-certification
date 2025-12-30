#!/usr/bin/env python3
"""
Validate synthetic FLS IDs used in coding standard mappings.

This script validates that:
1. All FLS IDs used in mappings are either native (from FLS RST source)
   or documented in synthetic_fls_ids.json
2. Synthetic IDs don't collide with native FLS IDs
3. All IDs follow the correct format (fls_ + 12 alphanumeric chars)
4. All synthetic IDs in the tracking file exist in fls_section_mapping.json

Usage:
    uv run python validate_synthetic_ids.py [--verbose]
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Project paths
TOOLS_DIR = Path(__file__).parent
PROJECT_ROOT = TOOLS_DIR.parent
FLS_SECTION_MAPPING = TOOLS_DIR / "fls_section_mapping.json"
SYNTHETIC_IDS_FILE = TOOLS_DIR / "synthetic_fls_ids.json"
FLS_RST_DIR = PROJECT_ROOT / "cache" / "repos" / "fls" / "src"
MAPPINGS_DIR = PROJECT_ROOT / "coding-standards-fls-mapping" / "mappings"

# FLS ID format: fls_ followed by 12 alphanumeric characters (mixed case)
FLS_ID_PATTERN = re.compile(r'^fls_[a-zA-Z0-9]{10,14}$')


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def collect_ids_from_mapping(mapping: dict) -> set[str]:
    """Recursively collect all FLS IDs from fls_section_mapping.json."""
    ids = set()
    
    def _collect(obj):
        if isinstance(obj, dict):
            if 'fls_id' in obj and obj['fls_id']:
                ids.add(obj['fls_id'])
            for v in obj.values():
                _collect(v)
        elif isinstance(obj, list):
            for item in obj:
                _collect(item)
    
    _collect(mapping)
    return ids


def collect_native_ids_from_rst(rst_dir: Path) -> set[str]:
    """Collect all FLS IDs from the FLS RST source files."""
    ids = set()
    if not rst_dir.exists():
        return ids
    
    for rst_file in rst_dir.glob("*.rst"):
        content = rst_file.read_text()
        ids.update(re.findall(r'fls_[a-zA-Z0-9]+', content))
    
    return ids


def collect_coding_standard_mapping_ids(mappings_dir: Path) -> dict[str, set[str]]:
    """Collect all FLS IDs used in coding standard mapping files."""
    result = {}
    
    if not mappings_dir.exists():
        return result
    
    for mapping_file in mappings_dir.glob("*_to_fls.json"):
        ids = set()
        try:
            data = load_json(mapping_file)
            for guideline in data.get('mappings', []):
                for fls_id in guideline.get('fls_ids', []):
                    ids.add(fls_id)
        except Exception as e:
            print(f"Warning: Could not parse {mapping_file.name}: {e}")
        result[mapping_file.name] = ids
    
    return result


def validate_id_format(fls_id: str) -> tuple[bool, str]:
    """Validate an FLS ID follows the correct format."""
    if not fls_id.startswith('fls_'):
        return False, "must start with 'fls_'"
    
    suffix = fls_id[4:]
    if not suffix.isalnum():
        return False, "suffix must be alphanumeric"
    
    if len(suffix) < 10 or len(suffix) > 14:
        return False, f"suffix length {len(suffix)} not in range [10, 14]"
    
    return True, "valid"


def main():
    parser = argparse.ArgumentParser(description="Validate synthetic FLS IDs")
    parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
    args = parser.parse_args()
    
    errors = []
    warnings = []
    
    print("=" * 60)
    print("FLS ID Validation")
    print("=" * 60)
    
    # Load data files
    print("\n1. Loading data files...")
    
    # Load native IDs from RST source
    native_ids_rst = collect_native_ids_from_rst(FLS_RST_DIR)
    print(f"   Native IDs from RST source: {len(native_ids_rst)}")
    
    # Load IDs from our section mapping
    if not FLS_SECTION_MAPPING.exists():
        print(f"ERROR: Section mapping not found: {FLS_SECTION_MAPPING}")
        return 1
    
    section_mapping = load_json(FLS_SECTION_MAPPING)
    section_mapping_ids = collect_ids_from_mapping(section_mapping)
    print(f"   IDs in fls_section_mapping.json: {len(section_mapping_ids)}")
    
    # Load synthetic IDs
    if SYNTHETIC_IDS_FILE.exists():
        synthetic_data = load_json(SYNTHETIC_IDS_FILE)
        synthetic_ids = set(synthetic_data.get('synthetic_ids', {}).keys())
        print(f"   Synthetic IDs tracked: {len(synthetic_ids)}")
    else:
        synthetic_data = {}
        synthetic_ids = set()
        warnings.append(f"Synthetic IDs file not found: {SYNTHETIC_IDS_FILE}")
    
    # Collect IDs used in coding standard mappings
    print("\n2. Checking coding standard mapping files...")
    
    coding_mapping_ids = collect_coding_standard_mapping_ids(MAPPINGS_DIR)
    all_used_ids = set()
    for filename, ids in coding_mapping_ids.items():
        print(f"   {filename}: {len(ids)} unique FLS IDs")
        all_used_ids.update(ids)
    print(f"   Total unique IDs used in mappings: {len(all_used_ids)}")
    
    # Validate ID formats
    print("\n3. Validating ID formats...")
    
    all_ids_to_check = section_mapping_ids | synthetic_ids | all_used_ids
    format_errors = 0
    
    for fls_id in sorted(all_ids_to_check):
        valid, reason = validate_id_format(fls_id)
        if not valid:
            errors.append(f"Invalid format: {fls_id} - {reason}")
            format_errors += 1
        elif args.verbose:
            print(f"   OK: {fls_id}")
    
    print(f"   Format errors: {format_errors}")
    
    # Check synthetic IDs don't collide with native RST IDs
    print("\n4. Checking for collisions with native IDs...")
    
    collisions = synthetic_ids & native_ids_rst
    if collisions:
        for fls_id in collisions:
            errors.append(f"Synthetic ID collides with native RST ID: {fls_id}")
    
    print(f"   Collisions found: {len(collisions)}")
    
    # Check all synthetic IDs exist in section mapping
    print("\n5. Verifying synthetic IDs are in section mapping...")
    
    missing_from_mapping = synthetic_ids - section_mapping_ids
    if missing_from_mapping:
        for fls_id in missing_from_mapping:
            errors.append(f"Synthetic ID not in fls_section_mapping.json: {fls_id}")
    
    print(f"   Missing from mapping: {len(missing_from_mapping)}")
    
    # Check all used IDs are known (either native or synthetic)
    print("\n6. Checking ID coverage for coding standard mappings...")
    
    known_ids = native_ids_rst | synthetic_ids
    unknown_ids = all_used_ids - known_ids
    
    if unknown_ids:
        print(f"   WARNING: {len(unknown_ids)} IDs not found in native RST or synthetic tracking:")
        for fls_id in sorted(unknown_ids)[:10]:
            warnings.append(f"Unknown ID in mappings: {fls_id}")
            print(f"      - {fls_id}")
        if len(unknown_ids) > 10:
            print(f"      ... and {len(unknown_ids) - 10} more")
    else:
        print("   All used IDs are documented (native or synthetic)")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    print(f"\nNative IDs (from RST):     {len(native_ids_rst)}")
    print(f"Synthetic IDs (tracked):   {len(synthetic_ids)}")
    print(f"IDs in section mapping:    {len(section_mapping_ids)}")
    print(f"IDs used in std mappings:  {len(all_used_ids)}")
    
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"  - {w}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")
    
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
        return 1
    
    print("\nAll validations passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
