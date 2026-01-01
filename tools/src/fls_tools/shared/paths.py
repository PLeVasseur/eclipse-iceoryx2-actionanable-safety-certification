"""
Common path utilities and constants.

This module provides the project root and common path helpers
used across all tools.

All verification and embedding tools require a --standard parameter.
Valid standards: misra-c, misra-cpp, cert-c, cert-cpp

CLI uses kebab-case (misra-c), internal/file names use snake_case (misra_c).
"""

from pathlib import Path


# =============================================================================
# Standard name mappings
# =============================================================================

# CLI name (kebab-case) -> internal/file name (snake_case)
STANDARD_CLI_TO_INTERNAL = {
    "misra-c": "misra_c",
    "misra-cpp": "misra_cpp",
    "cert-c": "cert_c",
    "cert-cpp": "cert_cpp",
}

# Internal name -> CLI name (reverse mapping)
STANDARD_INTERNAL_TO_CLI = {v: k for k, v in STANDARD_CLI_TO_INTERNAL.items()}

# Valid CLI standard names
VALID_STANDARDS = list(STANDARD_CLI_TO_INTERNAL.keys())

# Standard definitions file names (in coding-standards-fls-mapping/standards/)
STANDARD_DEFINITIONS = {
    "misra_c": "misra_c_2025.json",
    "misra_cpp": "misra_cpp_2023.json",
    "cert_c": "cert_c.json",
    "cert_cpp": "cert_cpp.json",
}

# Cache file names for extracted text
STANDARD_EXTRACTED_TEXT = {
    "misra_c": "misra_c_extracted_text.json",
    "misra_cpp": "misra_cpp_extracted_text.json",
    "cert_c": "cert_c_extracted_text.json",
    "cert_cpp": "cert_cpp_extracted_text.json",
}

# PDF paths (in cache/misra-standards/ or cache/cert-standards/)
STANDARD_PDF_PATHS = {
    "misra_c": "misra-standards/MISRA-C-2025.pdf",
    "misra_cpp": "misra-standards/MISRA-CPP-2023.pdf",
    # CERT standards are scraped from web, no PDFs
}


def normalize_standard(standard: str) -> str:
    """
    Convert CLI standard name (kebab-case) to internal name (snake_case).
    
    Args:
        standard: CLI name like "misra-c" or internal name like "misra_c"
    
    Returns:
        Internal name (snake_case)
    
    Raises:
        ValueError: If standard is not recognized
    
    Example:
        >>> normalize_standard("misra-c")
        "misra_c"
        >>> normalize_standard("misra_c")  # Already internal form
        "misra_c"
    """
    if standard in STANDARD_CLI_TO_INTERNAL:
        return STANDARD_CLI_TO_INTERNAL[standard]
    if standard in STANDARD_CLI_TO_INTERNAL.values():
        return standard  # Already internal form
    raise ValueError(
        f"Invalid standard: '{standard}'. "
        f"Valid standards: {', '.join(VALID_STANDARDS)}"
    )


def cli_standard(standard: str) -> str:
    """
    Convert internal standard name (snake_case) to CLI name (kebab-case).
    
    Args:
        standard: Internal name like "misra_c" or CLI name like "misra-c"
    
    Returns:
        CLI name (kebab-case)
    """
    if standard in STANDARD_INTERNAL_TO_CLI:
        return STANDARD_INTERNAL_TO_CLI[standard]
    if standard in STANDARD_CLI_TO_INTERNAL:
        return standard  # Already CLI form
    raise ValueError(
        f"Invalid standard: '{standard}'. "
        f"Valid standards: {', '.join(VALID_STANDARDS)}"
    )


# =============================================================================
# Project root and base directories
# =============================================================================

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


def get_cache_dir(root: Path | None = None) -> Path:
    """Get the cache directory."""
    root = root or get_project_root()
    return root / "cache"


def get_coding_standards_dir(root: Path | None = None) -> Path:
    """Get the coding-standards-fls-mapping directory."""
    root = root or get_project_root()
    return root / "coding-standards-fls-mapping"


def get_mappings_dir(root: Path | None = None) -> Path:
    """Get the coding-standards-fls-mapping/mappings directory."""
    return get_coding_standards_dir(root) / "mappings"


def get_standards_definitions_dir(root: Path | None = None) -> Path:
    """Get the coding-standards-fls-mapping/standards directory."""
    return get_coding_standards_dir(root) / "standards"


def get_embeddings_dir(root: Path | None = None) -> Path:
    """Get the embeddings directory."""
    root = root or get_project_root()
    return root / "embeddings"


def get_iceoryx2_fls_dir(root: Path | None = None) -> Path:
    """Get the iceoryx2-fls-mapping directory."""
    root = root or get_project_root()
    return root / "iceoryx2-fls-mapping"


# =============================================================================
# FLS paths (shared across all standards)
# =============================================================================

def get_fls_dir(root: Path | None = None) -> Path:
    """Get the embeddings/fls directory."""
    return get_embeddings_dir(root) / "fls"


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


def get_fls_section_mapping_path(root: Path | None = None) -> Path:
    """Get the path to fls_section_mapping.json."""
    return get_data_dir(root) / "fls_section_mapping.json"


def get_fls_id_to_section_path(root: Path | None = None) -> Path:
    """Get the path to fls_id_to_section.json."""
    return get_data_dir(root) / "fls_id_to_section.json"


def get_synthetic_fls_ids_path(root: Path | None = None) -> Path:
    """Get the path to synthetic_fls_ids.json."""
    return get_data_dir(root) / "synthetic_fls_ids.json"


# =============================================================================
# Standard-specific paths (parameterized by standard)
# =============================================================================

def get_standard_embeddings_dir(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the embeddings directory for a specific standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like embeddings/misra-c/
    """
    if not standard:
        raise ValueError("standard parameter is required")
    cli_name = cli_standard(standard)
    return get_embeddings_dir(root) / cli_name


def get_standard_mappings_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to the FLS mappings file for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like coding-standards-fls-mapping/mappings/misra_c_to_fls.json
    """
    if not standard:
        raise ValueError("standard parameter is required")
    internal = normalize_standard(standard)
    return get_mappings_dir(root) / f"{internal}_to_fls.json"


def get_standard_definitions_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to the standard definitions file.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like coding-standards-fls-mapping/standards/misra_c_2025.json
    """
    if not standard:
        raise ValueError("standard parameter is required")
    internal = normalize_standard(standard)
    filename = STANDARD_DEFINITIONS.get(internal)
    if not filename:
        raise ValueError(f"No definitions file configured for standard: {standard}")
    return get_standards_definitions_dir(root) / filename


def get_standard_extracted_text_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to cached extracted text for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like cache/misra_c_extracted_text.json
    """
    if not standard:
        raise ValueError("standard parameter is required")
    internal = normalize_standard(standard)
    filename = STANDARD_EXTRACTED_TEXT.get(internal)
    if not filename:
        raise ValueError(f"No extracted text file configured for standard: {standard}")
    return get_cache_dir(root) / filename


def get_standard_similarity_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to similarity results for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like embeddings/misra-c/similarity.json
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_standard_embeddings_dir(root, standard) / "similarity.json"


def get_standard_embeddings_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to guideline-level embeddings for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like embeddings/misra-c/embeddings.pkl
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_standard_embeddings_dir(root, standard) / "embeddings.pkl"


def get_standard_query_embeddings_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to query-level embeddings for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like embeddings/misra-c/query_embeddings.pkl
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_standard_embeddings_dir(root, standard) / "query_embeddings.pkl"


def get_standard_rationale_embeddings_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to rationale-level embeddings for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like embeddings/misra-c/rationale_embeddings.pkl
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_standard_embeddings_dir(root, standard) / "rationale_embeddings.pkl"


def get_standard_amplification_embeddings_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to amplification-level embeddings for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like embeddings/misra-c/amplification_embeddings.pkl
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_standard_embeddings_dir(root, standard) / "amplification_embeddings.pkl"


def get_standard_pdf_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to PDF file for a standard (MISRA only).
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like cache/misra-standards/MISRA-C-2025.pdf
    
    Raises:
        ValueError: If no PDF is configured for this standard (e.g., CERT)
    """
    if not standard:
        raise ValueError("standard parameter is required")
    internal = normalize_standard(standard)
    relative_path = STANDARD_PDF_PATHS.get(internal)
    if not relative_path:
        raise ValueError(f"No PDF configured for standard: {standard} (CERT standards are scraped from web)")
    return get_cache_dir(root) / relative_path


# =============================================================================
# Verification-specific paths (parameterized by standard)
# =============================================================================

def get_verification_dir(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the verification directory for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like coding-standards-fls-mapping/verification/misra-c/
    """
    if not standard:
        raise ValueError("standard parameter is required")
    cli_name = cli_standard(standard)
    return get_coding_standards_dir(root) / "verification" / cli_name


def get_verification_progress_path(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the path to verification progress file for a standard.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like coding-standards-fls-mapping/verification/misra-c/progress.json
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_verification_dir(root, standard) / "progress.json"


def get_verification_cache_dir(root: Path | None = None, standard: str = "") -> Path:
    """
    Get the cache directory for verification artifacts.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
    
    Returns:
        Path like cache/verification/misra-c/
    """
    if not standard:
        raise ValueError("standard parameter is required")
    cli_name = cli_standard(standard)
    return get_cache_dir(root) / "verification" / cli_name


def get_batch_report_path(
    root: Path | None = None,
    standard: str = "",
    batch: int = 1,
    session: int = 1,
) -> Path:
    """
    Get the path to a batch report file.
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
        batch: Batch number
        session: Session number
    
    Returns:
        Path like cache/verification/misra-c/batch1_session1.json
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_verification_cache_dir(root, standard) / f"batch{batch}_session{session}.json"


def get_batch_decisions_dir(
    root: Path | None = None,
    standard: str = "",
    batch: int = 1,
) -> Path:
    """
    Get the directory for per-guideline decision files (parallel verification).
    
    Args:
        root: Project root (defaults to get_project_root())
        standard: Standard name (CLI or internal form)
        batch: Batch number
    
    Returns:
        Path like cache/verification/misra-c/batch1_decisions/
    """
    if not standard:
        raise ValueError("standard parameter is required")
    return get_verification_cache_dir(root, standard) / f"batch{batch}_decisions"


# =============================================================================
# Other shared paths
# =============================================================================

def get_repos_cache_dir(root: Path | None = None) -> Path:
    """Get the cache/repos directory for cloned repositories."""
    return get_cache_dir(root) / "repos"


def get_fls_repo_dir(root: Path | None = None) -> Path:
    """Get the cache/repos/fls directory for cloned FLS repo."""
    return get_repos_cache_dir(root) / "fls"


def get_iceoryx2_repo_dir(root: Path | None = None, version: str | None = None) -> Path:
    """Get the cache/repos/iceoryx2 directory (optionally with version)."""
    base = get_repos_cache_dir(root) / "iceoryx2"
    if version:
        return base / version
    return base


def get_concept_to_fls_path(root: Path | None = None) -> Path:
    """Get the path to concept_to_fls.json."""
    return get_coding_standards_dir(root) / "concept_to_fls.json"


def get_misra_rust_applicability_path(root: Path | None = None) -> Path:
    """Get the path to misra_rust_applicability.json."""
    return get_coding_standards_dir(root) / "misra_rust_applicability.json"


# =============================================================================
# Path safety utilities
# =============================================================================

class PathOutsideProjectError(ValueError):
    """Raised when a path resolves outside the project root."""
    pass


def resolve_path(path: Path, root: Path | None = None) -> Path:
    """
    Resolve a path to an absolute path, handling relative paths correctly.
    
    If the path is absolute, returns it as-is.
    If the path is relative, resolves it from the current working directory.
    
    This avoids the bug where `root / relative_path_with_dotdot` doesn't work
    as expected (e.g., `root / "../cache"` keeps the `..` unresolved).
    
    Args:
        path: The path to resolve
        root: Ignored (kept for API compatibility) - relative paths always
              resolve from cwd
    
    Returns:
        The resolved absolute path
    """
    if path.is_absolute():
        return path
    return path.resolve()


def validate_path_in_project(path: Path, root: Path | None = None) -> Path:
    """
    Validate that a path is within the project root.
    
    Args:
        path: The path to validate (can be relative or absolute)
        root: Project root (defaults to get_project_root())
    
    Returns:
        The resolved absolute path
    
    Raises:
        PathOutsideProjectError: If the resolved path is outside the project root
    
    Example:
        >>> validate_path_in_project(Path("cache/verification"))  # OK
        >>> validate_path_in_project(Path("../other_project"))    # Raises error
    """
    if root is None:
        root = get_project_root()
    
    # Resolve to absolute path
    resolved = path.resolve()
    root_resolved = root.resolve()
    
    # Check if the path is within the project root
    try:
        resolved.relative_to(root_resolved)
        return resolved
    except ValueError:
        raise PathOutsideProjectError(
            f"Path '{resolved}' is outside project root '{root_resolved}'. "
            f"Use absolute paths or --batch N instead of relative paths."
        )
