"""Four-layer fuzzy matching for concept lookup.

Implements a multi-layer matching system to find similar concepts:
1. Exact match - key or alias exact match
2. Normalized match - lowercase, strip punctuation, collapse spaces
3. Token match - Jaccard similarity of word tokens
4. Embedding match - cosine similarity of semantic embeddings
"""

import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class MatchResult:
    """Result of matching a query against a concept."""

    concept_key: str
    match_type: str  # "exact", "normalized", "token", "embedding"
    score: float  # 1.0 for exact/normalized, Jaccard for token, cosine for embedding
    matched_via: str  # What matched (key, alias, description, etc.)

    def __repr__(self) -> str:
        return f"MatchResult({self.concept_key!r}, {self.match_type}, {self.score:.3f}, via={self.matched_via!r})"


@dataclass
class MatchResults:
    """Collection of match results with metadata."""

    query: str
    exact_match: Optional[MatchResult] = None
    normalized_match: Optional[MatchResult] = None
    token_matches: list[MatchResult] = field(default_factory=list)
    embedding_matches: list[MatchResult] = field(default_factory=list)

    def has_exact_or_normalized(self) -> bool:
        """Check if there's an exact or normalized match."""
        return self.exact_match is not None or self.normalized_match is not None

    def best_match(self) -> Optional[MatchResult]:
        """Return the best match (exact > normalized > token > embedding)."""
        if self.exact_match:
            return self.exact_match
        if self.normalized_match:
            return self.normalized_match
        if self.token_matches:
            return self.token_matches[0]
        if self.embedding_matches:
            return self.embedding_matches[0]
        return None

    def all_candidates(self) -> list[MatchResult]:
        """Return all candidates for user selection."""
        candidates = []
        if self.exact_match:
            candidates.append(self.exact_match)
        if self.normalized_match and self.normalized_match != self.exact_match:
            candidates.append(self.normalized_match)
        candidates.extend(self.token_matches)
        candidates.extend(self.embedding_matches)
        # Deduplicate by concept_key, keeping highest score
        seen = {}
        for m in candidates:
            if m.concept_key not in seen or m.score > seen[m.concept_key].score:
                seen[m.concept_key] = m
        return sorted(seen.values(), key=lambda m: m.score, reverse=True)


def normalize_string(s: str) -> str:
    """Normalize a string for matching.

    - Lowercase
    - Replace underscores, hyphens, and multiple spaces with single space
    - Strip leading/trailing whitespace
    - Remove non-alphanumeric except spaces
    """
    s = s.lower()
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def tokenize(s: str) -> set[str]:
    """Tokenize a string into a set of words.

    - Normalize first
    - Split on whitespace
    - Filter out single-character tokens
    """
    normalized = normalize_string(s)
    tokens = normalized.split()
    return {t for t in tokens if len(t) > 1}


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def exact_match(query: str, concepts: dict) -> Optional[MatchResult]:
    """Layer 1: Exact match on concept key or aliases.

    Args:
        query: The query string (potential concept key)
        concepts: Dictionary of concept_key -> concept_entry

    Returns:
        MatchResult if exact match found, None otherwise.
    """
    # Check exact key match
    if query in concepts:
        return MatchResult(
            concept_key=query, match_type="exact", score=1.0, matched_via="key"
        )

    # Check aliases
    for key, concept in concepts.items():
        aliases = concept.get("aliases", [])
        if query in aliases:
            return MatchResult(
                concept_key=key, match_type="exact", score=1.0, matched_via="alias"
            )

    return None


def normalized_match(query: str, concepts: dict) -> Optional[MatchResult]:
    """Layer 2: Normalized string match on concept key or aliases.

    Args:
        query: The query string
        concepts: Dictionary of concept_key -> concept_entry

    Returns:
        MatchResult if normalized match found, None otherwise.
    """
    query_norm = normalize_string(query)

    # Check normalized key match
    for key in concepts:
        if normalize_string(key) == query_norm:
            return MatchResult(
                concept_key=key,
                match_type="normalized",
                score=1.0,
                matched_via="key",
            )

    # Check normalized aliases
    for key, concept in concepts.items():
        aliases = concept.get("aliases", [])
        for alias in aliases:
            if normalize_string(alias) == query_norm:
                return MatchResult(
                    concept_key=key,
                    match_type="normalized",
                    score=1.0,
                    matched_via="alias",
                )

    return None


def token_match(
    query: str, concepts: dict, threshold: float = 0.5
) -> list[MatchResult]:
    """Layer 3: Token-based Jaccard similarity match.

    Compares tokenized query against:
    - Concept key tokens
    - Alias tokens
    - Keyword tokens
    - Description tokens

    Args:
        query: The query string
        concepts: Dictionary of concept_key -> concept_entry
        threshold: Minimum Jaccard similarity to include (default 0.5)

    Returns:
        List of MatchResults sorted by score descending.
    """
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    results = []

    for key, concept in concepts.items():
        best_score = 0.0
        best_via = ""

        # Check key
        key_tokens = tokenize(key)
        score = jaccard_similarity(query_tokens, key_tokens)
        if score > best_score:
            best_score = score
            best_via = "key"

        # Check aliases
        for alias in concept.get("aliases", []):
            alias_tokens = tokenize(alias)
            score = jaccard_similarity(query_tokens, alias_tokens)
            if score > best_score:
                best_score = score
                best_via = "alias"

        # Check keywords
        keywords_text = " ".join(concept.get("keywords", []))
        keywords_tokens = tokenize(keywords_text)
        score = jaccard_similarity(query_tokens, keywords_tokens)
        if score > best_score:
            best_score = score
            best_via = "keywords"

        # Check description
        desc_tokens = tokenize(concept.get("description", ""))
        score = jaccard_similarity(query_tokens, desc_tokens)
        if score > best_score:
            best_score = score
            best_via = "description"

        if best_score >= threshold:
            results.append(
                MatchResult(
                    concept_key=key,
                    match_type="token",
                    score=best_score,
                    matched_via=best_via,
                )
            )

    return sorted(results, key=lambda r: r.score, reverse=True)


class ConceptEmbeddings:
    """Cached embeddings for concept matching."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.embeddings: dict[str, np.ndarray] = {}
        self._model: Optional["SentenceTransformer"] = None  # type: ignore[name-defined]
        self._loaded = False

    def _get_model(self):
        """Get the model, loading if necessary."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    def _build_concept_text(self, key: str, concept: dict) -> str:
        """Build text representation for embedding a concept."""
        parts = [key.replace("_", " ")]
        if concept.get("description"):
            parts.append(concept["description"])
        if concept.get("keywords"):
            parts.extend(concept["keywords"])
        if concept.get("rust_terms"):
            parts.extend(concept["rust_terms"])
        if concept.get("c_terms"):
            parts.extend(concept["c_terms"])
        return " ".join(parts)

    def load_or_generate(self, concepts: dict, cache_path: Optional[Path] = None):
        """Load cached embeddings or generate new ones.

        Args:
            concepts: Dictionary of concept_key -> concept_entry
            cache_path: Path to cache file. If None, embeddings not cached.
        """
        if self._loaded:
            return

        # Try loading from cache
        if cache_path and cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    cached = pickle.load(f)
                # Check if cache is still valid (same concept keys)
                if set(cached.keys()) == set(concepts.keys()):
                    self.embeddings = cached
                    self._loaded = True
                    return
            except Exception:
                pass  # Cache invalid, regenerate

        # Generate embeddings
        model = self._get_model()
        for key, concept in concepts.items():
            text = self._build_concept_text(key, concept)
            embedding = model.encode(text, convert_to_numpy=True)
            self.embeddings[key] = embedding

        # Save to cache
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(self.embeddings, f)

        self._loaded = True

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a query string."""
        model = self._get_model()
        return model.encode(query, convert_to_numpy=True)

    def find_similar(
        self, query_embedding: np.ndarray, threshold: float = 0.75, top_k: int = 5
    ) -> list[tuple[str, float]]:
        """Find concepts similar to the query embedding.

        Args:
            query_embedding: The query embedding vector
            threshold: Minimum cosine similarity to include
            top_k: Maximum number of results

        Returns:
            List of (concept_key, similarity_score) tuples sorted by score descending.
        """
        if not self.embeddings:
            return []

        results = []
        for key, emb in self.embeddings.items():
            # Cosine similarity
            similarity = float(
                np.dot(query_embedding, emb)
                / (np.linalg.norm(query_embedding) * np.linalg.norm(emb))
            )
            if similarity >= threshold:
                results.append((key, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


def embedding_match(
    query: str,
    concepts: dict,
    embeddings: ConceptEmbeddings,
    threshold: float = 0.75,
) -> list[MatchResult]:
    """Layer 4: Embedding-based semantic similarity match.

    Args:
        query: The query string
        concepts: Dictionary of concept_key -> concept_entry
        embeddings: Preloaded ConceptEmbeddings instance
        threshold: Minimum cosine similarity to include (default 0.75)

    Returns:
        List of MatchResults sorted by score descending.
    """
    query_embedding = embeddings.embed_query(query)
    similar = embeddings.find_similar(query_embedding, threshold=threshold)

    return [
        MatchResult(
            concept_key=key,
            match_type="embedding",
            score=score,
            matched_via="semantic",
        )
        for key, score in similar
    ]


def find_similar_concepts(
    query: str,
    concepts: dict,
    embeddings: Optional[ConceptEmbeddings] = None,
    token_threshold: float = 0.5,
    embedding_threshold: float = 0.75,
) -> MatchResults:
    """Find concepts similar to the query using all four matching layers.

    Layers are applied in order:
    1. Exact match (key or alias)
    2. Normalized match (case/punctuation insensitive)
    3. Token match (Jaccard similarity >= token_threshold)
    4. Embedding match (cosine similarity >= embedding_threshold)

    If exact or normalized match is found, token/embedding layers are skipped.

    Args:
        query: The query string (potential concept name)
        concepts: Dictionary of concept_key -> concept_entry
        embeddings: Optional preloaded ConceptEmbeddings for semantic matching
        token_threshold: Minimum Jaccard similarity for token matching
        embedding_threshold: Minimum cosine similarity for embedding matching

    Returns:
        MatchResults with matches from all applicable layers.
    """
    results = MatchResults(query=query)

    # Layer 1: Exact match
    results.exact_match = exact_match(query, concepts)
    if results.exact_match:
        return results  # No need to check further

    # Layer 2: Normalized match
    results.normalized_match = normalized_match(query, concepts)
    if results.normalized_match:
        return results  # No need to check further

    # Layer 3: Token match
    results.token_matches = token_match(query, concepts, threshold=token_threshold)

    # Layer 4: Embedding match (only if embeddings provided)
    if embeddings is not None:
        results.embedding_matches = embedding_match(
            query, concepts, embeddings, threshold=embedding_threshold
        )

    return results
