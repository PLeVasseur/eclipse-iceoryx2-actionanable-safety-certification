#!/usr/bin/env python3
"""
Extract full text from MISRA C:2025 PDF for embedding generation.

This script parses the MISRA C:2025 PDF and extracts the complete text
for each rule and directive, including:
- Title
- Category (Required/Advisory/Mandatory)
- Analysis type
- Applies to (C90/C99/C11)
- Amplification
- Rationale
- Examples (code samples)
- Exceptions
- See also references

Additionally, this script performs enhanced parsing to generate search queries
for multi-query semantic search:
- Parses rationale into individual concerns (bullet points, numbered lists)
- Extracts C identifiers from amplification
- Parses see_also into guideline references
- Matches keywords against concept_to_fls.json for concept mapping
- Generates search_queries list for embedding generation

The extracted text is saved to cache/ (gitignored) because MISRA content
is copyrighted and should not be committed to version control.

Usage:
    uv run python tools/embeddings/extract_misra_text.py

Output:
    cache/misra_c_extracted_text.json
"""

import json
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader


# Common C standard library identifiers to extract from amplification
C_STDLIB_IDENTIFIERS = {
    # Memory allocation
    "malloc", "free", "calloc", "realloc", "aligned_alloc",
    # String functions
    "strcpy", "strncpy", "strcat", "strncat", "strlen", "strcmp", "strncmp",
    "memcpy", "memmove", "memset", "memcmp",
    # I/O functions
    "printf", "scanf", "fprintf", "fscanf", "sprintf", "snprintf",
    "fopen", "fclose", "fread", "fwrite", "fgets", "fputs",
    "getchar", "putchar", "gets", "puts",
    # Other stdlib
    "atoi", "atof", "atol", "strtol", "strtoul", "strtod",
    "abs", "labs", "div", "ldiv",
    "rand", "srand",
    "exit", "abort", "atexit",
    "qsort", "bsearch",
    # setjmp/longjmp
    "setjmp", "longjmp",
    # signal
    "signal", "raise",
    # errno
    "errno",
    # assert
    "assert",
    # time
    "time", "clock", "difftime", "mktime",
    # Thread functions (C11)
    "thrd_create", "thrd_join", "thrd_exit", "mtx_lock", "mtx_unlock",
    "cnd_wait", "cnd_signal",
    # Atomic (C11)
    "atomic_load", "atomic_store", "atomic_exchange",
}


from fls_tools.shared import (
    get_project_root,
    get_concept_to_fls_path,
    get_misra_c_standards_path,
    get_misra_c_extracted_text_path,
    get_misra_pdf_path,
)


def load_concept_keywords(project_root: Path) -> dict[str, list[str]]:
    """
    Load concept keywords from concept_to_fls.json.
    
    Returns dict mapping concept_name -> list of keywords.
    """
    concept_path = get_concept_to_fls_path(project_root)
    if not concept_path.exists():
        print(f"Warning: concept_to_fls.json not found at {concept_path}")
        return {}
    
    with open(concept_path, encoding="utf-8") as f:
        data = json.load(f)
    
    return {
        name: concept.get("keywords", [])
        for name, concept in data.get("concepts", {}).items()
    }


def detect_rationale_structure(rationale: str) -> str:
    """
    Detect the structure type of a rationale.
    
    Returns one of:
    - "bullet_list": Contains bullet points (●, •, -)
    - "numbered_list": Contains numbered items (1., 2., etc.)
    - "prose": Plain prose paragraphs
    """
    if not rationale:
        return "prose"
    
    # Check for bullet points
    if re.search(r'[●•]\s+', rationale):
        return "bullet_list"
    
    # Check for dash-style bullets at start of lines
    if re.search(r'\n-\s+[A-Z]', rationale):
        return "bullet_list"
    
    # Check for numbered lists
    if re.search(r'\n\d+\.\s+[A-Z]', rationale):
        return "numbered_list"
    
    return "prose"


def parse_rationale_concerns(rationale: str) -> dict:
    """
    Parse rationale text into structured components.
    
    Returns dict with:
    - full_text: Original text
    - structure_type: "bullet_list", "numbered_list", or "prose"
    - intro: Text before the list (if any)
    - concerns: List of individual concerns/items
    """
    result = {
        "full_text": rationale,
        "structure_type": detect_rationale_structure(rationale),
        "intro": "",
        "concerns": []
    }
    
    if not rationale:
        return result
    
    if result["structure_type"] == "bullet_list":
        # Split on bullet points
        # First, find where bullets start
        bullet_match = re.search(r'[●•]\s+', rationale)
        if bullet_match:
            result["intro"] = rationale[:bullet_match.start()].strip()
            bullet_section = rationale[bullet_match.start():]
            
            # Split on bullet markers
            items = re.split(r'[●•]\s+', bullet_section)
            result["concerns"] = [item.strip() for item in items if item.strip()]
        else:
            # Try dash-style bullets
            lines = rationale.split('\n')
            intro_lines = []
            in_list = False
            for line in lines:
                if re.match(r'^-\s+[A-Z]', line):
                    in_list = True
                    result["concerns"].append(line[2:].strip())
                elif in_list and line.startswith('  '):
                    # Continuation of previous item
                    if result["concerns"]:
                        result["concerns"][-1] += ' ' + line.strip()
                elif not in_list:
                    intro_lines.append(line)
            result["intro"] = '\n'.join(intro_lines).strip()
    
    elif result["structure_type"] == "numbered_list":
        # Split on numbered items
        parts = re.split(r'\n(\d+)\.\s+', rationale)
        if len(parts) > 1:
            result["intro"] = parts[0].strip()
            # parts alternates: intro, "1", item1, "2", item2, ...
            for i in range(1, len(parts), 2):
                if i + 1 < len(parts):
                    result["concerns"].append(parts[i + 1].strip())
    
    else:
        # Prose - keep as single block
        result["intro"] = rationale
        # No individual concerns for prose
    
    return result


def extract_identifiers_from_amplification(amplification: str) -> list[str]:
    """
    Extract C standard library identifiers mentioned in amplification.
    
    Returns list of identifiers found.
    """
    if not amplification:
        return []
    
    found = []
    text_lower = amplification.lower()
    
    # Check for known C stdlib identifiers
    for identifier in C_STDLIB_IDENTIFIERS:
        # Look for the identifier as a word boundary match
        if re.search(rf'\b{re.escape(identifier)}\b', amplification, re.IGNORECASE):
            found.append(identifier)
    
    return sorted(set(found))


def parse_see_also_refs(see_also: str) -> list[str]:
    """
    Parse see_also text into list of guideline references.
    
    Returns list like ["Dir 4.12", "Rule 18.7", "Rule 22.1"]
    """
    if not see_also:
        return []
    
    refs = []
    
    # Match patterns like "Dir 4.12" or "Rule 18.7"
    for match in re.finditer(r'(Dir|Rule)\s+(\d+\.\d+)', see_also):
        refs.append(f"{match.group(1)} {match.group(2)}")
    
    return refs


def match_concepts(guideline: dict, concept_keywords: dict[str, list[str]]) -> list[str]:
    """
    Match guideline text against concept keywords.
    
    Returns list of matched concept names.
    """
    if not concept_keywords:
        return []
    
    # Combine relevant text fields for matching
    text = ' '.join([
        guideline.get("title", ""),
        guideline.get("rationale", ""),
        guideline.get("amplification", ""),
    ]).lower()
    
    matched = []
    for concept_name, keywords in concept_keywords.items():
        for keyword in keywords:
            # Check if keyword appears in text
            if keyword.lower() in text:
                matched.append(concept_name)
                break  # Only add concept once
    
    return matched


def generate_search_queries(guideline: dict, parsed_rationale: dict) -> list[dict]:
    """
    Generate search queries for multi-query embedding search.
    
    Each query combines context (from title/intro) with a specific concern
    to improve semantic matching.
    
    Returns list of query dicts with:
    - id: Unique query ID (e.g., "Rule 21.3.q0")
    - text: Query text for embedding
    - source: Where the query came from (e.g., "rationale.concern.0")
    """
    queries = []
    gid = guideline.get("guideline_id", "")
    title = guideline.get("title", "").split('\n')[0]  # First line only
    
    # Clean title - remove C standard references
    title_clean = re.sub(r'C\d+\s*\[.*?\]', '', title).strip()
    if len(title_clean) > 100:
        title_clean = title_clean[:100]
    
    concerns = parsed_rationale.get("concerns", [])
    intro = parsed_rationale.get("intro", "")
    
    if concerns:
        # Generate one query per concern
        # Prepend context from title/intro
        context = title_clean
        if intro and len(intro) < 200:
            context = f"{title_clean}. {intro[:150]}"
        
        for i, concern in enumerate(concerns):
            # Clean up concern text
            concern_clean = concern.replace('\n', ' ').strip()
            # Remove trailing punctuation artifacts
            concern_clean = re.sub(r'[;,]$', '', concern_clean).strip()
            
            if len(concern_clean) > 20:  # Skip very short items
                queries.append({
                    "id": f"{gid}.q{i}",
                    "text": f"{context}: {concern_clean}",
                    "source": f"rationale.concern.{i}"
                })
    else:
        # For prose rationales, create single query from title + rationale
        rationale = guideline.get("rationale", "")
        if rationale:
            # Use title + first ~300 chars of rationale
            query_text = f"{title_clean}. {rationale[:300]}"
            queries.append({
                "id": f"{gid}.q0",
                "text": query_text,
                "source": "rationale.full"
            })
    
    # If no queries generated from rationale, use title only
    if not queries and title_clean:
        queries.append({
            "id": f"{gid}.q0",
            "text": title_clean,
            "source": "title"
        })
    
    return queries


def load_expected_guidelines(project_root: Path) -> list[dict]:
    """Load the list of expected guideline IDs from the standards file."""
    standards_path = get_misra_c_standards_path(project_root)
    with open(standards_path, encoding="utf-8") as f:
        data = json.load(f)
    
    guidelines = []
    for category in data["categories"]:
        for g in category.get("guidelines", []):
            guidelines.append({
                "id": g["id"],
                "title": g.get("title", ""),
                "guideline_type": g.get("guideline_type", "rule"),
                "category_name": category.get("name", "")
            })
    return guidelines


def extract_pdf_text(pdf_path: Path, start_page: int = 0) -> str:
    """Extract text from PDF starting from a specific page."""
    reader = PdfReader(pdf_path)
    pages_text = []
    for i, page in enumerate(reader.pages):
        if i >= start_page:
            text = page.extract_text()
            if text:
                # Normalize non-breaking spaces
                text = text.replace('\xa0', ' ')
                pages_text.append(text)
    return '\n'.join(pages_text)


def build_guideline_pattern(guideline_id: str) -> str:
    """Build regex pattern for a guideline ID."""
    # Handle both "Rule X.Y" and "Dir X.Y"
    parts = guideline_id.split()
    if len(parts) != 2:
        return re.escape(guideline_id)
    
    prefix, number = parts
    # Allow flexible whitespace between prefix and number
    return rf'{re.escape(prefix)}\s+{re.escape(number)}'


def find_all_guideline_positions(full_text: str, guidelines: list[dict]) -> list[tuple[str, int, str, str]]:
    """
    Find all positions where guideline definitions start.
    Returns list of (guideline_id, position, title_text, category).
    
    A definition is identified by the pattern:
    Rule/Dir X.Y <title text>
    [optional reference annotations]
    Category Required/Advisory/Mandatory
    """
    positions = []
    
    # Build combined pattern for all guidelines
    # Look for: Rule/Dir X.Y followed by text, eventually followed by Category
    for g in guidelines:
        gid = g["id"]
        pattern = build_guideline_pattern(gid)
        
        # Pattern: guideline ID at start of line, followed by title text
        # The title may span multiple lines before "Category"
        # Category can be: Required, Advisory, Mandatory, or Disapplied
        # We require "Analysis" or "Applies to" after Category to distinguish from cross-references
        # Title must NOT start with:
        # - Section number (like "4.2" or "5.3")
        # - "Section" (page headers like "Section 5: Rules")
        # - "Rule" or "Dir" (another guideline)
        full_pattern = rf'(?:^|\n)({pattern})\s+(?!(?:\d+\.\d+|Section|Rule|Dir)\s)([^\n]+(?:\n(?!Category)[^\n]+)*)\n(?:\[[^\]]+\]\n)*Category\s+(Required|Advisory|Mandatory|Disapplied)\n(?:Analysis|Applies to)'
        
        for match in re.finditer(full_pattern, full_text, re.MULTILINE):
            gid_found = match.group(1).replace('  ', ' ').strip()
            # Normalize the found ID
            gid_normalized = re.sub(r'\s+', ' ', gid_found)
            title = match.group(2).strip()
            category = match.group(3)
            
            positions.append((gid_normalized, match.start(), title, category))
    
    # Sort by position
    positions.sort(key=lambda x: x[1])
    
    return positions


def extract_guideline_content(full_text: str, start_pos: int, end_pos: int) -> str:
    """Extract the content of a guideline between start and end positions."""
    content = full_text[start_pos:end_pos].strip()
    
    # Clean up page headers/footers
    content = re.sub(r'Section \d+: (?:Rules|Directives)\n\d+\n', '', content)
    content = re.sub(r'Licensed to:.*?\d{4}\n', '', content)
    content = re.sub(r'\n\d+\n', '\n', content)  # Page numbers
    
    return content.strip()


def parse_guideline_fields(
    guideline_id: str, 
    content: str, 
    title: str, 
    category: str,
    concept_keywords: dict[str, list[str]] | None = None
) -> dict:
    """
    Parse the extracted content into structured fields with enhanced parsing.
    
    Args:
        guideline_id: The guideline ID (e.g., "Rule 21.3")
        content: Raw extracted content from PDF
        title: Extracted title
        category: Category (Required/Advisory/Mandatory)
        concept_keywords: Dict of concept_name -> keywords for matching
    
    Returns:
        Dict with all fields including enhanced parsed structures
    """
    # Use explicit typing to allow mixed value types
    result: dict = {
        "guideline_id": guideline_id,
        "title": title,
        "category": category,
        "analysis": "",
        "applies_to": "",
        "amplification": "",
        "rationale": "",
        "exceptions": "",
        "examples": "",
        "see_also": "",
        "full_text": content
    }
    
    if not content:
        return result
    
    # Extract Analysis type
    analysis_match = re.search(r'Analysis\s+([^\n]+)', content)
    if analysis_match:
        result["analysis"] = analysis_match.group(1).strip()
    
    # Extract Applies to
    applies_match = re.search(r'Applies to\s+([^\n]+)', content)
    if applies_match:
        result["applies_to"] = applies_match.group(1).strip()
    
    # Define section headers
    section_headers = [
        ("Amplification", "amplification"),
        ("Rationale", "rationale"), 
        ("Exception", "exceptions"),
        ("Example", "examples"),
        ("See also", "see_also")
    ]
    
    for header, field in section_headers:
        # Find where this section starts (header followed by newline)
        header_pattern = rf'\n{header}s?\s*\n'
        header_match = re.search(header_pattern, content, re.IGNORECASE)
        
        if header_match:
            start = header_match.end()
            
            # Find where next section starts
            end = len(content)
            for next_header, _ in section_headers:
                if next_header == header:
                    continue
                next_pattern = rf'\n{next_header}s?\s*\n'
                next_match = re.search(next_pattern, content[start:], re.IGNORECASE)
                if next_match:
                    potential_end = start + next_match.start()
                    if potential_end < end:
                        end = potential_end
            
            result[field] = content[start:end].strip()
    
    # =========================================================================
    # Enhanced parsing for search queries
    # =========================================================================
    
    # Parse rationale into concerns
    parsed_rationale = parse_rationale_concerns(result["rationale"])
    result["rationale_parsed"] = parsed_rationale
    
    # Extract identifiers from amplification
    result["amplification_identifiers"] = extract_identifiers_from_amplification(
        result["amplification"]
    )
    
    # Parse see_also references
    result["see_also_refs"] = parse_see_also_refs(result["see_also"])
    
    # Match concepts
    if concept_keywords:
        result["matched_concepts"] = match_concepts(result, concept_keywords)
    else:
        result["matched_concepts"] = []
    
    # Generate search queries
    result["search_queries"] = generate_search_queries(result, parsed_rationale)
    
    return result


def main():
    """Main extraction function."""
    project_root = get_project_root()
    pdf_path = get_misra_pdf_path(project_root)
    output_path = get_misra_c_extracted_text_path(project_root)
    
    if not pdf_path.exists():
        print(f"Error: MISRA PDF not found at {pdf_path}")
        return 1
    
    # Load concept keywords for matching
    print("Loading concept keywords...")
    concept_keywords = load_concept_keywords(project_root)
    print(f"Loaded {len(concept_keywords)} concepts")
    
    # Load expected guidelines
    print("Loading expected guideline IDs...")
    expected_guidelines = load_expected_guidelines(project_root)
    print(f"Expected {len(expected_guidelines)} guidelines")
    
    # Extract PDF text starting from page 20 (before directives start)
    # Directives are in Section 4 (around page 22), Rules in Section 5 (around page 46)
    print(f"Reading PDF: {pdf_path}")
    full_text = extract_pdf_text(pdf_path, start_page=20)
    print(f"Extracted {len(full_text)} characters from rules/directives sections")
    
    # Find all guideline definition positions
    print("Finding guideline definitions...")
    positions = find_all_guideline_positions(full_text, expected_guidelines)
    print(f"Found {len(positions)} guideline definitions")
    
    # Create lookup from expected guidelines
    expected_lookup = {g["id"]: g for g in expected_guidelines}
    
    # Extract each guideline's content
    print("Extracting guideline content...")
    extracted_guidelines = []
    found_ids = set()
    
    for i, (gid, start_pos, title, category) in enumerate(positions):
        # Normalize guideline ID for lookup
        gid_normalized = gid.replace('  ', ' ').strip()
        
        # Skip duplicates (keep first occurrence which should be the definition)
        if gid_normalized in found_ids:
            continue
        found_ids.add(gid_normalized)
        
        # Find end position (start of next guideline or end of text)
        if i + 1 < len(positions):
            end_pos = positions[i + 1][1]
        else:
            end_pos = len(full_text)
        
        # Extract content
        content = extract_guideline_content(full_text, start_pos, end_pos)
        
        # Parse fields (with concept matching)
        parsed = parse_guideline_fields(
            gid_normalized, content, title, category, concept_keywords
        )
        
        # Add metadata from expected
        expected = expected_lookup.get(gid_normalized, {})
        parsed["guideline_type"] = expected.get("guideline_type", 
            "directive" if gid_normalized.startswith("Dir") else "rule")
        parsed["category_name"] = expected.get("category_name", "")
        
        extracted_guidelines.append(parsed)
    
    # Sort by guideline ID
    def sort_key(g):
        gid = g["guideline_id"]
        parts = gid.split()
        prefix = 0 if parts[0] == "Dir" else 1
        num_parts = parts[1].split(".")
        return (prefix, int(num_parts[0]), int(num_parts[1]))
    
    extracted_guidelines.sort(key=sort_key)
    
    # Find missing guidelines
    found_normalized = {g["guideline_id"] for g in extracted_guidelines}
    missing = []
    for expected in expected_guidelines:
        if expected["id"] not in found_normalized:
            missing.append(expected["id"])
    
    # Validate counts
    rules = [g for g in extracted_guidelines if g["guideline_type"] == "rule"]
    directives = [g for g in extracted_guidelines if g["guideline_type"] == "directive"]
    with_rationale = [g for g in extracted_guidelines if g["rationale"]]
    with_category = [g for g in extracted_guidelines if g["category"]]
    
    # Enhanced parsing statistics
    with_concerns = [g for g in extracted_guidelines 
                     if g.get("rationale_parsed", {}).get("concerns")]
    total_concerns = sum(
        len(g.get("rationale_parsed", {}).get("concerns", []))
        for g in extracted_guidelines
    )
    total_queries = sum(len(g.get("search_queries", [])) for g in extracted_guidelines)
    with_concepts = [g for g in extracted_guidelines if g.get("matched_concepts")]
    with_identifiers = [g for g in extracted_guidelines if g.get("amplification_identifiers")]
    
    print(f"\nExtraction Summary:")
    print(f"  Total extracted: {len(extracted_guidelines)}")
    print(f"  Rules: {len(rules)}")
    print(f"  Directives: {len(directives)}")
    print(f"  With rationale: {len(with_rationale)}")
    print(f"  With category: {len(with_category)}")
    print(f"  Missing: {len(missing)}")
    
    print(f"\nEnhanced Parsing Summary:")
    print(f"  Guidelines with parsed concerns: {len(with_concerns)}")
    print(f"  Total individual concerns: {total_concerns}")
    print(f"  Total search queries generated: {total_queries}")
    print(f"  Guidelines with matched concepts: {len(with_concepts)}")
    print(f"  Guidelines with C identifiers: {len(with_identifiers)}")
    
    if missing:
        print(f"\nMissing guidelines:")
        for m in missing[:20]:
            print(f"  - {m}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
    
    # If we don't have all 212, try to add the missing ones with empty content
    if len(extracted_guidelines) < 212:
        print(f"\nAdding {len(missing)} missing guidelines with empty content...")
        for m in missing:
            expected = expected_lookup.get(m, {})
            extracted_guidelines.append({
                "guideline_id": m,
                "title": expected.get("title", ""),
                "category": "",
                "analysis": "",
                "applies_to": "",
                "amplification": "",
                "rationale": "",
                "exceptions": "",
                "examples": "",
                "see_also": "",
                "full_text": "",
                "guideline_type": expected.get("guideline_type", "rule"),
                "category_name": expected.get("category_name", ""),
                # Enhanced fields (empty for missing guidelines)
                "rationale_parsed": {
                    "full_text": "",
                    "structure_type": "prose",
                    "intro": "",
                    "concerns": []
                },
                "amplification_identifiers": [],
                "see_also_refs": [],
                "matched_concepts": [],
                "search_queries": [],
                "_extraction_note": "Content not found in PDF - may need manual extraction"
            })
        
        # Re-sort
        extracted_guidelines.sort(key=sort_key)
    
    # Final counts
    rules = [g for g in extracted_guidelines if g["guideline_type"] == "rule"]
    directives = [g for g in extracted_guidelines if g["guideline_type"] == "directive"]
    
    # Create output structure
    output = {
        "source": "MISRA-C-2025.pdf",
        "extraction_date": str(date.today()),
        "statistics": {
            "total_guidelines": len(extracted_guidelines),
            "rules": len(rules),
            "directives": len(directives),
            "with_rationale": len([g for g in extracted_guidelines if g["rationale"]]),
            "with_category": len([g for g in extracted_guidelines if g["category"]]),
            "missing_content": len([g for g in extracted_guidelines if not g["full_text"]]),
            # Enhanced parsing statistics
            "with_parsed_concerns": len(with_concerns),
            "total_concerns": total_concerns,
            "total_search_queries": total_queries,
            "with_matched_concepts": len(with_concepts),
            "with_c_identifiers": len(with_identifiers),
        },
        "guidelines": extracted_guidelines,
        "_copyright_notice": "This file contains copyrighted MISRA content. DO NOT COMMIT TO VERSION CONTROL."
    }
    
    # Validate final counts
    if len(extracted_guidelines) != 212:
        print(f"\nERROR: Expected 212 guidelines, got {len(extracted_guidelines)}")
    
    if len(rules) != 190:
        print(f"\nWARNING: Expected 190 rules, got {len(rules)}")
        
    if len(directives) != 22:
        print(f"\nWARNING: Expected 22 directives, got {len(directives)}")
    
    # Ensure cache directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to: {output_path}")
    
    # Show samples
    print("\nSample extractions:")
    for sample_id in ["Dir 4.1", "Rule 11.1", "Rule 21.3"]:
        for g in extracted_guidelines:
            if g["guideline_id"] == sample_id:
                print(f"\n{sample_id}:")
                title_preview = g['title'][:60] + "..." if len(g['title']) > 60 else g['title']
                print(f"  Title: {title_preview}")
                print(f"  Category: {g['category']}")
                print(f"  Rationale: {len(g['rationale'])} chars")
                
                # Enhanced parsing info
                rationale_parsed = g.get('rationale_parsed', {})
                concerns = rationale_parsed.get('concerns', [])
                print(f"  Structure: {rationale_parsed.get('structure_type', 'unknown')}")
                print(f"  Concerns: {len(concerns)}")
                if concerns:
                    for i, c in enumerate(concerns[:2]):
                        preview = c[:60] + "..." if len(c) > 60 else c
                        print(f"    [{i}] {preview}")
                    if len(concerns) > 2:
                        print(f"    ... and {len(concerns) - 2} more")
                
                queries = g.get('search_queries', [])
                print(f"  Search queries: {len(queries)}")
                
                concepts = g.get('matched_concepts', [])
                if concepts:
                    print(f"  Matched concepts: {', '.join(concepts[:3])}")
                
                identifiers = g.get('amplification_identifiers', [])
                if identifiers:
                    print(f"  C identifiers: {', '.join(identifiers[:5])}")
                
                see_also = g.get('see_also_refs', [])
                if see_also:
                    print(f"  See also refs: {', '.join(see_also)}")
                
                break
    
    return 0


if __name__ == "__main__":
    exit(main())
