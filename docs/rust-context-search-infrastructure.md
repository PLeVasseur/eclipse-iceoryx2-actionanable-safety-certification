# Rust Context Search Infrastructure

**Status:** Planning  
**Created:** 2026-01-03  
**Last Updated:** 2026-01-03

## Overview

This document describes the plan to add Rust-specific documentation sources to the verification workflow. The goal is to provide richer context when mapping MISRA C guidelines to Rust, helping determine whether:

- Rust has the same problem (→ `direct_mapping`)
- Rust solves it differently (→ `rust_alternative`)
- Rust's design prevents it (→ `rust_prevents`)
- The concept doesn't exist in Rust (→ `no_equivalent`)

## Motivation

Currently, the verification workflow searches the FLS directly using MISRA guideline text and manually-crafted queries. This can miss relevant context because:

1. MISRA uses C terminology that doesn't map directly to Rust concepts
2. The FLS is formal/normative but doesn't explain *why* Rust works the way it does
3. Unsafe Rust semantics are documented elsewhere (UCG, Nomicon)
4. Existing Rust tooling (Clippy) already addresses some MISRA-like concerns

By searching additional Rust documentation sources *before* the FLS, we can:
- Get better "steering" terms for FLS searches
- Find authoritative explanations of Rust mechanisms
- Identify existing tooling coverage
- Make more informed rationale type decisions

## Data Sources

| Source | Repository/URL | Focus | Priority |
|--------|---------------|-------|----------|
| **Rust Reference** | https://github.com/rust-lang/reference | Authoritative language reference (safe + unsafe) | 1 |
| **Unsafe Code Guidelines (UCG)** | https://github.com/rust-lang/unsafe-code-guidelines | Formal unsafe semantics | 2 |
| **Rustonomicon** | https://github.com/rust-lang/nomicon | Practical unsafe Rust guide | 3 |
| **Clippy Lints** | https://github.com/rust-lang/rust-clippy | ~700 lints with descriptions | 4 |

### Source Details

#### Rust Reference
- **Format:** mdBook (Markdown)
- **Structure:** `SUMMARY.md` defines hierarchy, `src/*.md` contains content
- **Value:** Covers all Rust language features, both safe and unsafe
- **Granularity:** Chapters → Sections → Paragraphs

#### Unsafe Code Guidelines (UCG)
- **Format:** mdBook (Markdown)
- **Structure:** Similar to Reference
- **Value:** Precise semantics for validity invariants, aliasing, layout, provenance
- **Granularity:** Chapters → Sections → Paragraphs

#### Rustonomicon
- **Format:** mdBook (Markdown)
- **Structure:** Similar to Reference
- **Value:** Practical guide with examples of safe unsafe patterns
- **Granularity:** Chapters → Sections → Paragraphs

#### Clippy Lints
- **Format:** Rust source + rendered HTML docs
- **Structure:** Lint definitions in `clippy_lints/src/`, metadata extractable
- **Value:** Shows existing tooling coverage for safety concerns
- **Granularity:** Individual lints (name, category, description, example)

**Clippy Categories:**
| Category | Description | Search Weight |
|----------|-------------|---------------|
| `correctness` | Code that is definitely wrong | 1.2x |
| `suspicious` | Code that is probably wrong | 1.15x |
| `complexity` | Code that is unnecessarily complex | 1.0x |
| `perf` | Performance improvements | 1.0x |
| `style` | Style/idiom improvements | 1.0x |
| `pedantic` | Very strict lints | 1.0x |
| `restriction` | Lints restricting certain patterns | 1.0x |
| `nursery` | Experimental lints | 0.9x |

---

## Implementation Plan

### Phase 1: Repository Acquisition

**Goal:** Clone all 4 source repositories to a local cache.

**Output:**
```
cache/docs/
├── reference/                # rust-lang/reference
├── unsafe-code-guidelines/   # rust-lang/unsafe-code-guidelines
├── nomicon/                  # rust-lang/nomicon
└── rust-clippy/              # rust-lang/rust-clippy
```

**Tool:** `clone-rust-docs`

```bash
uv run clone-rust-docs              # Clone/update all sources
uv run clone-rust-docs --source reference  # Clone specific source
```

**Status:** [ ] Not started

---

### Phase 2: Content Extraction - Rust Reference

**Goal:** Extract Reference content into structured JSON with embeddings.

**Output:**
```
embeddings/reference/
├── index.json                # Chapter/section listing with metadata
├── chapter_01.json           # Per-chapter content
├── chapter_02.json
├── ...
├── embeddings.pkl            # Section-level embeddings
└── paragraph_embeddings.pkl  # Paragraph-level embeddings
```

**JSON Structure:** Mirror FLS structure for consistency:
```json
{
  "chapter": 6,
  "title": "Items",
  "sections": [
    {
      "id": "ref_items_modules",
      "title": "Modules",
      "level": 2,
      "content": "...",
      "parent_id": null,
      "paragraphs": {
        "ref_items_modules_p1": "A module is a container for...",
        "ref_items_modules_p2": "Modules can be nested..."
      }
    }
  ]
}
```

**Tool:** `extract-reference`

```bash
uv run extract-reference            # Extract all chapters
uv run extract-reference --chapter 6  # Extract specific chapter
```

**Status:** [ ] Not started

---

### Phase 3: Content Extraction - UCG

**Goal:** Extract UCG content into structured JSON with embeddings.

**Output:**
```
embeddings/ucg/
├── index.json
├── chapter_01.json
├── ...
├── embeddings.pkl
└── paragraph_embeddings.pkl
```

**Tool:** `extract-ucg`

```bash
uv run extract-ucg
```

**Status:** [ ] Not started

---

### Phase 4: Content Extraction - Nomicon

**Goal:** Extract Nomicon content into structured JSON with embeddings.

**Output:**
```
embeddings/nomicon/
├── index.json
├── chapter_01.json
├── ...
├── embeddings.pkl
└── paragraph_embeddings.pkl
```

**Tool:** `extract-nomicon`

```bash
uv run extract-nomicon
```

**Status:** [ ] Not started

---

### Phase 5: Content Extraction - Clippy

**Goal:** Extract all ~700 Clippy lints with metadata and embeddings.

**Output:**
```
embeddings/clippy/
├── index.json                # Category listing and statistics
├── lints.json                # All lints with full descriptions
├── embeddings.pkl            # Lint-level embeddings
└── by_category/              # Optional: lints grouped by category
    ├── correctness.json
    ├── suspicious.json
    └── ...
```

**Lint JSON Structure:**
```json
{
  "name": "cast_ptr_alignment",
  "category": "correctness",
  "level": "deny",
  "description": "Checks for casts from a less-aligned pointer to a more-aligned pointer",
  "rationale": "Dereferencing a misaligned pointer is undefined behavior...",
  "example_bad": "let ptr = &1u8 as *const u8 as *const u64;",
  "example_good": "// Use proper alignment or transmute with care",
  "applicability": "MachineApplicable",
  "search_weight": 1.2
}
```

**Tool:** `extract-clippy-lints`

```bash
uv run extract-clippy-lints
```

**Status:** [ ] Not started

---

### Phase 6: Embedding Generation

**Goal:** Generate embeddings for all extracted content using the same model as FLS.

**Tool:** `generate-embeddings` (extend existing)

```bash
# Existing FLS embeddings
uv run generate-embeddings --source fls

# New sources
uv run generate-embeddings --source reference
uv run generate-embeddings --source ucg
uv run generate-embeddings --source nomicon
uv run generate-embeddings --source clippy

# All at once
uv run generate-embeddings --source all
```

**Embedding Model:** Same as FLS (verify current model and document).

**Status:** [ ] Not started

---

### Phase 7: Search Tool

**Goal:** Create unified search tool across all Rust documentation sources.

**Tool:** `search-rust-context`

```bash
# Search by MISRA guideline
uv run search-rust-context --guideline "Rule 11.3" --top 10

# Search by custom query
uv run search-rust-context --query "pointer aliasing alignment" --top 10

# Filter to specific sources
uv run search-rust-context --guideline "Rule 11.3" --sources ucg,nomicon

# Include/exclude Clippy
uv run search-rust-context --guideline "Rule 11.3" --no-clippy
```

**Output Format:**
```
============================================================
RUST CONTEXT SEARCH: Rule 11.3
============================================================
Guideline: A cast shall not be performed between a pointer to 
           object type and a pointer to a different object type

MISRA ADD-6 Context:
  Rationale: UB, DC
  All Rust: Yes (advisory)
  Safe Rust: No (n_a)

------------------------------------------------------------
RUST REFERENCE (3 matches)
------------------------------------------------------------
1. [0.74] Type Cast Expressions
   "Casting between two integers of the same size is a no-op..."
   Key concepts: cast, pointer, type coercion
   
2. [0.69] Pointer Types
   "Raw pointers *const T and *mut T..."

3. [0.62] Type Coercions
   "Coercions are implicit type conversions..."

------------------------------------------------------------
UNSAFE CODE GUIDELINES (2 matches)
------------------------------------------------------------
1. [0.72] Pointer Validity
   "A pointer is valid if it points to allocated memory..."
   Key concepts: validity, alignment, provenance

2. [0.68] Type Layout
   "The layout of a type defines its size and alignment..."

------------------------------------------------------------
RUSTONOMICON (2 matches)
------------------------------------------------------------
1. [0.75] Casts
   "The as keyword allows explicit type conversions..."
   Key concepts: as cast, transmute, pointer cast

2. [0.64] Working with Unsafe
   "Unsafe code must uphold certain invariants..."

------------------------------------------------------------
CLIPPY LINTS (3 matches)
------------------------------------------------------------
1. cast_ptr_alignment [correctness] (weight: 1.2x)
   "Checks for casts from a less-aligned to more-aligned pointer"
   
2. transmute_ptr_to_ptr [complexity]
   "Checks for transmutes between pointers to different types"

3. ptr_as_ptr [pedantic]
   "Checks for as casts between raw pointers"

------------------------------------------------------------
SUGGESTED FLS QUERIES (LLM-generated)
------------------------------------------------------------
Based on matches, consider searching FLS for:
  • "type cast expression"
  • "pointer type raw"
  • "type coercion"
  • "alignment layout"

Search ID: <uuid>
```

**Query Suggestion Generation:**
- Use LLM to analyze matched content and generate relevant FLS search queries
- Fall back to keyword extraction if LLM unavailable

**Status:** [ ] Not started

---

### Phase 8: Workflow Integration

**Goal:** Update verification workflow to use context search.

**Updated Protocol:**
```bash
# Step 0: Rust context search (NEW - always first)
uv run search-rust-context --guideline "Rule X.Y"

# Step 1: Deep FLS search  
uv run search-fls-deep --standard misra-c --guideline "Rule X.Y"

# Steps 2-4: Keyword FLS searches (informed by context suggestions)
uv run search-fls --query "<from context suggestions>" --top 10
uv run search-fls --query "<rust terminology>" --top 10
uv run search-fls --query "<additional angles>" --top 10
```

**Search Tracking:**
```bash
uv run record-decision \
    --search-used "uuid:search-rust-context:Rule 11.3:10" \
    --search-used "uuid:search-fls-deep:Rule 11.3:5" \
    ...
```

**AGENTS.md Updates:**
- Document `search-rust-context` tool
- Update verification protocol to require context search first
- Document the 4 data sources and their purposes

**Status:** [ ] Not started

---

### Phase 9: Concept Crosswalk Enrichment

**Goal:** Enrich existing `concept_to_fls.json` with cross-references to new sources.

**Current File:** `coding-standards-fls-mapping/concept_to_fls.json`

**Enriched Structure:**
```json
{
  "pointer cast": {
    "c_terms": ["pointer cast", "type punning", "(T*)expr"],
    "rust_terms": ["as cast", "raw pointer cast", "transmute"],
    "fls_sections": ["fls_1qhsun1vyarz"],
    "reference_sections": ["ref_type_cast_expressions"],
    "ucg_sections": ["ucg_pointer_validity", "ucg_type_layout"],
    "nomicon_sections": ["nomicon_casts", "nomicon_transmutes"],
    "clippy_lints": ["cast_ptr_alignment", "transmute_ptr_to_ptr"]
  }
}
```

**Approach:** Build incrementally as we verify guidelines, capturing mappings discovered during the process.

**Status:** [ ] Not started

---

## Progress Tracking

### Overall Progress

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Repository Acquisition | [ ] Not started | |
| 2 | Extract Reference | [ ] Not started | |
| 3 | Extract UCG | [ ] Not started | |
| 4 | Extract Nomicon | [ ] Not started | |
| 5 | Extract Clippy | [ ] Not started | |
| 6 | Generate Embeddings | [ ] Not started | |
| 7 | Search Tool | [ ] Not started | |
| 8 | Workflow Integration | [ ] Not started | |
| 9 | Concept Crosswalk | [ ] Not started | |

### Session Log

| Date | Session | Work Done |
|------|---------|-----------|
| 2026-01-03 | 1 | Created this plan document |

---

## Open Questions

1. **Embedding model verification:** What model are we currently using for FLS embeddings? Need to verify and document for consistency.

2. **Reference vs FLS overlap:** The Rust Reference and FLS cover similar ground. How do we handle overlap/deduplication in search results?

3. **Clippy version pinning:** Should we pin to a specific Clippy version, or always use latest?

4. **LLM for query suggestions:** Which LLM/API should be used for generating FLS query suggestions from context matches?

5. **Incremental updates:** How often should we refresh the cloned repos? On each verification session? Weekly?

---

## Related Documents

- [`AGENTS.md`](../AGENTS.md) - Tool documentation and verification workflow
- [`docs/future/cross-reference-analysis.md`](future/cross-reference-analysis.md) - Future cross-reference plans
- [`coding-standards-fls-mapping/concept_to_fls.json`](../coding-standards-fls-mapping/concept_to_fls.json) - Existing concept mappings
