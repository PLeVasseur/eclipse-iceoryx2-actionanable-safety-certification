"""
I/O utilities for loading JSON and embeddings.

This module provides common file I/O operations used across tools.
"""

import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np


def load_json(
    path: Path,
    description: str = "",
    exit_on_error: bool = True,
) -> dict | None:
    """
    Load a JSON file with error handling.
    
    Args:
        path: Path to the JSON file
        description: Human-readable description for error messages
        exit_on_error: If True, exit the program on missing file.
                       If False, return None.
    
    Returns:
        The loaded JSON data as a dict, or None if file is missing
        and exit_on_error is False.
    """
    if not path.exists():
        if exit_on_error:
            desc = description or str(path)
            print(f"ERROR: {desc} not found: {path}", file=sys.stderr)
            sys.exit(1)
        return None
    
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(
    path: Path,
    data: Any,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """
    Save data to a JSON file.
    
    Args:
        path: Path to write the JSON file
        data: Data to serialize to JSON
        indent: Indentation level (default: 2)
        ensure_ascii: If False (default), allow non-ASCII characters
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        f.write("\n")  # Add trailing newline


def load_embeddings(
    path: Path,
    exit_on_error: bool = True,
) -> tuple[list[str], np.ndarray, dict, dict]:
    """
    Load embeddings from a pickle file.
    
    The pickle file should have been created by generate_embeddings.py
    and contains embeddings in a specific format with 'data' key.
    
    Args:
        path: Path to the pickle file
        exit_on_error: If True, exit on missing file. If False, return empty.
    
    Returns:
        Tuple of:
        - ids: List of embedding IDs
        - embeddings: numpy array of embeddings (N x D)
        - id_to_index: Dict mapping ID to index in the array
        - metadata: Dict of additional metadata (if present)
    """
    if not path.exists():
        if exit_on_error:
            print(f"ERROR: Embeddings not found: {path}", file=sys.stderr)
            sys.exit(1)
        return [], np.array([]), {}, {}
    
    with open(path, "rb") as f:
        data = pickle.load(f)
    
    # Handle the embeddings format: data may be nested under 'data' key
    embed_data = data.get("data", data)
    
    return (
        embed_data.get("ids", []),
        embed_data.get("embeddings", np.array([])),
        embed_data.get("id_to_index", {}),
        data.get("metadata", {}),
    )


def save_embeddings(
    path: Path,
    ids: list[str],
    embeddings: np.ndarray,
    metadata: dict | None = None,
    **extra_fields,
) -> None:
    """
    Save embeddings to a pickle file.
    
    Args:
        path: Path to write the pickle file
        ids: List of embedding IDs
        embeddings: numpy array of embeddings (N x D)
        metadata: Optional metadata dict
        **extra_fields: Additional fields to include in the pickle
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "data": {
            "ids": ids,
            "embeddings": embeddings,
            "id_to_index": {id_: i for i, id_ in enumerate(ids)},
        },
        **extra_fields,
    }
    
    if metadata:
        data["metadata"] = metadata
    
    with open(path, "wb") as f:
        pickle.dump(data, f)
