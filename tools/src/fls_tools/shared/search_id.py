"""Search ID generation and validation for verification workflow integrity.

This module provides UUID4-based unique identifiers for search executions,
ensuring each search can only be claimed by one guideline's verification decision.

Usage:
    from fls_tools.shared import generate_search_id, validate_search_id

    # In search tools - generate and display ID
    search_id = generate_search_id()
    print(f"Search ID: {search_id}")

    # In record-decision - validate format
    if not validate_search_id(user_provided_id):
        raise ValueError("Invalid UUID4 format")
"""

import uuid


def generate_search_id() -> str:
    """Generate a UUID4 search identifier.

    Returns:
        A lowercase UUID4 string (e.g., '550e8400-e29b-41d4-a716-446655440000')
    """
    return str(uuid.uuid4())


def validate_search_id(search_id: str) -> bool:
    """Validate that a string is a valid UUID4.

    Args:
        search_id: The string to validate

    Returns:
        True if the string is a valid UUID4, False otherwise
    """
    try:
        val = uuid.UUID(search_id, version=4)
        # Ensure the string representation matches (catches uppercase, extra chars, etc.)
        return str(val) == search_id.lower()
    except (ValueError, AttributeError):
        return False
