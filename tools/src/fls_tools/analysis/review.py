#!/usr/bin/env python3
"""
Review helper for coding standard to FLS mappings.

This script helps human reviewers validate FLS ID assignments by:
1. Loading existing mappings (MISRA C, MISRA C++, CERT C, CERT C++)
2. Extracting FLS section content from RST source files
3. Displaying mappings with full FLS context (paragraphs, surrounding sections)
4. Supporting both batch (markdown report) and interactive review modes

Usage:
    # Generate markdown report for all MISRA C guidelines
    uv run python review_fls_mappings.py --standard misra-c --output markdown --output-file review.md

    # Interactive review of a specific category
    uv run python review_fls_mappings.py --standard misra-c --category "Rule 11" --interactive

    # Review specific guideline with context
    uv run python review_fls_mappings.py --standard misra-c --guideline "Rule 11.1" --context 3

    # Filter by applicability
    uv run python review_fls_mappings.py --standard misra-c --applicability not_applicable --output markdown
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterator


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FLSParagraph:
    """A single paragraph from the FLS."""
    dp_id: str  # e.g., "fls_8kqo952gjhaf"
    text: str
    line_number: int


@dataclass
class FLSSection:
    """A section from the FLS RST source."""
    fls_id: str | None  # e.g., "fls_jep7p27kaqlp"
    title: str
    level: int  # 1 = chapter, 2 = section, 3 = subsection
    section_number: str | None  # e.g., "15.1", populated from fls_section_mapping
    file: str  # RST filename without extension
    line_number: int
    rubrics: dict[str, list[FLSParagraph]] = field(default_factory=dict)
    # Rubric names: "Legality Rules", "Runtime Semantics", "Syntax", "Examples", "Undefined Behavior"
    code_examples: list[str] = field(default_factory=list)


@dataclass
class GuidelineMapping:
    """A guideline's mapping to FLS."""
    guideline_id: str
    guideline_type: str  # rule, directive, recommendation
    title: str  # Full title from standards file
    fls_ids: list[str]
    fls_sections: list[str]
    applicability_all_rust: str
    applicability_safe_rust: str
    misra_rust_category: str | None
    misra_rust_comment: str | None
    confidence: str | None
    notes: str


# =============================================================================
# FLS RST Parser
# =============================================================================

class FLSParser:
    """Parse FLS RST source files to extract sections and paragraphs."""

    def __init__(self, fls_src_dir: Path):
        self.fls_src_dir = fls_src_dir
        self.sections_by_id: dict[str, FLSSection] = {}
        self.sections_by_file: dict[str, list[FLSSection]] = {}
        self._parse_all_files()

    def _parse_all_files(self) -> None:
        """Parse all RST files in the FLS source directory."""
        for rst_file in self.fls_src_dir.glob("*.rst"):
            if rst_file.name in ("index.rst", "conf.py", "glossary.rst", "changelog.rst", "licenses.rst"):
                continue
            self._parse_file(rst_file)

    def _parse_file(self, rst_file: Path) -> None:
        """Parse a single RST file."""
        file_key = rst_file.stem
        self.sections_by_file[file_key] = []

        content = rst_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        current_section: FLSSection | None = None
        current_rubric: str | None = None
        pending_fls_id: str | None = None
        in_code_block = False
        code_block_lines: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for FLS anchor: .. _fls_xxxxx:
            anchor_match = re.match(r"\.\. _fls_([a-zA-Z0-9]+):", line)
            if anchor_match:
                pending_fls_id = f"fls_{anchor_match.group(1)}"
                i += 1
                continue

            # Check for section title (followed by === or ---)
            if i + 1 < len(lines) and lines[i + 1].strip():
                next_line = lines[i + 1]
                if re.match(r"^=+$", next_line.strip()):
                    # Chapter level (=)
                    section = FLSSection(
                        fls_id=pending_fls_id,
                        title=line.strip(),
                        level=1,
                        section_number=None,
                        file=file_key,
                        line_number=i + 1,
                    )
                    self._register_section(section)
                    current_section = section
                    current_rubric = None
                    pending_fls_id = None
                    i += 2
                    continue
                elif re.match(r"^-+$", next_line.strip()):
                    # Section level (-)
                    section = FLSSection(
                        fls_id=pending_fls_id,
                        title=line.strip(),
                        level=2,
                        section_number=None,
                        file=file_key,
                        line_number=i + 1,
                    )
                    self._register_section(section)
                    current_section = section
                    current_rubric = None
                    pending_fls_id = None
                    i += 2
                    continue
                elif re.match(r"^~+$", next_line.strip()):
                    # Subsection level (~)
                    section = FLSSection(
                        fls_id=pending_fls_id,
                        title=line.strip(),
                        level=3,
                        section_number=None,
                        file=file_key,
                        line_number=i + 1,
                    )
                    self._register_section(section)
                    current_section = section
                    current_rubric = None
                    pending_fls_id = None
                    i += 2
                    continue

            # Check for rubric: .. rubric:: Name
            rubric_match = re.match(r"\.\. rubric:: (.+)", line)
            if rubric_match:
                rubric_name = rubric_match.group(1).strip()
                current_rubric = rubric_name
                if current_section and rubric_name not in current_section.rubrics:
                    current_section.rubrics[rubric_name] = []
                i += 1
                continue

            # Check for code block start
            if re.match(r"\.\. code-block::", line):
                in_code_block = True
                code_block_lines = []
                i += 1
                continue

            # Handle code block content
            if in_code_block:
                if line.strip() == "" and code_block_lines:
                    # Check if next non-empty line is still indented
                    j = i + 1
                    while j < len(lines) and lines[j].strip() == "":
                        j += 1
                    if j < len(lines) and not lines[j].startswith("   "):
                        # End of code block
                        if current_section:
                            current_section.code_examples.append("\n".join(code_block_lines))
                        in_code_block = False
                        code_block_lines = []
                elif line.startswith("   "):
                    code_block_lines.append(line[3:])  # Remove indent
                elif line.strip() == "":
                    code_block_lines.append("")
                else:
                    # End of code block
                    if current_section and code_block_lines:
                        current_section.code_examples.append("\n".join(code_block_lines))
                    in_code_block = False
                    code_block_lines = []
                    continue  # Re-process this line
                i += 1
                continue

            # Check for paragraph with dp ID: :dp:`fls_xxxxx`
            dp_match = re.match(r":dp:`(fls_[a-zA-Z0-9]+)`\s*(.*)", line)
            if dp_match:
                dp_id = dp_match.group(1)
                text_start = dp_match.group(2)

                # Collect full paragraph (may span multiple lines)
                para_lines = [text_start] if text_start else []
                i += 1
                while i < len(lines) and lines[i].strip() and not lines[i].startswith(":dp:") and not lines[i].startswith(".. "):
                    para_lines.append(lines[i].strip())
                    i += 1

                para_text = " ".join(para_lines)
                # Clean up RST markup
                para_text = re.sub(r":t:`([^`]+)`", r"\1", para_text)
                para_text = re.sub(r":dt:`([^`]+)`", r"\1", para_text)
                para_text = re.sub(r":std:`([^`]+)`", r"\1", para_text)
                para_text = re.sub(r":ds:`([^`]+)`", r"\1", para_text)
                para_text = re.sub(r":s:`([^`]+)`", r"\1", para_text)
                para_text = re.sub(r"\[([^\]]+)\]s", r"\1s", para_text)  # [value]s -> values

                if current_section and current_rubric:
                    current_section.rubrics[current_rubric].append(
                        FLSParagraph(dp_id=dp_id, text=para_text, line_number=i)
                    )
                continue

            i += 1

    def _register_section(self, section: FLSSection) -> None:
        """Register a section in lookup dictionaries."""
        if section.fls_id:
            self.sections_by_id[section.fls_id] = section
        self.sections_by_file[section.file].append(section)

    def get_section(self, fls_id: str) -> FLSSection | None:
        """Get a section by its FLS ID."""
        return self.sections_by_id.get(fls_id)

    def get_nearby_sections(self, fls_id: str, context: int = 2) -> list[FLSSection]:
        """Get sections near the given FLS ID (same file, nearby in order)."""
        section = self.get_section(fls_id)
        if not section:
            return []

        file_sections = self.sections_by_file.get(section.file, [])
        try:
            idx = file_sections.index(section)
        except ValueError:
            return []

        start = max(0, idx - context)
        end = min(len(file_sections), idx + context + 1)
        return file_sections[start:end]


# =============================================================================
# Mapping Loader
# =============================================================================

class MappingLoader:
    """Load guideline mappings and standards data."""

    STANDARD_FILES = {
        "misra-c": {
            "standards": "standards/misra_c_2025.json",
            "mapping": "mappings/misra_c_to_fls.json",
        },
        "misra-cpp": {
            "standards": "standards/misra_cpp_2023.json",
            "mapping": "mappings/misra_cpp_to_fls.json",
        },
        "cert-c": {
            "standards": "standards/cert_c.json",
            "mapping": "mappings/cert_c_to_fls.json",
        },
        "cert-cpp": {
            "standards": "standards/cert_cpp.json",
            "mapping": "mappings/cert_cpp_to_fls.json",
        },
    }

    def __init__(self, base_dir: Path, standard: str):
        self.base_dir = base_dir
        self.standard = standard

        if standard not in self.STANDARD_FILES:
            raise ValueError(f"Unknown standard: {standard}. Valid: {list(self.STANDARD_FILES.keys())}")

        self.standards_data = self._load_json(self.STANDARD_FILES[standard]["standards"])
        self.mapping_data = self._load_json(self.STANDARD_FILES[standard]["mapping"])

        # Build title lookup from standards
        self.titles: dict[str, str] = {}
        for category in self.standards_data.get("categories", []):
            for guideline in category.get("guidelines", []):
                self.titles[guideline["id"]] = guideline.get("title", "")

    def _load_json(self, rel_path: str) -> dict:
        """Load a JSON file relative to base_dir."""
        path = self.base_dir / rel_path
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def get_mappings(self) -> list[GuidelineMapping]:
        """Get all guideline mappings."""
        mappings = []
        for m in self.mapping_data.get("mappings", []):
            gid = m.get("guideline_id", "")
            mappings.append(GuidelineMapping(
                guideline_id=gid,
                guideline_type=m.get("guideline_type", "rule"),
                title=self.titles.get(gid, ""),
                fls_ids=m.get("fls_ids", []),
                fls_sections=m.get("fls_sections", []),
                applicability_all_rust=m.get("applicability_all_rust", "unmapped"),
                applicability_safe_rust=m.get("applicability_safe_rust", "unmapped"),
                misra_rust_category=m.get("misra_rust_category"),
                misra_rust_comment=m.get("misra_rust_comment"),
                confidence=m.get("confidence"),
                notes=m.get("notes", ""),
            ))
        return mappings

    def filter_mappings(
        self,
        mappings: list[GuidelineMapping],
        guideline: str | None = None,
        category: str | None = None,
        applicability: str | None = None,
        batch_start: int | None = None,
        batch_end: int | None = None,
    ) -> list[GuidelineMapping]:
        """Filter mappings based on criteria."""
        result = mappings

        if guideline:
            result = [m for m in result if m.guideline_id == guideline]

        if category:
            # Match category prefix (e.g., "Rule 11" matches "Rule 11.1", "Rule 11.2", etc.)
            result = [m for m in result if m.guideline_id.startswith(category)]

        if applicability:
            result = [m for m in result if m.applicability_all_rust == applicability]

        if batch_start is not None or batch_end is not None:
            start = batch_start or 0
            end = batch_end or len(result)
            result = result[start:end]

        return result


# =============================================================================
# FLS Section Mapping Loader
# =============================================================================

class FLSSectionMapping:
    """Load and query the FLS section mapping."""

    def __init__(self, mapping_path: Path):
        with open(mapping_path, encoding="utf-8") as f:
            self.data = json.load(f)

        # Build ID to info lookup
        self.id_to_info: dict[str, dict] = {}
        self._build_lookup(self.data)

    def _build_lookup(self, data: dict, parent_section: str = "") -> None:
        """Recursively build FLS ID lookup."""
        for key, value in data.items():
            if isinstance(value, dict):
                fls_id = value.get("fls_id")
                section = value.get("fls_section", key)
                title = value.get("title", key)

                if fls_id and fls_id != "fls_extracted_from_syntax_block":
                    self.id_to_info[fls_id] = {
                        "section": section,
                        "title": title,
                        "file": value.get("file"),
                    }

                # Recurse into sections and subsections
                if "sections" in value:
                    self._build_lookup(value["sections"], section)
                if "subsections" in value:
                    self._build_lookup(value["subsections"], section)

    def get_info(self, fls_id: str) -> dict | None:
        """Get section info for an FLS ID."""
        return self.id_to_info.get(fls_id)

    def get_section_number(self, fls_id: str) -> str | None:
        """Get section number for an FLS ID."""
        info = self.get_info(fls_id)
        return info["section"] if info else None

    def get_title(self, fls_id: str) -> str | None:
        """Get title for an FLS ID."""
        info = self.get_info(fls_id)
        return info["title"] if info else None


# =============================================================================
# Output Formatters
# =============================================================================

class TerminalFormatter:
    """Format output for terminal display."""

    def format_mapping(
        self,
        mapping: GuidelineMapping,
        fls_parser: FLSParser,
        section_mapping: FLSSectionMapping,
        context: int = 2,
        show_paragraphs: bool = True,
        show_code_examples: bool = False,
    ) -> str:
        """Format a single mapping for terminal output."""
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append(f"📋 {mapping.guideline_id} ({mapping.guideline_type})")
        lines.append("=" * 80)
        lines.append(f"Title: {mapping.title}")
        lines.append("")

        # Current mapping
        lines.append("📍 CURRENT MAPPING:")
        lines.append(f"  applicability_all_rust:  {mapping.applicability_all_rust}")
        lines.append(f"  applicability_safe_rust: {mapping.applicability_safe_rust}")
        if mapping.misra_rust_category:
            lines.append(f"  misra_rust_category:     {mapping.misra_rust_category}")
        if mapping.misra_rust_comment:
            lines.append(f"  misra_rust_comment:      {mapping.misra_rust_comment}")
        lines.append(f"  confidence:              {mapping.confidence or 'N/A'}")
        lines.append(f"  notes: {mapping.notes}")
        lines.append("")

        # FLS IDs
        lines.append(f"📚 ASSIGNED FLS IDs ({len(mapping.fls_ids)}):")
        if not mapping.fls_ids:
            lines.append("  (none)")
        for fls_id in mapping.fls_ids:
            section_num = section_mapping.get_section_number(fls_id) or "?"
            title = section_mapping.get_title(fls_id) or "Unknown"
            lines.append(f"  • {fls_id} → {section_num} {title}")

        lines.append("")
        lines.append(f"📄 FLS Sections: {', '.join(mapping.fls_sections) if mapping.fls_sections else '(none)'}")
        lines.append("")

        # FLS content for each assigned ID
        if show_paragraphs and mapping.fls_ids:
            lines.append("📖 FLS CONTENT FOR ASSIGNED IDs:")
            lines.append("-" * 40)

            for fls_id in mapping.fls_ids:
                section = fls_parser.get_section(fls_id)
                if section:
                    lines.append(f"\n🔹 {fls_id}: {section.title}")
                    lines.append(f"   File: {section.file}.rst, Line: {section.line_number}")

                    for rubric_name, paragraphs in section.rubrics.items():
                        if paragraphs:
                            lines.append(f"\n   [{rubric_name}]")
                            for para in paragraphs[:5]:  # Limit to first 5 paragraphs
                                text = para.text[:200] + "..." if len(para.text) > 200 else para.text
                                lines.append(f"   • {text}")
                            if len(paragraphs) > 5:
                                lines.append(f"   ... and {len(paragraphs) - 5} more paragraphs")

                    if show_code_examples and section.code_examples:
                        lines.append(f"\n   [Code Examples]")
                        for example in section.code_examples[:2]:
                            lines.append("   ```rust")
                            for line in example.split("\n")[:10]:
                                lines.append(f"   {line}")
                            lines.append("   ```")
                else:
                    lines.append(f"\n🔹 {fls_id}: (not found in RST source)")

            lines.append("")

        # Nearby sections for context
        if context > 0 and mapping.fls_ids:
            lines.append("🔍 NEARBY FLS SECTIONS (for context):")
            lines.append("-" * 40)

            shown_ids = set(mapping.fls_ids)
            for fls_id in mapping.fls_ids[:2]:  # Limit to first 2 IDs for context
                nearby = fls_parser.get_nearby_sections(fls_id, context)
                for sec in nearby:
                    if sec.fls_id and sec.fls_id not in shown_ids:
                        section_num = section_mapping.get_section_number(sec.fls_id) or "?"
                        lines.append(f"  ○ {sec.fls_id} → {section_num} {sec.title}")
                        shown_ids.add(sec.fls_id)

            lines.append("")

        return "\n".join(lines)


class MarkdownFormatter:
    """Format output as Markdown."""

    def format_header(self, standard: str, total: int) -> str:
        """Format report header."""
        lines = [
            f"# FLS Mapping Review: {standard.upper()}",
            "",
            f"Generated: {date.today().isoformat()}",
            f"Total guidelines: {total}",
            "",
            "---",
            "",
        ]
        return "\n".join(lines)

    def format_mapping(
        self,
        mapping: GuidelineMapping,
        fls_parser: FLSParser,
        section_mapping: FLSSectionMapping,
        context: int = 2,
        show_paragraphs: bool = True,
        show_code_examples: bool = False,
    ) -> str:
        """Format a single mapping as Markdown."""
        lines = []

        # Header
        lines.append(f"## {mapping.guideline_id}")
        lines.append("")
        lines.append(f"**Type:** {mapping.guideline_type}")
        lines.append(f"**Title:** {mapping.title}")
        lines.append("")

        # Current mapping table
        lines.append("### Current Mapping")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| applicability_all_rust | `{mapping.applicability_all_rust}` |")
        lines.append(f"| applicability_safe_rust | `{mapping.applicability_safe_rust}` |")
        if mapping.misra_rust_category:
            lines.append(f"| misra_rust_category | `{mapping.misra_rust_category}` |")
        if mapping.misra_rust_comment:
            lines.append(f"| misra_rust_comment | {mapping.misra_rust_comment} |")
        lines.append(f"| confidence | `{mapping.confidence or 'N/A'}` |")
        lines.append("")

        lines.append(f"**Notes:** {mapping.notes}")
        lines.append("")

        # FLS IDs
        lines.append("### Assigned FLS IDs")
        lines.append("")
        if not mapping.fls_ids:
            lines.append("_(none)_")
        else:
            lines.append("| FLS ID | Section | Title |")
            lines.append("|--------|---------|-------|")
            for fls_id in mapping.fls_ids:
                section_num = section_mapping.get_section_number(fls_id) or "?"
                title = section_mapping.get_title(fls_id) or "Unknown"
                lines.append(f"| `{fls_id}` | {section_num} | {title} |")
        lines.append("")

        if mapping.fls_sections:
            lines.append(f"**FLS Sections:** {', '.join(mapping.fls_sections)}")
            lines.append("")

        # FLS content
        if show_paragraphs and mapping.fls_ids:
            lines.append("### FLS Content")
            lines.append("")

            for fls_id in mapping.fls_ids:
                section = fls_parser.get_section(fls_id)
                if section:
                    lines.append(f"#### `{fls_id}`: {section.title}")
                    lines.append("")
                    lines.append(f"_File: {section.file}.rst, Line: {section.line_number}_")
                    lines.append("")

                    for rubric_name, paragraphs in section.rubrics.items():
                        if paragraphs:
                            lines.append(f"**{rubric_name}:**")
                            lines.append("")
                            for para in paragraphs[:5]:
                                text = para.text[:300] + "..." if len(para.text) > 300 else para.text
                                lines.append(f"- {text}")
                            if len(paragraphs) > 5:
                                lines.append(f"- _... and {len(paragraphs) - 5} more paragraphs_")
                            lines.append("")

                    if show_code_examples and section.code_examples:
                        lines.append("**Code Examples:**")
                        lines.append("")
                        for example in section.code_examples[:2]:
                            lines.append("```rust")
                            lines.append(example[:500])
                            lines.append("```")
                            lines.append("")
                else:
                    lines.append(f"#### `{fls_id}`: _(not found in RST source)_")
                    lines.append("")

        # Nearby sections
        if context > 0 and mapping.fls_ids:
            lines.append("### Nearby FLS Sections")
            lines.append("")
            lines.append("_Sections near assigned IDs that might be relevant:_")
            lines.append("")

            shown_ids = set(mapping.fls_ids)
            nearby_found = False
            for fls_id in mapping.fls_ids[:2]:
                nearby = fls_parser.get_nearby_sections(fls_id, context)
                for sec in nearby:
                    if sec.fls_id and sec.fls_id not in shown_ids:
                        section_num = section_mapping.get_section_number(sec.fls_id) or "?"
                        lines.append(f"- `{sec.fls_id}` → {section_num} {sec.title}")
                        shown_ids.add(sec.fls_id)
                        nearby_found = True

            if not nearby_found:
                lines.append("_(none)_")
            lines.append("")

        # Review section
        lines.append("### Review")
        lines.append("")
        lines.append("- [ ] FLS IDs are correct")
        lines.append("- [ ] No missing FLS IDs")
        lines.append("- [ ] Applicability values correct")
        lines.append("- [ ] Notes are adequate")
        lines.append("")
        lines.append("**Issues found:**")
        lines.append("")
        lines.append("```")
        lines.append("(none)")
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

        return "\n".join(lines)


class JSONFormatter:
    """Format output as JSON."""

    def format_mapping(
        self,
        mapping: GuidelineMapping,
        fls_parser: FLSParser,
        section_mapping: FLSSectionMapping,
        context: int = 2,
        show_paragraphs: bool = True,
        show_code_examples: bool = False,
    ) -> dict:
        """Format a single mapping as a dict (for JSON output)."""
        result = {
            "guideline_id": mapping.guideline_id,
            "guideline_type": mapping.guideline_type,
            "title": mapping.title,
            "current_mapping": {
                "fls_ids": mapping.fls_ids,
                "fls_sections": mapping.fls_sections,
                "applicability_all_rust": mapping.applicability_all_rust,
                "applicability_safe_rust": mapping.applicability_safe_rust,
                "misra_rust_category": mapping.misra_rust_category,
                "misra_rust_comment": mapping.misra_rust_comment,
                "confidence": mapping.confidence,
                "notes": mapping.notes,
            },
            "fls_content": {},
            "nearby_sections": [],
        }

        # FLS content
        if show_paragraphs:
            for fls_id in mapping.fls_ids:
                section = fls_parser.get_section(fls_id)
                if section:
                    section_info = {
                        "title": section.title,
                        "file": section.file,
                        "line_number": section.line_number,
                        "section_number": section_mapping.get_section_number(fls_id),
                        "rubrics": {},
                    }
                    for rubric_name, paragraphs in section.rubrics.items():
                        section_info["rubrics"][rubric_name] = [
                            {"dp_id": p.dp_id, "text": p.text} for p in paragraphs
                        ]
                    if show_code_examples:
                        section_info["code_examples"] = section.code_examples
                    result["fls_content"][fls_id] = section_info

        # Nearby sections
        if context > 0:
            shown_ids = set(mapping.fls_ids)
            for fls_id in mapping.fls_ids[:2]:
                nearby = fls_parser.get_nearby_sections(fls_id, context)
                for sec in nearby:
                    if sec.fls_id and sec.fls_id not in shown_ids:
                        result["nearby_sections"].append({
                            "fls_id": sec.fls_id,
                            "title": sec.title,
                            "section_number": section_mapping.get_section_number(sec.fls_id),
                        })
                        shown_ids.add(sec.fls_id)

        return result


# =============================================================================
# Interactive Mode
# =============================================================================

class InteractiveReviewer:
    """Interactive review mode."""

    def __init__(
        self,
        mappings: list[GuidelineMapping],
        fls_parser: FLSParser,
        section_mapping: FLSSectionMapping,
        formatter: TerminalFormatter,
        context: int = 2,
        show_paragraphs: bool = True,
        show_code_examples: bool = False,
        decisions_file: Path | None = None,
    ):
        self.mappings = mappings
        self.fls_parser = fls_parser
        self.section_mapping = section_mapping
        self.formatter = formatter
        self.context = context
        self.show_paragraphs = show_paragraphs
        self.show_code_examples = show_code_examples
        self.decisions_file = decisions_file
        self.decisions: dict[str, dict] = {}

        if decisions_file and decisions_file.exists():
            with open(decisions_file, encoding="utf-8") as f:
                self.decisions = json.load(f)

    def run(self) -> None:
        """Run interactive review."""
        print("\n🔍 INTERACTIVE REVIEW MODE")
        print("=" * 40)
        print("Commands:")
        print("  [Enter] - Mark as correct, next")
        print("  f       - Flag for fixing, next")
        print("  s       - Skip, next")
        print("  n       - Add note")
        print("  p       - Previous")
        print("  g N     - Go to index N")
        print("  q       - Quit and save")
        print("=" * 40)
        print(f"Total guidelines to review: {len(self.mappings)}")
        print()

        idx = 0
        while 0 <= idx < len(self.mappings):
            mapping = self.mappings[idx]

            # Show current mapping
            output = self.formatter.format_mapping(
                mapping,
                self.fls_parser,
                self.section_mapping,
                self.context,
                self.show_paragraphs,
                self.show_code_examples,
            )
            print(output)

            # Show current decision if any
            if mapping.guideline_id in self.decisions:
                dec = self.decisions[mapping.guideline_id]
                print(f"📌 Current decision: {dec.get('status', '?')} - {dec.get('note', '')}")
                print()

            # Get user input
            print(f"[{idx + 1}/{len(self.mappings)}] Decision? ", end="", flush=True)
            try:
                cmd = input().strip().lower()
            except EOFError:
                break

            if cmd == "" or cmd == "c":
                # Correct
                self.decisions[mapping.guideline_id] = {"status": "correct", "note": ""}
                idx += 1
            elif cmd == "f":
                # Flag for fixing
                print("  Note (optional): ", end="", flush=True)
                note = input().strip()
                self.decisions[mapping.guideline_id] = {"status": "needs_fix", "note": note}
                idx += 1
            elif cmd == "s":
                # Skip
                self.decisions[mapping.guideline_id] = {"status": "skipped", "note": ""}
                idx += 1
            elif cmd == "n":
                # Add note
                print("  Note: ", end="", flush=True)
                note = input().strip()
                if mapping.guideline_id in self.decisions:
                    self.decisions[mapping.guideline_id]["note"] = note
                else:
                    self.decisions[mapping.guideline_id] = {"status": "pending", "note": note}
            elif cmd == "p":
                # Previous
                idx = max(0, idx - 1)
            elif cmd.startswith("g "):
                # Go to index
                try:
                    new_idx = int(cmd[2:]) - 1
                    if 0 <= new_idx < len(self.mappings):
                        idx = new_idx
                    else:
                        print(f"  Invalid index. Range: 1-{len(self.mappings)}")
                except ValueError:
                    print("  Invalid index number")
            elif cmd == "q":
                # Quit
                break
            else:
                print("  Unknown command. Press Enter for next, 'q' to quit.")

        # Save decisions
        self._save_decisions()
        print(f"\n✅ Review complete. Decisions saved.")

    def _save_decisions(self) -> None:
        """Save decisions to file."""
        if self.decisions_file:
            with open(self.decisions_file, "w", encoding="utf-8") as f:
                json.dump(self.decisions, f, indent=2)
            print(f"   Saved to: {self.decisions_file}")

        # Print summary
        correct = sum(1 for d in self.decisions.values() if d.get("status") == "correct")
        needs_fix = sum(1 for d in self.decisions.values() if d.get("status") == "needs_fix")
        skipped = sum(1 for d in self.decisions.values() if d.get("status") == "skipped")
        print(f"   Summary: {correct} correct, {needs_fix} need fix, {skipped} skipped")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Review helper for coding standard to FLS mappings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate markdown report for all MISRA C guidelines
  %(prog)s --standard misra-c --output markdown --output-file review.md

  # Interactive review of Rule 11 category
  %(prog)s --standard misra-c --category "Rule 11" --interactive

  # Review specific guideline
  %(prog)s --standard misra-c --guideline "Rule 11.1" --context 3

  # Filter by applicability
  %(prog)s --standard misra-c --applicability not_applicable --output markdown
        """,
    )

    # Input/filtering
    parser.add_argument(
        "--standard",
        choices=["misra-c", "misra-cpp", "cert-c", "cert-cpp"],
        default="misra-c",
        help="Coding standard to review (default: misra-c)",
    )
    parser.add_argument(
        "--guideline",
        help="Review specific guideline (e.g., 'Rule 11.1')",
    )
    parser.add_argument(
        "--category",
        help="Review all guidelines in category (e.g., 'Rule 11', 'Dir 4')",
    )
    parser.add_argument(
        "--batch",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="Review range by index (0-based, exclusive end)",
    )
    parser.add_argument(
        "--applicability",
        choices=["direct", "partial", "not_applicable", "rust_prevents", "unmapped"],
        help="Filter by applicability_all_rust value",
    )

    # Output
    parser.add_argument(
        "--output",
        choices=["terminal", "markdown", "json"],
        default="terminal",
        help="Output format (default: terminal)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="File to write output (default: stdout)",
    )

    # Context
    parser.add_argument(
        "--context",
        type=int,
        default=2,
        help="Number of sibling sections to show (default: 2)",
    )
    parser.add_argument(
        "--no-paragraphs",
        action="store_true",
        help="Don't show full paragraph text",
    )
    parser.add_argument(
        "--show-code-examples",
        action="store_true",
        help="Include code examples from RST",
    )

    # Interactive mode
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive review mode",
    )
    parser.add_argument(
        "--record-decisions",
        type=Path,
        help="File to record review decisions (JSON)",
    )

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent / "coding-standards-fls-mapping"
    fls_src_dir = script_dir.parent / "cache" / "repos" / "fls" / "src"
    section_mapping_path = script_dir / "fls_section_mapping.json"

    # Validate paths
    if not fls_src_dir.exists():
        print(f"Error: FLS source directory not found: {fls_src_dir}", file=sys.stderr)
        print("Run: git clone https://github.com/ferrocene/specification cache/repos/fls", file=sys.stderr)
        sys.exit(1)

    if not section_mapping_path.exists():
        print(f"Error: FLS section mapping not found: {section_mapping_path}", file=sys.stderr)
        sys.exit(1)

    # Load data
    print("Loading FLS RST source...", file=sys.stderr)
    fls_parser = FLSParser(fls_src_dir)
    print(f"  Loaded {len(fls_parser.sections_by_id)} sections", file=sys.stderr)

    print("Loading FLS section mapping...", file=sys.stderr)
    section_mapping = FLSSectionMapping(section_mapping_path)
    print(f"  Loaded {len(section_mapping.id_to_info)} FLS IDs", file=sys.stderr)

    print(f"Loading {args.standard} mappings...", file=sys.stderr)
    try:
        loader = MappingLoader(base_dir, args.standard)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    mappings = loader.get_mappings()
    print(f"  Loaded {len(mappings)} guidelines", file=sys.stderr)

    # Filter
    batch_start, batch_end = args.batch if args.batch else (None, None)
    filtered = loader.filter_mappings(
        mappings,
        guideline=args.guideline,
        category=args.category,
        applicability=args.applicability,
        batch_start=batch_start,
        batch_end=batch_end,
    )
    print(f"  Filtered to {len(filtered)} guidelines", file=sys.stderr)

    if not filtered:
        print("No guidelines match the filter criteria.", file=sys.stderr)
        sys.exit(0)

    # Output options
    show_paragraphs = not args.no_paragraphs

    # Interactive mode
    if args.interactive:
        formatter = TerminalFormatter()
        reviewer = InteractiveReviewer(
            filtered,
            fls_parser,
            section_mapping,
            formatter,
            context=args.context,
            show_paragraphs=show_paragraphs,
            show_code_examples=args.show_code_examples,
            decisions_file=args.record_decisions,
        )
        reviewer.run()
        return

    # Batch output
    output_lines = []

    if args.output == "markdown":
        formatter = MarkdownFormatter()
        output_lines.append(formatter.format_header(args.standard, len(filtered)))
        for mapping in filtered:
            output_lines.append(formatter.format_mapping(
                mapping,
                fls_parser,
                section_mapping,
                args.context,
                show_paragraphs,
                args.show_code_examples,
            ))
        output_text = "\n".join(output_lines)

    elif args.output == "json":
        formatter = JSONFormatter()
        result = {
            "standard": args.standard,
            "generated": date.today().isoformat(),
            "total": len(filtered),
            "mappings": [
                formatter.format_mapping(
                    mapping,
                    fls_parser,
                    section_mapping,
                    args.context,
                    show_paragraphs,
                    args.show_code_examples,
                )
                for mapping in filtered
            ],
        }
        output_text = json.dumps(result, indent=2)

    else:  # terminal
        formatter = TerminalFormatter()
        for mapping in filtered:
            output_lines.append(formatter.format_mapping(
                mapping,
                fls_parser,
                section_mapping,
                args.context,
                show_paragraphs,
                args.show_code_examples,
            ))
        output_text = "\n".join(output_lines)

    # Write output
    if args.output_file:
        args.output_file.write_text(output_text, encoding="utf-8")
        print(f"Output written to: {args.output_file}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
