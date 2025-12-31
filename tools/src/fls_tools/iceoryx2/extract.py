#!/usr/bin/env python3
"""
Extract FLS section information from RST source files.

This script parses the Ferrocene Language Specification RST files and extracts
all sections, subsections, and their FLS IDs, generating an updated
fls_section_mapping.json with complete hierarchy information.

Supports three extraction modes:
- headings: Extract sections from RST heading underlines (default)
- syntax: Extract sections from syntax block productions
- paragraphs: Extract individual paragraph IDs as sections
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Set


# RST heading underline characters in order of precedence (level 1 to 4)
# For FLS: = is chapter, - is section, ~ is subsection, ^ is sub-subsection
HEADING_CHARS = {
    '=': 1,  # Chapter title
    '-': 2,  # Section
    '~': 3,  # Subsection
    '^': 4,  # Sub-subsection
}

# Map RST filenames to chapter numbers
FILE_TO_CHAPTER = {
    'general.rst': 1,
    'lexical-elements.rst': 2,
    'items.rst': 3,
    'types-and-traits.rst': 4,
    'patterns.rst': 5,
    'expressions.rst': 6,
    'values.rst': 7,
    'statements.rst': 8,
    'functions.rst': 9,
    'associated-items.rst': 10,
    'implementations.rst': 11,
    'generics.rst': 12,
    'attributes.rst': 13,
    'entities-and-resolution.rst': 14,
    'ownership-and-deconstruction.rst': 15,
    'exceptions-and-errors.rst': 16,
    'concurrency.rst': 17,
    'program-structure-and-compilation.rst': 18,
    'unsafety.rst': 19,
    'macros.rst': 20,
    'ffi.rst': 21,
    'inline-assembly.rst': 22,
}

# Chapter-specific extraction configuration
# Modes: 'headings' (default), 'syntax', 'paragraphs'
# For 'syntax' mode, specify which productions to extract and what to include/exclude
# 
# Production config options:
#   - 'production': Name of the production to look up
#   - 'include': List of alternatives to include (if omitted, extracts the production itself as a section)
#   - 'exclude': List of alternatives to exclude
#   - 'extract_top_level': If True, extract all top-level productions in the syntax block
#     using 'include' as the list of productions to include
CHAPTER_CONFIG: Dict[str, Dict[str, Any]] = {
    # Chapters needing syntax extraction (no heading-based sections)
    'items.rst': {
        'mode': 'syntax',
        'extract_productions': [
            {
                'production': 'ItemWithVisibility',
                'include': [
                    'ConstantDeclaration',
                    'EnumDeclaration',
                    'ExternalBlock',
                    'ExternalCrateImport',
                    'FunctionDeclaration',
                    'Implementation',
                    'ModuleDeclaration',
                    'StaticDeclaration',
                    'StructDeclaration',
                    'TraitDeclaration',
                    'TypeAliasDeclaration',
                    'UnionDeclaration',
                    'UseImport',
                ],
                'exclude': [
                    'VisibilityModifier',  # Not a declaration type, just a modifier
                ],
            },
            {
                'production': 'MacroItem',
                'include': [
                    'MacroRulesDeclaration',
                    'TerminatedMacroInvocation',
                ],
            },
        ]
    },
    'functions.rst': {
        'mode': 'syntax',
        # For functions.rst, all productions are top-level definitions (not alternatives)
        # So we list the top-level productions we want as sections
        'extract_top_level_productions': [
            'FunctionDeclaration',
            'FunctionQualifierList',
            'FunctionParameterList',
            'FunctionParameter',
            'FunctionParameterPattern',
            'FunctionParameterVariadicPart',
            'ReturnType',
            'FunctionBody',
            'SelfParameter',
            'ShorthandSelf',
            'TypedSelf',
        ],
    },
    'associated-items.rst': {
        'mode': 'syntax',
        'extract_productions': [
            {
                'production': 'AssociatedItemWithVisibility',
                'include': [
                    'ConstantDeclaration',
                    'FunctionDeclaration',
                    'TypeAliasDeclaration',
                ],
                'exclude': [
                    'VisibilityModifier',  # Not a declaration type, just a modifier
                ],
            },
        ]
    },
    
    # Chapter needing paragraph extraction (no headings, no useful syntax)
    'unsafety.rst': {
        'mode': 'paragraphs'
    },
    
    # All other chapters default to 'headings' mode
}

# Sentinel value for syntax-extracted sections without native FLS IDs
FLS_EXTRACTED_FROM_SYNTAX = "fls_extracted_from_syntax_block"


class ExtractionWarnings:
    """Collects warnings during extraction for reporting."""
    
    def __init__(self):
        self.warnings: List[str] = []
    
    def add(self, message: str):
        self.warnings.append(message)
        print(f"  WARNING: {message}", file=sys.stderr)
    
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def title_to_key(title: str) -> str:
    """Convert a section title to a snake_case key."""
    key = re.sub(r'[^\w\s]', '', title.lower())
    key = re.sub(r'\s+', '_', key.strip())
    return key


def pascal_to_title(pascal: str) -> str:
    """Convert PascalCase to Title Case (e.g., ConstantDeclaration -> Constant Declaration)."""
    # Insert space before uppercase letters (except at start)
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', pascal)
    return spaced


def pascal_to_key(pascal: str) -> str:
    """Convert PascalCase to snake_case key."""
    return title_to_key(pascal_to_title(pascal))


def extract_chapter_info(lines: List[str], filepath: Path) -> tuple:
    """Extract chapter title and FLS ID from the beginning of an RST file."""
    chapter_title = None
    chapter_fls_id = None
    current_fls_id = None
    
    for i, line in enumerate(lines):
        # Check for FLS ID anchor
        fls_match = re.match(r'\.\. _fls_([a-z0-9]+):', line)
        if fls_match:
            current_fls_id = f"fls_{fls_match.group(1)}"
            continue
        
        # Check for chapter title (level 1 heading with =)
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line and next_line.startswith('=') and all(c == '=' for c in next_line.rstrip()):
                if len(next_line.rstrip()) >= len(line.rstrip()):
                    chapter_title = line.strip()
                    chapter_fls_id = current_fls_id
                    break
    
    return chapter_title, chapter_fls_id


def extract_from_headings(lines: List[str], filepath: Path, chapter_num: int,
                          warnings: ExtractionWarnings) -> Dict[str, Any]:
    """Extract sections from RST heading underlines."""
    sections = {}
    current_fls_id = None
    
    # Track section numbering at each level
    section_counters = [0, 0, 0, 0]  # For levels 1-4
    current_level = 0
    
    # Stack to track parent sections for nesting
    section_stack = [sections]
    level_stack = [0]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for FLS ID anchor
        fls_match = re.match(r'\.\. _fls_([a-z0-9]+):', line)
        if fls_match:
            current_fls_id = f"fls_{fls_match.group(1)}"
            i += 1
            continue
        
        # Check for heading (title followed by underline)
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line and len(next_line) >= len(line.rstrip()) and next_line[0] in HEADING_CHARS:
                underline_char = next_line[0]
                if all(c == underline_char for c in next_line.rstrip()):
                    level = HEADING_CHARS.get(underline_char, 0)
                    title = line.strip()
                    
                    # Skip chapter title (level 1)
                    if level == 1:
                        current_fls_id = None
                        i += 2
                        continue
                    
                    if level > 1:
                        # Update counters
                        section_counters[level - 2] += 1
                        # Reset lower level counters
                        for j in range(level - 1, len(section_counters)):
                            if j > level - 2:
                                section_counters[j] = 0
                        
                        # Build section number
                        if level == 2:
                            section_num = f"{chapter_num}.{section_counters[0]}"
                        elif level == 3:
                            section_num = f"{chapter_num}.{section_counters[0]}.{section_counters[1]}"
                        elif level == 4:
                            section_num = f"{chapter_num}.{section_counters[0]}.{section_counters[1]}.{section_counters[2]}"
                        else:
                            section_num = str(chapter_num)
                        
                        key = title_to_key(title)
                        section_data = {
                            'fls_section': section_num,
                            'title': title,
                            'fls_id': current_fls_id,
                        }
                        
                        # Determine where to place this section
                        if level == 2:
                            sections[key] = section_data
                            section_stack = [sections, section_data]
                            level_stack = [0, 2]
                        else:
                            # Pop stack until we find appropriate parent
                            while len(level_stack) > 1 and level_stack[-1] >= level:
                                section_stack.pop()
                                level_stack.pop()
                            
                            parent = section_stack[-1]
                            if 'subsections' not in parent:
                                parent['subsections'] = {}
                            parent['subsections'][key] = section_data
                            
                            section_stack.append(section_data)
                            level_stack.append(level)
                        
                        current_level = level
                        current_fls_id = None
                    
                    i += 2
                    continue
        
        i += 1
    
    return sections


def parse_syntax_block(lines: List[str], start_idx: int) -> tuple:
    """
    Parse a syntax block starting at the given index.
    Returns (productions_dict, end_index) where productions_dict maps
    production names to their alternatives.
    """
    productions = {}
    current_production = None
    current_alternatives = []
    
    i = start_idx
    # Skip the ".. syntax::" line and any blank lines
    while i < len(lines) and (lines[i].strip() == '' or lines[i].strip() == '.. syntax::'):
        i += 1
    
    while i < len(lines):
        line = lines[i]
        
        # Check if we've exited the syntax block (non-indented non-empty line)
        if line and not line.startswith(' ') and not line.startswith('\t'):
            break
        
        stripped = line.strip()
        
        # Check for production definition (Name ::=)
        prod_match = re.match(r'^([A-Z][a-zA-Z0-9]*)\s*::=\s*(.*)', stripped)
        if prod_match:
            # Save previous production
            if current_production:
                productions[current_production] = current_alternatives
            
            current_production = prod_match.group(1)
            current_alternatives = []
            
            # Check if there's content on the same line
            rest = prod_match.group(2).strip()
            if rest:
                # Parse alternatives from the rest of the line
                alts = extract_alternatives_from_text(rest)
                current_alternatives.extend(alts)
        elif stripped and current_production:
            # Continuation of current production
            alts = extract_alternatives_from_text(stripped)
            current_alternatives.extend(alts)
        
        i += 1
    
    # Save last production
    if current_production:
        productions[current_production] = current_alternatives
    
    return productions, i


def extract_alternatives_from_text(text: str) -> List[str]:
    """
    Extract PascalCase alternatives from syntax text.
    Handles patterns like 'Foo | Bar | Baz' or 'Foo? (Bar | Baz)'
    """
    alternatives = []
    
    # Find all PascalCase identifiers (syntax references)
    # These start with uppercase and contain letters/digits
    matches = re.findall(r'\b([A-Z][a-zA-Z0-9]*)\b', text)
    
    for match in matches:
        # Skip keywords and common syntax elements
        if match not in alternatives:
            alternatives.append(match)
    
    return alternatives


def extract_from_syntax(lines: List[str], filepath: Path, chapter_num: int,
                        config: Dict[str, Any], warnings: ExtractionWarnings,
                        base_section: str = "0") -> Dict[str, Any]:
    """
    Extract sections from syntax block productions.
    
    Args:
        lines: File lines
        filepath: Path to RST file
        chapter_num: Chapter number
        config: Configuration dict with 'extract_productions' or 'extract_top_level_productions' key
        warnings: Warnings collector
        base_section: Base section number (e.g., "0" for chapter-level, "1" for section 1)
    """
    sections = {}
    
    # Find and parse all syntax blocks
    all_productions = {}
    i = 0
    while i < len(lines):
        if '.. syntax::' in lines[i]:
            prods, end_idx = parse_syntax_block(lines, i)
            all_productions.update(prods)
            i = end_idx
        else:
            i += 1
    
    section_counter = 0
    
    # Check for extract_top_level_productions mode
    # This extracts top-level production names directly (not their alternatives)
    top_level_productions = config.get('extract_top_level_productions')
    if top_level_productions is not None:
        # Validate configured productions exist
        for prod_name in top_level_productions:
            if prod_name not in all_productions:
                warnings.add(f"Production '{prod_name}' configured in extract_top_level_productions "
                            f"but not found in {filepath.name}. Has it been removed from the FLS?")
                continue
            
            section_counter += 1
            section_num = f"{chapter_num}.{base_section}.{section_counter}"
            key = pascal_to_key(prod_name)
            
            sections[key] = {
                'fls_section': section_num,
                'title': pascal_to_title(prod_name),
                'fls_id': FLS_EXTRACTED_FROM_SYNTAX,
            }
        
        # Check for new productions not in our list
        for prod_name in all_productions.keys():
            if prod_name not in top_level_productions:
                warnings.add(f"Production '{prod_name}' found in {filepath.name} but not in "
                            f"extract_top_level_productions. Has it been added to the FLS? "
                            f"Consider updating CHAPTER_CONFIG.")
        
        return sections
    
    # Standard mode: extract alternatives from specific productions
    extract_productions = config.get('extract_productions', [])
    
    for prod_config in extract_productions:
        if isinstance(prod_config, str):
            # Simple string means extract the production itself
            prod_name = prod_config
            include_list = None
            exclude_list = []
        else:
            prod_name = prod_config['production']
            include_list = prod_config.get('include')
            exclude_list = prod_config.get('exclude', [])
        
        if prod_name not in all_productions:
            warnings.add(f"Production '{prod_name}' not found in {filepath.name}. "
                        f"Has it been removed from the FLS?")
            continue
        
        production_alternatives = all_productions[prod_name]
        
        if include_list is not None:
            # Check for items in include list that don't exist
            for item in include_list:
                if item not in production_alternatives:
                    warnings.add(f"'{item}' is configured in include list for '{prod_name}' "
                                f"but was not found in the syntax block. Has it been removed from the FLS?")
            
            # Check for new items not in include or exclude lists
            for alt in production_alternatives:
                if alt not in include_list and alt not in exclude_list:
                    # Only warn about PascalCase items (actual productions, not keywords)
                    if re.match(r'^[A-Z][a-zA-Z0-9]*$', alt) and alt != prod_name:
                        warnings.add(f"'{alt}' found in '{prod_name}' but not in include or exclude list. "
                                    f"Has it been added to the FLS? Consider updating CHAPTER_CONFIG.")
            
            # Use include list as the items to extract
            items_to_extract = [item for item in include_list if item in production_alternatives]
        else:
            # No include list - extract all alternatives
            items_to_extract = [alt for alt in production_alternatives 
                               if alt not in exclude_list and alt != prod_name]
        
        # Create sections for each item
        for item in items_to_extract:
            section_counter += 1
            section_num = f"{chapter_num}.{base_section}.{section_counter}"
            key = pascal_to_key(item)
            
            sections[key] = {
                'fls_section': section_num,
                'title': pascal_to_title(item),
                'fls_id': FLS_EXTRACTED_FROM_SYNTAX,
            }
    
    return sections


def extract_from_paragraphs(lines: List[str], filepath: Path, chapter_num: int,
                            warnings: ExtractionWarnings) -> Dict[str, Any]:
    """Extract individual paragraph IDs as sections."""
    sections = {}
    section_counter = 0
    
    for line in lines:
        # Match paragraph markers :dp:`fls_XXX`
        match = re.search(r':dp:`(fls_[a-z0-9]+)`', line)
        if match:
            fls_id = match.group(1)
            section_counter += 1
            section_num = f"{chapter_num}.{section_counter}"
            
            sections[fls_id] = {
                'fls_section': section_num,
                'title': fls_id,
                'fls_id': fls_id,
            }
    
    return sections


def parse_rst_file(filepath: Path, warnings: ExtractionWarnings) -> dict:
    """Parse an RST file and extract section hierarchy with FLS IDs."""
    content = filepath.read_text()
    lines = content.split('\n')
    
    chapter_num = FILE_TO_CHAPTER.get(filepath.name, 0)
    chapter_title, chapter_fls_id = extract_chapter_info(lines, filepath)
    
    # Determine extraction mode
    config = CHAPTER_CONFIG.get(filepath.name, {})
    mode = config.get('mode', 'headings')
    
    if mode == 'syntax':
        sections = extract_from_syntax(lines, filepath, chapter_num, config, warnings)
    elif mode == 'paragraphs':
        sections = extract_from_paragraphs(lines, filepath, chapter_num, warnings)
    else:  # headings mode (default)
        sections = extract_from_headings(lines, filepath, chapter_num, warnings)
        
        # Check if we got no sections and should warn
        if not sections and filepath.name not in CHAPTER_CONFIG:
            # Check if there are syntax blocks we could use
            has_syntax = '.. syntax::' in content
            has_paragraphs = ':dp:`fls_' in content
            
            if has_syntax or has_paragraphs:
                suggestions = []
                if has_syntax:
                    suggestions.append("mode='syntax'")
                if has_paragraphs:
                    suggestions.append("mode='paragraphs'")
                
                warnings.add(f"{filepath.name} has 0 heading sections and no configured extraction mode. "
                            f"Consider adding to CHAPTER_CONFIG with {' or '.join(suggestions)}.")
    
    # Handle overrides for mixed mode
    overrides = config.get('overrides', {})
    for section_num, override_config in overrides.items():
        override_mode = override_config.get('mode')
        if override_mode == 'syntax':
            # Find the section and add subsections from syntax
            subsections = extract_from_syntax(lines, filepath, chapter_num, 
                                             override_config, warnings, 
                                             base_section=section_num.split('.')[-1])
            # Find the parent section and merge
            for key, section in sections.items():
                if section.get('fls_section') == section_num:
                    if 'subsections' not in section:
                        section['subsections'] = {}
                    section['subsections'].update(subsections)
                    break
    
    return {
        'title': chapter_title,
        'fls_id': chapter_fls_id,
        'file': filepath.stem,
        'sections': sections
    }


def count_sections(sections: Dict[str, Any], depth: int = 0) -> tuple:
    """Recursively count sections and subsections."""
    section_count = len(sections)
    subsection_count = 0
    
    for section in sections.values():
        if isinstance(section, dict) and 'subsections' in section:
            sub_sections, sub_subsections = count_sections(section['subsections'], depth + 1)
            subsection_count += sub_sections + sub_subsections
    
    return section_count, subsection_count


def main():
    fls_src_dir = Path('cache/repos/fls/src')
    output_file = Path('tools/fls_section_mapping.json')
    
    if not fls_src_dir.exists():
        print(f"Error: FLS source directory not found: {fls_src_dir}")
        return 1
    
    mapping = {}
    all_warnings = ExtractionWarnings()
    
    for filename, chapter_num in sorted(FILE_TO_CHAPTER.items(), key=lambda x: x[1]):
        filepath = fls_src_dir / filename
        if not filepath.exists():
            print(f"Warning: File not found: {filepath}")
            continue
        
        config = CHAPTER_CONFIG.get(filename, {})
        mode = config.get('mode', 'headings')
        print(f"Processing {filename} (Chapter {chapter_num}, mode={mode})...")
        
        chapter_warnings = ExtractionWarnings()
        chapter_data = parse_rst_file(filepath, chapter_warnings)
        chapter_data['chapter'] = chapter_num
        mapping[str(chapter_num)] = chapter_data
        
        # Collect warnings
        all_warnings.warnings.extend(chapter_warnings.warnings)
    
    # Write output
    with open(output_file, 'w') as f:
        json.dump(mapping, f, indent=2)
    
    print(f"\nWrote mapping to {output_file}")
    
    # Print summary
    total_sections = 0
    total_subsections = 0
    for chapter_num, chapter_data in sorted(mapping.items(), key=lambda x: int(x[0])):
        sections = chapter_data.get('sections', {})
        num_sections, num_subsections = count_sections(sections)
        total_sections += num_sections
        total_subsections += num_subsections
        print(f"  Chapter {chapter_num}: {num_sections} sections, {num_subsections} subsections")
    
    print(f"\nTotal: {total_sections} sections, {total_subsections} subsections")
    
    if all_warnings.has_warnings():
        print(f"\n{len(all_warnings.warnings)} warning(s) generated. Review above for details.")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
