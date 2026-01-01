#!/usr/bin/env python3
"""
search_fls.py - Semantic Search Across FLS Content

This script performs semantic search across all FLS section and paragraph embeddings
to find relevant content for a given query.

Usage:
    uv run python verification/search_fls.py --query "memory allocation" --top 10
    uv run python verification/search_fls.py --query "pointer arithmetic" --sections-only
    uv run python verification/search_fls.py --query "undefined behavior" --paragraphs-only
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
    get_fls_index_path,
    get_fls_section_embeddings_path,
    get_fls_paragraph_embeddings_path,
    CATEGORY_NAMES,
    generate_search_id,
)


def load_embeddings(embeddings_path: Path) -> tuple[list[str], np.ndarray, dict]:
    """
    Load embeddings from pickle file.
    
    Returns:
        ids: List of FLS IDs
        embeddings: numpy array of embeddings (N x D)
        id_to_index: Dict mapping FLS ID to index
    """
    if not embeddings_path.exists():
        print(f"ERROR: Embeddings not found: {embeddings_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(embeddings_path, "rb") as f:
        data = pickle.load(f)
    
    # Handle the actual embeddings format: {'data': {'ids': [...], 'embeddings': np.array, 'id_to_index': {...}}}
    embed_data = data.get("data", data)
    
    ids = embed_data.get("ids", [])
    embeddings = embed_data.get("embeddings", np.array([]))
    id_to_index = embed_data.get("id_to_index", {})
    
    return ids, embeddings, id_to_index


def load_fls_index(root: Path) -> dict:
    """Load FLS index for section titles."""
    index_path = get_fls_index_path(root)
    if not index_path.exists():
        return {}
    with open(index_path) as f:
        return json.load(f)


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
    
    # Compute similarities with all embeddings at once
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
            "similarity": similarity,
            "title": section.get("title", ""),
            "chapter": section.get("chapter"),
            "type": "section",
        })
    
    return results


def search_paragraphs(
    query_embedding: np.ndarray,
    ids: list[str],
    embeddings: np.ndarray,
    paragraphs_metadata: dict,
    top_n: int,
) -> list[dict]:
    """Search paragraph-level embeddings."""
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    # Compute similarities with all embeddings at once
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    embed_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    similarities = np.dot(embed_norms, query_norm)
    
    # Get top-n indices
    top_indices = np.argsort(similarities)[::-1][:top_n]
    
    results = []
    for idx in top_indices:
        fls_id = ids[idx]
        similarity = float(similarities[idx])
        
        # Get metadata from paragraphs_metadata if available
        meta = paragraphs_metadata.get(fls_id, {})
        category = meta.get("category", 0)
        category_name = CATEGORY_NAMES.get(category, f"unknown_{category}")
        
        results.append({
            "fls_id": fls_id,
            "similarity": similarity,
            "text_preview": meta.get("text", "")[:150],
            "section_fls_id": meta.get("section_fls_id", ""),
            "section_title": meta.get("section_title", ""),
            "category": category,
            "category_name": category_name,
            "chapter": meta.get("chapter"),
            "type": "paragraph",
        })
    
    return results


def get_section_content(chapters: dict, fls_id: str) -> dict | None:
    """Get full section content by FLS ID."""
    for chapter_num, chapter in chapters.items():
        for section in chapter.get("sections", []):
            if section.get("fls_id") == fls_id:
                return {
                    "fls_id": fls_id,
                    "title": section.get("title"),
                    "chapter": chapter_num,
                    "content": section.get("content", ""),
                    "rubrics": section.get("rubrics", {}),
                }
    return None


def format_results(results: list[dict], verbose: bool, chapters: dict) -> None:
    """Format and print search results."""
    if not results:
        print("No results found.")
        return
    
    for i, r in enumerate(results, 1):
        if r["type"] == "section":
            print(f"\n{i}. [{r['similarity']:.3f}] {r['fls_id']}: {r['title']}")
            print(f"   Chapter: {r['chapter']}")
            
            if verbose:
                content = get_section_content(chapters, r["fls_id"])
                if content and content.get("content"):
                    preview = content["content"][:300]
                    if len(content["content"]) > 300:
                        preview += "..."
                    print(f"   Content: {preview}")
        
        elif r["type"] == "paragraph":
            print(f"\n{i}. [{r['similarity']:.3f}] {r['fls_id']} [{r['category_name']}]")
            print(f"   Section: {r['section_fls_id']} - {r['section_title']}")
            print(f"   Chapter: {r['chapter']}")
            print(f"   Text: {r['text_preview']}...")


def main():
    parser = argparse.ArgumentParser(
        description="Semantic search across FLS content"
    )
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Search query text",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of results to return (default: 10)",
    )
    parser.add_argument(
        "--sections-only",
        action="store_true",
        help="Search only section-level embeddings",
    )
    parser.add_argument(
        "--paragraphs-only",
        action="store_true",
        help="Search only paragraph-level embeddings",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show more content in results",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    fls_dir = get_fls_dir(root)
    
    # Generate and print search ID for verification workflow tracking
    search_id = generate_search_id()
    print(f"Search ID: {search_id}")
    print()
    
    # Load FLS chapters for metadata
    print("Loading FLS chapters...", file=sys.stderr)
    chapters = load_fls_chapters(root)
    
    # Build metadata lookups from chapters
    sections_metadata = {}
    paragraphs_metadata = {}
    for chapter_num, chapter in chapters.items():
        for section in chapter.get("sections", []):
            fls_id = section.get("fls_id")
            if fls_id:
                sections_metadata[fls_id] = {
                    "title": section.get("title", ""),
                    "chapter": chapter_num,
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
    
    # Load model
    print("Loading embedding model...", file=sys.stderr)
    model = SentenceTransformer("all-mpnet-base-v2")
    
    # Generate query embedding
    print(f"Searching for: {args.query}", file=sys.stderr)
    query_embedding = model.encode(args.query, convert_to_numpy=True)
    
    results = []
    
    # Search sections
    if not args.paragraphs_only:
        section_embeddings_path = get_fls_section_embeddings_path(root)
        if section_embeddings_path.exists():
            print("Searching section embeddings...", file=sys.stderr)
            ids, embeddings, _ = load_embeddings(section_embeddings_path)
            section_results = search_sections(query_embedding, ids, embeddings, sections_metadata, args.top)
            results.extend(section_results)
    
    # Search paragraphs
    if not args.sections_only:
        paragraph_embeddings_path = get_fls_paragraph_embeddings_path(root)
        if paragraph_embeddings_path.exists():
            print("Searching paragraph embeddings...", file=sys.stderr)
            ids, embeddings, _ = load_embeddings(paragraph_embeddings_path)
            paragraph_results = search_paragraphs(query_embedding, ids, embeddings, paragraphs_metadata, args.top)
            results.extend(paragraph_results)
    
    # Sort combined results by similarity
    results.sort(key=lambda x: x["similarity"], reverse=True)
    results = results[:args.top]
    
    # Output (chapters already loaded for metadata)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"TOP {len(results)} RESULTS FOR: {args.query}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        format_results(results, args.verbose, chapters)
    
    print(f"\nFound {len(results)} results.", file=sys.stderr)


if __name__ == "__main__":
    main()
