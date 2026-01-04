# MISRA to FLS Verification Rerun - Batches 1, 2, 3

**Date:** 2026-01-03
**Updated:** 2026-01-04
**Status:** In Progress - Schema v3.1 updates applied, resuming Batch 2

## Overview

Re-verify all guidelines in Batches 1, 2, and 3 from scratch to ensure consistency and quality of MISRA-to-FLS mappings.

### Scope

| Batch | Name | Guidelines | Description |
|-------|------|------------|-------------|
| 1 | High-score direct mappings | 20 | Direct mappings with similarity >= 0.65 |
| 2 | Not applicable | 118 | Guidelines not applicable to Rust - require FLS justification |
| 3 | Stdlib & Resources | 7 | Categories 21/22 with `applicability=yes` not in Batch 1 |
| **Total** | | **145** | |

**Remaining batches (not in scope):**
- Batch 4: Medium-score direct (55 guidelines)
- Batch 5: Edge cases (23 guidelines)

### Session Plan

- Session 1: Batch 1 (20 guidelines)
- Session 2: Batch 2 (118 guidelines)
- Session 3: Batch 3 (7 guidelines)

### Mode

Parallel decision files with merge before apply.

---

## Bug Fixes Applied (2026-01-04)

### Fix 1: scaffold.py misinterpreting v1.1 schema entries

The `scaffold.py` batch assignment logic checked `schema_ver == "1.0"` to determine
v1 vs v2 format. However, v1.1 entries (v1 structure + ADD-6 metadata) were falling
through to the v2 branch, which expected `all_rust.applicability` to exist.

Since v1.1 entries don't have `all_rust.applicability`, it defaulted to `"no"`,
incorrectly classifying 77 guidelines as `not_applicable`.

**Fix Applied:** Changed `scaffold.py` to use `is_v1_family(m)` instead of `schema_ver == "1.0"`.

### Fix 2: UUID validation at record time (prevents duplicate search reuse)

**Problem Identified:** Analysis of Batch 1 decision files revealed UUID reuse issues:
- 68 UUIDs reused within same guideline (across `all_rust` and `safe_rust` contexts)
- 1 UUID reused across different guidelines (Rule 19.2 and Rule 19.3)

Per AGENTS.md, `search-fls` UUIDs must be unique per context - only `search-fls-deep` 
UUIDs may be shared across contexts of the same guideline.

**Root Cause:** The validation was only in `merge-decisions`, which is too late.
The `--skip-uuid-validation` flag allowed bypassing this check.

**Fix Applied:**

1. **Updated `record-decision` tool** to validate UUIDs at record time:
   - **Check A (within guideline):** When recording second context, reject if any 
     `search-fls` UUIDs match those already recorded for the first context
   - **Check B (across guidelines):** Reject if any UUIDs are already used by 
     other guidelines in the batch
   - **Exception:** `search-fls-deep` UUIDs CAN be shared across contexts of same guideline

2. **Removed `--skip-uuid-validation` flag** from `merge-decisions` tool - no longer
   needed since validation happens at record time, and there are no more legacy decisions.

3. **Deleted existing Batch 1 decision files** - must re-verify all 20 guidelines
   with proper search protocol (separate keyword searches per context).

### Batch Size Changes After Fix 1

| Batch | Before Fix | After Fix | Explanation |
|-------|------------|-----------|-------------|
| 1 | 20 | 20 | No change |
| 2 | 195 | 118 | 77 v1.1 entries now correctly assigned elsewhere |
| 3 | 7 | 7 | No change (already correct) |
| 4 | 0 | 55 | v1.1 entries with medium scores |
| 5 | 1 | 23 | v1.1 entries with partial/rust_prevents |

---

## Schema v3.1 Updates (2026-01-04)

### Rationale

During verification, we identified the need to capture structured analysis summaries
in the decision files themselves for audit trail purposes. Each context needs:

1. **`misra_concern`** - The MISRA safety concern as it applies (or doesn't apply) to this context
2. **`rust_analysis`** - How Rust handles this concern in this context

These may differ between contexts:
- `all_rust`: "Union field access without tracking which field was last written causes UB"
- `safe_rust`: "Not applicable - safe Rust cannot read union fields"

### Schema Changes

**File:** `coding-standards-fls-mapping/schema/decision_file.schema.json`

1. Added `decision_file_v3_1` definition (v3.0 + required `analysis_summary`)
2. Added `analysis_summary` object definition with required `misra_concern` and `rust_analysis` strings
3. Added `context_decision_complete_v3_1` definition (requires `analysis_summary`)
4. Added `search-rust-context` to valid search tools enum
5. Updated oneOf to include v3.1

**Backward compatibility:** 
- v3.0 decisions (Batch 1) remain valid - `analysis_summary` is only required in v3.1
- New decisions (Batch 2+) will use v3.1 with required `analysis_summary`

### Tool Changes

**File:** `tools/src/fls_tools/standards/verification/record.py`

1. Added `DECISION_SCHEMA_VERSION = "3.1"` constant
2. Added `--misra-concern` parameter (required) - context-specific MISRA concern
3. Added `--rust-analysis` parameter (required) - context-specific Rust analysis
4. Updated context decision building to include `analysis_summary` object
5. Updated version handling to upgrade v3.0 → v3.1
6. Added `search-rust-context` to `VALID_SEARCH_TOOLS`

### AGENTS.md Updates

Updated the Search and Record Protocol to clarify:
- 8 search operations per guideline (context + deep + 6 keyword)
- Summary is captured in decision file via `--misra-concern` and `--rust-analysis`
- No separate "output summary to console" step needed

---

## Current State

As of 2026-01-04 (after schema v3.1 updates):

- **223 total guidelines** in mapping file
- **77 entries** are v1.1 format (v1 + ADD-6, `confidence: medium`)
- **108 entries** are v2.1 format (per-context + ADD-6, `confidence: high`)
- **38 entries** are v3.0 format (per-context + ADD-6, `confidence: high`)
- **146 entries** total have been previously verified

### Batch 1 Status: COMPLETE

- Batch report: `cache/verification/misra-c/batch1_session1.json` (v3.0, merged)
- Decision files: 20/20 complete in `cache/verification/misra-c/batch1_decisions/`
- All decisions recorded with v3.0 schema (no `analysis_summary`)
- Merge completed successfully

### Batch 2 Status: IN PROGRESS

- Batch report: `cache/verification/misra-c/batch2_session1.json` (generated)
- Decision files: 1/118 complete (Dir 4.6 done with v3.0)
- **117 remaining** - will use v3.1 schema with `analysis_summary`

### Batch 3 Status: NOT STARTED

- Guidelines: 7
- Will use v3.1 schema with `analysis_summary`

---

## Phase 1: Batch 1 Verification

**Session ID:** 1
**Guidelines:** 20
**Status:** Re-starting from scratch

### Step 1.1: Generate Batch Report

```bash
uv run verify-batch --standard misra-c --batch 1 --session 1 --mode llm
```

### Step 1.2: Verify Each Guideline

For each guideline:

1. **Validate batch membership:**
   ```bash
   uv run check-guideline --standard misra-c --guideline "Rule X.Y" --batch 1
   ```

2. **Run 5 searches:**
   ```bash
   # Step 0: Context search
   uv run search-rust-context --query "<MISRA concern>" --top 3
   
   # Step 1: Deep search (UUID can be shared across contexts)
   uv run search-fls-deep --standard misra-c --guideline "Rule X.Y"
   
   # Steps 2-4: Keyword searches (SEPARATE searches per context!)
   uv run search-fls --query "<C terminology>" --top 10 --for-guideline "Rule X.Y"
   uv run search-fls --query "<Rust terminology>" --top 10
   uv run search-fls --query "<safety concepts>" --top 10
   ```

3. **Output decision summary** (structured analysis before recording)

4. **Record decisions for both contexts (v3.1 schema):**
   
   **IMPORTANT:** Each context needs its own keyword searches. Only `search-fls-deep`
   UUID may be reused. Run new `search-fls` queries for each context.
   
   **NEW in v3.1:** `--misra-concern` and `--rust-analysis` are required for each context.
   
   ```bash
   # Record all_rust with searches from step 2
   uv run record-decision \
       --standard misra-c \
       --batch 1 \
       --guideline "Rule X.Y" \
       --context all_rust \
       --decision <decision> \
       --applicability <yes|no|partial> \
       --adjusted-category <category> \
       --rationale-type <type> \
       --confidence high \
       --misra-concern "<MISRA concern for this context - 1-2 sentences>" \
       --rust-analysis "<How Rust handles this in all_rust context - 2-4 sentences>" \
       --search-used "<context-uuid>:search-rust-context:<query>:<count>" \
       --search-used "<deep-uuid>:search-fls-deep:Rule X.Y:<count>" \
       --search-used "<kw1-uuid>:search-fls:<query1>:<count>" \
       --search-used "<kw2-uuid>:search-fls:<query2>:<count>" \
       --search-used "<kw3-uuid>:search-fls:<query3>:<count>" \
       --accept-match "<fls_id>:<title>:<category>:<score>:<reason>"
   
   # Run NEW keyword searches for safe_rust context
   uv run search-fls --query "<safe rust terminology>" --top 10
   uv run search-fls --query "<type system prevention>" --top 10
   uv run search-fls --query "<borrow checker safety>" --top 10
   
   # Record safe_rust with NEW search UUIDs (deep search UUID can be reused)
   uv run record-decision \
       --standard misra-c \
       --batch 1 \
       --guideline "Rule X.Y" \
       --context safe_rust \
       --decision <decision> \
       --applicability <yes|no|partial> \
       --adjusted-category <category> \
       --rationale-type <type> \
       --confidence high \
       --misra-concern "<MISRA concern for safe_rust - may be 'Not applicable - <reason>'>" \
       --rust-analysis "<How Rust handles this in safe_rust context - 2-4 sentences>" \
       --search-used "<deep-uuid>:search-fls-deep:Rule X.Y:<count>" \
       --search-used "<NEW-kw1-uuid>:search-fls:<query1>:<count>" \
       --search-used "<NEW-kw2-uuid>:search-fls:<query2>:<count>" \
       --search-used "<NEW-kw3-uuid>:search-fls:<query3>:<count>" \
       --accept-match "<fls_id>:<title>:<category>:<score>:<reason>"
   ```

### Step 1.3: Merge Decisions

After all 20 guidelines have decisions:

```bash
uv run merge-decisions --standard misra-c --batch 1 --session 1 --validate
```

### Step 1.4: Backup Batch 1 Artifacts

```bash
mkdir -p cache/verification-backup-2026-01-04/misra-c
cp cache/verification/misra-c/batch1_session1.json cache/verification-backup-2026-01-04/misra-c/
cp -r cache/verification/misra-c/batch1_decisions/ cache/verification-backup-2026-01-04/misra-c/
```

This preserves the batch report and decision files before proceeding to the next batch.

---

## Phase 2: Batch 2 Verification

**Session ID:** 2
**Guidelines:** 118

### Step 2.1: Generate Batch Report

```bash
uv run verify-batch --standard misra-c --batch 2 --session 2 --mode llm
```

### Step 2.2: Verify Each Guideline

Same process as Phase 1. These are "not applicable" guidelines, so most will have:
- `rationale_type: no_equivalent` or `rust_alternative`
- FLS justification explaining WHY no Rust equivalent exists

### Step 2.3: Merge Decisions

```bash
uv run merge-decisions --standard misra-c --batch 2 --session 2 --validate
```

### Step 2.4: Backup Batch 2 Artifacts

```bash
cp cache/verification/misra-c/batch2_session2.json cache/verification-backup-2026-01-04/misra-c/
cp -r cache/verification/misra-c/batch2_decisions/ cache/verification-backup-2026-01-04/misra-c/
```

---

## Phase 3: Batch 3 Verification

**Session ID:** 3
**Guidelines:** 7

### Step 3.1: Generate Batch Report

```bash
uv run verify-batch --standard misra-c --batch 3 --session 3 --mode llm
```

### Step 3.2: Verify Each Guideline

Same process as Phase 1. These are stdlib/resources guidelines (Categories 21+22), focusing on:
- C standard library functions and Rust equivalents
- Resource management (files, memory, etc.)

### Step 3.3: Merge Decisions

```bash
uv run merge-decisions --standard misra-c --batch 3 --session 3 --validate
```

### Step 3.4: Backup Batch 3 Artifacts

```bash
cp cache/verification/misra-c/batch3_session3.json cache/verification-backup-2026-01-04/misra-c/
cp -r cache/verification/misra-c/batch3_decisions/ cache/verification-backup-2026-01-04/misra-c/
```

---

## Phase 4: Stop and Check In

**DO NOT apply decisions yet.**

After all 145 guidelines have decisions recorded and merged:

1. Report completion status
2. Wait for user instructions
3. User will perform analysis comparing new decisions to current mapping file contents
4. Proceed with apply based on that analysis

### Expected Artifacts After Phase 3

Working directory:
```
cache/verification/misra-c/
  batch1_session1.json     # Batch report with verification_decision populated
  batch1_decisions/        # Individual decision files
  batch2_session2.json
  batch2_decisions/
  batch3_session3.json
  batch3_decisions/
```

Backup directory:
```
cache/verification-backup-2026-01-04/misra-c/
  batch1_session1.json
  batch1_decisions/
  batch2_session2.json
  batch2_decisions/
  batch3_session3.json
  batch3_decisions/
```

---

## Cleanup (Deferred)

Cleanup of batch reports (which contain copyrighted MISRA text) will be performed after apply, with explicit user approval:

```bash
rm cache/verification/misra-c/batch1_session1.json
rm cache/verification/misra-c/batch2_session2.json
rm cache/verification/misra-c/batch3_session3.json
rm -rf cache/verification/misra-c/batch*_decisions/
```

---

## Estimated Effort

| Batch | Guidelines | Est. Time per Guideline | Total |
|-------|------------|------------------------|-------|
| 1 | 20 | ~5-7 min (extra searches per context) | 2-3 hours |
| 2 | 118 | ~3-4 min (many similar patterns) | 6-8 hours |
| 3 | 7 | ~5-6 min | 30-45 min |

**Total estimated: 9-12 hours of verification work**
