# Synthetic FLS ID Methodology

This document describes how we handle FLS IDs for sections that don't have native anchors in the Ferrocene Language Specification (FLS) RST source files.

## Background

The FLS uses identifiers to mark content:

1. **Section Anchors** (`.. _fls_xxxxx:`): Mark the beginning of sections
2. **Paragraph IDs** (`:dp:`fls_xxxxx``): Mark individual paragraphs within sections

Both types are **native** FLS IDs - they exist in the FLS RST source and are authoritative.

## The Problem

When we extracted section structure from the FLS for `fls_section_mapping.json`, some sections (particularly those from `.. syntax::` blocks) don't have native FLS anchors. We need IDs for these sections to enable traceability.

## Solution: Synthetic IDs

We generate FLS-format IDs for sections without native anchors. These are called **synthetic IDs**.

### ID Format

Synthetic IDs follow the same format as native FLS IDs:
- Prefix: `fls_`
- Body: 12 alphanumeric characters (a-zA-Z0-9, mixed case)
- Generated using the same algorithm as FLS's `generate-random-ids.py`

### Collision Avoidance

Before generating synthetic IDs, we:
1. Load all native IDs from the FLS RST source (~6,000+ IDs)
2. Generate candidate IDs using random characters
3. Verify each candidate doesn't collide with any native ID

### Tracking

All synthetic IDs are tracked in `tools/synthetic_fls_ids.json`:

```json
{
  "metadata": {
    "description": "Tracks FLS IDs we generated for sections without native FLS anchors",
    "fls_id_format": "fls_ + 12 alphanumeric (a-zA-Z0-9)",
    "last_updated": "2025-12-31",
    "native_ids_checked": 6132
  },
  "synthetic_ids": {
    "fls_OhbVrpoiVgRV": {
      "fls_section": "3.0.1",
      "title": "Constant Declaration",
      "reason": "Extracted from syntax block, no native FLS anchor"
    }
  }
}
```

## Current Synthetic IDs

29 synthetic IDs have been generated for sections extracted from FLS syntax blocks:

| Section | Title | Synthetic ID |
|---------|-------|--------------|
| 3.0.1 | Constant Declaration | `fls_OhbVrpoiVgRV` |
| 3.0.2 | Enum Declaration | `fls_5IfLBcbfnoGM` |
| 3.0.3 | External Block | `fls_bJmTPSIAoCLr` |
| 3.0.4 | External Crate Import | `fls_Z3aWZkSBvrjn` |
| 3.0.5 | Function Declaration | `fls_9Wvgfygw2wMq` |
| 3.0.6 | Implementation | `fls_ZcUDIh7yfJs1` |
| 3.0.7 | Module Declaration | `fls_ON43xKmTecQo` |
| 3.0.8 | Static Declaration | `fls_Xsf2o3gyrDO1` |
| 3.0.9 | Struct Declaration | `fls_xkxwnQrS7RPe` |
| 3.0.10 | Trait Declaration | `fls_MOkIUpkDyr7O` |
| 3.0.11 | Type Alias Declaration | `fls_SJoRu1XXdo0c` |
| 3.0.12 | Union Declaration | `fls_Zuzren68K4Tu` |
| 3.0.13 | Use Import | `fls_nPFz46PDjqip` |
| 3.0.14 | Macro Rules Declaration | `fls_VJIqVLB5Lzxo` |
| 3.0.15 | Terminated Macro Invocation | `fls_iGFfWd3hjOkY` |
| 9.0.1 | Function Declaration | `fls_RBMeyyMDHqJ3` |
| 9.0.2 | Function Qualifier List | `fls_8aRUhR4IWrXP` |
| 9.0.3 | Function Parameter List | `fls_vhsBkDa9U4Uq` |
| 9.0.4 | Function Parameter | `fls_GWlG6g3Ot1OG` |
| 9.0.5 | Function Parameter Pattern | `fls_MmjxWkI9X7H6` |
| 9.0.6 | Function Parameter Variadic Part | `fls_aMuFbh7x41Zt` |
| 9.0.7 | Return Type | `fls_pdp4K8ffUF0e` |
| 9.0.8 | Function Body | `fls_WIXiiQE8JkqH` |
| 9.0.9 | Self Parameter | `fls_3MB9n7IWUSmT` |
| 9.0.10 | Shorthand Self | `fls_tzQPxC5HChpo` |
| 9.0.11 | Typed Self | `fls_evbLJoLoaeTO` |
| 10.0.1 | Constant Declaration | `fls_doe5c3veGprQ` |
| 10.0.2 | Function Declaration | `fls_FnIiU74KKEpY` |
| 10.0.3 | Type Alias Declaration | `fls_EZAmggQBwBAD` |

## Section Number Encoding

For content extracted from syntax blocks, we use the `X.0.Y` numbering pattern:

| Pattern | Meaning | Example |
|---------|---------|---------|
| `X.Y` | Standard FLS section | `8.1` (Let Statements) |
| `X.0.Y` | Syntax block extractions | `3.0.1` (Constant Declaration) |

## Validation

Run validation to ensure integrity:

```bash
uv run python tools/validate_synthetic_ids.py
```

This checks:
1. **No collisions**: Synthetic IDs don't match any native FLS IDs
2. **Format compliance**: All IDs follow `fls_[a-zA-Z0-9]{12}` pattern
3. **Mapping presence**: All synthetic IDs exist in `fls_section_mapping.json`
4. **Coverage**: All IDs used in coding standard mappings are known (native or synthetic)

## When to Add New Synthetic IDs

Add new synthetic IDs when:
1. You identify FLS content that needs traceability but lacks a native anchor
2. You extract new sections from FLS that don't have anchors

**Process**:
1. Verify the content truly lacks a native FLS ID (check RST source)
2. Generate a new ID using FLS format (random 12 alphanumeric chars)
3. Verify no collision with native IDs
4. Add to `synthetic_fls_ids.json` with section, title, and reason
5. Update `fls_section_mapping.json` with the new ID
6. Run validation to confirm

## References

- FLS Repository: https://github.com/ferrocene/specification
- FLS ID Generator: `cache/repos/fls/generate-random-ids.py`
- FLS Section Mapping: `tools/fls_section_mapping.json`
- Synthetic IDs Tracking: `tools/synthetic_fls_ids.json`
- Validation Script: `tools/validate_synthetic_ids.py`
