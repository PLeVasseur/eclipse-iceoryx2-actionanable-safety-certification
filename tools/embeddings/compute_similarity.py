#!/usr/bin/env python3
"""
Compute similarity between MISRA guidelines and FLS sections/paragraphs.

This script:
1. Loads pre-computed embeddings for MISRA and FLS (sections + paragraphs)
2. Computes cosine similarity matrices at both levels
3. For each MISRA guideline, finds:
   - Top-N most similar FLS sections (coarse matching)
   - Top-N most similar FLS paragraphs (fine-grained matching)
4. Identifies "missing siblings" when partial section matches occur
5. Saves results for use in verification and review

Usage:
    uv run python tools/embeddings/compute_similarity.py [--top-n N] [--para-top-n N]

Options:
    --top-n N         Number of top similar FLS sections (default: 20)
    --para-top-n N    Number of top similar FLS paragraphs (default: 30)
    --para-threshold  Also include all paragraphs above this score (default: 0.5)

Output:
    embeddings/similarity/misra_c_to_fls.json
"""

import argparse
import json
import pickle
from datetime import date
from pathlib import Path

import numpy as np


# Category code to human-readable name mapping
CATEGORY_NAMES = {
    0: "section",
    -1: "general",
    -2: "legality_rules",
    -3: "dynamic_semantics",
    -4: "undefined_behavior",
    -5: "implementation_requirements",
    -6: "implementation_permissions",
    -7: "examples",
    -8: "syntax",
}


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def load_embeddings(path: Path) -> dict:
    """Load embeddings from pickle file."""
    with open(path, 'rb') as f:
        return pickle.load(f)


def load_fls_sections(project_root: Path) -> dict:
    """
    Load FLS sections metadata for sibling detection.
    
    Loads all chapter files via index.json and builds a lookup dict.
    """
    fls_dir = project_root / "embeddings" / "fls"
    index_path = fls_dir / "index.json"
    
    if not index_path.exists():
        raise FileNotFoundError(
            f"FLS index not found at {index_path}. "
            "Run extract_fls_content.py first."
        )
    
    with open(index_path, encoding='utf-8') as f:
        index = json.load(f)
    
    # Build lookup by FLS ID across all chapters
    sections_by_id = {}
    for chapter_info in index['chapters']:
        chapter_file = fls_dir / chapter_info['file']
        if not chapter_file.exists():
            continue
        
        with open(chapter_file, encoding='utf-8') as f:
            chapter_data = json.load(f)
        
        for section in chapter_data['sections']:
            sections_by_id[section['fls_id']] = section
    
    return sections_by_id


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between two sets of vectors.
    a: (m, d) matrix
    b: (n, d) matrix
    Returns: (m, n) similarity matrix
    """
    # Normalize vectors
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    
    # Compute dot product
    return np.dot(a_norm, b_norm.T)


def find_top_similar_sections(
    similarity_matrix: np.ndarray, 
    misra_ids: list[str],
    fls_ids: list[str],
    fls_sections: dict,
    top_n: int = 20
) -> dict:
    """
    Find top-N most similar FLS sections for each MISRA guideline.
    Returns dict mapping misra_id -> list of match dicts.
    """
    results = {}
    
    for i, misra_id in enumerate(misra_ids):
        sims = similarity_matrix[i]
        top_indices = np.argsort(sims)[::-1][:top_n]
        
        top_matches = []
        for idx in top_indices:
            fls_id = fls_ids[idx]
            score = float(sims[idx])
            section = fls_sections.get(fls_id, {})
            
            top_matches.append({
                'fls_id': fls_id,
                'similarity': round(score, 4),
                'title': section.get('title', ''),
                'category': section.get('category', 0),
            })
        
        results[misra_id] = top_matches
    
    return results


def find_top_similar_paragraphs(
    similarity_matrix: np.ndarray, 
    misra_ids: list[str],
    para_ids: list[str],
    para_metadata: dict,
    top_n: int = 30,
    threshold: float = 0.5
) -> dict:
    """
    Find top-N most similar FLS paragraphs for each MISRA guideline.
    Also includes any paragraphs above the threshold even if not in top-N.
    
    Returns dict mapping misra_id -> list of match dicts.
    """
    results = {}
    
    for i, misra_id in enumerate(misra_ids):
        sims = similarity_matrix[i]
        
        # Get indices sorted by similarity (descending)
        sorted_indices = np.argsort(sims)[::-1]
        
        # Take top-N
        top_indices = set(sorted_indices[:top_n].tolist())
        
        # Also include any above threshold
        above_threshold = set(np.where(sims >= threshold)[0].tolist())
        
        # Union of both sets
        include_indices = top_indices | above_threshold
        
        # Sort by score for final output
        include_indices = sorted(include_indices, key=lambda idx: sims[idx], reverse=True)
        
        top_matches = []
        for idx in include_indices:
            para_id = para_ids[idx]
            score = float(sims[idx])
            meta = para_metadata.get(para_id, {})
            
            # Truncate text for preview
            text = meta.get('text', '')
            text_preview = text[:100] + '...' if len(text) > 100 else text
            
            top_matches.append({
                'fls_id': para_id,
                'similarity': round(score, 4),
                'text_preview': text_preview,
                'section_fls_id': meta.get('section_fls_id', ''),
                'section_title': meta.get('section_title', ''),
                'category': meta.get('category', 0),
                'category_name': meta.get('category_name', ''),
            })
        
        results[misra_id] = top_matches
    
    return results


def find_missing_siblings(
    top_matches: list[dict],
    fls_sections: dict,
    similarity_threshold: float = 0.3
) -> list[dict]:
    """
    Find "missing siblings" - FLS sections that are siblings of matched sections
    but weren't in the top matches.
    
    Returns list of flagged siblings with their context.
    """
    # Collect all matched FLS IDs above threshold
    matched_ids = {m['fls_id'] for m in top_matches if m['similarity'] >= similarity_threshold}
    
    # For each matched ID, find siblings that weren't matched
    missing = []
    checked_parents = set()
    
    for fls_id in matched_ids:
        section = fls_sections.get(fls_id)
        if not section:
            continue
        
        parent_id = section.get('parent_fls_id')
        if not parent_id or parent_id in checked_parents:
            continue
        
        checked_parents.add(parent_id)
        
        # Get all siblings
        sibling_ids = section.get('sibling_fls_ids', [])
        
        # Find siblings not in matches
        for sib_id in sibling_ids:
            if sib_id not in matched_ids:
                sib_section = fls_sections.get(sib_id)
                if sib_section:
                    missing.append({
                        'fls_id': sib_id,
                        'title': sib_section.get('title', ''),
                        'parent_fls_id': parent_id,
                        'reason': f"Sibling of matched {fls_id}"
                    })
    
    return missing


def main():
    parser = argparse.ArgumentParser(description='Compute MISRA-FLS similarity')
    parser.add_argument('--top-n', type=int, default=20,
                       help='Number of top similar FLS sections')
    parser.add_argument('--para-top-n', type=int, default=30,
                       help='Number of top similar FLS paragraphs')
    parser.add_argument('--para-threshold', type=float, default=0.5,
                       help='Also include paragraphs above this similarity score')
    args = parser.parse_args()
    
    project_root = get_project_root()
    
    # =========================================================================
    # Load Embeddings
    # =========================================================================
    print("Loading embeddings...")
    
    misra_emb_path = project_root / "embeddings" / "misra_c" / "embeddings.pkl"
    fls_section_emb_path = project_root / "embeddings" / "fls" / "embeddings.pkl"
    fls_para_emb_path = project_root / "embeddings" / "fls" / "paragraph_embeddings.pkl"
    
    if not misra_emb_path.exists():
        print(f"Error: MISRA embeddings not found at {misra_emb_path}")
        print("Run generate_embeddings.py first.")
        return 1
    
    if not fls_section_emb_path.exists():
        print(f"Error: FLS section embeddings not found at {fls_section_emb_path}")
        print("Run generate_embeddings.py first.")
        return 1
    
    misra_data = load_embeddings(misra_emb_path)
    fls_section_data = load_embeddings(fls_section_emb_path)
    
    print(f"  MISRA: {misra_data['num_items']} items, dim={misra_data['embedding_dim']}")
    print(f"  FLS sections: {fls_section_data['num_items']} items, dim={fls_section_data['embedding_dim']}")
    
    # Check for paragraph embeddings
    has_paragraphs = fls_para_emb_path.exists()
    if has_paragraphs:
        fls_para_data = load_embeddings(fls_para_emb_path)
        print(f"  FLS paragraphs: {fls_para_data['num_items']} items, dim={fls_para_data['embedding_dim']}")
        print(f"    Categories included: {fls_para_data.get('categories_included', 'unknown')}")
    else:
        print("  FLS paragraphs: not found (skipping paragraph-level matching)")
        fls_para_data = None
    
    # =========================================================================
    # Load FLS Sections Metadata
    # =========================================================================
    print("\nLoading FLS sections metadata...")
    fls_sections = load_fls_sections(project_root)
    print(f"  Loaded {len(fls_sections)} sections")
    
    # Extract arrays
    misra_ids = misra_data['data']['ids']
    misra_embeddings = misra_data['data']['embeddings']
    fls_section_ids = fls_section_data['data']['ids']
    fls_section_embeddings = fls_section_data['data']['embeddings']
    
    # =========================================================================
    # Section-Level Similarity
    # =========================================================================
    print("\n" + "="*60)
    print("Section-Level Similarity (Coarse)")
    print("="*60)
    
    print("\nComputing section similarity matrix...")
    section_sim_matrix = cosine_similarity(misra_embeddings, fls_section_embeddings)
    print(f"  Matrix shape: {section_sim_matrix.shape}")
    
    print(f"\nFinding top {args.top_n} section matches for each MISRA guideline...")
    section_matches = find_top_similar_sections(
        section_sim_matrix, misra_ids, fls_section_ids, fls_sections, top_n=args.top_n
    )
    
    # Find missing siblings for each guideline
    print("Finding missing siblings...")
    total_missing = 0
    section_results = {}
    
    for misra_id, matches in section_matches.items():
        missing = find_missing_siblings(matches, fls_sections)
        total_missing += len(missing)
        
        section_results[misra_id] = {
            'top_matches': matches,
            'missing_siblings': missing
        }
    
    print(f"  Total missing siblings flagged: {total_missing}")
    
    # =========================================================================
    # Paragraph-Level Similarity
    # =========================================================================
    para_results = {}
    para_stats = {}
    
    if has_paragraphs and fls_para_data is not None:
        print("\n" + "="*60)
        print("Paragraph-Level Similarity (Fine-grained)")
        print("="*60)
        
        para_ids = fls_para_data['data']['ids']
        para_embeddings = fls_para_data['data']['embeddings']
        para_metadata = fls_para_data.get('metadata', {})
        
        print("\nComputing paragraph similarity matrix...")
        para_sim_matrix = cosine_similarity(misra_embeddings, para_embeddings)
        print(f"  Matrix shape: {para_sim_matrix.shape}")
        
        print(f"\nFinding top {args.para_top_n} paragraph matches (+ any ≥{args.para_threshold})...")
        para_matches = find_top_similar_paragraphs(
            para_sim_matrix, misra_ids, para_ids, para_metadata,
            top_n=args.para_top_n, threshold=args.para_threshold
        )
        
        # Build para_results keyed by misra_id
        for misra_id, matches in para_matches.items():
            para_results[misra_id] = matches
        
        # Compute paragraph statistics
        total_para_matches = sum(len(m) for m in para_results.values())
        avg_para_matches = total_para_matches / len(misra_ids) if misra_ids else 0
        
        # Count by category
        category_counts = {}
        for matches in para_results.values():
            for m in matches:
                cat = m.get('category_name', 'unknown')
                category_counts[cat] = category_counts.get(cat, 0) + 1
        
        para_stats = {
            'paragraph_embeddings': fls_para_data['num_items'] if fls_para_data else 0,
            'categories_included': fls_para_data.get('categories_included', []) if fls_para_data else [],
            'avg_paragraph_matches_per_guideline': round(avg_para_matches, 1),
            'paragraph_matches_by_category': category_counts,
        }
        
        print(f"  Total paragraph matches: {total_para_matches}")
        print(f"  Avg per guideline: {avg_para_matches:.1f}")
    
    # =========================================================================
    # Merge Results and Save
    # =========================================================================
    print("\n" + "="*60)
    print("Saving Results")
    print("="*60)
    
    # Merge section and paragraph results
    results = {}
    for misra_id in misra_ids:
        results[misra_id] = {
            'top_matches': section_results[misra_id]['top_matches'],
            'missing_siblings': section_results[misra_id]['missing_siblings'],
        }
        if misra_id in para_results:
            results[misra_id]['top_paragraph_matches'] = para_results[misra_id]
    
    # Compute statistics
    avg_top_section_score = np.mean([
        r['top_matches'][0]['similarity'] for r in results.values() if r['top_matches']
    ])
    
    avg_top_para_score = None
    if para_results:
        scores = [
            r['top_paragraph_matches'][0]['similarity'] 
            for r in results.values() 
            if r.get('top_paragraph_matches')
        ]
        if scores:
            avg_top_para_score = np.mean(scores)
    
    # Create output
    output = {
        'generated_date': str(date.today()),
        'model': misra_data['model'],
        'parameters': {
            'section_top_n': args.top_n,
            'paragraph_top_n': args.para_top_n,
            'paragraph_threshold': args.para_threshold,
        },
        'statistics': {
            'misra_guidelines': len(misra_ids),
            'fls_sections': len(fls_section_ids),
            'avg_top_section_similarity': round(avg_top_section_score, 4),
            'total_missing_siblings': total_missing,
            **para_stats,
        },
        'results': results
    }
    
    if avg_top_para_score is not None:
        output['statistics']['avg_top_paragraph_similarity'] = round(avg_top_para_score, 4)
    
    # Save output
    output_path = project_root / "embeddings" / "similarity" / "misra_c_to_fls.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved to: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
    
    # =========================================================================
    # Show Sample Results
    # =========================================================================
    print("\n" + "="*60)
    print("Sample Results")
    print("="*60)
    
    sample_ids = ['Dir 4.1', 'Rule 11.1', 'Rule 18.1']
    for misra_id in sample_ids:
        if misra_id in results:
            r = results[misra_id]
            print(f"\n{misra_id}:")
            
            print(f"  Top 3 section matches:")
            for m in r['top_matches'][:3]:
                title = m.get('title', '')[:35]
                print(f"    {m['fls_id']}: {m['similarity']:.3f} - {title}...")
            
            if r.get('top_paragraph_matches'):
                print(f"  Top 3 paragraph matches:")
                for m in r['top_paragraph_matches'][:3]:
                    cat = m.get('category_name', '')
                    preview = m.get('text_preview', '')[:40]
                    print(f"    {m['fls_id']}: {m['similarity']:.3f} [{cat}] {preview}...")
            
            if r['missing_siblings']:
                print(f"  Missing siblings: {len(r['missing_siblings'])}")
    
    return 0


if __name__ == "__main__":
    exit(main())
