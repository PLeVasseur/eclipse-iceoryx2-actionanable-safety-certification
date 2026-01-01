#!/usr/bin/env python3
"""
recompute_similarity.py - Recompute Similarity for Specific Guidelines

This script recomputes similarity between a specific MISRA guideline and all FLS
sections/paragraphs. Useful when pre-computed similarity seems to have missed
relevant sections.

Unlike the batch compute_similarity.py, this:
1. Works on a single guideline at a time
2. Uses the full MISRA rationale text (not just title)
3. Shows more detailed results
4. Optionally outputs in a format ready for the batch report

Usage:
    uv run python verification/recompute_similarity.py --guideline "Rule 21.3"
    uv run python verification/recompute_similarity.py --guideline "Rule 21.3" --top 20 --json
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from fls_tools.shared import (
    get_project_root,
    get_fls_dir,
    get_standard_extracted_text_path,
    get_standard_similarity_path,
    get_fls_section_embeddings_path,
    get_fls_paragraph_embeddings_path,
    CATEGORY_NAMES,
    VALID_STANDARDS,
)


def load_json(path: Path, description: str) -> dict:
    """Load a JSON file with error handling."""
    if not path.exists():
        print(f"ERROR: {description} not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_embeddings(path: Path, description: str) -> tuple[list[str], np.ndarray, dict]:
    """
    Load embeddings from pickle file.
    
    Returns:
        ids: List of FLS IDs
        embeddings: numpy array of embeddings (N x D)
        id_to_index: Dict mapping FLS ID to index
    """
    if not path.exists():
        print(f"ERROR: {description} not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "rb") as f:
        data = pickle.load(f)
    
    # Handle the actual embeddings format
    embed_data = data.get("data", data)
    
    ids = embed_data.get("ids", [])
    embeddings = embed_data.get("embeddings", np.array([]))
    id_to_index = embed_data.get("id_to_index", {})
    
    return ids, embeddings, id_to_index


def load_fls_chapters(root: Path) -> dict:
    """Load all FLS chapter files for content lookup."""
    chapters = {}
    fls_dir = get_fls_dir(root)
    
    for chapter_file in fls_dir.glob("chapter_*.json"):
        try:
            with open(chapter_file) as f:
                data = json.load(f)
                chapter_num = data.get("chapter")
                if chapter_num:
                    chapters[chapter_num] = data
        except (json.JSONDecodeError, KeyError):
            continue
    
    return chapters


def build_metadata_from_chapters(chapters: dict) -> tuple[dict, dict]:
    """
    Build sections and paragraphs metadata dicts from loaded chapters.
    
    Returns:
        sections_metadata: Dict mapping fls_id -> {title, chapter, category}
        paragraphs_metadata: Dict mapping para_id -> {text, section_fls_id, section_title, category, chapter}
    """
    sections_metadata = {}
    paragraphs_metadata = {}
    
    for chapter_num, chapter in chapters.items():
        for section in chapter.get("sections", []):
            fls_id = section.get("fls_id")
            if fls_id:
                sections_metadata[fls_id] = {
                    "title": section.get("title", ""),
                    "chapter": chapter_num,
                    "category": section.get("category", 0),
                }
            # Also extract paragraph metadata from rubrics
            for cat_key, rubric_data in section.get("rubrics", {}).items():
                for para_id, para_text in rubric_data.get("paragraphs", {}).items():
                    paragraphs_metadata[para_id] = {
                        "text": para_text,
                        "section_fls_id": fls_id,
                        "section_title": section.get("title", ""),
                        "category": int(cat_key),
                        "chapter": chapter_num,
                    }
    
    return sections_metadata, paragraphs_metadata


def get_misra_text(misra_data: dict, guideline_id: str) -> str | None:
    """Get the full text for a MISRA guideline (title + rationale)."""
    for g in misra_data.get("guidelines", []):
        if g.get("guideline_id") == guideline_id:
            title = g.get("title", "")
            rationale = g.get("rationale", "")
            amplification = g.get("amplification", "")
            
            # Combine all available text
            parts = [title]
            if rationale:
                parts.append(rationale)
            if amplification:
                parts.append(amplification)
            
            return " ".join(parts)
    return None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def search_sections(
    query_embedding: np.ndarray,
    ids: list[str],
    embeddings: np.ndarray,
    sections_metadata: dict,
    top_n: int,
) -> list[dict]:
    """Search section-level embeddings."""
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    # Compute similarities with all embeddings at once (vectorized)
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    embed_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    similarities = np.dot(embed_norms, query_norm)
    
    # Get top-n indices
    top_indices = np.argsort(similarities)[::-1][:top_n]
    
    results = []
    for idx in top_indices:
        fls_id = ids[idx]
        similarity = float(similarities[idx])
        
        # Get metadata from sections_metadata if available
        section = sections_metadata.get(fls_id, {})
        
        results.append({
            "fls_id": fls_id,
            "similarity": round(similarity, 4),
            "title": section.get("title", ""),
            "chapter": section.get("chapter"),
            "category": section.get("category", 0),
        })
    
    return results


def search_paragraphs(
    query_embedding: np.ndarray,
    ids: list[str],
    embeddings: np.ndarray,
    paragraphs_metadata: dict,
    top_n: int,
    threshold: float = 0.5,
) -> list[dict]:
    """Search paragraph-level embeddings."""
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    # Compute similarities with all embeddings at once (vectorized)
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    embed_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    similarities = np.dot(embed_norms, query_norm)
    
    # Get all indices sorted by similarity (for threshold filtering)
    sorted_indices = np.argsort(similarities)[::-1]
    
    results = []
    for idx in sorted_indices:
        fls_id = ids[idx]
        similarity = float(similarities[idx])
        
        # Get metadata from paragraphs_metadata if available
        meta = paragraphs_metadata.get(fls_id, {})
        category = meta.get("category", 0)
        category_name = CATEGORY_NAMES.get(category, f"unknown_{category}")
        
        results.append({
            "fls_id": fls_id,
            "similarity": round(similarity, 4),
            "text_preview": meta.get("text", "")[:150] + "..." if meta.get("text") else "",
            "section_fls_id": meta.get("section_fls_id", ""),
            "section_title": meta.get("section_title", ""),
            "category": category,
            "category_name": category_name,
            "chapter": meta.get("chapter"),
        })
    
    # Return top_n OR anything above threshold
    top_results = results[:top_n]
    threshold_results = [r for r in results[top_n:] if r["similarity"] >= threshold]
    
    return top_results + threshold_results


def compare_with_precomputed(
    guideline_id: str,
    new_section_results: list[dict],
    new_paragraph_results: list[dict],
    precomputed: dict,
) -> dict:
    """Compare new results with pre-computed similarity."""
    pre = precomputed.get("results", {}).get(guideline_id, {})
    pre_sections = {m["fls_id"] for m in pre.get("top_matches", [])}
    pre_paragraphs = {m["fls_id"] for m in pre.get("top_paragraph_matches", [])}
    
    new_sections = {r["fls_id"] for r in new_section_results}
    new_paragraphs = {r["fls_id"] for r in new_paragraph_results}
    
    return {
        "sections_only_in_new": list(new_sections - pre_sections),
        "sections_only_in_precomputed": list(pre_sections - new_sections),
        "paragraphs_only_in_new": list(new_paragraphs - pre_paragraphs),
        "paragraphs_only_in_precomputed": list(pre_paragraphs - new_paragraphs),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Recompute similarity for a specific coding standard guideline"
    )
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard (e.g., misra-c, cert-cpp)",
    )
    parser.add_argument(
        "--guideline",
        type=str,
        required=True,
        help="Guideline ID (e.g., 'Rule 21.3')",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top results to return (default: 15)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Also include paragraphs above this score (default: 0.5)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare results with pre-computed similarity",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Load standard extracted text
    standard_path = get_standard_extracted_text_path(root, args.standard)
    print(f"Loading extracted text...", file=sys.stderr)
    misra_data = load_json(standard_path, "Extracted text")
    
    # Get guideline text
    guideline_text = get_misra_text(misra_data, args.guideline)
    if not guideline_text:
        print(f"ERROR: Guideline '{args.guideline}' not found in MISRA extracted text", file=sys.stderr)
        sys.exit(1)
    
    print(f"Guideline: {args.guideline}", file=sys.stderr)
    print(f"Text length: {len(guideline_text)} chars", file=sys.stderr)
    
    # Load FLS chapters for metadata
    print("Loading FLS chapters...", file=sys.stderr)
    chapters = load_fls_chapters(root)
    sections_metadata, paragraphs_metadata = build_metadata_from_chapters(chapters)
    
    # Load embeddings
    section_ids, section_embeddings, _ = load_embeddings(
        get_fls_section_embeddings_path(root),
        "FLS section embeddings"
    )
    paragraph_ids, paragraph_embeddings, _ = load_embeddings(
        get_fls_paragraph_embeddings_path(root),
        "FLS paragraph embeddings"
    )
    
    # Load model and compute query embedding
    print("Loading embedding model...", file=sys.stderr)
    model = SentenceTransformer("all-mpnet-base-v2")
    
    print("Computing embedding for guideline text...", file=sys.stderr)
    query_embedding = model.encode(guideline_text, convert_to_numpy=True)
    
    # Search
    print("Searching sections...", file=sys.stderr)
    section_results = search_sections(
        query_embedding, section_ids, section_embeddings, sections_metadata, args.top
    )
    
    print("Searching paragraphs...", file=sys.stderr)
    paragraph_results = search_paragraphs(
        query_embedding, paragraph_ids, paragraph_embeddings, paragraphs_metadata, 
        args.top, args.threshold
    )
    
    # Compare with pre-computed if requested
    comparison = None
    if args.compare:
        precomputed_path = get_standard_similarity_path(root, args.standard)
        if precomputed_path.exists():
            precomputed = load_json(precomputed_path, "Pre-computed similarity")
            comparison = compare_with_precomputed(
                args.guideline, section_results, paragraph_results, precomputed
            )
    
    # Output
    output = {
        "guideline_id": args.guideline,
        "text_preview": guideline_text[:200] + "..." if len(guideline_text) > 200 else guideline_text,
        "top_section_matches": section_results,
        "top_paragraph_matches": paragraph_results,
    }
    
    if comparison:
        output["comparison_with_precomputed"] = comparison
    
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"RECOMPUTED SIMILARITY FOR: {args.guideline}")
        print(f"{'='*60}")
        
        print(f"\nGuideline text preview:")
        print(f"  {output['text_preview']}")
        
        print(f"\n--- TOP SECTION MATCHES ---")
        for i, r in enumerate(section_results[:10], 1):
            print(f"{i}. [{r['similarity']:.3f}] {r['fls_id']}: {r['title']}")
        
        print(f"\n--- TOP PARAGRAPH MATCHES ---")
        for i, r in enumerate(paragraph_results[:10], 1):
            print(f"{i}. [{r['similarity']:.3f}] {r['fls_id']} [{r['category_name']}]")
            print(f"   Section: {r['section_title']}")
            print(f"   Text: {r['text_preview'][:80]}...")
        
        if comparison:
            print(f"\n--- COMPARISON WITH PRE-COMPUTED ---")
            print(f"Sections only in new results: {len(comparison['sections_only_in_new'])}")
            for fls_id in comparison['sections_only_in_new'][:5]:
                print(f"  + {fls_id}")
            print(f"Sections only in pre-computed: {len(comparison['sections_only_in_precomputed'])}")
            for fls_id in comparison['sections_only_in_precomputed'][:5]:
                print(f"  - {fls_id}")
    
    print(f"\nFound {len(section_results)} section matches, {len(paragraph_results)} paragraph matches.", file=sys.stderr)


if __name__ == "__main__":
    main()
