"""
Common path utilities and constants.

This module provides the project root and common path helpers
used across all tools.
"""

from pathlib import Path


def get_project_root() -> Path:
    """
    Get the project root directory.
    
    Returns the root of the eclipse-iceoryx2-actionanable-safety-certification
    repository, regardless of which script is calling this function.
    
    Path: tools/src/fls_tools/shared/paths.py
    Levels: shared -> fls_tools -> src -> tools -> project_root
    """
    return Path(__file__).parent.parent.parent.parent.parent


def get_tools_dir(root: Path | None = None) -> Path:
    """Get the tools directory."""
    root = root or get_project_root()
    return root / "tools"


def get_data_dir(root: Path | None = None) -> Path:
    """Get the tools/data directory containing configuration files."""
    root = root or get_project_root()
    return root / "tools" / "data"


def get_fls_dir(root: Path | None = None) -> Path:
    """Get the embeddings/fls directory."""
    root = root or get_project_root()
    return root / "embeddings" / "fls"


def get_misra_embeddings_dir(root: Path | None = None) -> Path:
    """Get the embeddings/misra_c directory."""
    root = root or get_project_root()
    return root / "embeddings" / "misra_c"


def get_similarity_dir(root: Path | None = None) -> Path:
    """Get the embeddings/similarity directory."""
    root = root or get_project_root()
    return root / "embeddings" / "similarity"


def get_mappings_dir(root: Path | None = None) -> Path:
    """Get the coding-standards-fls-mapping/mappings directory."""
    root = root or get_project_root()
    return root / "coding-standards-fls-mapping" / "mappings"


def get_standards_dir(root: Path | None = None) -> Path:
    """Get the coding-standards-fls-mapping/standards directory."""
    root = root or get_project_root()
    return root / "coding-standards-fls-mapping" / "standards"


def get_cache_dir(root: Path | None = None) -> Path:
    """Get the cache directory."""
    root = root or get_project_root()
    return root / "cache"


def get_iceoryx2_fls_dir(root: Path | None = None) -> Path:
    """Get the iceoryx2-fls-mapping directory."""
    root = root or get_project_root()
    return root / "iceoryx2-fls-mapping"


# Specific data file paths

def get_fls_section_mapping_path(root: Path | None = None) -> Path:
    """Get the path to fls_section_mapping.json."""
    return get_data_dir(root) / "fls_section_mapping.json"


def get_fls_id_to_section_path(root: Path | None = None) -> Path:
    """Get the path to fls_id_to_section.json."""
    return get_data_dir(root) / "fls_id_to_section.json"


def get_synthetic_fls_ids_path(root: Path | None = None) -> Path:
    """Get the path to synthetic_fls_ids.json."""
    return get_data_dir(root) / "synthetic_fls_ids.json"


def get_concept_to_fls_path(root: Path | None = None) -> Path:
    """Get the path to concept_to_fls.json."""
    root = root or get_project_root()
    return root / "coding-standards-fls-mapping" / "concept_to_fls.json"


def get_misra_rust_applicability_path(root: Path | None = None) -> Path:
    """Get the path to misra_rust_applicability.json."""
    root = root or get_project_root()
    return root / "coding-standards-fls-mapping" / "misra_rust_applicability.json"


# Additional directory helpers

def get_verification_cache_dir(root: Path | None = None) -> Path:
    """Get the cache/verification directory for batch reports."""
    return get_cache_dir(root) / "verification"


def get_repos_cache_dir(root: Path | None = None) -> Path:
    """Get the cache/repos directory for cloned repositories."""
    return get_cache_dir(root) / "repos"


def get_coding_standards_dir(root: Path | None = None) -> Path:
    """Get the coding-standards-fls-mapping directory."""
    root = root or get_project_root()
    return root / "coding-standards-fls-mapping"


def get_fls_repo_dir(root: Path | None = None) -> Path:
    """Get the cache/repos/fls directory for cloned FLS repo."""
    return get_repos_cache_dir(root) / "fls"


def get_iceoryx2_repo_dir(root: Path | None = None, version: str | None = None) -> Path:
    """Get the cache/repos/iceoryx2 directory (optionally with version)."""
    base = get_repos_cache_dir(root) / "iceoryx2"
    if version:
        return base / version
    return base


# Additional file path helpers

def get_verification_progress_path(root: Path | None = None) -> Path:
    """Get the path to verification_progress.json."""
    return get_coding_standards_dir(root) / "verification_progress.json"


def get_misra_c_mappings_path(root: Path | None = None) -> Path:
    """Get the path to misra_c_to_fls.json mappings."""
    return get_mappings_dir(root) / "misra_c_to_fls.json"


def get_misra_c_standards_path(root: Path | None = None) -> Path:
    """Get the path to misra_c_2025.json standards definition."""
    return get_standards_dir(root) / "misra_c_2025.json"


def get_misra_c_extracted_text_path(root: Path | None = None) -> Path:
    """Get the path to cached MISRA C extracted text."""
    return get_cache_dir(root) / "misra_c_extracted_text.json"


def get_misra_c_similarity_path(root: Path | None = None) -> Path:
    """Get the path to MISRA C to FLS similarity results."""
    return get_similarity_dir(root) / "misra_c_to_fls.json"


def get_fls_index_path(root: Path | None = None) -> Path:
    """Get the path to FLS index.json."""
    return get_fls_dir(root) / "index.json"


def get_fls_chapter_path(root: Path | None = None, chapter: int = 1) -> Path:
    """Get the path to a specific FLS chapter JSON file."""
    return get_fls_dir(root) / f"chapter_{chapter:02d}.json"


def get_fls_section_embeddings_path(root: Path | None = None) -> Path:
    """Get the path to FLS section-level embeddings."""
    return get_fls_dir(root) / "embeddings.pkl"


def get_fls_paragraph_embeddings_path(root: Path | None = None) -> Path:
    """Get the path to FLS paragraph-level embeddings."""
    return get_fls_dir(root) / "paragraph_embeddings.pkl"


def get_misra_c_embeddings_path(root: Path | None = None) -> Path:
    """Get the path to MISRA C guideline-level embeddings."""
    return get_misra_embeddings_dir(root) / "embeddings.pkl"


def get_misra_c_query_embeddings_path(root: Path | None = None) -> Path:
    """Get the path to MISRA C query-level embeddings."""
    return get_misra_embeddings_dir(root) / "query_embeddings.pkl"


def get_misra_c_rationale_embeddings_path(root: Path | None = None) -> Path:
    """Get the path to MISRA C rationale-level embeddings."""
    return get_misra_embeddings_dir(root) / "rationale_embeddings.pkl"


def get_misra_c_amplification_embeddings_path(root: Path | None = None) -> Path:
    """Get the path to MISRA C amplification-level embeddings."""
    return get_misra_embeddings_dir(root) / "amplification_embeddings.pkl"


def get_misra_pdf_path(root: Path | None = None) -> Path:
    """Get the path to MISRA C PDF (in cache)."""
    return get_cache_dir(root) / "misra-standards" / "MISRA-C-2025.pdf"
