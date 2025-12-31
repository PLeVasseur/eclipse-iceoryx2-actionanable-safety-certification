"""
Shared utilities for FLS mapping tools.

This package provides cross-cutting utilities used by both pipelines:
- Pipeline 1: iceoryx2 -> FLS mapping
- Pipeline 2: MISRA/CERT -> FLS mapping

Modules:
- paths: Project root and common path utilities
- constants: Shared constants (CATEGORY_NAMES, thresholds, etc.)
- io: JSON and embedding I/O utilities
- fls: FLS chapter loading and metadata utilities
- similarity: Cosine similarity and search utilities
"""

from .paths import (
    # Directory helpers
    get_project_root,
    get_tools_dir,
    get_data_dir,
    get_fls_dir,
    get_misra_embeddings_dir,
    get_similarity_dir,
    get_mappings_dir,
    get_standards_dir,
    get_cache_dir,
    get_iceoryx2_fls_dir,
    get_verification_cache_dir,
    get_repos_cache_dir,
    get_coding_standards_dir,
    get_fls_repo_dir,
    get_iceoryx2_repo_dir,
    # Specific data file paths
    get_fls_section_mapping_path,
    get_fls_id_to_section_path,
    get_synthetic_fls_ids_path,
    get_concept_to_fls_path,
    get_misra_rust_applicability_path,
    get_verification_progress_path,
    get_misra_c_mappings_path,
    get_misra_c_standards_path,
    get_misra_c_extracted_text_path,
    get_misra_c_similarity_path,
    get_fls_index_path,
    get_fls_chapter_path,
    get_fls_section_embeddings_path,
    get_fls_paragraph_embeddings_path,
    get_misra_c_embeddings_path,
    get_misra_c_query_embeddings_path,
    get_misra_c_rationale_embeddings_path,
    get_misra_c_amplification_embeddings_path,
    get_misra_pdf_path,
)

from .constants import (
    CATEGORY_CODES,
    CATEGORY_NAMES,
    DEFAULT_SECTION_THRESHOLD,
    DEFAULT_PARAGRAPH_THRESHOLD,
    CONCEPT_BOOST_ADDITIVE,
    CONCEPT_ONLY_BASE_SCORE,
    SEE_ALSO_SCORE_PENALTY,
    SEE_ALSO_MAX_MATCHES,
)

from .io import (
    load_json,
    save_json,
    load_embeddings,
)

from .fls import (
    load_fls_chapters,
    build_fls_metadata,
)

from .similarity import (
    cosine_similarity_vector,
    search_embeddings,
)

__all__ = [
    # paths - directories
    "get_project_root",
    "get_tools_dir",
    "get_data_dir",
    "get_fls_dir",
    "get_misra_embeddings_dir",
    "get_similarity_dir",
    "get_mappings_dir",
    "get_standards_dir",
    "get_cache_dir",
    "get_iceoryx2_fls_dir",
    "get_verification_cache_dir",
    "get_repos_cache_dir",
    "get_coding_standards_dir",
    "get_fls_repo_dir",
    "get_iceoryx2_repo_dir",
    # paths - specific data files
    "get_fls_section_mapping_path",
    "get_fls_id_to_section_path",
    "get_synthetic_fls_ids_path",
    "get_concept_to_fls_path",
    "get_misra_rust_applicability_path",
    "get_verification_progress_path",
    "get_misra_c_mappings_path",
    "get_misra_c_standards_path",
    "get_misra_c_extracted_text_path",
    "get_misra_c_similarity_path",
    "get_fls_index_path",
    "get_fls_chapter_path",
    "get_fls_section_embeddings_path",
    "get_fls_paragraph_embeddings_path",
    "get_misra_c_embeddings_path",
    "get_misra_c_query_embeddings_path",
    "get_misra_c_rationale_embeddings_path",
    "get_misra_c_amplification_embeddings_path",
    "get_misra_pdf_path",
    # constants
    "CATEGORY_CODES",
    "CATEGORY_NAMES",
    "DEFAULT_SECTION_THRESHOLD",
    "DEFAULT_PARAGRAPH_THRESHOLD",
    "CONCEPT_BOOST_ADDITIVE",
    "CONCEPT_ONLY_BASE_SCORE",
    "SEE_ALSO_SCORE_PENALTY",
    "SEE_ALSO_MAX_MATCHES",
    # io
    "load_json",
    "save_json",
    "load_embeddings",
    # fls
    "load_fls_chapters",
    "build_fls_metadata",
    # similarity
    "cosine_similarity_vector",
    "search_embeddings",
]
