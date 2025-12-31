"""
Shared constants used across FLS mapping tools.

This module provides constants that are used by multiple scripts,
avoiding duplication and ensuring consistency.
"""

# Category codes for FLS rubric content
# FLS content that doesn't have traditional section headings uses
# a special encoding with negative numbers.
CATEGORY_CODES = {
    "section": 0,
    "general": -1,
    "legality_rules": -2,
    "dynamic_semantics": -3,
    "undefined_behavior": -4,
    "implementation_requirements": -5,
    "implementation_permissions": -6,
    "examples": -7,
    "syntax": -8,
}

# Reverse mapping: code -> name
CATEGORY_NAMES = {v: k for k, v in CATEGORY_CODES.items()}

# Default similarity thresholds for FLS matching
DEFAULT_SECTION_THRESHOLD = 0.5
DEFAULT_PARAGRAPH_THRESHOLD = 0.55

# Concept boost parameters for semantic search
# When a matched concept's FLS IDs appear in search results,
# add this value to the similarity score
CONCEPT_BOOST_ADDITIVE = 0.1

# Base score for FLS IDs that appear in matched concepts
# but weren't found by embedding search
CONCEPT_ONLY_BASE_SCORE = 0.4

# See-also integration parameters
# When pulling matches from referenced guidelines, multiply
# their scores by this penalty factor
SEE_ALSO_SCORE_PENALTY = 0.9

# Maximum matches to pull from each see-also referenced guideline
SEE_ALSO_MAX_MATCHES = 3
