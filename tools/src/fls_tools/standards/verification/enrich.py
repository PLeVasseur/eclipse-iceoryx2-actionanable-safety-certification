#!/usr/bin/env python3
"""
enrich_fls_matches.py - Find additional FLS sections for guideline verification

This tool helps identify FLS sections that may have been missed during initial
verification by casting a broad semantic search net and drilling down into
relevant sections.

Usage:
    # Enrich a single guideline
    uv run enrich-fls-matches --guideline "Rule 22.8"
    
    # Enrich with custom search query
    uv run enrich-fls-matches --guideline "Rule 22.8" --query "error handling"
    
    # Prioritize specific chapters
    uv run enrich-fls-matches --guideline "Rule 22.8" --chapters 16,6
    
    # Enrich multiple guidelines
    uv run enrich-fls-matches --guidelines "Rule 22.8,Rule 22.9,Rule 22.10"
    
    # Save output to file
    uv run enrich-fls-matches --guideline "Rule 22.8" --output enrichment.json
    
    # Use semantic filtering for paragraphs
    uv run enrich-fls-matches --guideline "Rule 22.8" --semantic-filter-only
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
    get_fls_section_embeddings_path,
    get_fls_paragraph_embeddings_path,
    get_misra_c_extracted_text_path,
    get_concept_to_fls_path,
    get_verification_cache_dir,
    CATEGORY_NAMES,
)


# Lower thresholds for broader search
ENRICH_SECTION_THRESHOLD = 0.35
ENRICH_PARAGRAPH_THRESHOLD = 0.30


def load_embeddings(embeddings_path: Path) -> tuple[list[str], np.ndarray, dict]:
    """Load embeddings from pickle file."""
    if not embeddings_path.exists():
        print(f"ERROR: Embeddings not found: {embeddings_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(embeddings_path, "rb") as f:
        data = pickle.load(f)
    
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


def load_misra_extracted_text(root: Path) -> dict:
    """Load MISRA extracted text for rationale/amplification."""
    path = get_misra_c_extracted_text_path(root)
    if not path.exists():
        return {}
    
    with open(path) as f:
        data = json.load(f)
    
    # Build lookup by guideline_id
    guidelines = data.get("guidelines", [])
    lookup = {}
    for g in guidelines:
        gid = g.get("guideline_id")
        if gid:
            lookup[gid] = g
    
    return lookup


def load_concept_to_fls(root: Path) -> dict:
    """Load concept to FLS ID mappings."""
    path = get_concept_to_fls_path(root)
    if not path.exists():
        return {}
    
    with open(path) as f:
        return json.load(f)


def load_batch_report(batch_report_path: Path) -> dict | None:
    """Load a batch report for current matches."""
    if not batch_report_path.exists():
        return None
    
    with open(batch_report_path) as f:
        return json.load(f)


def get_guideline_from_batch_report(batch_report: dict, guideline_id: str) -> dict | None:
    """Get a specific guideline from a batch report."""
    for g in batch_report.get("guidelines", []):
        if g.get("guideline_id") == guideline_id:
            return g
    return None


def cosine_similarity_batch(query: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query and all embeddings."""
    query_norm = query / np.linalg.norm(query)
    embed_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    return np.dot(embed_norms, query_norm)


def search_sections(
    query_embedding: np.ndarray,
    ids: list[str],
    embeddings: np.ndarray,
    sections_metadata: dict,
    threshold: float,
    max_results: int,
    prioritized_chapters: list[int] | None = None,
) -> list[dict]:
    """Search section-level embeddings with optional chapter prioritization."""
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    similarities = cosine_similarity_batch(query_embedding, embeddings)
    
    results = []
    for idx, (fls_id, similarity) in enumerate(zip(ids, similarities)):
        if similarity < threshold:
            continue
        
        section = sections_metadata.get(fls_id, {})
        chapter = section.get("chapter")
        
        # Apply chapter boost if prioritized
        boosted_score = float(similarity)
        if prioritized_chapters and chapter in prioritized_chapters:
            boosted_score += 0.1  # Boost prioritized chapters
        
        results.append({
            "fls_id": fls_id,
            "title": section.get("title", ""),
            "chapter": chapter,
            "similarity": float(similarity),
            "boosted_score": boosted_score,
            "prioritized": prioritized_chapters and chapter in prioritized_chapters,
        })
    
    # Sort by boosted score
    results.sort(key=lambda x: x["boosted_score"], reverse=True)
    return results[:max_results]


def search_paragraphs(
    query_embedding: np.ndarray,
    ids: list[str],
    embeddings: np.ndarray,
    paragraphs_metadata: dict,
    threshold: float,
    max_results: int,
) -> list[dict]:
    """Search paragraph-level embeddings."""
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    similarities = cosine_similarity_batch(query_embedding, embeddings)
    
    results = []
    for idx, (fls_id, similarity) in enumerate(zip(ids, similarities)):
        if similarity < threshold:
            continue
        
        meta = paragraphs_metadata.get(fls_id, {})
        category = meta.get("category", 0)
        
        results.append({
            "fls_id": fls_id,
            "text": meta.get("text", ""),
            "section_fls_id": meta.get("section_fls_id", ""),
            "section_title": meta.get("section_title", ""),
            "category": category,
            "category_name": CATEGORY_NAMES.get(category, f"unknown_{category}"),
            "chapter": meta.get("chapter"),
            "similarity": float(similarity),
        })
    
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:max_results]


def get_section_with_paragraphs(
    chapters: dict,
    fls_id: str,
    query_embedding: np.ndarray | None = None,
    model: SentenceTransformer | None = None,
    semantic_filter: bool = False,
) -> dict | None:
    """Get full section content with all paragraphs, optionally scored by similarity."""
    for chapter_num, chapter in chapters.items():
        for section in chapter.get("sections", []):
            if section.get("fls_id") == fls_id:
                result = {
                    "fls_id": fls_id,
                    "title": section.get("title"),
                    "chapter": chapter_num,
                    "content": section.get("content", ""),
                    "paragraphs": {},
                }
                
                # Extract all paragraphs from rubrics
                for cat_key, rubric_data in section.get("rubrics", {}).items():
                    category = int(cat_key)
                    category_name = CATEGORY_NAMES.get(category, f"unknown_{category}")
                    
                    paragraphs = {}
                    for para_id, para_text in rubric_data.get("paragraphs", {}).items():
                        para_entry = {
                            "text": para_text,
                            "similarity": None,
                        }
                        
                        # Score paragraph if query embedding provided
                        if query_embedding is not None and model is not None:
                            para_embedding = model.encode(para_text, convert_to_numpy=True)
                            similarity = float(np.dot(
                                query_embedding / np.linalg.norm(query_embedding),
                                para_embedding / np.linalg.norm(para_embedding)
                            ))
                            para_entry["similarity"] = similarity
                        
                        # Include paragraph unless semantic filter is on and similarity is too low
                        if semantic_filter and para_entry["similarity"] is not None:
                            if para_entry["similarity"] >= ENRICH_PARAGRAPH_THRESHOLD:
                                paragraphs[para_id] = para_entry
                        else:
                            paragraphs[para_id] = para_entry
                    
                    if paragraphs:
                        result["paragraphs"][category_name] = paragraphs
                
                return result
    
    return None


def extract_search_queries(
    guideline_id: str,
    misra_text: dict,
    custom_query: str | None = None,
) -> list[str]:
    """Extract search queries from MISRA text and custom input."""
    queries = []
    
    # Add custom query first if provided
    if custom_query:
        queries.append(custom_query)
    
    # Get MISRA extracted text
    guideline_data = misra_text.get(guideline_id, {})
    
    # Use pre-computed search queries if available
    # These can be either strings or dicts with a "text" field
    if guideline_data.get("search_queries"):
        for sq in guideline_data["search_queries"]:
            if isinstance(sq, str):
                queries.append(sq)
            elif isinstance(sq, dict) and sq.get("text"):
                queries.append(sq["text"])
    
    # Use title
    if guideline_data.get("title"):
        queries.append(guideline_data["title"])
    
    # Use rationale (first 500 chars)
    if guideline_data.get("rationale"):
        queries.append(guideline_data["rationale"][:500])
    
    # Use amplification (first 500 chars)
    if guideline_data.get("amplification"):
        queries.append(guideline_data["amplification"][:500])
    
    # Deduplicate while preserving order (convert to string for hashing)
    seen = set()
    unique_queries = []
    for q in queries:
        if q and isinstance(q, str) and q not in seen:
            seen.add(q)
            unique_queries.append(q)
    
    return unique_queries


def check_concept_matches(
    guideline_id: str,
    misra_text: dict,
    concept_to_fls: dict,
) -> list[dict]:
    """Check for concept-based FLS matches."""
    matches = []
    
    guideline_data = misra_text.get(guideline_id, {})
    matched_concepts = guideline_data.get("matched_concepts", [])
    
    for concept in matched_concepts:
        if concept in concept_to_fls:
            fls_ids = concept_to_fls[concept].get("fls_ids", [])
            for fls_id in fls_ids:
                matches.append({
                    "fls_id": fls_id,
                    "source": "concept_match",
                    "concept": concept,
                })
    
    return matches


def enrich_guideline(
    guideline_id: str,
    root: Path,
    model: SentenceTransformer,
    chapters: dict,
    sections_metadata: dict,
    paragraphs_metadata: dict,
    section_ids: list[str],
    section_embeddings: np.ndarray,
    paragraph_ids: list[str],
    paragraph_embeddings: np.ndarray,
    misra_text: dict,
    concept_to_fls: dict,
    custom_query: str | None = None,
    prioritized_chapters: list[int] | None = None,
    max_sections: int = 15,
    semantic_filter: bool = False,
    current_matches: list[dict] | None = None,
) -> dict:
    """
    Enrich a single guideline with additional FLS matches.
    
    Returns a structured report of candidate sections and recommended additions.
    """
    # Get MISRA data
    guideline_data = misra_text.get(guideline_id, {})
    
    # Extract search queries
    queries = extract_search_queries(guideline_id, misra_text, custom_query)
    
    # Check concept-based matches
    concept_matches = check_concept_matches(guideline_id, misra_text, concept_to_fls)
    
    # Perform semantic search with each query and aggregate results
    all_section_matches = {}
    all_paragraph_matches = {}
    
    for query in queries[:5]:  # Limit to top 5 queries
        query_embedding = model.encode(query, convert_to_numpy=True)
        
        # Search sections
        section_results = search_sections(
            query_embedding,
            section_ids,
            section_embeddings,
            sections_metadata,
            ENRICH_SECTION_THRESHOLD,
            max_sections,
            prioritized_chapters,
        )
        
        for r in section_results:
            fls_id = r["fls_id"]
            if fls_id not in all_section_matches:
                all_section_matches[fls_id] = r
                all_section_matches[fls_id]["matched_queries"] = [query[:100]]
            else:
                # Take the higher score
                if r["boosted_score"] > all_section_matches[fls_id]["boosted_score"]:
                    all_section_matches[fls_id]["boosted_score"] = r["boosted_score"]
                    all_section_matches[fls_id]["similarity"] = r["similarity"]
                all_section_matches[fls_id]["matched_queries"].append(query[:100])
        
        # Search paragraphs
        paragraph_results = search_paragraphs(
            query_embedding,
            paragraph_ids,
            paragraph_embeddings,
            paragraphs_metadata,
            ENRICH_PARAGRAPH_THRESHOLD,
            max_sections * 2,
        )
        
        for r in paragraph_results:
            fls_id = r["fls_id"]
            if fls_id not in all_paragraph_matches:
                all_paragraph_matches[fls_id] = r
    
    # Add concept-matched sections that weren't found by semantic search
    for cm in concept_matches:
        fls_id = cm["fls_id"]
        if fls_id not in all_section_matches:
            # Get section info
            section_info = sections_metadata.get(fls_id, {})
            all_section_matches[fls_id] = {
                "fls_id": fls_id,
                "title": section_info.get("title", ""),
                "chapter": section_info.get("chapter"),
                "similarity": 0.4,  # Base score for concept matches
                "boosted_score": 0.4,
                "prioritized": False,
                "matched_queries": [],
                "source": "concept_match",
                "concept": cm["concept"],
            }
    
    # Sort and limit results
    sorted_sections = sorted(
        all_section_matches.values(),
        key=lambda x: x["boosted_score"],
        reverse=True
    )[:max_sections]
    
    # Drill down into top sections
    candidate_sections = []
    
    # Use the combined query for paragraph scoring
    combined_query = " ".join(queries[:3])
    combined_embedding = model.encode(combined_query, convert_to_numpy=True)
    
    for section_match in sorted_sections:
        section_detail = get_section_with_paragraphs(
            chapters,
            section_match["fls_id"],
            combined_embedding,
            model,
            semantic_filter,
        )
        
        if section_detail:
            candidate_sections.append({
                **section_match,
                "paragraphs": section_detail.get("paragraphs", {}),
            })
    
    # Build current matches set for comparison
    current_fls_ids = set()
    if current_matches:
        for m in current_matches:
            current_fls_ids.add(m.get("fls_id", ""))
    
    # Identify recommended additions (not already in current matches)
    recommended = []
    for cs in candidate_sections:
        if cs["fls_id"] not in current_fls_ids:
            # Get the most relevant paragraphs
            key_paragraphs = []
            for cat_name, paras in cs.get("paragraphs", {}).items():
                for para_id, para_data in paras.items():
                    if para_data.get("similarity") and para_data["similarity"] >= ENRICH_PARAGRAPH_THRESHOLD:
                        key_paragraphs.append({
                            "para_id": para_id,
                            "category": cat_name,
                            "similarity": para_data["similarity"],
                            "text_preview": para_data["text"][:200],
                        })
            
            key_paragraphs.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            
            recommended.append({
                "fls_id": cs["fls_id"],
                "fls_title": cs["title"],
                "chapter": cs["chapter"],
                "score": cs["boosted_score"],
                "matched_queries": cs.get("matched_queries", []),
                "source": cs.get("source", "semantic_search"),
                "concept": cs.get("concept"),
                "key_paragraphs": key_paragraphs[:5],
            })
    
    return {
        "guideline_id": guideline_id,
        "guideline_title": guideline_data.get("title", ""),
        "search_context": {
            "misra_rationale": guideline_data.get("rationale", "")[:500] if guideline_data.get("rationale") else None,
            "misra_amplification": guideline_data.get("amplification", "")[:500] if guideline_data.get("amplification") else None,
            "search_queries_used": queries[:5],
            "prioritized_chapters": prioritized_chapters,
        },
        "current_matches_count": len(current_matches) if current_matches else 0,
        "current_fls_ids": list(current_fls_ids),
        "candidate_sections": candidate_sections,
        "recommended_additions": recommended,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Find additional FLS sections for guideline verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Enrich a single guideline
    uv run enrich-fls-matches --guideline "Rule 22.8"
    
    # Add custom search terms
    uv run enrich-fls-matches --guideline "Rule 22.8" --query "error handling Result"
    
    # Prioritize specific chapters
    uv run enrich-fls-matches --guideline "Rule 22.8" --chapters 16,6
    
    # Multiple guidelines
    uv run enrich-fls-matches --guidelines "Rule 22.8,Rule 22.9"
        """
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--guideline", "-g",
        type=str,
        help="Single guideline ID to enrich (e.g., 'Rule 22.8')"
    )
    input_group.add_argument(
        "--guidelines",
        type=str,
        help="Comma-separated list of guideline IDs"
    )
    
    # Search options
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Additional search query to supplement MISRA text"
    )
    parser.add_argument(
        "--chapters", "-c",
        type=str,
        default=None,
        help="Comma-separated chapter numbers to prioritize (e.g., '16,6,17')"
    )
    parser.add_argument(
        "--max-sections",
        type=int,
        default=15,
        help="Maximum candidate sections to return (default: 15)"
    )
    
    # Filtering options
    parser.add_argument(
        "--semantic-filter-only",
        action="store_true",
        help="Only show paragraphs that meet semantic similarity threshold"
    )
    
    # Context options
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to batch report for current match context"
    )
    
    # Output options
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path (default: stdout)"
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Parse guideline IDs
    if args.guideline:
        guideline_ids = [args.guideline]
    else:
        guideline_ids = [g.strip() for g in args.guidelines.split(",")]
    
    # Parse prioritized chapters
    prioritized_chapters = None
    if args.chapters:
        prioritized_chapters = [int(c.strip()) for c in args.chapters.split(",")]
    
    # Load resources
    print("Loading FLS chapters...", file=sys.stderr)
    chapters = load_fls_chapters(root)
    
    # Build metadata lookups
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
            for cat_key, rubric_data in section.get("rubrics", {}).items():
                for para_id, para_text in rubric_data.get("paragraphs", {}).items():
                    paragraphs_metadata[para_id] = {
                        "text": para_text,
                        "section_fls_id": fls_id,
                        "section_title": section.get("title", ""),
                        "category": int(cat_key),
                        "chapter": chapter_num,
                    }
    
    print("Loading embeddings...", file=sys.stderr)
    section_ids, section_embeddings, _ = load_embeddings(get_fls_section_embeddings_path(root))
    paragraph_ids, paragraph_embeddings, _ = load_embeddings(get_fls_paragraph_embeddings_path(root))
    
    print("Loading MISRA extracted text...", file=sys.stderr)
    misra_text = load_misra_extracted_text(root)
    
    print("Loading concept mappings...", file=sys.stderr)
    concept_to_fls = load_concept_to_fls(root)
    
    print("Loading embedding model...", file=sys.stderr)
    model = SentenceTransformer("all-mpnet-base-v2")
    
    # Load batch report if provided
    batch_report = None
    if args.batch_report:
        batch_report_path = Path(args.batch_report)
        if not batch_report_path.is_absolute():
            batch_report_path = root / batch_report_path
        batch_report = load_batch_report(batch_report_path)
    
    # Process each guideline
    results = []
    for gid in guideline_ids:
        print(f"Enriching {gid}...", file=sys.stderr)
        
        # Get current matches from batch report if available
        current_matches = None
        if batch_report:
            guideline = get_guideline_from_batch_report(batch_report, gid)
            if guideline:
                vd = guideline.get("verification_decision", {})
                current_matches = vd.get("accepted_matches", [])
        
        result = enrich_guideline(
            gid,
            root,
            model,
            chapters,
            sections_metadata,
            paragraphs_metadata,
            section_ids,
            section_embeddings,
            paragraph_ids,
            paragraph_embeddings,
            misra_text,
            concept_to_fls,
            args.query,
            prioritized_chapters,
            args.max_sections,
            args.semantic_filter_only,
            current_matches,
        )
        results.append(result)
    
    # Output
    output_data = results[0] if len(results) == 1 else {"guidelines": results}
    output_json = json.dumps(output_data, indent=2)
    
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(output_json)
        print(f"Output written to {output_path}", file=sys.stderr)
    else:
        print(output_json)
    
    print(f"\nProcessed {len(results)} guideline(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
