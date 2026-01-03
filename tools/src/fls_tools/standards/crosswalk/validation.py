"""ID validation utilities for concept crosswalk enrichment.

Provides functions to load and validate IDs from multiple documentation sources:
- FLS (Ferrocene Language Specification)
- Rust Reference
- UCG (Unsafe Code Guidelines)
- Nomicon (Rustonomicon)
- Clippy lints
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ValidIds:
    """Container for valid IDs from all documentation sources."""

    fls_ids: set[str] = field(default_factory=set)
    reference_ids: set[str] = field(default_factory=set)
    ucg_ids: set[str] = field(default_factory=set)
    nomicon_ids: set[str] = field(default_factory=set)
    clippy_lints: set[str] = field(default_factory=set)

    def is_valid_fls_id(self, id: str) -> bool:
        """Check if an FLS ID is valid."""
        return id in self.fls_ids

    def is_valid_reference_id(self, id: str) -> bool:
        """Check if a Reference ID is valid."""
        return id in self.reference_ids

    def is_valid_ucg_id(self, id: str) -> bool:
        """Check if a UCG ID is valid."""
        return id in self.ucg_ids

    def is_valid_nomicon_id(self, id: str) -> bool:
        """Check if a Nomicon ID is valid."""
        return id in self.nomicon_ids

    def is_valid_clippy_lint(self, lint: str) -> bool:
        """Check if a Clippy lint name is valid."""
        return lint in self.clippy_lints


@dataclass
class ValidationResult:
    """Result of validating a concept's IDs."""

    concept_key: str
    valid: bool = True
    invalid_fls_ids: list[str] = field(default_factory=list)
    invalid_reference_ids: list[str] = field(default_factory=list)
    invalid_ucg_ids: list[str] = field(default_factory=list)
    invalid_nomicon_ids: list[str] = field(default_factory=list)
    invalid_clippy_lints: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Update valid flag based on invalid lists."""
        self.valid = not any(
            [
                self.invalid_fls_ids,
                self.invalid_reference_ids,
                self.invalid_ucg_ids,
                self.invalid_nomicon_ids,
                self.invalid_clippy_lints,
            ]
        )

    def error_messages(self) -> list[str]:
        """Generate error messages for invalid IDs."""
        messages = []
        if self.invalid_fls_ids:
            messages.append(f"Invalid FLS IDs: {', '.join(self.invalid_fls_ids)}")
        if self.invalid_reference_ids:
            messages.append(
                f"Invalid Reference IDs: {', '.join(self.invalid_reference_ids)}"
            )
        if self.invalid_ucg_ids:
            messages.append(f"Invalid UCG IDs: {', '.join(self.invalid_ucg_ids)}")
        if self.invalid_nomicon_ids:
            messages.append(
                f"Invalid Nomicon IDs: {', '.join(self.invalid_nomicon_ids)}"
            )
        if self.invalid_clippy_lints:
            messages.append(
                f"Invalid Clippy lints: {', '.join(self.invalid_clippy_lints)}"
            )
        return messages


def get_project_root() -> Path:
    """Get the project root directory."""
    # Walk up from this file to find project root
    current = Path(__file__).resolve()
    while current.parent != current:
        if (current / "AGENTS.md").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find project root")


def load_valid_ids(project_root: Optional[Path] = None) -> ValidIds:
    """Load valid IDs from all documentation sources.

    Args:
        project_root: Path to project root. If None, auto-detected.

    Returns:
        ValidIds container with all valid IDs loaded.
    """
    if project_root is None:
        project_root = get_project_root()

    valid_ids = ValidIds()

    # Load FLS IDs
    fls_ids_path = project_root / "tools" / "data" / "valid_fls_ids.json"
    if fls_ids_path.exists():
        with open(fls_ids_path) as f:
            data = json.load(f)
            valid_ids.fls_ids = set(data.get("ids", []))

    # Load Reference IDs
    ref_ids_path = project_root / "tools" / "data" / "valid_reference_ids.json"
    if ref_ids_path.exists():
        with open(ref_ids_path) as f:
            data = json.load(f)
            valid_ids.reference_ids = set(data.get("ids", []))

    # Load UCG IDs from chapter files
    ucg_dir = project_root / "embeddings" / "ucg"
    if ucg_dir.exists():
        for chapter_file in ucg_dir.glob("chapter_*.json"):
            with open(chapter_file) as f:
                data = json.load(f)
                for section in data.get("sections", []):
                    # Add section ID
                    if "id" in section:
                        valid_ids.ucg_ids.add(section["id"])
                    # Add paragraph IDs
                    for para_id in section.get("paragraphs", {}).keys():
                        valid_ids.ucg_ids.add(para_id)

    # Load Nomicon IDs from chapter files
    nomicon_dir = project_root / "embeddings" / "nomicon"
    if nomicon_dir.exists():
        for chapter_file in nomicon_dir.glob("chapter_*.json"):
            with open(chapter_file) as f:
                data = json.load(f)
                for section in data.get("sections", []):
                    # Add section ID
                    if "id" in section:
                        valid_ids.nomicon_ids.add(section["id"])
                    # Add paragraph IDs
                    for para_id in section.get("paragraphs", {}).keys():
                        valid_ids.nomicon_ids.add(para_id)

    # Load Clippy lint names
    clippy_lints_path = project_root / "embeddings" / "clippy" / "lints.json"
    if clippy_lints_path.exists():
        with open(clippy_lints_path) as f:
            data = json.load(f)
            for lint in data.get("lints", []):
                # Store snake_name (without clippy:: prefix)
                if "snake_name" in lint:
                    valid_ids.clippy_lints.add(lint["snake_name"])

    return valid_ids


def validate_concept_ids(
    concept_key: str, concept: dict, valid_ids: ValidIds
) -> ValidationResult:
    """Validate all IDs in a concept entry.

    Args:
        concept_key: The concept's key in the crosswalk
        concept: The concept entry dictionary
        valid_ids: ValidIds container with all valid IDs

    Returns:
        ValidationResult with any invalid IDs identified.
    """
    result = ValidationResult(concept_key=concept_key)

    # Validate FLS IDs
    for fls_id in concept.get("fls_ids", []):
        if not valid_ids.is_valid_fls_id(fls_id):
            result.invalid_fls_ids.append(fls_id)

    # Validate Reference IDs
    for ref_id in concept.get("reference_ids", []):
        if not valid_ids.is_valid_reference_id(ref_id):
            result.invalid_reference_ids.append(ref_id)

    # Validate UCG IDs
    for ucg_id in concept.get("ucg_ids", []):
        if not valid_ids.is_valid_ucg_id(ucg_id):
            result.invalid_ucg_ids.append(ucg_id)

    # Validate Nomicon IDs
    for nomicon_id in concept.get("nomicon_ids", []):
        if not valid_ids.is_valid_nomicon_id(nomicon_id):
            result.invalid_nomicon_ids.append(nomicon_id)

    # Validate Clippy lints
    for lint in concept.get("clippy_lints", []):
        if not valid_ids.is_valid_clippy_lint(lint):
            result.invalid_clippy_lints.append(lint)

    # Update valid flag
    result.__post_init__()

    return result


def validate_all_concepts(
    concepts: dict, valid_ids: ValidIds
) -> list[ValidationResult]:
    """Validate all concepts in the crosswalk.

    Args:
        concepts: Dictionary of concept_key -> concept_entry
        valid_ids: ValidIds container with all valid IDs

    Returns:
        List of ValidationResults (only includes invalid ones by default).
    """
    results = []
    for key, concept in concepts.items():
        result = validate_concept_ids(key, concept, valid_ids)
        if not result.valid:
            results.append(result)
    return results
