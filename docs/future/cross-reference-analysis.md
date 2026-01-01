# Cross-Reference Analysis Plan

> **Status:** NOT YET IMPLEMENTED
> 
> This document captures the planned approach for Pipeline 3, which will cross-reference
> MISRA-to-FLS mappings with iceoryx2-to-FLS mappings to prioritize coding guideline writing.

## Prerequisites

Before implementing this plan:
- [ ] Complete all MISRA C batch verification (Batches 1-5)
- [ ] All guidelines have `confidence: high`
- [ ] Rationale types are correctly assigned

---

## Phase 3: Generate Category Lists

### Objective

Create four output lists from the completed mapping, grouped by `fls_rationale_type`.

### Proposed Tool: `generate-guideline-categories`

**Location:** `tools/src/fls_tools/analysis/categories.py`

**Inputs:**
- `coding-standards-fls-mapping/mappings/misra_c_to_fls.json`

**Outputs:**
- `cache/analysis/skip_list.json` - `no_equivalent` guidelines
- `cache/analysis/adaptation_list.json` - `direct_mapping` + `partial_mapping` guidelines  
- `cache/analysis/alternative_list.json` - `rust_alternative` guidelines
- `cache/analysis/prevention_list.json` - `rust_prevents` guidelines

**Output Format (per list):**

```json
{
  "category": "adaptation_list",
  "description": "MISRA rules that map to Rust - need adapted guidelines",
  "generated_at": "2026-01-02T12:00:00Z",
  "count": 45,
  "guidelines": [
    {
      "guideline_id": "Rule 11.1",
      "guideline_title": "Conversions shall not be performed...",
      "fls_sections": [
        {"fls_id": "fls_xztr1kebz8bo", "fls_title": "Function Pointer Types"},
        {"fls_id": "fls_1qhsun1vyarz", "fls_title": "Type Cast Expressions"}
      ],
      "confidence": "high"
    }
  ]
}
```

---

## Phase 4: Cross-Reference with iceoryx2-FLS Mapping

### Objective

For each guideline in adaptation/alternative/prevention lists, calculate a priority score based on iceoryx2's actual usage of the relevant FLS constructs.

### Approach

For each guideline:
1. Get its `accepted_matches` (FLS section IDs)
2. Look up those FLS IDs in `iceoryx2-fls-mapping/*.json`
3. Sum the usage counts from `count` or `findings.count` fields
4. Produce a priority score

### Proposed Tool: `compute-priority-scores`

**Location:** `tools/src/fls_tools/analysis/priority.py`

**Inputs:**
- Category list files from Phase 3
- `iceoryx2-fls-mapping/*.json` files

**Output:** `cache/analysis/priority_scores.json`

```json
{
  "generated_at": "2026-01-02T12:00:00Z",
  "guidelines": [
    {
      "guideline_id": "Rule 11.1",
      "category": "adaptation_list",
      "fls_usage": [
        {"fls_id": "fls_xztr1kebz8bo", "title": "Function Pointer Types", "iceoryx2_count": 234},
        {"fls_id": "fls_1qhsun1vyarz", "title": "Type Cast Expressions", "iceoryx2_count": 1456}
      ],
      "total_iceoryx2_usage": 1690,
      "priority_tier": "high"
    }
  ]
}
```

### Priority Tier Calculation

Initial approach (may be refined):

| Tier | Criteria |
|------|----------|
| `high` | Total usage > 1000 OR category is `direct_mapping` with usage > 500 |
| `medium` | Total usage 100-1000 |
| `low` | Total usage < 100 |

### Weighting Considerations (Future Enhancement)

| Factor | Potential Weight | Notes |
|--------|------------------|-------|
| Raw FLS usage count | Base metric | Simple but may be naive |
| Category weight | `direct` > `partial` > `alternative` > `prevents` | Reflects action needed |
| Unsafe code involvement | Higher weight | Harder to verify, higher risk |
| Confidence level | Tie-breaker | Prefer high-confidence mappings |

---

## Phase 5: Generate Prioritized Guideline Writing Plan

### Objective

Produce an actionable, ordered list of guidelines to write.

### Proposed Tool: `generate-writing-plan`

**Location:** `tools/src/fls_tools/analysis/writing_plan.py`

**Inputs:**
- Priority scores from Phase 4
- Category lists from Phase 3

**Output:** `docs/guideline-writing-plan.md`

### Output Format

```markdown
# iceoryx2 Coding Guideline Writing Plan

Generated: 2026-01-02

## Summary

| Category | Count | Action |
|----------|-------|--------|
| Adaptation (direct/partial) | 45 | Write adapted MISRA guidelines |
| Alternative | 23 | Analyze if Rust mechanism needs guidelines |
| Prevention | 18 | Verify completeness, check escape hatches |
| Skip | 142 | Document as N/A in safety case |

## High Priority - Adaptation Required

### 1. Rule 11.1 - Function pointer conversions

**Priority Score:** 1690 (Function Pointer Types: 234, Type Cast Expressions: 1456)

**MISRA Concern:** Conversions shall not be performed between a pointer to a function and any other type

**FLS Sections:**
- `fls_xztr1kebz8bo` - Function Pointer Types
- `fls_1qhsun1vyarz` - Type Cast Expressions

**Suggested Rust Guideline:** [To be written]

---

### 2. Rule 21.3 - Memory allocation

**Priority Score:** 3233 (External Functions: 892, Unsafety: 2341)

...

## Medium Priority - Verify Prevention

### 1. Rule 10.4 - Arithmetic conversions

**Priority Score:** 10234 (Arithmetic Expressions)

**Prevention Mechanism:** Type system requires same types for operators

**Escape Hatches to Verify:**
- [ ] `as` casts - can bypass type checking
- [ ] `unsafe` transmute - can create invalid states

**Action:** Verify iceoryx2 usage of `as` casts in arithmetic contexts

---

## Lower Priority - Consider Rust-Specific Guidelines

### 1. Dir 4.8 - Implementation hiding

**Rust Alternative:** Visibility system (`pub`, `pub(crate)`, private-by-default)

**FLS Sections:**
- `fls_jdknpu3kf865` - Visibility
- `fls_9ucqbbd0s2yo` - Struct Types

**Consider:** Guidelines for visibility best practices in iceoryx2

---

## Skip List (No Guideline Needed)

These MISRA rules have no Rust equivalent. Document in safety case.

| Guideline | Reason |
|-----------|--------|
| Dir 4.10 | No header files in Rust |
| Rule 3.2 | No line splicing in Rust |
| Rule 4.1 | Rust escapes are unambiguous |
| ... | ... |
```

---

## Implementation Notes

### Tool Registration

Add to `tools/pyproject.toml`:

```toml
generate-guideline-categories = "fls_tools.analysis.categories:main"
compute-priority-scores = "fls_tools.analysis.priority:main"
generate-writing-plan = "fls_tools.analysis.writing_plan:main"
```

### Suggested Workflow

```bash
cd tools

# After all verification complete:
uv run generate-guideline-categories --standard misra-c
uv run compute-priority-scores --standard misra-c
uv run generate-writing-plan --standard misra-c --output ../docs/guideline-writing-plan.md
```

---

## Open Questions

1. **Weighting formula:** Should we use a more sophisticated priority calculation?

2. **Escape hatch analysis:** Should Phase 5 automatically identify potential escape hatches for `rust_prevents` guidelines, or leave that for manual review?

3. **Multi-standard support:** Should the writing plan combine all standards (MISRA C, MISRA C++, CERT) or generate separate plans?

4. **Incremental updates:** How to handle updates when iceoryx2 version changes or new verification is completed?
