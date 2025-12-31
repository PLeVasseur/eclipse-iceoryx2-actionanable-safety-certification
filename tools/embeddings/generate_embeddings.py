#!/usr/bin/env python3
"""
Generate vector embeddings for MISRA C and FLS content.

This script uses sentence-transformers to create semantic embeddings that
enable similarity search between MISRA guidelines and FLS sections/paragraphs.

Two levels of FLS embeddings are generated:
1. Section-level (coarse): For initial discovery of relevant FLS areas
2. Paragraph-level (fine-grained): For precise matching to specific rules

Usage:
    uv run python tools/embeddings/generate_embeddings.py [--model MODEL]

Options:
    --model MODEL              Embedding model name (default: all-mpnet-base-v2)
    --no-paragraphs            Skip paragraph embedding generation
    --paragraph-categories     Comma-separated category codes to include
                               (default: -1,-2,-3,-4,-5,-6)

Input:
    cache/misra_c_extracted_text.json
    embeddings/fls/index.json (and chapter_NN.json files)

Output:
    embeddings/misra_c/embeddings.pkl
    embeddings/fls/embeddings.pkl           (section-level)
    embeddings/fls/paragraph_embeddings.pkl (paragraph-level)
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


def load_misra_text(project_root: Path) -> list[dict]:
    """Load MISRA extracted text from cache."""
    cache_path = project_root / "cache" / "misra_c_extracted_text.json"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"MISRA text not found at {cache_path}. "
            "Run extract_misra_text.py first."
        )
    with open(cache_path, encoding='utf-8') as f:
        data = json.load(f)
    return data['guidelines']


def load_fls_sections(project_root: Path) -> list[dict]:
    """
    Load FLS sections from chapter files via index.json.
    
    The FLS content is split into per-chapter JSON files for easier
    management. This function loads all chapters and concatenates sections.
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
    
    all_sections = []
    for chapter_info in index['chapters']:
        chapter_file = fls_dir / chapter_info['file']
        if not chapter_file.exists():
            print(f"  Warning: Chapter file not found: {chapter_file}")
            continue
        
        with open(chapter_file, encoding='utf-8') as f:
            chapter_data = json.load(f)
        
        all_sections.extend(chapter_data['sections'])
    
    return all_sections


def prepare_misra_texts(guidelines: list[dict]) -> list[tuple[str, str]]:
    """
    Prepare MISRA guidelines for embedding.
    Returns list of (guideline_id, text_to_embed).
    """
    texts = []
    for g in guidelines:
        gid = g['guideline_id']
        
        # Build comprehensive text for embedding
        parts = []
        
        # Title is important
        if g.get('title'):
            parts.append(f"Title: {g['title']}")
        
        # Rationale captures the intent
        if g.get('rationale'):
            parts.append(f"Rationale: {g['rationale']}")
        
        # Amplification provides details
        if g.get('amplification'):
            parts.append(f"Amplification: {g['amplification']}")
        
        # Category context
        if g.get('category'):
            parts.append(f"Category: {g['category']}")
        
        # If no specific parts, use full text
        if not parts and g.get('full_text'):
            parts.append(g['full_text'])
        
        text = '\n'.join(parts)
        
        # Skip if no meaningful text
        if len(text.strip()) < 20:
            text = g.get('title', gid)  # Fallback to title or ID
        
        texts.append((gid, text))
    
    return texts


def prepare_fls_section_texts(sections: list[dict]) -> list[tuple[str, str]]:
    """
    Prepare FLS sections for embedding (coarse-grained).
    Returns list of (fls_id, text_to_embed).
    """
    texts = []
    for s in sections:
        fls_id = s['fls_id']
        
        # Build text for embedding
        parts = []
        
        # Title
        if s.get('title'):
            parts.append(f"Title: {s['title']}")
        
        # Content
        if s.get('content'):
            # Truncate very long content
            content = s['content']
            if len(content) > 8000:
                content = content[:8000] + "..."
            parts.append(content)
        
        text = '\n'.join(parts)
        
        # Skip if no meaningful text
        if len(text.strip()) < 20:
            text = s.get('title', fls_id)
        
        texts.append((fls_id, text))
    
    return texts


def prepare_fls_paragraph_texts(
    sections: list[dict],
    include_categories: set[int]
) -> tuple[list[tuple[str, str]], dict[str, dict]]:
    """
    Prepare FLS paragraphs for embedding (fine-grained).
    
    Args:
        sections: List of FLS sections with rubrics
        include_categories: Set of category codes to include (e.g., {-1, -2, -3, -4, -5, -6})
    
    Returns:
        Tuple of:
        - List of (paragraph_fls_id, text_to_embed) tuples
        - Dict of metadata: paragraph_fls_id -> {section_fls_id, section_title, category, category_name}
    """
    texts = []
    metadata = {}
    
    for section in sections:
        section_fls_id = section['fls_id']
        section_title = section.get('title', '')
        
        rubrics = section.get('rubrics', {})
        
        for cat_code_str, rubric_data in rubrics.items():
            cat_code = int(cat_code_str)
            
            # Skip categories not in our include set
            if cat_code not in include_categories:
                continue
            
            cat_name = CATEGORY_NAMES.get(cat_code, f"unknown_{cat_code}")
            # Convert to human-readable format for embedding
            cat_display = cat_name.replace('_', ' ').title()
            
            paragraphs = rubric_data.get('paragraphs', {})
            
            for para_fls_id, para_text in paragraphs.items():
                # Build text with context for better semantic matching
                # Format: "Section: {title}\nCategory: {category}\n{paragraph_text}"
                text = f"Section: {section_title}\nCategory: {cat_display}\n{para_text}"
                
                texts.append((para_fls_id, text))
                
                metadata[para_fls_id] = {
                    'section_fls_id': section_fls_id,
                    'section_title': section_title,
                    'category': cat_code,
                    'category_name': cat_name,
                    'text': para_text,  # Store original text for preview
                }
    
    return texts, metadata


def generate_embeddings(texts: list[tuple[str, str]], model) -> dict:
    """
    Generate embeddings for a list of (id, text) pairs.
    Returns dict with ids, embeddings array, and id_to_index lookup.
    """
    ids = [t[0] for t in texts]
    text_content = [t[1] for t in texts]
    
    print(f"  Generating embeddings for {len(texts)} items...")
    embeddings = model.encode(text_content, show_progress_bar=True)
    
    result = {
        'ids': ids,
        'embeddings': embeddings,
        'id_to_index': {id_: i for i, id_ in enumerate(ids)}
    }
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Generate embeddings for MISRA and FLS')
    parser.add_argument('--model', default='all-mpnet-base-v2',
                       help='Sentence transformer model name')
    parser.add_argument('--no-paragraphs', action='store_true',
                       help='Skip paragraph embedding generation')
    parser.add_argument('--paragraph-categories', default='-1,-2,-3,-4,-5,-6',
                       help='Comma-separated category codes to include for paragraphs')
    args = parser.parse_args()
    
    # Parse category codes
    include_categories = set(int(c.strip()) for c in args.paragraph_categories.split(','))
    
    project_root = get_project_root()
    
    # Load sentence transformer model
    print(f"Loading model: {args.model}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    print(f"  Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")
    
    # =========================================================================
    # MISRA Embeddings
    # =========================================================================
    print("\n" + "="*60)
    print("MISRA Embeddings")
    print("="*60)
    
    print("\nLoading MISRA guidelines...")
    guidelines = load_misra_text(project_root)
    print(f"  Loaded {len(guidelines)} guidelines")
    
    misra_texts = prepare_misra_texts(guidelines)
    print(f"  Prepared {len(misra_texts)} texts for embedding")
    
    print("\nGenerating MISRA embeddings...")
    misra_embeddings = generate_embeddings(misra_texts, model)
    
    misra_output = project_root / "embeddings" / "misra_c" / "embeddings.pkl"
    misra_output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(misra_output, 'wb') as f:
        pickle.dump({
            'model': args.model,
            'generated_date': str(date.today()),
            'num_items': len(misra_embeddings['ids']),
            'embedding_dim': model.get_sentence_embedding_dimension(),
            'data': misra_embeddings
        }, f)
    print(f"  Saved to: {misra_output}")
    print(f"  File size: {misra_output.stat().st_size / 1024 / 1024:.2f} MB")
    
    # =========================================================================
    # FLS Section Embeddings (Coarse)
    # =========================================================================
    print("\n" + "="*60)
    print("FLS Section Embeddings (Coarse)")
    print("="*60)
    
    print("\nLoading FLS sections...")
    sections = load_fls_sections(project_root)
    print(f"  Loaded {len(sections)} sections")
    
    fls_section_texts = prepare_fls_section_texts(sections)
    print(f"  Prepared {len(fls_section_texts)} section texts for embedding")
    
    print("\nGenerating FLS section embeddings...")
    fls_section_embeddings = generate_embeddings(fls_section_texts, model)
    
    fls_section_output = project_root / "embeddings" / "fls" / "embeddings.pkl"
    fls_section_output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(fls_section_output, 'wb') as f:
        pickle.dump({
            'model': args.model,
            'generated_date': str(date.today()),
            'num_items': len(fls_section_embeddings['ids']),
            'embedding_dim': model.get_sentence_embedding_dimension(),
            'level': 'section',
            'data': fls_section_embeddings
        }, f)
    print(f"  Saved to: {fls_section_output}")
    print(f"  File size: {fls_section_output.stat().st_size / 1024 / 1024:.2f} MB")
    
    # =========================================================================
    # FLS Paragraph Embeddings (Fine-grained)
    # =========================================================================
    if not args.no_paragraphs:
        print("\n" + "="*60)
        print("FLS Paragraph Embeddings (Fine-grained)")
        print("="*60)
        
        cat_names = [CATEGORY_NAMES.get(c, str(c)) for c in sorted(include_categories)]
        print(f"\nIncluding categories: {', '.join(cat_names)}")
        
        fls_para_texts, para_metadata = prepare_fls_paragraph_texts(sections, include_categories)
        print(f"  Prepared {len(fls_para_texts)} paragraph texts for embedding")
        
        # Show breakdown by category
        cat_counts = {}
        for meta in para_metadata.values():
            cat = meta['category']
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        print("  Paragraphs by category:")
        for cat in sorted(cat_counts.keys()):
            print(f"    {CATEGORY_NAMES.get(cat, str(cat))}: {cat_counts[cat]}")
        
        print("\nGenerating FLS paragraph embeddings...")
        fls_para_embeddings = generate_embeddings(fls_para_texts, model)
        
        fls_para_output = project_root / "embeddings" / "fls" / "paragraph_embeddings.pkl"
        
        with open(fls_para_output, 'wb') as f:
            pickle.dump({
                'model': args.model,
                'generated_date': str(date.today()),
                'num_items': len(fls_para_embeddings['ids']),
                'embedding_dim': model.get_sentence_embedding_dimension(),
                'level': 'paragraph',
                'categories_included': sorted(include_categories),
                'data': fls_para_embeddings,
                'metadata': para_metadata,
            }, f)
        print(f"  Saved to: {fls_para_output}")
        print(f"  File size: {fls_para_output.stat().st_size / 1024 / 1024:.2f} MB")
    
    print("\n" + "="*60)
    print("Done!")
    print("="*60)
    return 0


if __name__ == "__main__":
    exit(main())
