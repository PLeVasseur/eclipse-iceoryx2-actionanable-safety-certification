"""
FLS data loading utilities.

This module provides functions for loading FLS chapter files
and building metadata structures for FLS sections and paragraphs.
"""

import json
from pathlib import Path

from .paths import get_fls_dir
from .constants import CATEGORY_NAMES


def load_fls_chapters(root: Path | None = None) -> dict[int, dict]:
    """
    Load all FLS chapter files from embeddings/fls/.
    
    Args:
        root: Project root path. If None, uses get_project_root().
    
    Returns:
        Dict mapping chapter number (int) to chapter data (dict).
        Each chapter dict contains 'chapter', 'title', 'fls_id', 'sections'.
    """
    fls_dir = get_fls_dir(root)
    chapters: dict[int, dict] = {}
    
    for chapter_file in fls_dir.glob("chapter_*.json"):
        try:
            with open(chapter_file, encoding="utf-8") as f:
                data = json.load(f)
                chapter_num = data.get("chapter")
                if chapter_num is not None:
                    chapters[chapter_num] = data
        except (json.JSONDecodeError, KeyError):
            continue
    
    return chapters


def build_fls_metadata(
    chapters: dict[int, dict],
) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Build sections and paragraphs metadata dicts from loaded chapters.
    
    This function extracts metadata for quick lookup during search operations.
    
    Args:
        chapters: Dict of chapter data from load_fls_chapters()
    
    Returns:
        Tuple of:
        - sections_metadata: fls_id -> {title, chapter, category}
        - paragraphs_metadata: para_id -> {text, section_fls_id, section_title, category, chapter}
    """
    sections_metadata: dict[str, dict] = {}
    paragraphs_metadata: dict[str, dict] = {}
    
    for chapter_num, chapter in chapters.items():
        for section in chapter.get("sections", []):
            fls_id = section.get("fls_id")
            if fls_id:
                sections_metadata[fls_id] = {
                    "title": section.get("title", ""),
                    "chapter": chapter_num,
                    "category": section.get("category", 0),
                }
            
            # Extract paragraph metadata from rubrics
            for cat_key, rubric_data in section.get("rubrics", {}).items():
                for para_id, para_text in rubric_data.get("paragraphs", {}).items():
                    paragraphs_metadata[para_id] = {
                        "text": para_text,
                        "section_fls_id": fls_id,
                        "section_title": section.get("title", ""),
                        "category": int(cat_key),
                        "category_name": CATEGORY_NAMES.get(int(cat_key), f"unknown_{cat_key}"),
                        "chapter": chapter_num,
                    }
    
    return sections_metadata, paragraphs_metadata


def find_section_by_fls_id(
    chapters: dict[int, dict],
    fls_id: str,
) -> dict | None:
    """
    Find a section by its FLS ID across all chapters.
    
    Args:
        chapters: Dict of chapter data from load_fls_chapters()
        fls_id: The FLS ID to search for
    
    Returns:
        Dict with 'chapter', 'section', and 'chapter_fls_id' if found,
        None otherwise.
    """
    for chapter_num, chapter in chapters.items():
        for section in chapter.get("sections", []):
            if section.get("fls_id") == fls_id:
                return {
                    "chapter": chapter_num,
                    "section": section,
                    "chapter_fls_id": chapter.get("fls_id"),
                }
    return None


def get_sibling_sections(
    chapters: dict[int, dict],
    section_info: dict,
) -> list[dict]:
    """
    Get sibling sections (same parent) for a given section.
    
    Args:
        chapters: Dict of chapter data from load_fls_chapters()
        section_info: Section info dict from find_section_by_fls_id()
    
    Returns:
        List of dicts with 'chapter' and 'section' for each sibling.
    """
    if not section_info:
        return []
    
    chapter_num = section_info["chapter"]
    section = section_info["section"]
    parent_fls_id = section.get("parent_fls_id")
    section_fls_id = section.get("fls_id")
    
    if not parent_fls_id:
        return []
    
    siblings = []
    chapter = chapters.get(chapter_num, {})
    
    for s in chapter.get("sections", []):
        if s.get("parent_fls_id") == parent_fls_id and s.get("fls_id") != section_fls_id:
            siblings.append({
                "chapter": chapter_num,
                "section": s,
            })
    
    return siblings
