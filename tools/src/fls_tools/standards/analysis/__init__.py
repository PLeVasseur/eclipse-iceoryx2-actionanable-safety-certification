"""
Analysis tools for comparing verification decisions against mapping file.

This package provides tools for:
- Extracting comparison data between decisions and mappings
- Recording LLM outlier analysis with full context
- Interactive human review of outliers
- Generating analysis reports (final, per-batch, cross-batch)

Tools:
- extract-comparison-data: Extract and compare decision files vs mapping file
- record-outlier-analysis: Record LLM analysis for flagged guidelines
- list-pending-outliers: Show outliers not yet analyzed
- diff-fls-matches: Human-readable diff for a single guideline
- generate-analysis-reports: Generate Markdown reports
- review-outliers: Interactive human review tool
"""

from .shared import (
    # Path helpers
    get_analysis_dir,
    get_comparison_data_dir,
    get_outlier_analysis_dir,
    get_reports_dir,
    get_review_state_path,
    # Data loading
    load_comparison_data,
    load_outlier_analysis,
    load_review_state,
    save_review_state,
    # Flag computation
    compute_comparison,
    compute_flags,
    is_outlier,
    get_active_flags,
    # Batch helpers
    get_batch_expected_pattern,
    check_pattern_conformance,
    # Constants
    FLAG_TYPES,
    OUTLIER_THRESHOLDS,
)

__all__ = [
    # Path helpers
    "get_analysis_dir",
    "get_comparison_data_dir",
    "get_outlier_analysis_dir",
    "get_reports_dir",
    "get_review_state_path",
    # Data loading
    "load_comparison_data",
    "load_outlier_analysis",
    "load_review_state",
    "save_review_state",
    # Flag computation
    "compute_comparison",
    "compute_flags",
    "is_outlier",
    "get_active_flags",
    # Batch helpers
    "get_batch_expected_pattern",
    "check_pattern_conformance",
    # Constants
    "FLAG_TYPES",
    "OUTLIER_THRESHOLDS",
]
