# Concept Crosswalk Enrichment

**Status:** Complete  
**Created:** 2026-01-03  
**Last Updated:** 2026-01-03

## Overview

Extend `coding-standards-fls-mapping/concept_to_fls.json` to include cross-references to Rust documentation sources (Reference, UCG, Nomicon, Clippy). This enables better C→Rust terminology bridging during MISRA verification.

## Goals

1. **Enrich existing concepts** with Reference/UCG/Nomicon/Clippy IDs discovered during verification
2. **Add new Rust-specific concepts** when verification reveals useful concept clusters
3. **Prevent duplicate concepts** via multi-layer fuzzy matching (exact → normalized → token → embedding)
4. **Validate all IDs** at write time against known valid IDs

## Schema Changes

### Current Structure (preserve all existing fields)

```json
{
  "metadata": { ... },
  "concepts": {
    "type_conversions": {
      "description": "Type casts, implicit conversions, coercion",
      "keywords": ["cast", "type conversion", "coercion", ...],
      "fls_ids": ["fls_1qhsun1vyarz", ...],
      "fls_sections": ["6.5.10", ...],
      "typical_applicability_all_rust": "partial",
      "typical_applicability_safe_rust": "partial",
      "rationale": "..."
    }
  }
}
```

### Enriched Structure (new optional fields)

```json
{
  "metadata": { ... },
  "concepts": {
    "type_conversions": {
      "description": "Type casts, implicit conversions, coercion",
      "keywords": ["cast", "type conversion", "coercion", "as cast", "transmute", ...],
      "c_terms": ["type cast", "(T*)expr", "implicit conversion"],
      "rust_terms": ["as cast", "type coercion", "transmute"],
      "aliases": ["type_casts", "casting"],
      "fls_ids": ["fls_1qhsun1vyarz", ...],
      "fls_sections": ["6.5.10", ...],
      "reference_ids": ["expressions.operator-expr.type-cast", "type-coercions"],
      "ucg_ids": ["ucg_abi_of_a_type"],
      "nomicon_ids": ["nomicon_casts", "nomicon_transmutes"],
      "clippy_lints": ["cast_ptr_alignment", "transmute_ptr_to_ptr"],
      "typical_applicability_all_rust": "partial",
      "typical_applicability_safe_rust": "partial",
      "rationale": "..."
    }
  }
}
```

### New Fields Summary

| Field | Type | Description |
|-------|------|-------------|
| `c_terms` | `string[]` | C/MISRA terminology for this concept |
| `rust_terms` | `string[]` | Rust-specific terminology |
| `aliases` | `string[]` | Alternative keys that map to this concept |
| `reference_ids` | `string[]` | Rust Reference `r[...]` IDs |
| `ucg_ids` | `string[]` | UCG section IDs (synthetic `ucg_*`) |
| `nomicon_ids` | `string[]` | Nomicon section IDs (synthetic `nomicon_*`) |
| `clippy_lints` | `string[]` | Clippy lint names |

---

## Fuzzy Matching System

### Four-Layer Matching

When a user provides a concept name, the tool searches for existing matches using four layers (in order):

| Layer | Method | Example Match |
|-------|--------|---------------|
| 1. Exact | Key or alias exact match | `borrow_checking` = `borrow_checking` |
| 2. Normalized | Lowercase, strip `_-`, collapse spaces | `Borrow-Checking` → `borrowchecking` |
| 3. Token | Jaccard similarity of word tokens | `borrow_checker` ↔ `borrow_checking` (overlap: "borrow") |
| 4. Embedding | Cosine similarity of embeddings | `borrowck` ↔ `borrow_checking` (semantic) |

### Matching Thresholds

| Layer | Threshold | Action |
|-------|-----------|--------|
| Exact | 1.0 | Use existing concept (no prompt) |
| Normalized | 1.0 | Use existing concept (no prompt) |
| Token | ≥0.5 Jaccard | Prompt user with candidates |
| Embedding | ≥0.75 cosine | Prompt user with candidates |

### Embedding Strategy

- Embed: concept key + description + all keywords (concatenated)
- Use same model as FLS/Reference embeddings for consistency
- Cache embeddings for existing concepts (regenerate on file change)
- Compare query embedding against all concept embeddings

---

## Implementation Plan

### Phase 1: Schema and Validation Infrastructure

**Goal:** Define JSON schema, create ID validation utilities.

**Tasks:**
- [ ] Create JSON schema for enriched `concept_to_fls.json`
- [ ] Create `load_valid_ids()` utility that aggregates:
  - `tools/data/valid_fls_ids.json` (existing)
  - `tools/data/valid_reference_ids.json` (existing)
  - UCG IDs from `embeddings/ucg/chapter_*.json`
  - Nomicon IDs from `embeddings/nomicon/chapter_*.json`
  - Clippy lint names from `embeddings/clippy/lints.json`
- [ ] Create `validate_concept_ids()` function to check all IDs in a concept entry

**Output:**
- `coding-standards-fls-mapping/schema/concept_crosswalk.schema.json`
- `tools/src/fls_tools/standards/crosswalk/validation.py`

**Checkpoint:** Run `uv run validate-concept-crosswalk` on existing file (should pass with warnings about missing optional fields)

---

### Phase 2: Fuzzy Matching Module

**Goal:** Implement four-layer matching system.

**Tasks:**
- [ ] Create `tools/src/fls_tools/standards/crosswalk/matching.py`
- [ ] Implement `exact_match(query, concepts)` - key and alias lookup
- [ ] Implement `normalized_match(query, concepts)` - normalized string comparison
- [ ] Implement `token_match(query, concepts, threshold=0.5)` - Jaccard similarity
- [ ] Implement `embedding_match(query, concepts, threshold=0.75)` - cosine similarity
- [ ] Implement `find_similar_concepts(query, concepts)` - orchestrates all layers
- [ ] Add caching for concept embeddings

**Output:**
- `tools/src/fls_tools/standards/crosswalk/matching.py`

**Checkpoint:** Unit tests for each matching layer with known test cases:
- `borrow_checking` exact matches `borrow_checking`
- `Borrow-Checking` normalized matches `borrow_checking`
- `borrow_checker` token matches `borrow_checking`
- `borrowck` embedding matches `borrow_checking`

---

### Phase 3: Core `enrich-concept` Tool

**Goal:** Implement the main CLI tool for enriching concepts.

**Tasks:**
- [ ] Create `tools/src/fls_tools/standards/crosswalk/enrich.py`
- [ ] Implement argument parsing:
  ```
  --concept NAME          Concept key (or alias) to modify/create
  --show                  Display current concept state
  --description TEXT      Set/update description
  --add-keyword WORD      Add to keywords list
  --add-c-term TERM       Add to c_terms list
  --add-rust-term TERM    Add to rust_terms list
  --add-alias ALIAS       Add to aliases list
  --add-fls ID            Add FLS ID
  --add-reference ID      Add Reference ID
  --add-ucg ID            Add UCG ID
  --add-nomicon ID        Add Nomicon ID
  --add-clippy LINT       Add Clippy lint name
  --dry-run               Show changes without writing
  ```
- [ ] Implement concept lookup with fuzzy matching + user prompts
- [ ] Implement ID validation before adding
- [ ] Implement file update logic (preserve formatting, add to correct location)
- [ ] Add entry point to `pyproject.toml`

**Output:**
- `tools/src/fls_tools/standards/crosswalk/enrich.py`
- Entry point: `enrich-concept`

**Checkpoint:** Manual testing scenarios:
```bash
# Show existing concept
uv run enrich-concept --concept "type_conversions" --show

# Add reference ID to existing concept
uv run enrich-concept --concept "type_conversions" --add-reference "expressions.operator-expr.type-cast" --dry-run

# Try to create concept that fuzzy-matches existing
uv run enrich-concept --concept "borrowck" --description "test"
# Should prompt: "Similar to existing 'borrow_checking'. Use existing? [Y/n]"

# Create genuinely new concept
uv run enrich-concept --concept "drop_glue" --description "Compiler-generated destructor code" --add-rust-term "drop glue" --add-fls "fls_u2mzjgiwbkz0"
```

---

### Phase 4: Validation Tool

**Goal:** Standalone validation for the entire concept crosswalk file.

**Tasks:**
- [ ] Create `tools/src/fls_tools/standards/crosswalk/validate.py`
- [ ] Validate against JSON schema
- [ ] Validate all IDs in all concepts
- [ ] Check for duplicate aliases across concepts
- [ ] Check for orphaned aliases (alias that doesn't point to valid key)
- [ ] Report statistics (concepts count, IDs per source, etc.)
- [ ] Add entry point to `pyproject.toml`

**Output:**
- `tools/src/fls_tools/standards/crosswalk/validate.py`
- Entry point: `validate-concept-crosswalk`

**Checkpoint:**
```bash
uv run validate-concept-crosswalk
# Should report: 53 concepts, X FLS IDs, Y Reference IDs, etc.
# Should warn about any invalid IDs
```

---

### Phase 5: Integration and Documentation

**Goal:** Update AGENTS.md and plan document, test end-to-end workflow.

**Tasks:**
- [ ] Update AGENTS.md with new tools and workflow
- [ ] Update this plan document with completion status
- [ ] Update `docs/rust-context-search-infrastructure.md` Phase 9 status
- [ ] Test full workflow:
  1. Run `search-rust-context` for a MISRA guideline
  2. Find useful Reference/Nomicon/Clippy hits
  3. Use `enrich-concept` to record cross-references
  4. Verify with `validate-concept-crosswalk`

**Output:**
- Updated AGENTS.md
- Updated plan documents

**Checkpoint:** Successfully enrich 3-5 concepts with real data from verification workflow.

---

## File Structure

```
tools/src/fls_tools/standards/crosswalk/
├── __init__.py
├── enrich.py           # enrich-concept CLI
├── validate.py         # validate-concept-crosswalk CLI
├── matching.py         # Four-layer fuzzy matching
└── validation.py       # ID validation utilities

coding-standards-fls-mapping/
├── schema/
│   └── concept_crosswalk.schema.json  # NEW
└── concept_to_fls.json                # ENRICHED
```

## Entry Points (pyproject.toml)

```toml
enrich-concept = "fls_tools.standards.crosswalk.enrich:main"
validate-concept-crosswalk = "fls_tools.standards.crosswalk.validate:main"
```

---

## Progress Tracking

| Phase | Description | Status | Date |
|-------|-------------|--------|------|
| 1 | Schema and Validation Infrastructure | Complete | 2026-01-03 |
| 2 | Fuzzy Matching Module | Complete | 2026-01-03 |
| 3 | Core `enrich-concept` Tool | Complete | 2026-01-03 |
| 4 | Validation Tool | Complete | 2026-01-03 |
| 5 | Integration and Documentation | Complete | 2026-01-03 |

---

## Open Questions

1. **Embedding model:** Use same model as FLS (`all-MiniLM-L6-v2`)? Or a different one optimized for short phrases?
   - **Tentative:** Use same model for consistency.

2. **Concept embedding caching:** Store in `.pkl` file alongside `concept_to_fls.json`, or in `embeddings/` directory?
   - **Tentative:** Store in `embeddings/concepts/embeddings.pkl` for consistency with other embedding files.

3. **Alias collision detection:** If user tries to add alias that exists as another concept's key or alias, should we error or prompt for merge?
   - **Tentative:** Error with explanation. Merging concepts is complex and should be manual.

---

## Dependencies

- Existing embedding infrastructure (`sentence-transformers`)
- Existing valid ID files (`valid_fls_ids.json`, `valid_reference_ids.json`)
- Extracted chapter files for UCG/Nomicon ID validation

---

## Related Documents

- [`docs/rust-context-search-infrastructure.md`](../docs/rust-context-search-infrastructure.md) - Phase 9 references this work
- [`AGENTS.md`](../AGENTS.md) - Will need updates for new tools
- [`coding-standards-fls-mapping/concept_to_fls.json`](../coding-standards-fls-mapping/concept_to_fls.json) - File being enriched
