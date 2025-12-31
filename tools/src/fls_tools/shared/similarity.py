"""
Similarity computation utilities.

This module provides functions for computing cosine similarity
between embeddings and searching for similar items.
"""

import numpy as np


def cosine_similarity_vector(
    query: np.ndarray,
    embeddings: np.ndarray,
) -> np.ndarray:
    """
    Compute cosine similarity between a query vector and multiple embeddings.
    
    Args:
        query: Query embedding vector (D,)
        embeddings: Matrix of embeddings to compare against (N, D)
    
    Returns:
        Array of similarity scores (N,), one per embedding.
    """
    if embeddings.size == 0:
        return np.array([])
    
    query_norm = query / np.linalg.norm(query)
    embed_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    
    return np.dot(embed_norms, query_norm)


def cosine_similarity_matrix(
    queries: np.ndarray,
    embeddings: np.ndarray,
) -> np.ndarray:
    """
    Compute cosine similarity matrix between queries and embeddings.
    
    Args:
        queries: Matrix of query embeddings (M, D)
        embeddings: Matrix of target embeddings (N, D)
    
    Returns:
        Similarity matrix (M, N) where result[i,j] is similarity
        between query i and embedding j.
    """
    if queries.size == 0 or embeddings.size == 0:
        return np.array([])
    
    # Normalize both
    query_norms = queries / np.linalg.norm(queries, axis=1, keepdims=True)
    embed_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    
    return np.dot(query_norms, embed_norms.T)


def search_embeddings(
    query_embedding: np.ndarray,
    ids: list[str],
    embeddings: np.ndarray,
    top_n: int = 20,
) -> list[tuple[str, float]]:
    """
    Search embeddings with a query and return top matches.
    
    Args:
        query_embedding: Query vector (D,)
        ids: List of IDs corresponding to embeddings
        embeddings: Matrix of embeddings (N, D)
        top_n: Number of top results to return
    
    Returns:
        List of (id, similarity_score) tuples, sorted by score descending.
    """
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    similarities = cosine_similarity_vector(query_embedding, embeddings)
    top_indices = np.argsort(similarities)[::-1][:top_n]
    
    return [(ids[idx], float(similarities[idx])) for idx in top_indices]


def search_with_threshold(
    query_embedding: np.ndarray,
    ids: list[str],
    embeddings: np.ndarray,
    threshold: float,
    top_n: int | None = None,
) -> list[tuple[str, float]]:
    """
    Search embeddings and return matches above a threshold.
    
    Args:
        query_embedding: Query vector (D,)
        ids: List of IDs corresponding to embeddings
        embeddings: Matrix of embeddings (N, D)
        threshold: Minimum similarity score to include
        top_n: Optional limit on number of results
    
    Returns:
        List of (id, similarity_score) tuples above threshold,
        sorted by score descending.
    """
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    similarities = cosine_similarity_vector(query_embedding, embeddings)
    
    # Get indices above threshold
    above_threshold = np.where(similarities >= threshold)[0]
    
    # Sort by similarity descending
    sorted_indices = above_threshold[np.argsort(similarities[above_threshold])[::-1]]
    
    if top_n is not None:
        sorted_indices = sorted_indices[:top_n]
    
    return [(ids[idx], float(similarities[idx])) for idx in sorted_indices]
