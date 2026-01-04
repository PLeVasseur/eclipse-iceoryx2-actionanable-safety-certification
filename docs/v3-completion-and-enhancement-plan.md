# v3 Schema Completion and MISRA ADD-6 Enhancement Plan

This document outlines the plan to:
1. Complete the migration of remaining v1.1 entries to v3.0 format
2. Enhance verification workflow with deeper MISRA ADD-6 integration

**Created:** 2026-01-03  
**Status:** Planning  

---

## Executive Summary

### Current State

| Schema Version | Count | Percentage | Description |
|----------------|-------|------------|-------------|
| v1.0 | 0 | 0% | All migrated to v1.1 |
| v1.1 | 77 | 34.5% | Legacy flat structure + ADD-6 (batches 3, 4, 5) |
| v2.0 | 0 | 0% | All migrated to v2.1 |
| v2.1 | 108 | 48.4% | Per-context structure + ADD-6 (batches 1, 2 - partial v3 conversion) |
| v3.0 | 38 | 17.1% | Fresh verification with ADD-6 |
| **Total** | **223** | **100%** | |

### Migration Goals

1. **Complete v3.0 Migration:** Convert all remaining 185 entries (77 v1.1 + 108 v2.1) to v3.0 format
2. **Enhanced ADD-6 Integration:** Make MISRA ADD-6 data more prominent in verification workflow
3. **Tool Improvements:** Update batch.py and search tools to surface ADD-6 context

### Key Distinction

| Version | Source | Characteristics |
|---------|--------|-----------------|
| v1.1/v2.1 | Migration enrichment | Legacy structure + ADD-6 block added |
| v3.0 | Fresh verification OR migration upgrade | Per-context structure with ADD-6, verified FLS mappings |

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Schema Differences](#schema-differences)
3. [Migration Plan by File Type](#migration-plan-by-file-type)
4. [Tool Enhancement Plan](#tool-enhancement-plan)
5. [Implementation Phases](#implementation-phases)
6. [Progress Tracking](#progress-tracking)

---

## Current State Analysis

### Mapping File Inventory by Batch

| Batch | Name | Guidelines | Current Version | Target Version |
|-------|------|------------|-----------------|----------------|
| 1 | High-score direct | 20 | v2.1 | v3.0 (via verification) |
| 2 | Not applicable | 88 | v2.1 | v3.0 (via verification) |
| 3 | Stdlib & Resources | 38 | v1.1 (partially v3.0) | v3.0 |
| 4 | Medium-score direct | 55 | v1.1 | v3.0 |
| 5 | Edge cases | 22 | v1.1 | v3.0 |

### Current ADD-6 Data Sources

**Primary Source:** `coding-standards-fls-mapping/misra_rust_applicability.json`

Contains 228 guideline entries with:
- `misra_category` (Required/Advisory/Mandatory)
- `decidability` (Decidable/Undecidable/n/a)
- `scope` (STU/System/n/a)
- `rationale` array (UB/IDB/CQ/DC)
- `applicability_all_rust` (Yes/No/Partial)
- `applicability_safe_rust` (Yes/No/Partial)
- `adjusted_category` (required/advisory/recommended/disapplied/implicit/n_a)
- `comment` (Rust-specific notes)

### Files That Need Migration

| File Type | Location | Current State | Migration Needed |
|-----------|----------|---------------|------------------|
| Mapping file | `mappings/misra_c_to_fls.json` | Mixed v1.1/v2.1/v3.0 | Yes - upgrade to all v3.0 |
| Batch reports | `cache/verification/misra-c/` | Generated per-session | No - already v3.0 |
| Decision files | `cache/verification/.../decisions/` | Created per-session | No - already v3.0 |
| Progress file | `verification/misra-c/progress.json` | v2.0 format | No change needed |

---

## Schema Differences

### v1.1 Structure (Legacy Enriched)

```json
{
  "schema_version": "1.1",
  "guideline_id": "Rule 21.3",
  "guideline_title": "...",
  "guideline_type": "rule",
  "applicability_all_rust": "direct",        // Legacy enum values
  "applicability_safe_rust": "not_applicable",
  "fls_rationale_type": "rust_prevents",
  "misra_rust_category": "required",
  "confidence": "medium",
  "accepted_matches": [...],                  // Shared across both contexts
  "rejected_matches": [],
  "notes": "...",
  "misra_add6": {                             // ADD-6 block added by migration
    "misra_category": "Required",
    "decidability": "Undecidable",
    "scope": "System",
    "rationale_codes": ["UB"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "advisory",
    "comment": "...",
    "source_version": "ADD-6:2025"
  }
}
```

**v1.1 Limitations:**
- Flat structure: single `accepted_matches` for both contexts
- Legacy applicability values (`direct`, `partial`, `not_applicable`, `rust_prevents`)
- No per-context verification tracking
- No per-context confidence levels

### v2.1 Structure (Per-Context Enriched)

```json
{
  "schema_version": "2.1",
  "guideline_id": "Rule 11.1",
  "guideline_title": "...",
  "guideline_type": "rule",
  "misra_add6": { ... },                      // ADD-6 block
  "all_rust": {
    "applicability": "yes",                   // ADD-6 aligned values
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [...],                // Context-specific matches
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "..."
  },
  "safe_rust": {
    "applicability": "no",
    "adjusted_category": "n_a",
    "rationale_type": "rust_prevents",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "..."
  }
}
```

**v2.1 vs v3.0:** Structurally identical. The version number indicates:
- v2.1 = Existing v2.0 entry enriched with ADD-6 via migration tool
- v3.0 = Fresh verification decision or upgraded entry

### v3.0 Structure (Fresh Verification)

```json
{
  "schema_version": "3.0",
  "guideline_id": "Rule 21.3",
  "guideline_title": "...",
  "guideline_type": "rule",
  "misra_add6": {
    "misra_category": "Required",
    "decidability": "Undecidable",
    "scope": "System",
    "rationale_codes": ["UB"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "advisory",
    "comment": "Safe Rust has no direct heap allocation functions",
    "source_version": "ADD-6:2025"
  },
  "all_rust": {
    "applicability": "yes",
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [
      {
        "fls_id": "fls_abc123",
        "fls_title": "Section Title",
        "category": 0,
        "score": 0.65,
        "reason": "FLS states X which addresses MISRA concern Y"
      }
    ],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 5,
    "notes": "..."
  },
  "safe_rust": {
    "applicability": "no",
    "adjusted_category": "n_a",
    "rationale_type": "rust_prevents",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 5,
    "notes": "Safe Rust prevents this issue entirely"
  }
}
```

---

## Migration Plan by File Type

### 1. Mapping File Migration

**File:** `coding-standards-fls-mapping/mappings/misra_c_to_fls.json`

#### Option A: Verification-Based Migration (Recommended)

Continue the existing verification workflow for remaining batches. Each guideline is migrated to v3.0 when verified.

**Pros:**
- Fresh human-verified FLS matches
- Per-context decisions
- High-quality output

**Cons:**
- Time-consuming (185 guidelines remaining)
- Requires LLM verification sessions

**Process:**
1. Continue batch 3 verification (38 guidelines, some already v3.0)
2. Verify batch 4 (55 guidelines)
3. Verify batch 5 (22 guidelines)
4. Re-verify batches 1 & 2 to upgrade v2.1 → v3.0 (108 guidelines)

#### Option B: Automated Migration Tool

Create a migration tool that converts v1.1/v2.1 → v3.0 without re-verification.

**v1.1 → v3.0 Conversion Logic:**

```python
def migrate_v1_1_to_v3(entry: dict, add6: dict) -> dict:
    """Convert v1.1 entry to v3.0 format."""
    gid = entry["guideline_id"]
    
    # Map legacy applicability values to ADD-6 values
    app_map = {
        "direct": "yes",
        "partial": "partial",
        "not_applicable": "no",
        "rust_prevents": "no",  # rust_prevents → no, with rationale_type explaining
        "unmapped": "partial"
    }
    
    # Infer adjusted_category from legacy values
    cat_map = {
        "direct": "advisory",
        "partial": "advisory",
        "not_applicable": "n_a",
        "rust_prevents": "implicit"
    }
    
    return {
        "schema_version": "3.0",
        "guideline_id": gid,
        "guideline_title": entry["guideline_title"],
        "guideline_type": entry.get("guideline_type", "rule"),
        "misra_add6": entry.get("misra_add6", build_add6_block(add6.get(gid, {}))),
        "all_rust": {
            "applicability": app_map.get(entry["applicability_all_rust"], "partial"),
            "adjusted_category": add6.get(gid, {}).get("adjusted_category", 
                                 cat_map.get(entry["applicability_all_rust"], "advisory")),
            "rationale_type": entry["fls_rationale_type"],
            "confidence": entry["confidence"],
            "accepted_matches": entry["accepted_matches"],
            "rejected_matches": entry.get("rejected_matches", []),
            "verified": False,  # Mark as NOT verified (migrated only)
            "verified_by_session": None,
            "notes": entry.get("notes", "")
        },
        "safe_rust": {
            "applicability": app_map.get(entry["applicability_safe_rust"], "partial"),
            "adjusted_category": add6.get(gid, {}).get("adjusted_category_safe", 
                                 cat_map.get(entry["applicability_safe_rust"], "n_a")),
            "rationale_type": entry["fls_rationale_type"],
            "confidence": entry["confidence"],
            "accepted_matches": entry["accepted_matches"],  # Shared in v1.1
            "rejected_matches": entry.get("rejected_matches", []),
            "verified": False,
            "verified_by_session": None,
            "notes": entry.get("notes", "")
        }
    }
```

**v2.1 → v3.0 Conversion Logic:**

```python
def migrate_v2_1_to_v3(entry: dict) -> dict:
    """Convert v2.1 entry to v3.0 format (version bump only)."""
    entry["schema_version"] = "3.0"
    return entry
```

**Pros:**
- Fast (automated)
- Consistent structure

**Cons:**
- v1.1 entries get shared matches for both contexts (not ideal)
- `verified: false` indicates incomplete verification
- Requires follow-up verification to set `verified: true`

#### Recommended Approach: Hybrid

1. **Immediate:** Use automated migration for structural consistency (all entries become v3.0)
2. **Ongoing:** Continue verification to upgrade `verified: false` → `verified: true`
3. **Tracking:** Progress file tracks which entries are fully verified

### 2. Batch Report (No Migration Needed)

**Current State:** `batch.py` already generates v3.0 batch reports with `misra_add6` block.

**Files Affected:** `cache/verification/misra-c/batch*_session*.json`

**Enhancement Opportunities:**
- Surface ADD-6 data more prominently in human-readable mode
- Pre-populate verification decisions based on ADD-6 adjusted_category
- Highlight conflicts between current mapping and ADD-6 guidance

### 3. Decision File (No Migration Needed)

**Current State:** `record.py` already creates v3.0 decision files with `misra_add6_snapshot`.

**Files Affected:** `cache/verification/misra-c/batch*_decisions/*.json`

**Enhancement Opportunities:**
- Validate recorded decisions against ADD-6 guidance
- Warn when `adjusted_category` differs from ADD-6
- Warn when `applicability` differs from ADD-6

---

## Tool Enhancement Plan

### 1. batch.py Enhancements

**Current State:**
- Loads ADD-6 data from `misra_rust_applicability.json`
- Includes `misra_add6` block in batch reports
- v3.0 batch reports already work correctly

**Proposed Enhancements:**

#### Enhancement 1.1: ADD-6 Alignment Warnings

Add warnings when current mapping state conflicts with ADD-6 guidance:

```python
def check_add6_alignment(current_state: dict, add6: dict, guideline_id: str) -> list[str]:
    """Check for conflicts between current mapping and ADD-6 guidance."""
    warnings = []
    
    # Check applicability_all_rust
    curr_app = current_state.get("applicability_all_rust", "")
    add6_app = add6.get("applicability_all_rust", "")
    if curr_app and add6_app:
        curr_normalized = normalize_applicability(curr_app)  # "direct" -> "yes"
        add6_normalized = add6_app.lower()
        if curr_normalized != add6_normalized:
            warnings.append(
                f"all_rust applicability mismatch: mapping={curr_app} vs ADD-6={add6_app}"
            )
    
    # Check adjusted_category
    curr_cat = current_state.get("misra_rust_category", "")
    add6_cat = add6.get("adjusted_category", "")
    if curr_cat and add6_cat and curr_cat != add6_cat:
        warnings.append(
            f"adjusted_category mismatch: mapping={curr_cat} vs ADD-6={add6_cat}"
        )
    
    return warnings
```

**Output in batch report:**
```json
{
  "guideline_id": "Rule 21.3",
  "add6_alignment_warnings": [
    "all_rust applicability mismatch: mapping=direct vs ADD-6=Yes (compatible)",
    "adjusted_category mismatch: mapping=required vs ADD-6=advisory"
  ],
  ...
}
```

#### Enhancement 1.2: Human Mode ADD-6 Summary

In `--mode human`, include ADD-6 summary table:

```
============================================================
BATCH 3: Stdlib & Resources
============================================================

ADD-6 Summary for this batch:
  Applicability All Rust:   Yes: 25, No: 8, Partial: 5
  Applicability Safe Rust:  Yes: 15, No: 20, Partial: 3
  Adjusted Category:        required: 10, advisory: 12, disapplied: 8, implicit: 5, n_a: 3
  
Guidelines:
  Rule 21.1 - #define and #undef shall not be used
    ADD-6: Required | Decidable | STU | Rationale: UB, CQ
    All Rust: No -> n_a (no preprocessor)
    Safe Rust: No -> n_a
    Current: not_applicable (medium confidence)
    Alignment: OK
```

#### Enhancement 1.3: Pre-populated Suggestions

For v1.1 entries being verified, suggest initial values based on ADD-6:

```json
{
  "verification_decision": {
    "all_rust": {
      "suggested_applicability": "yes",        // From ADD-6
      "suggested_adjusted_category": "advisory", // From ADD-6
      "suggested_rationale_type": null,         // Verifier must determine
      ...
    }
  }
}
```

### 2. search.py Enhancements

**Current State:**
- Supports `--for-guideline` parameter to display ADD-6 context
- Already implemented in Phase 4 of v2-to-v3 migration

**Proposed Enhancements:**

#### Enhancement 2.1: Rationale-Informed Query Expansion

When `--for-guideline` is provided, automatically expand queries based on ADD-6 rationale codes:

```python
RATIONALE_QUERY_HINTS = {
    "UB": ["undefined behavior", "safety", "memory safety"],
    "IDB": ["implementation-defined", "platform-specific", "ABI"],
    "CQ": ["code quality", "maintainability", "readability"],
    "DC": ["design", "architecture", "modularity"]
}

def get_query_hints(add6: dict) -> list[str]:
    """Get additional search hints based on ADD-6 rationale codes."""
    hints = []
    for code in add6.get("rationale", []):
        hints.extend(RATIONALE_QUERY_HINTS.get(code, []))
    return hints
```

**Output:**
```
Search ID: abc123...

Query: "memory allocation"
ADD-6 Hints: "undefined behavior", "safety", "memory safety" (from UB rationale)

Consider also searching for:
  - "Drop trait" (ownership/cleanup)
  - "Box allocator" (heap allocation)
```

### 3. search_deep.py Enhancements

**Current State:**
- Displays ADD-6 context in header (implemented in Phase 4)
- Supports `--no-add6` flag to suppress

**Proposed Enhancements:**

#### Enhancement 3.1: Contextual Guidance Based on ADD-6

When ADD-6 indicates specific applicability, provide guidance:

```
======================================================================
DEEP SEARCH RESULTS: Rule 20.1 (#include directives)
======================================================================

MISRA ADD-6 Context:
  Original Category: Advisory
  Decidability: Decidable
  Scope: STU
  Rationale: CQ (Code Quality)
  All Rust: No -> n_a
  Safe Rust: No -> n_a
  Comment: Rust has no preprocessor

VERIFICATION GUIDANCE:
  ADD-6 indicates N/A for both contexts. Focus on finding FLS sections
  that explain WHY the C concept doesn't exist in Rust:
  - Module system (replaces #include)
  - Visibility rules (replaces header guards)
  - No preprocessor (fundamental difference)
  
  Suggested rationale_type: no_equivalent
```

#### Enhancement 3.2: See-Also From Similar ADD-6 Profile

Find related guidelines with similar ADD-6 characteristics:

```
Related Guidelines (similar ADD-6 profile):
  Rule 20.2: Same applicability (No/No), same rationale (CQ)
  Rule 20.3: Same applicability (No/No), same rationale (CQ)
  Rule 20.4: Same applicability (Partial/Partial), similar rationale
```

### 4. record.py Enhancements

**Current State:**
- Creates v3.0 decision files with `misra_add6_snapshot`
- Validates FLS IDs against known valid IDs
- Requires at least 4 searches per context

**Proposed Enhancements:**

#### Enhancement 4.1: ADD-6 Alignment Validation

Warn (but don't fail) when recorded decision conflicts with ADD-6:

```bash
uv run record-decision \
    --standard misra-c \
    --batch 3 \
    --guideline "Rule 21.3" \
    --context all_rust \
    --applicability no \           # ADD-6 says "Yes"
    --adjusted-category n_a \      # ADD-6 says "advisory"
    ...

# Output:
WARNING: Recorded applicability 'no' differs from ADD-6 'Yes'
WARNING: Recorded adjusted_category 'n_a' differs from ADD-6 'advisory'
Decision recorded. Consider reviewing alignment with MISRA ADD-6 guidance.
```

#### Enhancement 4.2: Default Value Suggestions

When values aren't provided, suggest defaults from ADD-6:

```bash
uv run record-decision \
    --standard misra-c \
    --batch 3 \
    --guideline "Rule 21.3" \
    --context all_rust \
    # --applicability not provided
    ...

# Output:
NOTE: --applicability not provided. ADD-6 suggests 'Yes' for all_rust context.
Use --applicability yes to accept, or specify a different value.
```

---

## Implementation Phases

### Phase 1: Automated v1.1/v2.1 → v3.0 Migration Tool

**Priority:** High  
**Effort:** Medium  
**Dependencies:** None

**Tasks:**
1. Create `upgrade-to-v3` tool in `tools/src/fls_tools/standards/verification/`
2. Implement v1.1 → v3.0 conversion with proper field mapping
3. Implement v2.1 → v3.0 conversion (version bump)
4. Mark migrated entries with `verified: false`
5. Test with dry-run mode
6. Run migration on `misra_c_to_fls.json`
7. Update schema counts in progress file

**Deliverable:** All 223 entries at v3.0, with clear verified/unverified distinction

### Phase 2: batch.py ADD-6 Enhancements

**Priority:** Medium  
**Effort:** Medium  
**Dependencies:** Phase 1 (for consistent v3.0 entries)

**Tasks:**
1. Implement ADD-6 alignment checking
2. Add warnings to batch report JSON
3. Enhance human mode output with ADD-6 summary
4. Add pre-populated suggestions for unverified entries
5. Test with existing batch reports

**Deliverable:** Richer batch reports with ADD-6 context

### Phase 3: Search Tool Enhancements

**Priority:** Medium  
**Effort:** Low  
**Dependencies:** None

**Tasks:**
1. Add rationale-informed query hints to `search.py`
2. Add contextual guidance to `search_deep.py`
3. Add similar ADD-6 profile suggestions
4. Test with representative guidelines

**Deliverable:** More helpful search output for verifiers

### Phase 4: record.py Enhancements

**Priority:** Low  
**Effort:** Low  
**Dependencies:** Phase 1 (for consistent v3.0 structure)

**Tasks:**
1. Add ADD-6 alignment validation (warnings)
2. Add default value suggestions from ADD-6
3. Update help text with ADD-6 guidance
4. Test with various scenarios

**Deliverable:** Smarter decision recording with ADD-6 awareness

### Phase 5: Verification Continuation

**Priority:** High  
**Effort:** High (ongoing)  
**Dependencies:** Phases 1-4

**Tasks:**
1. Continue batch 3 verification (remaining guidelines)
2. Verify batch 4 (55 guidelines)
3. Verify batch 5 (22 guidelines)
4. Re-verify batches 1 & 2 if needed (upgrade v3.0 unverified → verified)
5. Track progress in `verification_progress.json`

**Deliverable:** All 223 entries verified with `verified: true`

---

## Progress Tracking

### Phase 1: Migration Tool

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 1.1 | Create `upgrade-to-v3.py` module | pending | |
| 1.2 | Implement v1.1 → v3.0 conversion | pending | |
| 1.3 | Implement v2.1 → v3.0 conversion | pending | |
| 1.4 | Add `verified: false` marking | pending | |
| 1.5 | Add dry-run mode | pending | |
| 1.6 | Add entry point to pyproject.toml | pending | |
| 1.7 | Test with sample entries | pending | |
| 1.8 | Run migration on mapping file | pending | |
| 1.9 | Update documentation | pending | |

### Phase 2: batch.py Enhancements

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 2.1 | Implement `check_add6_alignment()` | pending | |
| 2.2 | Add alignment warnings to JSON output | pending | |
| 2.3 | Enhance human mode ADD-6 display | pending | |
| 2.4 | Add pre-populated suggestions | pending | |
| 2.5 | Test with existing batch reports | pending | |

### Phase 3: Search Tool Enhancements

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 3.1 | Add rationale query hints to search.py | pending | |
| 3.2 | Add contextual guidance to search_deep.py | pending | |
| 3.3 | Add similar ADD-6 profile suggestions | pending | |
| 3.4 | Test with representative guidelines | pending | |

### Phase 4: record.py Enhancements

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 4.1 | Add ADD-6 alignment validation | pending | |
| 4.2 | Add default value suggestions | pending | |
| 4.3 | Update help text | pending | |
| 4.4 | Test scenarios | pending | |

### Phase 5: Verification Continuation

| Batch | Guidelines | Current State | Target |
|-------|------------|---------------|--------|
| 3 | 38 | 38 v3.0 | All verified: true |
| 4 | 55 | 55 v1.1 | All v3.0 verified: true |
| 5 | 22 | 22 v1.1 | All v3.0 verified: true |
| 1 | 20 | 20 v2.1 | All v3.0 verified: true |
| 2 | 88 | 88 v2.1 | All v3.0 verified: true |

---

## Appendix A: Applicability Value Mapping

### Legacy (v1.x) to ADD-6 Aligned (v2.x/v3.x)

| Legacy Value | ADD-6 Applicability | Notes |
|--------------|---------------------|-------|
| `direct` | `yes` | Rule applies directly |
| `partial` | `partial` | Some aspects apply |
| `not_applicable` | `no` | Rule doesn't apply |
| `rust_prevents` | `no` | Rust design prevents issue |
| `unmapped` | `partial` | Default when unknown |

### Adjusted Category Inference

| Legacy Applicability | Suggested `adjusted_category` | Notes |
|---------------------|-------------------------------|-------|
| `direct` | Use ADD-6 value or `advisory` | Rule applies |
| `partial` | Use ADD-6 value or `advisory` | Partially applies |
| `not_applicable` | `n_a` | Not applicable |
| `rust_prevents` | `implicit` | Compiler enforces |

---

## Appendix B: ADD-6 Rationale Code Expansion

| Code | Full Name | Description | FLS Focus Areas |
|------|-----------|-------------|-----------------|
| `UB` | Undefined Behaviour | C undefined behavior | Unsafe code, FFI, raw pointers |
| `IDB` | Implementation-defined | Platform-specific behavior | ABI, type sizes, alignment |
| `CQ` | Code Quality | Maintainability/readability | Style, naming, structure |
| `DC` | Design Consideration | Architecture concerns | Modularity, separation |

---

## Appendix C: Tool Command Reference

### Migration

```bash
# Migrate all entries to v3.0 (dry-run)
uv run upgrade-to-v3 --standard misra-c --dry-run

# Run migration
uv run upgrade-to-v3 --standard misra-c

# Check migration results
uv run validate-standards
```

### Verification

```bash
# Check current progress
uv run check-progress --standard misra-c

# Generate batch report
uv run verify-batch --standard misra-c --batch 4 --session 3 --mode llm

# Search with ADD-6 context
uv run search-fls-deep --standard misra-c --guideline "Rule 21.3"
uv run search-fls --query "memory allocation" --for-guideline "Rule 21.3"

# Record decision
uv run record-decision --standard misra-c --batch 4 --guideline "Rule 21.3" \
    --context all_rust --applicability yes --adjusted-category advisory \
    --rationale-type direct_mapping --confidence high \
    --search-used "uuid:tool:query:count" \
    --accept-match "fls_id:title:cat:score:reason"

# Apply verification
uv run apply-verification --standard misra-c --batch 4 --session 3
```
